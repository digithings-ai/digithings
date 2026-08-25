"""H8 allocation input contracts (#2727 / WP8.2).

Defines :class:`AllocationInputBundle` and supporting frozen models that join
Phase 1 registry hashes, H7 mandate references, prior book weights, and control
settings into one validated identity. Assembly at H8 entry is Task 8.3 — this
module is contracts + hashes only; incumbent sizing behavior is unchanged.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from digiquant.olympus.hermes.allocation_hashes import (
    allocation_bundle_content_hash,
    allocation_bundle_hash_payload,
    prior_weights_from_entries,
    weights_fingerprint,
)

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
Probability: TypeAlias = Annotated[
    Decimal, Field(ge=0, le=1, allow_inf_nan=False, max_digits=16, decimal_places=8)
]
ReturnFraction: TypeAlias = Annotated[
    Decimal, Field(allow_inf_nan=False, max_digits=16, decimal_places=8)
]
NonNegativeDecimal: TypeAlias = Annotated[
    Decimal, Field(ge=0, allow_inf_nan=False, max_digits=20, decimal_places=8)
]
WeightPct: TypeAlias = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
PositiveSessions: TypeAlias = Annotated[int, Field(gt=0)]


class AllocationContractModel(BaseModel):
    """Strict immutable base for allocation input contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AllocationCadence(StrEnum):
    """Operator cadence pinned on the bundle."""

    DAILY = "daily"


class AssetInputStatus(StrEnum):
    """Whether one asset's calibrated slice is usable at H8 entry."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    EXCLUDED = "excluded"


class AllocationRunContext(AllocationContractModel):
    """Run/cutoff/cadence identity for one H8 sizing pass."""

    run_id: NonEmptyId
    session_date: date
    cutoff_at: AwareDatetime
    cadence: AllocationCadence = AllocationCadence.DAILY
    profile_config_version_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_cutoff_utc(self) -> AllocationRunContext:
        if self.cutoff_at.utcoffset() != timedelta(0):
            raise ValueError("cutoff_at must be timezone-aware UTC")
        return self


class MandateReference(AllocationContractModel):
    """H7 mandate slice for one ticker — direction and rank, no weights."""

    ticker: NonEmptyId
    direction: Literal["long", "flat"]
    conviction_rank: int = Field(ge=1)
    effective_forecast_id: UUID | None = None
    forecast_reference_hash: NonEmptyId | None = None
    degradation_reason: NonEmptyId | None = None


class CalibratedReturnSlice(AllocationContractModel):
    """Calibrated expected return and uncertainty for one asset."""

    ticker: NonEmptyId
    horizon_sessions: PositiveSessions
    expected_gross_return: ReturnFraction | None = None
    forecast_error_std: NonNegativeDecimal | None = None
    reliability_weight: Probability
    calibrated_forecast_content_hash: NonEmptyId | None = None
    status: AssetInputStatus
    unavailable_reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_calibrated_slice(self) -> CalibratedReturnSlice:
        if self.status is AssetInputStatus.AVAILABLE:
            if self.unavailable_reason is not None:
                raise ValueError("available calibrated slice cannot carry unavailable_reason")
            if self.calibrated_forecast_content_hash is None:
                raise ValueError("available calibrated slice requires calibrated_forecast_content_hash")
            if self.expected_gross_return is None or self.forecast_error_std is None:
                raise ValueError(
                    "available calibrated slice requires expected_gross_return and forecast_error_std"
                )
            if self.forecast_error_std == Decimal("0"):
                raise ValueError("forecast_error_std must be positive when available")
        else:
            if self.unavailable_reason is None or not self.unavailable_reason.strip():
                raise ValueError("non-available calibrated slice requires unavailable_reason")
            if self.calibrated_forecast_content_hash is not None:
                raise ValueError("non-available calibrated slice cannot carry calibrated_forecast_content_hash")
            if any(
                value is not None
                for value in (self.expected_gross_return, self.forecast_error_std)
            ):
                raise ValueError("non-available calibrated slice cannot carry return metrics")
        return self


class PriorWeightEntry(AllocationContractModel):
    """One prior risky weight before H8 sizing."""

    ticker: NonEmptyId
    weight_pct: WeightPct


class PriorBookSnapshot(AllocationContractModel):
    """Prior marked book weights consumed by H8."""

    entries: tuple[PriorWeightEntry, ...]
    cash_weight_pct: WeightPct

    @field_validator("entries", mode="before")
    @classmethod
    def _coerce_entries(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_prior_book(self) -> PriorBookSnapshot:
        tickers = [entry.ticker for entry in self.entries]
        if len(tickers) != len(set(tickers)):
            raise ValueError("prior book entries must be unique by ticker")
        if tickers != sorted(tickers):
            raise ValueError("prior book entries must be sorted by ticker")
        gross = sum(entry.weight_pct for entry in self.entries) + self.cash_weight_pct
        if gross > 100.0 + 1e-6:
            raise ValueError("prior book gross exposure cannot exceed 100%")
        return self

    def risky_weights(self) -> dict[str, float]:
        return {entry.ticker: entry.weight_pct for entry in self.entries}


class ControlSettingsFingerprint(AllocationContractModel):
    """Resolved incumbent control settings identity."""

    risk_policy_content_hash: NonEmptyId
    risk_policy_id: UUID


class CovarianceBinding(AllocationContractModel):
    """Exact covariance snapshot version aligned to canonical asset order."""

    snapshot_id: UUID
    content_hash: NonEmptyId
    tickers: tuple[NonEmptyId, ...]

    @field_validator("tickers", mode="before")
    @classmethod
    def _coerce_tickers(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class CostLiquidityBinding(AllocationContractModel):
    """Per-asset observational cost estimate hashes."""

    entries: tuple[tuple[NonEmptyId, NonEmptyId], ...]

    @field_validator("entries", mode="before")
    @classmethod
    def _coerce_entries(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(tuple(pair) for pair in value)
        return value

    @model_validator(mode="after")
    def _validate_cost_entries(self) -> CostLiquidityBinding:
        tickers = [ticker for ticker, _ in self.entries]
        if tickers != sorted(tickers):
            raise ValueError("cost_liquidity entries must be sorted by ticker")
        if len(tickers) != len(set(tickers)):
            raise ValueError("cost_liquidity entries must be unique by ticker")
        return self


class AllocationSourceHashes(AllocationContractModel):
    """Pinned upstream artifact digests for replay and H9 validation."""

    h7_memo_hash: NonEmptyId
    risk_policy_hash: NonEmptyId
    prior_weights_fingerprint: NonEmptyId
    covariance_hash: NonEmptyId | None = None
    calibrated_hashes: tuple[tuple[NonEmptyId, NonEmptyId], ...] = Field(default_factory=tuple)
    cost_hashes: tuple[tuple[NonEmptyId, NonEmptyId], ...] = Field(default_factory=tuple)

    @field_validator("calibrated_hashes", "cost_hashes", mode="before")
    @classmethod
    def _coerce_pair_tuple(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(tuple(pair) for pair in value)
        return value

    @model_validator(mode="after")
    def _validate_hash_pairs(self) -> AllocationSourceHashes:
        for label, pairs in (
            ("calibrated_hashes", self.calibrated_hashes),
            ("cost_hashes", self.cost_hashes),
        ):
            tickers = [ticker for ticker, _ in pairs]
            if tickers != sorted(tickers):
                raise ValueError(f"{label} must be sorted by ticker")
            if len(tickers) != len(set(tickers)):
                raise ValueError(f"{label} must be unique by ticker")
        return self


class AllocationInputBundle(AllocationContractModel):
    """Canonical validated identity for one H8 sizing pass."""

    schema_version: str = "1.0"
    run: AllocationRunContext
    canonical_asset_order: tuple[NonEmptyId, ...]
    mandates: tuple[MandateReference, ...]
    calibrated_returns: tuple[CalibratedReturnSlice, ...]
    prior_book: PriorBookSnapshot
    control_settings: ControlSettingsFingerprint
    covariance: CovarianceBinding | None = None
    cost_liquidity: CostLiquidityBinding | None = None
    source_hashes: AllocationSourceHashes
    bundle_content_hash: NonEmptyId

    @field_validator(
        "canonical_asset_order",
        "mandates",
        "calibrated_returns",
        mode="before",
    )
    @classmethod
    def _coerce_tuple_fields(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @model_validator(mode="after")
    def _validate_bundle(self) -> AllocationInputBundle:
        order = list(self.canonical_asset_order)
        if order != sorted(order):
            raise ValueError("canonical_asset_order must be sorted")
        if len(order) != len(set(order)):
            raise ValueError("canonical_asset_order must be unique")

        mandate_tickers = [item.ticker for item in self.mandates]
        calibrated_tickers = [item.ticker for item in self.calibrated_returns]
        if mandate_tickers != order:
            raise ValueError("mandates must align exactly with canonical_asset_order")
        if calibrated_tickers != order:
            raise ValueError("calibrated_returns must align exactly with canonical_asset_order")

        horizons = {item.horizon_sessions for item in self.calibrated_returns}
        if len(horizons) > 1:
            raise ValueError("all calibrated_returns must share one horizon_sessions")

        if self.covariance is not None:
            if list(self.covariance.tickers) != order:
                raise ValueError("covariance tickers must match canonical_asset_order")

        if self.cost_liquidity is not None:
            cost_tickers = [ticker for ticker, _ in self.cost_liquidity.entries]
            if not set(cost_tickers).issubset(set(order)):
                raise ValueError("cost_liquidity tickers must be subset of canonical_asset_order")

        expected_prior_fp = weights_fingerprint(self.prior_book.risky_weights())
        if self.source_hashes.prior_weights_fingerprint != expected_prior_fp:
            raise ValueError("source_hashes.prior_weights_fingerprint must match prior book")

        calibrated_pairs = tuple(
            (item.ticker, item.calibrated_forecast_content_hash or "")
            for item in self.calibrated_returns
            if item.calibrated_forecast_content_hash is not None
        )
        if self.source_hashes.calibrated_hashes != calibrated_pairs:
            raise ValueError("source_hashes.calibrated_hashes must match calibrated_returns")

        if self.cost_liquidity is not None:
            if self.source_hashes.cost_hashes != self.cost_liquidity.entries:
                raise ValueError("source_hashes.cost_hashes must match cost_liquidity entries")

        if self.covariance is not None:
            if self.source_hashes.covariance_hash != self.covariance.content_hash:
                raise ValueError("source_hashes.covariance_hash must match covariance binding")
        elif self.source_hashes.covariance_hash is not None:
            raise ValueError("covariance_hash requires covariance binding")

        if self.source_hashes.risk_policy_hash != self.control_settings.risk_policy_content_hash:
            raise ValueError("source_hashes.risk_policy_hash must match control_settings")

        expected_hash = allocation_bundle_content_hash(payload=self._hash_payload())
        if self.bundle_content_hash != expected_hash:
            raise ValueError("bundle_content_hash must match canonical bundle digest")
        return self

    def _hash_payload(self) -> dict[str, object]:
        run_payload = {
            "run_id": self.run.run_id,
            "session_date": self.run.session_date.isoformat(),
            "cutoff_at": self.run.cutoff_at.isoformat(),
            "cadence": self.run.cadence.value,
            "profile_config_version_id": (
                None if self.run.profile_config_version_id is None
                else str(self.run.profile_config_version_id)
            ),
        }
        mandates_payload = tuple(
            {
                "ticker": item.ticker,
                "direction": item.direction,
                "conviction_rank": item.conviction_rank,
                "effective_forecast_id": (
                    None if item.effective_forecast_id is None
                    else str(item.effective_forecast_id)
                ),
                "forecast_reference_hash": item.forecast_reference_hash,
                "degradation_reason": item.degradation_reason,
            }
            for item in self.mandates
        )
        calibrated_payload = tuple(
            {
                "ticker": item.ticker,
                "horizon_sessions": item.horizon_sessions,
                "expected_gross_return": (
                    None if item.expected_gross_return is None else str(item.expected_gross_return)
                ),
                "forecast_error_std": (
                    None if item.forecast_error_std is None else str(item.forecast_error_std)
                ),
                "reliability_weight": str(item.reliability_weight),
                "calibrated_forecast_content_hash": item.calibrated_forecast_content_hash,
                "status": item.status.value,
                "unavailable_reason": item.unavailable_reason,
            }
            for item in self.calibrated_returns
        )
        prior_payload = {
            "entries": [
                {"ticker": entry.ticker, "weight_pct": entry.weight_pct}
                for entry in self.prior_book.entries
            ],
            "cash_weight_pct": self.prior_book.cash_weight_pct,
        }
        control_payload = {
            "risk_policy_content_hash": self.control_settings.risk_policy_content_hash,
            "risk_policy_id": str(self.control_settings.risk_policy_id),
        }
        covariance_payload = (
            None
            if self.covariance is None
            else {
                "snapshot_id": str(self.covariance.snapshot_id),
                "content_hash": self.covariance.content_hash,
                "tickers": sorted(self.covariance.tickers),
            }
        )
        cost_payload = (
            None
            if self.cost_liquidity is None
            else {"entries": sorted([list(pair) for pair in self.cost_liquidity.entries])}
        )
        source_payload = {
            "h7_memo_hash": self.source_hashes.h7_memo_hash,
            "risk_policy_hash": self.source_hashes.risk_policy_hash,
            "prior_weights_fingerprint": self.source_hashes.prior_weights_fingerprint,
            "covariance_hash": self.source_hashes.covariance_hash,
            "calibrated_hashes": sorted([list(pair) for pair in self.source_hashes.calibrated_hashes]),
            "cost_hashes": sorted([list(pair) for pair in self.source_hashes.cost_hashes]),
        }
        return allocation_bundle_hash_payload(
            schema_version=self.schema_version,
            run=run_payload,
            canonical_asset_order=self.canonical_asset_order,
            mandates=mandates_payload,
            calibrated_returns=calibrated_payload,
            prior_book=prior_payload,
            control_settings=control_payload,
            covariance=covariance_payload,
            cost_liquidity=cost_payload,
            source_hashes=source_payload,
        )


def build_source_hashes(
    *,
    h7_memo_hash: str,
    risk_policy_hash: str,
    prior_entries: tuple[tuple[str, float], ...],
    calibrated_hashes: tuple[tuple[str, str], ...],
    covariance_hash: str | None = None,
    cost_hashes: tuple[tuple[str, str], ...] = (),
) -> AllocationSourceHashes:
    """Construct validated source hashes with prior weights fingerprint."""
    return AllocationSourceHashes(
        h7_memo_hash=h7_memo_hash,
        risk_policy_hash=risk_policy_hash,
        prior_weights_fingerprint=weights_fingerprint(prior_weights_from_entries(prior_entries)),
        covariance_hash=covariance_hash,
        calibrated_hashes=calibrated_hashes,
        cost_hashes=cost_hashes,
    )


__all__ = [
    "AllocationCadence",
    "AllocationInputBundle",
    "AllocationRunContext",
    "AllocationSourceHashes",
    "AssetInputStatus",
    "CalibratedReturnSlice",
    "ControlSettingsFingerprint",
    "CovarianceBinding",
    "CostLiquidityBinding",
    "MandateReference",
    "PriorBookSnapshot",
    "PriorWeightEntry",
    "build_source_hashes",
]
