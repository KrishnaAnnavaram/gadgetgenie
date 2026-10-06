"""Chat-model interface with real JSON mode, deterministic settings and bounded retries."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

import httpx


class ModelError(RuntimeError):
    pass


@dataclass
class Completion:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ChatModel(Protocol):
    name: str

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> Completion: ...


class OpenAICompatibleModel:
    """Any ``/chat/completions`` endpoint (Groq, OpenAI, vLLM, Ollama ...).

    ``temperature=0`` and a fixed ``seed`` make runs as repeatable as the provider allows,
    and ``json_mode`` really sets ``response_format``. Transient HTTP errors are retried a
    fixed number of times in a loop.
    """

    _TRANSIENT = {408, 429, 500, 502, 503, 504}

    def __init__(self, base_url: str, api_key: str, model: str, *, timeout_s: float = 30.0, seed: int = 7,
                 retries: int = 2, client: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep):
        if not api_key:
            raise ValueError("LLM_API_KEY is required for the OpenAI-compatible provider")
        self.name = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model, self._seed, self._retries = model, seed, max(0, retries)
        self._client = client or httpx.Client(timeout=timeout_s)
        self._sleep = sleep

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> Completion:
        body = {"model": self._model, "temperature": 0, "seed": self._seed,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        problem = ""
        for attempt in range(self._retries + 1):
            try:
                response = self._client.post(self._url, json=body, headers=self._headers)
            except httpx.HTTPError as exc:
                problem = type(exc).__name__
            else:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        usage = data.get("usage") or {}
                        return Completion(data["choices"][0]["message"]["content"] or "",
                                          int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        raise ModelError("unexpected response from the model API") from exc
                problem = f"HTTP {response.status_code}"
                if response.status_code not in self._TRANSIENT:
                    break
            if attempt < self._retries:
                self._sleep(min(1.5 * 2 ** attempt, 8.0))
        raise ModelError(f"model API failed: {problem}")


@dataclass
class FakeModel:
    """Test double. ``script`` items are returned (or raised) in order; ``fn(system, user)`` after that."""

    script: list = field(default_factory=list)
    fn: Callable[[str, str], str] | None = None
    name: str = "fake"
    calls: list[tuple[str, str, bool]] = field(default_factory=list)

    def chat(self, system: str, user: str, *, json_mode: bool = False) -> Completion:
        self.calls.append((system, user, json_mode))
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, BaseException):
                raise item
            return Completion(item, 10, 5)
        if self.fn is not None:
            return Completion(self.fn(system, user), 10, 5)
        raise ModelError("FakeModel script exhausted")
