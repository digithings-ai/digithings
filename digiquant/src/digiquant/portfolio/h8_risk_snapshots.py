"""H8 risk snapshot attachment at the sizing entry boundary (#2698 / WP6.3).

Keeps :mod:`digiquant.portfolio.risk_policy` free of
:mod:`digiquant.portfolio.phases.phase7e_risk_sizing` import cycles.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
from uuid import UUID

import polars as pl

from digiquant.research.state import ResearchState
from digiquant.portfolio.models.risk_policy import (
    CovarianceSnapshot,
    PolicyArtifactStatus,
    RiskPolicy,
    covariance_snapshot_content_hash,
    covariance_snapshot_id,
    policy_hash_payload,
    risk_policy_content_hash,
    risk_policy_id,
    snapshot_hash_payload,
)
from digiquant.portfolio.risk_policy import resolve_covariance_snapshot, resolve_risk_policy
from digiquant.dashboard.temporal import require_utc_datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class H8RiskArtifacts:
    """Resolved incumbent H8 inputs for audit — never wired into ``size_portfolio`` in Phase 1."""

    policy: RiskPolicy
    covariance_snapshot: CovarianceSnapshot


def _h8_effective_at(state: ResearchState) -> datetime:
    cutoff = state.knowledge_cutoff_at
    if cutoff is not None:
        return require_utc_datetime(cutoff, field_name="knowledge_cutoff_at")
    return datetime.combine(state.run_date, datetime.min.time(), tzinfo=UTC)


def _restamp_policy_unavailable(policy: RiskPolicy, *, reason: str) -> RiskPolicy:
    payload: dict[str, Any] = {
        **policy.model_dump(mode="python"),
        "status": PolicyArtifactStatus.UNAVAILABLE,
        "unavailable_reason": reason,
        "content_hash": "0" * 64,
        "policy_id": UUID(int=0),
    }
    draft = RiskPolicy.model_construct(**payload)
    content_hash = risk_policy_content_hash(payload=policy_hash_payload(draft))
    return RiskPolicy.model_validate(
        {
            **draft.model_dump(mode="python"),
            "content_hash": content_hash,
            "policy_id": risk_policy_id(
                method_version=draft.method_version, content_hash=content_hash
            ),
        }
    )


def _restamp_snapshot_unavailable(
    snapshot: CovarianceSnapshot, *, reason: str
) -> CovarianceSnapshot:
    payload: dict[str, Any] = {
        **snapshot.model_dump(mode="python"),
        "status": PolicyArtifactStatus.UNAVAILABLE,
        "unavailable_reason": reason,
        "content_hash": "0" * 64,
        "snapshot_id": UUID(int=0),
    }
    draft = CovarianceSnapshot.model_construct(**payload)
    content_hash = covariance_snapshot_content_hash(payload=snapshot_hash_payload(draft))
    return CovarianceSnapshot.model_validate(
        {
            **draft.model_dump(mode="python"),
            "content_hash": content_hash,
            "snapshot_id": covariance_snapshot_id(
                as_of_session=draft.as_of_session,
                tickers=draft.tickers,
                content_hash=content_hash,
            ),
        }
    )


def _fail_closed_artifacts(
    *,
    state: ResearchState,
    pm_tickers: list[str],
    reason: str,
) -> H8RiskArtifacts:
    """Typed unavailable artifacts when resolution fails (#2803)."""
    effective_at = _h8_effective_at(state)
    clipped = reason.strip()[:200] or "resolver_error"
    tagged = f"resolver_error:{clipped}"
    baseline_policy = resolve_risk_policy(
        {},
        effective_at=effective_at,
        source_run_id=str(state.run_id),
    ).policy
    baseline_snapshot = resolve_covariance_snapshot(
        tickers=pm_tickers,
        corr=None,
        as_of_session=state.run_date,
        resolved_at=effective_at,
    )
    return H8RiskArtifacts(
        policy=_restamp_policy_unavailable(baseline_policy, reason=tagged),
        covariance_snapshot=_restamp_snapshot_unavailable(baseline_snapshot, reason=tagged),
    )


def resolve_h8_risk_artifacts(
    *,
    state: ResearchState,
    pm_tickers: list[str],
    corr: pl.DataFrame | None,
    observation_count: int | None = None,
) -> H8RiskArtifacts:
    """Resolve policy + covariance snapshot at the H8 entry boundary (#2698 / WP6.3).

    Always returns typed artifacts. Resolver exceptions become visible
    ``unavailable`` dumps rather than silent omission (#2803).
    """
    try:
        effective_at = _h8_effective_at(state)
        resolution = resolve_risk_policy(
            state.config.preferences,
            effective_at=effective_at,
            source_run_id=str(state.run_id),
        )
        snapshot = resolve_covariance_snapshot(
            tickers=pm_tickers,
            corr=corr,
            as_of_session=state.run_date,
            resolved_at=effective_at,
            observation_count=observation_count,
        )
        return H8RiskArtifacts(policy=resolution.policy, covariance_snapshot=snapshot)
    except Exception as exc:
        logger.warning(
            "h8 risk snapshot resolution failed (%s: %s); attaching unavailable artifacts",
            type(exc).__name__,
            exc,
        )
        return _fail_closed_artifacts(
            state=state,
            pm_tickers=pm_tickers,
            reason=f"{type(exc).__name__}:{exc}",
        )


__all__ = ["H8RiskArtifacts", "resolve_h8_risk_artifacts"]
