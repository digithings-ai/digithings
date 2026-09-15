"""Identity-aware rate limiting for authenticated service callers (#4106).

The daily digiquant book run grounds many research segments through
``POST /v1/orchestrator_invoke`` from a single GitHub-runner IP. The limiter is
the outermost middleware — it runs *before* ``DigiAuthMiddleware`` — so it could
only key on the client IP, and the 11th call in a minute was 429'd mid-book. The
429 was then collapsed by digigraph into "web_search returned no rows", failing
the whole run three times (#4106).

Contract pinned here:
* anonymous (no ``Authorization``) traffic keeps the per-IP budget for the path;
* a caller presenting a bearer token is budgeted per token, at a multiple of the
  path budget (env-tunable), so one runner IP cannot exhaust another service's
  allowance;
* a coarse per-IP ceiling still applies to token-bearing traffic, so rotating
  tokens cannot bypass the flood guard;
* ``DIGI_DISABLE_RATE_LIMIT`` and the ``testclient`` host bypass are preserved.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from digisearch.server import app
from fastapi.testclient import TestClient

from digisearch import server

INVOKE = "/v1/orchestrator_invoke"
IP = "203.0.113.9"
PATH_LIMIT = 10  # /v1/orchestrator_invoke: 10 requests per 60s
TOKEN = "service-token-a"


@pytest.fixture(autouse=True)
def _clean_windows() -> Iterator[None]:
    server._rl_windows.clear()
    yield
    server._rl_windows.clear()


@pytest.fixture
def client() -> TestClient:
    # No default X-Forwarded-For: tests that exercise the limiter pass one, so
    # they are not caught by the ``testclient`` host bypass.
    return TestClient(app)


def _invoke(client: TestClient, *, token: str | None = None, ip: str = IP):
    headers = {"X-Forwarded-For": ip}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        INVOKE, json={"tool": "web_search", "arguments": {"query": "q"}}, headers=headers
    )


@pytest.mark.unit
class TestAnonymousTraffic:
    def test_ip_budget_is_unchanged(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT):
            assert _invoke(client).status_code != 429
        assert _invoke(client).status_code == 429

    def test_rejection_reports_the_budget_and_a_retry_after(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT):
            _invoke(client)
        blocked = _invoke(client)
        assert blocked.status_code == 429
        body = blocked.json()
        assert body["error"]["code"] == "rate_limit_exceeded"
        assert body["error"]["service"] == "digisearch"
        assert "10 requests per 60s" in body["error"]["message"]
        assert blocked.headers["Retry-After"] == "60"

    def test_distinct_ips_are_budgeted_separately(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT):
            _invoke(client)
        assert _invoke(client, ip="203.0.113.10").status_code != 429


@pytest.mark.unit
class TestAuthenticatedTraffic:
    def test_token_bearing_caller_exceeds_the_anonymous_budget(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT + 2):
            assert _invoke(client, token=TOKEN).status_code != 429

    def test_token_budget_defaults_to_six_times_the_path_budget(self, client: TestClient) -> None:
        budget = PATH_LIMIT * server._AUTH_RATE_LIMIT_MULTIPLIER
        for _ in range(budget):
            assert _invoke(client, token=TOKEN).status_code != 429
        assert _invoke(client, token=TOKEN).status_code == 429

    def test_budgets_are_keyed_per_token(self, client: TestClient) -> None:
        budget = PATH_LIMIT * server._AUTH_RATE_LIMIT_MULTIPLIER
        for _ in range(budget):
            _invoke(client, token=TOKEN)
        assert _invoke(client, token=TOKEN).status_code == 429
        # A different service must not inherit the exhausted token's window.
        assert _invoke(client, token="service-token-b").status_code != 429

    def test_env_multiplier_overrides_the_token_budget(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGISEARCH_AUTH_RATE_LIMIT_MULTIPLIER", "1")
        for _ in range(PATH_LIMIT):
            assert _invoke(client, token=TOKEN).status_code != 429
        assert _invoke(client, token=TOKEN).status_code == 429

    def test_rotating_tokens_cannot_bypass_the_ip_ceiling(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGISEARCH_IP_CEILING_MULTIPLIER", "1")
        for index in range(PATH_LIMIT):
            assert _invoke(client, token=f"rotating-{index}").status_code != 429
        assert _invoke(client, token="rotating-fresh").status_code == 429


@pytest.mark.unit
class TestBypasses:
    def test_disable_switch_skips_the_limiter(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGI_DISABLE_RATE_LIMIT", "1")
        for _ in range(PATH_LIMIT * 5):
            assert _invoke(client).status_code != 429

    def test_testclient_host_is_exempt_without_a_forwarded_for(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT * 5):
            response = client.post(INVOKE, json={"tool": "web_search", "arguments": {"query": "q"}})
            assert response.status_code != 429

    def test_healthz_is_exempt_even_with_a_token(self, client: TestClient) -> None:
        for _ in range(PATH_LIMIT * 5):
            response = client.get(
                "/healthz", headers={"X-Forwarded-For": IP, "Authorization": f"Bearer {TOKEN}"}
            )
            assert response.status_code == 200
