"""Typed catalogue schema, the read-only views the model may query, and their documentation.

Base tables keep explicit units (USD, GB, inches, kg, hours, mAh), a data source and a
price date for every device. Unknown values stay NULL: nothing is filled with averages.
The model only ever sees the two views, ``laptops`` and ``phones``; the surrogate key is
not part of either view, so it can never be displayed.
"""
from __future__ import annotations

from dataclasses import dataclass

CATEGORIES = ("phone", "tablet", "smartwatch", "laptop")
PHONE_CATEGORIES = ("phone", "tablet", "smartwatch")
WIFI_STANDARDS = ("Wi-Fi 5", "Wi-Fi 6", "Wi-Fi 6E", "Wi-Fi 7")

DDL = """
CREATE TABLE IF NOT EXISTS devices (
  device_id     INTEGER PRIMARY KEY,
  category      TEXT NOT NULL CHECK (category IN ('phone', 'tablet', 'smartwatch', 'laptop')),
  brand         TEXT NOT NULL,
  model         TEXT NOT NULL UNIQUE,
  release_year  INTEGER,
  price_usd     REAL CHECK (price_usd IS NULL OR price_usd > 0),
  price_as_of   DATE,
  rating        REAL CHECK (rating IS NULL OR (rating >= 0 AND rating <= 5)),
  source        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS phone_specs (
  device_id       INTEGER PRIMARY KEY REFERENCES devices(device_id),
  os              TEXT,
  chipset         TEXT,
  ram_gb          INTEGER,
  storage_gb      INTEGER,
  display_in      REAL,
  battery_mah     INTEGER,
  main_camera_mp  REAL,
  supports_5g     SMALLINT,
  nfc             SMALLINT,
  headphone_jack  SMALLINT,
  weight_g        REAL
);

CREATE TABLE IF NOT EXISTS laptop_specs (
  device_id          INTEGER PRIMARY KEY REFERENCES devices(device_id),
  os                 TEXT,
  cpu_brand          TEXT,
  cpu_model          TEXT,
  cpu_ghz            REAL,
  ram_gb             INTEGER,
  ram_max_gb         INTEGER,
  ssd_gb             INTEGER,
  hdd_gb             INTEGER,
  gpu_brand          TEXT,
  dedicated_gpu      SMALLINT,
  screen_in          REAL,
  weight_kg          REAL,
  battery_hours      REAL,
  wifi_standard      TEXT,
  fingerprint_reader SMALLINT
);

CREATE VIEW IF NOT EXISTS laptops AS
SELECT d.brand, d.model, d.release_year, d.price_usd, d.price_as_of, d.rating,
       s.os, s.cpu_brand, s.cpu_model, s.cpu_ghz, s.ram_gb, s.ram_max_gb, s.ssd_gb, s.hdd_gb,
       s.gpu_brand, s.dedicated_gpu, s.screen_in, s.weight_kg, s.battery_hours, s.wifi_standard,
       s.fingerprint_reader
FROM devices d JOIN laptop_specs s ON s.device_id = d.device_id
WHERE d.category = 'laptop';

CREATE VIEW IF NOT EXISTS phones AS
SELECT d.category, d.brand, d.model, d.release_year, d.price_usd, d.price_as_of, d.rating,
       s.os, s.chipset, s.ram_gb, s.storage_gb, s.display_in, s.battery_mah, s.main_camera_mp,
       s.supports_5g, s.nfc, s.headphone_jack, s.weight_g
FROM devices d JOIN phone_specs s ON s.device_id = d.device_id
WHERE d.category IN ('phone', 'tablet', 'smartwatch');
"""

BASE_TABLES = ("devices", "phone_specs", "laptop_specs")


@dataclass(frozen=True)
class ViewColumn:
    name: str
    type: str
    doc: str
    values: tuple[str, ...] = ()


_COMMON = (
    ViewColumn("brand", "TEXT", "manufacturer"),
    ViewColumn("model", "TEXT", "model name (unique)"),
    ViewColumn("release_year", "INTEGER", "year of release"),
    ViewColumn("price_usd", "REAL", "list price in US dollars, NULL if unknown"),
    ViewColumn("price_as_of", "DATE", "date the price was recorded"),
    ViewColumn("rating", "REAL", "average user rating 0-5, NULL if unknown"),
    ViewColumn("os", "TEXT", "operating system"),
)

VIEWS: dict[str, tuple[ViewColumn, ...]] = {
    "laptops": _COMMON + (
        ViewColumn("cpu_brand", "TEXT", "processor brand", ("Intel", "AMD", "Apple", "Qualcomm")),
        ViewColumn("cpu_model", "TEXT", "processor model"),
        ViewColumn("cpu_ghz", "REAL", "base clock in GHz"),
        ViewColumn("ram_gb", "INTEGER", "installed RAM in GB"),
        ViewColumn("ram_max_gb", "INTEGER", "maximum RAM in GB if expandable, else NULL"),
        ViewColumn("ssd_gb", "INTEGER", "SSD capacity in GB (0 = none)"),
        ViewColumn("hdd_gb", "INTEGER", "HDD capacity in GB (0 = none)"),
        ViewColumn("gpu_brand", "TEXT", "graphics brand", ("Intel", "AMD", "Nvidia", "Apple", "Qualcomm")),
        ViewColumn("dedicated_gpu", "SMALLINT", "1 if the GPU is a dedicated card, else 0"),
        ViewColumn("screen_in", "REAL", "screen diagonal in inches"),
        ViewColumn("weight_kg", "REAL", "weight in kg"),
        ViewColumn("battery_hours", "REAL", "rated battery life in hours, NULL if unknown"),
        ViewColumn("wifi_standard", "TEXT", "Wi-Fi generation", WIFI_STANDARDS),
        ViewColumn("fingerprint_reader", "SMALLINT", "1 if it has a fingerprint reader"),
    ),
    "phones": (ViewColumn("category", "TEXT", "device type", PHONE_CATEGORIES),) + _COMMON + (
        ViewColumn("chipset", "TEXT", "system on chip"),
        ViewColumn("ram_gb", "INTEGER", "RAM in GB"),
        ViewColumn("storage_gb", "INTEGER", "built-in storage in GB"),
        ViewColumn("display_in", "REAL", "screen diagonal in inches"),
        ViewColumn("battery_mah", "INTEGER", "battery capacity in mAh"),
        ViewColumn("main_camera_mp", "REAL", "main camera resolution in megapixels"),
        ViewColumn("supports_5g", "SMALLINT", "1 if 5G is supported"),
        ViewColumn("nfc", "SMALLINT", "1 if NFC is supported"),
        ViewColumn("headphone_jack", "SMALLINT", "1 if it has a 3.5 mm jack"),
        ViewColumn("weight_g", "REAL", "weight in grams"),
    ),
}


def view_columns() -> dict[str, frozenset[str]]:
    return {name: frozenset(c.name for c in cols) for name, cols in VIEWS.items()}


def enum_values() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {}
    for cols in VIEWS.values():
        for c in cols:
            if c.values:
                out.setdefault(c.name, set()).update(c.values)
    return {k: frozenset(v) for k, v in out.items()}


def schema_doc() -> str:
    """Prompt-ready description generated from the schema (never hand-maintained)."""
    lines = []
    for name, cols in VIEWS.items():
        lines.append(f"VIEW {name}")
        for c in cols:
            vals = f" values: {', '.join(c.values)}" if c.values else ""
            lines.append(f"  {c.name} {c.type} -- {c.doc}{vals}")
    return "\n".join(lines)
