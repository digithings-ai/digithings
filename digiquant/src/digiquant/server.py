"""DigiQuant HTTP API for DigiGraph. Phase 2: backtest, optimize, export, pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import threading
import uuid
from queue import Empty, Queue

from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)


def _subst_env(s: str) -> str:
    """Expand ${VAR} or $VAR patterns in *s* using current environment variables."""
    import re
    return re.sub(r"\$\{(\w+)\}|\$(\w+)", lambda m: os.environ.get(m.group(1) or m.group(2), ""), s)


def _allowed_origins() -> list[str]:
    """Read DIGI_ALLOWED_ORIGINS (comma-separated). Defaults to localhost origins when unset.

    Each origin may contain ``${VAR}`` references that are expanded from the environment,
    e.g. ``http://${API_HOST}:3000``.
    """
    raw = os.environ.get("DIGI_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return ["http://localhost:3000", "http://localhost:8000", "http://localhost:11434"]
    return [_subst_env(o.strip()) for o in raw.split(",") if o.strip()]

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
    allow_origins=_allowed_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


import time as _time
from collections import deque as _deque
from threading import Lock as _Lock

_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/run_backtest": (10, 60),
    "/run_optimize": (10, 60),
    "/run_pipeline": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health"}


def _rl_check(request: Request, max_req: int, window: int) -> JSONResponse | None:
    if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return None
    xff = request.headers.get("X-Forwarded-For")
    ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    if ip == "testclient":
        return None
    now = _time.monotonic()
    cutoff = now - window
    with _rl_lock:
        if ip not in _rl_windows:
            _rl_windows[ip] = _deque()
        q = _rl_windows[ip]
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_req:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {max_req} requests per {window}s."},
                headers={"Retry-After": str(window)},
            )
        q.append(now)
    return None


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """Per-IP rate limiting. /run_backtest and /run_optimize: 10/min; others: 30/min."""
    path = request.url.path
    if path not in _UNLIMITED_PATHS:
        max_req, window = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        result = _rl_check(request, max_req, window)
        if result is not None:
            return result
    return await call_next(request)


@app.middleware("http")
async def api_key_auth(request: Request, call_next):
    """Require Authorization: Bearer <DIGI_API_KEY> when DIGI_API_KEY env var is set. Health endpoint is exempt."""
    api_key = os.environ.get("DIGI_API_KEY", "").strip()
    if api_key and request.url.path not in ("/health",):
        auth_header = request.headers.get("Authorization", "")
        if not secrets.compare_digest(auth_header, f"Bearer {api_key}"):
            logger.warning("Unauthorized request to %s from %s", request.url.path, request.client)
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    """Propagate X-Request-ID header; generate one if absent."""
    req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


class BacktestRequest(BaseModel):
    """Request body for /run_backtest."""

    strategy_name: str = Field(..., description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV (overrides data_dir)")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")
    tearsheet_path: str | None = Field(default=None, description="Write HTML tearsheet to this path")
    full_tearsheet: bool = Field(default=True, description="Include extended charts (distributions, rolling metrics). Set false for faster results.")


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
            tearsheet_path=req.tearsheet_path,
            full_tearsheet=req.full_tearsheet,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log("run_backtest", agent_id="digiquant", payload={"strategy_name": req.strategy_name, "symbols": req.symbols, "run_id": result.run_id})
    return result


# ---------------------------------------------------------------------------
# Async backtest with SSE progress stream
# ---------------------------------------------------------------------------

# job_id -> {"queue": Queue, "result": BacktestResult | None, "error": str | None, "done": bool}
_backtest_jobs: dict[str, dict] = {}
_BACKTEST_JOB_TTL_SECS = 300  # jobs expire after 5 minutes


def _run_backtest_job(job_id: str, req: "BacktestRequest") -> None:
    """Run backtest in background thread; publish SSE events to the job queue."""
    q: Queue = _backtest_jobs[job_id]["queue"]
    try:
        q.put(json.dumps({"event": "start", "job_id": job_id, "strategy": req.strategy_name, "symbols": req.symbols}))
        result = run_backtest(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
            tearsheet_path=req.tearsheet_path,
            full_tearsheet=req.full_tearsheet,
        )
        _backtest_jobs[job_id]["result"] = result
        q.put(json.dumps({"event": "done", "job_id": job_id, "run_id": result.run_id,
                          "total_pnl": result.total_pnl, "sharpe_ratio": result.sharpe_ratio,
                          "num_trades": result.num_trades, "status": result.status}))
    except Exception as e:
        logger.error("Backtest job %s failed: %s", job_id, e)
        _backtest_jobs[job_id]["error"] = str(e)
        q.put(json.dumps({"event": "error", "job_id": job_id, "detail": str(e)}))
    finally:
        _backtest_jobs[job_id]["done"] = True
        q.put(None)  # Sentinel: SSE generator should close


@app.post("/backtest/start")
async def api_start_backtest(req: BacktestRequest) -> dict:
    """Submit a backtest job. Returns job_id immediately.

    Poll progress via GET /backtest/{job_id}/progress (SSE).
    Retrieve the final result via GET /backtest/{job_id}/result.
    """
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(status_code=400, detail="data_path or data_dir required.")
    job_id = uuid.uuid4().hex
    _backtest_jobs[job_id] = {"queue": Queue(), "result": None, "error": None, "done": False}
    thread = threading.Thread(target=_run_backtest_job, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.get("/backtest/{job_id}/progress")
async def api_backtest_progress(job_id: str) -> StreamingResponse:
    """SSE stream of backtest progress events for *job_id*.

    Events are JSON objects with an ``event`` field (``start`` | ``done`` | ``error``).
    The stream closes once the job completes or errors.
    """
    if job_id not in _backtest_jobs:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")

    async def event_generator():
        q: Queue = _backtest_jobs[job_id]["queue"]
        while True:
            try:
                item = await asyncio.get_event_loop().run_in_executor(None, lambda: q.get(timeout=30))
                if item is None:
                    break
                yield f"data: {item}\n\n"
            except Empty:
                yield "data: {\"event\": \"heartbeat\"}\n\n"
            except Exception as e:
                yield f"data: {{\"event\": \"error\", \"detail\": \"{e}\"}}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/backtest/{job_id}/result", response_model=BacktestResult)
async def api_backtest_result(job_id: str) -> BacktestResult:
    """Return the final BacktestResult for a completed job. 404 if not found; 202 if still running."""
    job = _backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
    if not job["done"]:
        raise HTTPException(status_code=202, detail="Job still running. Poll /progress for updates.")
    if job["error"]:
        raise HTTPException(status_code=500, detail=job["error"])
    if job["result"] is None:
        raise HTTPException(status_code=503, detail="Backtest returned no result.")
    return job["result"]


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
