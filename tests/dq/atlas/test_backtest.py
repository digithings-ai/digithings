"""Decision backtest core (Pillar 3C).

backtest_decisions turns realized per-decision trades into a tear sheet: hit-rate, alpha,
compounded return vs benchmark, max drawdown, information/Sortino ratios, and conviction-
bucket calibration (do higher-conviction calls earn higher alpha?).
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.backtest import Trade, backtest_decisions

pytestmark = pytest.mark.unit


def _t(day: int, ticker: str, ret: float, bench: float, conviction: float | None) -> Trade:
    return Trade(
        date=date(2026, 6, day),
        ticker=ticker,
        return_frac=ret,
        benchmark_frac=bench,
        conviction=conviction,
        stance="buy",
    )


def test_empty_is_zeroed() -> None:
    r = backtest_decisions([])
    assert r.n_trades == 0
    assert r.hit_rate == 0.0
    assert r.annualized_return_pct is None
    assert r.conviction_buckets == []


def test_hit_rate_and_alpha() -> None:
    # A +5% alpha, B +3% alpha, C −3% alpha → 2/3 hit, mean alpha = +5/3 %.
    r = backtest_decisions(
        [
            _t(1, "A", 0.10, 0.05, 5),
            _t(2, "B", 0.08, 0.05, 4),
            _t(3, "C", 0.02, 0.05, 2),
        ]
    )
    assert r.n_trades == 3
    assert r.hit_rate == pytest.approx(2 / 3, abs=1e-3)
    assert r.mean_alpha_pct == pytest.approx(5 / 3, abs=1e-3)
    assert r.information_ratio > 0  # positive mean alpha
    # Compounded: (1.10)(1.08)(1.02) − 1 ≈ 21.18%; benchmark (1.05)³ − 1 ≈ 15.76%.
    assert r.total_return_pct == pytest.approx(21.176, abs=0.01)
    assert r.benchmark_total_return_pct == pytest.approx(15.7625, abs=0.01)


def test_conviction_calibration_buckets() -> None:
    r = backtest_decisions(
        [
            _t(1, "A", 0.10, 0.05, 5),  # high, +5%
            _t(2, "B", 0.08, 0.05, 4),  # high, +3%
            _t(3, "C", 0.02, 0.05, 2),  # medium, −3%
        ]
    )
    buckets = {b.bucket: b for b in r.conviction_buckets}
    assert buckets["high"].n == 2
    assert buckets["high"].mean_alpha_pct == pytest.approx(4.0)  # (5+3)/2
    assert buckets["medium"].mean_alpha_pct == pytest.approx(-3.0)
    assert buckets["high"].mean_alpha_pct > buckets["medium"].mean_alpha_pct  # calibrated


def test_max_drawdown_of_equity_curve() -> None:
    # returns 10% / −20% / 5% → nav 1.10 → 0.88 → 0.924; worst dd = 0.88/1.10 − 1 = −20%.
    r = backtest_decisions(
        [_t(1, "A", 0.10, 0.0, 3), _t(2, "B", -0.20, 0.0, 3), _t(3, "C", 0.05, 0.0, 3)]
    )
    assert r.max_drawdown_pct == pytest.approx(-20.0, abs=0.01)


def test_unknown_conviction_bucket() -> None:
    r = backtest_decisions([_t(1, "A", 0.03, 0.01, None)])
    assert {b.bucket for b in r.conviction_buckets} == {"unknown"}


def test_annualizes_same_run_decisions_via_window_end() -> None:
    # Many tickers booked under one run_date (the decision_log norm): entry→entry span is 0,
    # but carrying each holding-window close lets the sequence still annualize.
    entry = date(2026, 6, 1)
    close = date(2026, 7, 1)  # ~30-day holding window
    trades = [
        Trade(date=entry, ticker="A", return_frac=0.05, benchmark_frac=0.02, end_date=close),
        Trade(date=entry, ticker="B", return_frac=0.03, benchmark_frac=0.02, end_date=close),
    ]
    r = backtest_decisions(trades)
    assert r.annualized_return_pct is not None
    assert r.annualized_return_pct > 0
    # Without a window close (legacy callers) a same-day book has no span → no annualization.
    bare = [Trade(date=entry, ticker="A", return_frac=0.05, benchmark_frac=0.02)]
    assert backtest_decisions(bare).annualized_return_pct is None


def test_sortino_falls_back_to_info_ratio_when_no_downside() -> None:
    # All-positive alpha → downside deviation is 0; Sortino reports the info ratio (its Sharpe
    # analogue), not a misleading 0.0.
    r = backtest_decisions([_t(1, "A", 0.10, 0.05, 4), _t(2, "B", 0.07, 0.05, 4)])
    assert r.information_ratio > 0
    assert r.sortino_ratio == pytest.approx(r.information_ratio)
