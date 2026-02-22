"""DigiQuant HTTP API for DigiGraph. Phase 2: backtest, optimize, export, pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from digiquant.addm import AddmResult, check_drift
from digiquant.audit import audit_log as dq_audit_log
from digiquant.backtest import run_backtest
from digiquant.export import run_export
from digiquant.models import BacktestResult, ExportResult, OptimizeResult
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

    strategy_name: str = Field(default="mean_reversion_tech", description="Strategy or idea label")
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "GOOGL"], description="Instruments")


class OptimizeRequest(BaseModel):
    """Request body for /run_optimize."""

    strategy_name: str = Field(default="mean_reversion_tech", description="Strategy label")
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "GOOGL"], description="Instruments")
    param_grid: list[dict[str, float | int | str]] | None = Field(default=None, description="Optional param grid")
    objective: str = Field(default="sharpe", description="sharpe | return | pnl")


class ExportRequest(BaseModel):
    """Request body for /run_export."""

    strategy_name: str = Field(..., description="Strategy label")
    params: dict[str, float | int | str] = Field(default_factory=dict, description="Best params from optimize")
    target: str = Field(default="nautilus", description="nautilus | tradingview | alpaca | quantconnect")


class PipelineRequest(BaseModel):
    """Request body for /run_pipeline (research -> backtest -> optimize -> export)."""

    strategy_name: str = Field(default="mean_reversion_tech", description="Strategy label")
    symbols: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "GOOGL"], description="Instruments")
    export_target: str = Field(default="nautilus", description="Export target")


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
    """Run a real NautilusTrader backtest. Requires digiquant[nautilus] and test data."""
    try:
        result = run_backtest(strategy_name=req.strategy_name, symbols=req.symbols or None)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log("run_backtest", agent_id="digiquant", payload={"strategy_name": req.strategy_name, "symbols": req.symbols, "run_id": result.run_id})
    return result


@app.post("/run_optimize", response_model=OptimizeResult)
def api_run_optimize(req: OptimizeRequest) -> OptimizeResult:
    """Run parameter optimization (grid over backtests). Requires Nautilus."""
    try:
        result = run_optimize(
            strategy_name=req.strategy_name,
            symbols=req.symbols or None,
            param_grid=req.param_grid,
            objective=req.objective,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log("run_optimize", agent_id="digiquant", payload={"strategy_name": req.strategy_name, "run_id": result.run_id, "num_evaluations": result.num_evaluations})
    return result


@app.post("/run_export", response_model=ExportResult)
def api_run_export(req: ExportRequest) -> ExportResult:
    """Export strategy config to artifact (JSON). Platform deploy not implemented for all targets."""
    return run_export(
        strategy_name=req.strategy_name,
        params=req.params or None,
        target=req.target,
    )


@app.post("/run_pipeline")
def api_run_pipeline(req: PipelineRequest) -> dict[str, BacktestResult | OptimizeResult | ExportResult]:
    """Run full pipeline: backtest -> optimize -> export. Requires Nautilus."""
    try:
        bt = run_backtest(strategy_name=req.strategy_name, symbols=req.symbols or None)
        opt = run_optimize(strategy_name=req.strategy_name, symbols=req.symbols or None)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    best_params = opt.best_params if opt.best_backtest else {}
    exp = run_export(strategy_name=req.strategy_name, params=best_params, target=req.export_target)
    return {"backtest": bt, "optimize": opt, "export": exp}
