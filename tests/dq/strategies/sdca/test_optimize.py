"""SDCA walk-forward optimizer (#3174) — injected evaluator, no Nautilus."""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import polars as pl
import pytest
from digiquant.optimize import _sdca_trials, run_optimize
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape
from digiquant.strategies.sdca.optimize import (
    SDCA_SHAPE_DEFAULTS,
    SdcaOptimizeProvenance,
    SdcaWalkForwardResult,
    _sensitivity_of,
    load_btc_optimized_provenance,
    load_sdca_extra_z,
    persist_btc_optimized,
    run_sdca_walk_forward,
    walk_forward_to_optimize_result,
)
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategies.sdca.price_oscillators import SdcaOscillatorSpec
from digiquant.strategies.sdca.risk_model import RiskModel
from digiquant.strategies.sdca.walk_forward import (
    SENSITIVITY_SPIKE_PCT,
    SdcaOptimizeObjective,
    SdcaTrialMetrics,
    make_walk_forward_folds,
    sensitivity_neighbors,
    shape_from_params,
)
from digiquant.strategy_specs import (
    _resolve_strategy_name,
    get_param_specs,
    infer_param_grid,
    sample_random_params,
)

try:
    import nautilus_trader as _nautilus_trader
except ImportError:
    _nautilus_trader = None

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


def _stub_nautilus_evaluator(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI digiquant lane has no nautilus_trader; ``_run_sdca_optimize`` imports
    ``nautilus_evaluator`` before the walk-forward monkeypatch runs.
    """
    stub = ModuleType("digiquant.strategies.sdca.nautilus_evaluator")

    def _unused(*_a: object, **_k: object) -> SdcaTrialMetrics:
        raise AssertionError("walk-forward should be monkeypatched before evaluator use")

    stub.evaluate_sdca_trial_nautilus = _unused  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "digiquant.strategies.sdca.nautilus_evaluator", stub)


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
        capital_deployed_peak_pct=40.0,
        max_drawdown_pct=12.0,
    )


class TestSensitivityNeighboursSkipNoOps:
    """+-5% of a zero weight is still zero: that is not a perturbation.

    Counting those as neighbours used to deflate any statistic taken over the
    neighbourhood, and made the report's ``neighbor_count`` depend on how many
    zero weights a candidate happened to carry.
    """

    def test_a_zero_weight_is_not_a_perturbation(self) -> None:
        base = {**SDCA_SHAPE_DEFAULTS, "valuation_weight": 1.0, "m2_weight": 0.0}
        neighbors = sensitivity_neighbors(base, frac=0.05)
        assert neighbors
        # No neighbour was produced BY the zero-valued m2 bump ...
        assert not any([k for k in n if n[k] != base[k]] == ["m2_weight"] for n in neighbors)
        # ... while a non-zero weight still produces both of its own.
        bumped = sorted(n["valuation_weight"] for n in neighbors if n["valuation_weight"] != 1.0)
        assert bumped[0] == pytest.approx(0.95)
        assert bumped[-1] == pytest.approx(1.05)

    def test_every_neighbour_differs_in_exactly_one_key(self) -> None:
        base = {**SDCA_SHAPE_DEFAULTS, "valuation_weight": 1.0}
        for neighbor in sensitivity_neighbors(base, frac=0.05):
            differing = [key for key in neighbor if neighbor[key] != base[key]]
            assert len(differing) == 1


class TestSensitivityGateUsesThePlateau:
    """#3174 asks for a stable *plateau*. Both arms are the pin.

    The second arm is the falsification test: a candidate whose whole
    neighbourhood moves together must still be rejected, so relaxing the
    statistic from ``max`` to a quantile cannot quietly turn the gate into one
    that never fires.
    """

    @staticmethod
    def _base() -> dict[str, float]:
        return {**SDCA_SHAPE_DEFAULTS, "valuation_weight": 1.0}

    def _report(self, evaluator: object) -> object:
        base = self._base()
        dates = _dates()
        prices = [100.0 + i for i in range(len(dates))]
        folds, _holdout = make_walk_forward_folds(dates)
        return _sensitivity_of(
            base,
            100.0,
            dates,
            prices,
            folds,
            _fitter,
            evaluator,  # type: ignore[arg-type]
            SdcaOptimizeObjective(),
            0.05,
            None,
        )

    def test_one_steep_edge_on_a_flat_surface_still_passes(self) -> None:
        base_shape = shape_from_params(self._base())

        def evaluator(
            dates: list[date],
            prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            assert isinstance(model, _ConstRails)
            vs = 92.0 if shape.buy_knee_risk != base_shape.buy_knee_risk else 100.0
            return SdcaTrialMetrics(
                vs_flat_dca_pct=vs,
                vs_lump_pct=-1.0,
                capital_deployed_pct=40.0,
                capital_deployed_peak_pct=40.0,
                max_drawdown_pct=12.0,
            )

        report = self._report(evaluator)
        # The worst axis is a cliff ...
        assert report.max_abs_delta_oos_pct == pytest.approx(8.0)
        # ... but the surface is flat, which is what the gate is asking about.
        assert report.p75_abs_delta_oos_pct == pytest.approx(0.0)
        assert report.stable is True
        assert report.worst_neighbor_key == "buy_knee_risk:+5%"
        assert report.worst_loss_pct == pytest.approx(-8.0)

    def test_a_broadly_sloping_surface_still_fails(self) -> None:
        base = self._base()
        base_shape = shape_from_params(base)

        def evaluator(
            dates: list[date],
            prices: list[float],
            model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators: object = None,
        ) -> SdcaTrialMetrics:
            assert isinstance(model, _ConstRails)
            unchanged = shape == base_shape and valuation_weight == base["valuation_weight"]
            return SdcaTrialMetrics(
                vs_flat_dca_pct=100.0 if unchanged else 97.0,
                vs_lump_pct=-1.0,
                capital_deployed_pct=40.0,
                capital_deployed_peak_pct=40.0,
                max_drawdown_pct=12.0,
            )

        report = self._report(evaluator)
        assert report.p75_abs_delta_oos_pct == pytest.approx(3.0)
        assert report.p75_abs_delta_oos_pct > SENSITIVITY_SPIKE_PCT
        assert report.stable is False


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
            "weekly_rsi_weight",
            "weekly_macd_weight",
            "sma_band_weight",
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
        assert result.sensitivity.worst_neighbor_key == "buy_max_rate:+5%"

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

    def test_persist_carries_the_mid_tier_into_the_preset(self, tmp_path: Path) -> None:
        dates = _dates()
        prices = [100.0] * len(dates)
        params = {
            **_HIDDEN,
            "buy_mid_knee_risk": 15.0,
            "buy_mid_curvature": 1.5,
            "sell_mid_knee_risk": 85.0,
            "sell_mid_curvature": 1.2,
        }
        result = run_sdca_walk_forward(
            dates,
            prices,
            [params],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        presets = tmp_path / "presets.json"
        presets.write_text(json.dumps({}))
        persist_btc_optimized(
            result,
            presets_path=presets,
            provenance_path=tmp_path / "prov.json",
            notes="mid-tier persist",
        )
        shape = json.loads(presets.read_text())["btc_optimized"]["shape"]
        assert shape["buy_mid_knee_risk"] == pytest.approx(15.0)
        assert shape["buy_mid_curvature"] == pytest.approx(1.5)
        assert shape["sell_mid_knee_risk"] == pytest.approx(85.0)
        assert shape["sell_mid_curvature"] == pytest.approx(1.2)
        # The persisted dict must re-validate as the same shape, mid tier included.
        reloaded = SdcaCurveShape.model_validate(shape)
        assert reloaded.buy_mid_knee_risk == pytest.approx(15.0)
        assert reloaded.sell_mid_curvature == pytest.approx(1.2)

    def test_checked_in_preset_and_provenance_load(self) -> None:
        preset = load_preset("btc_optimized")
        assert preset.shape is not None
        assert len(preset.curve_nodes) == 21
        prov = load_btc_optimized_provenance()
        assert prov.beats_flat_dca_oos is False
        # Promotion record (owner accept 2026-09-29): the notes must point at
        # the cycle-4 gate record, not the prior fit's boilerplate.
        assert "cycle-4" in prov.notes
        assert "SUPERSEDED" in prov.notes

    def test_run_optimize_sdca_dispatches_to_walk_forward(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, object] = {}

        # CI digiquant-test does not install nautilus_trader (#42). Stub the
        # evaluator module so dispatch is still asserted; walk_forward is patched.
        if _nautilus_trader is None:
            stub = ModuleType("digiquant.strategies.sdca.nautilus_evaluator")

            def _unused_nautilus_eval(*_a: object, **_k: object) -> None:
                raise AssertionError("walk_forward monkeypatch should intercept")

            stub.evaluate_sdca_trial_nautilus = _unused_nautilus_eval  # type: ignore[attr-defined]
            monkeypatch.setitem(sys.modules, "digiquant.strategies.sdca.nautilus_evaluator", stub)

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

        _stub_nautilus_evaluator(monkeypatch)
        monkeypatch.setattr("digiquant.optimize.run_sdca_walk_forward", fake_walk_forward)
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

    def test_run_optimize_freezes_stage_a_weight_params(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        captured: dict[str, object] = {}

        def fake_walk_forward(
            dates: list[date],
            prices: list[float],
            trials: list[dict[str, float | int | str]],
            **kwargs: object,
        ) -> SdcaWalkForwardResult:
            captured["trials"] = trials
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

        _stub_nautilus_evaluator(monkeypatch)
        monkeypatch.setattr("digiquant.optimize.run_sdca_walk_forward", fake_walk_forward)
        csv = tmp_path / "BTC-USD.csv"
        rows = ["timestamp,open,high,low,close,volume,symbol"]
        for i in range(60):
            d = date(2020, 1, 1) + timedelta(days=i)
            rows.append(f"{d},100,101,99,100,1,BTC-USD")
        csv.write_text("\n".join(rows) + "\n")
        run_optimize(
            strategy_name="sdca",
            symbols=["BTC-USD"],
            data_path=csv,
            param_grid=[dict(SDCA_SHAPE_DEFAULTS), dict(_HIDDEN)],
            base_params={"weekly_rsi_weight": 0.4, "valuation_weight": 0.6},
        )
        trials = captured["trials"]
        assert isinstance(trials, list)
        assert all(t.get("weekly_rsi_weight") == 0.4 for t in trials)
        assert all(t.get("valuation_weight") == 0.6 for t in trials)

    def test_sdca_auto_grid_excludes_curvatures(self) -> None:
        trials = _sdca_trials(None, "grid", 10, None)
        assert trials
        assert all("buy_curvature" not in t or t["buy_curvature"] == 1.0 for t in trials)
        extra_keys = {
            "m2_weight",
            "rs_eth_weight",
            "dxy_weight",
            "weekly_rsi_weight",
            "weekly_macd_weight",
            "sma_band_weight",
        }
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
                    "weekly_rsi_weight": 0.0,
                    "weekly_macd_weight": 0.0,
                    "sma_band_weight": 0.0,
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


class TestFoldWeighting:
    """``fold_weighting`` (default ``"unweighted"``) must reproduce every
    existing caller byte-for-byte; both weighted means are always populated
    regardless of which is primary."""

    def test_default_matches_explicit_unweighted_byte_for_byte(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        default = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        explicit = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
            fold_weighting="unweighted",
        )
        assert default.fold_weighting == "unweighted"
        assert default.mean_is_vs_flat_dca_pct == pytest.approx(explicit.mean_is_vs_flat_dca_pct)
        assert default.mean_oos_vs_flat_dca_pct == pytest.approx(explicit.mean_oos_vs_flat_dca_pct)
        assert default.sensitivity.max_abs_delta_oos_pct == pytest.approx(
            explicit.sensitivity.max_abs_delta_oos_pct
        )
        assert default.beats_flat_dca_oos == explicit.beats_flat_dca_oos

    def test_both_weighted_means_always_populated(self) -> None:
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        result = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        # Unweighted is primary here, so the primary field must equal the
        # unweighted sidecar -- and the duration sidecar must still be there.
        assert result.mean_oos_vs_flat_dca_pct == pytest.approx(
            result.mean_oos_vs_flat_dca_pct_unweighted
        )
        assert isinstance(result.mean_oos_vs_flat_dca_pct_duration_weighted, float)

    def test_duration_weighting_shifts_mean_is_toward_the_longer_expanding_fold(self) -> None:
        # IS windows expand fold-over-fold (fold 0 shortest, fold 2 longest);
        # OOS windows all tile the same fixed length, so mean_oos is identical
        # either way -- only the expanding IS leg can diverge.
        dates = _dates(200)
        prices = [100.0 + i for i in range(len(dates))]
        unweighted = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
        )
        duration = run_sdca_walk_forward(
            dates,
            prices,
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator,
            evaluator_label="synthetic_fixture",
            fold_weighting="duration",
        )
        assert duration.fold_weighting == "duration"
        assert duration.mean_oos_vs_flat_dca_pct == pytest.approx(unweighted.mean_oos_vs_flat_dca_pct)
        assert duration.mean_is_vs_flat_dca_pct != pytest.approx(unweighted.mean_is_vs_flat_dca_pct)
        # The evaluator's `- 0.02 * len(dates)` penalty makes vs_flat_dca_pct
        # decrease as the IS window grows, so weighting toward the longest
        # (last) fold must pull the duration-weighted mean IS down.
        assert duration.mean_is_vs_flat_dca_pct < unweighted.mean_is_vs_flat_dca_pct


class TestLoadSdcaExtraZOscillators:
    """A frozen ``oscillators`` spec must actually change the price-oscillator
    extras -- #3174's walk-forward silently reverted weekly_monthly_rsi/macd,
    sma_band, weekly_rsi, and weekly_macd to ``SdcaOscillatorSpec()`` defaults
    because ``load_sdca_extra_z``'s second ``extra_z_vectors(...)`` call (used
    to also pick up m2/dxy/rs_eth) omitted ``oscillators=oscillators`` and
    then clobbered the correctly-computed keys from the first call via
    ``dict.update``.
    """

    def test_frozen_oscillators_change_price_oscillator_extras(self, tmp_path: Path) -> None:
        dates = [date(2018, 1, 1) + timedelta(days=i) for i in range(900)]
        import math

        prices = [30_000.0 * (1.0 + 0.4 * math.sin(i / 45.0)) for i in range(len(dates))]

        frozen = SdcaOscillatorSpec(
            rsi_length=5,
            monthly_rsi_length=2,
            macd_fast=16,
            macd_slow=35,
            monthly_macd_fast=4,
            monthly_macd_slow=9,
            sma_band_window=120,
            sma_band_fast_window=30,
        )
        extra_frozen = load_sdca_extra_z(
            dates, prices, data_path=None, data_dir=str(tmp_path), oscillators=frozen
        )
        extra_default = load_sdca_extra_z(
            dates, prices, data_path=None, data_dir=str(tmp_path), oscillators=None
        )

        # weekly_monthly_rsi/macd (confluence family) are dormant on develop and
        # not emitted by load_sdca_extra_z, so only the wired oscillators are checked.
        for name in (
            "sma_band",
            "weekly_rsi",
            "weekly_macd",
        ):
            assert extra_frozen[name] != extra_default[name], (
                f"{name} did not change with a different oscillators spec -- "
                "load_sdca_extra_z is silently ignoring `oscillators` again"
            )


class TestLoadSdcaExtraZWindows:
    """``extra_windows`` must reach the per-indicator z computation through
    both ``load_sdca_extra_z`` and ``extra_z_vectors`` -- a per-indicator
    period-search result (e.g. dxy at 60 days) should not be silently
    dropped back to the shared default window."""

    def test_extra_windows_overrides_reach_load_sdca_extra_z(self, tmp_path: Path) -> None:
        dates = [date(2018, 1, 1) + timedelta(days=i) for i in range(400)]
        import math

        prices = [30_000.0 * (1.0 + 0.4 * math.sin(i / 45.0)) for i in range(len(dates))]
        dxy_values = [90.0 + 10.0 * math.sin(i / 20.0) for i in range(len(dates))]
        pl.DataFrame({"date": dates, "value": dxy_values}).write_csv(tmp_path / "DTWEXBGS.csv")

        extra_overridden = load_sdca_extra_z(
            dates, prices, data_path=None, data_dir=str(tmp_path), extra_windows={"dxy": 60}
        )
        extra_default = load_sdca_extra_z(
            dates, prices, data_path=None, data_dir=str(tmp_path), extra_windows=None
        )

        assert extra_overridden["dxy"] != extra_default["dxy"], (
            "extra_windows={'dxy': 60} did not change the dxy z-series -- "
            "load_sdca_extra_z is not threading extra_windows through to "
            "build_extra_indicators"
        )


class TestSensitivityGuardFailsLoudly:
    """An empty neighbour set must raise, not be reported as a stable plateau (#3174).

    The old ``max(deltas) if deltas else 0.0`` made ``stable=True, neighbor_count=0``
    reachable whenever every neighbour was dropped -- a guard that cannot fail.
    """

    def test_no_scoreable_neighbour_raises_instead_of_reporting_stable(self) -> None:
        params: dict[str, float | int | str] = {"note": "no numeric parameters"}
        # Precondition: a params dict with no numeric subject yields no neighbours,
        # which is exactly the state the old code silently reported as stable.
        assert sensitivity_neighbors(params, frac=0.05) == []

        with pytest.raises(ValueError, match="scored no neighbours"):
            _sensitivity_of(
                params,
                0.0,
                _dates(10),
                [100.0] * 10,
                [],
                _fitter,
                _evaluator,
                SdcaOptimizeObjective(),
                0.05,
                None,
            )


def _evaluator_with_deployment(end_pct: float, peak_pct: float):
    """Evaluator stub reporting a chosen capital-deployment profile."""

    def _ev(
        dates: list[date],
        prices: list[float],
        model: RiskModel,
        shape: SdcaCurveShape,
        valuation_weight: float,
        extra_indicators: object = None,
    ) -> SdcaTrialMetrics:
        return SdcaTrialMetrics(
            vs_flat_dca_pct=1.0,
            vs_lump_pct=0.0,
            capital_deployed_pct=end_pct,
            capital_deployed_peak_pct=peak_pct,
            max_drawdown_pct=0.0,
        )

    return _ev


class TestHoldoutTradedFlag:
    """A holdout that never trades must say so rather than report a number.

    The holdout window can sit entirely above the rails' median rail, so the
    composite risk never enters either shape's buy band: no capital is deployed,
    every metric is the held-cash outcome, and the candidate's ``holdout_metrics``
    comes out byte-identical to the baseline's. That identity reads like a
    measurement and is not one.

    The signal is ``capital_deployed_peak_pct``, the quantity ``is_feasible``
    already gates on. ``capital_deployed_pct`` is a documented end-of-window cash
    snapshot that goes negative whenever a curve sold appreciated asset into a
    rally, so it cannot answer "did this window trade" -- see the third case.
    """

    def _result(self, end_pct: float, peak_pct: float):
        return run_sdca_walk_forward(
            _dates(60),
            [100.0 + i for i in range(60)],
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_evaluator_with_deployment(end_pct, peak_pct),
            evaluator_label="synthetic_fixture",
        )

    def test_a_holdout_that_never_deployed_capital_is_flagged(self) -> None:
        result = self._result(0.0, 0.0)
        assert result.holdout_metrics is not None
        assert result.holdout_metrics.capital_deployed_peak_pct == 0.0
        assert result.holdout_traded is False

    def test_a_holdout_that_deployed_capital_is_flagged_as_traded(self) -> None:
        assert self._result(40.0, 40.0).holdout_traded is True

    def test_a_holdout_that_ended_net_negative_still_counts_as_traded(self) -> None:
        # Sold appreciated asset into a rally, so end-of-window cash exceeds the
        # starting cash and capital_deployed_pct is negative. The window plainly
        # traded, so the flag must not key on that field.
        assert self._result(-12.0, 30.0).holdout_traded is True

    def test_the_message_reports_whether_the_holdout_traded(self) -> None:
        envelope = walk_forward_to_optimize_result(
            self._result(0.0, 0.0), strategy_name="sdca", symbols=["BTC-USD"]
        )
        assert "holdout_traded=False" in envelope.message


class TestSelectionFoldExclusion:
    """A fold dropped from selection must be recorded, not silently averaged over."""

    def _result(self, breach_oos_start: date | None) -> SdcaWalkForwardResult:
        def _run(
            dates: list[date],
            prices: list[float],
            risk_model: RiskModel,
            shape: SdcaCurveShape,
            valuation_weight: float,
            extra_indicators=None,
        ) -> SdcaTrialMetrics:
            breach = breach_oos_start is not None and dates[0] == breach_oos_start
            return SdcaTrialMetrics(
                vs_flat_dca_pct=-5.0 if breach else 1.0,
                vs_lump_pct=0.0,
                capital_deployed_pct=100.0,
                capital_deployed_peak_pct=100.0,
                max_drawdown_pct=90.0 if breach else 10.0,
            )

        return run_sdca_walk_forward(
            _dates(60),
            [100.0 + i for i in range(60)],
            [dict(_HIDDEN)],
            rails_fitter=_fitter,
            evaluator=_run,
            evaluator_label="synthetic_fixture",
        )

    def test_a_fold_that_breached_a_rail_is_recorded_as_excluded(self) -> None:
        folds, _ = make_walk_forward_folds(_dates(60))
        target = folds[0].oos_start
        expected = [f.fold for f in folds if f.oos_start == target]
        result = self._result(target)
        assert expected, "fixture must breach at least one fold or the test is vacuous"
        assert result.fold_scores[0].feasible is False
        assert result.selection_excluded_folds == expected

    def test_no_fold_is_excluded_when_every_fold_is_feasible(self) -> None:
        result = self._result(None)
        assert all(score.feasible for score in result.fold_scores)
        assert result.selection_excluded_folds == []

    def test_the_message_reports_the_excluded_folds(self) -> None:
        folds, _ = make_walk_forward_folds(_dates(60))
        vetoed = self._result(folds[0].oos_start)
        assert vetoed.selection_excluded_folds, "fixture must exclude a fold"
        envelope = walk_forward_to_optimize_result(
            vetoed, strategy_name="sdca", symbols=["BTC-USD"]
        )
        rendered = f"selection_excluded_folds={vetoed.selection_excluded_folds}"
        assert rendered in envelope.message
        clean = walk_forward_to_optimize_result(
            self._result(None), strategy_name="sdca", symbols=["BTC-USD"]
        )
        assert "selection_excluded_folds=[]" in clean.message

    def test_the_provenance_records_the_excluded_folds(self, tmp_path: Path) -> None:
        folds, _ = make_walk_forward_folds(_dates(60))
        result = self._result(folds[0].oos_start)
        presets_path = tmp_path / "presets.json"
        presets_path.write_text(json.dumps({}))
        provenance_path = tmp_path / "provenance.json"
        persist_btc_optimized(
            result,
            presets_path=presets_path,
            provenance_path=provenance_path,
            notes="selection exclusion",
        )
        sidecar = json.loads(provenance_path.read_text())
        assert result.selection_excluded_folds, "fixture must exclude a fold"
        assert sidecar["selection_excluded_folds"] == result.selection_excluded_folds
