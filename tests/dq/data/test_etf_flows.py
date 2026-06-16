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

    def test_zscore_uses_leave_one_out_baseline(self) -> None:
        # The spike must NOT contaminate its own baseline: scored against the 3 prior steady
        # days, the 6x last-day turnover is a large z (not damped toward a small in-sample cap).
        z = compute_etf_flows_proxy(pl.DataFrame(_rows()), as_of=date(2026, 6, 15))["flows"]["XLK"][
            "dollar_volume_z"
        ]
        assert z is not None and z > 5.0  # in-sample would have pinned it near ~1.3

    def test_two_row_window_has_no_zscore(self) -> None:
        # A 2-row window leaves only ONE baseline point → no sample std → z is None (not a
        # spurious constant). OBV trend still computes.
        rows = [
            {"ticker": "AA", "date": "2026-06-12", "close": 10.0, "volume": 100},
            {"ticker": "AA", "date": "2026-06-15", "close": 11.0, "volume": 5_000},
        ]
        sig = compute_etf_flows_proxy(pl.DataFrame(rows), as_of=date(2026, 6, 15))["flows"]["AA"]
        assert sig["dollar_volume_z"] is None
        assert sig["obv_trend"] == "accumulation"

    def test_non_finite_values_yield_none_not_nan(self) -> None:
        # An inf close*volume must not silently produce a NaN z / inf avg.
        rows = [
            {"ticker": "BB", "date": "2026-06-11", "close": 1.0, "volume": 100.0},
            {"ticker": "BB", "date": "2026-06-12", "close": float("inf"), "volume": 100.0},
            {"ticker": "BB", "date": "2026-06-15", "close": 3.0, "volume": 100.0},
        ]
        sig = compute_etf_flows_proxy(pl.DataFrame(rows), as_of=date(2026, 6, 15))["flows"]["BB"]
        assert sig["dollar_volume_z"] is None
        assert sig["avg_dollar_volume"] is None

    def test_missing_required_column_returns_empty_not_crash(self) -> None:
        # A non-empty frame missing `volume` returns the stamped empty shape, not a crash.
        rows = [{"ticker": "CC", "date": "2026-06-15", "close": 10.0}]
        out = compute_etf_flows_proxy(pl.DataFrame(rows), as_of=date(2026, 6, 15))
        assert out["universe_size"] == 0
        assert out["flows"] == {}
        assert "proxy" in out["note"].lower()
