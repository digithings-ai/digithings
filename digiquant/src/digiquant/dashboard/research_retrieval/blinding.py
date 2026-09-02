"""Phase-scoped blinding for dashboard retrieval tools and provider prompts (spec §6.1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
)

from digiquant.dashboard.research_retrieval.planner import (
    H6_SELECTION_PROMPT_FORBIDDEN_KEYS,
    assert_no_materiality_in_prompt,
)

RetrievalPhase = Literal[
    "research_edit",
    "h1_thesis",
    "h2_thesis",
    "h5_analyst",
    "h6_deliberation",
    "h7_pm",
    "h8_sizing",
]

PromptRole = Literal["h5_analyst", "h6_deliberation"]

DIGEST_DOCUMENT_KEY = "digest"

_H5_BLOCKED_DOC_PREFIXES = ("analyst/", "deliberation/", "pm-")
_H5_BLOCKED_DOC_KEYS = frozenset({DIGEST_DOCUMENT_KEY, "beliefs"})

_PORTFOLIO_ALLOWED_PHASES = frozenset(
    {
        "research_edit",
        "h1_thesis",
        "h2_thesis",
        "h7_pm",
        "h8_sizing",
    }
)

# Portfolio / PM context must not enter H5/H6 provider prompts (WP14.2 blinding).
_H5_H6_PROMPT_FORBIDDEN_KEYS = frozenset(
    {
        "prior_book",
        "active_theses",
        "current_weights",
        "positions",
        "nav",
        "portfolio_metrics",
        "decision_lessons",
        "query_portfolio",
        "pm_direction",
        "deliberation/",
    }
)

_H6_EXTRA_FORBIDDEN_KEYS = frozenset(
    {
        "prior_deliberation",
        "h6_selection",
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


def forbidden_prompt_keys(role: PromptRole) -> frozenset[str]:
    """Return keys that must not appear in provider ``phase_inputs`` for *role*."""
    keys = set(_H5_H6_PROMPT_FORBIDDEN_KEYS) | set(H6_SELECTION_PROMPT_FORBIDDEN_KEYS)
    if role == "h6_deliberation":
        keys |= _H6_EXTRA_FORBIDDEN_KEYS
    return frozenset(keys)


def strip_blinded_forbidden_keys(
    phase_inputs: Mapping[str, Any],
    *,
    role: PromptRole,
) -> dict[str, Any]:
    """Return a copy of *phase_inputs* with blinding-forbidden keys removed."""
    blocked = forbidden_prompt_keys(role)
    return {key: value for key, value in phase_inputs.items() if key not in blocked}


def assert_blinded_h5_prompt(phase_inputs: Mapping[str, Any]) -> None:
    """Hard guard: H5 prompts must not include portfolio/PM/materiality leakage."""
    leaked = forbidden_prompt_keys("h5_analyst").intersection(phase_inputs)
    if leaked:
        raise ValueError(f"H5 prompt must not include blinded keys: {sorted(leaked)}")
    assert_no_materiality_in_prompt(phase_inputs)


def assert_blinded_h6_prompt(phase_inputs: Mapping[str, Any]) -> None:
    """Hard guard: H6 prompts must not include portfolio/PM/materiality leakage."""
    leaked = forbidden_prompt_keys("h6_deliberation").intersection(phase_inputs)
    if leaked:
        raise ValueError(f"H6 prompt must not include blinded keys: {sorted(leaked)}")
    assert_no_materiality_in_prompt(phase_inputs)


__all__ = [
    "DIGEST_DOCUMENT_KEY",
    "PromptRole",
    "RetrievalPhase",
    "assert_blinded_h5_prompt",
    "assert_blinded_h6_prompt",
    "forbidden_prompt_keys",
    "portfolio_tool_allowed",
    "research_document_allowed",
    "strip_blinded_forbidden_keys",
]
