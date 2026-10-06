"""Write device records (from the loaders or the synthetic generator) into a database."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from ..schema import DDL

DEVICE_COLUMNS = ("category", "brand", "model", "release_year", "price_usd", "price_as_of", "rating", "source")
LAPTOP_COLUMNS = ("os", "cpu_brand", "cpu_model", "cpu_ghz", "ram_gb", "ram_max_gb", "ssd_gb", "hdd_gb", "gpu_brand",
                  "dedicated_gpu", "screen_in", "weight_kg", "battery_hours", "wifi_standard", "fingerprint_reader")
PHONE_COLUMNS = ("os", "chipset", "ram_gb", "storage_gb", "display_in", "battery_mah", "main_camera_mp",
                 "supports_5g", "nfc", "headphone_jack", "weight_g")


def ddl_for(dialect: str) -> str:
    if dialect == "sqlite":
        return DDL
    return DDL.replace("CREATE VIEW IF NOT EXISTS", "CREATE OR REPLACE VIEW")   # PostgreSQL / MySQL


def _insert_all(cur, devices: list[dict], placeholder: str) -> int:
    seen: set[str] = set()
    count = 0
    for idx, dev in enumerate(devices, start=1):
        if dev["model"] in seen:                 # model names are unique; keep the first record
            continue
        seen.add(dev["model"])
        cols = ("device_id",) + DEVICE_COLUMNS
        cur.execute(f"INSERT INTO devices ({', '.join(cols)}) VALUES ({', '.join([placeholder] * len(cols))})",
                    (idx,) + tuple(dev.get(c) for c in DEVICE_COLUMNS))
        table, spec_cols = ("laptop_specs", LAPTOP_COLUMNS) if dev["category"] == "laptop" else \
            ("phone_specs", PHONE_COLUMNS)
        cols = ("device_id",) + spec_cols
        cur.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join([placeholder] * len(cols))})",
                    (idx,) + tuple(dev.get(c) for c in spec_cols))
        count += 1
    return count


def write_sqlite(devices: list[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(DDL)
        _insert_all(conn.cursor(), devices, "?")
        conn.commit()
    finally:
        conn.close()
    return path


def write_postgres(devices: list[dict], owner_dsn: str) -> int:  # pragma: no cover - needs PostgreSQL
    """Create the schema and load rows as the OWNER role (the app uses a separate read-only role)."""
    import psycopg

    with psycopg.connect(owner_dsn) as conn, conn.cursor() as cur:
        cur.execute(ddl_for("postgres"))
        n = _insert_all(cur, devices, "%s")
        conn.commit()
    return n
