"""H8 risk snapshot attachment at the sizing entry boundary (#2698 / WP6.3).

Keeps :mod:`digiquant.olympus.hermes.risk_policy` free of
:mod:`digiquant.olympus.hermes.phases.phase7e_risk_sizing` import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import polars as pl

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.models.risk_policy import CovarianceSnapshot, RiskPolicy
from digiquant.olympus.hermes.risk_policy import resolve_covariance_snapshot, resolve_risk_policy
from digiquant.olympus.temporal import require_utc_datetime


@dataclass(frozen=True)
class H8RiskArtifacts:
    """Resolved incumbent H8 inputs for audit — never wired into ``size_portfolio`` in Phase 1."""

    policy: RiskPolicy
    covariance_snapshot: CovarianceSnapshot


def _h8_effective_at(state: AtlasResearchState) -> datetime:
    cutoff = state.knowledge_cutoff_at
    if cutoff is not None:
        return require_utc_datetime(cutoff, field_name="knowledge_cutoff_at")
    return datetime.combine(state.run_date, datetime.min.time(), tzinfo=UTC)


def resolve_h8_risk_artifacts(
    *,
    state: AtlasResearchState,
    pm_tickers: list[str],
    corr: pl.DataFrame | None,
    observation_count: int | None = None,
) -> H8RiskArtifacts:
    """Resolve policy + covariance snapshot at the H8 entry boundary (#2698 / WP6.3)."""
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


__all__ = ["H8RiskArtifacts", "resolve_h8_risk_artifacts"]
