"""Shared backend gate for digisearch entrypoints (HTTP server + MCP server).

Both ``digisearch.server`` (startup event) and ``digisearch.mcp_server.run_mcp``
call :func:`require_real_search_backend` so the backend precedence can never
drift between the two. Precedence: Cloudflare (canonical, legacy
``VECTORIZE_*``/``D1_*`` fallback) → Azure → Chroma → ``RuntimeError``,
unless ``DIGISEARCH_ALLOW_STUB=1`` (unit tests only, never production).
"""

from __future__ import annotations

import logging
import os

from digisearch.search._stub import _first_env

logger = logging.getLogger(__name__)


def require_real_search_backend() -> None:
    """Fail unless Vectorize, Azure, Chroma, or DIGISEARCH_ALLOW_STUB=1 is set."""
    allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_stub:
        logger.warning("digisearch: DIGISEARCH_ALLOW_STUB=1 — in-memory stub allowed (tests only).")
        return
    # Canonical-first, legacy-fallback (#2239 credential rename) -- same precedence
    # `_vectorize_backend` uses, so this startup gate can never disagree with the
    # backend it's gating.
    if _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID") and _first_env(
        "CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN"
    ):
        return
    from digisearch.indexes.backends import azure_search as _az

    azure_ok = False
    try:
        azure_ok = _az.is_azure_configured()
    except (OSError, ImportError, AttributeError, RuntimeError, TypeError) as exc:
        logger.warning("Azure backend probe failed at startup: %s", exc)
        azure_ok = False
    chroma_ok = bool(os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"))
    if not azure_ok and not chroma_ok:
        raise RuntimeError(
            "digisearch requires a real backend: set CLOUDFLARE_ACCOUNT_ID+CLOUDFLARE_API_TOKEN "
            "(or legacy VECTORIZE_*/D1_* names), AZURE_SEARCH_* or CHROMA_PATH/CHROMA_HOST, "
            "or DIGISEARCH_ALLOW_STUB=1 for tests only."
        )
