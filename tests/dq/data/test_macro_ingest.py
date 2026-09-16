"""Unit tests for digiquant.data.prices.macro_ingest (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from digiquant.data.prices.macro_ingest import (
    YAHOO_FX_DEFAULT,
    MacroManifest,
    dedupe_observation_rows,
    fetch_fred,
    fetch_fx_intraday,
    fetch_fx_yahoo,
    fred_observations_to_rows,
    fx_intraday_payload_to_candles,
    yahoo_fx_payload_to_rows,
)


def _manifest() -> MacroManifest:
    return MacroManifest.from_dict(
        {
            "fred": {
                "series": [
                    {"id": "DGS10", "title": "10-Year Treasury", "unit": "percent"},
                ],
                "backfill_start": "1990-01-01",
            },
        }
    )


@pytest.mark.unit
def test_fred_observations_to_rows_filters_missing_values() -> None:
    observations = [
        {"date": "2025-01-01", "value": "4.12"},
        {"date": "2025-01-02", "value": "."},  # FRED sentinel for missing
        {"date": "2025-01-03", "value": ""},
        {"date": "", "value": "4.15"},
        {"date": "2025-01-04", "value": "not-a-number"},
    ]
    rows = fred_observations_to_rows("DGS10", "percent", "10Y", observations)
    assert len(rows) == 1
    assert rows[0]["obs_date"] == "2025-01-01"
    assert rows[0]["value"] == pytest.approx(4.12)
    assert rows[0]["source"] == "fred"
    assert rows[0]["series_id"] == "DGS10"
    assert rows[0]["meta"]["title"] == "10Y"


@pytest.mark.unit
def test_fetch_fred_mocks_http_and_returns_rows() -> None:
    fake_payload = {
        "observations": [
            {"date": "2025-04-01", "value": "4.12"},
            {"date": "2025-04-02", "value": "4.15"},
        ]
    }
    with patch("digiquant.data.prices.macro_ingest.fetch_fred_series") as fake:
        fake.return_value = fake_payload["observations"]
        rows = fetch_fred(_manifest(), api_key="fake-key", end="2025-04-30")
    assert len(rows) == 2
    assert {r["value"] for r in rows} == {4.12, 4.15}


@pytest.mark.unit
def test_fetch_fred_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        fetch_fred(_manifest(), api_key="")


@pytest.mark.unit
def test_dedupe_observation_rows_keeps_last() -> None:
    rows = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-01", "value": 4.0},
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-01", "value": 4.1},
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-02", "value": 4.2},
    ]
    out = dedupe_observation_rows(rows)
    assert len(out) == 2
    # Last-wins on duplicate (2025-01-01)
    for r in out:
        if r["obs_date"] == "2025-01-01":
            assert r["value"] == 4.1


@pytest.mark.unit
def test_macro_manifest_defaults() -> None:
    mani = MacroManifest.from_dict({})
    assert mani.fred_backfill_start == "1990-01-01"
    assert mani.fred_series == []


# ─── Retry + per-series isolation ──────────────────────────────────────


def _manifest_two_series() -> MacroManifest:
    return MacroManifest.from_dict(
        {
            "fred": {
                "series": [
                    {"id": "DGS10", "title": "10Y", "unit": "percent"},
                    {"id": "SOFR", "title": "SOFR", "unit": "percent"},
                ],
                "backfill_start": "2025-01-01",
            },
        }
    )


@pytest.mark.unit
def test_fetch_fred_isolates_per_series_failure(monkeypatch) -> None:
    # One series succeeds, the other raises. The succeeding series' rows are
    # returned; the failing one is skipped (logged to stderr), not propagated.
    import requests
    from digiquant.data.prices import macro_ingest

    def fake_fetch(api_key, series_id, *args, **kwargs):
        if series_id == "SOFR":
            raise requests.HTTPError("500 Server Error", response=None)
        return [{"date": "2025-01-02", "value": "4.25"}]

    monkeypatch.setattr(macro_ingest, "fetch_fred_series", fake_fetch)
    rows = fetch_fred(_manifest_two_series(), api_key="test")
    assert len(rows) == 1
    assert rows[0]["series_id"] == "DGS10"


@pytest.mark.unit
def test_fetch_fred_fails_only_when_all_series_fail(monkeypatch) -> None:
    import requests
    from digiquant.data.prices import macro_ingest

    def always_fail(*args, **kwargs):
        raise requests.HTTPError("500 Server Error", response=None)

    monkeypatch.setattr(macro_ingest, "fetch_fred_series", always_fail)
    with pytest.raises(RuntimeError, match="all 2 series failed"):
        fetch_fred(_manifest_two_series(), api_key="test")


@pytest.mark.unit
def test_retrying_session_retries_on_5xx(monkeypatch) -> None:
    # Session-level 500 retry is opaque to callers — they see the eventual 200
    # (or a final raised HTTPError if every retry exhausts). We verify the
    # Retry adapter is configured for 500/502/503/504 on GET.
    from digiquant.data.prices.macro_ingest import _retrying_session

    s = _retrying_session(total=2, backoff_factor=0.1)
    adapter = s.get_adapter("https://api.stlouisfed.org")
    retry_cfg = adapter.max_retries
    assert 500 in retry_cfg.status_forcelist
    assert 503 in retry_cfg.status_forcelist
    assert "GET" in retry_cfg.allowed_methods
    assert retry_cfg.total == 2


# ─── Yahoo FX (issue #328 — replaces Frankfurter for the daily pipeline) ────


def _fake_yahoo_long_frame():
    """Long-format Polars frame matching `_yahoo_fx_download`'s post-conversion
    contract. The boundary helper is responsible for collapsing yfinance's
    pandas multi-index into this shape, so tests work with Polars only."""
    import polars as pl

    symbols = [
        "EURUSD=X",
        "GBPUSD=X",
        "JPY=X",
        "CAD=X",
        "AUDUSD=X",
        "USDCHF=X",
        "NZDUSD=X",
    ]
    return pl.DataFrame(
        {
            "obs_date": ["2025-04-01"] * 7 + ["2025-04-02"] * 7,
            "yahoo_symbol": symbols * 2,
            "close": [
                1.0820,
                1.2685,
                150.10,
                1.3540,
                0.6620,
                0.8810,
                0.5920,
                1.0835,
                1.2702,
                149.95,
                1.3525,
                0.6635,
                0.8795,
                0.5910,
            ],
        }
    )


@pytest.mark.unit
def test_yahoo_fx_payload_to_rows_emits_one_row_per_symbol_per_day() -> None:
    payload = _fake_yahoo_long_frame()
    rows = yahoo_fx_payload_to_rows(payload, YAHOO_FX_DEFAULT)
    # 7 symbols × 2 days = 14 rows
    assert len(rows) == 14
    # Schema parity with the macro_series_observations contract
    sample = rows[0]
    assert set(sample.keys()) >= {"source", "series_id", "obs_date", "value", "unit", "meta"}
    assert all(r["source"] == "yahoo" for r in rows)
    assert all(r["unit"] == "fx" for r in rows)
    # Series IDs match the existing FX scheme (no rename — historical continuity)
    assert {r["series_id"] for r in rows} == {
        "FX/EUR",
        "FX/GBP",
        "FX/JPY",
        "FX/CAD",
        "FX/AUD",
        "FX/CHF",
        "FX/NZD",
    }
    # Quote convention is stamped so downstream consumers can disambiguate
    # vs the legacy Frankfurter rows (which were USD-base / foreign-quote).
    eur_row = next(r for r in rows if r["series_id"] == "FX/EUR" and r["obs_date"] == "2025-04-01")
    assert eur_row["meta"]["quote_convention"] == "USD_per_EUR"
    assert eur_row["meta"]["yahoo_symbol"] == "EURUSD=X"
    assert eur_row["value"] == pytest.approx(1.0820)
    jpy_row = next(r for r in rows if r["series_id"] == "FX/JPY" and r["obs_date"] == "2025-04-02")
    assert jpy_row["meta"]["quote_convention"] == "JPY_per_USD"
    assert jpy_row["value"] == pytest.approx(149.95)
    aud_row = next(r for r in rows if r["series_id"] == "FX/AUD" and r["obs_date"] == "2025-04-01")
    assert aud_row["meta"]["quote_convention"] == "USD_per_AUD"
    assert aud_row["meta"]["yahoo_symbol"] == "AUDUSD=X"
    chf_row = next(r for r in rows if r["series_id"] == "FX/CHF" and r["obs_date"] == "2025-04-01")
    assert chf_row["meta"]["quote_convention"] == "CHF_per_USD"
    assert chf_row["meta"]["yahoo_symbol"] == "USDCHF=X"
    nzd_row = next(r for r in rows if r["series_id"] == "FX/NZD" and r["obs_date"] == "2025-04-02")
    assert nzd_row["meta"]["quote_convention"] == "USD_per_NZD"
    assert nzd_row["meta"]["yahoo_symbol"] == "NZDUSD=X"


@pytest.mark.unit
def test_yahoo_fx_payload_to_rows_skips_unknown_symbols() -> None:
    """The boundary already filters NaN closes — payload-to-rows just guards
    against a yahoo_symbol the caller didn't ask about (e.g. partial mapping)."""
    import polars as pl

    payload = pl.DataFrame(
        {
            "obs_date": ["2025-04-01", "2025-04-01"],
            "yahoo_symbol": ["EURUSD=X", "AUDUSD=X"],
            "close": [1.08, 0.66],
        }
    )

    rows = yahoo_fx_payload_to_rows(
        payload,
        {"EURUSD=X": {"series_id": "FX/EUR", "quote_convention": "USD_per_EUR"}},
    )
    assert len(rows) == 1
    assert rows[0]["series_id"] == "FX/EUR"


@pytest.mark.unit
def test_fetch_fx_yahoo_returns_correct_schema(monkeypatch) -> None:
    """End-to-end: fetch_fx_yahoo mocks the yfinance boundary and returns
    rows that match the macro_series_observations schema."""
    import digiquant.data.prices.macro_ingest as mi

    captured: dict[str, list[str]] = {}

    def fake_download(yahoo_symbols, *, start, end):
        captured["symbols"] = yahoo_symbols
        return _fake_yahoo_long_frame()

    monkeypatch.setattr(mi, "_yahoo_fx_download", fake_download)
    rows = fetch_fx_yahoo(start="2025-04-01", end="2025-04-03")

    # All seven default pairs were requested
    assert set(captured["symbols"]) == {
        "EURUSD=X",
        "GBPUSD=X",
        "JPY=X",
        "CAD=X",
        "AUDUSD=X",
        "USDCHF=X",
        "NZDUSD=X",
    }
    # Schema matches macro_series_observations
    assert len(rows) == 14
    for r in rows:
        assert r["source"] == "yahoo"
        assert r["series_id"].startswith("FX/")
        assert isinstance(r["value"], float)
        assert r["unit"] == "fx"
        assert "quote_convention" in r["meta"]
    # Dedupe upsert key (source, series_id, obs_date) is unique across rows
    keys = {(r["source"], r["series_id"], r["obs_date"]) for r in rows}
    assert len(keys) == len(rows)


@pytest.mark.unit
def test_fetch_fx_yahoo_latest_only_keeps_newest_daily_candle_per_leg(monkeypatch) -> None:
    import digiquant.data.prices.macro_ingest as mi

    monkeypatch.setattr(
        mi,
        "_yahoo_fx_download",
        lambda symbols, *, start, end: _fake_yahoo_long_frame(),
    )
    rows = fetch_fx_yahoo(latest_only=True)

    assert len(rows) == 7
    assert {row["series_id"] for row in rows} == {
        "FX/EUR",
        "FX/GBP",
        "FX/JPY",
        "FX/CAD",
        "FX/AUD",
        "FX/CHF",
        "FX/NZD",
    }
    assert {row["obs_date"] for row in rows} == {"2025-04-02"}
    eur = next(row for row in rows if row["series_id"] == "FX/EUR")
    assert eur["value"] == pytest.approx(1.0835)


@pytest.mark.unit
def test_today_fx_refresh_is_last_wins_on_existing_daily_key() -> None:
    earlier = {
        "source": "yahoo",
        "series_id": "FX/EUR",
        "obs_date": "2026-08-21",
        "value": 1.10,
        "unit": "fx",
    }
    refreshed = {**earlier, "value": 1.11}

    assert dedupe_observation_rows([earlier, refreshed]) == [refreshed]


@pytest.mark.unit
def test_fetch_fx_yahoo_handles_empty_payload(monkeypatch) -> None:
    """Upstream returns an empty frame (e.g. weekend / blackout) → empty rows,
    not a crash."""
    import digiquant.data.prices.macro_ingest as mi
    import polars as pl

    empty_frame = pl.DataFrame(
        schema={"obs_date": pl.String, "yahoo_symbol": pl.String, "close": pl.Float64}
    )
    monkeypatch.setattr(mi, "_yahoo_fx_download", lambda symbols, *, start, end: empty_frame)
    rows = fetch_fx_yahoo()
    assert rows == []


@pytest.mark.unit
def test_fetch_fx_yahoo_does_not_collide_with_frankfurter_rows() -> None:
    """The dedupe key is (source, series_id, obs_date). Yahoo rows use
    source='yahoo', Frankfurter rows use source='frankfurter' — both can
    coexist without overwriting each other."""
    yahoo_rows = [
        {
            "source": "yahoo",
            "series_id": "FX/EUR",
            "obs_date": "2025-04-01",
            "value": 1.08,
            "unit": "fx",
        },
    ]
    ff_rows = [
        {
            "source": "frankfurter",
            "series_id": "FX/EUR",
            "obs_date": "2025-04-01",
            "value": 0.92,
            "unit": "fx",
        },
    ]
    deduped = dedupe_observation_rows(yahoo_rows + ff_rows)
    assert len(deduped) == 2  # both survive — distinct sources
    sources = {r["source"] for r in deduped}
    assert sources == {"yahoo", "frankfurter"}


# ─── Yahoo FX intraday candles (twelve-x turn grading) ─────────────────


def _fake_yahoo_ohlc_frame():
    """Long-format Polars frame matching `_yahoo_fx_download(ohlc=True)`'s
    post-conversion contract: one row per (ts, symbol) with an OHLC quad.
    The boundary helper is responsible for the pandas→Polars conversion, so
    tests work with Polars only."""
    from datetime import UTC, datetime

    import polars as pl

    rows = []
    for hour in (13, 14):
        for idx, sym in enumerate(YAHOO_FX_DEFAULT):
            rows.append(
                {
                    "ts": datetime(2025, 4, 1, hour, tzinfo=UTC),
                    "yahoo_symbol": sym,
                    "open": 100.0 + idx,
                    "high": 101.0 + idx,
                    "low": 99.0 + idx,
                    "close": 100.5 + idx,
                }
            )
    return pl.DataFrame(rows)


@pytest.mark.unit
def test_fetch_fx_intraday_one_batched_download_defaults_to_1h_730d(monkeypatch) -> None:
    import digiquant.data.prices.macro_ingest as mi

    calls: list[dict] = []

    def fake_download(yahoo_symbols, **kwargs):
        calls.append({"symbols": list(yahoo_symbols), **kwargs})
        return _fake_yahoo_ohlc_frame()

    monkeypatch.setattr(mi, "_yahoo_fx_download", fake_download)
    candles = fetch_fx_intraday()

    # One HTTP call for all seven default pairs — not one per pair.
    assert len(calls) == 1
    assert set(calls[0]["symbols"]) == set(YAHOO_FX_DEFAULT)
    assert calls[0]["interval"] == "1h"
    assert calls[0]["period"] == "730d"
    assert calls[0]["ohlc"] is True
    # 7 pairs x 2 bars, ids matching the daily FX/<CUR> convention exactly.
    assert len(candles) == 14
    assert {c.series_id for c in candles} == {
        "FX/EUR",
        "FX/GBP",
        "FX/JPY",
        "FX/CAD",
        "FX/AUD",
        "FX/CHF",
        "FX/NZD",
    }
    eur = next(c for c in candles if c.series_id == "FX/EUR" and c.ts.hour == 13)
    assert eur.close == pytest.approx(100.5)
    assert eur.open == pytest.approx(100.0)


@pytest.mark.unit
def test_fetch_fx_intraday_passes_interval_period_and_custom_symbols(monkeypatch) -> None:
    import digiquant.data.prices.macro_ingest as mi

    captured: dict = {}

    def fake_download(yahoo_symbols, **kwargs):
        captured.update({"symbols": list(yahoo_symbols), **kwargs})
        return _fake_yahoo_ohlc_frame()

    monkeypatch.setattr(mi, "_yahoo_fx_download", fake_download)
    mapping = {"EURUSD=X": {"series_id": "FX/EUR", "quote_convention": "USD_per_EUR"}}
    candles = fetch_fx_intraday(interval="30m", period="60d", symbols=mapping)

    assert captured["symbols"] == ["EURUSD=X"]
    assert captured["interval"] == "30m"
    assert captured["period"] == "60d"
    assert captured["ohlc"] is True
    assert {c.series_id for c in candles} == {"FX/EUR"}


@pytest.mark.unit
def test_fetch_fx_intraday_timestamps_are_tz_aware_utc(monkeypatch) -> None:
    """Naive frame timestamps are stamped UTC; offsets are converted to UTC."""
    from datetime import timedelta

    import digiquant.data.prices.macro_ingest as mi
    import polars as pl

    payload = pl.DataFrame(
        {
            "ts": ["2025-04-01T13:00:00", "2025-04-01T15:00:00+02:00"],
            "yahoo_symbol": ["EURUSD=X", "EURUSD=X"],
            "open": [1.08, 1.09],
            "high": [1.10, 1.11],
            "low": [1.07, 1.08],
            "close": [1.09, 1.10],
        }
    )
    monkeypatch.setattr(mi, "_yahoo_fx_download", lambda symbols, **kwargs: payload)
    candles = fetch_fx_intraday()

    assert len(candles) == 2
    for candle in candles:
        assert candle.ts.tzinfo is not None
        assert candle.ts.utcoffset() == timedelta(0)
    naive, offset = candles
    assert naive.ts.hour == 13  # naive input is stamped UTC, not shifted
    assert offset.ts.hour == 13  # 15:00+02:00 == 13:00 UTC


@pytest.mark.unit
def test_fx_intraday_payload_drops_missing_or_non_finite_ohlc() -> None:
    """NaN, NULL and inf in any OHLC field drop the whole candle."""
    import polars as pl

    payload = pl.DataFrame(
        {
            "ts": ["2025-04-01T13:00:00+00:00"] * 4,
            "yahoo_symbol": ["EURUSD=X"] * 4,
            "open": [1.08, 1.08, 1.08, 1.08],
            "high": [1.10, float("nan"), 1.10, 1.10],
            "low": [1.07, 1.07, None, 1.07],
            "close": [1.09, 1.09, 1.09, float("inf")],
        }
    )
    candles = fx_intraday_payload_to_candles(payload, YAHOO_FX_DEFAULT)

    assert len(candles) == 1
    assert candles[0].series_id == "FX/EUR"


@pytest.mark.unit
def test_fetch_fx_intraday_skips_unmapped_symbols(monkeypatch) -> None:
    import digiquant.data.prices.macro_ingest as mi
    import polars as pl

    payload = pl.DataFrame(
        {
            "ts": ["2025-04-01T13:00:00+00:00", "2025-04-01T13:00:00+00:00"],
            "yahoo_symbol": ["EURUSD=X", "NOTAMAPPED=X"],
            "open": [1.08, 1.0],
            "high": [1.10, 1.1],
            "low": [1.07, 0.9],
            "close": [1.09, 1.0],
        }
    )
    monkeypatch.setattr(mi, "_yahoo_fx_download", lambda symbols, **kwargs: payload)
    candles = fetch_fx_intraday()

    assert [c.series_id for c in candles] == ["FX/EUR"]


@pytest.mark.unit
def test_fetch_fx_intraday_handles_empty_payload(monkeypatch) -> None:
    """Upstream returns an empty frame (weekend / blackout) → no candles, no crash."""
    import digiquant.data.prices.macro_ingest as mi
    import polars as pl

    empty = pl.DataFrame(
        schema={
            "ts": pl.Datetime("us", "UTC"),
            "yahoo_symbol": pl.String,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
        }
    )
    monkeypatch.setattr(mi, "_yahoo_fx_download", lambda symbols, **kwargs: empty)
    assert fetch_fx_intraday() == []


# ─── CLI default sources (issue #328 — fred,yahoo replaces fred,frankfurter,fng) ─


@pytest.mark.unit
def test_fetch_macro_cli_default_sources_are_fred_and_yahoo() -> None:
    """Regression guard: the default --sources value must stay 'fred,yahoo' so
    the scheduled GitHub Action stops calling Frankfurter / FNG when no flag
    is passed."""
    from digiquant.cli.prices import fetch_macro_cmd

    sources_param = next(p for p in fetch_macro_cmd.params if p.name == "sources")
    assert sources_param.default == "fred,yahoo"
