"""MCP-free grokipedia tool helpers (JSON strings, fail-closed).

Keeping this out of ``mcp_server.py`` avoids importing ``mcp`` in unit tests
that only exercise the client, matching ``research_search.py``.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from digisearch.grokipedia.client import (
    GrokipediaError,
    GrokipediaNotFoundError,
    GrokipediaRateLimitError,
    GrokipediaRobotsError,
    get_shared_client,
)
from digisearch.grokipedia.models import GrokipediaPage

CONTENT_PREVIEW_CHARS = 20_000
MAX_CITATIONS = 10


def _error_string(op: str, exc: Exception) -> str:
    if isinstance(exc, GrokipediaRobotsError):
        return f"[grokipedia disabled: {exc}]"
    if isinstance(exc, GrokipediaRateLimitError):
        return f"[grokipedia rate limited: {exc}]"
    if isinstance(exc, GrokipediaNotFoundError):
        return f"[grokipedia not found: {exc}]"
    return f"[grokipedia {op} error: {exc}]"


def _page_for_mcp(page: GrokipediaPage) -> dict[str, Any]:
    content = page.content
    truncated = page.truncated
    if content is not None and len(content) > CONTENT_PREVIEW_CHARS:
        content = content[:CONTENT_PREVIEW_CHARS]
        truncated = True
    citations = [c.model_dump(mode="json") for c in page.citations[:MAX_CITATIONS]]
    return {
        "slug": page.slug,
        "title": page.title,
        "description": page.description,
        "content": content,
        "citations": citations,
        "url": page.url,
        "truncated": truncated,
    }


def grokipedia_search(query: str, limit: int = 10) -> str:
    """Search grokipedia. Returns JSON ``GrokipediaSearchResponse`` or an error string."""
    try:
        response = get_shared_client().search(query, limit=limit)
    except (GrokipediaError, ValidationError, ValueError) as exc:
        return _error_string("search", exc)
    return response.model_dump_json()


def grokipedia_get_page(slug: str) -> str:
    """Fetch one grokipedia page (JSON). Content is capped for MCP payloads."""
    try:
        page = get_shared_client().get_page(slug)
    except (GrokipediaError, ValidationError, ValueError) as exc:
        return _error_string("get_page", exc)
    return json.dumps(_page_for_mcp(page))


def grokipedia_typeahead(query: str, limit: int = 8) -> str:
    """Cheap grokipedia typeahead. Returns JSON or an error string."""
    try:
        response = get_shared_client().typeahead(query, limit=limit)
    except (GrokipediaError, ValidationError, ValueError) as exc:
        return _error_string("typeahead", exc)
    return response.model_dump_json()
