"""Tests for the dedicated `require_tool_calls=true` rate-limit budget (finding #7, PR #2361).

`X-Require-Tool-Calls` / `require_tool_calls=true` forces `tool_choice="required"`,
which reliably exhausts all `max_tool_rounds` completions instead of returning after
one -- a caller-controlled ~4-5x LLM-spend multiplier reachable with plain
`digigraph:chat` scope. `_enforce_require_tool_calls_budget` gives that class of
request its own, stricter budget on top of the general per-path rate limit.
"""

from __future__ import annotations

from unittest.mock import patch

import digigraph.server as server
import pytest
from digigraph.rate_limit import RateLimiter
from starlette.requests import Request


def _make_request(client_host: str = "203.0.113.9") -> Request:
    """A minimal real Starlette Request -- not FastAPI's TestClient -- so its
    client host isn't the 'testclient' sentinel that RateLimiter.check() exempts."""
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [],
        "client": (client_host, 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _fresh_limiter(monkeypatch):
    """Each test gets its own limiter instance and a small, deterministic budget
    so cases don't share sliding-window state with each other or the real default."""
    monkeypatch.setattr(server, "_require_tool_calls_limiter", RateLimiter())
    monkeypatch.setattr(server, "_REQUIRE_TOOL_CALLS_RATE_LIMIT", (2, 60))
    monkeypatch.delenv("DIGI_DISABLE_RATE_LIMIT", raising=False)


class TestRequireToolCallsBudget:
    def test_not_opted_in_never_limited(self):
        """require_tool_calls=False/None never consults this budget, no matter the volume --
        only the request's own opt-in is metered here."""
        req = _make_request()
        for _ in range(50):
            assert server._enforce_require_tool_calls_budget(False, req) is None
            assert server._enforce_require_tool_calls_budget(None, req) is None

    def test_opted_in_within_budget_allowed(self):
        req = _make_request()
        assert server._enforce_require_tool_calls_budget(True, req) is None
        assert server._enforce_require_tool_calls_budget(True, req) is None

    def test_opted_in_over_budget_returns_429(self):
        req = _make_request()
        assert server._enforce_require_tool_calls_budget(True, req) is None
        assert server._enforce_require_tool_calls_budget(True, req) is None
        response = server._enforce_require_tool_calls_budget(True, req)
        assert response is not None
        assert response.status_code == 429

    def test_budget_is_per_ip(self):
        """Exhausting the budget for one caller doesn't affect another IP."""
        caller_a = _make_request("203.0.113.1")
        caller_b = _make_request("203.0.113.2")
        assert server._enforce_require_tool_calls_budget(True, caller_a) is None
        assert server._enforce_require_tool_calls_budget(True, caller_a) is None
        assert server._enforce_require_tool_calls_budget(True, caller_a) is not None
        # caller_b's budget is untouched
        assert server._enforce_require_tool_calls_budget(True, caller_b) is None
        assert server._enforce_require_tool_calls_budget(True, caller_b) is None

    def test_disable_rate_limit_env_bypasses_budget(self, monkeypatch):
        monkeypatch.setenv("DIGI_DISABLE_RATE_LIMIT", "true")
        req = _make_request()
        for _ in range(10):
            assert server._enforce_require_tool_calls_budget(True, req) is None


class TestWorkflowEndpointBudget:
    """POST /workflow's WorkflowRequest.require_tool_calls reaches the identical
    tool_choice="required" spend-amplification path as chat (via
    require_tool_calls_for_workflow) but, before this fix, was never metered by this
    budget -- only the general 10 req/min /workflow limit applied (#2361 finding 7 gap).

    FastAPI TestClient requests are exempt from RateLimiter (client host ==
    'testclient', see rate_limit.py), so this calls the route function directly with a
    real Request -- the same technique the unit tests above use -- rather than going
    through TestClient.
    """

    def test_within_budget_reaches_workflow(self):
        from digigraph.models import WorkflowRequest, WorkflowResult

        req = WorkflowRequest(prompt="Build me a stat-arb on tech", require_tool_calls=True)
        http_req = _make_request("203.0.113.60")
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = WorkflowResult(success=True, message="", backtest_result={})
            result = server.api_run_digigraph_workflow(http_req, req)
        assert result is m.return_value
        m.assert_called_once()

    def test_over_budget_returns_429_without_reaching_workflow(self):
        from digigraph.models import WorkflowRequest, WorkflowResult
        from fastapi.responses import JSONResponse

        req = WorkflowRequest(prompt="Build me a stat-arb on tech", require_tool_calls=True)
        http_req = _make_request("203.0.113.61")
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = WorkflowResult(success=True, message="", backtest_result={})
            # Budget is (2, 60) per _fresh_limiter -- first two calls pass through.
            server.api_run_digigraph_workflow(http_req, req)
            server.api_run_digigraph_workflow(http_req, req)
            result = server.api_run_digigraph_workflow(http_req, req)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 429
        assert m.call_count == 2

    def test_require_tool_calls_false_never_limited(self):
        """A plain workflow request (require_tool_calls unset) never consults this
        budget -- it's still bounded by the general per-path /workflow limit only."""
        from digigraph.models import WorkflowRequest, WorkflowResult

        req = WorkflowRequest(prompt="Build me a stat-arb on tech")
        http_req = _make_request("203.0.113.62")
        with patch("digigraph.server.run_digigraph_workflow") as m:
            m.return_value = WorkflowResult(success=True, message="", backtest_result={})
            for _ in range(5):
                result = server.api_run_digigraph_workflow(http_req, req)
                assert result is m.return_value
        assert m.call_count == 5
