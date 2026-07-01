"""Phase-scoped blinding for Olympus retrieval tools (spec §6.1)."""

from __future__ import annotations

from typing import Literal

RetrievalPhase = Literal[
    "atlas_edit",
    "h1_thesis",
    "h2_thesis",
    "h5_analyst",
    "h6_deliberation",
    "h7_pm",
    "h8_sizing",
]

DIGEST_DOCUMENT_KEY = "digest"

_H5_BLOCKED_DOC_PREFIXES = ("analyst/", "deliberation/", "pm-")
_H5_BLOCKED_DOC_KEYS = frozenset({DIGEST_DOCUMENT_KEY, "beliefs"})

_PORTFOLIO_ALLOWED_PHASES = frozenset(
    {
        "atlas_edit",
        "h1_thesis",
        "h2_thesis",
        "h7_pm",
        "h8_sizing",
    }
)


def portfolio_tool_allowed(phase: RetrievalPhase) -> bool:
    """Return whether ``query_portfolio`` is exposed for *phase*."""
    return phase in _PORTFOLIO_ALLOWED_PHASES


def research_document_allowed(phase: RetrievalPhase, document_key: str) -> bool:
    """Return whether ``query_research`` may fetch *document_key* in *phase*."""
    if phase != "h5_analyst":
        return True
    key = document_key.strip()
    if key in _H5_BLOCKED_DOC_KEYS:
        return False
    return not any(key.startswith(prefix) for prefix in _H5_BLOCKED_DOC_PREFIXES)
