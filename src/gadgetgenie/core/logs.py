"""Query log: one record per question with the real attempt count, outcome and timing."""
from __future__ import annotations

import json
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class LogRecord:
    question: str
    status: str
    sql: str
    attempts: int
    solved_at: int | None
    faithful: bool | None
    seconds: float
    tokens: int
    errors: list[str] = field(default_factory=list)
    ts: float = field(default_factory=time.time)


class QueryLog:
    """In-memory ring buffer, optionally mirrored to a JSONL file."""

    def __init__(self, path: str | Path | None = None, keep: int = 1000):
        self.path = Path(path) if path else None
        self.keep = keep
        self.records: list[LogRecord] = []
        self._lock = threading.Lock()

    def add(self, record: LogRecord) -> None:
        with self._lock:
            self.records.append(record)
            del self.records[:-self.keep]
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def stats(self) -> dict:
        with self._lock:
            records = list(self.records)
        n = len(records)
        by_status = Counter(r.status for r in records)
        solved = Counter(r.solved_at for r in records if r.solved_at)
        return {
            "questions": n,
            "by_status": dict(by_status),
            "solved_at_attempt": {str(k): v for k, v in sorted(solved.items())},
            "retry_rate": (sum(1 for r in records if r.attempts > 1) / n) if n else None,
            "unfaithful_answers": sum(1 for r in records if r.faithful is False),
        }
