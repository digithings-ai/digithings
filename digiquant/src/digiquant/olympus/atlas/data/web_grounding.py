"""Web-grounding pre-pass for research phases (#650 / #2567).

For ``live_search`` segments, runs a read-only search pass and returns a cited
summary injected into ``phase_inputs`` before the normal structured-output
research call.

Olympus grounding uses **web-search-capable models only** (Perplexity /
``:online``) via :func:`digigraph.model_config.get_grounding_model` — provider
built-in search through :func:`digillm.openrouter_web_search`'s native branch.
The Exa ``openrouter:web_search`` server-tool path stays available as a digillm
toolkit fallback for non-native models; Olympus does not assemble Exa params.

Requires ``OPENROUTER_API_KEY``. Fails soft on error or missing key unless
``OLYMPUS_WEB_SEARCH=required``.
"""

from __future__ import annotations

import os
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous yaml config
)

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"

# Soft focus hint for the grounding query (native search ignores Exa allowlists).
_MAX_ALLOWED_DOMAINS = 5


class OlympusWebSearchError(RuntimeError):
    """Web grounding was required (``OLYMPUS_WEB_SEARCH=required``) but unavailable."""


def olympus_web_search_required() -> bool:
    """Return True when the run must fail if web grounding is unavailable."""
    return os.environ.get("OLYMPUS_WEB_SEARCH", "").strip().lower() in (
        "required",
        "1",
        "true",
        "yes",
    )


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_query(segment: str, run_date: date, scope: str) -> str:
    q = (
        f"For the '{segment}' segment of a daily market-research brief dated "
        f"{run_date.isoformat()}, search the web for the latest material developments — "
        "news, sentiment, positioning, fund/ETF flows, options/derivatives signals, and "
        "official (Fed/Treasury/regulatory) statements as relevant to this segment. "
    )
    if scope:
        q += f"Focus on: {scope}. "
    q += "Summarize the key findings as concise bullet points with inline source citations."
    return q


def _domains_for(segment: str, cfg: dict[str, Any]) -> list[str] | None:
    """Per-segment allowlist (capped), else the default list."""
    per_segment = cfg.get("per_segment") or {}
    domains = per_segment.get(segment) or cfg.get("web_allowed_websites", [])
    return list(domains)[:_MAX_ALLOWED_DOMAINS] or None


def _openrouter_web_search(model: str, query: str) -> tuple[str, list[str]] | None:
    """Olympus grounding dispatch — native search models only (no Exa params)."""
    if not model.startswith("openrouter/"):
        return None
    from digigraph.llm_client import openrouter_web_search

    # Do not pass engine=/max_results=/allowed_domains= — those only apply to the
    # digillm Exa toolkit branch, which Olympus must not use (#2567).
    return openrouter_web_search(model, query)


def fetch_web_grounding(
    *,
    model: str,
    segment: str,
    run_date: date,
    scope: str = "",
) -> dict[str, Any] | None:
    """Return ``{"summary", "sources", "as_of"}`` web grounding for a segment, or None."""
    cfg = _config()
    # Domain list is folded into the natural-language query focus only; native
    # provider search does not accept Exa allowlist tool params.
    allowed = _domains_for(segment, cfg)
    focus = scope
    if allowed:
        focus = (f"{scope} Prefer sources among: {', '.join(allowed)}.").strip()
    result = _openrouter_web_search(model, _build_query(segment, run_date, focus))
    if result is None:
        if olympus_web_search_required():
            raise OlympusWebSearchError(
                f"OLYMPUS_WEB_SEARCH=required but web search returned no results for {segment!r}"
            )
        return None
    summary, sources = result
    if not summary.strip():
        if olympus_web_search_required():
            raise OlympusWebSearchError(
                f"OLYMPUS_WEB_SEARCH=required but web search returned empty text for {segment!r}"
            )
        return None
    return {"summary": summary, "sources": sources, "as_of": run_date.isoformat()}
