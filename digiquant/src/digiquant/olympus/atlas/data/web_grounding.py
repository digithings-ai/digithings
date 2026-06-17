"""Web-grounding pre-pass for research phases via xAI Agent Tools ``web_search`` (#650).

Replaces the deprecated Live Search ``search_parameters`` path (HTTP 410). For a
``live_search`` phase we run a read-only search pass through the Responses API,
scoped to the curated domain allowlist, and return a cited summary that the caller
injects into ``phase_inputs`` before the normal research completion. Fails soft:
returns ``None`` (ungrounded) for non-xAI models or any error.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa  # scored-lint suppression: heterogeneous yaml config

import yaml

from digigraph.llm_client import web_search

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"

# xAI web_search rejects (HTTP 400) more than 5 allowed_domains per request.
_MAX_ALLOWED_DOMAINS = 5


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
    """Per-segment allowlist (capped at the xAI 5-domain limit), else the default."""
    per_segment = cfg.get("per_segment") or {}
    domains = per_segment.get(segment) or cfg.get("web_allowed_websites", [])
    return list(domains)[:_MAX_ALLOWED_DOMAINS] or None


def fetch_web_grounding(
    *,
    model: str,
    segment: str,
    run_date: date,
    scope: str = "",
) -> dict[str, Any] | None:
    """Return ``{"summary", "sources", "as_of"}`` web grounding for a segment, or None.

    ``None`` when the model isn't xAI, the search yields nothing, or the API errors —
    the caller then proceeds with data-tool-only (ungrounded) research.
    """
    cfg = _config()
    allowed = _domains_for(segment, cfg)
    max_results = int(cfg.get("max_search_results", 8))
    result = web_search(
        model,
        _build_query(segment, run_date, scope),
        allowed_domains=allowed,
        max_results=max_results,
    )
    if result is None:
        return None
    summary, sources = result
    if not summary.strip():
        return None
    return {"summary": summary, "sources": sources, "as_of": run_date.isoformat()}
