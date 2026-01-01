"""Phase-scoped blinding for dashboard retrieval tools and provider prompts (spec §6.1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import (  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes
    Any,
    Literal,
)

from digiquant.dashboard.research_retrieval.planner import (
    DELIBERATION_SELECTION_PROMPT_FORBIDDEN_KEYS,
    assert_no_materiality_in_prompt,
)

RetrievalPhase = Literal[
    "research_edit",
    "thesis",
    "market",
    "analyst",
    "deliberation",
    "direction",
    "sizing",
]

PromptRole = Literal["analyst", "deliberation"]

DIGEST_DOCUMENT_KEY = "digest"

_ANALYST_BLOCKED_DOC_PREFIXES = ("analyst/", "deliberation/", "pm-", "digest")
_ANALYST_BLOCKED_DOC_KEYS = frozenset({DIGEST_DOCUMENT_KEY, "beliefs"})

_PORTFOLIO_ALLOWED_PHASES = frozenset(
    {
        "research_edit",
        "thesis",
        "market",
        "direction",
        "sizing",
    }
)

# Portfolio / PM context must not enter analyst/deliberation provider prompts (WP14.2 blinding).
_ANALYST_DELIBERATION_PROMPT_FORBIDDEN_KEYS = frozenset(
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

_DELIBERATION_EXTRA_FORBIDDEN_KEYS = frozenset(
    {
        "prior_deliberation",
        "deliberation_selection",
    }
)


def portfolio_tool_allowed(phase: RetrievalPhase) -> bool:
    """Return whether ``query_portfolio`` is exposed for *phase*."""
    return phase in _PORTFOLIO_ALLOWED_PHASES


def research_document_allowed(phase: RetrievalPhase, document_key: str) -> bool:
    """Return whether ``query_research`` may fetch *document_key* in *phase*."""
    if phase != "analyst":
        return True
    key = document_key.strip()
    if key in _ANALYST_BLOCKED_DOC_KEYS:
        return False
    return not any(key.startswith(prefix) for prefix in _ANALYST_BLOCKED_DOC_PREFIXES)


def forbidden_prompt_keys(role: PromptRole) -> frozenset[str]:
    """Return keys that must not appear in provider ``phase_inputs`` for *role*."""
    keys = set(_ANALYST_DELIBERATION_PROMPT_FORBIDDEN_KEYS) | set(DELIBERATION_SELECTION_PROMPT_FORBIDDEN_KEYS)
    if role == "deliberation":
        keys |= _DELIBERATION_EXTRA_FORBIDDEN_KEYS
    return frozenset(keys)


def strip_blinded_forbidden_keys(
    phase_inputs: Mapping[str, Any],
    *,
    role: PromptRole,
) -> dict[str, Any]:
    """Return a copy of *phase_inputs* with blinding-forbidden keys removed."""
    blocked = forbidden_prompt_keys(role)
    return {key: value for key, value in phase_inputs.items() if key not in blocked}


def assert_blinded_analyst_prompt(phase_inputs: Mapping[str, Any]) -> None:
    """Hard guard: analyst prompts must not include portfolio/PM/materiality leakage."""
    leaked = forbidden_prompt_keys("analyst").intersection(phase_inputs)
    if leaked:
        raise ValueError(f"analyst prompt must not include blinded keys: {sorted(leaked)}")
    assert_no_materiality_in_prompt(phase_inputs)


def assert_blinded_deliberation_prompt(phase_inputs: Mapping[str, Any]) -> None:
    """Hard guard: deliberation prompts must not include portfolio/PM/materiality leakage."""
    leaked = forbidden_prompt_keys("deliberation").intersection(phase_inputs)
    if leaked:
        raise ValueError(f"deliberation prompt must not include blinded keys: {sorted(leaked)}")
    assert_no_materiality_in_prompt(phase_inputs)


__all__ = [
    "DIGEST_DOCUMENT_KEY",
    "PromptRole",
    "RetrievalPhase",
    "assert_blinded_analyst_prompt",
    "assert_blinded_deliberation_prompt",
    "forbidden_prompt_keys",
    "portfolio_tool_allowed",
    "research_document_allowed",
    "strip_blinded_forbidden_keys",
]
