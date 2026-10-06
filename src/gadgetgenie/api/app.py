"""FastAPI app: a JSON ``/api/ask`` endpoint and a small static chat page.

Security choices:
* no endpoint is CSRF-exempt because none relies on cookies: requests carry no ambient
  credentials, bodies must be ``application/json`` (a cross-site HTML form cannot send
  that without a CORS preflight), and CORS is limited to ``CORS_ORIGINS``;
* optional bearer-token auth (``API_TOKEN``) compared in constant time;
* per-client rate limiting; strict security headers (CSP without inline script);
* read-only: there are no write endpoints for the catalogue;
* errors never echo stack traces (``debug=False``).
"""
# no ``from __future__ import annotations``: FastAPI needs the real model classes at runtime
import hmac
import threading
import time
from collections import defaultdict, deque
from importlib import resources

from ..config import Settings
from ..core.memory import valid_session_id


class RateLimiter:
    """Sliding one-minute window per key."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            window = self._hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                return False
            window.append(now)
            return True


def create_app(recommender=None, settings: Settings | None = None):
    from fastapi import Depends, FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from pydantic import BaseModel, Field

    settings = settings or Settings.from_env()
    if recommender is None:
        from ..core.service import build_recommender

        recommender = build_recommender(settings)
    limiter = RateLimiter(settings.rate_limit_per_minute)
    app = FastAPI(title="GadgetGenie", version="0.1.0", debug=False, docs_url=None, redoc_url=None)

    if settings.cors_origins:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET", "POST"],
                           allow_headers=["Authorization", "Content-Type"], allow_credentials=False)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self'; "
                                                       "img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def guard(request: Request) -> None:
        if settings.api_token:
            supplied = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
            if not hmac.compare_digest(supplied.encode(), settings.api_token.encode()):
                raise HTTPException(status_code=401, detail="missing or invalid token")
        client = request.client.host if request.client else "unknown"
        if not limiter.allow(client):
            raise HTTPException(status_code=429, detail="too many requests, slow down")

    class AskBody(BaseModel):
        question: str = Field(min_length=1, max_length=settings.max_question_chars)
        session_id: str | None = Field(default=None, max_length=64)

    @app.post("/api/ask", dependencies=[Depends(guard)])
    def ask(body: AskBody, request: Request):
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(status_code=415, detail="send application/json")
        session = body.session_id if valid_session_id(body.session_id) else None
        return JSONResponse(recommender.ask(body.question, session).to_dict())

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/stats", dependencies=[Depends(guard)])
    def stats():
        return recommender.log.stats()

    static = resources.files("gadgetgenie") / "api" / "static"

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse((static / "index.html").read_text(encoding="utf-8"))

    @app.get("/static/{name}")
    def asset(name: str):
        types = {"app.js": "text/javascript", "style.css": "text/css"}
        if name not in types:
            raise HTTPException(status_code=404)
        return Response((static / name).read_text(encoding="utf-8"), media_type=types[name])

    return app
