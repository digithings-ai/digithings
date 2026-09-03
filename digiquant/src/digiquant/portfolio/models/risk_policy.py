"""Versioned risk policy and covariance snapshot contracts (#2692 / WP6.2).

Strict Pydantic v2 models resolve every incumbent H8 leaf with provenance before
H9/replay consumption. Phase 1 versions incumbent behavior only — no optimizer
or live ``size_portfolio`` input swap.

Style mirrors :mod:`digiquant.portfolio.models.forecast_calibration`:
frozen, ``extra="forbid"``, UTC-only aware datetimes, deterministic hashes.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from enum import StrEnum
from typing import Annotated, TypeAlias
from uuid import UUID, uuid5

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_RISK_POLICY_ID_NAMESPACE = UUID("f3a4b5c6-d7e8-4901-a2b3-c4d5e6f70891")
_COVARIANCE_SNAPSHOT_ID_NAMESPACE = UUID("a1b2c3d4-e5f6-4702-8c9d-0e1f2a3b4c5d")

NonEmptyId: TypeAlias = Annotated[str, Field(min_length=1)]
PositiveFloat: TypeAlias = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFloat: TypeAlias = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class RiskPolicyModel(BaseModel):
    """Strict immutable base for risk-policy contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyArtifactStatus(StrEnum):
    """Whether a resolved policy or covariance snapshot is usable."""

    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProvenanceSource(StrEnum):
    """Origin of one resolved policy leaf."""

    EXPLICIT_CONFIG = "explicit_config"
    NORMALIZED_CONFIG = "normalized_config"
    CODE_DEFAULT = "code_default"
    DERIVED_INVARIANT = "derived_invariant"


class ResolvedLeaf(RiskPolicyModel):
    """One fully resolved scalar or string with provenance."""

    value: float | int | str | bool
    source: ProvenanceSource
    config_key: str | None = None
    note: str | None = None


class CapabilityLimit(RiskPolicyModel):
    """Explicit unavailable/enforced state for advanced risk limits."""

    available: bool
    enforced: bool
    limit: float | None = None
    reason: NonEmptyId | None = None

    @model_validator(mode="after")
    def _validate_capability(self) -> CapabilityLimit:
        if not self.available:
            if self.enforced:
                raise ValueError("unavailable capability cannot be enforced")
            if self.limit is not None:
                raise ValueError("unavailable capability cannot carry a limit")
            if not self.reason:
                raise ValueError("unavailable capability requires reason")
        return self


class CorrelationBucketEntry(RiskPolicyModel):
    """One symmetric asset-class bucket correlation."""

    class_a: NonEmptyId
    class_b: NonEmptyId
    rho: float
    source: ProvenanceSource = ProvenanceSource.CODE_DEFAULT


class VolFallbackEntry(RiskPolicyModel):
    """One step in the per-ticker vol fallback chain."""

    key: NonEmptyId
    annualized_pct: float
    source: ProvenanceSource = ProvenanceSource.CODE_DEFAULT


class RankToConvictionEntry(RiskPolicyModel):
    """Rank→conviction mapping for one long-count regime."""

    n_long: int = Field(ge=1)
    mapping: dict[int, float]
    floor: float
    source: ProvenanceSource = ProvenanceSource.CODE_DEFAULT


class RiskPolicy(RiskPolicyModel):
    """Fully resolved incumbent H8 policy — every leaf carries provenance."""

    policy_id: UUID
    method_version: NonEmptyId
    effective_at: AwareDatetime
    source_run_id: NonEmptyId | None = None
    status: PolicyArtifactStatus
    unavailable_reason: NonEmptyId | None = None
    content_hash: NonEmptyId

    sizing_caps: dict[str, ResolvedLeaf]
    breaker: dict[str, ResolvedLeaf]
    turnover: dict[str, ResolvedLeaf]
    horizons: dict[str, ResolvedLeaf]
    control_order: tuple[NonEmptyId, ...]
    correlation_buckets: tuple[CorrelationBucketEntry, ...]
    vol_fallback_chain: tuple[VolFallbackEntry, ...]
    rank_to_conviction: tuple[RankToConvictionEntry, ...]
    annualize_factor: ResolvedLeaf
    vol_lookback_days: ResolvedLeaf
    corr_lookback_days: ResolvedLeaf

    factor_limits: CapabilityLimit
    stress_limits: CapabilityLimit
    tail_limits: CapabilityLimit
    liquidity_limits: CapabilityLimit
    cost_policy: CapabilityLimit
    cost_coefficients: dict[str, ResolvedLeaf]

    @model_validator(mode="after")
    def _validate_policy(self) -> RiskPolicy:
        if self.effective_at.utcoffset() != timedelta(0):
            raise ValueError("effective_at must be timezone-aware UTC")
        if self.status is PolicyArtifactStatus.UNAVAILABLE:
            if not self.unavailable_reason:
                raise ValueError("unavailable policy requires unavailable_reason")
        elif self.status is PolicyArtifactStatus.DEGRADED:
            if not self.unavailable_reason:
                raise ValueError("degraded policy requires unavailable_reason")
        elif self.unavailable_reason is not None:
            raise ValueError("available policy cannot carry unavailable_reason")
        expected_hash = risk_policy_content_hash(payload=policy_hash_payload(self))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical policy digest")
        expected_id = risk_policy_id(
            method_version=self.method_version, content_hash=self.content_hash
        )
        if self.policy_id != expected_id:
            raise ValueError("policy_id must be UUID5 of method_version+content_hash")
        return self


class CovarianceSnapshot(RiskPolicyModel):
    """Canonical as-of correlation matrix snapshot for one book."""

    snapshot_id: UUID
    method_version: NonEmptyId
    as_of_session: date
    lookback_days: int = Field(ge=1)
    estimator: NonEmptyId
    shrinkage: NonEmptyId
    fallback_policy: NonEmptyId
    tickers: tuple[NonEmptyId, ...]
    matrix: tuple[tuple[float, ...], ...]
    observation_count: int | None = Field(default=None, ge=0)
    source_table: NonEmptyId | None = None
    resolved_at: AwareDatetime
    status: PolicyArtifactStatus
    unavailable_reason: NonEmptyId | None = None
    content_hash: NonEmptyId

    @field_validator("matrix")
    @classmethod
    def _validate_matrix_shape(
        cls, value: tuple[tuple[float, ...], ...]
    ) -> tuple[tuple[float, ...], ...]:
        n = len(value)
        for row in value:
            if len(row) != n:
                raise ValueError("matrix must be square")
        return value

    @model_validator(mode="after")
    def _validate_snapshot(self) -> CovarianceSnapshot:
        if self.resolved_at.utcoffset() != timedelta(0):
            raise ValueError("resolved_at must be timezone-aware UTC")
        n = len(self.tickers)
        if len(self.matrix) != n:
            raise ValueError("matrix row count must match tickers")
        if self.status is PolicyArtifactStatus.UNAVAILABLE:
            if not self.unavailable_reason:
                raise ValueError("unavailable snapshot requires unavailable_reason")
        elif self.status is PolicyArtifactStatus.DEGRADED:
            if not self.unavailable_reason:
                raise ValueError("degraded snapshot requires unavailable_reason")
        elif self.unavailable_reason is not None:
            raise ValueError("available snapshot cannot carry unavailable_reason")

        for i in range(n):
            for j in range(n):
                val = self.matrix[i][j]
                if not math.isfinite(val):
                    raise ValueError("matrix entries must be finite")
                if abs(val) > 1.0 + 1e-9:
                    raise ValueError("correlation entries must lie in [-1, 1]")
                if abs(self.matrix[j][i] - val) > 1e-9:
                    raise ValueError("matrix must be symmetric")
            if abs(self.matrix[i][i] - 1.0) > 1e-9:
                raise ValueError("diagonal must be 1.0")

        expected_hash = covariance_snapshot_content_hash(payload=snapshot_hash_payload(self))
        if self.content_hash != expected_hash:
            raise ValueError("content_hash must match canonical snapshot digest")
        expected_id = covariance_snapshot_id(
            as_of_session=self.as_of_session,
            tickers=self.tickers,
            content_hash=self.content_hash,
        )
        if self.snapshot_id != expected_id:
            raise ValueError("snapshot_id must be UUID5 of session+tickers+content_hash")
        return self


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def risk_policy_content_hash(*, payload: dict[str, object]) -> str:
    """SHA-256 over canonical JSON of resolved policy identity fields."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def risk_policy_id(*, method_version: str, content_hash: str) -> UUID:
    """Deterministic UUID5 for a versioned risk policy."""
    if not method_version.strip() or not content_hash.strip():
        raise ValueError("method_version and content_hash are required")
    return uuid5(
        _RISK_POLICY_ID_NAMESPACE,
        f"{method_version.strip()}:{content_hash.strip()}",
    )


def covariance_snapshot_content_hash(*, payload: dict[str, object]) -> str:
    """SHA-256 over canonical JSON of snapshot economic identity."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def covariance_snapshot_id(
    *,
    as_of_session: date,
    tickers: tuple[str, ...],
    content_hash: str,
) -> UUID:
    """Deterministic UUID5 for one book correlation snapshot."""
    if not content_hash.strip():
        raise ValueError("content_hash is required")
    ticker_key = ",".join(t.strip().upper() for t in tickers)
    return uuid5(
        _COVARIANCE_SNAPSHOT_ID_NAMESPACE,
        f"{as_of_session.isoformat()}:{ticker_key}:{content_hash.strip()}",
    )


def _leaf_json(leaf: ResolvedLeaf) -> dict[str, object]:
    return {
        "value": leaf.value,
        "source": leaf.source.value,
        "config_key": leaf.config_key,
        "note": leaf.note,
    }


def _capability_json(cap: CapabilityLimit) -> dict[str, object]:
    return cap.model_dump(mode="json")


def policy_hash_payload(policy: RiskPolicy) -> dict[str, object]:
    return {
        "method_version": policy.method_version,
        "status": policy.status.value,
        # Distinct degrade/unavailable reasons must not share policy_id (#2803).
        "unavailable_reason": policy.unavailable_reason,
        "sizing_caps": {k: _leaf_json(v) for k, v in sorted(policy.sizing_caps.items())},
        "breaker": {k: _leaf_json(v) for k, v in sorted(policy.breaker.items())},
        "turnover": {k: _leaf_json(v) for k, v in sorted(policy.turnover.items())},
        "horizons": {k: _leaf_json(v) for k, v in sorted(policy.horizons.items())},
        "control_order": list(policy.control_order),
        "correlation_buckets": [e.model_dump(mode="json") for e in policy.correlation_buckets],
        "vol_fallback_chain": [e.model_dump(mode="json") for e in policy.vol_fallback_chain],
        "rank_to_conviction": [e.model_dump(mode="json") for e in policy.rank_to_conviction],
        "annualize_factor": _leaf_json(policy.annualize_factor),
        "vol_lookback_days": _leaf_json(policy.vol_lookback_days),
        "corr_lookback_days": _leaf_json(policy.corr_lookback_days),
        "factor_limits": _capability_json(policy.factor_limits),
        "stress_limits": _capability_json(policy.stress_limits),
        "tail_limits": _capability_json(policy.tail_limits),
        "liquidity_limits": _capability_json(policy.liquidity_limits),
        "cost_policy": _capability_json(policy.cost_policy),
        "cost_coefficients": {
            k: _leaf_json(v) for k, v in sorted(policy.cost_coefficients.items())
        },
    }


def snapshot_hash_payload(snapshot: CovarianceSnapshot) -> dict[str, object]:
    return {
        "method_version": snapshot.method_version,
        "as_of_session": snapshot.as_of_session.isoformat(),
        "lookback_days": snapshot.lookback_days,
        "estimator": snapshot.estimator,
        "shrinkage": snapshot.shrinkage,
        "fallback_policy": snapshot.fallback_policy,
        "tickers": list(snapshot.tickers),
        "matrix": [list(row) for row in snapshot.matrix],
        "observation_count": snapshot.observation_count,
        "status": snapshot.status.value,
        # Placeholder identity matrices must still diverge by reason (#2803).
        "unavailable_reason": snapshot.unavailable_reason,
    }


__all__ = [
    "CapabilityLimit",
    "CorrelationBucketEntry",
    "CovarianceSnapshot",
    "PolicyArtifactStatus",
    "ProvenanceSource",
    "RankToConvictionEntry",
    "ResolvedLeaf",
    "RiskPolicy",
    "VolFallbackEntry",
    "covariance_snapshot_content_hash",
    "covariance_snapshot_id",
    "policy_hash_payload",
    "risk_policy_content_hash",
    "risk_policy_id",
    "snapshot_hash_payload",
]
