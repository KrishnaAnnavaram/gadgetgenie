import json

import pytest

from gadgetgenie.core.executors import Rows
from gadgetgenie.core.llm import FakeModel, ModelError
from gadgetgenie.core.slots import extract, merge
from gadgetgenie.core.summarize import Summarizer, unsupported_numbers

ROWS = Rows(["model", "price_usd", "rating", "battery_hours"],
            [("Kestrel MidBook 3", 749.99, 4.6, None), ("Aurora BudgetBook 9", 1299.0, 4.1, 12.5)])


def test_faithful_summary_is_kept():
    model = FakeModel(["Kestrel MidBook 3 costs $749.99 with a 4.6 rating; Aurora BudgetBook 9 lasts 12.5 hours."])
    s = Summarizer(model).summarize("best laptops under $1,300", ROWS)
    assert s.faithful and not s.used_fallback and s.text.startswith("Kestrel")


def test_invented_numbers_trigger_fallback():
    model = FakeModel(["Kestrel MidBook 3 costs only $499 and lasts 20 hours."])
    s = Summarizer(model).summarize("best laptops", ROWS)
    assert not s.faithful and s.used_fallback
    assert set(s.unsupported) == {"499", "20"}
    assert "Kestrel MidBook 3" in s.text and "$749.99" in s.text


def test_formatting_variants_are_accepted():
    assert unsupported_numbers("Priced at $1,299 and $750, rated 4.6, 2 picks, 5G", ROWS, "q") == []


def test_model_sees_every_row_and_true_count():
    model = FakeModel(["Two good options."])
    Summarizer(model).summarize("q", ROWS)
    system, user, _ = model.calls[0]
    assert "(2 rows)" in system
    rows = json.loads(user.split("<rows>")[1].split("</rows>")[0])
    assert len(rows) == 2 and rows[0]["battery_hours"] is None


def test_summary_falls_back_when_model_is_down():
    s = Summarizer(FakeModel([ModelError("down")])).summarize("q", ROWS)
    assert s.used_fallback and "unknown" not in s.text.lower() or "Kestrel" in s.text


RATES = {"USD": 1.0, "INR": 0.012, "EUR": 1.1}


@pytest.mark.parametrize("question,lo,hi", [
    ("top laptops under ₹50,000", None, 600.0),
    ("phones between $200 and $400", 200.0, 400.0),
    ("laptops under 40k rupees", None, 480.0),
    ("tablets under 300 euros", None, 330.0),
    ("gaming laptops over $1000", 1000.0, None),
    ("laptops under 2 kg", None, None),
    ("phones with over 256GB storage", None, None),
    ("laptops rated above 4", None, None),
])
def test_budget_extraction(question, lo, hi):
    s = extract(question, RATES)
    assert (s.min_price_usd, s.max_price_usd) == (lo, hi)


def test_currency_without_rate_is_reported_not_guessed():
    s = extract("phones under £300", {"USD": 1.0})
    assert s.max_price_usd is None and "GBP" in s.problems[0]


def test_slots_capture_requirements():
    s = extract("cheapest 5G phone with NFC and 8GB RAM", RATES)
    assert (s.category, s.needs_5g, s.needs_nfc, s.min_ram_gb, s.sort) == ("phone", True, True, 8, "price")
    assert extract("How many smartwatches are there?").intent == "count"
    assert extract("What is the capital of France?").off_topic


def test_follow_up_inherits_category_but_unrelated_question_does_not():
    first = extract("best laptops under $900", RATES)
    follow = merge(first, extract("cheaper ones?", RATES), "cheaper ones?")
    assert follow.category == "laptop" and follow.max_price_usd == 900.0 and follow.sort == "price"
    unrelated = merge(first, extract("what is the weather?", RATES), "what is the weather?")
    assert unrelated.off_topic and unrelated.category is None
