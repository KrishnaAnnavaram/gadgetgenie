"""Rule-based stand-in for the chat model (offline demo, smoke tests, CI).

It turns the extracted slots into SQL and writes a plain summary. Its output goes through
the same JSON parsing, SQL guard, read-only execution and faithfulness check as a real
model's, so the demo exercises the whole pipeline. It understands only what the slot
extractor understands.
"""
from __future__ import annotations

import json
import re

from .llm import Completion
from .slots import extract

_QUESTION = re.compile(r"<question>(.*?)</question>", re.DOTALL)
_ROWS = re.compile(r"<rows>(.*?)</rows>", re.DOTALL)
_HINT_BRANDS = re.compile(r"brand in ([^;]+)")
_HINT_PRICE = re.compile(r"price_usd (<=|>=) ([\d.]+)")
_HINT_CATEGORY = re.compile(r"category: (\w+)")

LAPTOP_COLUMNS = "brand, model, price_usd, rating, ram_gb, ssd_gb, gpu_brand, weight_kg, battery_hours"
PHONE_COLUMNS = "brand, model, category, price_usd, rating, ram_gb, storage_gb, battery_mah, supports_5g"
ORDER = {
    "rating": "rating IS NULL, rating DESC, price_usd",
    "price": "price_usd IS NULL, price_usd ASC, rating DESC",
    "battery": "battery_hours IS NULL, battery_hours DESC",
    "weight": "weight_kg IS NULL, weight_kg ASC",
}


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_sql(question: str, hints: str, max_rows: int = 10) -> dict:
    slots = extract(question)
    category_hint = _HINT_CATEGORY.search(hints)
    category = slots.category or (category_hint.group(1) if category_hint else None)
    if category is None:
        return {"error": "I can only help with laptops, phones, tablets and smartwatches."}
    laptop = category == "laptop"
    view = "laptops" if laptop else "phones"
    where: list[str] = [] if laptop else [f"category = {_quote(category)}"]
    for op, value in _HINT_PRICE.findall(hints):
        where.append(f"price_usd {op} {float(value):.2f}")
    brands = _HINT_BRANDS.search(hints)
    if brands:
        names = [b.strip() for b in brands.group(1).split(",") if b.strip()]
        where.append(f"brand IN ({', '.join(_quote(b) for b in names)})")
    if slots.min_ram_gb:
        where.append(f"ram_gb >= {slots.min_ram_gb}")
    if slots.min_storage_gb:
        where.append(f"{'ssd_gb' if laptop else 'storage_gb'} >= {slots.min_storage_gb}")
    if laptop:
        if slots.needs_dedicated_gpu or "dedicated_gpu = 1" in hints:
            where.append("dedicated_gpu = 1")
        if slots.needs_fingerprint:
            where.append("fingerprint_reader = 1")
        if slots.max_weight_kg:
            where.append(f"weight_kg < {slots.max_weight_kg}")
        if slots.min_battery_hours:
            where.append(f"battery_hours >= {slots.min_battery_hours}")
        if slots.wifi_standard:
            where.append(f"wifi_standard = {_quote(slots.wifi_standard)}")
    else:
        if slots.needs_5g or "supports_5g = 1" in hints:
            where.append("supports_5g = 1")
        if slots.needs_nfc:
            where.append("nfc = 1")
    clause = f" WHERE {' AND '.join(where)}" if where else ""
    if slots.intent == "count":
        return {"sql": f"SELECT COUNT(*) AS devices FROM {view}{clause}"}
    if slots.intent == "average_price":
        return {"sql": f"SELECT ROUND(AVG(price_usd), 2) AS average_price_usd FROM {view}{clause}"}
    sort = slots.sort if slots.sort in ORDER else "rating"
    if sort == "battery" and not laptop:
        order = "battery_mah IS NULL, battery_mah DESC"
    elif sort == "weight" and not laptop:
        order = ORDER["rating"]
    else:
        order = ORDER[sort]
    columns = LAPTOP_COLUMNS if laptop else PHONE_COLUMNS
    return {"sql": f"SELECT {columns} FROM {view}{clause} ORDER BY {order} LIMIT {max_rows}"}


def _fmt(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".") if value != int(value) else f"{int(value):,}"
    return str(value)


def plain_summary(rows: list[dict]) -> str:
    if not rows:
        return "Nothing in the catalogue matched. Try relaxing the budget or one of the requirements."
    if len(rows) == 1 and len(rows[0]) == 1:
        (key, value), = rows[0].items()
        return f"{key.replace('_', ' ').capitalize()}: {_fmt(value)}."
    parts = []
    for row in rows[:5]:
        name = row.get("model") or ", ".join(f"{k} {_fmt(v)}" for k, v in row.items())
        extra = []
        if "price_usd" in row:
            extra.append("price unknown" if row["price_usd"] is None else f"${_fmt(row['price_usd'])}")
        if "rating" in row:
            extra.append(f"rating {_fmt(row['rating'])}")
        parts.append(f"{name} ({', '.join(extra)})" if extra else str(name))
    more = f" and {len(rows) - 5} more" if len(rows) > 5 else ""
    return f"Top matches: {'; '.join(parts)}{more}."


class OfflineModel:
    name = "offline-rules"

    def __init__(self, max_rows: int = 10):
        self.max_rows = max_rows

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> Completion:
        question_match = _QUESTION.search(user)
        question = question_match.group(1) if question_match else user
        if system.startswith("TASK: sql"):
            hints = re.search(r"<hints>(.*?)</hints>", user, re.DOTALL)
            return Completion(json.dumps(build_sql(question, hints.group(1) if hints else "", self.max_rows)))
        if system.startswith("TASK: summary"):
            rows_match = _ROWS.search(user)
            rows = json.loads(rows_match.group(1)) if rows_match else []
            return Completion(plain_summary(rows))
        return Completion("")
