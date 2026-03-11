"""Register built-in orchestrator tools and skills. Import this module to populate the registry."""

from __future__ import annotations

import json
import os
from typing import Any

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
from digigraph.orchestration.registry import ToolContext, register_skill, register_tool
from digigraph.tools.digisearch import (
    build_fetch_all_tool,
    build_search_tool,
    digisearch,
    digisearch_fetch_all,
)

DELEGATE_TAGS = {"delegate", "parallel_safe"}

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
        payload["note"] = "Full data is stored at dataset_ref; use it with visualization_agent, analysis_agent, data_prep_agent, etc."
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
                    row[k] = v[:_LLM_SEARCH_PREVIEW_CHARS] + ("..." if len(v) > _LLM_SEARCH_PREVIEW_CHARS else "")
                elif k != "content" and v is not None:
                    s = str(v)
                    row[k] = s[:_LLM_SEARCH_PREVIEW_CHARS] + ("..." if len(s) > _LLM_SEARCH_PREVIEW_CHARS else "")
            preview.append(row)
        payload["preview"] = preview
    return payload


def _digisearch_available(_context: ToolContext) -> bool:
    url = os.environ.get("DIGISEARCH_URL", "")
    return bool(url and url.strip())


def _handle_digisearch(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    top_k = args.get("top_k")
    if top_k is not None and not isinstance(top_k, int):
        top_k = 10
    top_k = top_k if top_k is not None else 10
    data = digisearch(
        str(q),
        index_name=context.index_name,
        top_k=top_k,
        filter=args.get("filter"),
        filters=args.get("filters"),
        columns=args.get("columns"),
        response_mode=args.get("response_mode", "full"),
        summarize_if_over=args.get("summarize_if_over"),
        facets=args.get("facets"),
        highlight_fields=args.get("highlight_fields"),
        order_by=args.get("order_by"),
        skip=args.get("skip", 0),
        include_total_count=args.get("include_total_count", False),
    )
    if not data:
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
            stored_profile = {"ref": dataset_ref, "profile": {"row_count": len(results), "columns": cols}}
        except Exception:
            pass
    if not results and not summary:
        return "No results found."
    payload_for_llm = _search_payload_for_llm(results, total, dataset_ref=dataset_ref, summary=summary)
    out: dict[str, Any] = {"content": json.dumps(payload_for_llm), "results": results, "summary": summary}
    if dataset_ref:
        out["dataset_ref"] = dataset_ref
    if stored_profile:
        out["stored_dataset_profile"] = stored_profile
    return out


def _handle_digisearch_fetch_all(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    page_size = 500
    max_results = args.get("max_results")
    data = digisearch_fetch_all(
        str(q),
        index_name=context.index_name,
        page_size=page_size,
        max_results=max_results,
        filter=args.get("filter"),
        filters=args.get("filters"),
        columns=args.get("columns"),
        order_by=args.get("order_by"),
    )
    if not data:
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
            stored_profile = {"ref": dataset_ref, "profile": {"row_count": len(results), "columns": cols}}
        except Exception:
            pass
    payload_for_llm = _search_payload_for_llm(results, total, dataset_ref=dataset_ref)
    out = {"content": json.dumps(payload_for_llm), "results": results, "total": total}
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


def _register_tools() -> None:
    register_tool(
        "digisearch",
        None,
        _handle_digisearch,
        schema_factory=lambda ctx: build_search_tool(ctx.index_config),
    )
    register_tool(
        "digisearch_fetch_all",
        None,
        _handle_digisearch_fetch_all,
        schema_factory=lambda ctx: build_fetch_all_tool(ctx.index_config),
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


def _register_skills() -> None:
    register_skill(
        "search",
        ["digisearch", "digisearch_fetch_all"],
        when=lambda ctx: _digisearch_available(ctx),
    )
    register_skill(
        "sitaas_rag",
        [
            "digisearch",
            "digisearch_fetch_all",
            "digistore_list",
            "digistore_profile",
            "visualization_agent",
            "analysis_agent",
            "data_prep_agent",
            "data_manipulation_agent",
            "data_engineer_agent",
        ],
        when=lambda ctx: ctx.has_run_data_dir,
    )


_register_tools()
_register_skills()
