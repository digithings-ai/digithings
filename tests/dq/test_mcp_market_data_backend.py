"""MCP market-data backend flag + as_of envelopes (#3780, Task 4)."""

from __future__ import annotations

import json

import digiquant.mcp_server as mcp
import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_ttl():
    # getattr-guarded so the RED run (before _ttl exists) fails on the
    # tool signature itself, not on this fixture.
    ttl = getattr(mcp, "_ttl", None)
    if ttl is not None:
        ttl.clear()
    yield
    ttl = getattr(mcp, "_ttl", None)
    if ttl is not None:
        ttl.clear()


def test_technicals_r2_backend_returns_asof_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    monkeypatch.setattr(
        mcp,
        "_read_r2_window",
        lambda ticker, as_of, manifest=None: [{"date": "2024-12-31", "close": 1.0}],
    )
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31"))
    assert out["as_of"] == "2024-12-31"
    assert out["rows"][0]["date"] == "2024-12-31"


def test_technicals_supabase_default_path(monkeypatch):
    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    payload = json.dumps({"ticker": "SPY", "latest": {}, "window": []})
    monkeypatch.setattr(mcp, "_supabase_technicals", lambda ticker, lookback: payload)
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31"))
    assert out["ticker"] == "SPY"


def test_technicals_r2_manifest_version_mismatch(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 2, "as_of": "2024-12-31"})
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31"))
    assert "unsupported manifest version" in out["error"]


def test_technicals_r2_unknown_ticker_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})

    def _boom(ticker, as_of, manifest=None):
        raise LookupError(f"unknown ticker {ticker!r}")

    monkeypatch.setattr(mcp, "_read_r2_window", _boom)
    out = json.loads(mcp.digiquant_get_price_technicals("FOO", lookback=20, as_of="2024-12-31"))
    assert "unknown ticker" in out["error"]


def test_read_r2_window_missing_pointer_maps_to_unknown_ticker(monkeypatch):
    """KeyError from R2HistoryStore.read_latest becomes unknown-ticker LookupError."""

    class _FakeStore:
        def read_latest(self, pointer_key):
            raise KeyError(pointer_key)

    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeStore())
    manifest = {"version": 1, "as_of": "2024-12-31", "datasets": {}}
    with pytest.raises(LookupError, match="unknown ticker"):
        mcp._read_r2_window("FOO", "2024-12-31", manifest)


def test_technicals_r2_ttl_caches_window(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    calls: list[tuple] = []

    def _counting(ticker, as_of, manifest=None):
        calls.append((ticker, as_of))
        return [{"date": "2024-12-31", "close": 1.0}]

    monkeypatch.setattr(mcp, "_read_r2_window", _counting)
    first = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    second = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    assert first == second
    assert len(calls) == 1


def test_technicals_r2_lookback_slices_tail(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    rows = [{"date": f"2024-12-{day:02d}", "close": float(day)} for day in (29, 30, 31)]
    monkeypatch.setattr(mcp, "_read_r2_window", lambda ticker, as_of, manifest=None: rows)
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=2, as_of="2024-12-31"))
    assert [r["date"] for r in out["rows"]] == ["2024-12-30", "2024-12-31"]


def test_macro_r2_backend_returns_asof_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    series = {"CPI": {"latest": {"obs_date": "2024-12-31", "value": 1.0}, "window": []}}
    monkeypatch.setattr(
        mcp, "_read_r2_macro_window", lambda series_ids, as_of, manifest=None: series
    )
    out = json.loads(mcp.digiquant_get_macro_series(["CPI"], lookback=6, as_of="2024-12-31"))
    assert out["as_of"] == "2024-12-31"
    assert out["series"]["CPI"]["latest"]["obs_date"] == "2024-12-31"
