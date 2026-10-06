"""A seeded, fictional device catalogue for the offline demo and the tests.

Brands and models are invented so the demo never presents made-up specs as facts
about real products. About 8% of optional specs (and some prices and ratings) are
left NULL on purpose, to exercise the "unknown" handling end to end.
"""
from __future__ import annotations

import random

BRANDS = {
    "laptop": ("Aurora", "Kestrel", "Nimbus", "Quanta", "Volta"),
    "phone": ("Lumen", "Orion", "Pixelle", "Tidal", "Zephyr"),
    "tablet": ("Lumen", "Orion", "Tidal"),
    "smartwatch": ("Orion", "Pulse", "Zephyr"),
}
SOURCE = "synthetic demo data (gadgetgenie.etl.synthetic)"
PRICE_DATE = "2026-01-01"


def _maybe(rng: random.Random, value, p_missing: float = 0.08):
    return None if rng.random() < p_missing else value


def _laptop(rng: random.Random, brand: str, i: int) -> dict:
    tier = rng.choice(("budget", "mid", "premium", "gaming"))
    cpu_brand = rng.choice(("Intel", "AMD")) if tier != "premium" or rng.random() < 0.6 else "Apple"
    ram = {"budget": (4, 8), "mid": (8, 16), "premium": (16, 32), "gaming": (16, 32)}[tier]
    dedicated = 1 if tier == "gaming" or (tier == "mid" and rng.random() < 0.3) else 0
    if dedicated:
        gpu = "Nvidia" if rng.random() < 0.7 else "AMD"
    else:
        gpu = cpu_brand                                  # integrated graphics from the CPU vendor
    base = {"budget": 420, "mid": 780, "premium": 1450, "gaming": 1350}[tier]
    ssd = rng.choice({"budget": (128, 256), "mid": (256, 512), "premium": (512, 1000), "gaming": (512, 1000)}[tier])
    return {
        "category": "laptop", "brand": brand, "model": f"{brand} {tier.title()}Book {i}",
        "release_year": rng.randint(2021, 2025),
        "price_usd": _maybe(rng, round(base * rng.uniform(0.8, 1.3), -1) - 0.01, 0.05),
        "price_as_of": PRICE_DATE, "rating": _maybe(rng, round(rng.uniform(3.0, 5.0), 1), 0.1),
        "source": SOURCE,
        "os": "macOS" if cpu_brand == "Apple" else rng.choice(("Windows 11", "Windows 11", "ChromeOS", "Linux")),
        "cpu_brand": cpu_brand, "cpu_model": f"{cpu_brand} X{rng.randint(3, 9)}-{rng.randint(100, 999)}",
        "cpu_ghz": _maybe(rng, round(rng.uniform(1.6, 3.6), 1)),
        "ram_gb": rng.choice(ram), "ram_max_gb": _maybe(rng, rng.choice((16, 32, 64)), 0.4),
        "ssd_gb": ssd, "hdd_gb": rng.choice((0, 0, 0, 1000)) if tier in ("budget", "gaming") else 0,
        "gpu_brand": gpu, "dedicated_gpu": dedicated,
        "screen_in": rng.choice((13.3, 14.0, 15.6, 16.0, 17.3) if tier == "gaming" else (13.3, 14.0, 15.6, 16.0)),
        "weight_kg": _maybe(rng, round(rng.uniform(1.0, 1.6) if tier == "premium" else rng.uniform(1.4, 2.8), 2)),
        "battery_hours": _maybe(rng, round(rng.uniform(4, 20), 1), 0.15),
        "wifi_standard": _maybe(rng, rng.choice(("Wi-Fi 5", "Wi-Fi 6", "Wi-Fi 6", "Wi-Fi 6E", "Wi-Fi 7"))),
        "fingerprint_reader": _maybe(rng, int(rng.random() < 0.5)),
    }


def _handheld(rng: random.Random, category: str, brand: str, i: int) -> dict:
    name = {"phone": "Phone", "tablet": "Tab", "smartwatch": "Watch"}[category]
    flagship = rng.random() < 0.35
    base = {"phone": 300, "tablet": 380, "smartwatch": 180}[category] * (2.6 if flagship else 1.0)
    display = {"phone": (6.1, 6.9), "tablet": (8.3, 13.0), "smartwatch": (1.2, 2.0)}[category]
    battery = {"phone": (3800, 5500), "tablet": (6000, 10500), "smartwatch": (250, 600)}[category]
    return {
        "category": category, "brand": brand, "model": f"{brand} {name} {i}{' Pro' if flagship else ''}",
        "release_year": rng.randint(2021, 2025),
        "price_usd": _maybe(rng, round(base * rng.uniform(0.8, 1.25), -1) - 0.01, 0.05),
        "price_as_of": PRICE_DATE, "rating": _maybe(rng, round(rng.uniform(3.0, 5.0), 1), 0.1),
        "source": SOURCE, "os": rng.choice(("Android", "Android", "OrionOS")) if category != "smartwatch" else "WearOS",
        "chipset": f"Chip-{rng.randint(1, 9)}{'X' if flagship else ''}",
        "ram_gb": rng.choice((8, 12, 16) if flagship else (3, 4, 6, 8)) if category != "smartwatch" else 2,
        "storage_gb": rng.choice((256, 512) if flagship else (64, 128, 256)) if category != "smartwatch" else 32,
        "display_in": round(rng.uniform(*display), 1), "battery_mah": rng.randint(*battery) // 10 * 10,
        "main_camera_mp": _maybe(rng, rng.choice((50, 108, 200) if flagship else (12, 48, 50, 64)))
        if category != "smartwatch" else None,
        "supports_5g": int(flagship or rng.random() < 0.5) if category != "smartwatch" else 0,
        "nfc": _maybe(rng, int(flagship or rng.random() < 0.6)),
        "headphone_jack": _maybe(rng, int(not flagship and rng.random() < 0.5)) if category != "smartwatch" else 0,
        "weight_g": _maybe(rng, round(rng.uniform(*{"phone": (160, 230), "tablet": (300, 700),
                                                     "smartwatch": (30, 60)}[category]), 0)),
    }


def generate(n_laptops: int = 60, n_phones: int = 50, n_tablets: int = 15, n_watches: int = 15,
             seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    devices: list[dict] = []
    for i in range(1, n_laptops + 1):
        devices.append(_laptop(rng, rng.choice(BRANDS["laptop"]), i))
    for category, n in (("phone", n_phones), ("tablet", n_tablets), ("smartwatch", n_watches)):
        for i in range(1, n + 1):
            devices.append(_handheld(rng, category, rng.choice(BRANDS[category]), i))
    return devices
