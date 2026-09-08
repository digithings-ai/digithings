"""digisearch built-in tool schemas and handlers (via vertical_orchestrator hub)."""

from __future__ import annotations

import json
import logging
from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.tool_common import (
    _ORCHESTRATOR_CLIENT_ERRORS,
    _STORE_ERRORS,
    _digi_bearer_from_context,
    _digisearch_service_base,
    _mark_truncated_excerpts,
    _merged_digisearch_filters,
    _search_payload_for_llm,
)
from digigraph.project_config import DigiProjectConfig
from digigraph.trace_events import rag_sources_from_results

logger = logging.getLogger(__name__)


def _invoke_ds(*args, **kwargs):
    """Late-bind through builtin so tests can patch ``builtin.invoke_digisearch_tool``."""
    from digigraph.orchestration import builtin as _reg

    return _reg.invoke_digisearch_tool(*args, **kwargs)


def _fetch_ds(*args, **kwargs):
    from digigraph.orchestration import builtin as _reg

    return _reg.fetch_digisearch_tool_dicts(*args, **kwargs)


def _schema_from_digisearch_manifest(ctx: ToolContext, tool_name: str) -> dict[str, Any]:
    try:
        by_name = _fetch_ds(
            _digisearch_service_base(),
            ctx.index_config if isinstance(ctx.index_config, dict) else {},
            _digi_bearer_from_context(ctx),
            ctx.request_id,
        )
        t = by_name.get(tool_name)
        if t:
            return t
    except _ORCHESTRATOR_CLIENT_ERRORS as exc:
        logger.warning("digisearch manifest fetch failed for %s: %s", tool_name, exc)
    if tool_name == "digisearch_fetch_all":
        return {
            "type": "function",
            "function": {
                "name": "digisearch_fetch_all",
                "description": "Fetch all matching documents (pagination). Requires reachable digisearch orchestrator API.",
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
            "description": "Search documents via digisearch. Requires DIGISEARCH_URL and POST /v1/orchestrator_tools.",
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
    # Security (#2265): overwrite unconditionally, never default-if-missing — a
    # model-supplied index_name must not reach another tenant's vector corpus.
    # index_name is not declared on the digisearch schema, but that never stopped
    # a model from supplying one anyway: OrchestratorInvokeRequest.arguments (on
    # the digisearch side) is dict[str, Any], never schema-validated. Mirrors the
    # vault handlers' mandatory fix (_handle_digivault_search /
    # _handle_digivault_get_note) — the digisearch index is the other half of
    # the same tenant boundary #2265 closed for digivault's path_prefix.
    args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    try:
        inv = _invoke_ds(
            _digisearch_service_base(),
            "digisearch",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digisearch orchestrator invoke failed: {e}"
    if not inv.get("ok"):
        return json.dumps(inv)
    data = inv.get("data")
    if not isinstance(data, dict):
        # A completed (ok=True) search with no usable payload is a zero-hit search,
        # not a "never searched" — return a dict (not a bare string) so execute_search
        # (research.py) can attach hit_count=0/query for the activity trace. The
        # "content" string is unchanged, so the model still reads the same text.
        return {"content": "No results found.", "results": [], "rag_sources": []}
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
        # Real zero-hit case: the search ran, dig(i)search answered, nothing matched.
        # Dict (not a bare string) so execute_search can attach hit_count=0/query.
        return {"content": "No results found.", "results": [], "rag_sources": []}
    payload_for_llm = _search_payload_for_llm(
        results, total, dataset_ref=dataset_ref, summary=summary
    )
    # Vault-sourced digisearch chunks are loadable, but via metadata.vault_path -- this
    # sink's doc_id is a repo path digivault_get_note cannot resolve (#2306).
    _mark_truncated_excerpts(
        payload_for_llm,
        results,
        load_hint="that row's metadata.vault_path (only rows that carry one are loadable)",
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
    # Security (#2265): same unconditional overwrite as _handle_digisearch. Not
    # reachable from the production allowlist today (digisearch_fetch_all is not in
    # infra/digichat-release/config/digiproject.yaml's allowed_tools), but leaving one
    # half of the tenant boundary on the old default-if-missing pattern is how it comes
    # back the moment this tool is allowlisted.
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
        inv = _invoke_ds(
            _digisearch_service_base(),
            "digisearch_fetch_all",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return f"digisearch orchestrator invoke failed: {e}"
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


def _schema_digisearch_research_delegate(ctx: ToolContext) -> dict[str, Any]:
    return _schema_from_digisearch_manifest(ctx, "digisearch_research_delegate")


def _handle_digisearch_research_delegate(
    args: dict[str, Any], context: ToolContext
) -> str | dict[str, Any]:
    msg = str(args.get("user_message") or "").strip()
    if not msg:
        return {"content": "user_message is required."}
    args_eff = dict(args)
    args_eff["user_message"] = msg
    # Security (#2265): same unconditional overwrite as _handle_digisearch. Gated behind
    # federated_hub_enabled() and not in any production allowlist today, but the tenant
    # boundary should not have a third shape.
    args_eff["index_name"] = context.index_name
    merged = _merged_digisearch_filters(context, args_eff)
    if merged:
        args_eff["filters"] = merged
    args_eff["session_id"] = context.session_id
    try:
        inv = _invoke_ds(
            _digisearch_service_base(),
            "digisearch_research_delegate",
            args_eff,
            default_index_name=context.index_name,
            bearer_token=_digi_bearer_from_context(context),
            request_id=context.request_id,
        )
    except _ORCHESTRATOR_CLIENT_ERRORS as e:
        return {"content": f"digisearch orchestrator invoke failed: {e}"}
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
