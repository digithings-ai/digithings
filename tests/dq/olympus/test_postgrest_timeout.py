"""H9 PostgREST/httpx timeouts must fail in minutes, not hang until the job cancel (#3319)."""

from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client
from digiquant.olympus.hermes.writers import ledger_io
from digiquant.olympus.postgrest_timeout import (
    CONNECT_TIMEOUT_SECONDS,
    EXECUTE_DEADLINE_SECONDS,
    READ_TIMEOUT_SECONDS,
    PostgrestTimeoutError,
    run_with_deadline,
)

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 8, 31)


def test_deadline_constants_are_minutes_not_hours() -> None:
    assert CONNECT_TIMEOUT_SECONDS == 10.0
    assert READ_TIMEOUT_SECONDS == 60.0
    assert EXECUTE_DEADLINE_SECONDS == 70.0
    assert EXECUTE_DEADLINE_SECONDS < 5 * 60


def test_run_with_deadline_returns_quickly_on_success() -> None:
    assert run_with_deadline(lambda: 7, seconds=1.0) == 7


def test_run_with_deadline_raises_without_waiting_unbounded() -> None:
    def hang() -> None:
        time.sleep(30)

    t0 = time.monotonic()
    with pytest.raises(PostgrestTimeoutError, match="0.05"):
        run_with_deadline(hang, seconds=0.05)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"deadline wrapper waited {elapsed:.1f}s; must not hang"


class _HungQuery:
    def select(self, *_a: Any, **_k: Any) -> _HungQuery:
        return self

    def in_(self, *_a: Any, **_k: Any) -> _HungQuery:
        return self

    def gte(self, *_a: Any, **_k: Any) -> _HungQuery:
        return self

    def lt(self, *_a: Any, **_k: Any) -> _HungQuery:
        return self

    def execute(self) -> SimpleNamespace:
        time.sleep(30)
        return SimpleNamespace(data=[])


class _HungClient:
    def table(self, _name: str) -> _HungQuery:
        return _HungQuery()


def test_last_closes_does_not_wait_unbounded_on_hung_price_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ledger_io, "EXECUTE_DEADLINE_SECONDS", 0.05)
    t0 = time.monotonic()
    with pytest.raises(PostgrestTimeoutError):
        ledger_io._last_closes(client=_HungClient(), tickers={"SPY"}, run_date=RUN_DATE)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0, f"_last_closes hung for {elapsed:.1f}s on a timed-out client"


def test_build_client_passes_httpx_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("supabase")
    import supabase

    captured: dict[str, Any] = {}

    def fake_create(url: str, key: str, options: Any = None) -> dict[str, str]:
        captured["url"] = url
        captured["key"] = key
        captured["options"] = options
        return {"client": "fake"}

    monkeypatch.setattr(supabase, "create_client", fake_create)
    out = build_client(SupabaseConfig(url="https://example.supabase.co", service_key="sk"))
    assert out == {"client": "fake"}
    options = captured["options"]
    assert options is not None
    timeout = options.postgrest_client_timeout
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect == CONNECT_TIMEOUT_SECONDS
    assert timeout.read == READ_TIMEOUT_SECONDS
