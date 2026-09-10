"""Web search built-in tool (External evidence tier)."""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext
from digigraph.orchestration.tool_common import (
    _digi_bearer_from_context,
    _digisearch_service_base,
)
from digigraph.trace_events import rag_sources_from_results

EXTERNAL_EVIDENCE_TIER = "External"
WEB_SEARCH_TOOL_NAME = "web_search"

WEB_SEARCH_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": WEB_SEARCH_TOOL_NAME,
        "description": (
            "Search the public web for current information via digillm. Results are "
            "External citations — they supplement digisearch/digivault corpus hits and "
            "must never replace them. Prefer digisearch/digivault first; use web_search "
            "only when the corpus cannot answer and live public facts are required."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Web search query (short, factual).",
                },
            },
            "required": ["query"],
        },
    },
}


def _web_search_available(context: ToolContext) -> bool:
    """web_search is request-opt-in only (#3420) — never ambient on corpus RAG."""
    return bool(context.state.get("enable_web_search"))


def _as_str_list(value: Any) -> list[str]:
    """Coerce an optional tool arg to a clean string list (a bare string becomes one entry)."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _call_digisearch_web_search(
    query: str,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 4,
    context: ToolContext | None = None,
) -> dict[str, Any]:
    """Invoke digisearch ``web_search`` via the vertical-orchestrator hub.

    Never ``import digisearch`` — the call goes through
    :func:`digigraph.vertical_orchestrator.digisearch_hub.invoke_digisearch_tool`
    (``POST /v1/orchestrator_invoke``). Normalizes the hub envelope
    (``{"ok", "data": {"results": [{url, title, snippet}]}}``) into the digigraph
    tool shape (``{"content", "results": [{doc_id, ...}]}``). Returns ``{}`` when
    the service errors or yields no rows — callers fail hard (no synthesis
    fallback, #3859).
    """
    from digigraph.vertical_orchestrator.digisearch_hub import invoke_digisearch_tool

    index_name = getattr(context, "index_name", None) or "default"
    inv = invoke_digisearch_tool(
        _digisearch_service_base(),
        "web_search",
        {
            "query": query,
            "include_domains": _as_str_list(include_domains),
            "exclude_domains": _as_str_list(exclude_domains),
            "max_results": max_results,
        },
        default_index_name=index_name,
        bearer_token=_digi_bearer_from_context(context) if context is not None else None,
        request_id=getattr(context, "request_id", None),
    )
    if not isinstance(inv, dict) or not inv.get("ok"):
        return {}
    data = inv.get("data")
    if not isinstance(data, dict):
        return {}
    hits = data.get("results") or []
    rows: list[dict[str, Any]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = str(hit.get("url") or "").strip()
        if not url:
            continue
        title = str(hit.get("title") or url).strip() or url
        snippet = str(hit.get("snippet") or "")
        rows.append(
            {
                "doc_id": url,
                "content": snippet,
                "rank": len(rows),
                "metadata": {
                    "title": title,
                    "source_url": url,
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    if not rows:
        return {}
    lines = []
    for row in rows:
        line = f"- [{row['metadata']['title']}]({row['doc_id']})"
        if row["content"]:
            line += f" — {row['content']}"
        lines.append(line)
    return {"content": "\n".join(lines), "results": rows}


def _handle_web_search(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """digisearch web_search tool only — fail hard, never synthesize (#3859)."""
    if not _web_search_available(context):
        return {
            "error": "tool_not_allowed",
            "tool": WEB_SEARCH_TOOL_NAME,
            "message": (
                "web_search is opt-in and disabled for this session. "
                "Enable via X-Digi-Enable-Web-Search / enable_web_search."
            ),
        }
    q = args.get("query", "")
    if not q or not str(q).strip():
        return "No search query provided."
    query = str(q).strip()
    from digigraph.llm_client import digifetch_web_search

    # Tool path needs no model — "" keeps the (model, query) shape for callers.
    summary, urls = digifetch_web_search(
        "",
        query,
        include_domains=args.get("include_domains"),
        exclude_domains=args.get("exclude_domains"),
        max_results=int(args.get("max_results", 4)),
        context=context,
    )
    results: list[dict[str, Any]] = []
    for i, url in enumerate(urls[:8]):
        if not isinstance(url, str) or not url.strip():
            continue
        u = url.strip()
        results.append(
            {
                "doc_id": u,
                "content": summary if i == 0 else "",
                "rank": i,
                "metadata": {
                    "title": u,
                    "source_url": u,
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    if not results and summary:
        # Summary without parseable URLs — still surface as one External cite.
        results.append(
            {
                "doc_id": "web://search",
                "content": summary,
                "rank": 0,
                "metadata": {
                    "title": "Web search",
                    "evidence_tier": EXTERNAL_EVIDENCE_TIER,
                    "source_kind": "external",
                },
            }
        )
    return {
        "content": summary or "Web search returned no results.",
        "results": results,
        "rag_sources": rag_sources_from_results(results),
        "name": WEB_SEARCH_TOOL_NAME,
    }
