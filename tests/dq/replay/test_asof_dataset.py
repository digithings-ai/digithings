"""WP16.3 — as-of dataset builder (#2987)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.dashboard.replay.asof_dataset import (
    AsOfDatasetBuildError,
    AsOfDatasetSnapshot,
    VersionedBarSeries,
    build_asof_dataset,
    build_replay_input_manifest,
    build_shared_portfolio_request,
)
from digiquant.dashboard.replay.canonical import data_hash_from_request
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    InstrumentBarSeries,
    OhlcvBar,
    PolicyFamily,
    PolicyVersionRef,
    TargetWeight,
)
from digiquant.dashboard.replay.policy_registry import PolicyRegistry, RegisteredPolicyVersion

pytestmark = pytest.mark.unit

_CUTOFF = datetime(2024, 6, 15, 12, 0, tzinfo=UTC)
_EARLIER = _CUTOFF - timedelta(days=2)
_LATER = _CUTOFF + timedelta(days=1)


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 6, day, tzinfo=UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str, closes: tuple[str, ...]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 10, c) for i, c in enumerate(closes)),
    )


def _versioned(
    ticker: str,
    closes: tuple[str, ...],
    *,
    version_id: str,
    known_at: datetime,
) -> VersionedBarSeries:
    series = _series(ticker, closes)
    return VersionedBarSeries(
        version_id=version_id,
        known_at=known_at,
        series=series,
        content_hash=sha256_hex(series.model_dump(mode="json")),
    )


def test_build_asof_dataset_selects_latest_visible_bar_version() -> None:
    bars = (
        _versioned("AAPL", ("100", "101"), version_id="bars-v1", known_at=_EARLIER),
        _versioned("AAPL", ("200", "201"), version_id="bars-v2", known_at=_LATER),
        _versioned("MSFT", ("50", "51"), version_id="bars-v1", known_at=_EARLIER),
    )
    execution = ExecutionPolicy(random_seed=7, commission_rate=Decimal("0.001"))

    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=execution,
        starting_cash=Decimal("250000"),
    )

    aapl = next(s for s in snapshot.series if s.ticker == "AAPL")
    assert aapl.bars[0].close == Decimal("100")


def test_later_bar_mutation_does_not_change_historical_manifest() -> None:
    bars = (
        _versioned("AAPL", ("100", "101"), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50", "51"), version_id="bars-v1", known_at=_EARLIER),
    )
    execution = ExecutionPolicy(random_seed=11)

    first = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=execution,
        starting_cash=Decimal("100000"),
    )
    manifest_v1 = build_replay_input_manifest(first, manifest_id="m-1")

    extended = (
        *bars,
        _versioned("AAPL", ("999", "998"), version_id="bars-v2", known_at=_LATER),
    )
    second = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=extended,
        execution=execution,
        starting_cash=Decimal("100000"),
    )
    manifest_v2 = build_replay_input_manifest(second, manifest_id="m-1")

    assert manifest_v1.manifest_content_hash == manifest_v2.manifest_content_hash
    assert first.dataset_content_hash == second.dataset_content_hash


def test_build_asof_dataset_rejects_future_bar_versions() -> None:
    bars = (_versioned("AAPL", ("100",), version_id="bars-future", known_at=_LATER),)

    with pytest.raises(AsOfDatasetBuildError, match="future"):
        build_asof_dataset(
            replay_as_of=_CUTOFF,
            bar_versions=bars,
            execution=ExecutionPolicy(),
            starting_cash=Decimal("100000"),
        )


def test_build_asof_dataset_rejects_incomplete_instrument_coverage() -> None:
    bars = (_versioned("AAPL", ("100", "101"), version_id="bars-v1", known_at=_EARLIER),)

    with pytest.raises(AsOfDatasetBuildError, match="MSFT"):
        build_asof_dataset(
            replay_as_of=_CUTOFF,
            bar_versions=bars,
            execution=ExecutionPolicy(),
            starting_cash=Decimal("100000"),
            required_tickers=("AAPL", "MSFT"),
        )


def test_paired_arms_share_bars_cash_costs_timing_seed() -> None:
    bars = (
        _versioned("AAPL", ("100", "101"), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50", "51"), version_id="bars-v1", known_at=_EARLIER),
    )
    execution = ExecutionPolicy(
        random_seed=42, commission_rate=Decimal("0.002"), fill_fraction=Decimal("0.9")
    )

    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=execution,
        starting_cash=Decimal("100000"),
    )
    manifest = build_replay_input_manifest(snapshot, manifest_id="shared-m")

    req_a = build_shared_portfolio_request(
        snapshot,
        request_id="arm-a",
        target_weights=(TargetWeight(ticker="AAPL", weight=Decimal("0.5")),),
    )
    req_b = build_shared_portfolio_request(
        snapshot,
        request_id="arm-b",
        target_weights=(TargetWeight(ticker="MSFT", weight=Decimal("0.5")),),
    )

    assert data_hash_from_request(req_a) == data_hash_from_request(req_b)
    assert req_a.starting_cash == req_b.starting_cash
    assert req_a.execution == req_b.execution
    assert manifest.shared.data_hash == data_hash_from_request(req_a)


def test_manifest_pins_infrastructure_source_refs() -> None:
    bars = (
        _versioned("AAPL", ("100",), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50",), version_id="bars-v1", known_at=_EARLIER),
    )
    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=ExecutionPolicy(random_seed=3),
        starting_cash=Decimal("100000"),
    )
    manifest = build_replay_input_manifest(snapshot, manifest_id="infra-m")

    families = {ref.family for ref in manifest.source_refs}
    assert PolicyFamily.DATA_SOURCE in families
    assert PolicyFamily.COST_SCHEDULE in families
    assert PolicyFamily.EXECUTION_FILL in families
    assert PolicyFamily.RANDOM_SEED in families


def test_resolve_policy_bundle_via_registry_from_snapshot() -> None:
    registry = PolicyRegistry()
    plan_body = {"mode": "research_plan", "planner": "incumbent"}
    plan_hash = sha256_hex(plan_body)
    registry.register(
        RegisteredPolicyVersion(
            family=PolicyFamily.RESEARCH_PLAN,
            version_id="plan-v1",
            content_hash=plan_hash,
            known_at=_EARLIER,
            payload=plan_body,
        ),
    )

    bars = (
        _versioned("AAPL", ("100",), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50",), version_id="bars-v1", known_at=_EARLIER),
    )
    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=ExecutionPolicy(),
        starting_cash=Decimal("100000"),
        policy_registry=registry,
        policy_refs=(
            PolicyVersionRef(
                family=PolicyFamily.RESEARCH_PLAN,
                version_id="plan-v1",
                content_hash=plan_hash,
            ),
        ),
    )

    assert snapshot.resolved_policies is not None
    assert snapshot.resolved_policies["research_plan"].payload == plan_body


def test_build_asof_dataset_requires_registry_when_policy_refs_declared() -> None:
    bars = (
        _versioned("AAPL", ("100",), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50",), version_id="bars-v1", known_at=_EARLIER),
    )
    plan_hash = sha256_hex({"mode": "research_plan"})
    policy_refs = (
        PolicyVersionRef(
            family=PolicyFamily.RESEARCH_PLAN,
            version_id="plan-v1",
            content_hash=plan_hash,
        ),
    )

    with pytest.raises(AsOfDatasetBuildError, match="policy_registry required"):
        build_asof_dataset(
            replay_as_of=_CUTOFF,
            bar_versions=bars,
            execution=ExecutionPolicy(),
            starting_cash=Decimal("100000"),
            policy_refs=policy_refs,
        )


def test_snapshot_is_frozen_immutable() -> None:
    bars = (
        _versioned("AAPL", ("100",), version_id="bars-v1", known_at=_EARLIER),
        _versioned("MSFT", ("50",), version_id="bars-v1", known_at=_EARLIER),
    )
    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=ExecutionPolicy(),
        starting_cash=Decimal("100000"),
    )
    assert isinstance(snapshot, AsOfDatasetSnapshot)
    with pytest.raises(Exception):
        snapshot.replay_as_of = _LATER  # type: ignore[misc]
