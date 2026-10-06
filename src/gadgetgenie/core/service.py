"""The recommender service and its single factory, used by the API, the CLI and the evaluation."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Settings
from ..schema import enum_values, view_columns
from .executors import Executor, Rows
from .llm import ChatModel
from .logs import LogRecord, QueryLog
from .memory import Sessions, Turn, new_session_id, valid_session_id
from .slots import Slots, extract, merge
from .sql_guard import GuardPolicy
from .summarize import Summarizer
from .text2sql import SQLOutcome, TextToSQL

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass
class Answer:
    session_id: str
    status: str
    text: str
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    truncated: bool = False
    attempts: int = 0
    faithful: bool | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Recommender:
    def __init__(self, text2sql: TextToSQL, summarizer: Summarizer, *, rates: dict[str, float],
                 known_brands: tuple[str, ...] = (), log: QueryLog | None = None, sessions: Sessions | None = None,
                 max_question_chars: int = 500):
        self.text2sql = text2sql
        self.summarizer = summarizer
        self.rates = rates
        self.known_brands = known_brands
        self.log = log or QueryLog()
        self.sessions = sessions or Sessions()
        self.max_question_chars = max_question_chars

    def clean(self, question: str) -> str:
        text = _CONTROL.sub(" ", unicodedata.normalize("NFKC", question or "")).strip()
        if not text:
            raise ValueError("please type a question")
        if len(text) > self.max_question_chars:
            raise ValueError(f"questions are limited to {self.max_question_chars} characters")
        return text

    def slots_for(self, question: str, session_id: str | None = None) -> Slots:
        current = extract(question, self.rates, self.known_brands)
        previous = self.sessions.last(session_id) if session_id else None
        return merge(previous.slots if previous else None, current, question)

    def generate(self, question: str, session_id: str | None = None) -> tuple[Slots, SQLOutcome]:
        """Slots + SQL outcome only (no summary); used by the evaluation harness."""
        slots = self.slots_for(question, session_id)
        previous = self.sessions.last(session_id) if session_id else None
        return slots, self.text2sql.run(question, slots, previous.question if previous else "")

    def ask(self, question: str, session_id: str | None = None) -> Answer:
        sid = session_id if valid_session_id(session_id) else new_session_id()
        try:
            text = self.clean(question)
        except ValueError as exc:
            return Answer(sid, "invalid", str(exc))
        slots = self.slots_for(text, sid)
        if slots.problems:
            # never silently drop a budget we could not convert: ask for a usable one instead
            return Answer(sid, "needs_input", "I couldn't use your budget: " + "; ".join(slots.problems)
                          + ". Please give the budget in US dollars.", notes=list(slots.problems))
        slots, outcome = self.generate(text, sid)
        notes: list[str] = []
        if slots.budget_note:
            notes.append(f"Budget converted: {slots.budget_note}")
        answer = Answer(sid, outcome.status, "", sql=outcome.sql, attempts=len(outcome.attempts), notes=notes)
        if outcome.status == "ok" and outcome.rows is not None:
            summary = self.summarizer.summarize(text, outcome.rows)
            answer.text, answer.faithful = summary.text, summary.faithful
            answer.columns, answer.rows, answer.truncated = outcome.rows.columns, outcome.rows.records(), \
                outcome.rows.truncated
            if not summary.faithful:
                notes.append("The model's summary quoted numbers not in the results, so a plain summary is shown.")
        elif outcome.status == "refused":
            answer.text = (f"I can't answer that from the device catalogue ({outcome.message}). "
                           "Ask me about laptops, phones, tablets or smartwatches.")
        else:
            answer.text = "Sorry, I couldn't build a working query for that. Try rephrasing it."
        self.sessions.remember(sid, Turn(text, slots, answer.text))
        self.log.add(LogRecord(text, outcome.status, outcome.sql, len(outcome.attempts), outcome.solved_at,
                               answer.faithful, outcome.seconds, outcome.tokens,
                               [a.error for a in outcome.attempts if a.error]))
        return answer


def ensure_demo_db(path: str | Path, seed: int = 11) -> Path:
    path = Path(path)
    if not path.exists():
        from ..etl.seed import write_sqlite
        from ..etl.synthetic import generate

        write_sqlite(generate(seed=seed), path)
    return path


def make_executor(settings: Settings, auto_seed: bool = True) -> Executor:
    from . import executors

    if settings.db_backend == "postgres":
        return executors.PostgresExecutor(settings.db_dsn, settings.query_timeout_s)
    if settings.db_backend == "mysql":
        return executors.MySQLExecutor(settings.db_dsn, settings.query_timeout_s)
    if auto_seed:
        ensure_demo_db(settings.sqlite_path)
    return executors.SQLiteExecutor(settings.sqlite_path, settings.query_timeout_s)


def make_model(settings: Settings) -> ChatModel:
    if settings.llm_provider == "offline":
        from .offline import OfflineModel

        return OfflineModel(settings.max_rows)
    from .llm import OpenAICompatibleModel

    return OpenAICompatibleModel(settings.llm_base_url, settings.llm_api_key, settings.llm_model,
                                 timeout_s=settings.llm_timeout_s, seed=settings.llm_seed)


def known_brands(executor: Executor) -> tuple[str, ...]:
    """Schema linking: brand names come from the catalogue itself."""
    try:
        rows: Rows = executor.run("SELECT DISTINCT brand FROM laptops UNION SELECT DISTINCT brand FROM phones", 500)
    except Exception:  # noqa: BLE001 - brand hints are optional
        return ()
    return tuple(sorted(str(r[0]) for r in rows.rows if r[0]))


def build_recommender(settings: Settings | None = None, *, model: ChatModel | None = None,
                      executor: Executor | None = None, auto_seed: bool = True) -> Recommender:
    settings = settings or Settings.from_env()
    settings.check()
    executor = executor or make_executor(settings, auto_seed)
    model = model or make_model(settings)
    policy = GuardPolicy(views=view_columns(), enums=enum_values(), max_rows=settings.max_rows,
                         source_dialect=settings.sql_dialect, target_dialect=executor.dialect)
    return Recommender(TextToSQL(model, executor, policy, settings.max_attempts), Summarizer(model),
                       rates=settings.fx_rates_to_usd, known_brands=known_brands(executor),
                       log=QueryLog(settings.log_path or None), max_question_chars=settings.max_question_chars)
