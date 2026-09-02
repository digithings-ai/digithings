"""WP16.9 — CLI surface for policy replay inspection (#3011)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from click.testing import CliRunner
from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_request,
    execution_policy_hash,
    fill_fraction_hash,
    policy_bundle_content_hash,
    random_seed_hash,
    replay_input_manifest_content_hash,
)
from digiquant.olympus.replay.cli import policy_replay
from digiquant.olympus.replay.models import (
    ExecutionPolicy,
    InstrumentBarSeries,
    OhlcvBar,
    PolicyBundle,
    PolicyFamily,
    PolicyVersionRef,
    PortfolioReplayRequest,
    ReplayArmLabel,
    ReplayArmSpec,
    ReplayInputManifest,
    SharedInputIdentity,
    TargetWeight,
    build_replay_pair,
)
from digiquant.olympus.replay.store import PolicyReplayStore
from digiquant.service import set_policy_replay_store

pytestmark = pytest.mark.unit

_TS = datetime(2024, 2, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh_store() -> None:
    set_policy_replay_store(PolicyReplayStore())
    yield
    set_policy_replay_store(None)


def _seed_pair() -> str:
    closes = ["100", "101", "102"]
    series = tuple(
        InstrumentBarSeries(
            ticker=t,
            bars=tuple(
                OhlcvBar(
                    ts=datetime(2024, 1, i + 2, tzinfo=UTC),
                    open=Decimal(c),
                    high=Decimal(c) + Decimal("1"),
                    low=Decimal(c) - Decimal("1"),
                    close=Decimal(c),
                    volume=Decimal("1000000"),
                )
                for i, c in enumerate(closes)
            ),
        )
        for t in ("AAPL", "MSFT")
    )
    request = PortfolioReplayRequest(
        request_id="req-cli",
        starting_cash=Decimal("100000"),
        series=series,
        target_weights=(
            TargetWeight(ticker="AAPL", weight=Decimal("0.4")),
            TargetWeight(ticker="MSFT", weight=Decimal("0.4")),
        ),
        execution=ExecutionPolicy(random_seed=42),
    )
    shared = SharedInputIdentity(
        data_hash=data_hash_from_request(request),
        cost_hash=cost_hash_from_execution(request.execution),
        execution_hash=execution_policy_hash(request.execution),
        random_seed_hash=random_seed_hash(request.execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(request.execution.fill_fraction),
        starting_cash=request.starting_cash,
    )
    dataset_hash = data_hash_from_request(request)
    sources = tuple(
        sorted(
            (
                PolicyVersionRef(
                    family=PolicyFamily.DATA_SOURCE,
                    version_id="bars-v1",
                    content_hash=dataset_hash,
                ),
                PolicyVersionRef(
                    family=PolicyFamily.COST_SCHEDULE,
                    version_id="cost-v1",
                    content_hash=shared.cost_hash,
                ),
            ),
            key=lambda ref: (ref.family.value, ref.version_id),
        )
    )
    manifest_hash = replay_input_manifest_content_hash(
        manifest_id="manifest-cli",
        replay_as_of=_TS,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    manifest = ReplayInputManifest(
        manifest_id="manifest-cli",
        replay_as_of=_TS,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=manifest_hash,
    )

    def _arm(label: ReplayArmLabel, arm_id: str, weights_fp: str) -> ReplayArmSpec:
        bundle = PolicyBundle(
            portfolio_target=PolicyVersionRef(
                family=PolicyFamily.PORTFOLIO_TARGET,
                version_id=f"p-{arm_id}",
                content_hash=sha256_hex({"weights_fingerprint": weights_fp}),
            ),
        )
        return ReplayArmSpec(
            arm=label,
            arm_id=arm_id,
            manifest_content_hash=manifest.manifest_content_hash,
            policy_bundle=bundle,
            weights_fingerprint=weights_fp,
            arm_content_hash=policy_bundle_content_hash(bundle, weights_fingerprint=weights_fp),
        )

    pair = build_replay_pair(
        pair_id="pair-cli",
        shared_manifest=manifest,
        incumbent=_arm(ReplayArmLabel.INCUMBENT, "inc-cli", "w-inc"),
        challenger=_arm(ReplayArmLabel.CHALLENGER, "chl-cli", "w-chl"),
    )
    from digiquant.service import get_policy_replay_store

    store = get_policy_replay_store()
    store.append_manifest(manifest, recorded_at=_TS)
    store.append_pair(pair, recorded_at=_TS)
    return pair.pair_content_hash


def test_cli_run_and_get_replay() -> None:
    pair_hash = _seed_pair()
    runner = CliRunner()
    run_result = runner.invoke(
        policy_replay,
        ["run", "--pair-content-hash", pair_hash, "--run-id", "cli-run-1"],
    )
    assert run_result.exit_code == 0, run_result.output
    payload = json.loads(run_result.output)
    assert payload["run_id"] == "cli-run-1"
    assert payload["status"] == "in_progress"
    assert "fills" not in payload

    get_result = runner.invoke(policy_replay, ["get-replay", "--run-id", "cli-run-1"])
    assert get_result.exit_code == 0, get_result.output
    fetched = json.loads(get_result.output)
    assert fetched["run_id"] == "cli-run-1"


def test_cli_get_replay_fails_closed() -> None:
    runner = CliRunner()
    result = runner.invoke(policy_replay, ["get-replay", "--run-id", f"missing-{uuid4()}"])
    assert result.exit_code != 0
