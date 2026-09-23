"""Iterative-ablation round loop (SDCA post-mortem follow-up, Phase 4).

Chris's own hypothesis: reweight the full indicator pool, drop whichever
indicator comes out dominant, re-run, repeat -- specifically to test whether
``power_law`` + ``m2`` + ``dxy`` work well together once ``power_law``'s
search-dominance (a real crossing-bug artifact, fixed in ``quantile_rails``)
is accounted for.

This module is the pure, dependency-injected round loop -- mirrors
``stage_a.py``'s own pure/testable design. The heavy real-data wiring
(parallel-worker reweight dispatch for large pools, the feasibility-aware
curve search, one walk-forward pass) belongs in the driver script,
``scripts/run_iterative_ablation.py``, which supplies ``reweight_fn`` and
``gate_fn`` below.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .indicator_catalog import SdcaCompositeWeights
from .walk_forward import SENSITIVITY_SPIKE_PCT

MAX_ROUNDS = 8
STALL_ROUNDS = 2

# Every droppable pool member: power_law plus every SdcaCompositeWeights
# extra field. A freshly-constructed default instance is always valid
# (power_law=1.0 alone satisfies "at least one weight positive"), so this
# needs no try/except.
_POOL_NAMES: frozenset[str] = frozenset({"power_law", *dict(SdcaCompositeWeights().extra_items())})

ReweightFn = Callable[[tuple[str, ...]], SdcaCompositeWeights]
GateFn = Callable[[tuple[str, ...], SdcaCompositeWeights], tuple[float, float]]

StopReason = Literal["pool_exhausted", "stalled", "budget_exhausted"]


def _weight_for_name(weights: SdcaCompositeWeights, name: str) -> float:
    if name == "power_law":
        return weights.power_law
    return dict(weights.extra_items())[name]


def _validate_pool(pool: tuple[str, ...]) -> None:
    unknown = set(pool) - _POOL_NAMES
    if unknown:
        raise ValueError(f"unknown indicator name(s) in pool: {sorted(unknown)}")


class AblationRoundResult(BaseModel):
    """One round's outcome. ``pool`` is the pool *before* dropping ``dominant_indicator``."""

    model_config = ConfigDict(frozen=True, strict=True)

    round_index: int
    pool: tuple[str, ...]
    weights: SdcaCompositeWeights
    dominant_indicator: str
    dominant_weight: float
    mean_oos_vs_flat_dca_pct_unweighted: float
    mean_oos_vs_flat_dca_pct_duration_weighted: float


class AblationRunResult(BaseModel):
    """The reported result is ``best_round`` (best duration-weighted OOS seen),
    not necessarily ``rounds[-1]`` -- the loop can run past its peak before a
    stall or the budget ceiling stops it."""

    model_config = ConfigDict(frozen=True, strict=True)

    rounds: tuple[AblationRoundResult, ...]
    best_round: AblationRoundResult
    stop_reason: StopReason


def run_ablation_rounds(
    initial_pool: Sequence[str],
    *,
    reweight_fn: ReweightFn,
    gate_fn: GateFn,
    max_rounds: int = MAX_ROUNDS,
    stall_rounds: int = STALL_ROUNDS,
    stall_threshold_pct: float = SENSITIVITY_SPIKE_PCT,
    on_round: Callable[[AblationRoundResult], None] | None = None,
) -> AblationRunResult:
    """Reweight, identify the dominant indicator, drop it, repeat.

    ``reweight_fn(pool)`` returns the current pool's best weights (the driver
    dispatches this to a parallel worker scan for large pools, or a direct
    ``optimize_stage_a_weights_combined_multi_ratio`` call once the pool is
    small). The dominant indicator is the argmax of ``reweight_fn``'s
    *continuous* weights over ``pool`` -- ``power_law`` included, since
    fixing the quantile-rails crossing bug may reveal its dominance was
    partly an artifact.

    ``gate_fn(pool, weights)`` returns
    ``(mean_oos_vs_flat_dca_pct_unweighted, mean_oos_vs_flat_dca_pct_duration_weighted)``
    for the fast per-round sanity gate (the driver wires this to a reduced
    ``search_wide_knee_curve_feasibility_aware`` + one ``run_sdca_walk_forward``
    pass).

    Stops when the pool drops below 2 names, when the duration-weighted OOS
    fails to improve by more than ``stall_threshold_pct`` for
    ``stall_rounds`` consecutive rounds (an improvement check, not a
    reproduction of ``walk_forward.sensitivity_neighbors`` -- any decrease
    counts as a non-improvement), or after ``max_rounds`` rounds.

    ``on_round``, when given, is called with each round's result immediately
    after it's computed (before the stop check) -- the driver uses this to
    write ``.scratch/ablation/round_{n}.json`` as the run progresses, so the
    dominant-indicator trend is visible round-over-round rather than only
    once the whole run finishes.
    """
    pool = tuple(dict.fromkeys(initial_pool))
    _validate_pool(pool)
    if len(pool) < 2:
        raise ValueError("initial pool must have at least 2 indicators")

    rounds: list[AblationRoundResult] = []
    stall_count = 0
    stop_reason: StopReason = "budget_exhausted"

    for round_index in range(1, max_rounds + 1):
        weights = reweight_fn(pool)
        dominant = max(pool, key=lambda name: _weight_for_name(weights, name))
        dominant_weight = _weight_for_name(weights, dominant)
        unweighted_oos, duration_oos = gate_fn(pool, weights)

        if rounds:
            improvement = duration_oos - rounds[-1].mean_oos_vs_flat_dca_pct_duration_weighted
            stall_count = stall_count + 1 if improvement <= stall_threshold_pct else 0

        round_result = AblationRoundResult(
            round_index=round_index,
            pool=pool,
            weights=weights,
            dominant_indicator=dominant,
            dominant_weight=dominant_weight,
            mean_oos_vs_flat_dca_pct_unweighted=unweighted_oos,
            mean_oos_vs_flat_dca_pct_duration_weighted=duration_oos,
        )
        rounds.append(round_result)
        if on_round is not None:
            on_round(round_result)

        if stall_count >= stall_rounds:
            stop_reason = "stalled"
            break

        pool = tuple(name for name in pool if name != dominant)
        if len(pool) < 2:
            stop_reason = "pool_exhausted"
            break
    else:
        stop_reason = "budget_exhausted"

    best_round = max(rounds, key=lambda r: r.mean_oos_vs_flat_dca_pct_duration_weighted)
    return AblationRunResult(rounds=tuple(rounds), best_round=best_round, stop_reason=stop_reason)
