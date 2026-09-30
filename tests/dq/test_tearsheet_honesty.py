"""Honesty threading through tearsheet surfaces (#4828).

Each surface that renders win-rate must carry N + Wilson 95% CI (never a
bare %), with LOW SAMPLE / REFUSED banners at the warn@30 / refuse@10
floors. African grey rule: every assertion names N.
"""

from __future__ import annotations

import pytest
from digiquant.charts.trades import _build_win_rate_donut, count_winning_trades
from digiquant.models import BacktestResult
from digiquant.stats.honesty import DISCLAIMER
from digiquant.tearsheet_page import _build_page
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


def _page(win_rate: float | None, num_trades: int, **kw) -> str:
    blanks = {
        "strategy_display": "EMA Cross",
        "symbols_str": "BTC-USD",
        "params_str": "period=20",
        "profit_factor": 1.2,
        "sortino": 0.5,
        "calmar": 0.5,
        "price_gen": "",
        "price_tab": "",
        "equity_gen": "",
        "equity_tab": "",
        "dd_gen": "",
        "dd_tab": "",
        "monthly_gen": "",
        "dist_gen": "",
        "dist_tab": "",
        "rolling_gen": "",
        "rolling_tab": "",
        "yearly_gen": "",
        "rolling_equity_html": "",
        "realized_pnl_html": "",
        "trade_pnl_dist_html": "",
        "trade_pnl_dist_trades_html": "",
        "rolling_dd_html": "",
        "monthly_yearly_html": "",
        "per_trade_pnl_html": "",
        "win_rate_donut_html": "",
        "rolling_calmar_html": "",
        "cum_trade_pnl_html": "",
        "underwater_html": "",
    }
    blanks.update(kw)
    return _build_page(_result(num_trades), win_rate=win_rate, **blanks)


def test_kpi_strip_win_rate_carries_n_and_ci() -> None:
    """KPI WIN RATE 0.6 with n=50 carries N + CI, not a bare %."""
    html = _page(0.6, 50)
    assert "WIN RATE" in html  # n=50
    assert "n=50" in html  # n=50
    assert "CI" in html  # n=50
    assert "60.0% (30/50" in html  # k=30, n=50


def test_kpi_win_rate_threshold_uses_ci_lower_bound() -> None:
    """Point estimate 0.6 (> 0.5) with n=12 has CI lo ~0.32 → negative."""
    html = _page(0.6, 12)
    assert 'WIN RATE</span><span class="kpi-value negative">' in html  # n=12


def test_kpi_win_rate_confident_above_half_is_positive() -> None:
    """Win rate 0.9 with n=1000 has CI lo > 0.5 → positive."""
    html = _page(0.9, 1000)
    assert 'WIN RATE</span><span class="kpi-value positive">' in html  # n=1000


def test_kpi_win_rate_refused_below_floor() -> None:
    """Win rate 0.6 with n=5 renders REFUSED on the KPI strip."""
    html = _page(0.6, 5)
    assert "REFUSED" in html  # n=5


def test_rendered_page_ships_disclaimer_verbatim() -> None:
    """Fixed disclaimer string is present on the rendered page (n=50)."""
    html = _page(0.6, 50)
    assert DISCLAIMER in html  # n=50


def test_donut_uses_caller_wins_not_round() -> None:
    """win_rate=0.5, n=10, num_wins=7 → slices [7, 3], not round(0.5*10)."""
    fig = _build_win_rate_donut(0.5, 10, num_wins=7)
    assert fig is not None  # n=10
    assert list(fig.data[0].values) == [7, 3]  # k=7, n=10
    ann = fig.layout.annotations[0].text
    assert "n=10" in ann  # n=10
    assert "CI" in ann  # n=10


def test_donut_center_shows_honest_rate() -> None:
    """Donut for k=30, n=50 centers the point estimate with N + CI."""
    fig = _build_win_rate_donut(0.6, 50, num_wins=30)
    assert fig is not None  # n=50
    ann = fig.layout.annotations[0].text
    assert "60.0%" in ann  # k=30, n=50
    assert "n=50" in ann  # n=50


def test_donut_refused_below_floor() -> None:
    """Donut for n=5 shows REFUSED in the center, not a win-rate %."""
    fig = _build_win_rate_donut(0.6, 5, num_wins=3)
    assert fig is not None  # n=5
    ann = fig.layout.annotations[0].text
    assert "REFUSED" in ann  # n=5


def test_count_winning_trades_from_series() -> None:
    """3 positives in a 10-trade series → 7 wins is wrong, 3 is right."""
    import polars as pl

    series = pl.Series("value", [10.0, -5.0, 3.0, -1.0, 7.0])
    assert count_winning_trades(series) == 3  # n=5
    assert count_winning_trades(None) is None
