"""Per-position performance attribution (Pillar 3B).

A single-benchmark, reconcilable decomposition of the paper book's active return. We have
each holding's return + a single benchmark (SPY), but **no benchmark sector weights**, so
classic multi-sector Brinson allocation/selection is not computable. Instead we compute the
honest quantities that *do* reconcile to the active return:

    contribution_i = wᵢ · rᵢ                      (holding i's share of portfolio return)
    selection_i    = wᵢ · (rᵢ − r_b)              (its return vs the benchmark, weighted)
    cash drag      = −w_cash · r_b                 (holding cash while the benchmark moved)

and the identity (when every holding is priced):

    Σ selection_i + cash_drag  ==  Σ wᵢ·rᵢ − r_b  ==  portfolio_return − benchmark_return
                                ==  active_return

Pure-functional (no I/O, no pandas): the caller assembles per-holding weights + window
returns (from price_history) and the benchmark return, and this returns the rows +
reconciliation. The script half does the Supabase reads/writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any  # noqa  # scored-lint: heterogeneous position_attribution record dicts

_RECONCILE_TOL_PCT = 1e-6


@dataclass(frozen=True)
class Holding:
    """One book holding for attribution: weight + window return (fractions, e.g. 0.03 = 3%)."""

    ticker: str
    weight_frac: float
    return_frac: float | None  # None when the price window is unavailable → excluded
    sector_bucket: str | None = None


@dataclass(frozen=True)
class AttributionRow:
    """One attribution row (a holding, or the synthetic CASH drag row). Percent points."""

    ticker: str
    sector_bucket: str | None
    weight_pct: float
    position_return_pct: float | None
    benchmark_return_pct: float
    contribution_pct: float | None
    selection_effect_pct: float | None
    allocation_effect_pct: float
    total_attribution_pct: float | None


@dataclass(frozen=True)
class AttributionResult:
    rows: list[AttributionRow]
    portfolio_return_pct: float
    benchmark_return_pct: float
    active_return_pct: float  # = Σ total_attribution_pct over priced rows + cash (identity)
    reconciles: bool  # Σ total == active within tolerance (False if a holding was unpriced)


def _pct(frac: float) -> float:
    return round(frac * 100.0, 6)


def compute_position_attribution(
    *, holdings: Sequence[Holding], benchmark_return_frac: float
) -> AttributionResult:
    """Decompose active return per holding vs a single benchmark (see module doc).

    Holdings with ``return_frac is None`` (no price window) are emitted with null effects
    and excluded from the totals; ``reconciles`` then reports ``False`` so callers can flag
    a partial attribution. Returns are fractions in, percent points out.
    """
    r_b = benchmark_return_frac
    rows: list[AttributionRow] = []
    port_return = 0.0
    invested = 0.0
    any_unpriced = False

    for h in holdings:
        invested += h.weight_frac
        if h.return_frac is None:
            any_unpriced = True
            rows.append(
                AttributionRow(
                    ticker=h.ticker,
                    sector_bucket=h.sector_bucket,
                    weight_pct=round(h.weight_frac * 100.0, 4),
                    position_return_pct=None,
                    benchmark_return_pct=_pct(r_b),
                    contribution_pct=None,
                    selection_effect_pct=None,
                    allocation_effect_pct=0.0,
                    total_attribution_pct=None,
                )
            )
            continue
        contribution = h.weight_frac * h.return_frac
        selection = h.weight_frac * (h.return_frac - r_b)
        port_return += contribution
        rows.append(
            AttributionRow(
                ticker=h.ticker,
                sector_bucket=h.sector_bucket,
                weight_pct=round(h.weight_frac * 100.0, 4),
                position_return_pct=_pct(h.return_frac),
                benchmark_return_pct=_pct(r_b),
                contribution_pct=_pct(contribution),
                selection_effect_pct=_pct(selection),
                allocation_effect_pct=0.0,
                total_attribution_pct=_pct(selection),
            )
        )

    cash_frac = max(0.0, 1.0 - invested)
    if cash_frac > 1e-9:
        cash_drag = -cash_frac * r_b  # cash earns 0 while the benchmark moved r_b
        rows.append(
            AttributionRow(
                ticker="CASH",
                sector_bucket="cash",
                weight_pct=round(cash_frac * 100.0, 4),
                position_return_pct=0.0,
                benchmark_return_pct=_pct(r_b),
                contribution_pct=0.0,
                selection_effect_pct=0.0,
                allocation_effect_pct=_pct(cash_drag),
                total_attribution_pct=_pct(cash_drag),
            )
        )

    active = port_return - r_b
    total_sum = sum(r.total_attribution_pct or 0.0 for r in rows)
    reconciles = (not any_unpriced) and abs(total_sum - _pct(active)) <= _RECONCILE_TOL_PCT
    return AttributionResult(
        rows=rows,
        portfolio_return_pct=_pct(port_return),
        benchmark_return_pct=_pct(r_b),
        active_return_pct=_pct(active),
        reconciles=reconciles,
    )


def attribution_rows_to_records(
    result: AttributionResult, *, date_str: str
) -> list[dict[str, Any]]:
    """Flatten :class:`AttributionResult` rows into ``position_attribution`` upsert dicts."""
    return [
        {
            "date": date_str,
            "ticker": row.ticker,
            "sector_bucket": row.sector_bucket,
            "weight_pct": row.weight_pct,
            "position_return_pct": row.position_return_pct,
            "benchmark_return_pct": row.benchmark_return_pct,
            "contribution_pct": row.contribution_pct,
            "selection_effect_pct": row.selection_effect_pct,
            "allocation_effect_pct": row.allocation_effect_pct,
            "total_attribution_pct": row.total_attribution_pct,
            "metrics_as_of": date_str,
        }
        for row in result.rows
    ]


__all__ = [
    "AttributionResult",
    "AttributionRow",
    "Holding",
    "attribution_rows_to_records",
    "compute_position_attribution",
]
