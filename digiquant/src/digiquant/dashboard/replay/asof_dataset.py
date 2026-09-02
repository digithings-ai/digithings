"""WP16.3 — cutoff-bound as-of dataset materialization (#2987).

Builds identical historical replay inputs (bars, calendar, cash, costs, timing,
seed) and :class:`~digiquant.olympus.replay.models.ReplayInputManifest`
envelopes. All source reads filter ``known_at <= replay_as_of``. Later source
mutations cannot change a historical manifest when the cutoff is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from digiquant.olympus.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_series,
    execution_policy_hash,
    fill_fraction_hash,
    random_seed_hash,
    replay_input_manifest_content_hash,
)
from digiquant.olympus.replay.models import (
    ExecutionPolicy,
    HoldingQuantity,
    InstrumentBarSeries,
    PolicyFamily,
    PolicyVersionRef,
    PortfolioReplayRequest,
    ReplayInputManifest,
    SharedInputIdentity,
    TargetWeight,
    WalkForwardFold,
)
from digiquant.olympus.replay.policy_registry import (
    PolicyRegistry,
    RegisteredPolicyVersion,
)
from digiquant.olympus.temporal import require_utc_datetime

__all__ = [
    "AsOfDatasetBuildError",
    "AsOfDatasetSnapshot",
    "VersionedBarSeries",
    "build_asof_dataset",
    "build_replay_input_manifest",
    "build_shared_portfolio_request",
]


class AsOfDatasetBuildError(RuntimeError):
    """As-of dataset could not be materialized at the cutoff."""


@dataclass(frozen=True)
class VersionedBarSeries:
    """One versioned bar series observation with knowledge time."""

    version_id: str
    known_at: datetime
    series: InstrumentBarSeries
    content_hash: str

    def __post_init__(self) -> None:
        require_utc_datetime(self.known_at, field_name="known_at")


@dataclass(frozen=True)
class AsOfDatasetSnapshot:
    """Pinned as-of replay inputs shared by every arm in a comparison."""

    replay_as_of: datetime
    series: tuple[InstrumentBarSeries, ...]
    execution: ExecutionPolicy
    starting_cash: Decimal
    dataset_content_hash: str
    bar_version_id: str
    source_refs: tuple[PolicyVersionRef, ...]
    shared: SharedInputIdentity
    resolved_policies: dict[str, RegisteredPolicyVersion] | None = None

    def __post_init__(self) -> None:
        require_utc_datetime(self.replay_as_of, field_name="replay_as_of")


def _select_bar_versions(
    *,
    bar_versions: tuple[VersionedBarSeries, ...],
    replay_as_of: datetime,
    required_tickers: tuple[str, ...],
) -> tuple[InstrumentBarSeries, ...]:
    cutoff = require_utc_datetime(replay_as_of, field_name="replay_as_of")
    visible = [row for row in bar_versions if row.known_at <= cutoff]
    if not visible:
        raise AsOfDatasetBuildError("no bar versions visible at replay cutoff")

    by_ticker: dict[str, VersionedBarSeries] = {}
    for row in visible:
        ticker = row.series.ticker
        current = by_ticker.get(ticker)
        if current is None or row.known_at > current.known_at:
            by_ticker[ticker] = row

    missing = [ticker for ticker in required_tickers if ticker not in by_ticker]
    if missing:
        raise AsOfDatasetBuildError(f"incomplete bar coverage at cutoff: {sorted(missing)}")

    tickers = sorted(by_ticker)
    return tuple(by_ticker[ticker].series for ticker in tickers)


def _bar_version_id(selected: tuple[InstrumentBarSeries, ...]) -> str:
    tickers = "-".join(s.ticker for s in selected)
    return f"bars-{tickers}-v1"


def _infrastructure_source_refs(
    *,
    dataset_content_hash: str,
    execution: ExecutionPolicy,
    shared: SharedInputIdentity,
    bar_version_id: str,
) -> tuple[PolicyVersionRef, ...]:
    refs = (
        PolicyVersionRef(
            family=PolicyFamily.DATA_SOURCE,
            version_id=bar_version_id,
            content_hash=dataset_content_hash,
        ),
        PolicyVersionRef(
            family=PolicyFamily.COST_SCHEDULE,
            version_id="cost-schedule-v1",
            content_hash=shared.cost_hash,
        ),
        PolicyVersionRef(
            family=PolicyFamily.EXECUTION_FILL,
            version_id="execution-fill-v1",
            content_hash=shared.execution_hash,
        ),
        PolicyVersionRef(
            family=PolicyFamily.RANDOM_SEED,
            version_id=f"seed-{execution.random_seed}",
            content_hash=shared.random_seed_hash,
        ),
    )
    return tuple(sorted(refs, key=lambda ref: (ref.family.value, ref.version_id)))


def _merge_source_refs(
    infrastructure: tuple[PolicyVersionRef, ...],
    policy_refs: tuple[PolicyVersionRef, ...],
) -> tuple[PolicyVersionRef, ...]:
    merged = {(_registry_family(ref), ref.version_id): ref for ref in infrastructure}
    for ref in policy_refs:
        merged[(_registry_family(ref), ref.version_id)] = ref
    return tuple(sorted(merged.values(), key=lambda ref: (ref.family.value, ref.version_id)))


def _registry_family(ref: PolicyVersionRef) -> str:
    return ref.family.value


def build_asof_dataset(
    *,
    replay_as_of: datetime,
    bar_versions: tuple[VersionedBarSeries, ...],
    execution: ExecutionPolicy,
    starting_cash: Decimal,
    required_tickers: tuple[str, ...] | None = None,
    policy_registry: PolicyRegistry | None = None,
    policy_refs: tuple[PolicyVersionRef, ...] = (),
) -> AsOfDatasetSnapshot:
    """Materialize shared replay inputs visible at *replay_as_of*."""
    cutoff = require_utc_datetime(replay_as_of, field_name="replay_as_of")

    tickers = required_tickers
    if tickers is None:
        tickers = tuple(sorted({row.series.ticker for row in bar_versions}))
    if not tickers:
        raise AsOfDatasetBuildError("required_tickers must be non-empty")

    if any(row.known_at > cutoff for row in bar_versions) and not any(
        row.known_at <= cutoff for row in bar_versions
    ):
        raise AsOfDatasetBuildError("future bar evidence at replay cutoff")

    series = _select_bar_versions(
        bar_versions=bar_versions,
        replay_as_of=cutoff,
        required_tickers=tickers,
    )
    dataset_hash = data_hash_from_series(series)
    bar_version_id = _bar_version_id(series)

    shared = SharedInputIdentity(
        data_hash=dataset_hash,
        cost_hash=cost_hash_from_execution(execution),
        execution_hash=execution_policy_hash(execution),
        random_seed_hash=random_seed_hash(execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(execution.fill_fraction),
        starting_cash=starting_cash,
    )
    infra_refs = _infrastructure_source_refs(
        dataset_content_hash=dataset_hash,
        execution=execution,
        shared=shared,
        bar_version_id=bar_version_id,
    )
    source_refs = _merge_source_refs(infra_refs, policy_refs)

    resolved: dict[str, RegisteredPolicyVersion] | None = None
    if policy_refs:
        if policy_registry is None:
            raise AsOfDatasetBuildError(
                "policy_registry required when policy_refs are declared"
            )
        resolved = {}
        for ref in policy_refs:
            version = policy_registry.resolve(ref, replay_as_of=cutoff, review_pinned=True)
            mode_key = ref.family.value
            if ref.family == PolicyFamily.RESEARCH_PLAN:
                mode_key = "research_plan"
            elif ref.family == PolicyFamily.PORTFOLIO_TARGET:
                mode_key = "portfolio_target"
            elif ref.family == PolicyFamily.OBSERVED_SHADOW:
                mode_key = "observed_shadow"
            resolved[mode_key] = version

    return AsOfDatasetSnapshot(
        replay_as_of=cutoff,
        series=series,
        execution=execution,
        starting_cash=starting_cash,
        dataset_content_hash=dataset_hash,
        bar_version_id=bar_version_id,
        source_refs=source_refs,
        shared=shared,
        resolved_policies=resolved,
    )


def build_replay_input_manifest(
    snapshot: AsOfDatasetSnapshot,
    *,
    manifest_id: str,
    fold: WalkForwardFold | None = None,
) -> ReplayInputManifest:
    """Build a validated :class:`ReplayInputManifest` from a pinned snapshot."""
    content_hash = replay_input_manifest_content_hash(
        manifest_id=manifest_id,
        replay_as_of=snapshot.replay_as_of,
        shared=snapshot.shared,
        source_refs=snapshot.source_refs,
        dataset_content_hash=snapshot.dataset_content_hash,
        fold=fold,
    )
    return ReplayInputManifest(
        manifest_id=manifest_id,
        replay_as_of=snapshot.replay_as_of,
        shared=snapshot.shared,
        source_refs=snapshot.source_refs,
        dataset_content_hash=snapshot.dataset_content_hash,
        fold=fold,
        manifest_content_hash=content_hash,
    )


def build_shared_portfolio_request(
    snapshot: AsOfDatasetSnapshot,
    *,
    request_id: str,
    target_weights: tuple[TargetWeight, ...],
    initial_holdings: tuple[HoldingQuantity, ...] = (),
) -> PortfolioReplayRequest:
    """Build one portfolio replay request using shared as-of inputs only."""
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=snapshot.starting_cash,
        series=snapshot.series,
        target_weights=target_weights,
        initial_holdings=initial_holdings,
        execution=snapshot.execution,
    )
