"""WP16.4 — policy-bound shared-cash portfolio replay (#2991)."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from digiquant.portfolio.allocation_hashes import sha256_hex
from digiquant.dashboard.replay.asof_dataset import (
    VersionedBarSeries,
    build_asof_dataset,
    build_replay_input_manifest,
)
from digiquant.dashboard.replay.canonical import policy_bundle_content_hash
from digiquant.dashboard.replay.models import (
    ExecutionPolicy,
    HoldingQuantity,
    InstrumentBarSeries,
    OhlcvBar,
    PolicyBundle,
    PolicyFamily,
    PolicyVersionRef,
    PortfolioReplayStatus,
    ReplayArmLabel,
    ReplayArmSpec,
    WalkForwardFold,
)
from digiquant.dashboard.replay.policy_portfolio import (
    PolicyArmReplayError,
    build_policy_arm_request,
    reconcile_portfolio_replay_result,
    run_policy_arm_replay_isolated,
    slice_series_for_eval_fold,
)
from digiquant.dashboard.replay.policy_registry import PolicyRegistry, RegisteredPolicyVersion

pytestmark = pytest.mark.unit

_UTC = UTC
_CUTOFF = datetime(2024, 6, 15, 12, 0, tzinfo=_UTC)
_EARLIER = _CUTOFF - timedelta(days=5)

_REPLAY_ROOT = (
    Path(__file__).resolve().parents[3] / "digiquant" / "src" / "digiquant" / "olympus" / "replay"
)


def _bar(day: int, close: str) -> OhlcvBar:
    px = Decimal(close)
    return OhlcvBar(
        ts=datetime(2024, 6, day, tzinfo=_UTC),
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


def _versioned(ticker: str, closes: tuple[str, ...]) -> VersionedBarSeries:
    series = _series(ticker, closes)
    return VersionedBarSeries(
        version_id=f"bars-{ticker}-v1",
        known_at=_EARLIER,
        series=series,
        content_hash=sha256_hex(series.model_dump(mode="json")),
    )


def _portfolio_payload(
    targets: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "mode": "portfolio_target",
        "target_weights": [
            {"ticker": ticker, "weight": weight} for ticker, weight in targets
        ],
    }


def _register_portfolio_policy(
    registry: PolicyRegistry,
    *,
    version_id: str,
    targets: tuple[tuple[str, str], ...],
) -> PolicyVersionRef:
    payload = _portfolio_payload(targets)
    digest = sha256_hex(payload)
    registry.register(
        RegisteredPolicyVersion(
            family=PolicyFamily.PORTFOLIO_TARGET,
            version_id=version_id,
            content_hash=digest,
            known_at=_EARLIER,
            payload=payload,
        ),
    )
    return PolicyVersionRef(
        family=PolicyFamily.PORTFOLIO_TARGET,
        version_id=version_id,
        content_hash=digest,
    )


def _arm_spec(
    *,
    arm: ReplayArmLabel,
    arm_id: str,
    manifest_hash: str,
    weights_fp: str,
    portfolio_ref: PolicyVersionRef,
) -> ReplayArmSpec:
    bundle = PolicyBundle(portfolio_target=portfolio_ref)
    return ReplayArmSpec(
        arm=arm,
        arm_id=arm_id,
        manifest_content_hash=manifest_hash,
        policy_bundle=bundle,
        weights_fingerprint=weights_fp,
        arm_content_hash=policy_bundle_content_hash(bundle, weights_fingerprint=weights_fp),
    )


def _fixture_snapshot_and_manifest(
    *,
    closes: tuple[str, ...] = ("100", "101", "102", "103", "104"),
) -> tuple:
    bars = (
        _versioned("AAPL", closes),
        _versioned("MSFT", closes),
    )
    execution = ExecutionPolicy(commission_rate=Decimal("0.001"), random_seed=7)
    snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=bars,
        execution=execution,
        starting_cash=Decimal("100000"),
    )
    manifest = build_replay_input_manifest(snapshot, manifest_id="m-wp164")
    return snapshot, manifest


def test_slice_series_for_eval_fold_keeps_inclusive_window() -> None:
    series = (
        _series("AAPL", ("100", "101", "102", "103", "104")),
        _series("MSFT", ("200", "201", "202", "203", "204")),
    )
    fold = WalkForwardFold(
        fold_id="fold-1",
        train_start=datetime(2024, 6, 10, tzinfo=_UTC),
        train_end=datetime(2024, 6, 12, tzinfo=_UTC),
        eval_start=datetime(2024, 6, 12, tzinfo=_UTC),
        eval_end=datetime(2024, 6, 13, tzinfo=_UTC),
    )
    sliced = slice_series_for_eval_fold(series, fold)
    assert len(sliced[0].bars) == 2
    assert sliced[0].bars[0].ts == datetime(2024, 6, 12, tzinfo=_UTC)
    assert sliced[0].bars[-1].ts == datetime(2024, 6, 13, tzinfo=_UTC)


def test_build_policy_arm_request_resolves_registered_targets() -> None:
    snapshot, manifest = _fixture_snapshot_and_manifest()
    registry = PolicyRegistry()
    ref = _register_portfolio_policy(
        registry,
        version_id="target-v1",
        targets=(("AAPL", "0.5"), ("MSFT", "0.3")),
    )
    arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="inc-1",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w-inc",
        portfolio_ref=ref,
    )
    request = build_policy_arm_request(
        snapshot=snapshot,
        manifest=manifest,
        arm=arm,
        registry=registry,
    )
    weights = {t.ticker: t.weight for t in request.target_weights}
    assert weights["AAPL"] == Decimal("0.5")
    assert weights["MSFT"] == Decimal("0.3")
    assert request.execution == snapshot.execution
    assert request.starting_cash == snapshot.starting_cash


def test_build_policy_arm_request_rejects_manifest_hash_mismatch() -> None:
    snapshot, manifest = _fixture_snapshot_and_manifest()
    registry = PolicyRegistry()
    ref = _register_portfolio_policy(registry, version_id="t1", targets=(("AAPL", "0.4"),))
    arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="inc",
        manifest_hash="b" * 64,
        weights_fp="w",
        portfolio_ref=ref,
    )
    with pytest.raises(PolicyArmReplayError, match="manifest_content_hash"):
        build_policy_arm_request(
            snapshot=snapshot,
            manifest=manifest,
            arm=arm,
            registry=registry,
        )


def test_build_policy_arm_request_slices_fold_eval_window() -> None:
    closes = ("100", "101", "102", "103", "104")
    snapshot, _manifest = _fixture_snapshot_and_manifest(closes=closes)
    fold = WalkForwardFold(
        fold_id="fold-eval",
        train_start=datetime(2024, 6, 10, tzinfo=_UTC),
        train_end=datetime(2024, 6, 11, tzinfo=_UTC),
        eval_start=datetime(2024, 6, 12, tzinfo=_UTC),
        eval_end=datetime(2024, 6, 14, tzinfo=_UTC),
    )
    manifest = build_replay_input_manifest(snapshot, manifest_id="m-fold", fold=fold)
    registry = PolicyRegistry()
    ref = _register_portfolio_policy(registry, version_id="t1", targets=(("AAPL", "0.4"),))
    arm = _arm_spec(
        arm=ReplayArmLabel.CHALLENGER,
        arm_id="ch-1",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w-ch",
        portfolio_ref=ref,
    )
    request = build_policy_arm_request(
        snapshot=snapshot,
        manifest=manifest,
        arm=arm,
        registry=registry,
    )
    assert len(request.series[0].bars) == 3


def test_reconcile_portfolio_replay_result_ok_on_engine_output(tmp_path) -> None:
    pytest.importorskip("nautilus_trader")
    snapshot, manifest = _fixture_snapshot_and_manifest()
    registry = PolicyRegistry()
    ref = _register_portfolio_policy(
        registry,
        version_id="t1",
        targets=(("AAPL", "0.4"), ("MSFT", "0.4")),
    )
    arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="inc-rec",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w",
        portfolio_ref=ref,
    )
    result = run_policy_arm_replay_isolated(
        snapshot=snapshot,
        manifest=manifest,
        arm=arm,
        registry=registry,
        work_dir=tmp_path,
    )
    assert result.status == PortfolioReplayStatus.OK
    reconcile_portfolio_replay_result(result)


def test_run_policy_arm_replay_isolated_deterministic_per_arm(tmp_path) -> None:
    pytest.importorskip("nautilus_trader")
    snapshot, manifest = _fixture_snapshot_and_manifest()
    registry = PolicyRegistry()
    inc_ref = _register_portfolio_policy(
        registry,
        version_id="inc-t",
        targets=(("AAPL", "0.5"), ("MSFT", "0.3")),
    )
    ch_ref = _register_portfolio_policy(
        registry,
        version_id="ch-t",
        targets=(("AAPL", "0.2"), ("MSFT", "0.6")),
    )
    inc = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="inc",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w-inc",
        portfolio_ref=inc_ref,
    )
    ch = _arm_spec(
        arm=ReplayArmLabel.CHALLENGER,
        arm_id="ch",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w-ch",
        portfolio_ref=ch_ref,
    )
    a = run_policy_arm_replay_isolated(
        snapshot=snapshot,
        manifest=manifest,
        arm=inc,
        registry=registry,
        work_dir=tmp_path / "inc-a",
    )
    b = run_policy_arm_replay_isolated(
        snapshot=snapshot,
        manifest=manifest,
        arm=inc,
        registry=registry,
        work_dir=tmp_path / "inc-b",
    )
    ch_result = run_policy_arm_replay_isolated(
        snapshot=snapshot,
        manifest=manifest,
        arm=ch,
        registry=registry,
        work_dir=tmp_path / "ch",
    )
    assert a.status == b.status == PortfolioReplayStatus.OK
    assert a.result_content_hash == b.result_content_hash
    assert ch_result.status == PortfolioReplayStatus.OK
    assert ch_result.result_content_hash != a.result_content_hash


def test_run_policy_arm_replay_hold_add_trim_exit_noop_partial(tmp_path) -> None:
    pytest.importorskip("nautilus_trader")
    closes = ("100", "101", "102", "103", "104")
    snapshot, manifest = _fixture_snapshot_and_manifest(closes=closes)
    registry = PolicyRegistry()

    def _run(
        targets: tuple[tuple[str, str], ...],
        arm_id: str,
        *,
        initial: tuple[HoldingQuantity, ...] = (),
    ):
        ref = _register_portfolio_policy(registry, version_id=f"t-{arm_id}", targets=targets)
        arm = _arm_spec(
            arm=ReplayArmLabel.INCUMBENT,
            arm_id=arm_id,
            manifest_hash=manifest.manifest_content_hash,
            weights_fp=arm_id,
            portfolio_ref=ref,
        )
        request = build_policy_arm_request(
            snapshot=snapshot,
            manifest=manifest,
            arm=arm,
            registry=registry,
            initial_holdings=initial,
        )
        from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

        return run_portfolio_replay_isolated(request, work_dir=tmp_path / arm_id)

    hold = _run(
        (("AAPL", "0.4"), ("MSFT", "0.4")),
        "hold",
        initial=(HoldingQuantity(ticker="AAPL", quantity=Decimal("100")),),
    )
    assert hold.status == PortfolioReplayStatus.OK

    add = _run((("AAPL", "0.6"), ("MSFT", "0.2")), "add")
    assert any(f.side == "BUY" and f.ticker == "AAPL" and not f.is_seed for f in add.fills)

    trim = _run((("AAPL", "0.2"), ("MSFT", "0.2")), "trim")
    assert trim.status == PortfolioReplayStatus.OK

    exit_ = _run((("AAPL", "0.0"),), "exit")
    assert exit_.status == PortfolioReplayStatus.OK

    noop = _run((), "noop")
    assert noop.ending_nav == Decimal("100000.00")

    partial_snapshot = build_asof_dataset(
        replay_as_of=_CUTOFF,
        bar_versions=(
            _versioned("AAPL", closes),
            _versioned("MSFT", closes),
        ),
        execution=ExecutionPolicy(
            commission_rate=Decimal("0"),
            fill_fraction=Decimal("0.5"),
        ),
        starting_cash=Decimal("100000"),
    )
    partial_manifest = build_replay_input_manifest(partial_snapshot, manifest_id="m-partial")
    partial_arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="partial",
        manifest_hash=partial_manifest.manifest_content_hash,
        weights_fp="partial",
        portfolio_ref=_register_portfolio_policy(
            registry,
            version_id="partial-t",
            targets=(("AAPL", "0.8"), ("MSFT", "0.0")),
        ),
    )
    partial_req = build_policy_arm_request(
        snapshot=partial_snapshot,
        manifest=partial_manifest,
        arm=partial_arm,
        registry=registry,
    )
    from digiquant.dashboard.replay.worker import run_portfolio_replay_isolated

    partial = run_portfolio_replay_isolated(partial_req, work_dir=tmp_path / "partial")
    full = _run((("AAPL", "0.8"), ("MSFT", "0.0")), "full")
    p_qty = next(h.quantity for h in partial.holdings if h.ticker == "AAPL")
    f_qty = next(h.quantity for h in full.holdings if h.ticker == "AAPL")
    assert p_qty < f_qty


def test_unavailable_portfolio_policy_fails_closed(tmp_path) -> None:
    registry = PolicyRegistry()
    payload = {"status": "unavailable", "reason": "no_targets"}
    digest = sha256_hex(payload)
    registry.register(
        RegisteredPolicyVersion(
            family=PolicyFamily.PORTFOLIO_TARGET,
            version_id="missing",
            content_hash=digest,
            known_at=_EARLIER,
            payload=payload,
        ),
    )
    snapshot, manifest = _fixture_snapshot_and_manifest()
    ref = PolicyVersionRef(
        family=PolicyFamily.PORTFOLIO_TARGET,
        version_id="missing",
        content_hash=digest,
    )
    arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="bad",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="bad",
        portfolio_ref=ref,
    )
    result = run_policy_arm_replay_isolated(
        snapshot=snapshot,
        manifest=manifest,
        arm=arm,
        registry=registry,
        work_dir=tmp_path,
    )
    assert result.status == PortfolioReplayStatus.ERROR
    assert "no_targets" in result.message
    assert result.ending_nav is None


def test_reconcile_rejects_inconsistent_nav() -> None:
    from digiquant.dashboard.replay.models import (
        HoldingSnapshot,
        PortfolioReplayResult,
        portfolio_replay_result_content_hash,
    )

    draft = PortfolioReplayResult.model_construct(
        schema_version="1.0",
        request_id="bad",
        request_content_hash="a" * 64,
        status=PortfolioReplayStatus.OK,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("50000"),
        ending_nav=Decimal("99999"),
        total_commission=Decimal("0"),
        rebalance_commission=Decimal("0"),
        holdings=(
            HoldingSnapshot(
                ticker="AAPL",
                quantity=Decimal("100"),
                last_price=Decimal("100"),
                market_value=Decimal("10000"),
            ),
        ),
        fills=(),
        nav_path=(),
        message="synthetic",
        result_content_hash="0" * 64,
    )
    digest = portfolio_replay_result_content_hash(draft)
    bad = PortfolioReplayResult(
        request_id="bad",
        request_content_hash="a" * 64,
        status=PortfolioReplayStatus.OK,
        starting_cash=Decimal("100000"),
        ending_cash=Decimal("50000"),
        ending_nav=Decimal("99999"),
        total_commission=Decimal("0"),
        rebalance_commission=Decimal("0"),
        holdings=draft.holdings,
        fills=(),
        nav_path=(),
        message="synthetic",
        result_content_hash=digest,
    )
    with pytest.raises(ValueError, match="ending_nav"):
        reconcile_portfolio_replay_result(bad)


def test_reconcile_failure_returns_typed_error(tmp_path) -> None:
    pytest.importorskip("nautilus_trader")
    from unittest.mock import patch

    snapshot, manifest = _fixture_snapshot_and_manifest()
    registry = PolicyRegistry()
    ref = _register_portfolio_policy(
        registry,
        version_id="t1",
        targets=(("AAPL", "0.4"), ("MSFT", "0.4")),
    )
    arm = _arm_spec(
        arm=ReplayArmLabel.INCUMBENT,
        arm_id="reconcile-fail",
        manifest_hash=manifest.manifest_content_hash,
        weights_fp="w",
        portfolio_ref=ref,
    )
    with patch(
        "digiquant.dashboard.replay.policy_portfolio.reconcile_portfolio_replay_result",
        side_effect=ValueError("synthetic reconcile failure"),
    ):
        result = run_policy_arm_replay_isolated(
            snapshot=snapshot,
            manifest=manifest,
            arm=arm,
            registry=registry,
            work_dir=tmp_path,
        )
    assert result.status == PortfolioReplayStatus.ERROR
    assert "reconcile failed" in result.message
    assert result.ending_nav is None


def test_policy_portfolio_never_calls_multi_symbol_runner() -> None:
    for name in ("policy_portfolio.py", "nautilus_portfolio.py"):
        tree = ast.parse((_REPLAY_ROOT / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "nautilus_runner" not in node.module
            elif isinstance(node, ast.Call):
                func = node.func
                call_name = getattr(func, "attr", None) or getattr(func, "id", None)
                assert call_name != "_run_multi_symbol_backtest"


def test_fold_slice_requires_synchronized_timestamps() -> None:
    series = (
        _series("AAPL", ("100", "101", "102")),
        InstrumentBarSeries(
            ticker="MSFT",
            bars=(
                _bar(20, "200"),
                _bar(21, "201"),
                _bar(22, "202"),
            ),
        ),
    )
    fold = WalkForwardFold(
        fold_id="f",
        train_start=datetime(2024, 6, 10, tzinfo=_UTC),
        train_end=datetime(2024, 6, 11, tzinfo=_UTC),
        eval_start=datetime(2024, 6, 11, tzinfo=_UTC),
        eval_end=datetime(2024, 6, 12, tzinfo=_UTC),
    )
    with pytest.raises(PolicyArmReplayError, match="synchronized"):
        slice_series_for_eval_fold(series, fold)
