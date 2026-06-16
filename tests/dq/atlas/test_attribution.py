"""Single-benchmark attribution core (Pillar 3B).

compute_position_attribution decomposes active return into per-holding contribution +
selection and a cash-drag allocation row. The defining property is the reconciliation
identity: Σ total_attribution == portfolio_return − benchmark_return (when every holding is
priced).
"""

from __future__ import annotations

import pytest

from digiquant.olympus.atlas.attribution import (
    Holding,
    attribution_rows_to_records,
    compute_position_attribution,
)

pytestmark = pytest.mark.unit


def _by_ticker(result):
    return {r.ticker: r for r in result.rows}


def test_reconciliation_identity_fully_invested() -> None:
    # 60% A (+10%) / 40% B (0%), benchmark +5%. port = 6%, active = +1%.
    result = compute_position_attribution(
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
    result = compute_position_attribution(
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
    result = compute_position_attribution(
        holdings=[Holding("WIN", 1.0, 0.08, None)], benchmark_return_frac=0.03
    )
    assert _by_ticker(result)["WIN"].selection_effect_pct == pytest.approx(5.0)  # beats benchmark
    loser = compute_position_attribution(
        holdings=[Holding("LOSE", 1.0, 0.01, None)], benchmark_return_frac=0.03
    )
    assert _by_ticker(loser)["LOSE"].selection_effect_pct == pytest.approx(-2.0)


def test_unpriced_holding_marks_partial() -> None:
    result = compute_position_attribution(
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
    result = compute_position_attribution(
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


def test_records_flatten_with_date() -> None:
    result = compute_position_attribution(
        holdings=[Holding("AAA", 1.0, 0.05, "sector-technology")], benchmark_return_frac=0.05
    )
    records = attribution_rows_to_records(result, date_str="2026-06-12")
    assert records[0]["date"] == "2026-06-12"
    assert records[0]["ticker"] == "AAA"
    assert records[0]["metrics_as_of"] == "2026-06-12"
    assert "selection_effect_pct" in records[0]


def test_empty_holdings_is_flat() -> None:
    result = compute_position_attribution(holdings=[], benchmark_return_frac=0.05)
    # No holdings → the whole book is cash; active = −benchmark (full cash drag).
    assert result.rows[0].ticker == "CASH"
    assert result.active_return_pct == pytest.approx(-5.0)
    assert result.reconciles is True
