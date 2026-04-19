"""Unit tests for DigiKey per-IP token-bucket rate limiter."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from digikey.ratelimit import (
    TokenBucketRateLimiter,
    rate_limit_dependency,
    register_rate_limit_handler,
    reset_limiter_for_tests,
)

pytestmark = pytest.mark.unit


def _build_app() -> FastAPI:
    app = FastAPI()
    register_rate_limit_handler(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/status")
    def status_route() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/oauth/token", dependencies=[Depends(rate_limit_dependency)])
    def token() -> dict[str, str]:
        return {"access_token": "stub"}

    return app


@pytest.fixture()
def rl_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # per_min=60 (1/sec refill), burst=20 — matches task spec for burst test.
    monkeypatch.setenv("DIGIKEY_RL_PER_MIN", "60")
    monkeypatch.setenv("DIGIKEY_RL_BURST", "20")
    reset_limiter_for_tests()
    yield
    reset_limiter_for_tests()


def test_burst_allows_up_to_burst_then_429(rl_env: None) -> None:
    app = _build_app()
    client = TestClient(app)

    for i in range(20):
        r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.1"})
        assert r.status_code != 429, f"unexpected 429 at request {i + 1}"

    r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.1"})
    assert r.status_code == 429
    body = r.json()
    assert body["detail"] == "rate_limited"
    assert isinstance(body["retry_after"], int)
    assert body["retry_after"] >= 1
    assert "retry-after" in {k.lower() for k in r.headers.keys()}
    assert int(r.headers["Retry-After"]) == body["retry_after"]


def test_window_recovery_after_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    """After enough monotonic time elapses, new requests are allowed again."""
    monkeypatch.setenv("DIGIKEY_RL_PER_MIN", "60")
    monkeypatch.setenv("DIGIKEY_RL_BURST", "5")
    reset_limiter_for_tests()

    app = _build_app()
    client = TestClient(app)

    # Drive a fake monotonic clock.
    now = {"t": 1000.0}

    def fake_monotonic() -> float:
        return now["t"]

    monkeypatch.setattr("digikey.ratelimit.time.monotonic", fake_monotonic)

    for _ in range(5):
        r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.2"})
        assert r.status_code != 429

    r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.2"})
    assert r.status_code == 429
    retry_after = r.json()["retry_after"]
    assert retry_after >= 1

    # Advance past retry_after; refill allows a new request.
    now["t"] += retry_after + 0.1
    r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.2"})
    assert r.status_code != 429

    reset_limiter_for_tests()


def test_per_ip_isolation(rl_env: None) -> None:
    app = _build_app()
    client = TestClient(app)

    # Exhaust IP A.
    for _ in range(20):
        client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.3"})
    r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.3"})
    assert r.status_code == 429

    # IP B still has a full bucket.
    r = client.post("/v1/oauth/token", headers={"X-Forwarded-For": "10.0.0.4"})
    assert r.status_code != 429


def test_exempt_routes_not_rate_limited(rl_env: None) -> None:
    app = _build_app()
    client = TestClient(app)

    # Hammer /health and /v1/status well past the burst.
    for _ in range(100):
        assert client.get("/health", headers={"X-Forwarded-For": "10.0.0.5"}).status_code == 200
        assert client.get("/v1/status", headers={"X-Forwarded-For": "10.0.0.5"}).status_code == 200


def test_token_bucket_refill_and_consume() -> None:
    """Direct async bucket check: consume burst, exhaust, refill."""
    import asyncio

    async def _run() -> None:
        limiter = TokenBucketRateLimiter(per_min=60, burst=3)

        for _ in range(3):
            allowed, retry = await limiter.check("ip")
            assert allowed
            assert retry == 0.0

        allowed, retry = await limiter.check("ip")
        assert not allowed
        assert retry > 0

    asyncio.run(_run())
