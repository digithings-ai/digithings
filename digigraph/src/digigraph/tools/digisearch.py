"""DigiSearch tool for DigiGraph: HTTP-only client.

Calls DigiSearch POST /query. Returns raw response data only; formatting
for the web UI is done in the DigiGraph server when building the stream.

Tool description and parameters can be built from the project's index config
so the orchestrator knows index structure, filterable fields, and filter format.
"""

from __future__ import annotations

import os
from typing import Any

import httpx


def _build_search_tool_description(index_config: dict[str, Any]) -> str:
    """Build tool description from index config so the orchestrator knows index structure and params."""
    index_name = (index_config.get("index_name") or "default").strip()
    parts = [
        "Search the document index for relevant information. Use when you need to find content related to the user's question. Generate a concise search query optimized for retrieval.",
        f"Index: {index_name}.",
    ]
    filterable = index_config.get("filterable_fields") or []
    if filterable:
        parts.append(
            f"Filterable fields (use in 'filters' with op eq/ne/gt/ge/lt/le/in): {', '.join(filterable)}. "
            "Structured filters format: [{\"field\": \"<name>\", \"op\": \"eq\"|\"in\"|..., \"value\": <scalar or list for 'in'>}]."
        )
    facetable = index_config.get("facetable_fields") or []
    if facetable:
        parts.append(f"Facets (request counts per value): {', '.join(facetable[:8])}{'...' if len(facetable) > 8 else ''}.")
    result_meta = index_config.get("result_metadata_fields") or []
    if result_meta:
        parts.append(f"Columns you can request: {', '.join(result_meta[:12])}{'...' if len(result_meta) > 12 else ''}.")
    complex_fields = index_config.get("complex_field_structures") or {}
    if complex_fields:
        parts.append(
            "Some fields are JSON/collections (toRecipients, attachments, etc.); filtering on them requires 'filter' (raw OData) when the index allows it, e.g. toRecipients/any(r: r/emailAddress/address eq 'x')."
        )
    return " ".join(parts)


def build_search_tool(index_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the digisearch OpenAI-style tool. When index_config is provided, description and param hints reflect the index."""
    index_config = index_config or {}
    description = _build_search_tool_description(index_config)
    filterable = index_config.get("filterable_fields") or []
    filterable_hint = f" Use only these filterable fields: {', '.join(filterable)}." if filterable else ""
    return {
        "type": "function",
        "function": {
            "name": "digisearch",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A search query optimized for finding relevant documents.",
                    },
                    "filter": {
                        "type": "string",
                        "description": "Optional raw OData filter (when index allows raw filter). Use for collection fields, e.g. toRecipients/any(r: r/emailAddress/address eq 'user@example.com').",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "description": "Field name (must be filterable)."},
                                "op": {"type": "string", "description": "Operator: eq, ne, gt, ge, lt, le, or in (value = list or comma-separated)."},
                                "value": {"description": "Scalar value, or list/string for op 'in'."},
                            },
                            "required": ["field", "op", "value"],
                        },
                        "description": f"Optional structured filters, e.g. [{{\"field\": \"sourceType\", \"op\": \"eq\", \"value\": \"EXCHANGE\"}}].{filterable_hint}",
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional metadata columns to return (e.g. subject, fromAddress, sourceType, sentDateTime).",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max number of results (default 10).",
                    },
                    "response_mode": {
                        "type": "string",
                        "enum": ["full", "summary"],
                        "description": "Return full rows or a data summary.",
                    },
                    "summarize_if_over": {
                        "type": "integer",
                        "description": "If result count exceeds this, return summary instead of full rows.",
                    },
                    "facets": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional facet expressions, e.g. ['sourceType', 'itemType,count:20'] to get value counts.",
                    },
                    "order_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional sort clauses, e.g. ['sentDateTime desc', 'search.score() desc'].",
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Pagination offset (default 0).",
                    },
                    "include_total_count": {
                        "type": "boolean",
                        "description": "When true, response total is the full match count for pagination.",
                    },
                },
                "required": ["query"],
            },
        },
    }


def digisearch(
    text: str,
    index_name: str = "default",
    top_k: int = 10,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    response_mode: str = "full",
    summarize_if_over: int | None = None,
    facets: list[str] | None = None,
    highlight_fields: list[str] | None = None,
    order_by: list[str] | None = None,
    skip: int = 0,
    include_total_count: bool = False,
) -> dict[str, Any] | None:
    """Search DigiSearch. Returns raw response dict (results, query, index_name, total, summary?, facets?) or None."""
    base_url = os.environ.get("DIGISEARCH_URL", "").strip()
    if not base_url:
        return None
    url = f"{base_url.rstrip('/')}/query"
    payload: dict[str, Any] = {"text": text, "index_name": index_name, "top_k": top_k, "mode": mode}
    if filter is not None and filter.strip():
        payload["filter"] = filter.strip()
    if filters:
        payload["filters"] = filters
    if facets:
        payload["facets"] = facets
    if highlight_fields:
        payload["highlight_fields"] = highlight_fields
    if order_by:
        payload["order_by"] = order_by
    if skip:
        payload["skip"] = skip
    if include_total_count:
        payload["include_total_count"] = True
    if columns:
        payload["columns"] = columns
    if response_mode and response_mode.strip().lower() != "full":
        payload["response_mode"] = response_mode.strip().lower()
    if summarize_if_over is not None:
        payload["summarize_if_over"] = summarize_if_over
    try:
        with httpx.Client(timeout=15.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None
