"""DigiQuant HTTP API for DigiGraph. Phase 2: backtest, optimize, export, pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from queue import Empty, Queue
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from digibase.cors import install_cors
from digibase.errors import json_error_response, register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics
from digibase.otel import setup_otel_fastapi
from digikey.integrations.service_middleware import DigiAuthMiddleware, digiquant_path_scopes

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

logger = logging.getLogger(__name__)

from digiquant import __version__
from digiquant.addm import AddmResult, check_drift, record_sharpe
from digiquant.audit import audit_log as dq_audit_log
from digiquant.models import BacktestResult, ExportResult, OptimizeResult, OptimizationConstraints
from digiquant.graph.pipeline import run_quant_workflow
from digiquant.service import (
    service_list_strategies,
    service_run_backtest,
    service_run_export,
    service_run_optimize,
)

app = FastAPI(
    title="DigiQuant",
    description="High-perf backtest/optimize/export API for DigiGraph (MCP in Phase 2)",
    version=__version__,
)
install_metrics(app, service="digiquant", version=__version__)
install_cors(app, service="digiquant")
app.add_middleware(DigiAuthMiddleware, service="digiquant", path_scopes=digiquant_path_scopes)


import time as _time
from collections import deque as _deque
from threading import Lock as _Lock

_rl_windows: dict[str, _deque] = {}
_rl_lock = _Lock()
_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/run_backtest": (10, 60),
    "/run_optimize": (10, 60),
    "/run_pipeline": (10, 60),
    "/v1/workflow": (10, 60),
    "/v1/jobs/backtest": (10, 60),
    "/v1/orchestrator_tools": (30, 60),
    "/v1/orchestrator_invoke": (10, 60),
}
_DEFAULT_RATE_LIMIT = (30, 60)
_UNLIMITED_PATHS = {"/health", "/healthz"}


def _rl_check(request: Request, max_req: int, window: int) -> JSONResponse | None:
    if os.environ.get("DIGI_DISABLE_RATE_LIMIT", "").lower() in ("1", "true", "yes"):
        return None
    xff = request.headers.get("X-Forwarded-For")
    ip = (
        xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")
    )
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
            return json_error_response(
                status_code=429,
                code="rate_limit_exceeded",
                message=f"Rate limit exceeded: {max_req} requests per {window}s.",
                request=request,
                service="digiquant",
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


install_request_id_middleware(app)
install_request_id_logging()


class BacktestRequest(BaseModel):
    """Request body for /run_backtest."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str = Field(..., min_length=1, description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    data_path: str | None = Field(
        default=None, description="Path to single OHLCV CSV (overrides data_dir)"
    )
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")
    strategy_params: dict[str, float | int | str] | None = Field(
        default=None,
        description="Optional strategy parameters (e.g. fast_ema_period, slow_ema_period)",
    )
    tearsheet_path: str | None = Field(
        default=None, description="Write HTML tearsheet to this path"
    )
    full_tearsheet: bool = Field(
        default=True,
        description="Include extended charts (distributions, rolling metrics). Set false for faster results.",
    )


class OptimizeRequest(BaseModel):
    """Request body for /run_optimize."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str = Field(..., min_length=1, description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    param_grid: list[dict[str, float | int | str]] | None = Field(
        default=None, description="Explicit param grid (overrides auto)"
    )
    method: str = Field(default="grid", description="grid | bayesian | random")
    n_trials: int = Field(default=50, description="Trials for bayesian/random")
    objective: str = Field(default="sharpe", description="sharpe | return | pnl")
    constraints: OptimizationConstraints | None = Field(
        default=None, description="Hard limits (min_trades, max_drawdown_pct, etc.)"
    )
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")


class ExportRequest(BaseModel):
    """Request body for /run_export."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str = Field(..., min_length=1, description="Strategy label")
    params: dict[str, float | int | str] = Field(
        default_factory=dict, description="Best params from optimize"
    )
    target: str = Field(
        default="nautilus",
        description="nautilus | nautilus_bundle | tradingview | alpaca | quantconnect",
    )


class PipelineRequest(BaseModel):
    """Request body for /run_pipeline and POST /v1/workflow (internal LangGraph pipeline)."""

    model_config = ConfigDict(extra="forbid")

    strategy_name: str = Field(..., min_length=1, description="Strategy name (required)")
    symbols: list[str] = Field(..., min_length=1, description="Instruments (required)")
    export_target: str = Field(default="nautilus", description="Export target")
    data_path: str | None = Field(default=None, description="Path to single OHLCV CSV")
    data_dir: str | None = Field(default=None, description="Directory with {symbol}.csv files")
    strategy_params: dict[str, float | int | str] | None = Field(
        default=None,
        description="Optional params for the initial backtest before optimize",
    )
    run_optimize: bool = Field(default=True, description="Run optimize after backtest")
    run_export: bool = Field(
        default=True, description="Run export after optimize (if policy allows)"
    )
    method: str = Field(default="grid", description="Optimization method")
    n_trials: int = Field(default=50, ge=1, description="Max trials / grid size hint")
    constraints: OptimizationConstraints | None = Field(
        default=None,
        description="Hard optimization limits (min_trades, max_drawdown_pct, …)",
    )


def _pipeline_requires_export(req: PipelineRequest) -> bool:
    if not req.run_export:
        return False
    return os.environ.get("DIGIQUANT_ALLOW_EXPORT", "1").strip().lower() in ("1", "true", "yes")


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check for Docker and DigiGraph (kept for back-compat)."""
    return {"status": "ok", "service": "digiquant"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. Pair with DigiSmith's ``/v1/status``
    for richer diagnostics.
    """
    return {"ok": True}


@app.get("/strategies")
def api_list_strategies() -> list[dict]:
    """Registered Nautilus strategies (name, aliases, description, default_params)."""
    return service_list_strategies()


@app.get("/check_drift", response_model=AddmResult)
def api_check_drift(
    strategy_id: str = "mean_reversion_tech",
    baseline_run_id: str | None = None,
    current_sharpe: float | None = None,
) -> AddmResult:
    """Check ADDM drift for strategy. Phase 3: heartbeat calls this; if drift_detected, trigger re-optimize."""
    return check_drift(
        strategy_id=strategy_id,
        baseline_run_id=baseline_run_id,
        current_sharpe=current_sharpe,
    )


@app.post("/run_backtest", response_model=BacktestResult)
def api_run_backtest(req: BacktestRequest) -> BacktestResult:
    """Run a real NautilusTrader backtest. Requires data_path or data_dir (no defaults)."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        result = service_run_backtest(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
            strategy_params=req.strategy_params,
            tearsheet_path=req.tearsheet_path,
            full_tearsheet=req.full_tearsheet,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    dq_audit_log(
        "run_backtest",
        agent_id="digiquant",
        payload={
            "strategy_name": req.strategy_name,
            "symbols": req.symbols,
            "run_id": result.run_id,
        },
    )
    if result.sharpe_ratio is not None:
        record_sharpe(req.strategy_name, result.sharpe_ratio)
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
        q.put(
            json.dumps(
                {
                    "event": "start",
                    "job_id": job_id,
                    "strategy": req.strategy_name,
                    "symbols": req.symbols,
                }
            )
        )
        result = service_run_backtest(
            strategy_name=req.strategy_name,
            symbols=req.symbols,
            data_path=req.data_path,
            data_dir=req.data_dir,
            strategy_params=req.strategy_params,
            tearsheet_path=req.tearsheet_path,
            full_tearsheet=req.full_tearsheet,
        )
        _backtest_jobs[job_id]["result"] = result
        q.put(
            json.dumps(
                {
                    "event": "done",
                    "job_id": job_id,
                    "run_id": result.run_id,
                    "total_pnl": result.total_pnl,
                    "sharpe_ratio": result.sharpe_ratio,
                    "num_trades": result.num_trades,
                    "status": result.status,
                }
            )
        )
    except Exception as e:
        logger.error("Backtest job %s failed: %s", job_id, e)
        _backtest_jobs[job_id]["error"] = str(e)
        q.put(json.dumps({"event": "error", "job_id": job_id, "detail": str(e)}))
    finally:
        _backtest_jobs[job_id]["done"] = True
        q.put(None)  # Sentinel: SSE generator should close


def _submit_backtest_job(req: BacktestRequest) -> dict:
    """Create async backtest job; return ``{"job_id": ...}``."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(status_code=400, detail="data_path or data_dir required.")
    job_id = uuid.uuid4().hex
    _backtest_jobs[job_id] = {"queue": Queue(), "result": None, "error": None, "done": False}
    thread = threading.Thread(target=_run_backtest_job, args=(job_id, req), daemon=True)
    thread.start()
    return {"job_id": job_id}


@app.post("/backtest/start")
async def api_start_backtest(req: BacktestRequest) -> dict:
    """Submit a backtest job. Returns job_id immediately.

    Poll progress via GET /backtest/{job_id}/progress (SSE).
    Retrieve the final result via GET /backtest/{job_id}/result.
    """
    return _submit_backtest_job(req)


v1 = APIRouter(prefix="/v1", tags=["v1"])


class OrchestratorInvokeRequest(BaseModel):
    """Request for POST /v1/orchestrator_invoke (hub tool dispatch)."""

    tool: str = Field(..., description="digiquant_* tool name from orchestrator manifest")
    arguments: dict[str, Any] = Field(default_factory=dict)


@v1.post("/orchestrator_tools")
def v1_orchestrator_tools() -> dict[str, Any]:
    """Return OpenAI-style tools owned by DigiQuant (for DigiGraph orchestration)."""
    from digiquant.orchestrator_tools import build_orchestrator_tool_manifest

    return {"tools": build_orchestrator_tool_manifest(), "version": 1}


def _normalize_symbols(raw: Any) -> list[str]:
    if isinstance(raw, str):
        s = raw.strip()
        return [s.upper()] if s else []
    if isinstance(raw, list):
        return [str(s).strip().upper() for s in raw if s is not None and str(s).strip()]
    return []


@v1.post("/orchestrator_invoke")
def v1_orchestrator_invoke(req: OrchestratorInvokeRequest) -> dict[str, Any]:
    """Execute one DigiQuant orchestrator tool (DigiGraph hub dispatch)."""
    tool = (req.tool or "").strip()
    args = req.arguments if isinstance(req.arguments, dict) else {}

    if tool == "digiquant_list_strategies":
        data = service_list_strategies()
        return {"ok": True, "service": "digiquant", "tool": tool, "data": data}

    if tool == "digiquant_run_backtest":
        symbols = _normalize_symbols(args.get("symbols"))
        if not symbols or not args.get("strategy_name"):
            return {"ok": False, "error": "strategy_name and non-empty symbols required"}
        bt_req = BacktestRequest(
            strategy_name=str(args["strategy_name"]),
            symbols=symbols,
            data_path=args.get("data_path"),
            data_dir=args.get("data_dir"),
            strategy_params=args.get("strategy_params"),
            tearsheet_path=args.get("tearsheet_path"),
            full_tearsheet=bool(args.get("full_tearsheet", True)),
        )
        try:
            if bt_req.data_path is None and bt_req.data_dir is None:
                return {"ok": False, "error": "data_path or data_dir required"}
            result = service_run_backtest(
                strategy_name=bt_req.strategy_name,
                symbols=bt_req.symbols,
                data_path=bt_req.data_path,
                data_dir=bt_req.data_dir,
                strategy_params=bt_req.strategy_params,
                tearsheet_path=bt_req.tearsheet_path,
                full_tearsheet=bt_req.full_tearsheet,
            )
        except (ValueError, RuntimeError) as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "service": "digiquant",
            "tool": tool,
            "data": result.model_dump(mode="json"),
        }

    if tool == "digiquant_run_optimize":
        symbols = _normalize_symbols(args.get("symbols"))
        if not symbols or not args.get("strategy_name"):
            return {"ok": False, "error": "strategy_name and non-empty symbols required"}
        constraints = None
        if args.get("constraints"):
            try:
                constraints = OptimizationConstraints.model_validate(args["constraints"])
            except Exception as e:
                return {"ok": False, "error": f"invalid constraints: {e}"}
        try:
            if args.get("data_path") is None and args.get("data_dir") is None:
                return {"ok": False, "error": "data_path or data_dir required"}
            result = service_run_optimize(
                strategy_name=str(args["strategy_name"]),
                symbols=symbols,
                param_grid=args.get("param_grid"),
                method=str(args.get("method") or "grid"),
                n_trials=int(args.get("n_trials") or 50),
                objective=str(args.get("objective") or "sharpe"),
                constraints=constraints,
                data_path=args.get("data_path"),
                data_dir=args.get("data_dir"),
            )
        except RuntimeError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "service": "digiquant",
            "tool": tool,
            "data": result.model_dump(mode="json"),
        }

    if tool == "digiquant_run_export":
        if not args.get("strategy_name"):
            return {"ok": False, "error": "strategy_name required"}
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        try:
            result = service_run_export(
                strategy_name=str(args["strategy_name"]),
                params=params,
                target=str(args.get("target") or "nautilus"),
            )
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {
            "ok": True,
            "service": "digiquant",
            "tool": tool,
            "data": result.model_dump(mode="json"),
        }

    if tool in ("digiquant_run_pipeline", "digiquant_pipeline_delegate"):
        symbols = _normalize_symbols(args.get("symbols"))
        strategy = str(args.get("strategy_name") or "").strip()
        if not strategy or not symbols:
            return {"ok": False, "error": "strategy_name and non-empty symbols required"}
        constraints = None
        if args.get("constraints"):
            try:
                constraints = OptimizationConstraints.model_validate(args["constraints"])
            except Exception as e:
                return {"ok": False, "error": f"invalid constraints: {e}"}
        try:
            if args.get("data_path") is None and args.get("data_dir") is None:
                return {"ok": False, "error": "data_path or data_dir required"}
            raw = run_quant_workflow(
                {
                    "strategy_name": strategy,
                    "symbols": symbols,
                    "data_path": args.get("data_path"),
                    "data_dir": args.get("data_dir"),
                    "strategy_params": args.get("strategy_params"),
                    "export_target": str(args.get("export_target") or "nautilus"),
                    "run_optimize": bool(args.get("run_optimize", True)),
                    "run_export": bool(args.get("run_export", True)),
                    "method": str(args.get("method") or "grid"),
                    "n_trials": int(args.get("n_trials") or 50),
                    "constraints": constraints.model_dump(mode="json") if constraints else None,
                }
            )
        except (ValueError, RuntimeError) as e:
            return {"ok": False, "error": str(e)}
        if raw.get("error"):
            return {"ok": False, "error": str(raw["error"]), "data": raw}
        dq_audit_log(
            "v1_orchestrator_invoke_pipeline",
            agent_id="digiquant",
            payload={"strategy_name": strategy, "symbols": symbols, "tool": tool},
        )
        return {"ok": True, "service": "digiquant", "tool": tool, "data": raw}

    raise HTTPException(status_code=400, detail=f"Unknown orchestrator tool: {tool!r}")


@v1.post("/jobs/backtest")
async def v1_post_jobs_backtest(req: BacktestRequest) -> dict:
    """Versioned alias for async backtest submission (same as POST /backtest/start)."""
    return _submit_backtest_job(req)


@v1.post("/workflow")
def v1_post_workflow(req: PipelineRequest) -> dict[str, Any]:
    """Run the quant pipeline; returns JSON including ``trace`` and serialized step results."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        raw = run_quant_workflow(req.model_dump(mode="json"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if raw.get("error"):
        raise HTTPException(status_code=503, detail=str(raw["error"]))
    dq_audit_log(
        "v1_workflow",
        agent_id="digiquant",
        payload={"strategy_name": req.strategy_name, "symbols": req.symbols},
    )
    return raw


@v1.get("/jobs/{job_id}/status")
async def v1_get_job_status(job_id: str) -> dict:
    """Job lifecycle: ``running`` | ``completed`` | ``failed`` (DigiQuant backtest jobs)."""
    job = _backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
    if not job["done"]:
        status = "running"
    elif job["error"]:
        status = "failed"
    else:
        status = "completed"
    return {
        "job_id": job_id,
        "status": status,
        "done": job["done"],
        "error": job["error"],
    }


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
                item = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: q.get(timeout=30)
                )
                if item is None:
                    break
                yield f"data: {item}\n\n"
            except Empty:
                yield 'data: {"event": "heartbeat"}\n\n'
            except Exception as e:
                yield f'data: {{"event": "error", "detail": "{e}"}}\n\n'
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/backtest/{job_id}/result", response_model=BacktestResult)
async def api_backtest_result(job_id: str) -> BacktestResult:
    """Return the final BacktestResult for a completed job. 404 if not found; 202 if still running."""
    job = _backtest_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id!r}")
    if not job["done"]:
        raise HTTPException(
            status_code=202, detail="Job still running. Poll /progress for updates."
        )
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
        result = service_run_optimize(
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
    dq_audit_log(
        "run_optimize",
        agent_id="digiquant",
        payload={
            "strategy_name": req.strategy_name,
            "run_id": result.run_id,
            "num_evaluations": result.num_evaluations,
        },
    )
    return result


@app.post("/run_export", response_model=ExportResult)
def api_run_export(req: ExportRequest) -> ExportResult:
    """Export strategy config to artifact (JSON). Platform deploy not implemented for all targets."""
    try:
        return service_run_export(
            strategy_name=req.strategy_name,
            params=req.params,
            target=req.target,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/run_pipeline")
def api_run_pipeline(req: PipelineRequest) -> dict[str, Any]:
    """Run full pipeline via internal LangGraph (backtest → optional optimize → optional export)."""
    if req.data_path is None and req.data_dir is None:
        raise HTTPException(
            status_code=400,
            detail="data_path or data_dir required. Specify where OHLCV data lives.",
        )
    try:
        raw = run_quant_workflow(req.model_dump(mode="json"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    if raw.get("error"):
        raise HTTPException(status_code=503, detail=raw["error"])
    if not raw.get("backtest"):
        raise HTTPException(status_code=503, detail="Pipeline incomplete: backtest missing")
    if req.run_optimize and not raw.get("optimize"):
        raise HTTPException(status_code=503, detail="Pipeline incomplete: optimize missing")
    if _pipeline_requires_export(req) and not raw.get("export"):
        raise HTTPException(status_code=503, detail="Pipeline incomplete: export missing")
    out: dict[str, Any] = {"trace": raw.get("trace") or []}
    if raw.get("backtest"):
        out["backtest"] = BacktestResult.model_validate(raw["backtest"])
    if raw.get("optimize"):
        out["optimize"] = OptimizeResult.model_validate(raw["optimize"])
    if raw.get("export"):
        out["export"] = ExportResult.model_validate(raw["export"])
    return out


app.include_router(v1)

register_fastapi_error_handlers(app, service="digiquant")
setup_otel_fastapi(app, service_name="digiquant")
