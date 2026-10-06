"""CSV loaders that map messy source headers onto the typed schema.

* headers are matched through explicit alias lists (case/space/underscore-insensitive);
  a required column that cannot be found is an error, not a silent skip;
* every value goes through a unit parser; anything unparseable becomes NULL and is
  counted in the report (no averages are ever filled in);
* prices are converted to USD with a rate the caller supplies, and the price date and
  data source are stored with every row.
"""
from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .units import inches, size_gb, storage_split, to_flag, to_float, to_int, weight_kg


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


LAPTOP_ALIASES = {
    "brand": ["brand", "company", "manufacturer"],
    "model": ["model", "name", "product", "model_name"],
    "release_year": ["release_year", "year", "released"],
    "price": ["price", "price_euros", "price_eur", "price_usd", "price_inr"],
    "rating": ["rating", "stars", "user_rating"],
    "os": ["os", "opsys", "operating_system"],
    "cpu": ["cpu", "processor", "processor_name"],
    "ram": ["ram", "ram_gb", "memory_ram"],
    "ram_max": ["ram_max", "ram_expandable", "max_ram"],
    "storage": ["memory", "storage"],
    "ssd": ["ssd", "ssd_gb"],
    "hdd": ["hdd", "hdd_gb"],
    "gpu": ["gpu", "graphics"],
    "screen": ["inches", "screen_size", "screen", "display_size"],
    "weight": ["weight", "weight_kg"],
    "battery": ["battery_life", "battery_hours", "battery"],
    "wifi": ["wifi", "wifi_standard", "wi_fi"],
    "fingerprint": ["fingerprint", "fingerprint_reader", "fingerprint_sensor"],
}
LAPTOP_REQUIRED = ("brand", "model")

PHONE_ALIASES = {
    "category": ["category", "type", "device_type"],
    "brand": ["brand", "manufacturer"],
    "model": ["model", "model_name", "name"],
    "release_year": ["release_year", "released", "year", "announced"],
    "price": ["price", "price_usd", "price_eur", "price_inr"],
    "rating": ["rating", "stars"],
    "os": ["os", "operating_system"],
    "chipset": ["chipset", "soc"],
    "ram": ["ram", "ram_gb", "ram_options", "memory_ram"],
    "storage": ["storage", "storage_gb", "memory_options", "internal_memory"],
    "display": ["display_size_in", "display_in", "display_size", "screen_size"],
    "battery": ["battery_mah", "battery", "battery_capacity"],
    "camera": ["main_camera_mp", "main_camera_resolution", "main_camera"],
    "5g": ["supports_5g", "5g", "network_5g"],
    "nfc": ["nfc"],
    "jack": ["headphone_jack", "jack_3_5mm", "audio_jack"],
    "weight": ["weight", "weight_g"],
}
PHONE_REQUIRED = ("brand", "model")


class SchemaMismatchError(ValueError):
    pass


@dataclass
class LoadReport:
    rows_read: int = 0
    rows_loaded: int = 0
    rejected: list[str] = field(default_factory=list)
    missing: Counter = field(default_factory=Counter)
    unmapped_headers: list[str] = field(default_factory=list)


def map_headers(headers: list[str], aliases: dict[str, list[str]], required: tuple[str, ...]) -> dict[str, str]:
    by_key = {_key(h): h for h in headers}
    mapping: dict[str, str] = {}
    for field_name, names in aliases.items():
        for alias in names:
            if _key(alias) in by_key:
                mapping[field_name] = by_key[_key(alias)]
                break
    missing = [f for f in required if f not in mapping]
    if missing:
        raise SchemaMismatchError(f"required columns not found: {missing}; headers were {headers}")
    return mapping


def _cpu_brand(text: str | None) -> str | None:
    t = (text or "").lower()
    for word, brand in (("intel", "Intel"), ("amd", "AMD"), ("ryzen", "AMD"), ("apple", "Apple"),
                        ("m1", "Apple"), ("m2", "Apple"), ("m3", "Apple"), ("snapdragon", "Qualcomm")):
        if word in t:
            return brand
    return None


def _gpu(text: str | None) -> tuple[str | None, int | None]:
    t = (text or "").lower()
    if not t:
        return None, None
    if "nvidia" in t or "geforce" in t or "rtx" in t or "gtx" in t:
        return "Nvidia", 1
    if "amd" in t or "radeon" in t:
        return "AMD", 0 if "vega" in t and "rx" not in t else 1
    if "intel" in t:
        return "Intel", 0
    if "apple" in t:
        return "Apple", 0
    return None, None


def _wifi(text: str | None) -> str | None:
    t = (text or "").lower().replace(" ", "")
    for code, label in (("wi-fi7", "Wi-Fi 7"), ("wifi7", "Wi-Fi 7"), ("802.11be", "Wi-Fi 7"),
                        ("6e", "Wi-Fi 6E"), ("wi-fi6", "Wi-Fi 6"), ("wifi6", "Wi-Fi 6"), ("802.11ax", "Wi-Fi 6"),
                        ("wi-fi5", "Wi-Fi 5"), ("wifi5", "Wi-Fi 5"), ("802.11ac", "Wi-Fi 5")):
        if code in t:
            return label
    return None


def _ghz(text: str | None) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*GHz", text or "", re.IGNORECASE)
    return float(m.group(1)) if m else None


def _year(text: str | None) -> int | None:
    m = re.search(r"\b(19|20)\d{2}\b", str(text or ""))
    return int(m.group()) if m else None


def _ram(text: str | None) -> int | None:
    return size_gb(text) if re.search(r"[a-z]", text or "", re.IGNORECASE) else to_int(text)


def _price_usd(raw, currency: str, rate_to_usd: float | None) -> float | None:
    amount = to_float(raw)
    if amount is None or amount <= 0:
        return None
    if currency.upper() == "USD":
        return round(amount, 2)
    if rate_to_usd is None:
        raise ValueError(f"prices are in {currency}; pass the {currency}->USD rate used for conversion")
    return round(amount * rate_to_usd, 2)


def _note_missing(report: LoadReport, record: dict) -> None:
    for k, v in record.items():
        if v is None:
            report.missing[k] += 1


def load_laptops(path: str | Path, *, source: str, price_currency: str = "USD", rate_to_usd: float | None = None,
                 price_as_of: str | None = None) -> tuple[list[dict], LoadReport]:
    report = LoadReport()
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        mapping = map_headers(reader.fieldnames or [], LAPTOP_ALIASES, LAPTOP_REQUIRED)
        report.unmapped_headers = [h for h in reader.fieldnames or [] if h not in mapping.values()]
        for raw in reader:
            report.rows_read += 1
            get = lambda f: raw.get(mapping[f]) if f in mapping else None  # noqa: E731
            brand, model = (get("brand") or "").strip(), (get("model") or "").strip()
            if not brand or not model:
                report.rejected.append(f"row {report.rows_read}: missing brand or model")
                continue
            ssd, hdd = (to_int(get("ssd")), to_int(get("hdd"))) if "ssd" in mapping else storage_split(get("storage"))
            gpu_brand, dedicated = _gpu(get("gpu"))
            record = {
                "category": "laptop", "brand": brand, "model": model,
                "release_year": _year(get("release_year")),
                "price_usd": _price_usd(get("price"), price_currency, rate_to_usd),
                "price_as_of": price_as_of, "rating": to_float(get("rating")), "source": source,
                "os": (get("os") or "").strip() or None, "cpu_brand": _cpu_brand(get("cpu")),
                "cpu_model": (get("cpu") or "").strip() or None, "cpu_ghz": _ghz(get("cpu")),
                "ram_gb": _ram(get("ram")),
                "ram_max_gb": size_gb(get("ram_max")) or to_int(get("ram_max")),
                "ssd_gb": ssd, "hdd_gb": hdd, "gpu_brand": gpu_brand, "dedicated_gpu": dedicated,
                "screen_in": inches(get("screen")), "weight_kg": weight_kg(get("weight")),
                "battery_hours": to_float(get("battery")), "wifi_standard": _wifi(get("wifi")),
                "fingerprint_reader": to_flag(get("fingerprint")),
            }
            _note_missing(report, record)
            rows.append(record)
            report.rows_loaded += 1
    return rows, report


def _category(text: str | None) -> str:
    t = (text or "").lower()
    if "watch" in t:
        return "smartwatch"
    if "tab" in t or "ipad" in t:
        return "tablet"
    return "phone"


def load_phones(path: str | Path, *, source: str, price_currency: str = "USD", rate_to_usd: float | None = None,
                price_as_of: str | None = None) -> tuple[list[dict], LoadReport]:
    report = LoadReport()
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        mapping = map_headers(reader.fieldnames or [], PHONE_ALIASES, PHONE_REQUIRED)
        report.unmapped_headers = [h for h in reader.fieldnames or [] if h not in mapping.values()]
        for raw in reader:
            report.rows_read += 1
            get = lambda f: raw.get(mapping[f]) if f in mapping else None  # noqa: E731
            brand, model = (get("brand") or "").strip(), (get("model") or "").strip()
            if not brand or not model:
                report.rejected.append(f"row {report.rows_read}: missing brand or model")
                continue
            weight = to_float(get("weight"))
            record = {
                "category": _category(get("category")), "brand": brand, "model": model,
                "release_year": _year(get("release_year")),
                "price_usd": _price_usd(get("price"), price_currency, rate_to_usd),
                "price_as_of": price_as_of, "rating": to_float(get("rating")), "source": source,
                "os": (get("os") or "").strip() or None, "chipset": (get("chipset") or "").strip() or None,
                "ram_gb": size_gb(get("ram")) or to_int(get("ram")),
                "storage_gb": size_gb(get("storage")) or to_int(get("storage")),
                "display_in": inches(get("display")), "battery_mah": to_int(get("battery")),
                "main_camera_mp": to_float(get("camera")), "supports_5g": to_flag(get("5g")),
                "nfc": to_flag(get("nfc")), "headphone_jack": to_flag(get("jack")), "weight_g": weight,
            }
            _note_missing(report, record)
            rows.append(record)
            report.rows_loaded += 1
    return rows, report
