"""OpenAI-style orchestrator tool definitions for DigiSearch.

Hubs (e.g. DigiGraph) fetch these via ``POST /v1/orchestrator_tools`` and execute
via ``POST /v1/orchestrator_invoke`` so search tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any


def _build_search_tool_description(index_config: dict[str, Any]) -> str:
    """Build tool description from index config."""
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
        parts.append(
            f"Facets (request counts per value): {', '.join(facetable[:8])}{'...' if len(facetable) > 8 else ''}."
        )
    result_meta = index_config.get("result_metadata_fields") or []
    if result_meta:
        parts.append(
            f"Columns you can request: {', '.join(result_meta[:12])}{'...' if len(result_meta) > 12 else ''}."
        )
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
    """Build the digisearch OpenAI-style tool dict."""
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
                                "op": {
                                    "type": "string",
                                    "description": "Operator: eq, ne, gt, ge, lt, le, or in (value = list or comma-separated).",
                                },
                                "value": {"description": "Scalar value, or list/string for op 'in'."},
                            },
                            "required": ["field", "op", "value"],
                        },
                        "description": (
                            f"Optional structured filters, e.g. [{{\"field\": \"sourceType\", \"op\": \"eq\", \"value\": \"EXCHANGE\"}}].{filterable_hint}"
                        ),
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional metadata columns to return (e.g. subject, fromAddress, sourceType, sentDateTime).",
                    },
                    "top_k": {"type": "integer", "description": "Max number of results (default 10)."},
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
                    "skip": {"type": "integer", "description": "Pagination offset (default 0)."},
                    "include_total_count": {
                        "type": "boolean",
                        "description": "When true, response total is the full match count for pagination.",
                    },
                },
                "required": ["query"],
            },
        },
    }


def build_fetch_all_tool(index_config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the digisearch_fetch_all OpenAI-style tool dict."""
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


def build_digisearch_research_delegate_tool() -> dict[str, Any]:
    """Hub connector: delegated composite research turn (maps to ``POST /v1/research_turn``)."""
    return {
        "type": "function",
        "function": {
            "name": "digisearch_research_delegate",
            "description": "Delegated research turn on DigiSearch (HTTP composite). Returns citations and formatted context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_message": {"type": "string", "description": "Question or search intent"},
                    "index_name": {"type": "string", "description": "Optional index; defaults to workflow index"},
                    "top_k": {"type": "integer", "description": "Hits to retrieve (default 10)"},
                    "mode": {"type": "string", "description": "keyword | vector | hybrid"},
                    "filter": {"type": "string", "description": "Optional raw OData filter"},
                },
                "required": ["user_message"],
            },
        },
    }


def build_orchestrator_tool_manifest(
    index_config: dict[str, Any] | None = None,
    *,
    include_research_delegate: bool = False,
) -> list[dict[str, Any]]:
    """Return OpenAI tool dicts for the orchestrator surface."""
    ic = index_config or {}
    tools: list[dict[str, Any]] = [build_search_tool(ic), build_fetch_all_tool(ic)]
    if include_research_delegate:
        tools.append(build_digisearch_research_delegate_tool())
    return tools
