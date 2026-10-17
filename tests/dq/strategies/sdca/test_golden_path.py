"""Golden-path driver: research -> backtest -> optimize -> tearsheet.

The driver is mostly sequencing, so these tests are aimed at the things
sequencing can get wrong: an argument that silently means two different things,
a stage that runs on data the previous stage did not produce, and a verdict that
claims a gate nobody evaluated.

Every market series here is synthetic. The repo carries no staged price history
on this worktree, and a fixture that reads a real CSV would make the suite depend
on data that is gitignored.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from digiquant.strategies.lab import golden_path
from digiquant.strategies.lab.curve import AccumDistCurve
from digiquant.strategies.lab.curve_sim import evaluate_sdca_trial_curve_sim
from digiquant.strategies.lab.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.lab.presets import load_preset
from digiquant.strategies.lab.providers import resolve_sdca_risk_model
from digiquant.strategies.lab.risk_index import build_risk_index

pytestmark = pytest.mark.unit

INITIAL_CASH = 10_000.0


def _synthetic(row_count: int = 400, seed: int = 7) -> tuple[list[date], list[float]]:
    """A trending, noisy daily series -- enough shape for a risk index to warm up."""
    rng = random.Random(seed)
    start = date(2024, 1, 1)
    dates = [start + timedelta(days=i) for i in range(row_count)]
    level = 100.0
    prices: list[float] = []
    for _ in range(row_count):
        level *= math.exp(0.0006 + rng.gauss(0.0, 0.02))
        prices.append(level)
    return dates, prices


def _rolling_z_model(dates, prices):
    """The only risk model in this module that needs no fitted coefficients."""
    return resolve_sdca_risk_model(
        "rolling_z",
        dates=pl.Series(list(dates), dtype=pl.Date),
        price=pl.Series([float(price) for price in prices], dtype=pl.Float64),
    )


def _rails_fitter(dates, prices):
    return _rolling_z_model(dates, prices)


def _trials() -> list[dict[str, float]]:
    return [{"buy_knee_risk": 30.0}, {"buy_knee_risk": 40.0}]


def _research(row_count: int = 400):
    dates, prices = _synthetic(row_count)
    return golden_path.research_asset(
        dates=dates, prices=prices, risk_model=_rolling_z_model(dates, prices)
    )


def build_raw_risk_index(dates: list[date], prices: list[float]) -> pl.DataFrame:
    """The untrimmed index, so the warmup trim can be measured rather than assumed."""
    return build_risk_index(
        pl.Series(dates, dtype=pl.Date),
        pl.Series(prices, dtype=pl.Float64),
        _rolling_z_model(dates, prices),
    )


# --------------------------------------------------------------------------- #
# Stage 1 -- research
# --------------------------------------------------------------------------- #


def test_research_asset_returns_aligned_series() -> None:
    stage = _research()
    assert stage.row_count == len(stage.risk_index)
    assert len(stage.prices) == stage.row_count
    assert stage.row_count > 300
    assert stage.dropped_warmup_rows >= 0
    assert stage.start < stage.end
    # The trim is the contract: every surviving row has a usable risk.
    assert stage.risk_index["risk"].null_count() == 0
    assert len(stage.risk_values()) == stage.row_count


def test_research_asset_drops_the_warmup_head() -> None:
    """The composite is undefined until its slowest input warms up."""
    dates, prices = _synthetic()
    untrimmed = golden_path.research_asset(
        dates=dates,
        prices=prices,
        risk_model=_rolling_z_model(dates, prices),
        include_indicators=False,
    )
    raw = build_raw_risk_index(dates, prices)
    assert raw["risk"].null_count() > 0, (
        "fixture no longer has a warmup head, so the trim is untested"
    )
    assert untrimmed.dropped_warmup_rows == raw["risk"].null_count()
    assert untrimmed.row_count == len(dates) - untrimmed.dropped_warmup_rows


def test_research_asset_reads_market_data_from_disk(tmp_path: Path) -> None:
    dates, prices = _synthetic()
    csv_path = tmp_path / "TEST.csv"
    # load_ohlcv_csv requires a full OHLCV frame, not just timestamp/close.
    pl.DataFrame(
        {
            "timestamp": pl.Series(dates, dtype=pl.Date),
            "open": pl.Series(prices, dtype=pl.Float64),
            "high": pl.Series(prices, dtype=pl.Float64),
            "low": pl.Series(prices, dtype=pl.Float64),
            "close": pl.Series(prices, dtype=pl.Float64),
            "volume": pl.Series([1_000.0] * len(dates), dtype=pl.Float64),
        }
    ).write_csv(csv_path)

    stage = golden_path.research_asset(
        symbols=["TEST"],
        data_path=csv_path,
        risk_model_name="rolling_z",
        include_indicators=False,
    )
    assert stage.row_count > 300
    assert stage.end > stage.start


def test_research_asset_rejects_two_market_data_sources() -> None:
    dates, prices = _synthetic(50)
    with pytest.raises(ValueError, match="not both"):
        golden_path.research_asset(
            dates=dates,
            prices=prices,
            symbols=["TEST"],
            risk_model=_rolling_z_model(dates, prices),
        )


def test_research_asset_requires_a_risk_model() -> None:
    dates, prices = _synthetic(50)
    with pytest.raises(ValueError, match="rolling_z"):
        golden_path.research_asset(dates=dates, prices=prices)


def test_research_asset_rejects_unusable_market_data() -> None:
    dates, prices = _synthetic(50)
    model = _rolling_z_model(dates, prices)

    with pytest.raises(ValueError, match="differ in length"):
        golden_path.research_asset(dates=dates[:-1], prices=prices, risk_model=model)

    with pytest.raises(ValueError, match="strictly increasing"):
        golden_path.research_asset(
            dates=[dates[0], dates[0], *dates[1:-1]], prices=prices, risk_model=model
        )

    with pytest.raises(ValueError, match="strictly positive"):
        golden_path.research_asset(dates=dates, prices=[0.0, *prices[1:]], risk_model=model)

    with pytest.raises(ValueError, match="no market data"):
        golden_path.research_asset(risk_model=model)


# --------------------------------------------------------------------------- #
# Stage 2 -- backtest
# --------------------------------------------------------------------------- #


def test_backtest_asset_marks_the_report_non_authoritative() -> None:
    stage = _research()
    result = golden_path.backtest_asset(stage, preset="balanced", initial_cash=INITIAL_CASH)
    assert result.authoritative is False
    assert "Nautilus" in result.caveat
    assert result.frame.height == stage.row_count
    assert set(result.frame.columns) >= {
        "date",
        "price",
        "risk",
        "daily_trade_usd",
        "net_deployed",
        "asset_units",
    }


def test_backtest_asset_resolves_a_named_preset() -> None:
    stage = _research()
    preset = load_preset("balanced")
    assert len(preset.curve_nodes) == 21
    # Same curve either way it is passed.
    by_name = golden_path.backtest_asset(stage, preset="balanced", initial_cash=INITIAL_CASH)
    by_curve = golden_path.backtest_asset(
        stage, curve=AccumDistCurve(preset.curve_nodes), initial_cash=INITIAL_CASH
    )
    assert by_name.report.total_pnl == by_curve.report.total_pnl


def test_backtest_asset_requires_a_curve() -> None:
    stage = _research()
    with pytest.raises(ValueError, match="a curve is required"):
        golden_path.backtest_asset(stage, initial_cash=INITIAL_CASH)


# --------------------------------------------------------------------------- #
# Stage 3 -- optimize
# --------------------------------------------------------------------------- #


def test_optimize_asset_labels_the_default_evaluator() -> None:
    stage = _research()
    result = golden_path.optimize_asset(
        stage, trials=_trials(), rails_fitter=_rails_fitter, n_folds=2
    )
    assert result.evaluator_label == "curve_simulator"
    assert result.num_evaluations >= 1
    assert result.best_params["buy_knee_risk"] in (30.0, 40.0)


def test_optimize_asset_names_a_custom_evaluator() -> None:
    """A custom evaluator contributes its own name, not the simulator's."""
    stage = _research()

    def custom_evaluator(dates, prices, risk_model, shape, valuation_weight, extra_indicators=None):
        return evaluate_sdca_trial_curve_sim(
            dates,
            prices,
            risk_model,
            shape,
            valuation_weight,
            extra_indicators=extra_indicators,
        )

    result = golden_path.optimize_asset(
        stage,
        trials=_trials()[:1],
        rails_fitter=_rails_fitter,
        evaluator=custom_evaluator,
        n_folds=2,
    )
    assert result.evaluator_label == "custom_evaluator"
    assert result.num_evaluations >= 1


def test_optimize_asset_rejects_an_empty_trial_list() -> None:
    stage = _research()
    with pytest.raises(ValueError, match="at least one"):
        golden_path.optimize_asset(stage, trials=[], rails_fitter=_rails_fitter)


# --------------------------------------------------------------------------- #
# Stage 4 -- tearsheet
# --------------------------------------------------------------------------- #


def test_tearsheet_payload_carries_the_rendered_series() -> None:
    stage = _research()
    backtest = golden_path.backtest_asset(stage, preset="balanced", initial_cash=INITIAL_CASH)
    payload = golden_path.tearsheet_payload(stage, backtest, preset_name="balanced")

    for key in (
        "rails",
        "risk_curve",
        "cost_basis_curve",
        "capital_deployed_curve",
        "lump_equity_curve",
        "flat_dca_equity_curve",
    ):
        assert key in payload, f"missing documented key {key}"
    assert len(payload["rails"]) <= stage.row_count
    assert len(payload["risk_curve"]) == stage.row_count


def test_tearsheet_payload_never_invents_z_provenance_from_raw_technicals() -> None:
    """``indicator_z`` expects z-scores; technicals are raw values.

    The technical series and the catalog's ordered names are disjoint today
    (oscillators vs macro extras), so a naive assertion would pass for the wrong
    reason. This rigs an overlap on ``valuation`` -- an ordered catalog name --
    so a driver that forwarded the technical series would give that curve points.
    """
    stage = _research()
    backtest = golden_path.backtest_asset(stage, preset="balanced", initial_cash=INITIAL_CASH)
    weights = SdcaCompositeWeights(valuation=1.0)
    rigged = replace(stage, indicators={"valuation": [0.5] * stage.row_count})

    payload = golden_path.tearsheet_payload(rigged, backtest, weights=weights)
    curves = payload["indicator_curves"]
    assert curves, "weights were not forwarded, so the guard would be unobservable"
    valuation = next(curve for curve in curves if curve["name"] == "valuation")
    assert valuation["points"] == [], (
        "raw technicals were forwarded as z-scores; indicator provenance must "
        "come only from the caller"
    )

    # Positive control: the caller's own z IS forwarded.
    supplied = {"valuation": [0.5] * stage.row_count}
    with_z = golden_path.tearsheet_payload(rigged, backtest, weights=weights, indicator_z=supplied)
    with_z_curve = next(
        curve for curve in with_z["indicator_curves"] if curve["name"] == "valuation"
    )
    assert with_z_curve["points"], "a caller-supplied z series was dropped"


def test_tearsheet_payload_omits_indicator_curves_without_weights() -> None:
    stage = _research()
    backtest = golden_path.backtest_asset(stage, preset="balanced", initial_cash=INITIAL_CASH)
    payload = golden_path.tearsheet_payload(stage, backtest)
    assert "indicator_curves" not in payload


# --------------------------------------------------------------------------- #
# The driver
# --------------------------------------------------------------------------- #


def test_run_golden_path_without_trials_does_not_evaluate_the_gate() -> None:
    dates, prices = _synthetic()
    result = golden_path.run_golden_path(
        dates=dates,
        prices=prices,
        risk_model=_rolling_z_model(dates, prices),
        preset="balanced",
        initial_cash=INITIAL_CASH,
    )
    assert result.optimize is None
    assert result.verdict.cleared is False
    assert result.verdict.beats_flat_dca_oos is None
    assert "did not run" in result.verdict.reason


def test_run_golden_path_rejects_half_the_optimize_collaborators() -> None:
    """One of two would silently skip the stage, so both or neither."""
    dates, prices = _synthetic()
    common = {
        "dates": dates,
        "prices": prices,
        "risk_model": _rolling_z_model(dates, prices),
        "preset": "balanced",
        "initial_cash": INITIAL_CASH,
    }
    with pytest.raises(ValueError, match="both trials and rails_fitter"):
        golden_path.run_golden_path(**common, trials=_trials())
    with pytest.raises(ValueError, match="both trials and rails_fitter"):
        golden_path.run_golden_path(**common, rails_fitter=_rails_fitter)


def test_run_golden_path_runs_all_four_stages() -> None:
    dates, prices = _synthetic()
    result = golden_path.run_golden_path(
        dates=dates,
        prices=prices,
        risk_model=_rolling_z_model(dates, prices),
        preset="balanced",
        initial_cash=INITIAL_CASH,
        trials=_trials()[:1],
        rails_fitter=_rails_fitter,
        n_folds=2,
    )
    assert result.stages == ("research", "backtest", "optimize", "tearsheet")
    assert result.optimize is not None
    assert result.tearsheet is not None
    assert isinstance(result.verdict.beats_flat_dca_oos, bool)
    assert isinstance(result.verdict.sensitivity_stable, bool)
    assert result.verdict.cleared == (
        result.verdict.beats_flat_dca_oos and result.verdict.sensitivity_stable
    )


@pytest.mark.parametrize(
    ("beats", "stable", "expected_cleared"),
    [
        (True, True, True),
        (True, False, False),
        (False, True, False),
        (False, False, False),
    ],
)
def test_verdict_requires_both_halves(beats: bool, stable: bool, expected_cleared: bool) -> None:
    """Neither a positive OOS nor a stable neighbourhood clears the gate alone."""
    stub = SimpleNamespace(
        beats_flat_dca_oos=beats,
        mean_oos_vs_flat_dca_pct=-5.0,
        sensitivity=SimpleNamespace(stable=stable, max_abs_delta_oos_pct=1.5),
    )
    verdict = golden_path._verdict(stub)
    assert verdict.cleared is expected_cleared
    assert verdict.beats_flat_dca_oos is beats
    assert verdict.sensitivity_stable is stable


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


def test_persist_golden_path_writes_artifacts_and_carries_the_caveat(tmp_path: Path) -> None:
    dates, prices = _synthetic()
    result = golden_path.run_golden_path(
        dates=dates,
        prices=prices,
        risk_model=_rolling_z_model(dates, prices),
        preset="balanced",
        initial_cash=INITIAL_CASH,
        trials=_trials()[:1],
        rails_fitter=_rails_fitter,
        n_folds=2,
    )
    paths = golden_path.persist_golden_path(result, tmp_path, stem="smoke")

    assert set(paths) == {"risk_index", "backtest_frame", "tearsheet", "manifest"}
    for path in paths.values():
        assert path.exists() and path.stat().st_size > 0

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    # The caveat travels with the numbers: an artifact cannot be mistaken for a
    # published backtest or for a cleared gate.
    assert manifest["backtest"]["authoritative"] is False
    assert "Nautilus" in manifest["backtest"]["caveat"]
    assert manifest["rules"]["feasibility"].startswith(
        "Feasibility gates on capital_deployed_peak_pct"
    )
    assert "digiquant.io" in manifest["rules"]["publish"]
    assert manifest["verdict"]["cleared"] == result.verdict.cleared
    assert manifest["optimize_ran"] is True
    assert manifest["range"]["rows"] == result.research.row_count


def test_persist_golden_path_omits_the_tearsheet_when_not_built(tmp_path: Path) -> None:
    dates, prices = _synthetic()
    result = golden_path.run_golden_path(
        dates=dates,
        prices=prices,
        risk_model=_rolling_z_model(dates, prices),
        preset="balanced",
        initial_cash=INITIAL_CASH,
        with_tearsheet=False,
    )
    paths = golden_path.persist_golden_path(result, tmp_path, stem="no_tearsheet")
    assert "tearsheet" not in paths
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["tearsheet_written"] is False


# --------------------------------------------------------------------------- #
# Reachability through the facade
# --------------------------------------------------------------------------- #


def test_the_driver_is_reachable_through_the_facade() -> None:
    import digiquant.strategies.lab as lab

    assert lab.run_golden_path is golden_path.run_golden_path
    assert lab.research_asset is golden_path.research_asset
    assert lab.backtest_asset is golden_path.backtest_asset
    assert lab.optimize_asset is golden_path.optimize_asset
    assert lab.tearsheet_payload is golden_path.tearsheet_payload
    assert lab.persist_golden_path is golden_path.persist_golden_path
    assert lab.GoldenPathResult is golden_path.GoldenPathResult
    assert lab.GoldenPathVerdict is golden_path.GoldenPathVerdict
