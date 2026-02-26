"""DigiQuant HTTP API for DigiGraph. Phase 2: backtest, optimize, export, pipeline."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from digiquant.addm import AddmResult, check_drift
from digiquant.audit import audit_log as dq_audit_log
from digiquant.backtest import run_backtest
from digiquant.export import run_export
from digiquant.models import BacktestResult, ExportResult, OptimizeResult, OptimizationConstraints
from digiquant.optimize import run_optimize

app = FastAPI(
    title="DigiQuant",
    description="High-perf backtest/optimize/export API for DigiGraph (MCP in Phase 2)",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class BacktestRequest(BaseModel):
    """Request body for /run_backtest."""

    strategy_name: str = Field(..., description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV (overrides data_dir)")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")


class OptimizeRequest(BaseModel):
    """Request body for /run_optimize."""

    strategy_name: str = Field(..., description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    param_grid: list[dict[str, float | int | str]] | None = Field(default=None, description="Explicit param grid (overrides auto)")
    method: str = Field(default="grid", description="grid | bayesian | random")
    n_trials: int = Field(default=50, description="Trials for bayesian/random")
    objective: str = Field(default="sharpe", description="sharpe | return | pnl")
    constraints: OptimizationConstraints | None = Field(default=None, description="Hard limits (min_trades, max_drawdown_pct, etc.)")
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")


class ExportRequest(BaseModel):
    """Request body for /run_export."""

    strategy_name: str = Field(..., description="Strategy label")
    params: dict[str, float | int | str] = Field(default_factory=dict, description="Best params from optimize")
    target: str = Field(default="nautilus", description="nautilus | tradingview | alpaca | quantconnect")


class PipelineRequest(BaseModel):
    """Request body for /run_pipeline (research -> backtest -> optimize -> export)."""

    strategy_name: str = Field(..., description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    export_target: str = Field(default="nautilus", description="Export target")
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")


@app.get("/health")
def health() -> dict[str, str]:
    """Health check for Docker and DigiGraph."""
    return {"status": "ok", "service": "digiquant"}


@app.get("/check_drift", response_model=AddmResult)
def api_check_drift(strategy_id: str = "mean_reversion_tech", baseline_run_id: str | None = None) -> AddmResult:
    """Check ADDM drift for strategy. Phase 3: heartbeat calls this; if drift_detected, trigger re-optimize."""
    return check_drift(strategy_id=strategy_id, baseline_run_id=baseline_run_id)


@app.post("/run_backtest", response_model=BacktestResult)
def api_run_backtest(req: BacktestRequest) -> BacktestResult:
    """Run a real NautilusTrader backtest. Requires data_path or data_dir (no defaults)."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        result = run_backtest(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log("run_backtest", agent_id="digiquant", payload={"strategy_name": req.strategy_name, "symbols": req.symbols, "run_id": result.run_id})
    return result


@app.post("/run_optimize", response_model=OptimizeResult)
def api_run_optimize(req: OptimizeRequest) -> OptimizeResult:
    """Run parameter optimization (grid, bayesian, or random). Requires Nautilus."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        result = run_optimize(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            param_grid=req.param_grid,
            method=req.method,
            n_trials=req.n_trials,
            objective=req.objective,
            constraints=req.constraints,
            data_path=req.data_path,
            data_dir=req.data_dir,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log("run_optimize", agent_id="digiquant", payload={"strategy_name": req.strategy_name, "run_id": result.run_id, "num_evaluations": result.num_evaluations})
    return result


@app.post("/run_export", response_model=ExportResult)
def api_run_export(req: ExportRequest) -> ExportResult:
    """Export strategy config to artifact (JSON). Platform deploy not implemented for all targets."""
    try:
        return run_export(
            strategy_name=req.strategy_name,
            params=req.params,
            target=req.target,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/run_pipeline")
def api_run_pipeline(req: PipelineRequest) -> dict[str, BacktestResult | OptimizeResult | ExportResult]:
    """Run full pipeline: backtest -> optimize -> export. Requires data_path or data_dir."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        bt = run_backtest(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
        )
        opt = run_optimize(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    best_params = opt.best_params if opt.best_backtest else {}
    try:
        exp = run_export(strategy_name=req.strategy_name, params=best_params, target=req.export_target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"backtest": bt, "optimize": opt, "export": exp}
