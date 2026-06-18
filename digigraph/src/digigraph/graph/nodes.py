"""Graph nodes: research (LLM), backtest (DigiQuant). Phase 1."""

from __future__ import annotations

import json
import logging
import os
import time

import httpx
from digibase.http import outbound_service_headers
from digibase.http_client import sync_client

from digigraph.graph.research import _stream_callback_ctx, research_node
from digigraph.graph.state import WorkflowState
from digigraph.trading_profile import optimization_constraints_dict_from_profile
from digigraph.trace_events import TraceEventV1

logger = logging.getLogger(__name__)

DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")
DIGIQUANT_DATA_DIR = os.environ.get("DIGIQUANT_DATA_DIR")

_DIGIQUANT_CLIENT_ERRORS = (
    httpx.HTTPStatusError,
    httpx.RequestError,
    json.JSONDecodeError,
    OSError,
    TypeError,
    ValueError,
)

__all__ = [
    "research_node",
    "backtest_node",
    "optimize_node",
    "strategy_validator_node",
    "supervisor_node",
    "_stream_callback_ctx",
]


def _digiquant_outbound_headers(state: WorkflowState) -> dict[str, str]:
    bearer = state.get("digi_bearer")
    bearer = str(bearer).strip() if bearer else None
    return outbound_service_headers(state.get("request_id"), bearer)


def _resolve_stream_callback(
    state: WorkflowState,
    config: dict | None,
) -> object | None:
    cb = None
    if config and isinstance(config.get("configurable"), dict):
        cb = config["configurable"].get("stream_callback")
    if cb is None:
        cb = state.get("stream_callback")
    if cb is None:
        cb = _stream_callback_ctx.get()
    return cb


def supervisor_node(state: WorkflowState, config: dict | None = None) -> dict:
    """Optional entry node: trace span + depth budget (set DIGI_SUPERVISOR=1)."""
    max_d = int(os.environ.get("DIGI_SUPERVISOR_MAX_DEPTH", "8"))
    depth = state.get("supervisor_depth_remaining")
    if depth is None:
        depth = max_d
    cb = _resolve_stream_callback(state, config)
    if cb is not None and callable(cb):
        ev = TraceEventV1(
            type="span",
            workflow_id=state.get("workflow_id"),
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            payload={"node": "supervisor", "depth_remaining": depth},
        )
        cb("trace", ev.model_dump())
    if depth <= 0:
        return {"error": "supervisor: max routing depth exceeded", "supervisor_depth_remaining": 0}
    return {"supervisor_depth_remaining": depth - 1, "supervisor_route": "research"}


def strategy_validator_node(state: WorkflowState, config: dict | None = None) -> dict:
    """Ensure quant backtest inputs exist before calling DigiQuant."""
    if state.get("error"):
        return {}
    cb = _resolve_stream_callback(state, config)
    if cb is not None and callable(cb):
        ev = TraceEventV1(
            type="graph_step",
            workflow_id=state.get("workflow_id"),
            request_id=state.get("request_id"),
            session_id=state.get("session_id"),
            payload={"node": "validate_strategy", "status": "start"},
        )
        cb("trace", ev.model_dump())
    strategy_name = state.get("strategy_name")
    symbols = state.get("symbols")
    if not strategy_name or not isinstance(strategy_name, str) or not strategy_name.strip():
        return {"error": "strategy_validator: missing strategy_name for backtest."}
    if not symbols or not isinstance(symbols, list) or len(symbols) == 0:
        return {"error": "strategy_validator: symbols must be a non-empty list."}
    if os.environ.get("DIGI_REQUIRE_TRADING_PROFILE", "").strip().lower() in ("1", "true", "yes"):
        tp = state.get("trading_profile")
        if not tp or not isinstance(tp, dict):
            return {
                "error": "strategy_validator: trading_profile required when DIGI_REQUIRE_TRADING_PROFILE is enabled.",
            }
    merged_oc: dict = {}
    existing_oc = state.get("optimization_constraints")
    if isinstance(existing_oc, dict):
        merged_oc.update(existing_oc)
    from_profile = optimization_constraints_dict_from_profile(state.get("trading_profile"))
    if from_profile:
        merged_oc.update(from_profile)
    if merged_oc:
        return {"optimization_constraints": merged_oc}
    return {}


def backtest_node(state: WorkflowState) -> dict:
    """Call DigiQuant backtest; write result or error into state. Requires strategy_name and symbols.

    Prefers **POST /v1/jobs/backtest** + **GET /v1/jobs/{id}/status** polling, then
    **GET /backtest/{job_id}/result**. Otherwise uses /backtest/start + SSE progress, then
    synchronous **POST /run_backtest** for minimal DigiQuant deployments.
    Progress events are logged at DEBUG level.
    """
    if state.get("error"):
        return {"backtest_result": None, "error": state.get("error")}
    strategy_name = state.get("strategy_name")
    symbols = state.get("symbols")
    if not strategy_name or not symbols or not isinstance(symbols, list) or len(symbols) == 0:
        return {
            "backtest_result": None,
            "error": "strategy_name and symbols (non-empty list) required. Research node must provide them.",
        }
    if not DIGIQUANT_DATA_DIR:
        return {
            "backtest_result": None,
            "error": "DIGIQUANT_DATA_DIR env required. Set path to directory with {symbol}.csv files.",
        }
    payload: dict = {
        "strategy_name": strategy_name,
        "symbols": symbols,
        "data_dir": DIGIQUANT_DATA_DIR,
    }
    params = state.get("strategy_params")
    if params and isinstance(params, dict) and len(params) > 0:
        payload["strategy_params"] = params
    base_url = DIGIQUANT_URL.rstrip("/")
    req_headers = _digiquant_outbound_headers(state)

    try:
        with sync_client(timeout=60.0) as client:
            used_v1_jobs = False
            start_r = client.post(f"{base_url}/v1/jobs/backtest", json=payload, headers=req_headers)
            if start_r.status_code == 404:
                start_r = client.post(
                    f"{base_url}/backtest/start", json=payload, headers=req_headers
                )
            elif start_r.status_code == 200:
                used_v1_jobs = True
            else:
                start_r.raise_for_status()

            if start_r.status_code == 200:
                job_id = start_r.json().get("job_id")
                if job_id:
                    if used_v1_jobs:
                        deadline = time.monotonic() + 120.0
                        while time.monotonic() < deadline:
                            st_r = client.get(
                                f"{base_url}/v1/jobs/{job_id}/status",
                                headers=req_headers,
                            )
                            st_r.raise_for_status()
                            st = st_r.json()
                            if st.get("status") == "failed":
                                return {
                                    "backtest_result": None,
                                    "error": st.get("error") or "Backtest failed",
                                }
                            if st.get("status") == "completed":
                                break
                            time.sleep(0.5)
                        else:
                            return {
                                "backtest_result": None,
                                "error": "Backtest job timed out waiting for completion.",
                            }
                    else:
                        with client.stream(
                            "GET",
                            f"{base_url}/backtest/{job_id}/progress",
                            timeout=90.0,
                            headers=req_headers,
                        ) as stream:
                            for line in stream.iter_lines():
                                if line.startswith("data: "):
                                    try:
                                        event = json.loads(line[6:])
                                        logger.debug("Backtest progress [%s]: %s", job_id, event)
                                        if event.get("event") == "done":
                                            break
                                        if event.get("event") == "error":
                                            return {
                                                "backtest_result": None,
                                                "error": event.get("detail", "Backtest failed"),
                                            }
                                    except json.JSONDecodeError:
                                        continue
                    result_r = client.get(
                        f"{base_url}/backtest/{job_id}/result",
                        timeout=10.0,
                        headers=req_headers,
                    )
                    result_r.raise_for_status()
                    return {
                        "backtest_result": result_r.json(),
                        "error": None,
                        "backtest_job_id": str(job_id),
                    }

            r = client.post(
                f"{base_url}/run_backtest", json=payload, timeout=60.0, headers=req_headers
            )
            r.raise_for_status()
            return {"backtest_result": r.json(), "error": None}
    except _DIGIQUANT_CLIENT_ERRORS as e:
        return {"backtest_result": None, "error": str(e)}


def optimize_node(state: WorkflowState) -> dict:
    """Call DigiQuant POST /run_optimize after a successful backtest. Requires strategy_name, symbols, DIGIQUANT_DATA_DIR."""
    if state.get("error"):
        return {"optimize_result": None, "optimize_error": None}
    strategy_name = state.get("strategy_name")
    symbols = state.get("symbols")
    if not strategy_name or not symbols or not isinstance(symbols, list) or len(symbols) == 0:
        return {
            "optimize_result": None,
            "optimize_error": "optimize_node: strategy_name and symbols required.",
        }
    if not DIGIQUANT_DATA_DIR:
        return {
            "optimize_result": None,
            "optimize_error": "DIGIQUANT_DATA_DIR env required for optimize.",
        }
    payload: dict = {
        "strategy_name": strategy_name,
        "symbols": symbols,
        "data_dir": DIGIQUANT_DATA_DIR,
        "method": os.environ.get("DIGIQUANT_OPTIMIZE_METHOD", "grid"),
        "n_trials": int(os.environ.get("DIGIQUANT_OPTIMIZE_N_TRIALS", "50")),
    }
    oc = state.get("optimization_constraints")
    if oc and isinstance(oc, dict) and len(oc) > 0:
        payload["constraints"] = oc
    base_url = DIGIQUANT_URL.rstrip("/")
    req_headers = _digiquant_outbound_headers(state)
    try:
        with sync_client(timeout=300.0) as client:
            r = client.post(f"{base_url}/run_optimize", json=payload, headers=req_headers)
            r.raise_for_status()
            return {"optimize_result": r.json(), "optimize_error": None}
    except _DIGIQUANT_CLIENT_ERRORS as e:
        return {"optimize_result": None, "optimize_error": str(e)}
