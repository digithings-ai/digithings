"""LangGraph pipeline for DigiQuant: validate → backtest → optional optimize → optional export."""

from __future__ import annotations

import os
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from digiquant.models import BacktestResult, ExportResult, OptimizeResult, OptimizationConstraints
from digiquant.service import service_run_backtest, service_run_export, service_run_optimize


class PipelineTraceStep(TypedDict, total=False):
    """One pipeline trace entry — refs only, no embedded result bodies (SIMP-035)."""

    step: str
    status: str
    detail: str | None
    run_id: str | None


class QuantPipelineState(TypedDict, total=False):
    strategy_name: str
    symbols: list[str]
    data_path: str | None
    data_dir: str | None
    strategy_params: dict[str, float | int | str] | None
    constraints: OptimizationConstraints | None
    export_target: str
    run_optimize: bool
    run_export: bool
    method: str
    n_trials: int
    backtest: BacktestResult | None
    optimize: OptimizeResult | None
    export: ExportResult | None
    error: str | None
    trace: Annotated[list[PipelineTraceStep], add]


def _allow_export() -> bool:
    return os.environ.get("DIGIQUANT_ALLOW_EXPORT", "1").strip().lower() in ("1", "true", "yes")


def node_validate(state: QuantPipelineState) -> dict[str, Any]:
    err = None
    if not state.get("strategy_name") or not str(state.get("strategy_name")).strip():
        err = "strategy_name required"
    elif not state.get("symbols") or not isinstance(state["symbols"], list):
        err = "symbols must be a non-empty list"
    elif len(state["symbols"]) == 0:
        err = "symbols must be a non-empty list"
    elif not state.get("data_path") and not state.get("data_dir"):
        err = "data_path or data_dir required"
    if err:
        return {"error": err, "trace": [{"step": "validate", "status": "failed", "detail": err}]}
    return {"trace": [{"step": "validate", "status": "ok"}]}


def node_backtest(state: QuantPipelineState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    try:
        bt = service_run_backtest(
            strategy_name=str(state["strategy_name"]),
            symbols=list(state["symbols"]),
            data_path=state.get("data_path"),
            data_dir=state.get("data_dir"),
            strategy_params=state.get("strategy_params"),
        )
        return {
            "backtest": bt,
            "trace": [{"step": "backtest", "status": "ok", "run_id": bt.run_id}],
        }
    except Exception as e:
        msg = str(e)
        return {
            "error": msg,
            "trace": [{"step": "backtest", "status": "failed", "detail": msg}],
        }


def node_optimize(state: QuantPipelineState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    try:
        opt = service_run_optimize(
            strategy_name=str(state["strategy_name"]),
            symbols=list(state["symbols"]),
            data_path=state.get("data_path"),
            data_dir=state.get("data_dir"),
            method=str(state.get("method") or "grid"),
            n_trials=int(state.get("n_trials") or 50),
            constraints=state.get("constraints"),
        )
        return {
            "optimize": opt,
            "trace": [{"step": "optimize", "status": "ok", "run_id": opt.run_id}],
        }
    except Exception as e:
        msg = str(e)
        return {
            "error": msg,
            "trace": [{"step": "optimize", "status": "failed", "detail": msg}],
        }


def node_export(state: QuantPipelineState) -> dict[str, Any]:
    if state.get("error"):
        return {}
    if not _allow_export():
        return {
            "trace": [
                {"step": "export", "status": "skipped", "detail": "DIGIQUANT_ALLOW_EXPORT disabled"}
            ]
        }
    opt = state.get("optimize")
    params: dict[str, float | int | str] = {}
    if opt is not None and getattr(opt, "best_params", None):
        params = dict(opt.best_params)
    elif state.get("strategy_params"):
        params = dict(state["strategy_params"] or {})
    try:
        exp = service_run_export(
            strategy_name=str(state["strategy_name"]),
            params=params,
            target=str(state.get("export_target") or "nautilus"),
        )
        return {
            "export": exp,
            "trace": [{"step": "export", "status": "ok", "run_id": exp.run_id}],
        }
    except Exception as e:
        msg = str(e)
        return {
            "error": msg,
            "trace": [{"step": "export", "status": "failed", "detail": msg}],
        }


def route_after_validate(state: QuantPipelineState) -> str:
    if state.get("error"):
        return END
    return "backtest"


def route_after_backtest(state: QuantPipelineState) -> str:
    if state.get("error"):
        return END
    if state.get("run_optimize", True):
        return "optimize"
    if state.get("run_export", True) and _allow_export():
        return "export"
    return END


def route_after_optimize(state: QuantPipelineState) -> str:
    if state.get("error"):
        return END
    if state.get("run_export", True) and _allow_export():
        return "export"
    return END


_pipeline_graph_cache: object | None = None


def build_pipeline_graph():  # type: ignore[no-untyped-def]
    """Compile the quant pipeline graph once per process. Requires ``langgraph``."""
    global _pipeline_graph_cache
    if _pipeline_graph_cache is not None:
        return _pipeline_graph_cache
    g: StateGraph[QuantPipelineState] = StateGraph(QuantPipelineState)
    g.add_node("validate", node_validate)
    g.add_node("backtest", node_backtest)
    g.add_node("optimize", node_optimize)
    g.add_node("export", node_export)
    g.add_edge(START, "validate")
    g.add_conditional_edges("validate", route_after_validate, {"backtest": "backtest", END: END})
    g.add_conditional_edges(
        "backtest",
        route_after_backtest,
        {"optimize": "optimize", "export": "export", END: END},
    )
    g.add_conditional_edges("optimize", route_after_optimize, {"export": "export", END: END})
    g.add_edge("export", END)
    _pipeline_graph_cache = g.compile()
    return _pipeline_graph_cache


def run_quant_workflow(initial: dict[str, Any]) -> dict[str, Any]:
    """Run the compiled pipeline and return JSON-serializable dict (for HTTP/MCP)."""
    raw_constraints = initial.get("constraints")
    co: OptimizationConstraints | None
    if raw_constraints is None:
        co = None
    elif isinstance(raw_constraints, OptimizationConstraints):
        co = raw_constraints
    else:
        co = OptimizationConstraints.model_validate(raw_constraints)

    graph = build_pipeline_graph()
    state_in: QuantPipelineState = {  # type: ignore[assignment]
        "strategy_name": initial["strategy_name"],
        "symbols": list(initial["symbols"]),
        "data_path": initial.get("data_path"),
        "data_dir": initial.get("data_dir"),
        "strategy_params": initial.get("strategy_params"),
        "constraints": co,
        "export_target": initial.get("export_target") or "nautilus",
        "run_optimize": initial.get("run_optimize", True),
        "run_export": initial.get("run_export", True),
        "method": initial.get("method") or "grid",
        "n_trials": int(initial.get("n_trials") or 50),
        "trace": [],
    }
    out = graph.invoke(state_in)
    result: dict[str, Any] = {
        "error": out.get("error"),
        "trace": list(out.get("trace") or []),
    }
    bt = out.get("backtest")
    if bt is not None:
        result["backtest"] = bt.model_dump(mode="json")
    op = out.get("optimize")
    if op is not None:
        result["optimize"] = op.model_dump(mode="json")
    ex = out.get("export")
    if ex is not None:
        result["export"] = ex.model_dump(mode="json")
    return result
