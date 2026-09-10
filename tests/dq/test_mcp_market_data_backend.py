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

    def _window(ticker, as_of, manifest=None, return_stale=False):
        rows = [{"date": "2024-12-31", "close": 1.0}]
        return (rows, False) if return_stale else rows

    monkeypatch.setattr(mcp, "_read_r2_window", _window)
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

    def _boom(ticker, as_of, manifest=None, return_stale=False):
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

    def _counting(ticker, as_of, manifest=None, return_stale=False):
        calls.append((ticker, as_of))
        rows = [{"date": "2024-12-31", "close": 1.0}]
        return (rows, False) if return_stale else rows

    monkeypatch.setattr(mcp, "_read_r2_window", _counting)
    first = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    second = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    assert first == second
    assert len(calls) == 1


# ── Task 7 fix round M1 (#3780): stale-flagged payloads must not sit in the
# 900s TTL cache (a stale serve would pin the stale flag for the full window
# even after the vendor flake clears). Fresh payloads cache normally (above).


def test_technicals_r2_stale_payload_skips_ttl_store(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    calls: list[tuple] = []

    def _stale_window(ticker, as_of, manifest=None, return_stale=False):
        calls.append((ticker, as_of))
        rows = [{"date": "2024-12-31", "close": 1.0}]
        return (rows, True) if return_stale else rows

    monkeypatch.setattr(mcp, "_read_r2_window", _stale_window)
    first = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    assert json.loads(first)["stale"] is True
    second = mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31")
    assert json.loads(second)["stale"] is True
    assert len(calls) == 2


def test_macro_r2_stale_payload_skips_ttl_store(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-01"})
    series = {"CPI": {"latest": {"obs_date": "2024-12-01", "value": 1.0}, "window": []}}
    calls: list[tuple] = []

    def _counting(series_ids, as_of, manifest=None):
        calls.append((tuple(series_ids), as_of))
        return series

    monkeypatch.setattr(mcp, "_read_r2_macro_window", _counting)
    first = mcp.digiquant_get_macro_series(["CPI"], lookback=6, as_of="2024-12-31")
    assert json.loads(first)["stale"] is True
    mcp.digiquant_get_macro_series(["CPI"], lookback=6, as_of="2024-12-31")
    assert len(calls) == 2


def test_technicals_r2_lookback_slices_tail(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_manifest", lambda: {"version": 1, "as_of": "2024-12-31"})
    rows = [{"date": f"2024-12-{day:02d}", "close": float(day)} for day in (29, 30, 31)]

    def _window(ticker, as_of, manifest=None, return_stale=False):
        return (rows, False) if return_stale else rows

    monkeypatch.setattr(mcp, "_read_r2_window", _window)
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


# ── Task 7 fix round M2 (#3780): the manifest `stale` (Task 6 writer-side)
# vs envelope `stale` (reader-side) naming collision must stay documented at
# the envelope construction site until Task 10 docs carry the glossary entry.


def test_envelope_docstrings_distinguish_both_stale_signals():
    for fn in (mcp.digiquant_get_price_technicals, mcp.digiquant_get_macro_series):
        assert "writer-side" in fn.__doc__ and "reader-side" in fn.__doc__
        assert "Task 10" in fn.__doc__


# ── Task 4 review findings (Refs #3780): helpers ──


def _history_payload(dates, closes=None):
    """Real parquet bytes for a tiny OHLCV frame + its SHA-256."""
    import hashlib
    import io

    import polars as pl

    closes = list(closes) if closes is not None else [float(i + 1) for i in range(len(dates))]
    frame = pl.DataFrame(
        {
            "date": list(dates),
            "open": closes,
            "high": [c + 0.1 for c in closes],
            "low": [c - 0.1 for c in closes],
            "close": closes,
            "volume": [100.0] * len(dates),
        }
    )
    buf = io.BytesIO()
    frame.write_parquet(buf)
    payload = buf.getvalue()
    return payload, hashlib.sha256(payload).hexdigest()


def _price_manifest(as_of, ticker="SPY", sha="abc", obj=None):
    return {
        "version": 1,
        "as_of": as_of,
        "datasets": {
            ticker: {
                "object": obj or f"market-data/price/{ticker}/{as_of}.parquet",
                "sha256": sha,
            }
        },
    }


class _FakeR2Store:
    """Minimal R2HistoryStore double serving fixed parquet bytes."""

    def __init__(self, payload, generation_key="market-data/price/SPY/gen.parquet"):
        self._payload = payload
        self._generation_key = generation_key

    def get_generation(self, key, sha256):
        return self._payload

    def read_latest(self, pointer_key):
        return self._generation_key


# Finding 1: a failing live fetch must yield the error envelope, never a
# valid-looking empty window for the requested as_of.
def test_technicals_r2_live_fetch_failure_yields_error_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    payload, sha = _history_payload(["2024-12-27", "2024-12-30", "2024-12-31"], [1.0, 2.0, 3.0])
    manifest = _price_manifest("2024-12-31", sha=sha)
    monkeypatch.setattr(mcp, "_read_manifest", lambda: manifest)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(payload))

    def _boom(tickers, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("digiquant.data.prices.fetchers.fetch_batch", _boom)
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2025-01-15"))
    assert "boom" in out["error"]
    assert "rows" not in out


# Finding 2: a manifest missing the requested macro sha must fail loud so
# Task 6 key mismatches surface instead of serving empty windows.
def test_macro_r2_missing_sha_yields_error_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    manifest = {"version": 1, "as_of": "2024-12-31", "datasets": {}}
    monkeypatch.setattr(mcp, "_read_manifest", lambda: manifest)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(b""))
    out = json.loads(mcp.digiquant_get_macro_series(["CPI"], lookback=6, as_of="2024-12-31"))
    assert "CPI" in out["error"]


def test_macro_r2_missing_pointer_yields_error_envelope(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    manifest = {"version": 1, "as_of": "2024-12-31", "datasets": {}}
    monkeypatch.setattr(mcp, "_read_manifest", lambda: manifest)

    class _NoPointer(_FakeR2Store):
        def read_latest(self, pointer_key):
            raise KeyError(pointer_key)

    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _NoPointer(b""))
    out = json.loads(mcp.digiquant_get_macro_series(["DGS10"], lookback=6, as_of="2024-12-31"))
    assert "DGS10" in out["error"]


# Finding 3: indicator columns must stay aligned to their dates even when the
# stored parquet rows arrive out of order.
def test_r2_window_indicator_columns_align_to_dates_on_shuffled_input(monkeypatch):
    dates = ["2024-12-31", "2024-12-30", "2024-12-29", "2024-12-27", "2024-12-26"]
    closes = [5.0, 4.0, 3.0, 2.0, 1.0]
    payload, sha = _history_payload(dates, closes)
    manifest = _price_manifest("2024-12-31", sha=sha)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(payload))
    rows = mcp._read_r2_window("SPY", "2024-12-31", manifest)
    assert [str(r["date"]) for r in rows] == sorted(dates)
    assert [r["close"] for r in rows] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_r2_window_indicator_row_mismatch_fails_loud(monkeypatch):
    from digiquant.data.prices import technicals as _tech

    real_compute = _tech.compute_indicators

    def _truncated(df, trading_days=None):
        full = real_compute(df, trading_days=trading_days)
        return full.head(full.height - 1)

    monkeypatch.setattr(_tech, "compute_indicators", _truncated)
    payload, sha = _history_payload(["2024-12-27", "2024-12-30", "2024-12-31"])
    manifest = _price_manifest("2024-12-31", sha=sha)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(payload))
    with pytest.raises(RuntimeError, match="row mismatch"):
        mcp._read_r2_window("SPY", "2024-12-31", manifest)


# Finding 4: fake backend serving real parquet bytes through the UNMOCKED
# _read_r2_window — covers R2 → merge → indicators with the real parser.
def test_read_r2_window_parses_real_parquet_bytes_end_to_end(monkeypatch):
    payload, sha = _history_payload(
        ["2024-12-25", "2024-12-26", "2024-12-27", "2024-12-30", "2024-12-31"],
        [1.0, 2.0, 3.0, 4.0, 5.0],
    )
    manifest = _price_manifest("2024-12-31", sha=sha)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(payload))
    rows = mcp._read_r2_window("SPY", "2024-12-31", manifest)
    assert [str(r["date"]) for r in rows] == [
        "2024-12-25",
        "2024-12-26",
        "2024-12-27",
        "2024-12-30",
        "2024-12-31",
    ]
    assert [r["close"] for r in rows] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert "sma_20" in rows[0] and "rsi_14" in rows[0]


# Finding 6: as_of vs manifest seal must compare chronologically, not
# lexicographically ("20240115" is chronologically before "2024-02-01" but
# sorts after it as a string, which would wrongly trigger a live fetch).
def test_r2_window_asof_comparison_is_chronological_not_lexicographic(monkeypatch):
    payload, sha = _history_payload(["2024-01-11", "2024-01-12", "2024-01-15"])
    manifest = _price_manifest("2024-02-01", sha=sha)
    monkeypatch.setattr(mcp, "_get_r2_store", lambda: _FakeR2Store(payload))
    calls: list = []

    def _record(tickers, **kwargs):
        from digiquant.data.prices.fetchers import FetchResult

        calls.append((tickers, kwargs))
        return FetchResult(frames={}, errors={})

    monkeypatch.setattr("digiquant.data.prices.fetchers.fetch_batch", _record)
    rows = mcp._read_r2_window("SPY", "20240115", manifest)
    assert calls == []
    assert [r["close"] for r in rows] == [1.0, 2.0, 3.0]
