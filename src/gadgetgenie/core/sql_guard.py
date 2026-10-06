"""SQL guard: parse model-written SQL with sqlglot and accept only safe, bounded reads.

Checks, in order (the first failure raises :class:`UnsafeSQL` with a message the model
can act on):

1. it parses and is exactly one statement;
2. the statement is a SELECT (or UNION/INTERSECT/EXCEPT of SELECTs) and the tree has
   no write, DDL, ``INTO``, locking, ``SET``, ``PRAGMA``, ``LOAD``... node anywhere;
3. it reads only the allow-listed views (CTEs defined in the query are fine), never a
   schema-qualified object such as ``mysql.user`` or ``information_schema.tables``;
4. every column belongs to an allow-listed view or is an alias defined in the query,
   and ``*`` appears only inside ``COUNT(*)``;
5. every function is allow-listed (``SLEEP``, ``BENCHMARK``, ``LOAD_FILE``, ``pg_sleep``...
   are refused);
6. text compared with an enumerated column uses a valid value;
7. the outer query has a ``LIMIT`` no larger than ``max_rows`` (added or lowered).

The checked AST is re-rendered for the target database, so the exact statement that was
validated is the one that runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError


class UnsafeSQL(ValueError):
    """The query was refused by the guard."""


SAFE_FUNCTIONS = frozenset(
    "COUNT SUM AVG MIN MAX ROUND ABS FLOOR CEIL CEILING COALESCE IFNULL NULLIF CAST CASE IF IIF "
    "AND OR LOWER UPPER LENGTH TRIM SUBSTRING SUBSTR CONCAT GREATEST LEAST ROW_NUMBER RANK DENSE_RANK "
    "STDDEV VARIANCE".split()
)

_BANNED = tuple(
    node for node in (
        getattr(exp, name, None) for name in (
            "Insert", "Update", "Delete", "Merge", "Drop", "Create", "Alter", "AlterTable", "TruncateTable",
            "Command", "Into", "Lock", "Set", "Pragma", "Copy", "Grant", "Revoke", "Use", "LoadData",
            "Transaction", "Commit", "Rollback", "Attach", "Detach", "Analyze", "Describe", "Show",
        )
    ) if isinstance(node, type)
)


@dataclass
class GuardPolicy:
    views: dict[str, frozenset[str]]
    enums: dict[str, frozenset[str]] = field(default_factory=dict)
    max_rows: int = 10
    source_dialect: str = "sqlite"
    target_dialect: str = "sqlite"
    max_length: int = 3000


@dataclass(frozen=True)
class CheckedSQL:
    sql: str
    views: tuple[str, ...]
    limit: int


def _parse_one(sql: str, policy: GuardPolicy) -> exp.Expression:
    text = (sql or "").strip()
    if not text:
        raise UnsafeSQL("the query is empty")
    if len(text) > policy.max_length:
        raise UnsafeSQL(f"the query is longer than {policy.max_length} characters")
    try:
        trees = [t for t in sqlglot.parse(text, read=policy.source_dialect) if t is not None]
    except (ParseError, TokenError) as exc:
        raise UnsafeSQL("SQL syntax error: " + str(exc).splitlines()[0]) from exc
    if len(trees) != 1:
        raise UnsafeSQL(f"send exactly one statement (got {len(trees)})")
    return trees[0]


def _check_kind(tree: exp.Expression) -> None:
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise UnsafeSQL(f"only SELECT statements are allowed (got {tree.key.upper()})")
    banned = next((n for n in tree.walk() if isinstance(n, _BANNED)), None)
    if banned is not None:
        raise UnsafeSQL(f"{banned.key.upper()} is not allowed")
    if any(w.args.get("recursive") for w in tree.find_all(exp.With)):
        raise UnsafeSQL("recursive CTEs are not allowed")


def _check_sources(tree: exp.Expression, policy: GuardPolicy) -> dict[str, str]:
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    aliases: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeSQL("table functions are not allowed")
        if table.db or table.catalog:
            raise UnsafeSQL(f"qualified names like {table.sql()} are not allowed; use {sorted(policy.views)}")
        name = table.name.lower()
        if name in ctes:
            continue
        if name not in policy.views:
            raise UnsafeSQL(f"unknown table {name!r}; query only {sorted(policy.views)}")
        aliases[(table.alias or name).lower()] = name
    return aliases


def _check_columns(tree: exp.Expression, policy: GuardPolicy, aliases: dict[str, str]) -> None:
    known = frozenset().union(*policy.views.values())
    defined = {a.alias.lower() for a in tree.find_all(exp.Alias) if a.alias}
    for cte in tree.find_all(exp.CTE):
        alias = cte.args.get("alias")
        for col in (alias.args.get("columns") or []) if alias is not None else []:
            defined.add(col.name.lower())
    for col in tree.find_all(exp.Column):
        if isinstance(col.this, exp.Star):
            raise UnsafeSQL("name the columns you need instead of t.*")
        name, owner = col.name.lower(), col.table.lower()
        if owner in aliases:
            if name not in policy.views[aliases[owner]]:
                raise UnsafeSQL(f"{aliases[owner]} has no column {name!r}")
        elif name not in known and name not in defined:
            raise UnsafeSQL(f"unknown column {name!r}")
    for star in tree.find_all(exp.Star):
        if not isinstance(star.parent, exp.Count):
            raise UnsafeSQL("SELECT * is not allowed; name the columns you need")


def _check_functions(tree: exp.Expression) -> None:
    for fn in tree.find_all(exp.Func):
        name = fn.name.upper() if isinstance(fn, exp.Anonymous) else fn.sql_name().upper()
        if name not in SAFE_FUNCTIONS:
            raise UnsafeSQL(f"function {name} is not allowed")


def _check_literals(tree: exp.Expression, policy: GuardPolicy) -> None:
    def check(column: exp.Column, values: list[exp.Expression]) -> None:
        allowed = policy.enums.get(column.name.lower())
        for v in values:
            if allowed and isinstance(v, exp.Literal) and v.is_string and v.this not in allowed:
                raise UnsafeSQL(f"{column.name} has no value {v.this!r}; use one of {sorted(allowed)}")

    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In):
        if isinstance(node, exp.In):
            if isinstance(node.this, exp.Column):
                check(node.this, list(node.expressions))
            continue
        for side, other in ((node.this, node.expression), (node.expression, node.this)):
            if isinstance(side, exp.Column):
                check(side, [other])


def _bound(tree: exp.Expression, max_rows: int) -> int:
    clause = tree.args.get("limit")
    if clause is None:
        n = max_rows
    else:
        value = clause.args.get("count") if isinstance(clause, exp.Fetch) else clause.expression
        if not (isinstance(value, exp.Literal) and not value.is_string and str(value.this).isdigit()):
            raise UnsafeSQL("LIMIT must be a whole number")
        n = min(int(value.this), max_rows)
    if n < 1:
        raise UnsafeSQL("LIMIT must be at least 1")
    tree.set("limit", exp.Limit(expression=exp.Literal.number(n)))
    return n


def check_sql(sql: str, policy: GuardPolicy) -> CheckedSQL:
    tree = _parse_one(sql, policy)
    _check_kind(tree)
    aliases = _check_sources(tree, policy)
    _check_columns(tree, policy, aliases)
    _check_functions(tree)
    _check_literals(tree, policy)
    limit = _bound(tree, policy.max_rows)
    rendered = tree.sql(dialect=policy.target_dialect, comments=False)
    return CheckedSQL(sql=rendered, views=tuple(sorted(set(aliases.values()))), limit=limit)
