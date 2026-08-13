"""OpenAI-style orchestrator tool definitions for digisearch.

Hubs (e.g. digigraph) fetch these via ``POST /v1/orchestrator_tools`` and execute
via ``POST /v1/orchestrator_invoke`` so search tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any, TypedDict


class FunctionParametersSchema(TypedDict, total=False):
    type: str
    properties: dict[str, Any]
    required: list[str]


class FunctionToolSchema(TypedDict):
    """OpenAI function-tool ``function`` block (SIMP-036)."""

    name: str
    description: str
    parameters: FunctionParametersSchema


class OpenAIToolDict(TypedDict):
    """OpenAI function-tool dict returned by ``POST /v1/orchestrator_tools``."""

    type: str
    function: FunctionToolSchema


TOOL_DIGISEARCH = "digisearch"
TOOL_DIGISEARCH_FETCH_ALL = "digisearch_fetch_all"
TOOL_DIGISEARCH_RESEARCH_DELEGATE = "digisearch_research_delegate"

ORCHESTRATOR_TOOL_NAMES: frozenset[str] = frozenset(
    {
        TOOL_DIGISEARCH,
        TOOL_DIGISEARCH_FETCH_ALL,
        TOOL_DIGISEARCH_RESEARCH_DELEGATE,
    }
)


def _build_search_tool_description(index_config: dict[str, Any]) -> str:
    """Build tool description from index config."""
    index_name = (index_config.get("index_name") or "default").strip()
    parts = [
        # Corpus-neutral by design (#2306). This text previously carried worked examples
        # for a Microsoft Exchange mailbox index ("for 'all emails from user X' use
        # filters: fromAddress eq ..."), which is boilerplate from a different
        # deployment: on the digithings/OCC documentation corpora no such field exists,
        # so it invited filters that match nothing and framed a docs assistant as an email
        # search. The concrete field names the model may use are appended below from
        # index_config (filterable/facetable/result_metadata fields), which is the only
        # part that can be accurate for whichever index is actually mounted.
        "Search the document corpus for passages relevant to the user's question. This is "
        "semantic (vector) search: it matches on meaning, so phrase the query as the idea "
        "you are looking for rather than as a bag of keywords. "
        "Each hit is one CHUNK of a document, not the whole document, and its content is an "
        "excerpt — a hit marked content_truncated has more text than you were shown. When a "
        "hit carries metadata.vault_path it came from the vault: pass that value to "
        "digivault_get_note to read the whole note instead of reasoning from the chunk. "
        "For a result set larger than one page, use include_total_count and paginate with "
        "skip/top_k; digisearch_fetch_all retrieves every match where that tool is available.",
        f"Index: {index_name}.",
    ]
    filterable = index_config.get("filterable_fields") or []
    if filterable:
        parts.append(
            f"Filterable fields (use in 'filters' with op eq/ne/gt/ge/lt/le/in): {', '.join(filterable)}. "
            'Structured filters format: [{"field": "<name>", "op": "eq"|"in"|..., "value": <scalar or list for \'in\'>}].'
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
    # Only offer date-range guidance when this index actually has a date field to filter
    # on (#2306). Appended unconditionally, it named sentDateTime/createdDateTime — mailbox
    # fields absent from the documentation corpora — so on those indexes it advertised a
    # filter that can only ever match nothing.
    date_fields = [f for f in filterable if "date" in f.lower() or "time" in f.lower()]
    if date_fields:
        parts.append(
            f"For date ranges use filters with {' or '.join(date_fields[:2])} "
            "and op ge/le (ISO 8601)."
        )
    if index_config.get("facetable_fields"):
        parts.append(
            "For exploratory queries use the facets parameter to get value counts before narrowing."
        )
    return " ".join(parts)


def build_search_tool(index_config: dict[str, Any] | None = None) -> OpenAIToolDict:
    """Build the digisearch OpenAI-style tool dict."""
    index_config = index_config or {}
    description = _build_search_tool_description(index_config)
    filterable = index_config.get("filterable_fields") or []
    filterable_hint = (
        f" Use only these filterable fields: {', '.join(filterable)}." if filterable else ""
    )
    return {
        "type": "function",
        "function": {
            "name": TOOL_DIGISEARCH,
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
                        "description": (
                            "Optional raw OData filter, for collection fields the structured "
                            "`filters` array cannot express. Only usable when this index "
                            "declares such fields (they are listed above with worked "
                            "examples); otherwise prefer `filters`."
                        ),
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "description": "Field name (must be filterable).",
                                },
                                "op": {
                                    "type": "string",
                                    "description": "Operator: eq, ne, gt, ge, lt, le, or in (value = list or comma-separated).",
                                },
                                "value": {
                                    "description": "Scalar value, or list/string for op 'in'."
                                },
                            },
                            "required": ["field", "op", "value"],
                        },
                        "description": (
                            f'Optional structured filters, e.g. [{{"field": "source", "op": "eq", "value": "SECURITY.md"}}].{filterable_hint}'
                        ),
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional metadata columns to return. Use only names listed as "
                            "available for this index above; unknown names are ignored."
                        ),
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
                    "include_facets": {
                        "type": "boolean",
                        "description": "When true, response carries facet counts (Azure only). Use for narrowing follow-up queries.",
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


def build_fetch_all_tool(index_config: dict[str, Any] | None = None) -> OpenAIToolDict:
    """Build the digisearch_fetch_all OpenAI-style tool dict."""
    index_config = index_config or {}
    index_name = (index_config.get("index_name") or "default").strip()
    filterable = index_config.get("filterable_fields") or []
    filterable_hint = f" Filterable fields: {', '.join(filterable)}." if filterable else ""
    return {
        "type": "function",
        "function": {
            "name": TOOL_DIGISEARCH_FETCH_ALL,
            "description": (
                "Fetch ALL matching documents by paginating automatically. Use when the user asks for 'all' results "
                "(e.g. all emails from user X, all emails mentioning a subject). Guarantees complete result set. "
                f"Index: {index_name}.{filterable_hint}"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (can be * for filter-only).",
                    },
                    "filter": {
                        "type": "string",
                        "description": (
                            "Optional raw OData filter over this index's filterable fields, e.g. "
                            "source eq 'SECURITY.md'. Prefer the structured `filters` array."
                        ),
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "op": {
                                    "type": "string",
                                    "enum": ["eq", "ne", "gt", "ge", "lt", "le", "in"],
                                },
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


def build_digisearch_research_delegate_tool() -> OpenAIToolDict:
    """Hub connector: delegated composite research turn (maps to ``POST /v1/research_turn``)."""
    return {
        "type": "function",
        "function": {
            "name": TOOL_DIGISEARCH_RESEARCH_DELEGATE,
            "description": "Delegated research turn on digisearch (HTTP composite). Returns citations and formatted context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_message": {"type": "string", "description": "Question or search intent"},
                    "index_name": {
                        "type": "string",
                        "description": "Optional index; defaults to workflow index",
                    },
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
) -> list[OpenAIToolDict]:
    """Return OpenAI tool dicts for the orchestrator surface."""
    ic = index_config or {}
    tools: list[OpenAIToolDict] = [build_search_tool(ic), build_fetch_all_tool(ic)]
    if include_research_delegate:
        tools.append(build_digisearch_research_delegate_tool())
    return tools
