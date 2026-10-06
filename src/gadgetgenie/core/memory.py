"""Per-session conversation state, kept server-side and keyed by random session IDs.

Nothing here flushes on every request: a session keeps its last question and slots so a
follow-up like "cheaper ones?" can reuse the category and constraints.
"""
from __future__ import annotations

import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .slots import Slots


def new_session_id() -> str:
    return secrets.token_hex(16)


def valid_session_id(value: str | None) -> bool:
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


@dataclass
class Turn:
    question: str
    slots: Slots
    answer: str


class Sessions:
    def __init__(self, capacity: int = 2000):
        self.capacity = capacity
        self._turns: OrderedDict[str, Turn] = OrderedDict()
        self._lock = threading.Lock()

    def last(self, session_id: str) -> Turn | None:
        with self._lock:
            return self._turns.get(session_id)

    def remember(self, session_id: str, turn: Turn) -> None:
        with self._lock:
            self._turns.pop(session_id, None)
            self._turns[session_id] = turn
            while len(self._turns) > self.capacity:
                self._turns.popitem(last=False)
