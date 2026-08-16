"""In-memory, non-persisted reason-coded adjustment events for the H8 sizing
pipeline (#2417, Olympus WP2 Task 2.2, OLY-REV-009).

Explanation-only: nothing here is written to Supabase, and this is a deliberately
separate type from the persisted portfolio-lineage ledger models in
:mod:`digiquant.olympus.hermes.models.portfolio_ledger` (``TargetAdjustmentType`` /
``TargetAdjustment``, #2415) — that ledger is append-only, persisted, and currently
fully dark (zero production traffic). ``TargetAdjustmentType`` was extended
(#2417) to carry the same 12 string values defined here as an additive superset
of its original 3 (``cap``/``rounding``/``carry``), so the two vocabularies agree
on their reason codes even though the two *types* stay separate — one governs
an in-memory event, the other a persisted row, and unifying them would couple
the dark ledger to the live sizing pipeline for no present benefit. These
events are plain return-value objects threaded through the H8 sizing call chain
and intended for future in-process consumers that want an explanation of a
requested->approved delta (H9, pre-trade risk, outcome episodes) — no such
consumer exists in this codebase yet; see ``RebalancePayload.adjustments`` in
``atlas/state.py`` for the current wire shape. H8 remains the sole owner of the
final weight — nothing here changes, reorders, or re-derives a weight; every
event field is populated from a value already computed on the real
weight-calculation path.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class SizingAdjustmentType(StrEnum):
    """The 12 named H8 adjustment reasons (#2417)."""

    CONVICTION_FLOOR = "conviction_floor"
    SINGLE_NAME_CAP = "single_name_cap"
    SECTOR_CAP = "sector_cap"
    CORRELATION_DEDUP = "correlation_dedup"
    VOLATILITY_SCALE = "volatility_scale"
    DRAWDOWN_BREAKER = "drawdown_breaker"
    GRID_ROUNDING = "grid_rounding"
    CADENCE_HOLD = "cadence_hold"
    MINIMUM_HOLD_OVERRIDE = "minimum_hold_override"
    CONTINUITY_CARRY = "continuity_carry"
    FINAL_GROSS_SCALE = "final_gross_scale"
    FLAT_EXIT = "flat_exit"


class SizingAdjustment(BaseModel):
    """One reason-coded requested->approved delta on a single ticker.

    ``unit`` is ``"pct"`` for weight-percentage deltas (the common case) or
    ``"conviction"`` for the conviction-floor haircut, whose original/adjusted
    values are conviction scores, not portfolio percentages.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str
    adjustment_type: SizingAdjustmentType
    original_pct: float
    adjusted_pct: float
    unit: Literal["pct", "conviction"] = "pct"
    reason: Annotated[str, Field(min_length=1, max_length=200)]


class LineageValidationError(Exception):
    """Base class for H8 lineage-validation failures (#2417).

    Deliberately separate from the fail-soft try/except already guarding
    ``size_portfolio()`` inside ``_build_sized_book`` — that guard exists to keep a
    sizing crash from taking down the whole node. This layer is louder on purpose:
    an unexplained requested->approved delta means an adjustment site forgot to
    emit an event, not that upstream data was bad, so callers are expected to log
    it (not swallow it silently and not let it fail the run).
    """


class UnexplainedDeltaError(LineageValidationError):
    """Raised when a requested->approved delta has no matching ``SizingAdjustment``."""


def validate_sizing_lineage(
    requested: dict[str, float],
    approved: dict[str, float],
    adjustments: list[SizingAdjustment],
    *,
    materiality_pct: float,
) -> None:
    """Raise :class:`UnexplainedDeltaError` if a material delta has no matching event.

    ``materiality_pct`` must be the same band/threshold value the no-trade-band
    clamp in ``turnover.apply_turnover_to_sized_book`` uses for a given ticker, so
    this never re-flags a delta that clamp already decided was immaterial with an
    independently-tuned epsilon. Callers pass the largest (most permissive) band in
    play when a single scalar is required.
    """
    explained = {a.ticker for a in adjustments}
    tickers = set(requested) | set(approved)
    unexplained = sorted(
        ticker
        for ticker in tickers
        if abs(approved.get(ticker, 0.0) - requested.get(ticker, 0.0)) > materiality_pct
        and ticker not in explained
    )
    if unexplained:
        raise UnexplainedDeltaError(f"unexplained sizing delta(s) for: {unexplained}")


__all__ = [
    "LineageValidationError",
    "SizingAdjustment",
    "SizingAdjustmentType",
    "UnexplainedDeltaError",
    "validate_sizing_lineage",
]
