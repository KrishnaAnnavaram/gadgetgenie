"""Configuration from environment variables. One ``Settings`` object is shared by the
API, the CLI and the evaluation harness; secrets have no defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def read_env_file(path: str | os.PathLike = ".env") -> None:
    """Load KEY=VALUE lines from a git-ignored file without overriding real environment variables."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def parse_rates(raw: str) -> dict[str, float]:
    """``"INR=0.012, EUR=1.08"`` -> ``{"INR": 0.012, "EUR": 1.08}`` (units of USD per 1 unit)."""
    rates: dict[str, float] = {}
    for part in raw.split(","):
        if not part.strip():
            continue
        code, sep, value = part.partition("=")
        if not sep:
            raise ValueError(f"bad FX_RATES_TO_USD entry {part!r}; expected CODE=rate")
        rate = float(value)
        if rate <= 0:
            raise ValueError(f"exchange rate for {code.strip()} must be positive")
        rates[code.strip().upper()] = rate
    rates["USD"] = 1.0
    return rates


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "offline"                 # "openai" (OpenAI-compatible API) or "offline"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = field(default="", repr=False)
    llm_model: str = "llama-3.1-8b-instant"
    llm_timeout_s: float = 30.0
    llm_seed: int = 7

    db_backend: str = "sqlite"                    # "sqlite", "postgres" or "mysql"
    sqlite_path: str = "data/gadgetgenie.db"
    db_dsn: str = field(default="", repr=False)   # read-only account for postgres/mysql
    sql_dialect: str = "sqlite"                   # dialect the LLM is asked to write

    max_rows: int = 10
    query_timeout_s: float = 5.0
    max_attempts: int = 3
    max_question_chars: int = 500
    fx_rates_to_usd: dict = field(default_factory=lambda: {"USD": 1.0})

    log_path: str = ""                            # JSONL query log (empty = in memory only)
    api_token: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = ()
    rate_limit_per_minute: int = 30

    @classmethod
    def from_env(cls, env_file: str | None = ".env") -> "Settings":
        if env_file:
            read_env_file(env_file)
        key = _get("LLM_API_KEY")
        provider = (_get("LLM_PROVIDER") or ("openai" if key else "offline")).lower()
        backend = _get("DB_BACKEND", cls.db_backend).lower()
        return cls(
            llm_provider=provider,
            llm_base_url=_get("LLM_BASE_URL", cls.llm_base_url),
            llm_api_key=key,
            llm_model=_get("LLM_MODEL", cls.llm_model),
            llm_timeout_s=float(_get("LLM_TIMEOUT_S", str(cls.llm_timeout_s))),
            llm_seed=int(_get("LLM_SEED", str(cls.llm_seed))),
            db_backend=backend,
            sqlite_path=_get("SQLITE_PATH", cls.sqlite_path),
            db_dsn=_get("DB_DSN"),
            sql_dialect=_get("SQL_DIALECT", "sqlite" if backend == "sqlite" else backend).lower(),
            max_rows=int(_get("MAX_ROWS", str(cls.max_rows))),
            query_timeout_s=float(_get("QUERY_TIMEOUT_S", str(cls.query_timeout_s))),
            max_attempts=int(_get("MAX_ATTEMPTS", str(cls.max_attempts))),
            max_question_chars=int(_get("MAX_QUESTION_CHARS", str(cls.max_question_chars))),
            fx_rates_to_usd=parse_rates(_get("FX_RATES_TO_USD")),
            log_path=_get("QUERY_LOG_PATH"),
            api_token=_get("API_TOKEN"),
            cors_origins=tuple(o.strip() for o in _get("CORS_ORIGINS").split(",") if o.strip()),
            rate_limit_per_minute=int(_get("RATE_LIMIT_PER_MINUTE", str(cls.rate_limit_per_minute))),
        )

    def check(self) -> None:
        if self.llm_provider not in {"openai", "offline"}:
            raise ValueError("LLM_PROVIDER must be 'openai' or 'offline'")
        if self.llm_provider == "openai" and not self.llm_api_key:
            raise ValueError("LLM_PROVIDER=openai needs LLM_API_KEY")
        if self.db_backend not in {"sqlite", "postgres", "mysql"}:
            raise ValueError("DB_BACKEND must be sqlite, postgres or mysql")
        if self.db_backend != "sqlite" and not self.db_dsn:
            raise ValueError(f"DB_BACKEND={self.db_backend} needs DB_DSN for a read-only account")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("MAX_ATTEMPTS must be 1..5")
        if not 1 <= self.max_rows <= 100:
            raise ValueError("MAX_ROWS must be 1..100")
        if self.query_timeout_s <= 0:
            raise ValueError("QUERY_TIMEOUT_S must be positive")
