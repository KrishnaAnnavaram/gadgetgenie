import pytest

pytest.importorskip("fastapi")

from gadgetgenie.config import Settings  # noqa: E402


@pytest.fixture()
def client(make_recommender, settings):
    from fastapi.testclient import TestClient

    from gadgetgenie.api.app import create_app

    s = Settings(**{**settings.__dict__, "api_token": "t0ken", "rate_limit_per_minute": 3})
    return TestClient(create_app(make_recommender(), s))


AUTH = {"Authorization": "Bearer t0ken"}


def test_api_requires_token_and_json(client):
    assert client.post("/api/ask", json={"question": "best laptops"}).status_code == 401
    ok = client.post("/api/ask", json={"question": "best laptops"}, headers=AUTH)
    assert ok.status_code == 200 and ok.json()["status"] == "ok"
    form = client.post("/api/ask", data={"question": "best laptops"}, headers=AUTH)
    assert form.status_code in (415, 422)                  # cross-site form posts are not accepted


def test_api_rate_limit_and_headers(client):
    codes = [client.post("/api/ask", json={"question": "best phones"}, headers=AUTH).status_code for _ in range(4)]
    assert codes[-1] == 429
    page = client.get("/")
    assert page.status_code == 200 and "script-src 'self'" in page.headers["content-security-policy"]


def test_no_write_endpoints_and_safe_client(client):
    assert client.post("/api/devices", json={}).status_code in (404, 405)
    js = client.get("/static/app.js").text
    assert "innerHTML" not in js and "textContent" in js
    assert client.get("/static/../config.py").status_code == 404
