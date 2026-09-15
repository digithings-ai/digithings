"""Tool-only web grounding pre-pass for research phases (#650 / #2567 / #3853 / #3859).

For ``live_search`` segments, calls the first-party digisearch ``web_search``
tool (``search_domains.yaml`` passes straight through as the tool's
``include_domains`` / ``exclude_domains`` / ``max_results``) and returns a
cited summary injected into ``phase_inputs`` before the normal
structured-output research call.

The tool call goes through digigraph's orchestrator hub (``POST
/v1/orchestrator_invoke``) — never ``import digisearch``. There is no
synthesis fallback: a requested search must succeed or raise
:exc:`DashboardWebSearchError` unconditionally. A scoped search that returns no
rows retries once without the ``include_domains`` allowlist (logged) before
failing (#4086) — every row still comes from the tool, so the invariant holds.
Skipped-by-design segments (fresh ingested FRED layer, ``live_search=False``)
never reach this module.
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

logger = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "search_domains.yaml"

# Enforced caps on the first-party web_search tool call. digisearch's
# ``WebSearchRequest`` rejects the whole request over either (``include_domains``
# <= 5, ``exclude_domains`` <= 20), which fails the segment and so the book —
# the same class as the query cap (#4163).
_MAX_ALLOWED_DOMAINS = 5
_MAX_EXCLUDED_DOMAINS = 20


class DashboardWebSearchError(RuntimeError):
    """Requested web grounding failed — the run aborts rather than reasoning ungrounded."""


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


# digisearch's ``WebSearchRequest.query`` is ``Field(max_length=500)``
# (``digisearch/src/digisearch/web_search/models.py``, #3853). Enforced here as
# well so an oversize query from any caller degrades to a logged truncation
# instead of a ValidationError that fails a whole book run (#4163).
_MAX_QUERY_CHARS = 500


def call_web_search_tool(
    *,
    query: str,
    include_domains: list[str],
    max_results: int,
    bearer_token: str | None = None,
    exclude_domains: list[str] | None = None,
) -> dict[str, Any]:
    """First-party web_search tool via digigraph's orchestrator hub (#3853).

    Carries the Task 1 service JWT (#3859): an explicit ``bearer_token`` wins,
    else :func:`_pipeline_bearer` mints one via digikey. The token threads
    into ``_call_digisearch_web_search`` via ``ToolContext.state``
    (``digi_bearer``) — the only bearer seam on its signature.

    Domain scoping (``include_domains`` / ``exclude_domains``) and
    ``max_results`` pass straight through to the tool — never folded into the
    query text. Returns ``{"summary", "sources"}`` in the digigraph-compatible
    shape, plus ``relaxed_domains: True`` when the allowlist had to be relaxed.
    Raises ``RuntimeError`` when the service errors or when both the
    scoped search and its unscoped retry yield no rows (#4086).
    Never imports digisearch directly — the call goes over HTTP
    (``POST /v1/orchestrator_invoke``).
    """
    from digigraph.orchestration.registry import ToolContext
    from digigraph.orchestration.web_search_tools import call_digisearch_web_search

    if len(query) > _MAX_QUERY_CHARS:
        logger.warning(
            "web_search query is %d chars; digisearch caps it at %d - truncating",
            len(query),
            _MAX_QUERY_CHARS,
        )
        query = query[:_MAX_QUERY_CHARS].rsplit(" ", 1)[0] or query[:_MAX_QUERY_CHARS]

    token = bearer_token if bearer_token is not None else _pipeline_bearer()
    context = ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={"digi_bearer": token} if token else {},
    )

    def _search(include: list[str]) -> list[Any]:
        tool_out = call_digisearch_web_search(
            query,
            include_domains=include,
            exclude_domains=excluded,
            max_results=max_results,
            context=context,
        )
        return (tool_out or {}).get("results") or []

    scoped = list(include_domains or [])
    excluded = list(exclude_domains or [])
    rows = _search(scoped)
    relaxed_domains = False
    if not rows and scoped:
        # The hosted ddgs provider post-filters by domain (it cannot bias), so a
        # narrow allowlist can zero out an otherwise fine result set (#4086).
        logger.warning(
            "digisearch web_search returned no rows for include_domains=%s; "
            "retrying unscoped (max_results=%s)",
            scoped,
            max_results,
        )
        rows = _search([])
        relaxed_domains = True
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
        detail = f"scoped_domains={scoped!r}" if scoped else "unscoped"
        if relaxed_domains:
            detail += "; unscoped retry also returned no rows"
        raise RuntimeError(f"digisearch web_search returned no rows ({detail})")
    out: dict[str, Any] = {"summary": "\n".join(lines), "sources": sources}
    if relaxed_domains:
        out["relaxed_domains"] = True
    return out


def fetch_web_grounding(
    *,
    model: str = "",
    segment: str,
    run_date: date | str,
    scope: str = "",
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int | None = None,
) -> dict[str, Any]:
    """Return ``{"summary", "sources", "as_of"}`` web grounding for a segment.

    Tool-only: a requested search must succeed or raise
    :exc:`DashboardWebSearchError` — never ``None``. Domain scoping and the
    result count default to ``search_domains.yaml`` and pass straight through
    to the ``web_search`` tool. Propagates ``relaxed_domains: True`` when a
    scoped search had to be relaxed to keep real grounding flowing (#4086).
    ``model`` is accepted for caller compatibility and ignored: grounding
    comes from the tool, not a synthesis model.
    """
    cfg = _config()
    domains = (
        list(include_domains) if include_domains is not None else (_domains_for(segment, cfg) or [])
    )
    excluded = (
        list(exclude_domains)
        if exclude_domains is not None
        else list(cfg.get("web_excluded_websites") or [])
    )
    if len(excluded) > _MAX_EXCLUDED_DOMAINS:
        # Warned, not silent: dropping entries means we search a domain the
        # operator asked to exclude. digisearch would 400 the whole request.
        logger.warning(
            "exclude_domains has %d entries; digisearch caps it at %d - ignoring the rest",
            len(excluded),
            _MAX_EXCLUDED_DOMAINS,
        )
        excluded = excluded[:_MAX_EXCLUDED_DOMAINS]
    if max_results is None:
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
            exclude_domains=excluded,
            max_results=max_results,
        )
    except DashboardWebSearchError:
        raise
    except Exception as exc:
        raise DashboardWebSearchError(
            f"web_search tool failed for segment={segment!r}: {exc}"
        ) from exc
    summary = str(tool_out.get("summary") or "").strip()
    sources = list(tool_out.get("sources") or [])
    if not summary:
        raise DashboardWebSearchError(
            f"web_search tool returned empty summary for segment={segment!r}"
        )
    out: dict[str, Any] = {"summary": summary, "sources": sources, "as_of": as_of}
    if tool_out.get("relaxed_domains"):
        out["relaxed_domains"] = True
    return out
