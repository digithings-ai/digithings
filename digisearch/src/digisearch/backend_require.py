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

logger = logging.getLogger(__name__)

_LEGACY_WARNED: set[str] = set()


def _first_env(*names: str) -> str:
    """Return the first non-empty, stripped env var among ``names``.

    Canonical-first, legacy-fallback precedence (#2239 credential rename):
    every credential read tries ``CLOUDFLARE_ACCOUNT_ID`` /
    ``CLOUDFLARE_API_TOKEN`` first, then the legacy ``VECTORIZE_*`` / ``D1_*``
    names. Single home for this helper (S18 review): ``search._stub`` and
    ``embedding.factory`` import it from here instead of redefining it.
    """
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _env_truthy(name: str, default: str = "0") -> bool:
    """True when env *name* (or *default* when unset) reads as truthy."""
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _warn_legacy_env(canonical: str, *legacy: str) -> None:
    if os.environ.get(canonical, "").strip():
        return
    for name in legacy:
        if os.environ.get(name, "").strip():
            if name not in _LEGACY_WARNED:
                _LEGACY_WARNED.add(name)
                logger.warning("Using deprecated env var %s; set %s instead", name, canonical)
            return


def selected_index_backend() -> str | None:
    """Return the explicitly selected index backend, or ``None`` for legacy selection.

    ``DIGISEARCH_INDEX_BACKEND`` is the named selector (``sqlite``, ``chroma``,
    ``azure``, ``vectorize`` or ``stub``). When unset, legacy precedence is
    preserved and the local caller defaults to sqlite.
    """
    raw = os.environ.get("DIGISEARCH_INDEX_BACKEND", "").strip().lower()
    return raw or None


def require_real_search_backend() -> None:
    """Fail unless a real backend is selected and configured.

    The default (no ``DIGISEARCH_INDEX_BACKEND`` and no legacy Chroma/Vectorize
    configuration) is the local SQLite exact-scan backend, which always exists.
    """
    allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if allow_stub:
        logger.warning("digisearch: DIGISEARCH_ALLOW_STUB=1 — in-memory stub allowed (tests only).")
        return

    explicit = selected_index_backend()
    if explicit == "sqlite":
        return
    if explicit == "stub":
        raise RuntimeError(
            "DIGISEARCH_INDEX_BACKEND=stub requires DIGISEARCH_ALLOW_STUB=1 (tests only)."
        )
    if explicit not in (None, "azure", "vectorize", "chroma"):
        raise RuntimeError(
            "DIGISEARCH_INDEX_BACKEND must be one of: sqlite, chroma, azure, vectorize, stub."
        )

    # Canonical-first, legacy-fallback (#2239 credential rename) -- same precedence
    # `_vectorize_backend` uses, so this startup gate can never disagree with the
    # backend it's gating.
    _warn_legacy_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
    _warn_legacy_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    vectorize_ok = bool(
        _first_env("CLOUDFLARE_ACCOUNT_ID", "VECTORIZE_ACCOUNT_ID", "D1_ACCOUNT_ID")
        and _first_env("CLOUDFLARE_API_TOKEN", "VECTORIZE_API_TOKEN", "D1_API_TOKEN")
    )
    if explicit == "vectorize":
        if vectorize_ok:
            return
        raise RuntimeError(
            "DIGISEARCH_INDEX_BACKEND=vectorize requires "
            "CLOUDFLARE_ACCOUNT_ID+CLOUDFLARE_API_TOKEN (or legacy VECTORIZE_*/D1_* names)."
        )
    if explicit == "azure":
        if _azure_configured():
            return
        raise RuntimeError("DIGISEARCH_INDEX_BACKEND=azure requires AZURE_SEARCH_* configuration.")
    if explicit == "chroma":
        if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"):
            return
        raise RuntimeError("DIGISEARCH_INDEX_BACKEND=chroma requires CHROMA_PATH or CHROMA_HOST.")
    if vectorize_ok:
        return
    if _azure_configured():
        return
    if os.environ.get("CHROMA_PATH") or os.environ.get("CHROMA_HOST"):
        return
    # No explicit selector and no remote/Chroma config: the sqlite default is real.


def _azure_configured() -> bool:
    from digisearch.indexes.backends import azure_search as _az

    try:
        return bool(_az.is_azure_configured())
    except (OSError, ImportError, AttributeError, RuntimeError, TypeError) as exc:
        logger.warning("Azure backend probe failed at startup: %s", exc)
        return False
