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
        "Search the document index for relevant information. Use when you need to find content related to the user's question. Generate a concise search query optimized for retrieval. "
        "For 'all emails from user X' use filters: fromAddress eq 'x@example.com' or fromName; for 'emails mentioning subject Y' use a text query and/or filters. "
        "For requests that need the full result set (e.g. 'all emails from X'), use digisearch_fetch_all so every matching document is retrieved; otherwise use digisearch with include_total_count and pagination (skip/top_k) if needed.",
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
            "Collection fields (toRecipients, attachments, mentions, etc.) require the 'filter' param (raw OData). "
        )
        examples = []
        for field_name, field_def in list(complex_fields.items())[:3]:
            if isinstance(field_def, dict) and field_def.get("filter_example"):
                ex = field_def["filter_example"]
                if ex and len(ex) < 120:
                    examples.append(f"{field_name}: {ex}")
        if examples:
            parts.append("Examples: " + "; ".join(examples) + ".")
        else:
            parts.append("E.g. toRecipients/any(r: r/emailAddress/address eq 'user@example.com').")
    parts.append("For date ranges use filters with sentDateTime or createdDateTime and op ge/le (ISO 8601).")
    if index_config.get("facetable_fields"):
        parts.append("For exploratory queries use the facets parameter to get value counts before narrowing.")
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


def digisearch_fetch_all(
    text: str,
    index_name: str = "default",
    page_size: int = 500,
    max_results: int | None = None,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    order_by: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Fetch all matching documents by paginating until exhausted. Returns combined results and total.
    Use for 'retrieve them all' queries (e.g. all emails from user X). Writes to Digistore when run_data_dir set.
    """
    all_results: list[dict] = []
    skip = 0
    total_so_far = 0
    total_estimate: int | None = None
    while True:
        data = digisearch(
            text=text,
            index_name=index_name,
            top_k=page_size,
            mode=mode,
            filter=filter,
            filters=filters,
            columns=columns,
            order_by=order_by,
            skip=skip,
            include_total_count=True,
        )
        if not data:
            break
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        total_so_far += len(results)
        total_estimate = data.get("total")
        if total_estimate is not None and total_so_far >= total_estimate:
            break
        if max_results is not None and total_so_far >= max_results:
            all_results = all_results[:max_results]
            break
        if len(results) < page_size:
            break
        skip += page_size
    return {
        "results": all_results,
        "total": len(all_results),
        "query": text,
        "index_name": index_name,
    }


def build_fetch_all_tool(index_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the digisearch_fetch_all OpenAI-style tool for 'retrieve all' queries."""
    index_config = index_config or {}
    index_name = (index_config.get("index_name") or "default").strip()
    filterable = index_config.get("filterable_fields") or []
    filterable_hint = f" Filterable fields: {', '.join(filterable)}." if filterable else ""
    return {
        "type": "function",
        "function": {
            "name": "digisearch_fetch_all",
            "description": (
                "Fetch ALL matching documents by paginating automatically. Use when the user asks for 'all' results "
                "(e.g. all emails from user X, all emails mentioning a subject). Guarantees complete result set. "
                f"Index: {index_name}.{filterable_hint}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (can be * for filter-only)."},
                    "filter": {
                        "type": "string",
                        "description": "Optional raw OData filter, e.g. fromAddress eq 'user@example.com'.",
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {"type": "string", "enum": ["eq", "ne", "gt", "ge", "lt", "le", "in"]},
                                "value": {"description": "Scalar or list for 'in'."},
                            },
                            "required": ["field", "op", "value"],
                        },
                        "description": "Optional structured filters.",
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metadata columns to return.",
                    },
                    "order_by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Sort clauses, e.g. ['sentDateTime desc'].",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Optional cap on total results (default no cap).",
                    },
                },
                "required": ["query"],
            },
        },
    }
