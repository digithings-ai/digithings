"""Supabase-backed research and portfolio retrieval (spec §6.1)."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.decision_log import fetch_recent_lessons
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.research_retrieval.blinding import (
    DIGEST_DOCUMENT_KEY,
    RetrievalPhase,
    portfolio_tool_allowed,
    research_document_allowed,
)
from digiquant.olympus.research_retrieval.cache import ResearchCache, _parse_row_date

logger = logging.getLogger(__name__)


def _resolve_document_key(
    *,
    document_key: str | None,
    segment: str | None,
) -> str | None:
    if document_key:
        return document_key.strip()
    if segment:
        return segment.strip()
    return None


def _query_documents_row(
    client: SupabaseClient,
    *,
    document_key: str,
    as_of_date: date,
) -> tuple[dict[str, Any] | None, date | None]:
    exact_resp = (
        client.table("documents")
        .select("date, document_key, payload, doc_type")
        .eq("document_key", document_key)
        .eq("date", as_of_date.isoformat())
        .limit(1)
        .execute()
    )
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        row = exact_rows[0]
        row_date = _parse_row_date(row.get("date"))
        return row, row_date

    fallback_resp = (
        client.table("documents")
        .select("date, document_key, payload, doc_type")
        .eq("document_key", document_key)
        .lt("date", as_of_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    fallback_rows = list(getattr(fallback_resp, "data", None) or [])
    if not fallback_rows:
        return None, None
    row = fallback_rows[0]
    return row, _parse_row_date(row.get("date"))


def _query_digest_row(
    client: SupabaseClient,
    *,
    as_of_date: date,
) -> tuple[dict[str, Any] | None, date | None]:
    exact_resp = (
        client.table("daily_snapshots")
        .select("date, snapshot")
        .eq("date", as_of_date.isoformat())
        .limit(1)
        .execute()
    )
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        row = exact_rows[0]
        return row, _parse_row_date(row.get("date"))

    fallback_resp = (
        client.table("daily_snapshots")
        .select("date, snapshot")
        .lt("date", as_of_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    fallback_rows = list(getattr(fallback_resp, "data", None) or [])
    if not fallback_rows:
        return None, None
    row = fallback_rows[0]
    return row, _parse_row_date(row.get("date"))


def _positions_for_as_of(
    client: SupabaseClient,
    *,
    as_of_date: date,
    ticker: str | None = None,
) -> tuple[list[dict[str, Any]], date | None]:
    exact_resp = (
        client.table("positions")
        .select("date, ticker, weight_pct, entry_date")
        .eq("date", as_of_date.isoformat())
        .execute()
    )
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        rows = exact_rows
        resolved = as_of_date
    else:
        fallback_resp = (
            client.table("positions")
            .select("date, ticker, weight_pct, entry_date")
            .lt("date", as_of_date.isoformat())
            .order("date", desc=True)
            .limit(200)
            .execute()
        )
        fallback_rows = list(getattr(fallback_resp, "data", None) or [])
        if not fallback_rows:
            return [], None
        fallback_rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
        top_date = str(fallback_rows[0].get("date") or "")
        rows = [row for row in fallback_rows if str(row.get("date") or "") == top_date]
        resolved = _parse_row_date(top_date)

    if ticker:
        rows = [row for row in rows if str(row.get("ticker") or "") == ticker]
    return rows, resolved


def _nav_for_as_of(client: SupabaseClient, *, as_of_date: date) -> dict[str, Any]:
    exact_resp = (
        client.table("nav_history")
        .select("date, nav, cash_pct, invested_pct")
        .eq("date", as_of_date.isoformat())
        .limit(1)
        .execute()
    )
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        nav_row = exact_rows[0]
        nav_date = str(nav_row.get("date") or as_of_date.isoformat())
    else:
        fallback_resp = (
            client.table("nav_history")
            .select("date, nav, cash_pct, invested_pct")
            .lt("date", as_of_date.isoformat())
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        fallback_rows = list(getattr(fallback_resp, "data", None) or [])
        if not fallback_rows:
            return {}
        nav_row = fallback_rows[0]
        nav_date = str(nav_row.get("date") or "")

    metrics_resp = (
        client.table("portfolio_metrics")
        .select("date, pnl_pct, sharpe, volatility, max_drawdown, alpha")
        .eq("date", nav_date)
        .limit(1)
        .execute()
    )
    metrics_rows = list(getattr(metrics_resp, "data", None) or [])
    snapshot: dict[str, Any] = {
        "date": nav_date,
        "nav": nav_row.get("nav"),
        "cash_pct": nav_row.get("cash_pct"),
        "invested_pct": nav_row.get("invested_pct"),
    }
    if metrics_rows:
        snapshot["metrics"] = metrics_rows[0]
    return snapshot


def _theses_for_as_of(client: SupabaseClient, *, as_of_date: date) -> list[dict[str, Any]]:
    resp = (
        client.table("theses")
        .select("date, thesis_id, name, vehicle, invalidation, status, notes")
        .lte("date", as_of_date.isoformat())
        .order("date", desc=True)
        .limit(100)
        .execute()
    )
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return []
    rows.sort(key=lambda row: str(row.get("date") or ""), reverse=True)
    top_date = str(rows[0].get("date") or "")
    terminal = {"CLOSED", "INVALIDATED"}
    return [
        row
        for row in rows
        if str(row.get("date") or "") == top_date
        and str(row.get("status") or "ACTIVE").upper() not in terminal
    ]


def query_research(
    client: SupabaseClient,
    *,
    run_date: date,
    document_key: str | None = None,
    as_of_date: date | None = None,
    segment: str | None = None,
    phase: RetrievalPhase = "atlas_edit",
    cache: ResearchCache | None = None,
) -> dict[str, Any]:
    """Fetch a research document or digest row with prior_published date semantics."""
    key = _resolve_document_key(document_key=document_key, segment=segment)
    if not key:
        return {"error": "query_research requires document_key or segment"}

    if not research_document_allowed(phase, key):
        return {
            "error": (f"query_research document_key {key!r} is not available in phase {phase!r}")
        }

    effective_as_of = as_of_date or run_date
    requested_as_of = as_of_date.isoformat() if as_of_date is not None else None

    if cache is not None:
        cached_row = (
            cache.get_digest(as_of_date=effective_as_of, run_date=run_date)
            if key == DIGEST_DOCUMENT_KEY
            else cache.get_document(key, as_of_date=effective_as_of, run_date=run_date)
        )
        if cached_row is not None:
            payload = (
                cached_row.get("snapshot")
                if key == DIGEST_DOCUMENT_KEY
                else cached_row.get("payload")
            )
            if isinstance(payload, dict):
                return {
                    "document_key": key,
                    "requested_as_of_date": requested_as_of,
                    "as_of_date": str(cached_row.get("date") or "")[:10],
                    "source": "daily_snapshots" if key == DIGEST_DOCUMENT_KEY else "documents",
                    "payload": payload,
                    "cache_hit": True,
                }

    try:
        if key == DIGEST_DOCUMENT_KEY:
            row, resolved_date = _query_digest_row(client, as_of_date=effective_as_of)
            source = "daily_snapshots"
            payload = row.get("snapshot") if isinstance(row, dict) else None
        else:
            row, resolved_date = _query_documents_row(
                client,
                document_key=key,
                as_of_date=effective_as_of,
            )
            source = "documents"
            payload = row.get("payload") if isinstance(row, dict) else None
    except Exception as exc:  # noqa: BLE001 — return structured error to tool caller
        logger.warning("query_research failed for %s: %s", key, exc)
        return {"error": f"query_research failed: {exc}"}

    if row is None or resolved_date is None or not isinstance(payload, dict):
        return {"error": f"no research row found for {key!r} as of {effective_as_of.isoformat()}"}

    return {
        "document_key": key,
        "requested_as_of_date": requested_as_of,
        "as_of_date": resolved_date.isoformat(),
        "source": source,
        "payload": payload,
        "cache_hit": False,
    }


def query_portfolio(
    client: SupabaseClient,
    *,
    run_date: date,
    phase: RetrievalPhase,
    as_of_date: date | None = None,
    ticker: str | None = None,
    watchlist: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Fetch portfolio book, NAV, theses, and decision lessons for *phase*."""
    if not portfolio_tool_allowed(phase):
        return {"error": "query_portfolio is not available in this phase (portfolio blinding)"}

    effective_as_of = as_of_date or run_date
    try:
        positions, resolved_date = _positions_for_as_of(
            client,
            as_of_date=effective_as_of,
            ticker=ticker,
        )
        nav = _nav_for_as_of(client, as_of_date=effective_as_of)
        theses = _theses_for_as_of(client, as_of_date=effective_as_of)
        lessons = fetch_recent_lessons(
            client=client,
            run_date=effective_as_of,
            watchlist=watchlist,
        )
    except Exception as exc:  # noqa: BLE001 — return structured error to tool caller
        logger.warning("query_portfolio failed: %s", exc)
        return {"error": f"query_portfolio failed: {exc}"}

    as_of_str = (resolved_date or effective_as_of).isoformat()
    return {
        "as_of_date": as_of_str,
        "positions": positions,
        "nav": nav,
        "theses": theses,
        "decision_lessons": lessons,
    }


def extract_section(body: dict[str, Any], section_path: str | None) -> dict[str, Any]:
    """Navigate *section_path* (JSON Pointer-style) within *body*."""
    if section_path is None:
        return body
    cur: Any = body
    for token in section_path.strip("/").split("/"):
        if not token:
            continue
        if isinstance(cur, dict):
            cur = cur.get(token, {})
        else:
            return {}
    return cur if isinstance(cur, dict) else {"value": cur}
