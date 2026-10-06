"""Parse the model's JSON reply: ``{"sql": "..."}`` or ``{"error": "..."}``.

The text is decoded with a real JSON decoder (``json.loads``, then ``raw_decode`` from
each ``{``), so nested braces and quotes inside SQL (``LIKE '%Apple%'``, apostrophes in
explanations) survive intact. Nothing is rewritten with regular expressions.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_THINK = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL | re.IGNORECASE)


class BadReply(ValueError):
    pass


@dataclass(frozen=True)
class Reply:
    kind: str        # "sql" or "refusal"
    text: str


def _objects(text: str):
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            yield value
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    start = text.find("{")
    while start != -1:
        try:
            value, _ = decoder.raw_decode(text, start)
            if isinstance(value, dict):
                yield value
        except json.JSONDecodeError:
            pass
        start = text.find("{", start + 1)


def parse_reply(raw: str) -> Reply:
    text = _THINK.sub("", raw or "").strip()
    if not text:
        raise BadReply("empty reply; answer with a JSON object {\"sql\": \"...\"}")
    candidates = [m.group(1).strip() for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        for obj in _objects(candidate):
            sql = obj.get("sql")
            if isinstance(sql, str) and sql.strip():
                return Reply("sql", sql.strip().rstrip(";").strip())
            err = obj.get("error")
            if isinstance(err, str) and err.strip():
                return Reply("refusal", err.strip())
    raise BadReply('reply was not a JSON object with an "sql" or "error" key; reply with JSON only')
