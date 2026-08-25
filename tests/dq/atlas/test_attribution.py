"""Current-book lookback core (#2598).

compute_current_book_lookback decomposes trailing-window active return into per-holding
contribution + selection and a cash-drag allocation row. The defining property is the
reconciliation identity: Σ total_attribution == portfolio_return − benchmark_return
(when every holding is priced) against the *identical* lookback-interval benchmark.
"""

from __future__ import annotations

import pytest
from digiquant.olympus.atlas.attribution import (
    Holding,
    attribution_rows_to_records,
    compute_current_book_lookback,
    compute_position_attribution,
    lookback_rows_to_records,
)

pytestmark = pytest.mark.unit


def _by_ticker(result):
    return {r.ticker: r for r in result.rows}


def test_reconciliation_identity_fully_invested() -> None:
    # 60% A (+10%) / 40% B (0%), benchmark +5%. port = 6%, active = +1%.
    result = compute_current_book_lookback(
        holdings=[
            Holding("AAA", 0.60, 0.10, "sector-technology"),
            Holding("BBB", 0.40, 0.00, "fixed-income"),
        ],
        benchmark_return_frac=0.05,
    )
    assert result.portfolio_return_pct == pytest.approx(6.0)
    assert result.active_return_pct == pytest.approx(1.0)
    assert result.reconciles is True
    total = sum(r.total_attribution_pct for r in result.rows)
    assert total == pytest.approx(result.active_return_pct, abs=1e-6)
    rows = _by_ticker(result)
    assert rows["AAA"].selection_effect_pct == pytest.approx(3.0)  # 0.6×(10−5)
    assert rows["BBB"].selection_effect_pct == pytest.approx(-2.0)  # 0.4×(0−5)
    assert rows["AAA"].contribution_pct == pytest.approx(6.0)  # 0.6×10


def test_cash_drag_reconciles() -> None:
    # 50% A (+10%) / 50% cash, benchmark +5%. port = 5%, active = 0%.
    result = compute_current_book_lookback(
        holdings=[Holding("AAA", 0.50, 0.10, "sector-technology")],
        benchmark_return_frac=0.05,
    )
    assert result.active_return_pct == pytest.approx(0.0)
    cash = _by_ticker(result)["CASH"]
    assert cash.weight_pct == pytest.approx(50.0)
    assert cash.allocation_effect_pct == pytest.approx(-2.5)  # −0.5×5
    assert result.reconciles is True
    assert sum(r.total_attribution_pct for r in result.rows) == pytest.approx(0.0, abs=1e-6)


def test_outperform_positive_underperform_negative_selection() -> None:
    result = compute_current_book_lookback(
        holdings=[Holding("WIN", 1.0, 0.08, None)], benchmark_return_frac=0.03
    )
    assert _by_ticker(result)["WIN"].selection_effect_pct == pytest.approx(5.0)  # beats benchmark
    loser = compute_current_book_lookback(
        holdings=[Holding("LOSE", 1.0, 0.01, None)], benchmark_return_frac=0.03
    )
    assert _by_ticker(loser)["LOSE"].selection_effect_pct == pytest.approx(-2.0)


def test_unpriced_holding_marks_partial() -> None:
    result = compute_current_book_lookback(
        holdings=[
            Holding("AAA", 0.50, 0.10, None),
            Holding("ZZZ", 0.50, None, None),  # no price window
        ],
        benchmark_return_frac=0.05,
    )
    assert result.reconciles is False  # an unpriced holding breaks the exact identity
    zzz = _by_ticker(result)["ZZZ"]
    assert zzz.contribution_pct is None
    assert zzz.selection_effect_pct is None
    assert zzz.total_attribution_pct is None


def test_net_invested_over_100_reconciles_with_negative_cash() -> None:
    # Weights sum to 120% (a leveraged book). cash_frac = −0.20 must be kept (not clamped)
    # so the identity still holds: Σ total == portfolio_return − benchmark.
    result = compute_current_book_lookback(
        holdings=[
            Holding("AAA", 0.70, 0.10, "sector-technology"),
            Holding("BBB", 0.50, 0.04, "fixed-income"),
        ],
        benchmark_return_frac=0.05,
    )
    cash = {r.ticker: r for r in result.rows}["CASH"]
    assert cash.weight_pct == pytest.approx(-20.0)  # negative = leverage sleeve
    assert result.reconciles is True
    assert sum(r.total_attribution_pct for r in result.rows) == pytest.approx(
        result.active_return_pct, abs=1e-6
    )


def test_lookback_records_carry_explicit_interval_and_contract() -> None:
    result = compute_current_book_lookback(
        holdings=[Holding("AAA", 1.0, 0.05, "sector-technology")], benchmark_return_frac=0.05
    )
    records = lookback_rows_to_records(
        result,
        date_str="2026-06-12",
        window_start_date="2026-05-22",
        window_end_date="2026-06-12",
        lookback_days=21,
    )
    assert records[0]["date"] == "2026-06-12"
    assert records[0]["ticker"] == "AAA"
    assert records[0]["metrics_as_of"] == "2026-06-12"
    assert records[0]["window_start_date"] == "2026-05-22"
    assert records[0]["window_end_date"] == "2026-06-12"
    assert records[0]["lookback_days"] == 21
    assert records[0]["contract"] == "current_book_lookback"
    assert "selection_effect_pct" in records[0]


def test_deprecated_alias_matches_lookback() -> None:
    holdings = [Holding("AAA", 1.0, 0.05, None)]
    assert compute_position_attribution(
        holdings=holdings, benchmark_return_frac=0.03
    ) == compute_current_book_lookback(holdings=holdings, benchmark_return_frac=0.03)


def test_deprecated_records_flatten_with_date() -> None:
    result = compute_current_book_lookback(
        holdings=[Holding("AAA", 1.0, 0.05, "sector-technology")], benchmark_return_frac=0.05
    )
    records = attribution_rows_to_records(result, date_str="2026-06-12")
    assert records[0]["date"] == "2026-06-12"
    assert records[0]["contract"] == "current_book_lookback"


def test_empty_holdings_is_flat() -> None:
    result = compute_current_book_lookback(holdings=[], benchmark_return_frac=0.05)
    # No holdings → the whole book is cash; active = −benchmark (full cash drag).
    assert result.rows[0].ticker == "CASH"
    assert result.active_return_pct == pytest.approx(-5.0)
    assert result.reconciles is True


def test_active_return_uses_identical_period_benchmark_only() -> None:
    """Active return is portfolio − the lookback-interval benchmark, not a different horizon."""
    result = compute_current_book_lookback(
        holdings=[Holding("AAA", 1.0, 0.10, None)],
        benchmark_return_frac=0.04,  # identical 21-day window
    )
    assert result.active_return_pct == pytest.approx(6.0)  # 10 − 4
    # A different benchmark horizon must not be mixed in — caller supplies one interval.
    other = compute_current_book_lookback(
        holdings=[Holding("AAA", 1.0, 0.10, None)],
        benchmark_return_frac=0.01,  # different interval → different active
    )
    assert other.active_return_pct == pytest.approx(9.0)
    assert result.active_return_pct != other.active_return_pct
