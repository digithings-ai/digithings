"""Register built-in orchestrator tools and skills. Import this module to populate the registry."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from digigraph.agents.analysis.runner import run_analysis_agent
from digigraph.agents.analysis.schema import ANALYSIS_AGENT_TOOL
from digigraph.agents.data_engineer.runner import run_data_engineer_agent
from digigraph.agents.data_engineer.schema import DATA_ENGINEER_AGENT_TOOL
from digigraph.agents.data_manipulation.runner import run_data_manipulation_agent
from digigraph.agents.data_manipulation.schema import DATA_MANIPULATION_AGENT_TOOL
from digigraph.agents.data_prep.runner import run_data_prep_agent
from digigraph.agents.data_prep.schema import DATA_PREP_AGENT_TOOL
from digigraph.agents.visualization.runner import run_visualization_agent
from digigraph.agents.visualization.schema import VISUALIZATION_AGENT_TOOL
from digigraph.orchestration.plugins import load_entrypoint_tools
from digigraph.orchestration.registry import ToolContext, register_skill, register_tool
from digigraph.policy import code_execution_allowed, federated_hub_enabled
from digigraph.project_config import DigiProjectConfig
from digigraph.trace_events import rag_sources_from_results
from digigraph.vertical_orchestrator import (
    fetch_digisearch_tool_dicts,
    fetch_digiquant_tool_dicts,
    invoke_digisearch_tool,
    invoke_digiquant_tool,
)

logger = logging.getLogger(__name__)

DELEGATE_TAGS = {"delegate", "parallel_safe"}

_ORCHESTRATOR_CLIENT_ERRORS = (
    httpx.HTTPStatusError,
    httpx.RequestError,
    json.JSONDecodeError,
    OSError,
    TypeError,
    ValueError,
)

_STORE_ERRORS = (OSError, TypeError, ValueError, RuntimeError)


def _merged_digisearch_filters(
    context: ToolContext, args: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Merge workflow state research_filters / evidence_tier_preference with per-call tool args."""
    parts: list[dict[str, Any]] = []
    st = context.state or {}
    wf_filters = st.get("research_filters")
    if isinstance(wf_filters, list):
        for x in wf_filters:
            if isinstance(x, dict):
                parts.append(x)
    arg_filters = args.get("filters")
    if isinstance(arg_filters, list):
        for x in arg_filters:
            if isinstance(x, dict):
                parts.append(x)
    tiers = st.get("evidence_tier_preference")
    if isinstance(tiers, list) and tiers:
        parts.append({"field": "evidence_tier", "op": "in", "value": list(tiers)})
    return parts or None


# Max size of search result payload sent to the LLM (avoids context explosion).
_LLM_SEARCH_PREVIEW_ROWS = 5
_LLM_SEARCH_PREVIEW_CHARS = 300


def _search_payload_for_llm(
    results: list[dict[str, Any]],
    total: int,
    *,
    dataset_ref: str | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a small payload for the tool message so we do not send full results to the LLM."""
    payload: dict[str, Any] = {"total": total}
    if dataset_ref:
        payload["dataset_ref"] = dataset_ref
        payload["note"] = (
            "Full data is stored at dataset_ref; use it with visualization_agent, analysis_agent, data_prep_agent, etc."
        )
    if summary and isinstance(summary, dict):
        payload["summary"] = summary
    if results:
        preview: list[dict[str, Any]] = []
        for r in results[:_LLM_SEARCH_PREVIEW_ROWS]:
            if not isinstance(r, dict):
                continue
            row: dict[str, Any] = {}
            for k, v in r.items():
                if k == "content" and isinstance(v, str):
                    row[k] = v[:_LLM_SEARCH_PREVIEW_CHARS] + (
                        "..." if len(v) > _LLM_SEARCH_PREVIEW_CHARS else ""
                    )
                elif k != "content" and v is not None:
                    s = str(v)
                    row[k] = s[:_LLM_SEARCH_PREVIEW_CHARS] + (
                        "..." if len(s) > _LLM_SEARCH_PREVIEW_CHARS else ""
                    )
            preview.append(row)
        payload["preview"] = preview
    return payload


def _digisearch_available(_context: ToolContext) -> bool:
    url = os.environ.get("DIGISEARCH_URL", "")
    return bool(url and url.strip())


def _digi_bearer_from_context(context: ToolContext) -> str | None:
    st = context.state
    if isinstance(st, dict):
        raw = st.get("digi_bearer")
        return str(raw).strip() if raw else None
    return None


def _digisearch_service_base() -> str:
    return DigiProjectConfig.load().get_digisearch_url()


def _digiquant_service_base() -> str:
    return DigiProjectConfig.load().get_digiquant_url()


def _schema_from_digisearch_manifest(ctx: ToolContext, tool_name: str) -> dict[str, Any]:
    try:
        by_name = fetch_digisearch_tool_dicts(
            _digisearch_service_base(),
            ctx.index_config if isinstance(ctx.index_config, dict) else {},
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get(tool_name)
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("DigiSearch manifest fetch failed for %s: %s", tool_name, exc)
    if tool_name == "digisearch_fetch_all":
        return {
            "type": "function",
            "function": {
                "name": "digisearch_fetch_all",
                "description": "Fetch all matching documents (pagination). Requires reachable DigiSearch orchestrator API.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            },
        }
    return {
        "type": "function",
        "function": {
            "name": "digisearch",
            "description": "Search documents via DigiSearch. Requires DIGISEARCH_URL and POST /v1/orchestrator_tools.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }


def _handle_digisearch(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    args_eff = dict(args)
    if "index_name" not in args_eff and context.index_name:
        args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"DigiSearch orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return "No results found."
    results = data.get("results", [])
    summary = data.get("summary")
    total = data.get("total", len(results))
    dataset_ref: str | None = None
    stored_profile: dict[str, Any] | None = None
    if context.has_run_data_dir and results:
        try:
            from digigraph.run_storage import write_search_results

            dataset_ref = write_search_results(context.session_id, results)
            cols = list(results[0].keys()) if results and isinstance(results[0], dict) else []
            stored_profile = {
                "ref": dataset_ref,
                "profile": {"row_count": len(results), "columns": cols},
            }
        except _STORE_ERRORS as exc:
            logger.warning("write_search_results failed: %s", exc)
    if not results and not summary:
        return "No results found."
    payload_for_llm = _search_payload_for_llm(
        results, total, dataset_ref=dataset_ref, summary=summary
    )
    out: dict[str, Any] = {
        "content": json.dumps(payload_for_llm),
        "results": results,
        "summary": summary,
        "rag_sources": rag_sources_from_results(results),
    }
    if dataset_ref:
        out["dataset_ref"] = dataset_ref
    if stored_profile:
        out["stored_dataset_profile"] = stored_profile
    return out


def _handle_digisearch_fetch_all(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    args_eff = dict(args)
    if "index_name" not in args_eff and context.index_name:
        args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    # Clamp max_results to the configured limit.
    limits = DigiProjectConfig.load().get_limits()
    cap = limits.max_rows_per_fetch
    caller_max = args_eff.get("max_results")
    if caller_max is None:
        args_eff["max_results"] = cap
    elif isinstance(caller_max, int) and caller_max > cap:
        args_eff["max_results"] = cap
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch_fetch_all",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"DigiSearch orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return "No results found."
    results = data.get("results", [])
    total = data.get("total", len(results))
    dataset_ref = None
    stored_profile = None
    if context.has_run_data_dir and results:
        try:
            from digigraph.run_storage import write_search_results

            dataset_ref = write_search_results(context.session_id, results)
            cols = list(results[0].keys()) if results and isinstance(results[0], dict) else []
            stored_profile = {
                "ref": dataset_ref,
                "profile": {"row_count": len(results), "columns": cols},
            }
        except _STORE_ERRORS as exc:
            logger.warning("write_search_results failed: %s", exc)
    payload_for_llm = _search_payload_for_llm(results, total, dataset_ref=dataset_ref)
    out = {
        "content": json.dumps(payload_for_llm),
        "results": results,
        "total": total,
        "rag_sources": rag_sources_from_results(results),
    }
    if dataset_ref:
        out["dataset_ref"] = dataset_ref
    if stored_profile:
        out["stored_dataset_profile"] = stored_profile
    return out


def _handle_visualization(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_visualization_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_analysis(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_analysis_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_prep(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_prep_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_manipulation(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_manipulation_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        second_dataset_ref=args.get("second_dataset_ref"),
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_engineer(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    result = run_data_engineer_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        additional_dataset_refs=args.get("additional_dataset_refs"),
        options=args.get("options"),
    )
    return {"content": result}


DIGISTORE_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_list",
        "description": "List datasets stored in this session (read-only). Returns name and row_count for each. Use to discover available dataset_refs before calling visualization_agent, analysis_agent, or data_manipulation_agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_row_count": {
                    "type": "boolean",
                    "description": "Include row count per dataset (default true).",
                },
            },
        },
    },
}

DIGISTORE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_profile",
        "description": "Get schema and sample rows for a stored dataset (read-only). Use to inspect columns and sample data before visualization or manipulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {
                    "type": "string",
                    "description": "Dataset name or ref (e.g. search_1) from digistore_list or a previous search result.",
                },
                "sample_size": {
                    "type": "integer",
                    "description": "Number of sample rows to return (default 5).",
                },
            },
            "required": ["dataset_ref"],
        },
    },
}


def _handle_digistore_list(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_list

    include_row_count = args.get("include_row_count", True)
    datasets = digistore_list(context.session_id, include_row_count=include_row_count)
    return {"content": json.dumps({"datasets": datasets})}


def _handle_digistore_profile(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_profile

    ref = args.get("dataset_ref")
    if not ref or not str(ref).strip():
        return {"content": json.dumps({"error": "dataset_ref is required."})}
    sample_size = args.get("sample_size", 5)
    try:
        profile = digistore_profile(context.session_id, str(ref), sample_size=sample_size)
        return {"content": json.dumps(profile)}
    except ValueError as e:
        return {"content": json.dumps({"error": str(e)})}


TODO_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "todo",
        "description": "Emit a list of intended tasks or steps for this request. Use to make your plan explicit before executing tools (e.g. 'search all from X', 'chart by date', 'export CSV'). The list is recorded for context; execution continues with the normal tool loop.",
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of task descriptions.",
                }
            },
            "required": ["tasks"],
        },
    },
}


def _handle_todo(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Record the LLM's intended task list; return a short confirmation."""
    tasks = args.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = [str(tasks)]
    tasks = [str(t) for t in tasks if t]
    if context.state is not None:
        context.state["todo_plan"] = tasks
    n = len(tasks)
    return {"content": f"Recorded {n} task(s). Proceed with your tools."}


CREATE_PLAN_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "create_plan",
        "description": "Submit a structured execution plan: ordered steps with agent names, arguments, and optional depends_on. Use {{step_id.field}} in args to reference prior step outputs (e.g. {{1.dataset_ref}}). The executor will run steps in dependency order and in parallel when independent.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Step id (e.g. '1', '2')."},
                            "agent": {
                                "type": "string",
                                "description": "Tool/agent name (e.g. digisearch_fetch_all, visualization_agent).",
                            },
                            "args": {
                                "type": "object",
                                "description": "Arguments for the agent. Use {{step_id.field}} for placeholders.",
                            },
                            "depends_on": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Step ids that must complete before this step.",
                            },
                        },
                        "required": ["id", "agent"],
                    },
                    "description": "Ordered steps to execute.",
                }
            },
            "required": ["steps"],
        },
    },
}


def _handle_create_plan(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """Store the structured plan in state for the executor; return confirmation and plan."""
    steps = args.get("steps") or []
    if not isinstance(steps, list):
        return {"content": "steps must be a list."}
    normalized = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        step_id = s.get("id")
        agent = s.get("agent")
        if not step_id or not agent:
            continue
        normalized.append(
            {
                "id": str(step_id),
                "agent": str(agent),
                "args": s.get("args") if isinstance(s.get("args"), dict) else {},
                "depends_on": [str(d) for d in s.get("depends_on") or []]
                if isinstance(s.get("depends_on"), list)
                else [],
            }
        )
    if context.state is not None:
        context.state["plan"] = normalized
    return {
        "content": f"Plan recorded ({len(normalized)} steps). Executor will run when planning_mode is enabled.",
        "plan": normalized,
    }


def _schema_digisearch_research_delegate(ctx: ToolContext) -> dict[str, Any]:
    return _schema_from_digisearch_manifest(ctx, "digisearch_research_delegate")


def _schema_digiquant_pipeline_delegate(ctx: ToolContext) -> dict[str, Any]:
    try:
        by_name = fetch_digiquant_tool_dicts(
            _digiquant_service_base(),
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get("digiquant_pipeline_delegate") or by_name.get("digiquant_run_pipeline")
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("DigiQuant manifest fetch failed: %s", exc)
    return {
        "type": "function",
        "function": {
            "name": "digiquant_pipeline_delegate",
            "description": "Run DigiQuant pipeline. Requires DIGIQUANT_URL and POST /v1/orchestrator_tools.",
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


def _handle_digisearch_research_delegate(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    msg = str(args.get("user_message") or "").strip()
    if not msg:
        return {"content": "user_message is required."}
    args_eff = dict(args)
    args_eff["user_message"] = msg
    if "index_name" not in args_eff and context.index_name:
        args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    args_eff["session_id"] = context.session_id
    try:
        inv = invoke_digisearch_tool(
            _digisearch_service_base(),
            "digisearch_research_delegate",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return {"content": f"DigiSearch orchestrator invoke failed: {e}"}
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        return json.dumps(inv)
    fc = str(data.get("formatted_context") or "")
    payload_preview = (
        fc if fc else json.dumps({"total": data.get("total"), "note": "no formatted_context"})
    )
    return {
        "content": payload_preview,
        "rag_sources": data.get("rag_sources") or [],
        "results": data.get("results"),
        "trace": data.get("trace"),
        "service": "digisearch",
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
        inv = invoke_digiquant_tool(
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


def _federated_delegate_tool_names() -> list[str]:
    if not federated_hub_enabled():
        return []
    return ["digisearch_research_delegate", "digiquant_pipeline_delegate"]


def _register_tools() -> None:
    register_tool(
        "digisearch",
        None,
        _handle_digisearch,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch"),
    )
    register_tool(
        "digisearch_fetch_all",
        None,
        _handle_digisearch_fetch_all,
        schema_factory=lambda ctx: _schema_from_digisearch_manifest(ctx, "digisearch_fetch_all"),
    )
    register_tool(
        "visualization_agent",
        VISUALIZATION_AGENT_TOOL,
        _handle_visualization,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "analysis_agent",
        ANALYSIS_AGENT_TOOL,
        _handle_analysis,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_prep_agent",
        DATA_PREP_AGENT_TOOL,
        _handle_data_prep,
        tags=DELEGATE_TAGS,
    )
    register_tool(
        "data_manipulation_agent",
        DATA_MANIPULATION_AGENT_TOOL,
        _handle_data_manipulation,
        tags=DELEGATE_TAGS,
    )
    if code_execution_allowed():
        register_tool(
            "data_engineer_agent",
            DATA_ENGINEER_AGENT_TOOL,
            _handle_data_engineer,
            tags=DELEGATE_TAGS,
        )
    register_tool(
        "digistore_list",
        DIGISTORE_LIST_TOOL,
        _handle_digistore_list,
    )
    register_tool(
        "digistore_profile",
        DIGISTORE_PROFILE_TOOL,
        _handle_digistore_profile,
    )
    register_tool(
        "todo",
        TODO_TOOL,
        _handle_todo,
    )
    register_tool(
        "create_plan",
        CREATE_PLAN_TOOL,
        _handle_create_plan,
    )
    if federated_hub_enabled():
        register_tool(
            "digisearch_research_delegate",
            None,
            _handle_digisearch_research_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digisearch_research_delegate,
        )
        register_tool(
            "digiquant_pipeline_delegate",
            None,
            _handle_digiquant_pipeline_delegate,
            tags=DELEGATE_TAGS,
            schema_factory=_schema_digiquant_pipeline_delegate,
        )


def _sitaas_rag_tool_names() -> list[str]:
    names = [
        "digisearch",
        "digisearch_fetch_all",
        "digistore_list",
        "digistore_profile",
        "visualization_agent",
        "analysis_agent",
        "data_prep_agent",
        "data_manipulation_agent",
    ]
    if code_execution_allowed():
        names.append("data_engineer_agent")
    names.extend(["todo", "create_plan", *_federated_delegate_tool_names()])
    return names


def _register_skills() -> None:
    search_bundle = ["digisearch", "digisearch_fetch_all", *_federated_delegate_tool_names()[:1]]
    register_skill(
        "search",
        search_bundle,
        when=lambda ctx: _digisearch_available(ctx),
    )
    register_skill(
        "sitaas_rag",
        _sitaas_rag_tool_names(),
        when=lambda ctx: ctx.has_run_data_dir,
    )


_register_tools()
_register_skills()
load_entrypoint_tools()
