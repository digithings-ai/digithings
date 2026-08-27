"""WP16.4 — policy-bound shared-cash portfolio replay (#2991).

Connects WP16.3 as-of datasets, policy registry resolution, and walk-forward
fold slicing to the WP10.4 shared-cash Nautilus adapter. One fresh spawned
engine per arm/fold — never ``nautilus_runner._run_multi_symbol_backtest``.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from digiquant.olympus.replay.asof_dataset import AsOfDatasetSnapshot
from digiquant.olympus.replay.models import (
    HoldingQuantity,
    InstrumentBarSeries,
    PortfolioReplayRequest,
    PortfolioReplayResult,
    PortfolioReplayStatus,
    ReplayArmSpec,
    ReplayInputManifest,
    TargetWeight,
    WalkForwardFold,
    inconclusive_result,
)
from digiquant.olympus.replay.nautilus_portfolio import reconcile_portfolio_replay_result
from digiquant.olympus.replay.policy_registry import (
    PolicyRegistry,
    PolicyRegistryError,
    PolicyRegistryMissingError,
    PolicyRegistryUnavailableError,
)
from digiquant.olympus.replay.worker import run_portfolio_replay_isolated

__all__ = [
    "PolicyArmReplayError",
    "build_policy_arm_request",
    "reconcile_portfolio_replay_result",
    "run_policy_arm_replay_isolated",
    "slice_series_for_eval_fold",
]

_MONEY_QUANTUM = Decimal("0.01")
_MIN_EVAL_BARS = 3


class PolicyArmReplayError(RuntimeError):
    """Policy arm request could not be built or validated."""


def slice_series_for_eval_fold(
    series: tuple[InstrumentBarSeries, ...],
    fold: WalkForwardFold,
) -> tuple[InstrumentBarSeries, ...]:
    """Return synchronized bars within ``fold`` eval window (inclusive)."""
    if not series:
        raise PolicyArmReplayError("series must be non-empty")

    reference_stamps = [b.ts for b in series[0].bars]
    for inst in series[1:]:
        stamps = [b.ts for b in inst.bars]
        if stamps != reference_stamps:
            raise PolicyArmReplayError("eval fold slice requires synchronized bar timestamps")

    eval_start = fold.eval_start
    eval_end = fold.eval_end
    keep_indices = [
        i
        for i, ts in enumerate(reference_stamps)
        if eval_start <= ts <= eval_end
    ]
    sliced: list[InstrumentBarSeries] = []
    for inst in series:
        bars = tuple(inst.bars[i] for i in keep_indices)
        sliced.append(InstrumentBarSeries(ticker=inst.ticker, bars=bars))
    return tuple(sliced)


def _targets_from_payload(payload: dict[str, object]) -> tuple[TargetWeight, ...]:
    raw = payload.get("target_weights")
    if not isinstance(raw, list):
        raise PolicyArmReplayError("portfolio_target payload missing target_weights list")
    weights: list[TargetWeight] = []
    for row in raw:
        if not isinstance(row, dict):
            raise PolicyArmReplayError("target_weights entries must be objects")
        ticker = row.get("ticker")
        weight = row.get("weight")
        if not isinstance(ticker, str) or not ticker.strip():
            raise PolicyArmReplayError("target_weights entry missing ticker")
        if weight is None:
            raise PolicyArmReplayError(f"target_weights entry for {ticker!r} missing weight")
        weights.append(TargetWeight(ticker=ticker, weight=Decimal(str(weight))))
    return tuple(sorted(weights, key=lambda t: t.ticker))


def build_policy_arm_request(
    *,
    snapshot: AsOfDatasetSnapshot,
    manifest: ReplayInputManifest,
    arm: ReplayArmSpec,
    registry: PolicyRegistry,
    initial_holdings: tuple[HoldingQuantity, ...] = (),
) -> PortfolioReplayRequest:
    """Build one portfolio replay request from pinned manifest + arm policy."""
    if arm.manifest_content_hash != manifest.manifest_content_hash:
        raise PolicyArmReplayError(
            "arm manifest_content_hash does not match ReplayInputManifest"
        )
    if snapshot.shared != manifest.shared:
        raise PolicyArmReplayError("snapshot shared inputs do not match manifest.shared")

    portfolio_ref = arm.policy_bundle.portfolio_target
    if portfolio_ref is None:
        raise PolicyArmReplayError("arm policy_bundle missing portfolio_target ref")

    try:
        resolved = registry.resolve(
            portfolio_ref,
            replay_as_of=manifest.replay_as_of,
            review_pinned=True,
        )
    except PolicyRegistryUnavailableError as exc:
        raise PolicyArmReplayError(str(exc)) from exc
    except (PolicyRegistryMissingError, PolicyRegistryError) as exc:
        raise PolicyArmReplayError(str(exc)) from exc

    target_weights = _targets_from_payload(resolved.payload)
    series = snapshot.series
    if manifest.fold is not None:
        series = slice_series_for_eval_fold(series, manifest.fold)
        if len(series[0].bars) < _MIN_EVAL_BARS:
            raise PolicyArmReplayError(
                f"eval fold {manifest.fold.fold_id!r} yields {len(series[0].bars)} bars; "
                f"need at least {_MIN_EVAL_BARS} for next-bar execution"
            )

    request_id = f"{arm.arm_id}:{manifest.manifest_id}"
    if manifest.fold is not None:
        request_id = f"{request_id}:{manifest.fold.fold_id}"

    return PortfolioReplayRequest(
        request_id=request_id,
        starting_cash=snapshot.starting_cash,
        series=series,
        target_weights=target_weights,
        initial_holdings=initial_holdings,
        execution=snapshot.execution,
    )


def run_policy_arm_replay_isolated(
    *,
    snapshot: AsOfDatasetSnapshot,
    manifest: ReplayInputManifest,
    arm: ReplayArmSpec,
    registry: PolicyRegistry,
    timeout_s: float = 120.0,
    work_dir: Path | str | None = None,
    initial_holdings: tuple[HoldingQuantity, ...] = (),
) -> PortfolioReplayResult:
    """Spawn one fresh worker for *arm* under *manifest* and return typed result."""
    try:
        request = build_policy_arm_request(
            snapshot=snapshot,
            manifest=manifest,
            arm=arm,
            registry=registry,
            initial_holdings=initial_holdings,
        )
    except PolicyArmReplayError as exc:
        return inconclusive_result(
            request_id=arm.arm_id,
            request_content_hash=arm.arm_content_hash,
            status=PortfolioReplayStatus.ERROR,
            message=str(exc),
            starting_cash=snapshot.starting_cash,
        )

    result = run_portfolio_replay_isolated(
        request,
        timeout_s=timeout_s,
        work_dir=work_dir,
    )
    if result.status == PortfolioReplayStatus.OK:
        reconcile_portfolio_replay_result(result)
    return result
