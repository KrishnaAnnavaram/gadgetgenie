"""Read-only database access with a row cap and a statement timeout.

The app's account must be read-only in production (see ``deploy/``); the executors add a
second layer so that a query that somehow slipped past the guard still cannot write.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from ..schema import BASE_TABLES, VIEWS


class ExecutionError(RuntimeError):
    pass


@dataclass
class Rows:
    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    meta: dict = field(default_factory=dict)

    def records(self) -> list[dict]:
        return [dict(zip(self.columns, (_plain(v) for v in r))) for r in self.rows]


def _plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class Executor(Protocol):
    dialect: str

    def run(self, sql: str, max_rows: int) -> Rows: ...


class SQLiteExecutor:
    dialect = "sqlite"
    _OK = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}

    def __init__(self, path: str | Path, timeout_s: float = 5.0):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"no database at {self.path}; run `gadgetgenie seed` first")
        self.timeout_s = timeout_s
        self.readable = {n.lower() for n in (*BASE_TABLES, *VIEWS)}

    def _authorize(self, action, arg1, arg2, _db, _src):
        if action not in self._OK:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_READ and arg1 and arg1.lower() not in self.readable:
            return sqlite3.SQLITE_DENY
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in {"load_extension", "readfile", "writefile"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def run(self, sql: str, max_rows: int) -> Rows:
        conn = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True, check_same_thread=False)
        try:
            conn.execute("PRAGMA query_only = 1")
            conn.set_authorizer(self._authorize)
            stop_at = time.monotonic() + self.timeout_s
            conn.set_progress_handler(lambda: int(time.monotonic() > stop_at), 2000)
            try:
                cursor = conn.execute(sql)
                fetched = cursor.fetchmany(max_rows + 1)
            except sqlite3.Error as exc:
                message = str(exc)
                if "interrupted" in message.lower():
                    message = f"query took longer than {self.timeout_s:g} s and was stopped"
                raise ExecutionError(message) from exc
            names = [d[0] for d in cursor.description or ()]
            return Rows(names, [tuple(r) for r in fetched[:max_rows]], truncated=len(fetched) > max_rows)
        finally:
            conn.close()


class PostgresExecutor:  # pragma: no cover - requires a PostgreSQL server
    dialect = "postgres"

    def __init__(self, dsn: str, timeout_s: float = 5.0):
        self.dsn, self.timeout_s = dsn, timeout_s

    def run(self, sql: str, max_rows: int) -> Rows:
        import psycopg

        try:
            with psycopg.connect(self.dsn) as conn:
                conn.read_only = True
                with conn.cursor() as cur:
                    cur.execute(f"SET LOCAL statement_timeout = {int(self.timeout_s * 1000)}")
                    cur.execute(sql)
                    fetched = cur.fetchmany(max_rows + 1)
                    names = [d.name for d in cur.description or ()]
                conn.rollback()
        except psycopg.Error as exc:
            raise ExecutionError(str(exc).strip().splitlines()[0]) from exc
        return Rows(names, [tuple(r) for r in fetched[:max_rows]], truncated=len(fetched) > max_rows)


class MySQLExecutor:  # pragma: no cover - requires a MySQL server
    dialect = "mysql"

    def __init__(self, dsn: str, timeout_s: float = 5.0):
        from urllib.parse import unquote, urlparse

        u = urlparse(dsn)                     # mysql://user:password@host:3306/database
        self._params = {"host": u.hostname or "localhost", "port": u.port or 3306, "user": unquote(u.username or ""),
                        "password": unquote(u.password or ""), "database": (u.path or "/").lstrip("/")}
        self.timeout_s = timeout_s

    def run(self, sql: str, max_rows: int) -> Rows:
        import pymysql

        try:
            conn = pymysql.connect(**self._params, autocommit=False, read_timeout=int(self.timeout_s) + 1)
            try:
                with conn.cursor() as cur:
                    cur.execute("SET SESSION TRANSACTION READ ONLY")
                    cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(self.timeout_s * 1000)}")
                    cur.execute("START TRANSACTION READ ONLY")
                    cur.execute(sql)
                    fetched = cur.fetchmany(max_rows + 1)
                    names = [d[0] for d in cur.description or ()]
                conn.rollback()
            finally:
                conn.close()
        except pymysql.MySQLError as exc:
            raise ExecutionError(str(exc)) from exc
        return Rows(names, [tuple(r) for r in fetched[:max_rows]], truncated=len(fetched) > max_rows)
