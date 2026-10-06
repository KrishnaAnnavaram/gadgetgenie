import json

import pytest

from gadgetgenie.core.llm import FakeModel, ModelError
from gadgetgenie.core.replies import BadReply, parse_reply
from gadgetgenie.core.text2sql import TextToSQL


def test_sql_with_quotes_and_braces_is_preserved():
    # the old fallback regex \{[^{}]*\} plus a global quote rewrite corrupted replies like this
    raw = 'Sure! {"sql": "SELECT model FROM laptops WHERE brand LIKE \'%Apple%\' AND model <> \'Kestrel\'\'s {X}\'"}'
    reply = parse_reply(raw)
    assert reply.kind == "sql"
    assert "LIKE '%Apple%'" in reply.text and "Kestrel''s {X}" in reply.text


def test_fenced_refusal_and_think_blocks():
    assert parse_reply('```json\n{"sql": "SELECT 1"}\n```').text == "SELECT 1"
    assert parse_reply('<think>{"sql": "DROP"}</think>{"error": "not about devices"}').kind == "refusal"


@pytest.mark.parametrize("raw", ["", "SELECT model FROM laptops", '{"query": "SELECT 1"}', "{'sql': 'x'}",
                                 '{"sql": ""}'])
def test_unusable_replies_raise(raw):
    with pytest.raises(BadReply):
        parse_reply(raw)


def _sql(text):
    return json.dumps({"sql": text})


def _loop(model, executor, policy, attempts=3):
    return TextToSQL(model, executor, policy, max_attempts=attempts)


def test_malformed_reply_is_retried_not_crashed(executor, policy):
    # previously: recursion without `return`, then `'sql' in None` -> TypeError -> HTTP 500
    model = FakeModel(["not json at all", '{"neither": 1}', _sql("SELECT model FROM laptops")])
    out = _loop(model, executor, policy).run("laptops")
    assert out.status == "ok" and out.solved_at == 3
    assert [a.number for a in out.attempts] == [1, 2, 3]
    assert out.attempts[0].error and out.attempts[1].error and not out.attempts[2].error


def test_feedback_contains_previous_attempt_and_error(executor, policy):
    model = FakeModel([_sql("DELETE FROM laptops"), _sql("SELECT model FROM laptops")])
    out = _loop(model, executor, policy).run("laptops")
    assert out.status == "ok" and out.solved_at == 2
    second_user_message = model.calls[1][1]
    assert "DELETE FROM laptops" in second_user_message and "only SELECT" in second_user_message


def test_attempts_are_bounded(executor, policy):
    model = FakeModel(fn=lambda s, u: _sql("SELECT * FROM laptops"))
    out = _loop(model, executor, policy, attempts=3).run("laptops")
    assert out.status == "failed" and len(model.calls) == 3 and out.solved_at is None
    assert "3 attempts" in out.message


def test_database_errors_are_fed_back(executor, policy):
    model = FakeModel([_sql("SELECT STDDEV(price_usd) FROM laptops"),  # passes the guard, fails in SQLite
                       _sql("SELECT model FROM laptops")])
    out = _loop(model, executor, policy).run("laptops")
    assert out.status == "ok" and len(out.attempts) == 2


def test_refusal_stops_without_retry(executor, policy):
    model = FakeModel(['{"error": "That is not about devices."}'])
    out = _loop(model, executor, policy).run("capital of France?")
    assert out.status == "refused" and len(model.calls) == 1


def test_model_outage_returns_cleanly(executor, policy):
    out = _loop(FakeModel([ModelError("down")]), executor, policy).run("laptops")
    assert out.status == "model_error" and "unavailable" in out.message


def test_json_mode_is_requested(executor, policy):
    model = FakeModel([_sql("SELECT model FROM laptops")])
    _loop(model, executor, policy).run("laptops")
    assert model.calls[0][2] is True
