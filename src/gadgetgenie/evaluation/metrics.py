"""Comparison and aggregation helpers for the evaluation harness."""
from __future__ import annotations

import math


def close(a, b, rel: float = 1e-4, abs_tol: float = 0.0051) -> bool:
    try:
        return math.isclose(float(a), float(b), rel_tol=rel, abs_tol=abs_tol)
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def key_set(columns: list[str], rows: list, key: str) -> set | None:
    """Values of ``key`` (case-insensitive column match) or None if the column is missing."""
    lowered = [c.lower() for c in columns]
    if key.lower() not in lowered:
        return None
    i = lowered.index(key.lower())
    return {row[i] for row in rows}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def scalar_match(pred_rows: list, gold_value) -> bool:
    """The gold value appears in the single predicted row (extra label columns are fine)."""
    if len(pred_rows) != 1:
        return False
    if gold_value is None:
        return any(v is None for v in pred_rows[0])
    return any(v is not None and close(v, gold_value) for v in pred_rows[0])


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))
    return ordered[idx]


def cumulative_by_attempt(solved_at: list[int | None], max_attempts: int) -> dict[str, float]:
    """Share of items answered correctly within k attempts, for k = 1..max_attempts."""
    n = len(solved_at)
    return {str(k): (sum(1 for s in solved_at if s is not None and s <= k) / n if n else 0.0)
            for k in range(1, max_attempts + 1)}
