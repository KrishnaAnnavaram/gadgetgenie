import sqlite3

import pytest

from gadgetgenie.etl.loaders import SchemaMismatchError, load_laptops, load_phones
from gadgetgenie.etl.seed import write_sqlite
from gadgetgenie.etl.units import MissingRateError, inches, size_gb, storage_split, to_flag, to_usd, weight_kg

LAPTOP_CSV = """Company,Product,TypeName,Inches,Cpu,Ram,Memory,Gpu,OpSys,Weight,Price_euros
Acme,Alpha 14,Notebook,14,Intel Core i5 8250U 1.6GHz,8GB,256GB SSD,Intel UHD Graphics 620,Windows 10,1.37kg,899
Acme,Beta 15,Gaming,15.6,AMD Ryzen 7 5800H,16GB,512GB SSD +  1TB HDD,Nvidia GeForce RTX 3060,Windows 11,2.3kg,
Acme,,Notebook,13.3,Intel,4GB,128GB Flash Storage,Intel,Linux,1.2kg,300
Acme,Gamma 13,Ultrabook,13.3,Apple M2,16GB,512GB SSD,Apple GPU,macOS,,1499
"""

PHONE_CSV = """Brand,Model_Name,Category,Announced,Price,Ram_Options,Memory_options,Display_Size_in,Supports_5G,NFC
Orbit,One,Mobile,2023 March,499,8GB,256GB,6.5,TRUE,yes
Orbit,Pad,Tab,2022,,6GB,128GB,10.9,FALSE,
"""


def test_unit_parsers():
    assert size_gb("8GB") == 8 and size_gb("1TB") == 1000 and size_gb("lots") is None
    assert storage_split("512GB SSD +  1TB HDD") == (512, 1000)
    assert storage_split("128GB Flash Storage") == (128, 0)
    assert storage_split("") == (None, None)
    assert weight_kg("1.37kg") == 1.37 and weight_kg("1370g") == 1.37 and weight_kg("") is None
    assert inches('15.6"') == 15.6 and to_flag("TRUE") == 1 and to_flag("?") is None


def test_conversion_needs_an_explicit_rate():
    assert to_usd(50000, "INR", {"INR": 0.012}) == 600.0
    with pytest.raises(MissingRateError):
        to_usd(10, "EUR", {"USD": 1.0})


def test_laptop_loader_maps_messy_headers_and_keeps_nulls(tmp_path):
    path = tmp_path / "laptops.csv"
    path.write_text(LAPTOP_CSV, encoding="utf-8")
    rows, report = load_laptops(path, source="test fixture", price_currency="EUR", rate_to_usd=1.1,
                                price_as_of="2026-01-01")
    assert report.rows_read == 4 and report.rows_loaded == 3 and len(report.rejected) == 1
    alpha, beta, gamma = rows
    assert alpha["price_usd"] == pytest.approx(988.9) and alpha["cpu_brand"] == "Intel" and alpha["cpu_ghz"] == 1.6
    assert (beta["ssd_gb"], beta["hdd_gb"], beta["dedicated_gpu"], beta["gpu_brand"]) == (512, 1000, 1, "Nvidia")
    assert beta["price_usd"] is None                       # missing price stays NULL, never an average
    assert gamma["weight_kg"] is None and gamma["cpu_brand"] == "Apple"
    assert report.missing["price_usd"] == 1 and all(r["source"] == "test fixture" for r in rows)
    assert "TypeName" in report.unmapped_headers


def test_foreign_currency_without_rate_is_an_error(tmp_path):
    path = tmp_path / "laptops.csv"
    path.write_text(LAPTOP_CSV, encoding="utf-8")
    with pytest.raises(ValueError, match="rate"):
        load_laptops(path, source="x", price_currency="EUR")


def test_phone_loader_and_category_mapping(tmp_path):
    path = tmp_path / "phones.csv"
    path.write_text(PHONE_CSV, encoding="utf-8")
    rows, report = load_phones(path, source="fixture")
    one, pad = rows
    assert (one["category"], one["release_year"], one["ram_gb"], one["supports_5g"], one["nfc"]) == \
        ("phone", 2023, 8, 1, 1)
    assert pad["category"] == "tablet" and pad["price_usd"] is None and pad["nfc"] is None


def test_missing_required_columns_fail_loudly(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("Maker,Thing\nA,B\n", encoding="utf-8")
    with pytest.raises(SchemaMismatchError, match="brand"):
        load_laptops(path, source="x")


def test_seed_builds_views_without_primary_key(tmp_path, devices):
    db = write_sqlite(devices, tmp_path / "c.db")
    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(laptops)")]
    assert "device_id" not in cols and "model" in cols
    n_laptops = sum(1 for d in devices if d["category"] == "laptop")
    assert conn.execute("SELECT COUNT(*) FROM laptops").fetchone()[0] == n_laptops
    assert conn.execute("SELECT COUNT(*) FROM devices WHERE source IS NULL").fetchone()[0] == 0
    nulls = conn.execute("SELECT COUNT(*) FROM laptops WHERE battery_hours IS NULL").fetchone()[0]
    assert nulls > 0                                       # unknown specs are kept as NULL
    conn.close()
