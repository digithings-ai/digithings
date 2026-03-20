"""Unit tests for strategy_specs: param grid, aliases, grid cap."""

from __future__ import annotations

import random

import pytest

from digiquant.strategy_specs import (
    MAX_GRID_SIZE,
    _resolve_strategy_name,
    get_param_specs,
    get_search_space_for_optuna,
    infer_param_grid,
    sample_random_params,
)


@pytest.mark.unit
class TestResolveStrategyName:
    def test_canonical_unchanged(self) -> None:
        assert _resolve_strategy_name("ema_cross") == "ema_cross"

    def test_alias_ema_resolves(self) -> None:
        assert _resolve_strategy_name("ema") == "ema_cross"

    def test_alias_momentum_tech_resolves(self) -> None:
        assert _resolve_strategy_name("momentum_tech") == "ema_cross"

    def test_alias_mean_reversion_stat_arb_resolves(self) -> None:
        assert _resolve_strategy_name("mean_reversion_stat_arb") == "bollinger_mr"

    def test_alias_momentum_energy_resolves(self) -> None:
        assert _resolve_strategy_name("momentum_energy") == "rsi_momentum"

    def test_unknown_passthrough(self) -> None:
        assert _resolve_strategy_name("unknown_xyz") == "unknown_xyz"


@pytest.mark.unit
class TestGetParamSpecs:
    def test_ema_cross_has_expected_params(self) -> None:
        specs = get_param_specs("ema_cross")
        assert "fast_ema_period" in specs
        assert "slow_ema_period" in specs

    def test_bollinger_mr_has_expected_params(self) -> None:
        specs = get_param_specs("bollinger_mr")
        assert "period" in specs
        assert "std_dev" in specs

    def test_rsi_momentum_has_expected_params(self) -> None:
        specs = get_param_specs("rsi_momentum")
        assert "rsi_period" in specs
        assert "oversold" in specs
        assert "overbought" in specs

    def test_alias_resolves_correctly(self) -> None:
        specs = get_param_specs("ema")
        assert "fast_ema_period" in specs

    def test_unknown_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Unknown strategy"):
            get_param_specs("does_not_exist")

    def test_returns_copy_not_original(self) -> None:
        specs1 = get_param_specs("ema_cross")
        specs2 = get_param_specs("ema_cross")
        specs1["injected"] = (0, 1, 0, None, "int")
        assert "injected" not in specs2

    def test_each_spec_has_five_elements(self) -> None:
        specs = get_param_specs("ema_cross")
        for name, spec in specs.items():
            assert len(spec) == 5, f"{name} spec should have 5 elements"
            lo, hi, default, step_hint, type_str = spec
            assert type_str in ("int", "float"), f"{name} type_str invalid"
            assert lo <= hi, f"{name} lo > hi"


@pytest.mark.unit
class TestInferParamGrid:
    def test_returns_list_of_dicts(self) -> None:
        grid = infer_param_grid("ema_cross")
        assert isinstance(grid, list)
        assert len(grid) > 0
        assert all(isinstance(p, dict) for p in grid)

    def test_grid_excludes_trade_size_by_default(self) -> None:
        grid = infer_param_grid("ema_cross")
        for params in grid:
            assert "trade_size" not in params

    def test_grid_size_scales_with_num_points(self) -> None:
        grid2 = infer_param_grid("ema_cross", num_points_per_param=2)
        grid3 = infer_param_grid("ema_cross", num_points_per_param=3)
        assert len(grid3) >= len(grid2)

    def test_grid_params_in_spec_range(self) -> None:
        specs = get_param_specs("ema_cross")
        grid = infer_param_grid("ema_cross", num_points_per_param=3)
        for params in grid:
            for name, val in params.items():
                if name in specs:
                    lo, hi, _, _, _ = specs[name]
                    assert lo <= val <= hi, f"{name}={val} out of [{lo},{hi}]"

    def test_grid_cap_raises_on_explosion(self) -> None:
        """Grid exceeding MAX_GRID_SIZE raises ValueError with actionable message.

        rsi_momentum has float params (oversold, overbought), so with 200 points:
        rsi_period(15) * oversold(200) * overbought(200) = 600,000 >> MAX_GRID_SIZE.
        """
        with pytest.raises(ValueError, match="MAX_GRID_SIZE|exceeding|combinations"):
            infer_param_grid("rsi_momentum", num_points_per_param=200)

    def test_max_grid_size_is_10000(self) -> None:
        assert MAX_GRID_SIZE == 10_000

    def test_base_params_merged_into_each_combo(self) -> None:
        base = {"some_extra_key": 99}
        grid = infer_param_grid("ema_cross", base_params=base)
        for params in grid:
            assert params.get("some_extra_key") == 99

    def test_exclude_params_removes_param(self) -> None:
        grid = infer_param_grid("bollinger_mr", exclude_params={"period", "trade_size"})
        for params in grid:
            assert "period" not in params

    def test_single_point_grid(self) -> None:
        """num_points_per_param=1 returns a single combo using default values."""
        grid = infer_param_grid("ema_cross", num_points_per_param=1)
        assert len(grid) == 1


@pytest.mark.unit
class TestSampleRandomParams:
    def test_returns_n_samples(self) -> None:
        samples = sample_random_params("ema_cross", n=5)
        assert len(samples) == 5

    def test_samples_are_dicts(self) -> None:
        samples = sample_random_params("ema_cross", n=3)
        assert all(isinstance(p, dict) for p in samples)

    def test_samples_exclude_trade_size_by_default(self) -> None:
        samples = sample_random_params("ema_cross", n=5)
        for p in samples:
            assert "trade_size" not in p

    def test_reproducible_with_seeded_rng(self) -> None:
        rng1 = random.Random(42)
        s1 = sample_random_params("ema_cross", n=3, rng=rng1)
        rng2 = random.Random(42)
        s2 = sample_random_params("ema_cross", n=3, rng=rng2)
        assert s1 == s2

    def test_values_in_spec_range(self) -> None:
        specs = get_param_specs("ema_cross")
        samples = sample_random_params("ema_cross", n=20)
        for params in samples:
            for name, val in params.items():
                if name in specs:
                    lo, hi, _, _, _ = specs[name]
                    assert lo <= val <= hi, f"{name}={val} out of [{lo},{hi}]"

    def test_zero_samples(self) -> None:
        samples = sample_random_params("ema_cross", n=0)
        assert samples == []


@pytest.mark.unit
class TestGetSearchSpaceForOptuna:
    def test_returns_dict(self) -> None:
        space = get_search_space_for_optuna("ema_cross")
        assert isinstance(space, dict)

    def test_excludes_trade_size(self) -> None:
        space = get_search_space_for_optuna("ema_cross")
        assert "trade_size" not in space

    def test_each_entry_has_four_elements(self) -> None:
        space = get_search_space_for_optuna("ema_cross")
        for name, spec in space.items():
            assert len(spec) == 4, f"{name} spec should be (type, lo, hi, step)"
            suggest_type, lo, hi, step = spec
            assert suggest_type in ("int", "float")
            assert lo <= hi

    def test_base_params_excluded_from_space(self) -> None:
        space = get_search_space_for_optuna("ema_cross", base_params={"fast_ema_period": 10})
        assert "fast_ema_period" not in space

    def test_all_base_params_excluded(self) -> None:
        specs = get_param_specs("ema_cross")
        all_base = {k: 10 for k in specs}
        space = get_search_space_for_optuna("ema_cross", base_params=all_base)
        assert space == {}
