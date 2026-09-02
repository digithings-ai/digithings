"""Supabase-backed research and portfolio retrieval (spec §6.1).

WP14.4 binds drill-down tools to compiled :class:`ContextManifest` rows — document
access resolves through manifest legacy refs; enforce mode rejects un-pinned calls
and latest-date fallbacks.

Group A book reads (`positions`, `nav_history`, `portfolio_metrics`) are
house-scoped so an overlay same-calendar row cannot leak into dashboard pages.
House document lookups (`query_research` / `_query_documents_row`) likewise
default to the house ``workspace_id``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)
from uuid import UUID

from digiquant.research.decision_log import fetch_recent_lessons
from digiquant.research.supabase_io import SupabaseClient
from digiquant.dashboard.research_retrieval.blinding import (
    DIGEST_DOCUMENT_KEY,
    RetrievalPhase,
    portfolio_tool_allowed,
    research_document_allowed,
)
from digiquant.dashboard.research_retrieval.cache import ResearchCache, _parse_row_date
from digiquant.dashboard.research_retrieval.context import ContextItemKind, ContextManifest
from digiquant.dashboard.research_retrieval.store import LoadedResearchState
from digiquant.dashboard.tenancy import house_workspace_id

logger = logging.getLogger(__name__)


class RetrievalManifestMode(StrEnum):
    """Rollout knob for manifest-pinned drill-down retrieval (off|shadow|enforce)."""

    OFF = "off"
    SHADOW = "shadow"
    ENFORCE = "enforce"


@dataclass(frozen=True)
class RetrievalDocumentAllowlist:
    """Exact document_key + as_of_date pairs permitted by one context manifest."""

    entries: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class RetrievalQueryPin:
    """Bind one provider attempt's drill-down tools to an exact context manifest."""

    manifest: ContextManifest
    allowlist: RetrievalDocumentAllowlist
    mode: RetrievalManifestMode


def build_retrieval_query_pin(
    *,
    manifest: ContextManifest,
    state: LoadedResearchState,
    mode: RetrievalManifestMode,
) -> RetrievalQueryPin:
    """Derive drill-down allowlist from the pinned state version's legacy refs."""
    if manifest.state_version_id != state.version.state_version_id:
        raise ValueError("manifest.state_version_id must match loaded research state")
    allowed: set[tuple[str, str]] = set()
    legacy_by_id = {ref.legacy_ref_id: ref for ref in state.legacy_refs}
    manifest_legacy_ids = frozenset(state.version.manifest.legacy_ref_ids)

    prefix = f"{ContextItemKind.LEGACY_REF.value}:"
    for entity_ref in manifest.included_entity_ids:
        if not entity_ref.startswith(prefix):
            continue
        raw_id = entity_ref[len(prefix) :]
        try:
            ref_id = UUID(raw_id)
        except ValueError:
            continue
        legacy = legacy_by_id.get(ref_id)
        if legacy is not None:
            allowed.add((legacy.document_key, legacy.as_of_date))

    for ref_id in manifest_legacy_ids:
        legacy = legacy_by_id.get(ref_id)
        if legacy is not None:
            allowed.add((legacy.document_key, legacy.as_of_date))

    return RetrievalQueryPin(
        manifest=manifest,
        allowlist=RetrievalDocumentAllowlist(entries=frozenset(allowed)),
        mode=mode,
    )


def _pin_rejects_latest_fallback(
    pin: RetrievalQueryPin | None, as_of_date: date | None
) -> str | None:
    if pin is None or pin.mode is RetrievalManifestMode.OFF:
        return None
    if as_of_date is None:
        return "as_of_date required when retrieval manifest is pinned (no latest fallback)"
    return None


def _pin_rejects_document_access(
    pin: RetrievalQueryPin | None,
    *,
    document_key: str,
    as_of_date: date | None,
) -> str | None:
    if pin is None or pin.mode is RetrievalManifestMode.OFF:
        return None
    latest_err = _pin_rejects_latest_fallback(pin, as_of_date)
    if latest_err is not None:
        return latest_err
    assert as_of_date is not None
    key = (document_key, as_of_date.isoformat())
    if key not in pin.allowlist.entries:
        return (
            f"document {document_key!r} as of {as_of_date.isoformat()} "
            "not permitted by context manifest"
        )
    return None


def apply_retrieval_pin_to_result(
    result: dict[str, Any],
    *,
    pin: RetrievalQueryPin | None,
    pin_error: str | None,
) -> dict[str, Any]:
    """Attach manifest linkage telemetry without mutating the stored manifest."""
    if pin is None:
        return result
    out = dict(result)
    out["context_manifest_id"] = str(pin.manifest.manifest_id)
    out["context_state_version_id"] = str(pin.manifest.state_version_id)
    out["context_manifest_content_hash"] = pin.manifest.content_hash
    out["context_manifest_estimated_tokens"] = pin.manifest.estimated_tokens
    if pin_error is not None and pin.mode is RetrievalManifestMode.SHADOW:
        out["retrieval_pin_shadow"] = pin_error
    return out


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
    exact_resp = _eq_house(
        client.table("documents")
        .select("date, document_key, payload, doc_type")
        .eq("document_key", document_key)
        .eq("date", as_of_date.isoformat())
        .limit(1)
    ).execute()
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        row = exact_rows[0]
        row_date = _parse_row_date(row.get("date"))
        return row, row_date

    fallback_resp = _eq_house(
        client.table("documents")
        .select("date, document_key, payload, doc_type")
        .eq("document_key", document_key)
        .lt("date", as_of_date.isoformat())
        .order("date", desc=True)
        .limit(1)
    ).execute()
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


def _eq_house(query: Any) -> Any:
    """dashboard pages / research tools read the house book, never overlay same-date rows."""
    return query.eq("workspace_id", str(house_workspace_id()))


def _positions_for_as_of(
    client: SupabaseClient,
    *,
    as_of_date: date,
    ticker: str | None = None,
) -> tuple[list[dict[str, Any]], date | None]:
    exact_resp = _eq_house(
        client.table("positions")
        .select("date, ticker, weight_pct, entry_date")
        .eq("date", as_of_date.isoformat())
    ).execute()
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        rows = exact_rows
        resolved = as_of_date
    else:
        fallback_resp = _eq_house(
            client.table("positions")
            .select("date, ticker, weight_pct, entry_date")
            .lt("date", as_of_date.isoformat())
            .order("date", desc=True)
            .limit(200)
        ).execute()
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
    exact_resp = _eq_house(
        client.table("nav_history")
        .select("date, nav, cash_pct, invested_pct")
        .eq("date", as_of_date.isoformat())
        .limit(1)
    ).execute()
    exact_rows = list(getattr(exact_resp, "data", None) or [])
    if exact_rows:
        nav_row = exact_rows[0]
        nav_date = str(nav_row.get("date") or as_of_date.isoformat())
    else:
        fallback_resp = _eq_house(
            client.table("nav_history")
            .select("date, nav, cash_pct, invested_pct")
            .lt("date", as_of_date.isoformat())
            .order("date", desc=True)
            .limit(1)
        ).execute()
        fallback_rows = list(getattr(fallback_resp, "data", None) or [])
        if not fallback_rows:
            return {}
        nav_row = fallback_rows[0]
        nav_date = str(nav_row.get("date") or "")

    metrics_resp = _eq_house(
        client.table("portfolio_metrics")
        .select("date, pnl_pct, sharpe, volatility, max_drawdown, alpha")
        .eq("date", nav_date)
        .limit(1)
    ).execute()
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
    phase: RetrievalPhase = "research_edit",
    cache: ResearchCache | None = None,
    retrieval_pin: RetrievalQueryPin | None = None,
) -> dict[str, Any]:
    """Fetch a research document or digest row with prior_published date semantics."""
    key = _resolve_document_key(document_key=document_key, segment=segment)
    if not key:
        return {"error": "query_research requires document_key or segment"}

    if not research_document_allowed(phase, key):
        return {
            "error": (f"query_research document_key {key!r} is not available in phase {phase!r}")
        }

    pin_error = _pin_rejects_document_access(
        retrieval_pin,
        document_key=key,
        as_of_date=as_of_date,
    )
    if pin_error is not None:
        if retrieval_pin is not None and retrieval_pin.mode is RetrievalManifestMode.ENFORCE:
            return apply_retrieval_pin_to_result(
                {"error": pin_error}, pin=retrieval_pin, pin_error=pin_error
            )

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
                cached_result = {
                    "document_key": key,
                    "requested_as_of_date": requested_as_of,
                    "as_of_date": str(cached_row.get("date") or "")[:10],
                    "source": "daily_snapshots" if key == DIGEST_DOCUMENT_KEY else "documents",
                    "payload": payload,
                    "cache_hit": True,
                }
                return apply_retrieval_pin_to_result(
                    cached_result,
                    pin=retrieval_pin,
                    pin_error=pin_error,
                )

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
    except Exception as exc:  # return structured error to tool caller
        logger.warning("query_research failed for %s: %s", key, exc)
        return {"error": f"query_research failed: {exc}"}

    if row is None or resolved_date is None or not isinstance(payload, dict):
        err = {"error": f"no research row found for {key!r} as of {effective_as_of.isoformat()}"}
        return apply_retrieval_pin_to_result(err, pin=retrieval_pin, pin_error=pin_error)

    result = {
        "document_key": key,
        "requested_as_of_date": requested_as_of,
        "as_of_date": resolved_date.isoformat(),
        "source": source,
        "payload": payload,
        "cache_hit": False,
    }
    return apply_retrieval_pin_to_result(result, pin=retrieval_pin, pin_error=pin_error)


def query_portfolio(
    client: SupabaseClient,
    *,
    run_date: date,
    phase: RetrievalPhase,
    as_of_date: date | None = None,
    ticker: str | None = None,
    watchlist: tuple[str, ...] = (),
    retrieval_pin: RetrievalQueryPin | None = None,
) -> dict[str, Any]:
    """Fetch portfolio book, NAV, theses, and decision lessons for *phase*."""
    if not portfolio_tool_allowed(phase):
        return {"error": "query_portfolio is not available in this phase (portfolio blinding)"}

    pin_error = _pin_rejects_latest_fallback(retrieval_pin, as_of_date)
    if pin_error is not None:
        if retrieval_pin is not None and retrieval_pin.mode is RetrievalManifestMode.ENFORCE:
            return apply_retrieval_pin_to_result(
                {"error": pin_error}, pin=retrieval_pin, pin_error=pin_error
            )

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
    except Exception as exc:  # return structured error to tool caller
        logger.warning("query_portfolio failed: %s", exc)
        return {"error": f"query_portfolio failed: {exc}"}

    as_of_str = (resolved_date or effective_as_of).isoformat()
    result = {
        "as_of_date": as_of_str,
        "positions": positions,
        "nav": nav,
        "theses": theses,
        "decision_lessons": lessons,
    }
    return apply_retrieval_pin_to_result(result, pin=retrieval_pin, pin_error=pin_error)


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
