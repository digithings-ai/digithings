"""Event-boundary period accounting contracts (#2596, closes OLY-REV-007 / OLY-REV-008).

Exact-date target weights must not be applied across a full return interval. This module
defines the strict Pydantic v2 vocabulary for one shared EOD calculation consumed by NAV,
P&L, and daily attribution:

    opening holdings/cash + fills/costs + closing marks (+ optional corporate actions)
        -> AccountingPeriod (equity, ticker net PnL, cash PnL, contributions, residual, status)

Style mirrors ``hermes.models.portfolio_ledger``: frozen/strict models, closed ``StrEnum``
vocabularies, ``Decimal`` for every money/quantity/price field (``allow_inf_nan=False``),
and UTC-only ``AwareDatetime`` where a clock time is required. Scope is contracts only —
``engine.py`` is the pure calculator; Task 3.2 owns persistence.

Anti-goals: target-snapshot ownership inference, float-only reconciliation, current-book
lookback as realized attribution, public exposure of private accounting tables.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Symbol: TypeAlias = Annotated[str, Field(min_length=1, max_length=20)]
NonNegDecimal: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
PositiveDecimal: TypeAlias = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
SignedDecimal: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
# Total dollars for a whole fill (same unit convention as migration 070).
Fee: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
SignedAmount: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]


class FillSide(StrEnum):
    """Direction of a period fill. Only fills alter realized quantity and cash."""

    BUY = "buy"
    SELL = "sell"


class DividendPolicy(StrEnum):
    """How cash dividends are treated inside the period engine."""

    IGNORE = "ignore"
    TO_CASH = "to_cash"


class SplitPolicy(StrEnum):
    """How splits adjust quantity. Marks must be consistent with the post-split price."""

    IGNORE = "ignore"
    ADJUST_QUANTITY = "adjust_quantity"


class CorporateActionKind(StrEnum):
    DIVIDEND_CASH = "dividend_cash"
    SPLIT = "split"


class PeriodStatus(StrEnum):
    """Lifecycle of a computed (and later persisted) accounting period.

    ``final`` is only legal when marks are complete and fresh and the residual is inside
    the versioned tolerance. Missing/stale marks or an unexplained residual must never
    produce a false final period.
    """

    FINAL = "final"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"
    FAILED = "failed"


class QualityReason(StrEnum):
    """Closed vocabulary of why a period is not (or cannot be) final."""

    MISSING_OPENING_MARK = "missing_opening_mark"
    MISSING_CLOSING_MARK = "missing_closing_mark"
    STALE_CLOSING_MARK = "stale_closing_mark"
    BENCHMARK_BOUNDARY_MISMATCH = "benchmark_boundary_mismatch"
    RESIDUAL_EXCEEDED = "residual_exceeded"
    ZERO_OPENING_EQUITY = "zero_opening_equity"
    NEGATIVE_QUANTITY = "negative_quantity"
    CORPORATE_ACTION_IGNORED = "corporate_action_ignored"
    OPEN_GAP = "open_gap"


class AccountingModel(BaseModel):
    """Frozen/strict base for every accounting contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountingPolicy(AccountingModel):
    """Versioned Decimal tolerances and corporate-action policy for one engine run."""

    policy_version_id: Annotated[str, Field(min_length=1, max_length=100)]
    absolute_tolerance: NonNegDecimal = Decimal("0.01")
    relative_tolerance: NonNegDecimal = Field(default=Decimal("0.000001"), le=1)
    max_mark_age: timedelta = timedelta(hours=36)
    dividend_policy: DividendPolicy = DividendPolicy.TO_CASH
    split_policy: SplitPolicy = SplitPolicy.ADJUST_QUANTITY


class OpeningHolding(AccountingModel):
    """Quantity held at the period open (prior close). Mark is supplied separately."""

    symbol: Symbol
    quantity: NonNegDecimal


class MarkObservation(AccountingModel):
    """A priced mark for one symbol at a known observation clock and business date."""

    symbol: Symbol
    price: PositiveDecimal
    as_of: date
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_utc(self) -> MarkObservation:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() != timedelta(0):
            raise ValueError("observed_at must be timezone-aware UTC")
        return self


class PeriodFill(AccountingModel):
    """One fill inside the period boundary. Fee/slippage are total dollars for the fill."""

    symbol: Symbol
    side: FillSide
    quantity: PositiveDecimal
    price: PositiveDecimal
    fee: Fee = Decimal("0")
    slippage: SignedAmount = Decimal("0")
    executed_at: AwareDatetime
    execution_id: UUID | None = None

    @model_validator(mode="after")
    def validate_utc(self) -> PeriodFill:
        if self.executed_at.tzinfo is None or self.executed_at.utcoffset() != timedelta(0):
            raise ValueError("executed_at must be timezone-aware UTC")
        return self


class CorporateAction(AccountingModel):
    """Optional dividend or split applied inside the period per AccountingPolicy."""

    symbol: Symbol
    kind: CorporateActionKind
    effective_date: date
    # DIVIDEND_CASH: dollars per share. SPLIT: new/old ratio (e.g. 2 for a 2-for-1).
    amount: PositiveDecimal


class BenchmarkBoundary(AccountingModel):
    """Benchmark must share the identical open/close boundary as the portfolio period."""

    symbol: Symbol
    period_date: date
    opening_price: PositiveDecimal
    closing_price: PositiveDecimal


class PeriodAccountingInput(AccountingModel):
    """Authoritative inputs for one event-boundary period computation."""

    period_date: date
    policy: AccountingPolicy
    opening_cash: NonNegDecimal
    opening_holdings: tuple[OpeningHolding, ...] = ()
    opening_marks: tuple[MarkObservation, ...] = ()
    closing_marks: tuple[MarkObservation, ...] = ()
    fills: tuple[PeriodFill, ...] = ()
    corporate_actions: tuple[CorporateAction, ...] = ()
    benchmark: BenchmarkBoundary | None = None

    @model_validator(mode="after")
    def validate_symbols_unique(self) -> PeriodAccountingInput:
        open_syms = [h.symbol for h in self.opening_holdings]
        if len(open_syms) != len(set(open_syms)):
            raise ValueError("opening_holdings symbols must be unique")
        for label, marks in (
            ("opening_marks", self.opening_marks),
            ("closing_marks", self.closing_marks),
        ):
            syms = [m.symbol for m in marks]
            if len(syms) != len(set(syms)):
                raise ValueError(f"{label} symbols must be unique")
        # Benchmark boundary mismatch is an engine quality reason (FAILED), not a
        # construction error — callers may pass a misaligned boundary to assert failure.
        return self


class TickerPeriodResult(AccountingModel):
    """Per-ticker gross/net PnL and contribution for one period."""

    symbol: Symbol
    opening_quantity: NonNegDecimal
    # Signed so an oversell can be reported as FAILED with NEGATIVE_QUANTITY rather
    # than raising at model construction time and hiding the quality reason.
    closing_quantity: SignedDecimal
    opening_mark: PositiveDecimal | None
    closing_mark: PositiveDecimal | None
    gross_pnl: SignedDecimal
    fees: NonNegDecimal
    slippage: SignedAmount
    net_pnl: SignedDecimal
    contribution: SignedDecimal | None
    quality_reasons: tuple[QualityReason, ...] = ()


class ClosingHolding(AccountingModel):
    """EOD holding after fills and corporate actions, marked at the closing price."""

    symbol: Symbol
    quantity: NonNegDecimal
    mark: PositiveDecimal | None
    market_value: SignedDecimal | None


class AccountingPeriod(AccountingModel):
    """Reconciled (or explicitly non-final) event-boundary period result.

    Core identities the engine must satisfy when ``status == final``:

    - ``E1 = E0 + sum(NetPnL_i) + CashPnL``
    - ``E1 = ClosingCash + sum(q_i,1 * P_i,1)``
    - ``sum(Contribution_i) + CashContribution = (E1 - E0) / E0``
    """

    id: UUID
    period_date: date
    policy_version_id: str
    status: PeriodStatus
    quality_reasons: tuple[QualityReason, ...]
    opening_equity: SignedDecimal
    closing_equity: SignedDecimal
    opening_cash: NonNegDecimal
    closing_cash: SignedDecimal
    cash_pnl: SignedDecimal
    cash_contribution: SignedDecimal | None
    gross_pnl_total: SignedDecimal
    net_pnl_total: SignedDecimal
    fees_total: NonNegDecimal
    slippage_total: SignedAmount
    residual: SignedDecimal
    absolute_tolerance: NonNegDecimal
    relative_tolerance: NonNegDecimal
    benchmark_symbol: Symbol | None = None
    benchmark_return: SignedDecimal | None = None
    ticker_results: tuple[TickerPeriodResult, ...]
    closing_holdings: tuple[ClosingHolding, ...]
