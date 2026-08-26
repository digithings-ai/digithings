"""WP10.4 — shared-cash Nautilus portfolio replay contracts (#2784).

Strict internal models for isolated shadow/challenger portfolio replay.
These are not public ``BacktestResult`` contracts and must not be used as a
production booking path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from digiquant.olympus.hermes.allocation_hashes import sha256_hex

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
FiniteNonNegDec: TypeAlias = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
FiniteDec: TypeAlias = Annotated[Decimal, Field(allow_inf_nan=False)]
UnitInterval: TypeAlias = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]

# Production / live surfaces must never import this package.
FORBIDDEN_IMPORT_PREFIXES: frozenset[str] = frozenset(
    {
        "digiquant.brokers",
        "digiquant.olympus.hermes.writers",
        "digiquant.olympus.hermes.phases.h9_commit_run",
        "digiquant.olympus.hermes.phases.phase7e_risk_sizing",
        "digiquant.olympus.atlas.supabase_io",
        "digiquant.nautilus_runner",
        "supabase",
        "httpx",
        "requests",
    }
)


class ReplayContractModel(BaseModel):
    """Strict immutable base for portfolio replay contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PortfolioReplayStatus(StrEnum):
    """Typed outcomes for isolated portfolio replay."""

    OK = "ok"
    INCONCLUSIVE = "inconclusive"
    TIMEOUT = "timeout"
    CRASH = "crash"
    ERROR = "error"


class OhlcvBar(ReplayContractModel):
    """One OHLCV bar for a single instrument (UTC)."""

    ts: datetime
    open: FiniteNonNegDec
    high: FiniteNonNegDec
    low: FiniteNonNegDec
    close: FiniteNonNegDec
    volume: FiniteNonNegDec = Decimal("1000000")

    @model_validator(mode="after")
    def _validate_bar(self) -> OhlcvBar:
        if self.ts.tzinfo is None:
            raise ValueError("bar timestamps must be timezone-aware UTC")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.close > self.high or self.close < self.low:
            raise ValueError("close must be within [low, high]")
        if self.open > self.high or self.open < self.low:
            raise ValueError("open must be within [low, high]")
        return self


class InstrumentBarSeries(ReplayContractModel):
    """Synchronized bar series for one ticker."""

    ticker: NonEmptyId
    bars: tuple[OhlcvBar, ...]

    @field_validator("bars", mode="before")
    @classmethod
    def _coerce_bars(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_series(self) -> InstrumentBarSeries:
        if not self.bars:
            raise ValueError(f"{self.ticker}: bars must be non-empty")
        stamps = [b.ts for b in self.bars]
        if stamps != sorted(stamps):
            raise ValueError(f"{self.ticker}: bars must be sorted by timestamp")
        if len(set(stamps)) != len(stamps):
            raise ValueError(f"{self.ticker}: bars must have unique timestamps")
        return self


class TargetWeight(ReplayContractModel):
    """Target portfolio weight for one risky ticker (fraction of NAV)."""

    ticker: NonEmptyId
    weight: UnitInterval


class HoldingQuantity(ReplayContractModel):
    """Current share quantity for one ticker at the decision cutoff."""

    ticker: NonEmptyId
    quantity: FiniteNonNegDec


class ExecutionPolicy(ReplayContractModel):
    """Deterministic execution assumptions for the shared-cash engine."""

    venue: NonEmptyId = "SIM"
    commission_rate: UnitInterval = Decimal("0")
    fill_fraction: UnitInterval = Decimal("1")
    next_bar_execution: bool = True
    random_seed: int = 42


class PortfolioReplayRequest(ReplayContractModel):
    """Validated input for one shared-cash multi-instrument replay arm."""

    schema_version: str = "1.0"
    request_id: NonEmptyId
    starting_cash: FiniteNonNegDec
    series: tuple[InstrumentBarSeries, ...]
    target_weights: tuple[TargetWeight, ...]
    initial_holdings: tuple[HoldingQuantity, ...] = ()
    execution: ExecutionPolicy = ExecutionPolicy()

    @field_validator("series", "target_weights", "initial_holdings", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_request(self) -> PortfolioReplayRequest:
        tickers = [s.ticker for s in self.series]
        if not tickers:
            raise ValueError("series must include at least one instrument")
        if tickers != sorted(tickers):
            raise ValueError("series must be sorted by ticker")
        if len(tickers) != len(set(tickers)):
            raise ValueError("series tickers must be unique")

        stamps = [[b.ts for b in s.bars] for s in self.series]
        first = stamps[0]
        if any(ts != first for ts in stamps[1:]):
            raise ValueError("all instruments must share identical bar timestamps")

        target_tickers = [t.ticker for t in self.target_weights]
        if target_tickers != sorted(target_tickers):
            raise ValueError("target_weights must be sorted by ticker")
        if len(target_tickers) != len(set(target_tickers)):
            raise ValueError("target_weights tickers must be unique")
        unknown_targets = set(target_tickers) - set(tickers)
        if unknown_targets:
            raise ValueError(
                f"target_weights tickers missing from series: {sorted(unknown_targets)}"
            )
        weight_sum = sum((t.weight for t in self.target_weights), Decimal("0"))
        if weight_sum > Decimal("1") + Decimal("1e-12"):
            raise ValueError("sum of target_weights cannot exceed 1")

        holding_tickers = [h.ticker for h in self.initial_holdings]
        if holding_tickers != sorted(holding_tickers):
            raise ValueError("initial_holdings must be sorted by ticker")
        if len(holding_tickers) != len(set(holding_tickers)):
            raise ValueError("initial_holdings tickers must be unique")
        unknown_holdings = set(holding_tickers) - set(tickers)
        if unknown_holdings:
            raise ValueError(
                f"initial_holdings tickers missing from series: {sorted(unknown_holdings)}"
            )
        return self

    def content_hash(self) -> str:
        """Stable digest of the request payload."""
        return sha256_hex(self.model_dump(mode="json"))


class FillRecord(ReplayContractModel):
    """One engine fill observed during replay."""

    ticker: NonEmptyId
    side: NonEmptyId
    quantity: FiniteNonNegDec
    price: FiniteNonNegDec
    commission: FiniteNonNegDec
    ts: datetime
    is_seed: bool = False


class HoldingSnapshot(ReplayContractModel):
    """End-of-replay holding for one ticker."""

    ticker: NonEmptyId
    quantity: FiniteNonNegDec
    last_price: FiniteNonNegDec
    market_value: FiniteNonNegDec


class NavPoint(ReplayContractModel):
    """One synchronized mark-to-market NAV observation on the shared-cash path."""

    ts: datetime
    nav: FiniteNonNegDec

    @model_validator(mode="after")
    def _validate_point(self) -> NavPoint:
        if self.ts.tzinfo is None:
            raise ValueError("nav_path timestamps must be timezone-aware UTC")
        return self


class PortfolioReplayResult(ReplayContractModel):
    """Strict internal portfolio result from one spawned shared-cash engine."""

    schema_version: str = "1.0"
    request_id: NonEmptyId
    request_content_hash: NonEmptyId
    status: PortfolioReplayStatus
    starting_cash: FiniteNonNegDec
    ending_cash: FiniteNonNegDec | None = None
    ending_nav: FiniteNonNegDec | None = None
    total_commission: FiniteNonNegDec | None = None
    rebalance_commission: FiniteNonNegDec | None = None
    holdings: tuple[HoldingSnapshot, ...] = ()
    fills: tuple[FillRecord, ...] = ()
    nav_path: tuple[NavPoint, ...] = ()
    message: str = ""
    result_content_hash: NonEmptyId | None = None

    @field_validator("holdings", "fills", "nav_path", mode="before")
    @classmethod
    def _coerce_tuples(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_result(self) -> PortfolioReplayResult:
        if self.nav_path:
            stamps = [p.ts for p in self.nav_path]
            if stamps != sorted(stamps):
                raise ValueError("nav_path must be sorted by timestamp")
            if len(set(stamps)) != len(stamps):
                raise ValueError("nav_path timestamps must be unique")
        if self.status == PortfolioReplayStatus.OK:
            if self.ending_cash is None or self.ending_nav is None:
                raise ValueError("ok result requires ending_cash and ending_nav")
            if self.total_commission is None or self.rebalance_commission is None:
                raise ValueError("ok result requires commission totals")
            if self.result_content_hash is None:
                raise ValueError("ok result requires result_content_hash")
            expected = portfolio_replay_result_content_hash(self)
            if self.result_content_hash != expected:
                raise ValueError("result_content_hash must match canonical digest")
        return self


def portfolio_replay_result_content_hash(result: PortfolioReplayResult) -> str:
    """Digest of financially material result fields (excludes the hash itself)."""
    payload = {
        "schema_version": result.schema_version,
        "request_id": result.request_id,
        "request_content_hash": result.request_content_hash,
        "status": result.status.value,
        "starting_cash": result.starting_cash,
        "ending_cash": result.ending_cash,
        "ending_nav": result.ending_nav,
        "total_commission": result.total_commission,
        "rebalance_commission": result.rebalance_commission,
        "holdings": [h.model_dump(mode="json") for h in result.holdings],
        "fills": [f.model_dump(mode="json") for f in result.fills],
        "nav_path": [p.model_dump(mode="json") for p in result.nav_path],
        "message": result.message,
    }
    return sha256_hex(payload)


def max_drawdown_from_nav_path(nav_path: tuple[NavPoint, ...]) -> Decimal | None:
    """Peak-to-trough drawdown fraction (≤ 0) from a synchronized NAV path.

    Returns ``None`` when the path is empty (caller reports typed unavailable).
    A single mark yields ``0`` (no trough after a peak).
    """
    if not nav_path:
        return None
    peak = nav_path[0].nav
    worst = Decimal("0")
    for point in nav_path:
        if point.nav > peak:
            peak = point.nav
        if peak > 0:
            dd = (point.nav - peak) / peak
            if dd < worst:
                worst = dd
    return worst



def inconclusive_result(
    *,
    request_id: str,
    request_content_hash: str,
    status: PortfolioReplayStatus,
    message: str,
    starting_cash: Decimal = Decimal("0"),
) -> PortfolioReplayResult:
    """Build a typed non-ok result with no fabricated portfolio numbers."""
    if status == PortfolioReplayStatus.OK:
        raise ValueError("inconclusive_result cannot use status=ok")
    return PortfolioReplayResult(
        request_id=request_id,
        request_content_hash=request_content_hash,
        status=status,
        starting_cash=starting_cash,
        message=message,
    )


__all__ = [
    "FORBIDDEN_IMPORT_PREFIXES",
    "ExecutionPolicy",
    "FillRecord",
    "HoldingQuantity",
    "HoldingSnapshot",
    "InstrumentBarSeries",
    "NavPoint",
    "OhlcvBar",
    "PortfolioReplayRequest",
    "PortfolioReplayResult",
    "PortfolioReplayStatus",
    "ReplayContractModel",
    "TargetWeight",
    "inconclusive_result",
    "max_drawdown_from_nav_path",
    "portfolio_replay_result_content_hash",
]
