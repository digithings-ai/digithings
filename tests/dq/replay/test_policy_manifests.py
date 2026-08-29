"""WP16.1 — policy replay manifests and canonical hashing (#2979)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.olympus.hermes.allocation_hashes import sha256_hex
from digiquant.olympus.replay.canonical import (
    cost_hash_from_execution,
    data_hash_from_request,
    execution_policy_hash,
    fill_fraction_hash,
    policy_bundle_content_hash,
    random_seed_hash,
    replay_input_manifest_content_hash,
    replay_pair_content_hash,
    walk_forward_fold_content_hash,
)
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
    ReplayPairSpec,
    SharedInputIdentity,
    TargetWeight,
    WalkForwardFold,
    build_replay_pair,
)

pytestmark = pytest.mark.unit

_UTC = timezone.utc
_REPO = Path(__file__).resolve().parents[3]
_SRC = str(_REPO / "digiquant" / "src")


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 1, day, tzinfo=_UTC),
        open=px,
        high=px + Decimal("1"),
        low=px - Decimal("1"),
        close=px,
        volume=Decimal("1000000"),
    )


def _series(ticker: str, closes: list[str]) -> InstrumentBarSeries:
    return InstrumentBarSeries(
        ticker=ticker,
        bars=tuple(_bar(i + 2, c) for i, c in enumerate(closes)),
    )


def _request(
    *,
    request_id: str = "req-1",
    targets: tuple[tuple[str, str], ...] = (("AAPL", "0.4"), ("MSFT", "0.4")),
    starting_cash: str = "100000",
    seed: int = 42,
    commission: str = "0",
    fill: str = "1",
    closes_override: tuple[str, str, str] | None = None,
) -> PortfolioReplayRequest:
    closes = list(closes_override or ("100", "101", "102"))
    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=Decimal(starting_cash),
        series=(
            _series("AAPL", closes),
            _series("MSFT", closes),
        ),
        target_weights=tuple(
            TargetWeight(ticker=ticker, weight=Decimal(weight)) for ticker, weight in targets
        ),
        execution=ExecutionPolicy(
            commission_rate=Decimal(commission),
            fill_fraction=Decimal(fill),
            random_seed=seed,
        ),
    )


def _policy_ref(
    family: PolicyFamily,
    version_id: str,
    content_hash: str = "a" * 64,
) -> PolicyVersionRef:
    return PolicyVersionRef(
        family=family,
        version_id=version_id,
        content_hash=content_hash,
    )


def _shared_identity(request: PortfolioReplayRequest) -> SharedInputIdentity:
    execution = request.execution
    return SharedInputIdentity(
        data_hash=data_hash_from_request(request),
        cost_hash=cost_hash_from_execution(execution),
        execution_hash=execution_policy_hash(execution),
        random_seed_hash=random_seed_hash(execution.random_seed),
        fill_fraction_hash=fill_fraction_hash(execution.fill_fraction),
        starting_cash=request.starting_cash,
    )


def _manifest(
    request: PortfolioReplayRequest,
    *,
    manifest_id: str = "manifest-1",
    replay_as_of: datetime | None = None,
) -> ReplayInputManifest:
    replay_as_of = replay_as_of or datetime(2024, 1, 2, tzinfo=_UTC)
    shared = _shared_identity(request)
    dataset_hash = data_hash_from_request(request)
    sources = tuple(
        sorted(
            (
                _policy_ref(PolicyFamily.DATA_SOURCE, "bars-v1", dataset_hash),
                _policy_ref(PolicyFamily.COST_SCHEDULE, "cost-v1", shared.cost_hash),
            ),
            key=lambda ref: (ref.family.value, ref.version_id),
        )
    )
    content_hash = replay_input_manifest_content_hash(
        manifest_id=manifest_id,
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        fold=None,
    )
    return ReplayInputManifest(
        manifest_id=manifest_id,
        replay_as_of=replay_as_of,
        shared=shared,
        source_refs=sources,
        dataset_content_hash=dataset_hash,
        manifest_content_hash=content_hash,
    )


def _arm(
    arm: ReplayArmLabel,
    manifest: ReplayInputManifest,
    *,
    arm_id: str,
    weights_fp: str,
    portfolio_version: str,
) -> ReplayArmSpec:
    bundle = PolicyBundle(
        portfolio_target=_policy_ref(
            PolicyFamily.PORTFOLIO_TARGET,
            portfolio_version,
            content_hash=sha256_hex({"weights_fingerprint": weights_fp}),
        ),
    )
    return ReplayArmSpec(
        arm=arm,
        arm_id=arm_id,
        manifest_content_hash=manifest.manifest_content_hash,
        policy_bundle=bundle,
        weights_fingerprint=weights_fp,
        arm_content_hash=policy_bundle_content_hash(bundle, weights_fingerprint=weights_fp),
    )


def test_policy_version_ref_rejects_path_like_id() -> None:
    with pytest.raises(ValueError, match="version_id"):
        _policy_ref(PolicyFamily.RESEARCH_PLAN, "/tmp/evil.pickle")


def test_policy_version_ref_rejects_unknown_family_string() -> None:
    with pytest.raises((ValueError, TypeError)):
        PolicyVersionRef(
            family="arbitrary_import",
            version_id="v1",
            content_hash="a" * 64,
        )


def test_shared_input_hash_changes_on_data_cost_seed_fill_cash() -> None:
    base = _request()
    base_shared = _shared_identity(base)

    other_data = _shared_identity(_request(closes_override=("200", "201", "202")))
    assert other_data.data_hash != base_shared.data_hash

    other_cost = _shared_identity(_request(commission="0.001"))
    assert other_cost.cost_hash != base_shared.cost_hash

    other_seed = _shared_identity(_request(seed=99))
    assert other_seed.random_seed_hash != base_shared.random_seed_hash

    other_fill = _shared_identity(_request(fill="0.5"))
    assert other_fill.fill_fraction_hash != base_shared.fill_fraction_hash

    other_cash = _shared_identity(_request(starting_cash="200000"))
    assert other_cash.starting_cash != base_shared.starting_cash


def test_manifest_hash_stable_cross_process() -> None:
    request = _request()
    manifest = _manifest(request)
    payload = {
        "manifest_id": manifest.manifest_id,
        "replay_as_of": manifest.replay_as_of.isoformat(),
        "shared": manifest.shared.model_dump(mode="json"),
        "refs": [ref.model_dump(mode="json") for ref in manifest.source_refs],
        "dataset_hash": manifest.dataset_content_hash,
    }
    encoded = json.dumps(payload, sort_keys=True)
    script = (
        "import json,sys;"
        "from datetime import datetime;"
        "from digiquant.olympus.replay.canonical import replay_input_manifest_content_hash;"
        "from digiquant.olympus.replay.models import PolicyVersionRef, SharedInputIdentity;"
        "p=json.loads(sys.argv[1]);"
        "shared=SharedInputIdentity(**p['shared']);"
        "refs=tuple(PolicyVersionRef(**r) for r in p['refs']);"
        "h=replay_input_manifest_content_hash("
        "manifest_id=p['manifest_id'],"
        "replay_as_of=datetime.fromisoformat(p['replay_as_of']),"
        "shared=shared,"
        "source_refs=refs,"
        "dataset_content_hash=p['dataset_hash'],"
        "fold=None);"
        "print(h)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script, encoded],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": _SRC},
    )
    assert proc.stdout.strip() == manifest.manifest_content_hash


def test_pair_requires_identical_shared_manifest() -> None:
    incumbent_req = _request()
    challenger_req = _request(
        request_id="req-2",
        closes_override=("110", "111", "112"),
    )
    incumbent_manifest = _manifest(incumbent_req, manifest_id="m-inc")
    challenger_manifest = _manifest(challenger_req, manifest_id="m-ch")

    incumbent_arm = _arm(
        ReplayArmLabel.INCUMBENT,
        incumbent_manifest,
        arm_id="inc",
        weights_fp="w-inc",
        portfolio_version="incumbent@v1",
    )
    challenger_arm = _arm(
        ReplayArmLabel.CHALLENGER,
        challenger_manifest,
        arm_id="ch",
        weights_fp="w-ch",
        portfolio_version="challenger@v1",
    )

    with pytest.raises(ValueError, match="identical shared manifest"):
        ReplayPairSpec(
            pair_id="pair-1",
            shared_manifest=incumbent_manifest,
            incumbent=incumbent_arm,
            challenger=challenger_arm,
            pair_content_hash=replay_pair_content_hash(
                pair_id="pair-1",
                shared_manifest=incumbent_manifest,
                incumbent=incumbent_arm,
                challenger=challenger_arm,
            ),
        )


def test_pair_allows_only_declared_policy_differences() -> None:
    request = _request()
    manifest = _manifest(request)
    incumbent_arm = _arm(
        ReplayArmLabel.INCUMBENT,
        manifest,
        arm_id="inc",
        weights_fp="w-inc",
        portfolio_version="incumbent@v1",
    )
    challenger_arm = _arm(
        ReplayArmLabel.CHALLENGER,
        manifest,
        arm_id="ch",
        weights_fp="w-ch",
        portfolio_version="challenger@v1",
    )
    pair = build_replay_pair(
        pair_id="pair-ok",
        shared_manifest=manifest,
        incumbent=incumbent_arm,
        challenger=challenger_arm,
    )
    assert pair.incumbent.policy_bundle != pair.challenger.policy_bundle
    assert pair.incumbent.manifest_content_hash == pair.challenger.manifest_content_hash


def test_pair_construction_rejects_unequal_shared_inputs() -> None:
    request = _request()
    manifest = _manifest(request)
    bad_incumbent = _arm(
        ReplayArmLabel.INCUMBENT,
        manifest,
        arm_id="inc",
        weights_fp="w-inc",
        portfolio_version="incumbent@v1",
    )
    other_manifest = _manifest(_request(starting_cash="50000"), manifest_id="other")
    bad_challenger = _arm(
        ReplayArmLabel.CHALLENGER,
        other_manifest,
        arm_id="ch",
        weights_fp="w-ch",
        portfolio_version="challenger@v1",
    )
    with pytest.raises(ValueError, match="identical shared manifest"):
        build_replay_pair(
            pair_id="pair-bad",
            shared_manifest=manifest,
            incumbent=bad_incumbent,
            challenger=bad_challenger,
        )


def test_walk_forward_fold_hash_stable_and_utc_required() -> None:
    fold = WalkForwardFold(
        fold_id="fold-1",
        train_start=datetime(2023, 1, 1, tzinfo=_UTC),
        train_end=datetime(2023, 6, 30, tzinfo=_UTC),
        eval_start=datetime(2023, 7, 1, tzinfo=_UTC),
        eval_end=datetime(2023, 12, 31, tzinfo=_UTC),
        embargo_days=5,
        purge_horizon_days=21,
    )
    h1 = walk_forward_fold_content_hash(fold)
    h2 = walk_forward_fold_content_hash(fold)
    assert h1 == h2
    assert len(h1) == 64

    with pytest.raises(ValueError, match="timezone-aware UTC"):
        WalkForwardFold(
            fold_id="fold-bad",
            train_start=datetime(2023, 1, 1),  # noqa: DTZ001 — intentional naive for rejection test
            train_end=datetime(2023, 6, 30, tzinfo=_UTC),
            eval_start=datetime(2023, 7, 1, tzinfo=_UTC),
            eval_end=datetime(2023, 12, 31, tzinfo=_UTC),
        )


def test_models_are_strict_and_frozen() -> None:
    ref = _policy_ref(PolicyFamily.DATA_SOURCE, "bars-v1")
    with pytest.raises(Exception):
        ref.version_id = "mutated"
