"""SDCA walk-forward optimizer (#3174) — injected evaluator, no Nautilus."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import pytest
from digiquant.optimize import _sdca_trials, run_optimize
from digiquant.strategies.sdca import optimize as sdca_opt
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    SdcaOptimizeProvenance,
    SdcaWalkForwardResult,
    persist_btc_optimized,
    run_sdca_walk_forward,
    walk_forward_to_optimize_result,
)
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import SdcaTrialMetrics
from digiquant.strategy_specs import (
    _resolve_strategy_name,
    get_param_specs,
    infer_param_grid,
    sample_random_params,
)

pytestmark = pytest.mark.unit

_HIDDEN = {
    "buy_max_rate": 8.0,
    "buy_knee_risk": 30.0,
    "sell_knee_risk": 70.0,
    "sell_max_rate": 6.0,
    "buy_curvature": 1.0,
    "sell_curvature": 2.0,
    "valuation_weight": 1.0,
    "m2_weight": 0.0,
}


def _dates(n: int = 60) -> list[date]:
    return [date(2020, 1, 1) + timedelta(days=i) for i in range(n)]


class _ConstRails:
    def rails(self, dates: pl.Series) -> pl.DataFrame:
        n = dates.len()
        return pl.DataFrame({"low": [50.0] * n, "median": [100.0] * n, "high": [200.0] * n})


def _fitter(dates: list[date], prices: list[float]) -> RiskModel:
    assert dates and prices and len(dates) == len(prices)
    return _ConstRails()


def _distance(shape: SdcaCurveShape, weight: float, m2_weight: float = 0.0) -> float:
    return (
        (shape.buy_max_rate - _HIDDEN["buy_max_rate"]) ** 2
        + ((shape.buy_knee_risk - _HIDDEN["buy_knee_risk"]) / 10.0) ** 2
        + ((shape.sell_knee_risk - _HIDDEN["sell_knee_risk"]) / 10.0) ** 2
        + (shape.sell_max_rate - _HIDDEN["sell_max_rate"]) ** 2
        + (weight - _HIDDEN["valuation_weight"]) ** 2
        + (m2_weight - _HIDDEN.get("m2_weight", 0.0)) ** 2
    )


def _evaluator(
    dates: list[date],
    prices: list[float],
    model: RiskModel,
    shape: SdcaCurveShape,
    valuation_weight: float,
    extra_indicators: object = None,
) -> SdcaTrialMetrics:
    assert isinstance(model, _ConstRails)
    extras = extra_indicators or []
    m2_w = 0.0
    for ind in extras:
        if getattr(ind, "name", "") == "m2":
            m2_w = float(ind.weight)
    vs_flat = 5.0 - _distance(shape, valuation_weight, m2_w) - 0.02 * len(dates)
    return SdcaTrialMetrics(
        vs_flat_dca_pct=vs_flat,
        vs_lump_pct=-1.0,
        capital_deployed_pct=40.0,
        max_drawdown_pct=12.0,
    )


class TestStrategySpecsSdca:
    def test_btc_sdca_alias_resolves(self) -> None:
        assert _resolve_strategy_name("btc_sdca") == "sdca"
        assert _resolve_strategy_name("sdca") == "sdca"

    def test_specs_cover_six_shape_params_and_weight(self) -> None:
        specs = get_param_specs("sdca")
        for name in (
            "buy_max_rate",
            "buy_knee_risk",
            "sell_knee_risk",
            "sell_max_rate",
            "buy_curvature",
            "sell_curvature",
            "valuation_weight",
            "m2_weight",
            "rs_eth_weight",
            "dxy_weight",
        ):
            assert name in specs
        lo_buy, hi_buy, _, _, _ = specs["buy_knee_risk"]
        lo_sell, hi_sell, _, _, _ = specs["sell_knee_risk"]
        assert hi_buy < lo_sell
        assert specs["valuation_weight"][0] == 0.0
        assert specs["m2_weight"][2] == 0.0

    def test_alias_get_param_specs(self) -> None:
        assert set(get_param_specs("btc_sdca")) == set(get_param_specs("sdca"))

    def test_random_samples_keep_dead_zone(self) -> None:
        samples = sample_random_params("sdca", n=30)
        for params in samples:
            assert params["buy_knee_risk"] < params["sell_knee_risk"]


class TestWalkForwardSearch:
    def test_picks_closer_shape_on_oos_vs_flat_dca(self) -> None:
        dates = _dates()
        prices = [100.0 + i for i in range(len(dates))]
        worse = {**SDCA_SHAPE_DEFAULTS, "buy_max_rate": 20.0, "buy_knee_risk": 15.0}
        result = run_sdca_walk_forward(
            dates,
            prices,
            [worse, dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        assert result.best_params["buy_max_rate"] == pytest.approx(_HIDDEN["buy_max_rate"])
        assert result.best_params["buy_knee_risk"] == pytest.approx(_HIDDEN["buy_knee_risk"])
        assert result.num_evaluations == 2
        assert len(result.fold_scores) == 3
        # IS windows are longer, so the synthetic gap is positive.
        assert result.is_oos_gap_pct != 0.0
        assert result.holdout_metrics is not None
        assert result.sensitivity.neighbor_count > 0

    def test_optimize_result_message_states_oos(self) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        result = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        opt = walk_forward_to_optimize_result(result, strategy_name="sdca", symbols=["BTC-USD"])
        assert opt.best_backtest is None
        assert "mean_oos_vs_flat_dca_pct" in opt.message
        assert "beats_flat_dca_oos" in opt.message
        assert opt.best_params["sell_knee_risk"] == pytest.approx(70.0)


class TestPersistAndDispatch:
    def test_persist_writes_preset_and_provenance(self, tmp_path: Path) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        result = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        presets = tmp_path / "presets.json"
        presets.write_text(json.dumps({}))
        provenance_path = tmp_path / "prov.json"
        prov = persist_btc_optimized(
            result,
            presets_path=presets,
            provenance_path=provenance_path,
            notes="unit-test persist",
        )
        assert prov.evaluator == "synthetic_fixture"
        loaded = json.loads(presets.read_text())
        assert "btc_optimized" in loaded
        assert loaded["btc_optimized"]["shape"]["buy_max_rate"] == pytest.approx(8.0)
        roundtrip = SdcaOptimizeProvenance.model_validate_json(provenance_path.read_text())
        assert roundtrip.beats_flat_dca_oos == result.beats_flat_dca_oos

    def test_checked_in_preset_and_provenance_load(self) -> None:
        preset = load_preset("btc_optimized")
        assert preset.shape is not None
        assert len(preset.curve_nodes) == 21
        path = Path(sdca_opt.__file__).with_name("btc_optimized_provenance.json")
        prov = SdcaOptimizeProvenance.model_validate_json(path.read_text())
        assert prov.beats_flat_dca_oos is False
        assert "nautilus" in prov.notes.lower() or "SIGABRT" in prov.notes

    def test_run_optimize_sdca_dispatches_to_walk_forward(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, object] = {}

        def fake_walk_forward(
            dates: list[date],
            prices: list[float],
            trials: list[dict[str, float | int | str]],
            **kwargs: object,
        ) -> SdcaWalkForwardResult:
            captured["n_trials"] = len(trials)
            captured["evaluator_label"] = kwargs["evaluator_label"]
            dates_l = list(dates)
            prices_l = list(prices)
            return run_sdca_walk_forward(
                dates_l,
                prices_l,
                [dict(_HIDDEN)],
                rails_fitter=_fitter,
                evaluator=_evaluator,
                evaluator_label="injected",
            )

        monkeypatch.setattr(
            "digiquant.strategies.sdca.optimize.run_sdca_walk_forward", fake_walk_forward
        )
        csv = tmp_path / "BTC-USD.csv"
        n = 60
        rows = ["timestamp,open,high,low,close,volume,symbol"]
        for i in range(n):
            d = date(2020, 1, 1) + timedelta(days=i)
            rows.append(f"{d},100,101,99,100,1,BTC-USD")
        csv.write_text("\n".join(rows) + "\n")
        opt = run_optimize(
            strategy_name="btc_sdca",
            symbols=["BTC-USD"],
            data_path=csv,
            param_grid=[dict(_HIDDEN), dict(SDCA_SHAPE_DEFAULTS)],
        )
        assert captured["evaluator_label"] == "nautilus"
        assert captured["n_trials"] == 2
        assert opt.strategy_name == "btc_sdca"
        assert "mean_oos_vs_flat_dca_pct" in opt.message

    def test_sdca_auto_grid_excludes_curvatures(self) -> None:
        trials = _sdca_trials(None, "grid", 10, None)
        assert trials
        assert all("buy_curvature" not in t or t["buy_curvature"] == 1.0 for t in trials)
        extra_keys = {"m2_weight", "rs_eth_weight", "dxy_weight"}
        assert all(t.get(k, 0.0) == 0.0 for t in trials for k in extra_keys)
        assert len(trials) == len(
            infer_param_grid(
                "sdca",
                num_points_per_param=2,
                exclude_params={
                    "buy_curvature",
                    "sell_curvature",
                    "trade_size",
                    *extra_keys,
                },
                base_params={
                    "buy_curvature": 1.0,
                    "sell_curvature": 2.0,
                    "m2_weight": 0.0,
                    "rs_eth_weight": 0.0,
                    "dxy_weight": 0.0,
                },
            )
        )

    def test_random_samples_include_extra_weights(self) -> None:
        samples = sample_random_params("sdca", n=20)
        assert all("m2_weight" in s and "rs_eth_weight" in s and "dxy_weight" in s for s in samples)
        assert min(s["m2_weight"] for s in samples) < max(s["m2_weight"] for s in samples)

    def test_walk_forward_searches_extra_weights(self) -> None:
        dates = _dates()
        prices = [100.0 + i for i in range(len(dates))]
        hidden = {**_HIDDEN, "valuation_weight": 0.4, "m2_weight": 0.6}
        worse = {**SDCA_SHAPE_DEFAULTS, "m2_weight": 0.0, "valuation_weight": 1.0}
        extra_z = {"m2": [0.0] * len(dates)}
        result = run_sdca_walk_forward(
            dates,
            prices,
            [worse, dict(hidden)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
            extra_z=extra_z,
        )
        assert result.best_params["m2_weight"] == pytest.approx(0.6)
        assert result.best_params["valuation_weight"] == pytest.approx(0.4)
