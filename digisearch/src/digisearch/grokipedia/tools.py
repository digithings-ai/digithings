"""MCP-facing wrappers. Always return JSON strings; never raise to the server."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from digisearch.grokipedia.client import GrokipediaClient
from digisearch.grokipedia.models import GrokipediaError

logger = logging.getLogger(__name__)

_client: GrokipediaClient | None = None


def set_client(client: GrokipediaClient | None) -> None:
    """Replace the process-wide client (tests). Pass ``None`` to reset."""
    global _client
    _client = client


def get_client() -> GrokipediaClient:
    global _client
    if _client is None:
        _client = GrokipediaClient()
    return _client


def _dump(model: Any) -> str:
    return model.model_dump_json()


def _caught(op: str, exc: Exception) -> str:
    logger.error("grokipedia %s failed: %s", op, exc)
    return GrokipediaError(error=f"{op} failed: {exc}").model_dump_json()


def grokipedia_search(query: str, limit: int = 10) -> str:
    """Search grokipedia.com via ``GET /api/full-text-search`` (unofficial spike)."""
    try:
        return _dump(get_client().search(query, limit=limit))
    except (ValidationError, TypeError, ValueError, OSError, RuntimeError) as exc:
        return _caught("search", exc)


def grokipedia_get_page(slug: str, include_content: bool = True) -> str:
    """Fetch a grokipedia page via ``GET /api/page-preview`` (not ``/api/page``)."""
    try:
        return _dump(get_client().get_page(slug, include_content=include_content))
    except (ValidationError, TypeError, ValueError, OSError, RuntimeError) as exc:
        return _caught("get_page", exc)
