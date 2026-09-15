"""digisearch MCP server. Exposes document search as MCP tools for digigraph/digiflow."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

from digisearch.core.models import Query
from digisearch.logging import configure_logging
from digisearch.monitors.models import DeliveryConfig, Watch, WatchSchedule
from digisearch.monitors.store import MonitorStore, MonitorStoreError, get_store
from digisearch.monitors.validation import watch_config_error
from digisearch.research_search import search_strategies as _search_strategies_impl
from digisearch.search._stub import query_index
from digisearch.web_search.models import summarize_validation_error

configure_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "digisearch",
    json_response=True,
)

DIGISEARCH_INDEX = os.environ.get("DIGISEARCH_INDEX", "default")

_digisearch_client: Any | None = None


def create_mcp_with_indexes(client: object) -> FastMCP:
    """Wire a digisearch client into the MCP server so tools use the real backend.

    Call this at startup when a configured client is available. Without it, tools
    fall back to the in-memory stub (development only).
    """
    global _digisearch_client
    _digisearch_client = client
    if client is not None:
        logger.info("digisearch MCP server wired to real client: %s", type(client).__name__)
    else:
        logger.warning("create_mcp_with_indexes called with None — MCP tools will use stub backend")
    return mcp


@mcp.tool()
def digisearch_query(
    text: str,
    index_name: str | None = None,
    top_k: int = 10,
    mode: str = "hybrid",
) -> str:
    """Search documents in digisearch. Returns relevant chunks for RAG or agent context.

    Use this when you need to find information in ingested documents (research papers,
    strategy docs, compliance docs, etc.). Supports keyword, vector, and hybrid search.
    """
    idx = index_name or DIGISEARCH_INDEX or "default"
    q = Query(text=text, top_k=top_k, mode=mode)
    if _digisearch_client is not None:
        try:
            results = _digisearch_client.query(text=text, index_name=idx, top_k=top_k, mode=mode)
            from digisearch.core.models import SearchResponse

            response = SearchResponse(results=results)
        except (RuntimeError, ValueError, ImportError, OSError, TypeError) as e:
            logger.error("digisearch client query failed: %s", e)
            return f"[digisearch query error: {e}]"
    else:
        allow_stub = os.environ.get("DIGISEARCH_ALLOW_STUB", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not allow_stub:
            return "digisearch MCP is not wired to a backend client and stub fallback is disabled."
        response = query_index(q, index_name=idx)
    if not response.results:
        return f"No results for query: {text!r}"
    lines = [f"Query: {text}\n---"]
    for r in response.results[:top_k]:
        meta = r.chunk.metadata
        parts = []
        if meta.get("subject"):
            parts.append(f"subject={meta['subject'][:80]!r}")
        if meta.get("fromName") or meta.get("fromAddress"):
            parts.append(f"from={meta.get('fromName') or meta.get('fromAddress')}")
        if meta.get("sourceType"):
            parts.append(f"source={meta['sourceType']}")
        if meta.get("sentDateTime") or meta.get("createdDateTime"):
            parts.append(f"date={meta.get('sentDateTime') or meta.get('createdDateTime')}")
        meta_line = " | ".join(parts) if parts else None
        content_preview = (
            (r.chunk.content[:400] + "...") if len(r.chunk.content) > 400 else r.chunk.content
        )
        if meta_line:
            lines.append(f"[score={r.score:.2f}] {meta_line}\n{content_preview}")
        else:
            lines.append(f"[score={r.score:.2f}] {content_preview}")
    return "\n\n".join(lines)


@mcp.tool()
def web_search(
    query: str,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 4,
) -> str:
    """Search the public web (first-party tool). Returns JSON WebSearchResponse."""
    try:
        from digisearch.web_search.models import (
            WebSearchConfigError,
            WebSearchRequest,
            summarize_validation_error,
        )
        from digisearch.web_search.service import run_web_search
    except ImportError as e:
        return f"[web_search unavailable: install digisearch[web-search] for web_search: {e}]"
    try:
        req = WebSearchRequest(
            query=query,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            max_results=max_results,
        )
    except ValidationError as e:
        return f"[web_search invalid input: {summarize_validation_error(e)}]"
    try:
        return run_web_search(req).model_dump_json()
    except WebSearchConfigError as e:
        return f"[web_search unavailable: {e}]"


@mcp.tool()
def search_strategies(
    query: str,
    top_k: int = 10,
    date_from_ymd: int | None = None,
    date_to_ymd: int | None = None,
    doc_type: str | None = None,
    segment: str | None = None,
    sector: str | None = None,
    run_type: str | None = None,
    index_name: str | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over the research library indexed by digisearch.

    Filters are AND-combined. Date range filters use ``date_ordinal`` (an
    integer ``YYYYMMDD`` stamped at ingest); pass e.g. ``date_from_ymd=20260420``
    for "on or after 2026-04-20". String filters (``doc_type``, ``segment``,
    ``sector``, ``run_type``) match exactly and case-sensitively against the
    metadata stamped by :func:`digisearch.research_ingest.ingest_research_payload`.

    Returns up to ``top_k`` typed result dicts:
    ``{chunk_id, doc_id, content, content_length, score, metadata}``. Empty
    list when nothing matches.
    """
    return _search_strategies_impl(
        query=query,
        top_k=top_k,
        date_from_ymd=date_from_ymd,
        date_to_ymd=date_to_ymd,
        doc_type=doc_type,
        segment=segment,
        sector=sector,
        run_type=run_type,
        index_name=index_name,
    )


try:
    import json as _json

    from digisearch.agent.pipeline import run_research_turn as _run_research_turn

    @mcp.tool()
    def digisearch_research_turn(
        user_message: str,
        index_name: str | None = None,
        top_k: int = 10,
        mode: str = "hybrid",
        workspace_id: str | None = None,
        source: str = "corpus",
        effort: str = "fast",
    ) -> str:
        """Composite research turn (plan → retrieve → aggregate) with citations for hub/trace parity.

        ``source`` defaults to ``corpus``; pass ``web`` or ``auto`` to run the
        OSS web branch (``effort``: fast | thorough).
        """
        payload = {
            "user_message": user_message,
            "index_name": index_name or DIGISEARCH_INDEX or "default",
            "top_k": top_k,
            "mode": mode,
            "workspace_id": workspace_id,
            "source": source,
            "effort": effort,
        }
        return _json.dumps(_run_research_turn(payload), indent=2)

except ImportError:
    logger.info("digisearch_research_turn MCP tool omitted (install digisearch[agent])")


@mcp.tool()
def digisearch_web_search(
    query: str,
    search_type: str = "auto",
    num_results: int = 8,
    category: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> str:
    """Live web search via EXA (alternative to the owned corpus).

    Dormant without EXA_API_KEY — returns a disabled message instead of failing.
    search_type: instant|fast|auto|deep-lite|deep|deep-reasoning.
    include_domains/exclude_domains restrict or drop hits by domain.
    """
    from digisearch import web_exa

    if not web_exa.is_exa_configured():
        return "EXA web search is disabled (EXA_API_KEY is not set)."
    if search_type not in web_exa.VALID_SEARCH_TYPES:
        return f"[digisearch web search error: invalid search_type: {search_type!r}]"
    try:
        data = web_exa.exa_search(
            query,
            search_type=search_type,  # type: ignore[arg-type]
            num_results=max(1, min(int(num_results), 100)),
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
    except (web_exa.ExaError, ValueError) as e:
        logger.error("digisearch web search failed: %s", e)
        return f"[digisearch web search error: {e}]"
    return web_exa.format_web_results(data)


# --- Phase C monitors (§4.7, #4065) -------------------------------------------------
#
# Four MCP tools over the same store/runner the HTTP routes use. Fail-closed
# shape of `digisearch_web_search`: without a reachable store the tools return a
# disabled message instead of raising. Create/update-time validation goes
# through `watch_config_error` — the same gate the HTTP API applies — because a
# watch with an unparseable cron would raise inside `is_due` at tick time, where
# `tick_due_watches` swallows the failure per watch and it would silently never
# run.

_MONITORS_DISABLED = "digisearch monitors are disabled (monitor store is unavailable)."


def _monitor_store_or_none() -> MonitorStore | None:
    """Open the monitor store, or fail closed with ``None`` when unreachable."""
    try:
        return get_store()
    except (OSError, sqlite3.Error) as e:
        logger.error("digisearch monitor store unavailable: %s", e)
        return None


@mcp.tool()
def monitors_create_watch(
    query: str,
    schedule_cron: str | None = None,
    interval_seconds: int | None = None,
    num_results: int = 8,
    category: str | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    delivery_mode: Literal["poll", "webhook", "fanout"] = "poll",
) -> str:
    """Create a scheduled web-search watch. Returns JSON {watch, delivery_secret}.

    The one-time ``delivery_secret`` (used to verify delivery HMACs) appears in
    this response only — never on list/read. Provide ``schedule_cron`` (5-field
    digiclaw grammar) or ``interval_seconds`` (>= 60); cron wins when both are
    given. The watch is named after the query. ``delivery_mode`` other than
    ``poll`` needs targets, which this surface cannot set, so those are rejected.
    """
    store = _monitor_store_or_none()
    if store is None:
        return _MONITORS_DISABLED
    text = query.strip()
    if not text:
        return "[monitors create error: query is required]"
    if not schedule_cron and interval_seconds is None:
        return "[monitors create error: schedule_cron or interval_seconds is required]"
    try:
        # Both WatchSchedule constructions stay inside this try: the interval
        # floor (ge=60) and the cron-required validator raise pydantic
        # ValidationError, which must flatten to the documented string, not escape.
        if schedule_cron:
            schedule = WatchSchedule(mode="cron", cron=schedule_cron)
        else:
            schedule = WatchSchedule(mode="interval", interval_seconds=interval_seconds)
        watch = Watch(
            name=text[:120],
            query=text,
            num_results=num_results,
            category=category,
            include_domains=include_domains or [],
            exclude_domains=exclude_domains or [],
            schedule=schedule,
            delivery=DeliveryConfig(mode=delivery_mode),
        )
    except ValidationError as e:
        return f"[monitors create error: {summarize_validation_error(e)}]"
    failure = watch_config_error(watch)
    if failure is not None:
        _, code, message = failure
        return f"[monitors create error: {code}: {message}]"
    created = store.create_watch(watch)
    secret = secrets.token_hex(32)
    store.set_delivery_secret(created.watch_id, secret)
    return json.dumps(
        {"watch": created.model_dump(mode="json"), "delivery_secret": secret}, indent=2
    )


@mcp.tool()
def monitors_list_watches() -> str:
    """List scheduled watches newest-updated first as JSON {"watches": [...]}."""
    store = _monitor_store_or_none()
    if store is None:
        return _MONITORS_DISABLED
    watches = store.list_watches()
    return json.dumps({"watches": [watch.model_dump(mode="json") for watch in watches]}, indent=2)


@mcp.tool()
def monitors_trigger_watch(watch_id: str, mode: Literal["manual", "poll"] = "manual") -> str:
    """Run one watch turn now and return its JSON MonitorRun.

    A failed turn is still persisted and returned with ``status="failed"``
    (mirrors ``POST /v1/monitors/{watch_id}/trigger``).
    """
    store = _monitor_store_or_none()
    if store is None:
        return _MONITORS_DISABLED
    try:
        from digisearch.monitors.runner import MonitorRunError, run_watch
    except ImportError as e:
        return f"[monitors unavailable: install digisearch[web-search] for monitors: {e}]"
    try:
        run = run_watch(watch_id, trigger=mode, store=store)
    except MonitorStoreError as e:
        return f"[monitors trigger error: {e.code}: {e}]"
    except MonitorRunError as e:
        run = store.get_run(watch_id, e.run_id)
    return json.dumps(run.model_dump(mode="json"), indent=2)


@mcp.tool()
def monitors_get_runs(watch_id: str, limit: int = 20) -> str:
    """List stored runs for one watch, newest first, as JSON {"runs", "next_cursor"}."""
    store = _monitor_store_or_none()
    if store is None:
        return _MONITORS_DISABLED
    try:
        runs, next_cursor = store.list_runs(watch_id, limit=limit)
    except MonitorStoreError as e:
        return f"[monitors runs error: {e.code}: {e}]"
    return json.dumps(
        {"runs": [run.model_dump(mode="json") for run in runs], "next_cursor": next_cursor},
        indent=2,
    )


def run_mcp(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int = 8765,
) -> None:
    """Run the MCP server. Default: streamable HTTP on 127.0.0.1:8765."""
    from digisearch.backend_require import require_real_search_backend

    require_real_search_backend()
    bind = host or os.environ.get("DIGISEARCH_MCP_HOST", "127.0.0.1")
    mcp.settings.host = bind
    mcp.settings.port = port
    mcp.run(transport=transport)
