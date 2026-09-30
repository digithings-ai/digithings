"""Honesty threading through tearsheet surfaces (#4828).

Each surface that renders win-rate must carry N + Wilson 95% CI (never a
bare %), with LOW SAMPLE / REFUSED banners at the warn@30 / refuse@10
floors. African grey rule: every assertion names N.
"""

from __future__ import annotations

import pytest
from digiquant.models import BacktestResult
from digiquant.tearsheet_stats import (
    _build_categorized_stats,
    _build_full_stats_table,
    _build_risk_metrics_table,
)

pytestmark = pytest.mark.unit


def _result(num_trades: int) -> BacktestResult:
    return BacktestResult(
        run_id="r1",
        strategy_name="ema_cross",
        symbols=["BTC-USD"],
        start_time="2020-01-01",
        end_time="2021-01-01",
        num_trades=num_trades,
    )


def test_categorized_stats_win_rate_carries_n_and_ci() -> None:
    """Win Rate 0.6 with n=50 renders honest string, not a bare %."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50
    assert "60.0%" in html  # k=30, n=50
    assert "60.00%" not in html  # n=50: old bare-% shape is gone


def test_categorized_stats_low_sample_banner() -> None:
    """Win Rate 0.6 with n=20 renders LOW SAMPLE alongside the interval."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(20))
    assert "LOW SAMPLE" in html  # n=20
    assert "n=20" in html  # n=20


def test_categorized_stats_refused_below_floor() -> None:
    """Win Rate 0.6 with n=5 renders REFUSED, not a percentage."""
    html = _build_categorized_stats(None, None, {"Win Rate": 0.6}, _result(5))
    assert "REFUSED" in html  # n=5


def test_categorized_stats_missing_win_rate_is_dash() -> None:
    """No Win Rate stat with n=50 stays an em-dash, not a fabricated CI."""
    html = _build_categorized_stats(None, None, {}, _result(50))
    assert "—" in html  # n=50


def test_risk_metrics_win_rate_carries_n_and_ci() -> None:
    """Risk table Win Rate 0.6 with n=50 renders honest string."""
    html = _build_risk_metrics_table(None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50


def test_full_stats_win_rate_carries_n_and_ci() -> None:
    """Full-stats dump Win Rate 0.6 with n=50 renders honest string."""
    html = _build_full_stats_table(None, None, {"Win Rate": 0.6}, _result(50))
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50
