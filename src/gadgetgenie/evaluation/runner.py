"""Gold-set evaluation of a :class:`~gadgetgenie.core.service.Recommender`.

Each gold item stores a question and a gold SQL query (or ``expect_refusal``). The
expected answer is obtained by running the gold query - through the same guard and the
same read-only executor - on the database under test, so ground truth always matches
the data. The recommender itself is called exactly as users call it (``ask``).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from importlib import resources
from pathlib import Path

from ..core.sql_guard import UnsafeSQL, check_sql
from .metrics import cumulative_by_attempt, jaccard, key_set, percentile, scalar_match


class GoldError(ValueError):
    pass


@dataclass(frozen=True)
class GoldItem:
    id: str
    question: str
    gold_sql: str = ""
    compare: str = "set"            # "set" (on `key`) or "scalar"
    key: str = "model"
    expect_refusal: bool = False


@dataclass
class ItemResult:
    id: str
    question: str
    status: str
    correct: bool
    attempts: int
    solved_at: int | None
    jaccard: float | None = None
    faithful: bool | None = None
    seconds: float = 0.0
    tokens: int = 0
    sql: str = ""
    detail: str = ""
    errors: list[str] = field(default_factory=list)


def load_gold(path: str | Path | None = None) -> list[GoldItem]:
    if path is None:
        text = (resources.files("gadgetgenie") / "evaluation" / "gold.jsonl").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    items, seen = [], set()
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        raw = json.loads(line)
        item = GoldItem(**raw)
        if item.id in seen:
            raise GoldError(f"line {n}: duplicate id {item.id}")
        if not item.expect_refusal and not item.gold_sql:
            raise GoldError(f"line {n}: {item.id} needs gold_sql or expect_refusal")
        if item.compare not in {"set", "scalar"}:
            raise GoldError(f"line {n}: unknown compare mode {item.compare}")
        seen.add(item.id)
        items.append(item)
    return items


def validate_gold(items: list[GoldItem], policy) -> None:
    """Every gold query must pass the same guard as model output (catches typos and values
    that do not exist in the data model before they become wrong ground truth)."""
    for item in items:
        if item.gold_sql:
            try:
                check_sql(item.gold_sql, policy)
            except UnsafeSQL as exc:
                raise GoldError(f"{item.id}: gold query rejected: {exc}") from exc


def evaluate(recommender, items: list[GoldItem]) -> dict:
    t2s = recommender.text2sql
    validate_gold(items, t2s.policy)
    results: list[ItemResult] = []
    for item in items:
        before = recommender.log.records[-1] if recommender.log.records else None
        started = time.perf_counter()
        answer = recommender.ask(item.question)
        seconds = round(time.perf_counter() - started, 3)
        latest = recommender.log.records[-1] if recommender.log.records else None
        record = latest if latest is not before else None
        res = ItemResult(item.id, item.question, answer.status, False, answer.attempts, None,
                         faithful=answer.faithful, seconds=seconds, tokens=record.tokens if record else 0,
                         sql=answer.sql, errors=record.errors if record else [])
        if item.expect_refusal:
            res.correct = answer.status == "refused"
        elif answer.status == "ok":
            gold = t2s.executor.run(check_sql(item.gold_sql, t2s.policy).sql, t2s.policy.max_rows)
            pred_rows = [tuple(r.get(c) for c in answer.columns) for r in answer.rows]
            if item.compare == "scalar":
                gold_value = gold.rows[0][0] if gold.rows else None
                res.correct = scalar_match(pred_rows, gold_value)
                res.detail = f"gold={gold_value!r}"
            else:
                gold_set = key_set(gold.columns, gold.rows, item.key) or set()
                pred_set = key_set(answer.columns, pred_rows, item.key)
                if pred_set is None:
                    res.detail = f"answer has no {item.key!r} column"
                    res.jaccard = 0.0
                else:
                    res.jaccard = round(jaccard(pred_set, gold_set), 3)
                    res.correct = pred_set == gold_set
        res.solved_at = res.attempts if res.correct and not item.expect_refusal else None
        results.append(res)
    return summarize(results, items, t2s.max_attempts)


def summarize(results: list[ItemResult], items: list[GoldItem], max_attempts: int) -> dict:
    data = [r for r, i in zip(results, items) if not i.expect_refusal]
    off = [r for r, i in zip(results, items) if i.expect_refusal]
    sets = [r for r, i in zip(results, items) if not i.expect_refusal and i.compare == "set"]
    latencies = [r.seconds for r in results]
    faithful = [r.faithful for r in data if r.faithful is not None]
    return {
        "items": len(results),
        "execution_accuracy": sum(r.correct for r in data) / len(data) if data else None,
        "exact_set_match": sum(r.correct for r in sets) / len(sets) if sets else None,
        "mean_jaccard": sum(r.jaccard or 0.0 for r in sets) / len(sets) if sets else None,
        "accuracy_within_attempts": cumulative_by_attempt([r.solved_at for r in data], max_attempts),
        "retry_rate": sum(r.attempts > 1 for r in results) / len(results) if results else None,
        "refusal_accuracy": sum(r.correct for r in off) / len(off) if off else None,
        "wrong_refusals": [r.id for r in data if r.status == "refused"],
        "faithful_summaries": sum(faithful) / len(faithful) if faithful else None,
        "latency_mean_s": sum(latencies) / len(latencies) if latencies else None,
        "latency_p95_s": percentile(latencies, 0.95),
        "tokens_total": sum(r.tokens for r in results),
        "results": [asdict(r) for r in results],
    }


def format_report(report: dict) -> str:
    def pct(v):
        return "n/a" if v is None else f"{100 * v:.1f}%"

    lines = [
        f"items: {report['items']}",
        f"execution accuracy: {pct(report['execution_accuracy'])}",
        f"exact-set match (recommendation lists): {pct(report['exact_set_match'])}  "
        f"mean Jaccard: {report['mean_jaccard']:.3f}" if report["mean_jaccard"] is not None else "",
        "accuracy within k attempts: " + ", ".join(f"k={k}: {pct(v)}"
                                                   for k, v in report["accuracy_within_attempts"].items()),
        f"retry rate: {pct(report['retry_rate'])}",
        f"refusal accuracy (off-topic): {pct(report['refusal_accuracy'])}",
        f"faithful summaries: {pct(report['faithful_summaries'])}",
        f"latency mean / p95: {report['latency_mean_s']:.3f}s / {report['latency_p95_s']:.3f}s",
        f"tokens: {report['tokens_total']}",
    ]
    wrong = [r for r in report["results"] if not r["correct"]]
    if wrong:
        lines.append("incorrect: " + ", ".join(r["id"] for r in wrong))
    return "\n".join(line for line in lines if line)
