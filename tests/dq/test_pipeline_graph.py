"""Unit tests for DigiQuant LangGraph pipeline (mocked service layer)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digiquant.graph.pipeline import run_quant_workflow
from digiquant.models import BacktestResult, ExportResult, OptimizeResult


def _bt() -> BacktestResult:
    return BacktestResult(
        run_id="b1",
        strategy_name="ema_cross",
        symbols=["AAPL"],
        start_time="2020-01-01",
        end_time="2020-06-01",
        status="ok",
    )


def _opt() -> OptimizeResult:
    return OptimizeResult(
        run_id="o1",
        strategy_name="ema_cross",
        symbols=["AAPL"],
        best_params={"fast_ema_period": 10},
        num_evaluations=3,
        status="ok",
    )


def _exp() -> ExportResult:
    return ExportResult(
        run_id="e1",
        target="nautilus",
        strategy_name="ema_cross",
        artifact_path="/tmp/x.json",
        status="ok",
    )


@pytest.mark.unit
def test_pipeline_skips_optimize_and_export_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ALLOW_EXPORT", "0")
    with (
        patch("digiquant.graph.pipeline.service_run_backtest", return_value=_bt()),
        patch("digiquant.graph.pipeline.service_run_optimize") as m_opt,
        patch("digiquant.graph.pipeline.service_run_export") as m_exp,
    ):
        raw = run_quant_workflow({
            "strategy_name": "ema_cross",
            "symbols": ["AAPL"],
            "data_dir": "/data",
            "run_optimize": False,
            "run_export": False,
        })
    m_opt.assert_not_called()
    m_exp.assert_not_called()
    assert raw.get("error") is None
    assert raw.get("backtest") is not None
    assert raw.get("optimize") is None
    assert raw.get("export") is None
    steps = [t.get("step") for t in (raw.get("trace") or [])]
    assert "validate" in steps and "backtest" in steps


@pytest.mark.unit
def test_pipeline_runs_full_chain_when_export_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ALLOW_EXPORT", "1")
    with (
        patch("digiquant.graph.pipeline.service_run_backtest", return_value=_bt()),
        patch("digiquant.graph.pipeline.service_run_optimize", return_value=_opt()),
        patch("digiquant.graph.pipeline.service_run_export", return_value=_exp()),
    ):
        raw = run_quant_workflow({
            "strategy_name": "ema_cross",
            "symbols": ["AAPL"],
            "data_dir": "/data",
        })
    assert raw.get("error") is None
    assert raw.get("backtest") and raw.get("optimize") and raw.get("export")
    assert any(t.get("step") == "export" and t.get("status") == "ok" for t in raw["trace"])


@pytest.mark.unit
def test_pipeline_validates_constraints_dict() -> None:
    with (
        patch("digiquant.graph.pipeline.service_run_backtest", return_value=_bt()),
        patch("digiquant.graph.pipeline.service_run_optimize", return_value=_opt()),
        patch("digiquant.graph.pipeline.service_run_export", return_value=_exp()),
    ):
        raw = run_quant_workflow({
            "strategy_name": "ema_cross",
            "symbols": ["AAPL"],
            "data_dir": "/data",
            "constraints": {"min_trades": 5},
        })
    assert raw.get("error") is None
    assert raw.get("optimize") is not None
