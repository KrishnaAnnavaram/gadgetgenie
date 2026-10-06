import json

import httpx
import pytest

from gadgetgenie.config import Settings, parse_rates
from gadgetgenie.core.llm import ModelError, OpenAICompatibleModel


def test_rates_parsing():
    assert parse_rates("INR=0.012, eur=1.08") == {"INR": 0.012, "EUR": 1.08, "USD": 1.0}
    with pytest.raises(ValueError):
        parse_rates("INR")
    with pytest.raises(ValueError):
        parse_rates("INR=-1")


def test_defaults_and_checks(monkeypatch):
    for name in ("LLM_API_KEY", "LLM_PROVIDER", "DB_BACKEND", "DB_DSN", "FX_RATES_TO_USD"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env(env_file=None)
    assert s.llm_provider == "offline" and s.db_dsn == "" and s.api_token == ""
    s.check()
    assert "api_key" not in repr(s) and "db_dsn" not in repr(s)
    monkeypatch.setenv("DB_BACKEND", "mysql")
    with pytest.raises(ValueError, match="DB_DSN"):
        Settings.from_env(env_file=None).check()


def _model(handler, **kw):
    return OpenAICompatibleModel("http://llm.test/v1", "key", "m", client=httpx.Client(
        transport=httpx.MockTransport(handler)), sleep=lambda s: None, **kw)


def test_request_is_deterministic_and_uses_json_mode():
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"sql": "SELECT 1"}'}}],
                                         "usage": {"prompt_tokens": 12, "completion_tokens": 3}})

    out = _model(handler, seed=42).chat("sys", "user", json_mode=True)
    assert out.text == '{"sql": "SELECT 1"}' and out.prompt_tokens == 12
    assert seen["temperature"] == 0 and seen["seed"] == 42 and seen["response_format"] == {"type": "json_object"}


def test_transient_errors_retry_a_fixed_number_of_times():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429)

    with pytest.raises(ModelError, match="429"):
        _model(handler, retries=2).chat("s", "u")
    assert len(calls) == 3


def test_auth_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401)

    with pytest.raises(ModelError):
        _model(handler).chat("s", "u")
    assert len(calls) == 1


def test_rate_limiter_window():
    from gadgetgenie.api.app import RateLimiter

    rl = RateLimiter(2)
    assert rl.allow("a", 0) and rl.allow("a", 1) and not rl.allow("a", 2)
    assert rl.allow("b", 2) and rl.allow("a", 62)
