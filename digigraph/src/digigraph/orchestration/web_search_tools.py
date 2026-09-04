"""Web search built-in tool (External evidence tier)."""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext
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


def _handle_web_search(args: dict[str, Any], context: ToolContext) -> str | dict[str, Any]:
    """digillm web search — External cites; never a silent corpus substitute (#3420)."""
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

    from digigraph.llm_client import openrouter_web_search
    from digigraph.llm_client import web_search as xai_web_search
    from digigraph.model_config import get_grounding_model, get_model_for_mode

    model = get_grounding_model() or get_model_for_mode()
    grounded = openrouter_web_search(model, query)
    if grounded is None:
        grounded = xai_web_search(model, query)
    if grounded is None:
        return {
            "content": "Web search returned no results.",
            "results": [],
            "rag_sources": [],
            "name": WEB_SEARCH_TOOL_NAME,
        }
    summary, urls = grounded
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
