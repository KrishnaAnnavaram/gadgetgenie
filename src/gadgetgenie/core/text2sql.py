"""The text-to-SQL loop: ask (JSON mode) -> parse -> guard -> execute, retried a fixed number of times.

* Iterative: a ``for`` loop over attempt numbers, so every outcome (success, refusal,
  exhausted attempts, model outage) returns a value; nothing recurses.
* A malformed reply, a guard rejection or a database error is fed back to the model
  as the "previous attempt" for the next try.
* A deliberate ``{"error": ...}`` refusal (off-topic question) ends the loop without retrying.
* Every attempt is recorded with its real attempt number.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..schema import schema_doc
from . import prompts
from .executors import ExecutionError, Executor, Rows
from .llm import ChatModel, ModelError
from .replies import BadReply, parse_reply
from .slots import Slots
from .sql_guard import GuardPolicy, UnsafeSQL, check_sql


@dataclass
class AttemptLog:
    number: int
    raw_reply: str
    sql: str = ""
    error: str = ""


@dataclass
class SQLOutcome:
    status: str                         # "ok" | "refused" | "failed" | "model_error"
    sql: str = ""
    rows: Rows | None = None
    message: str = ""
    attempts: list[AttemptLog] = field(default_factory=list)
    tokens: int = 0
    seconds: float = 0.0

    @property
    def solved_at(self) -> int | None:
        return len(self.attempts) if self.status == "ok" else None


class TextToSQL:
    def __init__(self, model: ChatModel, executor: Executor, policy: GuardPolicy, max_attempts: int = 3):
        self.model = model
        self.executor = executor
        self.policy = policy
        self.max_attempts = max_attempts
        self.system = prompts.render(prompts.SQL_PROMPT, dialect=policy.source_dialect, schema=schema_doc(),
                                     max_rows=policy.max_rows)

    def _user_message(self, question: str, slots: Slots | None, context: str, last: AttemptLog | None) -> str:
        parts = [prompts.tag("question", question)]
        if slots is not None:
            parts.append(prompts.tag("hints", slots.hints()))
        if context:
            parts.append(prompts.tag("previous_question", context))
        if last is not None:
            parts.append("Your previous attempt failed. Fix it.\n"
                         + prompts.tag("previous_reply", last.raw_reply[:1500]) + "\n"
                         + prompts.tag("error", last.error))
        return "\n".join(parts)

    def run(self, question: str, slots: Slots | None = None, context: str = "") -> SQLOutcome:
        started = time.perf_counter()
        outcome = SQLOutcome(status="failed")
        last: AttemptLog | None = None
        for number in range(1, self.max_attempts + 1):
            try:
                completion = self.model.chat(self.system, self._user_message(question, slots, context, last),
                                             json_mode=True)
            except ModelError as exc:
                outcome.status, outcome.message = "model_error", f"the language model is unavailable ({exc})"
                break
            outcome.tokens += completion.prompt_tokens + completion.completion_tokens
            attempt = AttemptLog(number, completion.text)
            outcome.attempts.append(attempt)
            try:
                reply = parse_reply(completion.text)
                if reply.kind == "refusal":
                    outcome.status, outcome.message = "refused", reply.text
                    break
                checked = check_sql(reply.text, self.policy)
                attempt.sql = checked.sql
                rows = self.executor.run(checked.sql, self.policy.max_rows)
            except (BadReply, UnsafeSQL, ExecutionError) as exc:
                attempt.error = str(exc)
                last = attempt
                continue
            outcome.status, outcome.sql, outcome.rows = "ok", checked.sql, rows
            break
        else:
            outcome.message = f"no valid query after {self.max_attempts} attempts: {last.error if last else ''}"
        outcome.seconds = round(time.perf_counter() - started, 3)
        return outcome
