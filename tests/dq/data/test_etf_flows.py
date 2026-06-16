"""Tests for the ETF flow-proxy compute (Pillar 1D)."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from digiquant.data.prices.etf_flows import compute_etf_flows_proxy


def _rows() -> list[dict]:
    # XLK: steady ~1M dollar-volume then a big spike on the last day (high z-score), and an
    # uptrend (accumulation). XLE: flat price (no direction) with steady volume → flat OBV.
    return [
        {"ticker": "XLK", "date": "2026-06-10", "close": 100.0, "volume": 10_000},
        {"ticker": "XLK", "date": "2026-06-11", "close": 101.0, "volume": 10_000},
        {"ticker": "XLK", "date": "2026-06-12", "close": 102.0, "volume": 10_000},
        {"ticker": "XLK", "date": "2026-06-15", "close": 104.0, "volume": 60_000},  # turnover spike
        {"ticker": "XLE", "date": "2026-06-10", "close": 90.0, "volume": 5_000},
        {"ticker": "XLE", "date": "2026-06-11", "close": 90.0, "volume": 5_000},
        {"ticker": "XLE", "date": "2026-06-12", "close": 90.0, "volume": 5_000},
        {"ticker": "XLE", "date": "2026-06-15", "close": 90.0, "volume": 5_000},
    ]


@pytest.mark.unit
class TestComputeEtfFlowsProxy:
    def test_turnover_spike_and_accumulation(self) -> None:
        out = compute_etf_flows_proxy(pl.DataFrame(_rows()), as_of=date(2026, 6, 15))
        assert out["universe_size"] == 2
        assert "proxy" in out["note"].lower()  # proxy nature is explicit for the prompt
        xlk = out["flows"]["XLK"]
        assert xlk["dollar_volume_z"] > 1.0  # the last-day turnover spike stands out
        assert xlk["obv_trend"] == "accumulation"  # rising closes on rising volume
        # Flat price → no directional volume → flat OBV; even turnover is steady → z≈0/None.
        assert out["flows"]["XLE"]["obv_trend"] == "flat"

    def test_respects_as_of_cutoff(self) -> None:
        # As of 06-12 the XLK spike (06-15) is excluded → steady turnover, no big z-score.
        out = compute_etf_flows_proxy(pl.DataFrame(_rows()), as_of=date(2026, 6, 12))
        assert out["universe_size"] == 2
        assert out["flows"]["XLK"]["obv_trend"] == "accumulation"

    def test_single_row_ticker_dropped(self) -> None:
        rows = [{"ticker": "ONE", "date": "2026-06-15", "close": 10.0, "volume": 100}]
        out = compute_etf_flows_proxy(pl.DataFrame(rows), as_of=date(2026, 6, 15))
        assert out["universe_size"] == 0  # need >= 2 rows for a signal

    def test_empty_frame(self) -> None:
        out = compute_etf_flows_proxy(pl.DataFrame(), as_of=date(2026, 6, 15))
        assert out["universe_size"] == 0
        assert out["flows"] == {}

    def test_accepts_real_date_dtype(self) -> None:
        frame = pl.DataFrame(_rows()).with_columns(pl.col("date").str.to_date())
        out = compute_etf_flows_proxy(frame, as_of=date(2026, 6, 15))
        assert out["flows"]["XLK"]["obv_trend"] == "accumulation"
