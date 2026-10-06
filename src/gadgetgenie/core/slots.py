"""Intent and slot extraction: category, budget (converted to USD), brands, must-haves, ordering.

Slots are passed to the model as explicit hints ("price_usd <= 600.00, converted from
INR 50,000 at 0.012 USD per INR") so budget questions in other currencies are answered in
the catalogue's currency, and the conversion is shown to the user. A currency without a
configured rate becomes a reported problem rather than a guessed number.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from ..etl.units import MissingRateError, detect_currency, to_usd

_CATEGORY_WORDS = [
    (r"\b(laptops?|notebooks?|macbooks?|ultrabooks?|chromebooks?)\b", "laptop"),
    (r"\b(smart ?watch(es)?|watch(es)?|wearables?)\b", "smartwatch"),
    (r"\b(tablets?|ipads?|tabs)\b", "tablet"),
    (r"\b(phones?|smartphones?|mobiles?|handsets?|cell ?phones?)\b", "phone"),
]
_DEVICE_WORDS = re.compile(
    r"\b(device|gadget|gpu|cpu|ram|ssd|storage|battery|camera|5g|nfc|screen|display|processor|rating|price|"
    r"brand|model|specs?|gaming)\b", re.IGNORECASE)
_AMOUNT = r"([$₹€£]?\s*\d[\d,]*(?:\.\d+)?\s*(?:k\b)?\s*(?:usd|inr|eur|gbp|dollars?|rupees?|rs\.?|euros?|pounds?)?)"


@dataclass(frozen=True)
class Slots:
    category: str | None = None
    intent: str = "recommend"                  # recommend | count | average_price
    max_price_usd: float | None = None
    min_price_usd: float | None = None
    budget_note: str = ""
    brands: tuple[str, ...] = ()
    min_ram_gb: int | None = None
    min_storage_gb: int | None = None
    needs_5g: bool = False
    needs_nfc: bool = False
    needs_dedicated_gpu: bool = False
    needs_fingerprint: bool = False
    max_weight_kg: float | None = None
    min_battery_hours: float | None = None
    wifi_standard: str | None = None
    sort: str = "rating"                       # rating | price | battery | weight
    off_topic: bool = False
    problems: tuple[str, ...] = field(default=())

    def hints(self) -> str:
        parts = []
        if self.category:
            view = "laptops" if self.category == "laptop" else "phones"
            parts.append(f"category: {self.category} (view {view}"
                         + (f", category = '{self.category}'" if view == "phones" else "") + ")")
        if self.max_price_usd is not None:
            parts.append(f"price_usd <= {self.max_price_usd:.2f}")
        if self.min_price_usd is not None:
            parts.append(f"price_usd >= {self.min_price_usd:.2f}")
        if self.budget_note:
            parts.append(self.budget_note)
        if self.brands:
            parts.append("brand in " + ", ".join(self.brands))
        for flag, text in ((self.min_ram_gb, "ram_gb >= {}"), (self.min_storage_gb, "storage >= {} GB"),
                           (self.max_weight_kg, "weight_kg <= {}"), (self.min_battery_hours, "battery_hours >= {}")):
            if flag is not None:
                parts.append(text.format(flag))
        for flag, text in ((self.needs_5g, "supports_5g = 1"), (self.needs_nfc, "nfc = 1"),
                           (self.needs_dedicated_gpu, "dedicated_gpu = 1"),
                           (self.needs_fingerprint, "fingerprint_reader = 1")):
            if flag:
                parts.append(text)
        if self.wifi_standard:
            parts.append(f"wifi_standard = '{self.wifi_standard}'")
        parts.append(f"intent: {self.intent}, order by: {self.sort}")
        return "; ".join(parts)


def _amount(text: str) -> tuple[float, str | None]:
    currency = detect_currency(text)
    number = re.search(r"\d[\d,]*(?:\.\d+)?", text)
    value = float(number.group().replace(",", "")) if number else 0.0
    if re.search(r"\d\s*k\b", text, re.IGNORECASE):
        value *= 1000
    return value, currency


_MAX_WORDS = r"under|below|less than|cheaper than|up to|upto|within|at most|max(?:imum)?|no more than"
_MIN_WORDS = r"over|above|more than|at least|minimum"
_UNIT_AFTER = re.compile(r"\s*(gb|tb|kg|hours?|hrs?|mah|inch|inches|\"|mp|ghz|stars?)\b", re.IGNORECASE)


def _price_mentions(question: str) -> list[tuple[str, str, int]]:
    """(kind, amount text, end offset) for every budget phrase in the question."""
    m = re.search(rf"between\s+{_AMOUNT}\s+(?:and|to|-)\s+{_AMOUNT}", question, re.IGNORECASE)
    if m:
        return [("min", m.group(1), m.end(1)), ("max", m.group(2), m.end(2))]
    found = []
    for kind, words in (("max", _MAX_WORDS), ("min", _MIN_WORDS)):
        for m in re.finditer(rf"\b(?:{words})\s*{_AMOUNT}", question, re.IGNORECASE):
            found.append((kind, m.group(1), m.end(1)))
    return found


def _budget(question: str, rates: dict[str, float]) -> tuple[float | None, float | None, str, list[str]]:
    lo = hi = None
    notes: list[str] = []
    problems: list[str] = []
    default_ccy = detect_currency(question) or "USD"
    for kind, raw, end in _price_mentions(question):
        if _UNIT_AFTER.match(question, end):
            continue                                  # "under 2 kg", "over 16GB": not a price
        value, ccy = _amount(raw)
        if ccy is None and value < 50:
            continue                                  # "rating above 4" is not a budget
        ccy = ccy or default_ccy
        try:
            usd = to_usd(value, ccy, rates)
        except MissingRateError as exc:
            problems.append(str(exc))
            continue
        if ccy != "USD":
            notes.append(f"{ccy} {value:,.0f} converted at {rates[ccy]} USD per {ccy} = ${usd:,.2f}")
        if kind == "max":
            hi = usd
        else:
            lo = usd
    return lo, hi, "; ".join(notes), problems


def extract(question: str, rates: dict[str, float] | None = None, known_brands: tuple[str, ...] = ()) -> Slots:
    rates = rates or {"USD": 1.0}
    q = question.lower()
    category = next((cat for pattern, cat in _CATEGORY_WORDS if re.search(pattern, q)), None)
    brands = tuple(b for b in known_brands if re.search(rf"\b{re.escape(b.lower())}\b", q))
    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", q):
        intent = "count"
    elif re.search(r"\baverage\b|\bmean\b", q) and "price" in q:
        intent = "average_price"
    else:
        intent = "recommend"
    sort = "rating"
    if re.search(r"\b(cheap(er|est)?|affordable|budget|lowest price|least expensive|inexpensive)\b", q):
        sort = "price"
    elif re.search(r"\b(battery|longest lasting)\b", q) and re.search(r"\b(best|longest|most|top)\b", q):
        sort = "battery"
    elif re.search(r"\b(lightest|light ?weight|portable)\b", q):
        sort = "weight"
    ram = re.search(r"(\d+)\s*gb\s*(?:of\s*)?ram", q)
    storage = re.search(r"(\d+)\s*(gb|tb)\s*(?:of\s*)?(?:storage|ssd)", q)
    weight = re.search(r"(?:under|below|less than|lighter than)\s*(\d+(?:\.\d+)?)\s*kg", q)
    battery = re.search(r"(?:over|more than|at least)\s*(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)", q)
    wifi = re.search(r"wi-?fi\s*(6e|6|7|5)\b", q)
    lo, hi, note, problems = _budget(question, rates)
    off_topic = category is None and not brands and not _DEVICE_WORDS.search(q) and lo is None and hi is None
    return Slots(
        category=category, intent=intent, max_price_usd=hi, min_price_usd=lo, budget_note=note, brands=brands,
        min_ram_gb=int(ram.group(1)) if ram else None,
        min_storage_gb=(int(storage.group(1)) * (1000 if storage.group(2) == "tb" else 1)) if storage else None,
        needs_5g=bool(re.search(r"\b5g\b", q)), needs_nfc=bool(re.search(r"\bnfc\b", q)),
        needs_dedicated_gpu=bool(re.search(r"\b(dedicated (gpu|graphics)|gaming|graphics card)\b", q)),
        needs_fingerprint=bool(re.search(r"\bfingerprint\b", q)),
        max_weight_kg=float(weight.group(1)) if weight else None,
        min_battery_hours=float(battery.group(1)) if battery else None,
        wifi_standard=f"Wi-Fi {wifi.group(1).upper()}" if wifi else None,
        sort=sort, off_topic=off_topic, problems=tuple(problems),
    )


_FOLLOW_UP = re.compile(r"^\s*(and|what about|how about|only|which of|cheaper|lighter|any|show|those|ones)\b",
                        re.IGNORECASE)


def merge(previous: Slots | None, current: Slots, question: str) -> Slots:
    """Carry the category and unspecified constraints over to a follow-up such as "cheaper ones?".

    Only applies when the new question names no category and either looks like a follow-up
    or mentions device constraints; an unrelated question is left alone.
    """
    if previous is None or previous.category is None or current.category is not None:
        return current
    if current.off_topic and not _FOLLOW_UP.search(question):
        return current
    inherited = {name: getattr(previous, name) for name in (
        "category", "max_price_usd", "min_price_usd", "budget_note", "brands", "min_ram_gb", "min_storage_gb",
        "max_weight_kg", "min_battery_hours", "wifi_standard") if getattr(current, name) in (None, "", ())}
    flags = {name: getattr(previous, name) or getattr(current, name) for name in (
        "needs_5g", "needs_nfc", "needs_dedicated_gpu", "needs_fingerprint")}
    return replace(current, off_topic=False, **inherited, **flags)
