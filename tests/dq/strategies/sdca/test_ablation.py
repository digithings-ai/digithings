"""Iterative-ablation round loop (SDCA post-mortem follow-up, Phase 4)."""

from __future__ import annotations

import pytest
from digiquant.strategies.sdca.ablation import (
    AblationRoundResult,
    AblationRunResult,
    run_ablation_rounds,
)
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights

pytestmark = pytest.mark.unit


def _weights_favoring(pool: tuple[str, ...], dominant: str) -> SdcaCompositeWeights:
    """A weights object where ``dominant`` is the clear argmax over ``pool``;
    every name outside ``pool`` (already dropped, or never in it) is zeroed."""
    kwargs: dict[str, float] = {"power_law": 0.0}
    for name in pool:
        kwargs[name] = 0.9 if name == dominant else 0.1
    return SdcaCompositeWeights(**kwargs)


def _front_runner_reweight(pool: tuple[str, ...]) -> SdcaCompositeWeights:
    """Deterministic stand-in for a real reweight: the pool's first (surviving)
    member is always dominant, so successive rounds retire the initial pool
    order one name at a time."""
    return _weights_favoring(pool, pool[0])


def _constant_gate(oos: float) -> callable:
    def gate_fn(pool: tuple[str, ...], weights: SdcaCompositeWeights) -> tuple[float, float]:
        return oos, oos

    return gate_fn


def _sequence_gate(values: list[tuple[float, float]]) -> callable:
    """Returns each ``(unweighted, duration)`` pair in order, one per call."""
    calls = {"n": 0}

    def gate_fn(pool: tuple[str, ...], weights: SdcaCompositeWeights) -> tuple[float, float]:
        pair = values[calls["n"]]
        calls["n"] += 1
        return pair

    return gate_fn


class TestRunAblationRounds:
    def test_drops_dominant_each_round_in_pool_order(self) -> None:
        pool = ("power_law", "m2", "dxy", "weekly_rsi", "sma_band")
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(10.0, 10.0), (20.0, 20.0), (30.0, 30.0)]),
            max_rounds=3,
        )
        assert isinstance(result, AblationRunResult)
        assert [r.dominant_indicator for r in result.rounds] == ["power_law", "m2", "dxy"]
        # Each round's `pool` is the pool *before* dropping that round's dominant.
        assert result.rounds[0].pool == pool
        assert result.rounds[1].pool == ("m2", "dxy", "weekly_rsi", "sma_band")
        assert result.rounds[2].pool == ("dxy", "weekly_rsi", "sma_band")
        assert result.rounds[0].dominant_weight == pytest.approx(0.9)
        assert result.stop_reason == "budget_exhausted"

    def test_unweighted_and_duration_weighted_oos_land_in_distinct_fields(self) -> None:
        pool = ("power_law", "m2", "dxy")
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(5.0, 9.0)]),
            max_rounds=1,
        )
        round0 = result.rounds[0]
        assert round0.mean_oos_vs_flat_dca_pct_unweighted == pytest.approx(5.0)
        assert round0.mean_oos_vs_flat_dca_pct_duration_weighted == pytest.approx(9.0)

    def test_stops_when_pool_drops_below_two(self) -> None:
        pool = ("power_law", "m2", "dxy")
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_constant_gate(10.0),
            max_rounds=8,
        )
        # 3 names -> drop 1/round; after round 2 only "dxy" is left (< 2).
        assert result.stop_reason == "pool_exhausted"
        assert len(result.rounds) == 2
        assert [r.dominant_indicator for r in result.rounds] == ["power_law", "m2"]

    def test_stops_after_two_consecutive_non_improving_rounds(self) -> None:
        pool = ("power_law", "m2", "dxy", "weekly_rsi", "sma_band")
        # round1=50 (baseline, no comparison yet); round2=50.5 (+0.5, below the
        # 2.0pp noise threshold -> non-improvement #1); round3=50.9 (+0.4,
        # non-improvement #2) -> stop, even though the pool still has room.
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(50.0, 50.0), (50.5, 50.5), (50.9, 50.9)]),
            max_rounds=8,
        )
        assert result.stop_reason == "stalled"
        assert len(result.rounds) == 3

    def test_stops_at_round_budget_when_always_improving(self) -> None:
        pool = ("power_law", "m2", "dxy", "weekly_rsi", "sma_band")
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(float(10 * n), float(10 * n)) for n in range(1, 4)]),
            max_rounds=3,
        )
        assert result.stop_reason == "budget_exhausted"
        assert len(result.rounds) == 3

    def test_best_round_is_best_seen_not_last(self) -> None:
        pool = ("power_law", "m2", "dxy", "weekly_rsi", "sma_band")
        # Peaks at round 2 (50.0), then two consecutive declines stall the loop
        # at round 4 -- the reported best round must be round 2, not round 4.
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(10.0, 10.0), (50.0, 50.0), (20.0, 20.0), (15.0, 15.0)]),
            max_rounds=8,
        )
        assert result.stop_reason == "stalled"
        assert len(result.rounds) == 4
        assert result.best_round.round_index == 2
        assert result.best_round.mean_oos_vs_flat_dca_pct_duration_weighted == pytest.approx(50.0)
        assert result.best_round is not result.rounds[-1]

    def test_dominant_indicator_can_be_power_law(self) -> None:
        """power_law is itself a droppable pool member (Chris's own hypothesis:
        fixing the crossing bug may reveal its dominance was partly artifact)."""
        pool = ("power_law", "m2")
        result = run_ablation_rounds(
            pool,
            reweight_fn=lambda p: _weights_favoring(p, "power_law"),
            gate_fn=_constant_gate(0.0),
            max_rounds=8,
        )
        assert result.rounds[0].dominant_indicator == "power_law"
        assert result.stop_reason == "pool_exhausted"
        assert len(result.rounds) == 1

    def test_rejects_unknown_indicator_name(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            run_ablation_rounds(
                ("power_law", "not_a_real_indicator"),
                reweight_fn=_front_runner_reweight,
                gate_fn=_constant_gate(0.0),
            )

    def test_rejects_pool_smaller_than_two(self) -> None:
        with pytest.raises(ValueError, match="at least 2"):
            run_ablation_rounds(
                ("power_law",),
                reweight_fn=_front_runner_reweight,
                gate_fn=_constant_gate(0.0),
            )

    def test_on_round_hook_fires_once_per_round_before_stop_check(self) -> None:
        pool = ("power_law", "m2", "dxy")
        seen: list[int] = []
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_sequence_gate([(10.0, 10.0), (20.0, 20.0)]),
            max_rounds=2,
            on_round=lambda r: seen.append(r.round_index),
        )
        assert seen == [1, 2]
        assert seen == [r.round_index for r in result.rounds]

    def test_round_result_is_frozen_and_typed(self) -> None:
        pool = ("power_law", "m2")
        result = run_ablation_rounds(
            pool,
            reweight_fn=_front_runner_reweight,
            gate_fn=_constant_gate(0.0),
        )
        round0 = result.rounds[0]
        assert isinstance(round0, AblationRoundResult)
        with pytest.raises(Exception):
            round0.dominant_indicator = "m2"  # frozen model
