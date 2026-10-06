import pytest

from gadgetgenie.core.executors import ExecutionError, SQLiteExecutor


def test_reads_through_views(executor):
    rows = executor.run("SELECT COUNT(*) FROM laptops", 5)
    assert rows.rows[0][0] == 40


@pytest.mark.parametrize("sql", [
    "DELETE FROM devices",
    "UPDATE devices SET price_usd = 1",
    "DROP VIEW laptops",
    "INSERT INTO devices (category, brand, model, source) VALUES ('laptop', 'x', 'y', 'z')",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT sql FROM sqlite_master",
    "PRAGMA writable_schema = ON",
])
def test_writes_and_catalog_reads_blocked_without_guard(executor, sql):
    with pytest.raises(ExecutionError):
        executor.run(sql, 5)
    assert executor.run("SELECT COUNT(*) FROM laptops", 5).rows[0][0] == 40


def test_timeout(db_path):
    slow = SQLiteExecutor(db_path, timeout_s=0.2)
    with pytest.raises(ExecutionError, match="longer than"):
        slow.run("SELECT COUNT(*) FROM laptops a, laptops b, laptops c, laptops d, laptops e", 5)


def test_recursive_ctes_are_denied(executor):
    with pytest.raises(ExecutionError, match="not authorized"):
        executor.run("WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT MAX(i) FROM n", 5)


def test_row_cap(executor):
    rows = executor.run("SELECT model FROM laptops", 7)
    assert len(rows.rows) == 7 and rows.truncated


def test_missing_db_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="seed"):
        SQLiteExecutor(tmp_path / "none.db")
