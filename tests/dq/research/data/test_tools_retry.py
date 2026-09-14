"""Data-tool dispatcher retries transient Supabase faults 3× (#3299)."""

from __future__ import annotations

import json
import time

import httpx
import pytest
from digiquant.research.data.tools import build_data_tool_dispatcher

from tests.dq.research.data.test_queries import _FakeClient

pytestmark = pytest.mark.unit


def _timeout() -> httpx.ReadTimeout:
    return httpx.ReadTimeout(
        "The read operation timed out",
        request=httpx.Request("GET", "https://x.supabase.co/rest/v1/t"),
    )


class _FlakyClient(_FakeClient):
    """Fails the first ``failures`` execute() calls with a transient fault."""

    def __init__(self, tables, failures: int = 2):  # type: ignore[no-untyped-def]
        super().__init__(tables)
        self.failures = failures
        self.attempts = 0

    def table(self, name):  # type: ignore[no-untyped-def]
        inner = super().table(name)
        client = self
        orig_execute = inner.execute

        def _execute():  # type: ignore[no-untyped-def]
            client.attempts += 1
            if client.attempts <= client.failures:
                raise _timeout()
            return orig_execute()

        inner.execute = _execute  # type: ignore[method-assign]
        return inner


def _theses_client(**over):  # type: ignore[no-untyped-def]
    return _FlakyClient(
        {
            "theses": [
                {"ticker": "SPY", "date": "2026-06-08", "thesis_id": "t1"},
            ]
        },
        **over,
    )


def test_transient_disconnect_retries_then_returns_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    client = _theses_client(failures=2)
    dispatch = build_data_tool_dispatcher(client)
    out = json.loads(dispatch("query_data", {"table": "theses"}))
    assert out["rows"][0]["thesis_id"] == "t1"
    assert client.attempts == 3


def test_persistent_outage_returns_error_string_after_three_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    client = _theses_client(failures=10)
    dispatch = build_data_tool_dispatcher(client)
    out = json.loads(dispatch("query_data", {"table": "theses"}))
    # Retries exhausted: the pre-existing error shape, not a raise.
    assert "timed out" in out["error"]
    assert client.attempts == 3


def test_schema_error_fails_fast_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    class _BadColumnClient(_FakeClient):
        attempts = 0

        def table(self, name):  # type: ignore[no-untyped-def]
            inner = super().table(name)

            def _execute():  # type: ignore[no-untyped-def]
                type(self).attempts += 1
                raise ValueError('column "nope" does not exist (42703)')

            inner.execute = _execute  # type: ignore[method-assign]
            return inner

    # Use a table without a per-column allowlist so the 42703 still reaches
    # Supabase (price_technicals/price_history now fail-fast in query_data #3771).
    dispatch = build_data_tool_dispatcher(_BadColumnClient({}))
    err = dispatch("query_data", {"table": "positions", "columns": "nope"})
    # A real bug (42703) is not transient: one attempt, Error string, no sleep.
    assert "42703" in err
    assert _BadColumnClient.attempts == 1
    assert sleeps == []
