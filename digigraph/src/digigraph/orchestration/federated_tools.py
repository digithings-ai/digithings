"""Federated hub delegate tools (digiquant pipeline)."""

from __future__ import annotations

import json
import logging
from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.tool_common import (
    _ORCHESTRATOR_CLIENT_ERRORS,
    _digi_bearer_from_context,
    _digiquant_service_base,
)

logger = logging.getLogger(__name__)


def _invoke_dq(*args, **kwargs):
    from digigraph.orchestration import builtin as _reg

    return _reg.invoke_digiquant_tool(*args, **kwargs)


def _fetch_dq(*args, **kwargs):
    from digigraph.orchestration import builtin as _reg

    return _reg.fetch_digiquant_tool_dicts(*args, **kwargs)


def _schema_digiquant_pipeline_delegate(ctx: ToolContext) -> dict[str, Any]:
    try:
        by_name = _fetch_dq(
            _digiquant_service_base(),
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get("digiquant_pipeline_delegate") or by_name.get("digiquant_run_pipeline")
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("digiquant manifest fetch failed: %s", exc)
    return {
        "type": "function",
        "function": {
            "name": "digiquant_pipeline_delegate",
            "description": "Run digiquant pipeline. Requires DIGIQUANT_URL and POST /v1/orchestrator_tools.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def _handle_digiquant_pipeline_delegate(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    sym_raw = args.get("symbols")
    if isinstance(sym_raw, str):
        symbols = [sym_raw.strip().upper()] if sym_raw.strip() else []
    elif isinstance(sym_raw, list):
        symbols = [str(s).strip().upper() for s in sym_raw if s is not None and str(s).strip()]
    else:
        symbols = []
    strategy = str(args.get("strategy_name") or "").strip()
    if not strategy or not symbols:
        return {"content": json.dumps({"error": "strategy_name and non-empty symbols required"})}
    payload: dict[str, Any] = {
        "strategy_name": strategy,
        "symbols": symbols,
        "data_path": args.get("data_path"),
        "data_dir": args.get("data_dir"),
        "strategy_params": args.get("strategy_params"),
        "export_target": args.get("export_target") or "nautilus",
        "run_optimize": bool(args.get("run_optimize", True)),
        "run_export": bool(args.get("run_export", True)),
        "method": str(args.get("method") or "grid"),
        "n_trials": int(args.get("n_trials") or 50),
        "constraints": args.get("constraints"),
    }
    try:
        inv = _invoke_dq(
            _digiquant_service_base(),
            "digiquant_pipeline_delegate",
            payload,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return json.dumps({"ok": False, "error": str(e)})
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return json.dumps(inv)
    return {
        "content": json.dumps(
            {
                k: data.get(k)
                for k in ("trace", "backtest", "optimize", "export", "error")
                if k in data
            },
            default=str,
        ),
        "service": "digiquant",
        "trace": data.get("trace"),
    }
