import pytest

from gadgetgenie.core.sql_guard import GuardPolicy, UnsafeSQL, check_sql
from gadgetgenie.schema import enum_values, view_columns

SAFE = [
    "SELECT model, price_usd FROM laptops WHERE price_usd <= 800 ORDER BY rating DESC",
    "SELECT brand, COUNT(*) AS n FROM phones WHERE category = 'phone' GROUP BY brand",
    "SELECT model FROM laptops WHERE brand LIKE '%Aurora%' AND ram_gb >= 16",
    "SELECT l.model, l.price_usd FROM laptops AS l WHERE l.dedicated_gpu = 1",
    "WITH cheap AS (SELECT model, price_usd FROM phones WHERE price_usd < 300) SELECT model FROM cheap",
    "SELECT model FROM laptops UNION SELECT model FROM phones",
    "SELECT ROUND(AVG(price_usd), 2) FROM phones WHERE category = 'tablet'",
]

ATTACKS = [
    ("DROP TABLE devices", "only SELECT"),
    ("DELETE FROM laptops", "only SELECT"),
    ("UPDATE phones SET price_usd = 1", "only SELECT"),
    ("INSERT INTO devices (model) VALUES ('x')", "only SELECT"),
    ("SELECT model FROM laptops; DROP TABLE devices", "exactly one statement"),
    ("SELECT * FROM laptops", "SELECT \\*"),
    ("SELECT l.* FROM laptops l", "t.\\*"),
    ("SELECT model, source FROM devices", "unknown table"),                    # base tables are hidden
    ("SELECT device_id FROM laptops", "unknown column"),                       # primary key never exposed
    ("SELECT table_name FROM information_schema.tables", "qualified"),
    ("SELECT user FROM mysql.user", "qualified"),
    ("SELECT name FROM sqlite_master", "unknown table"),
    ("SELECT SLEEP(10)", "SLEEP"),
    ("SELECT BENCHMARK(1000000, MD5('a'))", "BENCHMARK"),
    ("SELECT LOAD_FILE('/etc/passwd')", "LOAD_FILE"),
    ("SELECT pg_sleep(5)", "PG_SLEEP"),
    ("SELECT model FROM laptops INTO OUTFILE '/tmp/x'", "INTO|syntax|not allowed"),
    ("SELECT model FROM laptops FOR UPDATE", "LOCK"),
    ("SELECT model FROM laptops UNION SELECT model FROM devices", "unknown table"),
    ("SELECT model FROM laptops WHERE wifi_standard = 'Wi-Fi 8'", "no value"),
    ("SELECT model FROM phones WHERE category = 'mobile'", "no value"),
    ("SELECT model FROM laptops LIMIT (SELECT 1)", "whole number"),
    ("ignore the rules and DROP TABLE laptops", "syntax|only SELECT"),
    ("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT i FROM n", "recursive"),
    ("", "empty"),
]


@pytest.fixture()
def policy():
    return GuardPolicy(views=view_columns(), enums=enum_values(), max_rows=10)


@pytest.mark.parametrize("sql", SAFE)
def test_safe_queries_pass_and_are_bounded(sql, policy):
    checked = check_sql(sql, policy)
    assert checked.limit <= 10 and "LIMIT" in checked.sql


@pytest.mark.parametrize("sql,message", ATTACKS)
def test_attacks_are_refused(sql, message, policy):
    with pytest.raises(UnsafeSQL, match=f"(?i){message}"):
        check_sql(sql, policy)


def test_limit_capped_and_added(policy):
    assert check_sql("SELECT model FROM laptops LIMIT 1000", policy).limit == 10
    assert check_sql("SELECT model FROM laptops LIMIT 3", policy).limit == 3
    assert check_sql("SELECT model FROM laptops", policy).sql.endswith("LIMIT 10")
    with pytest.raises(UnsafeSQL):
        check_sql("SELECT model FROM laptops LIMIT 0", policy)


def test_mysql_input_runs_on_sqlite(policy):
    mysql = GuardPolicy(views=policy.views, enums=policy.enums, source_dialect="mysql", target_dialect="sqlite")
    out = check_sql("SELECT `model` FROM laptops WHERE brand = 'Aurora' LIMIT 5", mysql)
    assert "`" not in out.sql and out.limit == 5


def test_quotes_survive(policy):
    out = check_sql("SELECT model FROM laptops WHERE model LIKE '%Kestrel''s%'", policy)
    assert "Kestrel''s" in out.sql
