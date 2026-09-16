"""Fail-fast pre-flight health check for the web_search tool (#4198).

The daily digiquant book pipeline grounds every research phase on the
first-party ``web_search`` tool (no fallbacks, #3859). On 2026-09-15 a dead
search provider let the pipeline burn ~3h of compute before the run failed;
this check proves the real call chain answers *before* any research phase
starts. Healthy means an ``ok: true`` hub envelope with at least one result
row — a soft ``{"ok": false, ...}`` envelope is precisely the failure mode
this check exists to catch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Fixed, cheap probe: one request, one row, no domain allowlist. Any query
# returns rows when the provider is healthy; determinism keeps the check
# comparable run to run.
_HEALTH_QUERY = "python"
_HEALTH_MAX_RESULTS = 1
_DEFAULT_TIMEOUT_S = 25.0


class WebSearchHealthError(RuntimeError):
    """The web_search tool failed its fail-fast pre-flight check (#4198)."""


@dataclass(frozen=True)
class WebSearchHealth:
    """Outcome of a successful web_search pre-flight probe."""

    ok: bool
    endpoint: str
    elapsed_s: float
    results: int
    error: str = ""


def resolve_web_search_endpoint() -> str:
    """Return the ``/v1/orchestrator_invoke`` URL the pipeline grounds through."""
    try:
        from digigraph.orchestration.tool_common import _digisearch_service_base

        return f"{_digisearch_service_base().strip().rstrip('/')}/v1/orchestrator_invoke"
    except Exception as exc:  # diagnostics only — never the failure itself
        return f"(unconfigured: {exc})"


def check_web_search_health(*, timeout_s: float = _DEFAULT_TIMEOUT_S) -> WebSearchHealth:
    """Exercise the real web_search path once; raise unless it is healthy.

    Calls ``call_web_search_tool`` (digiquant -> digigraph hub -> POST
    ``/v1/orchestrator_invoke`` -> ``web_search``) and fails hard on any
    provider error, HTTP 5xx/429, empty result set, malformed envelope,
    timeout, or connection error. Never degrades or falls back: when this
    raises, the run is invalid and must stop before research starts.
    """
    from digigraph.orchestration.web_search_tools import WEB_SEARCH_TOOL_NAME

    from digiquant.research.data.web_grounding import call_web_search_tool

    endpoint = resolve_web_search_endpoint()
    started = time.monotonic()
    try:
        out = call_web_search_tool(
            query=_HEALTH_QUERY,
            include_domains=[],
            max_results=_HEALTH_MAX_RESULTS,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        raise WebSearchHealthError(
            f"{WEB_SEARCH_TOOL_NAME} pre-flight failed: tool={WEB_SEARCH_TOOL_NAME} "
            f"endpoint={endpoint} elapsed={elapsed:.2f}s error={exc}"
        ) from exc
    elapsed = time.monotonic() - started
    sources = [s for s in (out.get("sources") or []) if str(s).strip()]
    if not sources:
        raise WebSearchHealthError(
            f"{WEB_SEARCH_TOOL_NAME} pre-flight failed: tool={WEB_SEARCH_TOOL_NAME} "
            f"endpoint={endpoint} elapsed={elapsed:.2f}s "
            "error=healthy envelope carried zero result rows"
        )
    return WebSearchHealth(ok=True, endpoint=endpoint, elapsed_s=elapsed, results=len(sources))
