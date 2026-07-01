"""LLM tool definitions for Olympus retrieval (spec §6.1)."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.research_retrieval.blinding import RetrievalPhase
from digiquant.olympus.research_retrieval.cache import ResearchCache
from digiquant.olympus.research_retrieval.queries import (
    extract_section,
    query_portfolio,
    query_research,
)

logger = logging.getLogger(__name__)

RESEARCH_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_research",
            "description": (
                "Fetch a research vertical document or daily digest snapshot from Supabase. "
                "Use document_key (e.g. macro, equity, digest) or segment slug. "
                "as_of_date defaults to the latest row strictly before run_date."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_key": {"type": "string"},
                    "segment": {"type": "string"},
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_prior_document",
            "description": (
                "Fetch prior materialized document body (or one section) for edit-mode patching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "document_key": {"type": "string"},
                    "section_path": {
                        "type": "string",
                        "description": "JSON Pointer path; omit for full body",
                    },
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["document_key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_portfolio",
            "description": (
                "Fetch positions, NAV, active theses, and recent decision_log lessons. "
                "Not available on blinded analyst phases."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "ticker": {"type": "string"},
                },
            },
        },
    },
]


def _parse_optional_date(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    return date.fromisoformat(str(raw)[:10])


def build_research_tool_dispatcher(
    client: SupabaseClient,
    *,
    run_date: date,
    phase: RetrievalPhase,
    cache: ResearchCache | None = None,
    watchlist: tuple[str, ...] = (),
) -> Callable[[str, dict[str, Any]], str]:
    """Return ``execute_tool(name, args) -> json_str`` for retrieval tools."""

    def execute_tool(name: str, args: dict[str, Any]) -> str:
        try:
            if name == "query_research":
                result = query_research(
                    client,
                    run_date=run_date,
                    document_key=args.get("document_key"),
                    segment=args.get("segment"),
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    phase=phase,
                    cache=cache,
                )
            elif name == "fetch_prior_document":
                document_key = args.get("document_key")
                if not document_key:
                    return "Error: fetch_prior_document requires document_key"
                research = query_research(
                    client,
                    run_date=run_date,
                    document_key=str(document_key),
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    phase=phase,
                    cache=cache,
                )
                if "error" in research:
                    result = research
                else:
                    payload = research.get("payload")
                    body = payload if isinstance(payload, dict) else {}
                    result = extract_section(body, args.get("section_path"))
            elif name == "query_portfolio":
                result = query_portfolio(
                    client,
                    run_date=run_date,
                    phase=phase,
                    as_of_date=_parse_optional_date(args.get("as_of_date")),
                    ticker=args.get("ticker"),
                    watchlist=watchlist,
                )
            else:
                return f"Error: unknown tool {name!r}"
            return json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — tool errors are returned to the model
            logger.warning("research tool %s failed: %s", name, exc)
            return f"Error: {name} failed: {exc}"

    return execute_tool
