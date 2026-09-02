"""In-memory reason-coded adjustment events for the H8 sizing pipeline
(#2417, Olympus WP2 Task 2.2, OLY-REV-009), handed to H9 for durable persistence
(#2768).

These events remain a deliberately separate type from the persisted portfolio-lineage
ledger models in :mod:`digiquant.portfolio.models.portfolio_ledger`
(``TargetAdjustmentType`` / ``TargetAdjustment``, #2415): that ledger is append-only
and H9 is its sole writer. H8 applies caps upstream of H9 and returns these events
plus ``SizingResult.requested_pct`` on the sized book; H9 maps ``unit="pct"`` events
onto ``portfolio_ledger_target_adjustments`` keyed to the matching
``RequestedTarget``. ``unit="conviction"`` events stay explanation-only (different
dimension from weight columns).
``TargetAdjustmentType`` was extended (#2417) to carry the same 12 string values
defined here as an additive superset of its original 3 (``cap``/``rounding``/
``carry``), and migration 095 widened the DB CHECK so persisted rows can use the
fine-grained codes. The two *types* stay separate — one governs an in-memory event,
the other a persisted row — so the live sizing pipeline is not coupled to the
ledger model package. H8 remains the sole owner of the final weight — nothing here
changes, reorders, or re-derives a weight; every event field is populated from a
value already computed on the real weight-calculation path.
"""

from __future__ import annotations

from collections import defaultdict
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

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

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

    Membership alone is not enough: a ticker can carry a ``SizingAdjustment`` for
    an unrelated reason while its actual requested->approved delta remains
    unexplained. So this walks each ticker's ``pct``-unit adjustment chain in
    emission order and requires it to *end* at (approximately) ``approved`` — not
    merely that some adjustment mentioning the ticker exists. ``unit="conviction"``
    events describe a conviction-score haircut, not a weight-percentage delta, so
    they never participate in this chain.

    Deliberately **not** checked: that the chain *starts* at (approximately)
    ``requested``. The two call sites in this codebase disagree on what
    ``requested`` even means — ``sizing.SizingResult.requested_pct`` (used by the
    ``test_sizing.py`` lineage battery) is the sizer's own pre-adjustment raw
    weight, so it does line up with ``chain[0].original_pct`` by construction; but
    ``phase7e_risk_sizing._validate_h8_lineage`` passes the **PM's own
    ``target_pct`` ask** as ``requested``, and ``size_portfolio`` derives its raw
    weight from conviction/stance, entirely independent of what the PM asked for
    (see ``_effective_inputs``/``_memo_effective_inputs``). Requiring
    ``chain_start ≈ requested`` is therefore only an accident of the first
    call site and a false positive on the second — a bound PM ask reconciled by a
    real ``SizingAdjustment`` chain would still get flagged as unexplained. Only
    the chain's *end* needs to match the actually-approved value; where that
    chain started is not this function's business.
    """
    by_ticker: dict[str, list[SizingAdjustment]] = defaultdict(list)
    for adjustment in adjustments:
        if adjustment.unit == "pct":
            by_ticker[adjustment.ticker].append(adjustment)

    tickers = set(requested) | set(approved)
    unexplained = []
    for ticker in sorted(tickers):
        requested_pct = requested.get(ticker, 0.0)
        approved_pct = approved.get(ticker, 0.0)
        if abs(approved_pct - requested_pct) <= materiality_pct:
            continue
        chain = by_ticker.get(ticker)
        if not chain:
            unexplained.append(ticker)
            continue
        chain_end = chain[-1].adjusted_pct
        if abs(chain_end - approved_pct) > materiality_pct:
            unexplained.append(ticker)
    if unexplained:
        raise UnexplainedDeltaError(f"unexplained sizing delta(s) for: {unexplained}")


__all__ = [
    "LineageValidationError",
    "SizingAdjustment",
    "SizingAdjustmentType",
    "UnexplainedDeltaError",
    "validate_sizing_lineage",
]
