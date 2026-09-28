from pathlib import Path

from digiquant.strategies.sdca.periodic_cycle_state import (
    CycleState,
    load_cycle_state,
    save_cycle_state,
)


class TestCycleStateRoundTrip:
    def test_missing_file_returns_fresh_state_with_full_pool(self, tmp_path: Path) -> None:
        state = load_cycle_state(tmp_path / "periodic_cycle_state.json")
        assert state.cycle_count == 0
        assert state.next_cycle_type == "ablation"
        assert len(state.ablation_pool_remaining) == 17
        assert state.best_seen is None

    def test_save_then_load_round_trips_exactly(self, tmp_path: Path) -> None:
        path = tmp_path / "periodic_cycle_state.json"
        original = CycleState(
            cycle_count=3,
            next_cycle_type="curve",
            ablation_pool_remaining=("power_law", "m2", "dxy"),
            best_seen={"duration_weighted_oos_pct": 52.01, "beats_flat_dca_oos": True},
        )
        save_cycle_state(path, original)
        reloaded = load_cycle_state(path)
        assert reloaded == original

    def test_pool_below_two_resets_to_full_surviving_indicators(self, tmp_path: Path) -> None:
        path = tmp_path / "periodic_cycle_state.json"
        save_cycle_state(
            path,
            CycleState(
                cycle_count=5,
                next_cycle_type="ablation",
                ablation_pool_remaining=("power_law",),
                best_seen=None,
            ),
        )
        state = load_cycle_state(path)
        assert len(state.ablation_pool_remaining) == 17  # reset, not left at 1
