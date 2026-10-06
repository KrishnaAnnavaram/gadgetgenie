"""Unit and currency parsing. Every parser returns ``None`` for unknown input instead of
guessing, so missing specs stay NULL and are shown as "unknown"."""
from __future__ import annotations

import re

_NUM = r"(\d+(?:\.\d+)?)"


def to_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"nan", "none", "null", "n/a", "na", "-", "unknown"}:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group()) if m else None


def to_int(value) -> int | None:
    f = to_float(value)
    return None if f is None else int(round(f))


def to_flag(value) -> int | None:
    text = str(value if value is not None else "").strip().lower()
    if text in {"1", "yes", "y", "true", "t"}:
        return 1
    if text in {"0", "no", "n", "false", "f"}:
        return 0
    return None


def size_gb(text) -> int | None:
    """``"8GB"`` -> 8, ``"1TB"`` -> 1000, ``"512 MB"`` -> 0.5 rounded to 1."""
    if text is None:
        return None
    m = re.search(_NUM + r"\s*(TB|GB|MB)", str(text), re.IGNORECASE)
    if not m:
        return None
    value, unit = float(m.group(1)), m.group(2).upper()
    factor = {"TB": 1000, "GB": 1, "MB": 0.001}[unit]
    return max(1, int(round(value * factor)))


def storage_split(text) -> tuple[int | None, int | None]:
    """``"256GB SSD + 1TB HDD"`` -> (256, 1000). Flash storage counts as SSD; parts that are
    not mentioned are 0, but an unparseable string gives (None, None)."""
    if text is None or not str(text).strip():
        return None, None
    ssd = hdd = 0
    found = False
    for part in str(text).split("+"):
        gb = size_gb(part)
        if gb is None:
            continue
        found = True
        upper = part.upper()
        if "HDD" in upper:
            hdd += gb
        elif "SSD" in upper or "FLASH" in upper or "EMMC" in upper:
            ssd += gb
        elif "HYBRID" in upper:
            hdd += gb
    return (ssd, hdd) if found else (None, None)


def weight_kg(text) -> float | None:
    if text is None:
        return None
    s = str(text).strip().lower()
    m = re.search(_NUM + r"\s*(kg|g|lbs?)\b", s)
    if m:
        value, unit = float(m.group(1)), m.group(2)
        return round({"kg": value, "g": value / 1000}.get(unit, value * 0.45359237), 3)
    return to_float(s)


def inches(text) -> float | None:
    if text is None:
        return None
    m = re.search(_NUM + r'\s*(?:"|in(?:ch(?:es)?)?\b)', str(text), re.IGNORECASE)
    return float(m.group(1)) if m else to_float(text)


_CURRENCY_SIGNS = {"$": "USD", "₹": "INR", "€": "EUR", "£": "GBP", "¥": "JPY"}
_CURRENCY_WORDS = {"usd": "USD", "dollar": "USD", "dollars": "USD", "inr": "INR", "rs": "INR", "rupee": "INR",
                   "rupees": "INR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "gbp": "GBP", "pound": "GBP",
                   "pounds": "GBP", "jpy": "JPY", "yen": "JPY"}


def detect_currency(text: str) -> str | None:
    for sign, code in _CURRENCY_SIGNS.items():
        if sign in text:
            return code
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _CURRENCY_WORDS:
            return _CURRENCY_WORDS[word]
    return None


class MissingRateError(ValueError):
    pass


def to_usd(amount: float, currency: str, rates: dict[str, float]) -> float:
    """Convert with an explicitly configured rate (USD per unit). Never guesses a rate."""
    code = currency.upper()
    if code not in rates:
        raise MissingRateError(
            f"no exchange rate configured for {code}; set FX_RATES_TO_USD as {code}=<USD per 1 {code}>")
    return round(amount * rates[code], 2)
