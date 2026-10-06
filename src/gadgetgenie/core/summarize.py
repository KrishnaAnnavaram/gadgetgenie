"""Turn the returned rows into a recommendation and check that it is faithful to them.

The model sees every row that was returned plus the true count, and is told so (an
earlier design showed it 5 rows but told it the full count). After it answers, every
number in the text must be traceable to the rows, the question or the row count;
otherwise the answer is replaced by a plain, template-based summary and flagged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from . import prompts
from .executors import Rows
from .llm import ChatModel, ModelError
from .offline import plain_summary

_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_SAFE_TOKENS = re.compile(r"\b(?:[2-5]G|Wi-?Fi\s*\d+E?|USB[- ]?C?\s*\d(?:\.\d)?|\d+(?:st|nd|rd|th))\b", re.IGNORECASE)


@dataclass
class Summary:
    text: str
    faithful: bool
    unsupported: list[str] = field(default_factory=list)
    used_fallback: bool = False


def _variants(value: float) -> set[str]:
    out = {f"{value:g}", f"{value:.2f}", f"{value:.1f}", f"{round(value)}"}
    return {v.rstrip("0").rstrip(".") if "." in v else v for v in out}


def allowed_numbers(rows: Rows, question: str) -> set[str]:
    # counts and ranks such as "top 3" or "and 5 more" never exceed the number of returned rows
    allowed: set[str] = {str(i) for i in range(len(rows.rows) + 1)}
    sources = [question]
    for row in rows.rows:
        for value in row:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                allowed |= _variants(float(value))
            elif value is not None:
                sources.append(str(value))
    for text in sources:
        for token in _NUMBER.findall(text):
            allowed |= _variants(float(token.replace(",", "")))
    return allowed


def unsupported_numbers(text: str, rows: Rows, question: str) -> list[str]:
    allowed = allowed_numbers(rows, question)
    cleaned = _SAFE_TOKENS.sub(" ", text)
    bad = []
    for token in _NUMBER.findall(cleaned):
        value = float(token.replace(",", ""))
        if not (_variants(value) & allowed):
            bad.append(token)
    return bad


class Summarizer:
    def __init__(self, model: ChatModel):
        self.model = model

    def summarize(self, question: str, rows: Rows) -> Summary:
        records = rows.records()
        system = prompts.render(prompts.SUMMARY_PROMPT, row_count=len(records),
                                truncated=", more exist" if rows.truncated else "")
        user = prompts.tag("question", question) + "\n<rows>" + json.dumps(records, default=str) + "</rows>"
        try:
            text = self.model.chat(system, user).text.strip()
        except ModelError:
            text = ""
        if not text:
            return Summary(plain_summary(records), faithful=True, used_fallback=True)
        bad = unsupported_numbers(text, rows, question)
        if bad:
            return Summary(plain_summary(records), faithful=False, unsupported=bad, used_fallback=True)
        return Summary(text, faithful=True)
