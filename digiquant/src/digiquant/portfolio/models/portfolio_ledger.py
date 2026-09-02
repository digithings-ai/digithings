"""Append-only portfolio lineage contracts (#2415, closes Finding OLY-REV-009).

Today, "decision", "target", "order", and "fill" are conflated across snapshots and
documents — one mutable row is asked to mean several different things at different
points in a run, so replaying what actually happened on a given ``run_date`` requires
re-deriving intent from state that was overwritten. This module defines eight private,
append-only Pydantic contracts that separate those concepts into one explicit,
replayable chain:

    PortfolioCommit (daily anchor)
        -> DecisionIntent (H7/H8 symbol-level decision: add/trim/exit/no_op/reject)
        -> RequestedTarget (raw pre-adjustment weight/quantity)
        -> TargetAdjustment (cap/rounding/carry applied to a RequestedTarget)
        -> ApprovedTarget (final approved weight/quantity, supersedable same-date)
        -> OrderIntent (paper order derived from an ApprovedTarget)
        -> PaperExecution (immutable fill, idempotent on retry)
        -> HoldingLot (position lot opened/closed by a PaperExecution)

Scope — contracts and schema only. This module does not change H7/H8/H9 ownership and
does not touch any live-trading or broker path. ``hermes/writers/commit_io.py`` (H9)
remains the sole authoritative writer of the ``positions`` **book** — the portfolio's
official state. That is a narrower claim than "the only writer of these tables": since
#2420 (Task 2.4) ``hermes/writers/execution_io.py`` appends ``PaperExecution`` and
``HoldingLot`` rows for the day's fills, which records what an order *did* rather than
what the portfolio *is*, and it neither writes nor rewrites the book.

Since #2418 these models are **no longer dark**: ``hermes/writers/ledger_io.py`` appends
the first five links of the chain (including ``TargetAdjustment`` since #2768) from
every H9 run that actually commits, unless the ``OLYMPUS_PORTFOLIO_LEDGER`` kill switch
is off (see ``digiquant/ARCHITECTURE.md``), and ``execution_io.py`` appends the last two.
A run that short-circuits as ``status="noop"`` returns before the append — "no rows" on
that path is intentional, not a missing producer.

They are also **read back** now, which they were not before #2420:
``digiquant/scripts/research/execute_at_open.py`` walks the chain forward from
``PortfolioCommit`` through ``OrderIntent``, ``ApprovedTarget``, ``PaperExecution`` and
``HoldingLot``, and projects it into the public ``position_events`` table — naming each
event from the lots it can see rather than from a diff of two snapshots, which is the
whole point of having a lineage. A contract with a producer and no consumer is a schema;
this one is now a data path, so a change to a field below has a reader to break.

Anti-goals carried over from the issue: no broker/live-trading paths, no mutable fills,
no second H9 writer. Every quantity/weight/price field below is ``Decimal`` (never
``float``) and, where a value could be economically meaningful or absent, is modeled as
``Decimal | None`` rather than defaulting to zero — this is a deliberate break from
``commit_io.py``'s legacy ``_coerce_float`` convention (silent 0.0 on failure), which
stays untouched but is exactly the anti-pattern this module exists to avoid. "No fill
happened" is the absence of a ``PaperExecution`` row, never a zero-valued one.

Style mirrors ``digillm/src/digillm/telemetry.py``: one closed ``StrEnum`` per
vocabulary, a frozen/strict base (``extra="forbid"``, ``frozen=True``), UTC-only
``AwareDatetime`` fields, and a business-rule ``model_validator(mode="after")`` on each
concrete record — deliberately not the looser, mutable, ``Literal``-union style of
``hermes/models/deliberation.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from digiquant.dashboard.tenancy import house_workspace_id

# Fixed namespace for PaperExecution's deterministic idempotency key. Any stable literal
# UUID works here — it only needs to never change between deploys.
_PAPER_EXECUTION_ID_NAMESPACE = UUID("f6a12e2e-8b1a-5c9d-9e4a-2b6f7a8c9d0e")

Symbol: TypeAlias = Annotated[str, Field(min_length=1, max_length=20)]
Weight: TypeAlias = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]
Quantity: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
PositiveQuantity: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
PositivePrice: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
# Money, in total dollars for a whole fill (migration 070). Deliberately NOT reusing
# ``Quantity``/``Weight`` above: those carry the same numeric constraint but mean shares
# and portfolio fraction, and a dollar amount typed as a share count is the kind of unit
# confusion that reads as correct forever. ``Fee`` is a cost so it cannot be negative;
# ``SignedAmount`` must admit both signs because favourable slippage is real and clamping
# it would silently discard better-than-mark execution.
Fee: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
SignedAmount: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]


class DecisionAction(StrEnum):
    """Closed vocabulary of H7/H8 symbol-level decisions."""

    ADD = "add"
    TRIM = "trim"
    EXIT = "exit"
    NO_OP = "no_op"
    REJECT = "reject"


class DecisionReason(StrEnum):
    """Closed reason codes. Every DecisionIntent carries one — never a bare null."""

    NEW_CONVICTION = "new_conviction"
    CONVICTION_REDUCED = "conviction_reduced"
    THESIS_INVALIDATED = "thesis_invalidated"
    NO_SIGNAL_CHANGE = "no_signal_change"
    RISK_CAP_BREACH = "risk_cap_breach"
    LOW_CONVICTION = "low_conviction"
    DATA_UNAVAILABLE = "data_unavailable"


# Which reasons are valid for which action — keeps "reject"/"no_op" from ever being
# paired with a reason that only makes sense for an "add"/"trim"/"exit", closing off
# a second axis of null-adjacent ambiguity (a technically-non-null but nonsensical
# reason code).
_ACTION_REASONS: dict[DecisionAction, frozenset[DecisionReason]] = {
    DecisionAction.ADD: frozenset({DecisionReason.NEW_CONVICTION}),
    DecisionAction.TRIM: frozenset({DecisionReason.CONVICTION_REDUCED}),
    DecisionAction.EXIT: frozenset({DecisionReason.THESIS_INVALIDATED}),
    DecisionAction.NO_OP: frozenset(
        {DecisionReason.NO_SIGNAL_CHANGE, DecisionReason.DATA_UNAVAILABLE}
    ),
    DecisionAction.REJECT: frozenset(
        {
            DecisionReason.RISK_CAP_BREACH,
            DecisionReason.LOW_CONVICTION,
            DecisionReason.DATA_UNAVAILABLE,
        }
    ),
}


class TargetAdjustmentType(StrEnum):
    """Closed vocabulary of adjustments applied to a RequestedTarget.

    ``CAP``, ``ROUNDING``, and ``CARRY`` are the original (#2415) coarse-grained
    values and remain for backward compatibility with existing persisted rows
    and tests. The remaining members are the 12 canonical H8 adjustment reasons
    defined by ``hermes.sizing_events.SizingAdjustmentType`` (#2417), added here
    as an additive superset so a persisted ``TargetAdjustment`` row can carry the
    same fine-grained reason an in-memory ``SizingAdjustment`` event carries,
    without a breaking rename of the coarse legacy values.

    Migration 095 widened the ``adjustment_type`` CHECK on
    ``portfolio_ledger_target_adjustments`` to this full vocabulary; H9
    (``ledger_io.append_commit_chain``, #2768) is the producer.

    This enum and ``SizingAdjustmentType`` are deliberately kept as two separate
    types rather than unified into one: this one governs a persisted,
    append-only ledger row, while ``SizingAdjustmentType`` governs the in-memory
    explanation object returned alongside H8's sized book.
    """

    CAP = "cap"
    ROUNDING = "rounding"
    CARRY = "carry"

    # The 12 canonical H8 adjustment reasons (#2417), mirrored from
    # ``hermes.sizing_events.SizingAdjustmentType``. CHECK-constrained by
    # migration 095 (069 originally allowed only cap/rounding/carry).
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


class OrderIntentStatus(StrEnum):
    """Lifecycle of a paper order intent.

    Deliberately excludes a ``superseded`` value: whether a row was later superseded is
    a fact about a *different*, later-inserted row (see ``OrderIntent.supersedes_id``),
    never something the superseded row's own ``status`` could carry at insert time under
    an append-only, no-UPDATE table. ``pending``/``executed``/``rejected`` are each fully
    knowable at the moment this row is written, which is exactly why they remain here.
    """

    PENDING = "pending"
    EXECUTED = "executed"
    REJECTED = "rejected"


class OrderRejectionReason(StrEnum):
    """Closed reason codes for a rejected OrderIntent."""

    RISK_LIMIT = "risk_limit"
    INSUFFICIENT_CASH = "insufficient_cash"
    STALE_TARGET = "stale_target"
    MARKET_CLOSED = "market_closed"
    DATA_UNAVAILABLE = "data_unavailable"


class HoldingLotStatus(StrEnum):
    """Lifecycle of a position lot."""

    OPEN = "open"
    CLOSED = "closed"


def _reject_non_utc(*values: AwareDatetime | None) -> None:
    """Raise unless every non-null timestamp is UTC (offset exactly +00:00)."""
    for value in values:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("portfolio ledger timestamps must be UTC")


def paper_execution_id(order_intent_id: UUID, executed_date: date) -> UUID:
    """Deterministic idempotency key for a paper execution.

    A writer derives ``PaperExecution.id`` from this rather than randomizing it, so an
    exact same-date retry of the same order intent computes the identical primary key
    and collides against the migration's ``UNIQUE (order_intent_id, executed_date)``
    constraint instead of inserting a second, divergent fill row.
    """
    return uuid5(_PAPER_EXECUTION_ID_NAMESPACE, f"{order_intent_id}:{executed_date.isoformat()}")


class PortfolioLedgerModel(BaseModel):
    """Strict, immutable base for every portfolio lineage contract.

    Mirrors ``digillm.telemetry.TelemetryModel`` exactly: unknown fields are rejected
    rather than silently dropped, and instances are frozen so a fill or an executed
    order can never be rewritten in place — a correction is always a new row with its
    own supersession link, never a mutation.

    T0 (#5-T0): ``workspace_id`` is NOT NULL on every portfolio-ledger table as of
    migration 097. The house pipeline is the only producer today, so the field defaults
    to :func:`house_workspace_id`; overlay / multi-workspace writers (T4) will pass an
    explicit id. Without this field, read-back via ``model_validate`` rejects stamped
    rows (``extra="forbid"``) and degrades H9 cost-liquidity evidence.

    Known limitation (accepted, LOW severity): Pydantic v2's ``model_copy(update=...)``
    bypasses both ``frozen=True`` and every ``model_validator`` — it is a shallow
    field-copy, not a re-validated construction — on *any* frozen Pydantic model, not a
    gap specific to this one. Nothing in this module calls ``model_copy``; a caller
    who reaches for it directly gets an object that looks like a valid record but was
    never checked against this module's business rules (e.g. the UTC/XOR/rejection
    invariants below). The only sanctioned way to "change" a row is the pattern this
    schema already enforces at the database layer: construct a brand-new instance
    (going through ``__init__`` and full validation) whose ``supersedes_id`` points at
    the prior row. See ``TestPortfolioLedgerModel::test_model_copy_bypasses_freeze_and_validation``
    in ``tests/dq/portfolio/test_portfolio_ledger.py`` for a regression test pinning this
    as expected (if unfortunate) upstream behavior rather than a silently-forgotten bug.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID = Field(default_factory=house_workspace_id)


class TimedPortfolioLedgerRecord(PortfolioLedgerModel):
    """Shared UTC validation for the ``effective_at``/``recorded_at`` timestamp pair.

    ``effective_at`` is the producer-supplied business time the row describes (when the
    decision/target/order was actually made); ``recorded_at`` is the ledger's own write
    clock. They are deliberately separate columns, mirroring migration 067's
    ``recorded_at timestamptz NOT NULL DEFAULT now()`` convention.
    """

    effective_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_utc(self) -> TimedPortfolioLedgerRecord:
        _reject_non_utc(self.effective_at, self.recorded_at)
        return self


class PortfolioCommit(TimedPortfolioLedgerRecord):
    """Daily lineage-chain anchor/root for one ``run_date``.

    Not a duplicate of H9's commit manifest (``writers/commit_io.py``) — this is a
    read-side lineage anchor that every other record in the chain points back to
    (directly or transitively), not a booking/write-path artifact.

    Carries no ``status`` field: a same-date recommit is always a new row whose
    ``supersedes_id`` points back at the prior commit it replaces, mirroring
    ``ApprovedTarget.supersedes_id`` exactly. There is no "superseded" state to track on
    this row itself — the ledger never learns after the fact that a commit was
    superseded, since that would require either an UPDATE (rejected by the append-only
    trigger) or a second row re-using the same id (rejected by the PRIMARY KEY).
    Currency is purely structural: a commit is current for its ``run_date`` iff no later
    commit's ``supersedes_id`` points at it.
    """

    id: UUID
    run_date: date
    policy_version_id: Annotated[str, Field(min_length=1, max_length=100)]
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> PortfolioCommit:
        if self.supersedes_id == self.id:
            raise ValueError("a commit cannot supersede itself")
        return self


class DecisionIntent(TimedPortfolioLedgerRecord):
    """One symbol-level decision produced by H7/H8 deliberation for a ``run_date``."""

    id: UUID
    portfolio_commit_id: UUID
    run_date: date
    symbol: Symbol
    action: DecisionAction
    reason: DecisionReason

    @model_validator(mode="after")
    def validate_lifecycle(self) -> DecisionIntent:
        if self.reason not in _ACTION_REASONS[self.action]:
            raise ValueError(f"reason {self.reason!r} is not valid for action {self.action!r}")
        return self


class RequestedTarget(TimedPortfolioLedgerRecord):
    """Raw requested weight/quantity following a DecisionIntent, pre-cap/rounding/carry.

    Exactly one of ``requested_weight``/``requested_quantity`` is set (XOR, not OR): a
    conceptually unknown value is ``None``, never a coerced ``0`` — an explicit ``0``
    (e.g. a full-exit target) is a distinct, legitimate value from "unknown" — but a row
    carrying both would leave every downstream ``TargetAdjustment`` against it
    dimensionally ambiguous, since an adjustment records a bare ``original_value``/
    ``adjusted_value`` with no unit column of its own and infers weight-vs-quantity from
    whichever column is populated here. Mirrors the migration's
    ``chk_portfolio_ledger_requested_targets_presence`` exactly.
    """

    id: UUID
    decision_intent_id: UUID
    run_date: date
    symbol: Symbol
    requested_weight: Weight | None = None
    requested_quantity: Quantity | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> RequestedTarget:
        if (self.requested_weight is None) == (self.requested_quantity is None):
            raise ValueError(
                "a requested target must carry exactly one of requested_weight/"
                "requested_quantity, never both or neither"
            )
        return self


# Adjustment types that can only ever reduce a value — a cap, dedup, or breaker
# by definition trims toward a limit, never expands past it. ``CAP`` is the
# original (#2415) value; the other six are #2417 additions that share the
# same reducing-only invariant but were missing from ``validate_lifecycle``
# until this fix (#2417 CodeRabbit review on #2434). ``CORRELATION_DEDUP``
# trims an overlapping position's size down, same as a cap — an increasing
# correlation-dedup record is exactly as invalid as an increasing cap one.
# ``GRID_ROUNDING`` always rounds down to the sizing grid (never to nearest —
# see ``sizing._round_to_grid``'s own reduce-only invariant), and ``FLAT_EXIT``
# always drives a held position to exactly 0 (an H7-flat exit or a PM-exit —
# see ARCHITECTURE.md's H8 adjustment-event taxonomy table), so both belong
# here alongside the caps/dedup/breaker set. ``VOLATILITY_SCALE`` and
# ``FINAL_GROSS_SCALE`` are deliberately absent: both can scale a book UP as
# well as down (vol-target up-scale toward an under-filled budget, #943; a
# binding gross/pos/sector candidate scale that exceeds 1), so neither is
# reduce-only.
_REDUCING_ADJUSTMENT_TYPES: frozenset[TargetAdjustmentType] = frozenset(
    {
        TargetAdjustmentType.CAP,
        TargetAdjustmentType.SINGLE_NAME_CAP,
        TargetAdjustmentType.SECTOR_CAP,
        TargetAdjustmentType.CORRELATION_DEDUP,
        TargetAdjustmentType.DRAWDOWN_BREAKER,
        TargetAdjustmentType.GRID_ROUNDING,
        TargetAdjustmentType.FLAT_EXIT,
    }
)


class TargetAdjustment(TimedPortfolioLedgerRecord):
    """A cap, rounding, or carry adjustment applied to a RequestedTarget."""

    id: UUID
    requested_target_id: UUID
    run_date: date
    symbol: Symbol
    adjustment_type: TargetAdjustmentType
    original_value: Quantity
    adjusted_value: Quantity
    reason: Annotated[str, Field(min_length=1, max_length=200)]

    @model_validator(mode="after")
    def validate_lifecycle(self) -> TargetAdjustment:
        if (
            self.adjustment_type in _REDUCING_ADJUSTMENT_TYPES
            and self.adjusted_value > self.original_value
        ):
            raise ValueError(
                f"a {self.adjustment_type.value} adjustment can only reduce the original value"
            )
        return self


class ApprovedTarget(TimedPortfolioLedgerRecord):
    """Final approved weight/quantity after adjustments.

    ``supersedes_id`` is the anchor for same-date target changes: a new ApprovedTarget
    for the same symbol+run_date points back to the prior one it supersedes, so a
    changed same-date target is always a new row with an explicit lineage link, never a
    mutation of the old one.
    """

    id: UUID
    requested_target_id: UUID
    run_date: date
    symbol: Symbol
    approved_weight: Weight | None = None
    approved_quantity: Quantity | None = None
    supersedes_id: UUID | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> ApprovedTarget:
        if self.approved_weight is None and self.approved_quantity is None:
            raise ValueError(
                "an approved target must carry an explicit weight or quantity, never both absent"
            )
        if self.supersedes_id == self.id:
            raise ValueError("an approved target cannot supersede itself")
        return self


class OrderIntent(TimedPortfolioLedgerRecord):
    """A paper order intent derived from an ApprovedTarget.

    Once ``status`` is ``executed`` the row is terminal: no other field exists that
    would let a later write "rewrite" it (also enforced by the migration's mutation
    trigger). A ``rejected`` row always carries ``rejection_reason``.

    ``supersedes_id`` is orthogonal to ``status``, and backward-linking like
    ``ApprovedTarget.supersedes_id``: a changed same-date order is always a new row
    pointing back at the prior one it replaces, never a mutation of that prior row (and
    never a forward link recorded on the row being replaced — that would require either
    an UPDATE, rejected by the append-only trigger, or a second row re-using the same id,
    rejected by the PRIMARY KEY). A fresh replacement order is free to independently
    reach its own eventual ``pending``/``executed``/``rejected`` status regardless of
    whether it happens to supersede an earlier row.
    """

    id: UUID
    approved_target_id: UUID
    run_date: date
    symbol: Symbol
    quantity: PositiveQuantity
    status: OrderIntentStatus
    supersedes_id: UUID | None = None
    rejection_reason: OrderRejectionReason | None = None

    @model_validator(mode="after")
    def validate_lifecycle(self) -> OrderIntent:
        if self.status is OrderIntentStatus.REJECTED:
            if self.rejection_reason is None:
                raise ValueError("a rejected order intent requires rejection_reason")
        elif self.rejection_reason is not None:
            raise ValueError("only a rejected order intent may carry rejection_reason")
        if self.supersedes_id == self.id:
            raise ValueError("an order intent cannot supersede itself")
        return self


class PaperExecution(PortfolioLedgerModel):
    """Immutable fill record for an OrderIntent.

    ``quantity`` and ``price`` are required, strictly-positive Decimal fields — "no
    fill happened" is the absence of a row, never a zero-valued one. ``id`` must equal
    ``paper_execution_id(order_intent_id, executed_date)``, so an exact same-date retry
    with the same inputs is idempotent: it computes the identical id/field values
    rather than a fresh, divergent row.

    ``fee`` and ``slippage`` (migration 070) are **total dollars for the whole fill**,
    not per-share and not basis points, so ``fee + slippage`` is directly the fill's cash
    cost. ``slippage`` is signed: ``(effective fill price - declared mark) * quantity``,
    positive when the fill was worse than the mark. Both are ``None``-able only because
    the append-only trigger makes rows written before migration 070 impossible to
    backfill — ``None`` means "predates cost tracking". A writer that has a cost model,
    including the degenerate one where a paper fill executes exactly at the declared open,
    always sends an explicit value: ``Decimal(0)`` there is a *measured* zero, not a
    missing one.
    """

    id: UUID
    order_intent_id: UUID
    executed_date: date
    symbol: Symbol
    quantity: PositiveQuantity
    price: PositivePrice
    fee: Fee | None = None
    slippage: SignedAmount | None = None
    executed_at: AwareDatetime
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self) -> PaperExecution:
        _reject_non_utc(self.executed_at, self.recorded_at)
        expected_id = paper_execution_id(self.order_intent_id, self.executed_date)
        if self.id != expected_id:
            raise ValueError(
                "PaperExecution.id must be paper_execution_id(order_intent_id, "
                "executed_date) so an exact same-date retry is idempotent, not a "
                "freshly randomized id"
            )
        return self


class HoldingLot(PortfolioLedgerModel):
    """The position lot opened (and eventually closed) by a PaperExecution.

    Mirrors ``digillm.telemetry.TimedTelemetryModel``'s ``finished_at`` pattern:
    ``closed_at``/``closed_by_execution_id`` are nullable, but their nullability is
    tied strictly to ``status`` — an open lot can never carry either, and a closed lot
    must carry both.
    """

    id: UUID
    opened_by_execution_id: UUID
    closed_by_execution_id: UUID | None = None
    run_date: date
    symbol: Symbol
    quantity: PositiveQuantity
    open_price: PositivePrice
    status: HoldingLotStatus
    opened_at: AwareDatetime
    closed_at: AwareDatetime | None = None
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_lifecycle(self) -> HoldingLot:
        _reject_non_utc(self.opened_at, self.closed_at, self.recorded_at)
        if self.status is HoldingLotStatus.OPEN:
            if self.closed_at is not None or self.closed_by_execution_id is not None:
                raise ValueError(
                    "an open holding lot cannot carry closed_at or closed_by_execution_id"
                )
        else:
            if self.closed_at is None or self.closed_by_execution_id is None:
                raise ValueError(
                    "a closed holding lot requires both closed_at and closed_by_execution_id"
                )
            if self.closed_at < self.opened_at:
                raise ValueError("closed_at must not precede opened_at")
        if (
            self.closed_by_execution_id is not None
            and self.closed_by_execution_id == self.opened_by_execution_id
        ):
            raise ValueError("a holding lot cannot be closed by the execution that opened it")
        return self


PortfolioLedgerRecord: TypeAlias = (
    PortfolioCommit
    | DecisionIntent
    | RequestedTarget
    | TargetAdjustment
    | ApprovedTarget
    | OrderIntent
    | PaperExecution
    | HoldingLot
)


__all__ = [
    "ApprovedTarget",
    "DecisionAction",
    "DecisionIntent",
    "DecisionReason",
    "HoldingLot",
    "HoldingLotStatus",
    "OrderIntent",
    "OrderIntentStatus",
    "OrderRejectionReason",
    "PaperExecution",
    "PortfolioCommit",
    "PortfolioLedgerModel",
    "PortfolioLedgerRecord",
    "RequestedTarget",
    "TargetAdjustment",
    "TargetAdjustmentType",
    "TimedPortfolioLedgerRecord",
    "paper_execution_id",
]
