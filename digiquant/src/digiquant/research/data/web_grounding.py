"""Web-grounding pre-pass for research phases (#650 / #2567 / #3853).

For ``live_search`` segments, tries the first-party digisearch ``web_search``
tool first (enforced ``include_domains`` from ``search_domains.yaml``) and
falls back to a read-only synthesis pass, returning a cited summary injected
into ``phase_inputs`` before the normal structured-output research call.

The tool call goes through digigraph's orchestrator hub (``POST
/v1/orchestrator_invoke``) — never ``import digisearch`` — mirroring how the
legacy fallback lazily imports ``digigraph.llm_client`` below. The fallback
synthesizes via a plain digillm completion over in-house retrieval context
(:func:`digigraph.model_config.get_grounding_model` selects the synthesis
model from the tier's ``web_search_models`` cheap-only pins). Citations are
model-recalled only; the prompt forbids inventing sources.

Fails soft on error or missing key unless ``DIGIQUANT_WEB_SEARCH=required``.
"""

from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous yaml config
)

import yaml

from digiquant.dashboard.envcompat import WEB_SEARCH, env_lookup

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"

# Enforced include_domains cap on the first-party web_search tool call.
_MAX_ALLOWED_DOMAINS = 5


class DashboardWebSearchError(RuntimeError):
    """Web grounding was required (``OLYMPUS_WEB_SEARCH=required``) but unavailable."""


def dashboard_web_search_required() -> bool:
    """Return True when the run must fail if web grounding is unavailable."""
    return env_lookup(WEB_SEARCH).strip().lower() in (
        "required",
        "1",
        "true",
        "yes",
    )


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_query(segment: str, run_date: date | str, scope: str = "") -> str:
    run_label = run_date.isoformat() if isinstance(run_date, date) else str(run_date)
    q = (
        f"For the '{segment}' segment of a daily market-research brief dated "
        f"{run_label}, search the web for the latest material developments — "
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
    """dashboard grounding dispatch — plain completion synthesis via llm_client."""
    from digigraph.llm_client import openrouter_web_search

    # No prefix gate and no Exa params: the wrapper synthesizes over whatever
    # model the house routes (fail-soft None on error).
    return openrouter_web_search(model, query)


def _pipeline_bearer() -> str | None:
    """Service JWT for pipeline hub calls (Task 1 ``digibase.service_auth``).

    Lazy import so this module imports cleanly when digibase is minimal.
    ``ServiceAuthError`` propagates — callers map it to fail-hard.
    """
    try:
        from digibase.service_auth import get_service_jwt
    except ImportError:
        return None
    return get_service_jwt()


def call_web_search_tool(
    *,
    query: str,
    include_domains: list[str],
    max_results: int,
    bearer_token: str | None = None,
) -> dict[str, Any]:
    """First-party web_search tool via digigraph's orchestrator hub (#3853).

    Carries the Task 1 service JWT (#3859): an explicit ``bearer_token`` wins,
    else :func:`_pipeline_bearer` mints one via digikey. The token threads
    into ``_call_digisearch_web_search`` via ``ToolContext.state``
    (``digi_bearer``) — the only bearer seam on its signature.

    Returns ``{"summary", "sources"}`` in the digigraph-compatible shape.
    Raises ``RuntimeError`` when the service errors or yields no rows so the
    caller falls back to synthesis. Never imports digisearch directly — the
    call goes over HTTP (``POST /v1/orchestrator_invoke``), mirroring how
    :func:`_openrouter_web_search` lazily imports ``digigraph.llm_client``.
    """
    from digigraph.orchestration.registry import ToolContext
    from digigraph.orchestration.web_search_tools import _call_digisearch_web_search

    token = bearer_token if bearer_token is not None else _pipeline_bearer()
    context = ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"digi_bearer": token} if token else {},
    )
    tool_out = _call_digisearch_web_search(
        query,
        include_domains=list(include_domains or []),
        max_results=max_results,
        context=context,
    )
    rows = (tool_out or {}).get("results") or []
    lines: list[str] = []
    sources: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("doc_id") or "").strip()
        if not url:
            continue
        meta = row.get("metadata") or {}
        title = str(meta.get("title") or url).strip() or url
        snippet = str(row.get("content") or "").strip()
        line = f"- [{title}]({url})"
        if snippet:
            line += f": {snippet}"
        lines.append(line)
        sources.append(url)
    if not lines:
        raise RuntimeError("digisearch web_search returned no rows")
    return {"summary": "\n".join(lines), "sources": sources}


def fetch_web_grounding(
    *,
    model: str,
    segment: str,
    run_date: date | str,
    scope: str = "",
) -> dict[str, Any] | None:
    """Return ``{"summary", "sources", "as_of"}`` web grounding for a segment, or None."""
    cfg = _config()
    # Tool-first (#3853): search_domains.yaml is the enforced include_domains
    # contract on the first-party web_search tool (capped at 5). The legacy
    # synthesis fallback still gets the domains as a soft query preference.
    domains = _domains_for(segment, cfg) or []
    try:
        max_results = int(cfg.get("max_search_results", 4) or 4)
    except (TypeError, ValueError):
        max_results = 4
    max_results = max(1, min(max_results, 10))
    as_of = run_date.isoformat() if isinstance(run_date, date) else str(run_date)
    try:
        tool_out = call_web_search_tool(
            query=_build_query(segment, run_date, scope),
            include_domains=domains,
            max_results=max_results,
        )
        summary = str(tool_out.get("summary") or "").strip()
        sources = list(tool_out.get("sources") or [])
        if summary:
            return {"summary": summary, "sources": sources, "as_of": as_of}
    except Exception:
        # Broad by design (Task 6 pattern): missing extra, 503, transport
        # errors, empty rows — all fall back to synthesis below.
        logger.debug("digisearch web_search tool failed; falling back to synthesis", exc_info=True)
    allowed = domains or None
    focus = scope
    if allowed:
        focus = (f"{scope} Prefer sources among: {', '.join(allowed)}.").strip()
    result = _openrouter_web_search(model, _build_query(segment, run_date, focus))
    if result is None:
        if dashboard_web_search_required():
            raise DashboardWebSearchError(
                f"OLYMPUS_WEB_SEARCH=required but web search returned no results for {segment!r}"
            )
        return None
    summary, sources = result
    if not summary.strip():
        if dashboard_web_search_required():
            raise DashboardWebSearchError(
                f"OLYMPUS_WEB_SEARCH=required but web search returned empty text for {segment!r}"
            )
        return None
    return {"summary": summary, "sources": sources, "as_of": as_of}
