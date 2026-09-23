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
    get_args,
)
from uuid import UUID

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
from digiquant.ops.checkpoint_archive import read_archived_document, read_archived_documents
from digiquant.research.decision_log import fetch_recent_lessons
from digiquant.research.supabase_io import SupabaseClient
from digiquant.supabase_retry import run_with_supabase_retry

logger = logging.getLogger(__name__)

# The valid retrieval/blinding phases. Validating against the ``RetrievalPhase``
# literal keeps an unknown phase from silently falling through unblinded.
_RETRIEVAL_PHASES = frozenset(get_args(RetrievalPhase))


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


def _hydrate_archived_row(
    client: SupabaseClient,
    row: dict[str, Any],
    *,
    store: Any | None,
) -> dict[str, Any]:
    """Read one NULL-payload row through the archive pointer (#3792).

    ``archive_documents`` NULLs the payload cell of non-latest versions; the
    row still resolves the version, so hydrate it from R2 instead of
    degrading the caller to missing. Pointer-miss keeps the row as-is.
    """
    if row.get("payload") is not None or not row.get("document_key") or not row.get("date"):
        return row
    payload = read_archived_document(
        client,
        store,
        workspace_id=str(house_workspace_id()),
        document_key=str(row["document_key"]),
        date_str=str(row["date"]),
    )
    if payload is None:
        return row
    return {**row, "payload": payload}


def _hydrate_archived_rows(
    client: SupabaseClient,
    rows: list[dict[str, Any]],
    *,
    store: Any | None,
) -> list[dict[str, Any]]:
    """Read a whole page of NULL-payload rows in ONE archive query (#4562).

    ``search_research`` returns up to 500 rows, and every NULL-payload row on
    the page used to cost its own ``archive_objects`` select -- ~1 s each in
    production, so a 7-version history walked sequentially. Collect the page's
    ``(document_key, date)`` pairs, resolve them in one round-trip, and merge
    the payloads back in. A row that does not resolve keeps its NULL payload,
    which is the same degradation as the single-row helper.
    """
    pending: list[tuple[str, str]] = []
    for row in rows:
        if row.get("payload") is not None or not row.get("document_key") or not row.get("date"):
            continue
        pending.append((str(row["document_key"]), str(row["date"])))
    if not pending:
        return rows
    payloads = read_archived_documents(
        client, store, workspace_id=str(house_workspace_id()), keys=pending
    )
    if not payloads:
        return rows
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("payload") is not None or not row.get("document_key") or not row.get("date"):
            out.append(row)
            continue
        payload = payloads.get((str(row["document_key"]), str(row["date"])))
        out.append({**row, "payload": payload} if payload is not None else row)
    return out


def _query_documents_row(
    client: SupabaseClient,
    *,
    document_key: str,
    as_of_date: date,
    store: Any | None = None,
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
        row = _hydrate_archived_row(client, exact_rows[0], store=store)
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
    row = _hydrate_archived_row(client, fallback_rows[0], store=store)
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
    store: Any | None = None,
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

    def _fetch_rows() -> tuple[Any | None, Any, str, Any | None]:
        if key == DIGEST_DOCUMENT_KEY:
            digest_row, digest_date = _query_digest_row(client, as_of_date=effective_as_of)
            digest_payload = digest_row.get("snapshot") if isinstance(digest_row, dict) else None
            return digest_row, digest_date, "daily_snapshots", digest_payload
        doc_row, doc_date = _query_documents_row(
            client,
            document_key=key,
            as_of_date=effective_as_of,
            store=store,
        )
        doc_payload = doc_row.get("payload") if isinstance(doc_row, dict) else None
        return doc_row, doc_date, "documents", doc_payload

    try:
        # Transient disconnects / PGRST002 / 502s retry 3× (#3299); anything
        # else still fails fast into the structured error below.
        row, resolved_date, source, payload = run_with_supabase_retry(
            _fetch_rows,
            operation=f"query_research {key}",
        )
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


_SEARCHABLE_DATASETS = frozenset(
    {
        "documents",
        "daily_snapshots",
        "theses",
        "thesis_vehicles",
        "positions",
        "nav_history",
        "portfolio_metrics",
        "position_events",
        "decision_log",
    }
)

_PORTFOLIO_DATASETS = frozenset(
    {
        "theses",
        "thesis_vehicles",
        "positions",
        "nav_history",
        "portfolio_metrics",
        "position_events",
        "decision_log",
    }
)

_HOUSE_SCOPED_DATASETS = frozenset(
    {"documents", "positions", "nav_history", "portfolio_metrics", "position_events"}
)

_SEARCH_COLUMNS: dict[str, str] = {
    "documents": (
        "date, document_key, title, doc_type, category, segment, sector, run_type, content, payload"
    ),
    "daily_snapshots": "date, snapshot",
    "theses": "date, thesis_id, name, vehicle, invalidation, status, notes",
    "thesis_vehicles": "date, thesis_id, ticker, source_exploration_key",
    "positions": "date, ticker, weight_pct, entry_date",
    "nav_history": "date, nav, cash_pct, invested_pct",
    "portfolio_metrics": "date, pnl_pct, sharpe, volatility, max_drawdown, alpha",
    "position_events": "date, ticker, event, book_source",
    "decision_log": "run_date, run_id, ticker, stance, status, alpha, reflection",
}

_SEARCH_DATE_COLUMN: dict[str, str] = {"decision_log": "run_date"}

_PREVIEW_CHARS = 500


def _document_keys_for_ticker(client: SupabaseClient, *, ticker: str) -> list[str]:
    """Resolve a ticker to candidate ``documents.document_key`` values.

    ``documents`` has no ticker column, so the ticker join runs through
    ``thesis_vehicles.source_exploration_key`` plus the conventional
    ``deep-dives/<TICKER>`` / ``custom-research/<TICKER>`` keys.
    """
    keys: set[str] = {ticker, f"deep-dives/{ticker}", f"custom-research/{ticker}"}
    try:
        resp = (
            client.table("thesis_vehicles")
            .select("source_exploration_key")
            .eq("ticker", ticker)
            .limit(200)
            .execute()
        )
    except Exception as exc:  # ticker join is best-effort, never fatal
        logger.warning("search_research ticker join failed for %s: %s", ticker, exc)
        return sorted(keys)
    for row in getattr(resp, "data", None) or []:
        source = row.get("source_exploration_key")
        if source:
            keys.add(str(source))
    return sorted(keys)


def _search_table(
    client: SupabaseClient,
    *,
    table: str,
    columns: str,
    date_column: str,
    date_from: date | None,
    date_to: date | None,
    eq_filters: dict[str, str],
    in_filters: dict[str, list[str]],
    or_filter: str | None,
    limit: int,
    offset: int,
    house_scoped: bool,
) -> list[dict[str, Any]]:
    """One bounded, ordered, paginated read against a typed dataset table."""

    def _run() -> list[dict[str, Any]]:
        query = client.table(table).select(columns)
        if house_scoped:
            query = _eq_house(query)
        if date_from is not None:
            query = query.gte(date_column, date_from.isoformat())
        if date_to is not None:
            query = query.lte(date_column, date_to.isoformat())
        for column, value in eq_filters.items():
            query = query.eq(column, value)
        for column, values in in_filters.items():
            query = query.in_(column, values)
        if or_filter:
            query = query.or_(or_filter)
        query = query.order(date_column, desc=True)
        query = query.range(offset, offset + limit - 1)
        resp = query.execute()
        return list(getattr(resp, "data", None) or [])

    return run_with_supabase_retry(_run, operation=f"search_research {table}")


def _preview_row(row: dict[str, Any]) -> dict[str, Any]:
    """Bound large text bodies unless the caller asked for full content."""
    out = dict(row)
    content = out.get("content")
    if isinstance(content, str) and len(content) > _PREVIEW_CHARS:
        out["content"] = content[:_PREVIEW_CHARS]
        out["content_truncated"] = True
    return out


def _postprocess_search_rows(
    client: SupabaseClient,
    rows: list[dict[str, Any]],
    *,
    dataset: str,
    retrieval_phase: RetrievalPhase,
    full_content: bool,
    store: Any | None,
) -> list[dict[str, Any]]:
    """Apply phase blinding, R2 payload read-through, and preview truncation."""
    out: list[dict[str, Any]] = []
    for row in rows:
        if dataset == "documents":
            key = str(row.get("document_key") or "")
            if not research_document_allowed(retrieval_phase, key):
                continue
        elif dataset == "daily_snapshots":
            # The snapshot IS the digest payload, so the same phase gate that
            # blinds ``documents/digest`` must apply here too.
            if not research_document_allowed(retrieval_phase, DIGEST_DOCUMENT_KEY):
                continue
        out.append(row)
    if dataset == "documents":
        # Blinded keys are dropped above, so only visible rows are ever fetched.
        out = _hydrate_archived_rows(client, out, store=store)
    if dataset in {"documents", "daily_snapshots"} and not full_content:
        out = [_preview_row(row) for row in out]
    return out


def search_research(
    client: SupabaseClient,
    *,
    run_date: date,
    dataset: str = "documents",
    run_type: str | None = "baseline",
    run_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    document_key: str | None = None,
    segment: str | None = None,
    ticker: str | None = None,
    sector: str | None = None,
    subject: str | None = None,
    doc_type: str | None = None,
    include_prior: bool = False,
    as_of_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
    full_content: bool = False,
    retrieval_phase: RetrievalPhase = "research_edit",
    retrieval_pin: RetrievalQueryPin | None = None,
    store: Any | None = None,
) -> dict[str, Any]:
    """Filterable research/portfolio reader over the typed dataset surfaces.

    Storage routing is transparent: live rows come from Supabase, and archived
    older ``documents.payload`` cells are hydrated through the R2 pointer
    (``_hydrate_archived_row``). Market history is served by the dedicated
    price/macro tools, never here. No raw table or column name is accepted, so
    the generic PostgREST surface that ``query_data`` exposed is gone.
    """
    if dataset not in _SEARCHABLE_DATASETS:
        return {"error": f"search_research unknown dataset {dataset!r}"}

    if retrieval_phase not in _RETRIEVAL_PHASES:
        return {"error": f"search_research unknown retrieval phase {retrieval_phase!r}"}

    capped_limit = max(1, min(int(limit), 500))
    safe_offset = max(0, int(offset))

    if dataset in _PORTFOLIO_DATASETS and not portfolio_tool_allowed(retrieval_phase):
        return {"error": "search_research portfolio datasets are not available in this phase"}

    # ``run_date`` is the hard ceiling. A caller-supplied ``as_of_date`` can only
    # narrow the window (replay an earlier point in time); it can never push the
    # upper bound past the run's logical date and read future research.
    anchor = run_date
    if as_of_date is not None and as_of_date < anchor:
        anchor = as_of_date
    upper = date_to or anchor
    if upper > anchor:  # never read ahead of the run's logical date
        upper = anchor
    if date_from is not None:
        lower: date | None = date_from
    elif include_prior:
        lower = None
    else:
        lower = upper

    key = _resolve_document_key(document_key=document_key, segment=segment)

    eq_filters: dict[str, str] = {}
    in_filters: dict[str, list[str]] = {}
    or_filter: str | None = None
    empty_intersection = False

    if dataset == "documents":
        if run_type:
            eq_filters["run_type"] = run_type
        if sector:
            eq_filters["sector"] = sector
        if doc_type:
            eq_filters["doc_type"] = doc_type
        if ticker:
            ticker_keys = _document_keys_for_ticker(client, ticker=ticker)
            if key:
                # ``document_key`` and ``ticker`` both name the ``document_key``
                # column, so an explicit key intersects the ticker-derived set
                # instead of ANDing a contradictory eq() with in_().
                ticker_keys = [candidate for candidate in ticker_keys if candidate == key]
                in_filters["document_key"] = ticker_keys
                if not ticker_keys:
                    empty_intersection = True
            else:
                in_filters["document_key"] = ticker_keys
        elif key:
            eq_filters["document_key"] = key
        if subject:
            token = subject.replace("%", "").replace(",", " ").strip()
            or_filter = f"title.like.%{token}%,category.like.%{token}%,document_key.like.%{token}%"
    elif dataset == "thesis_vehicles":
        if ticker:
            eq_filters["ticker"] = ticker
    elif dataset in {"positions", "position_events", "decision_log"}:
        if ticker:
            eq_filters["ticker"] = ticker
        if dataset == "decision_log" and run_id:
            eq_filters["run_id"] = run_id

    pin_error: str | None = None
    if dataset == "documents" and key:
        pin_error = _pin_rejects_document_access(
            retrieval_pin, document_key=key, as_of_date=as_of_date
        )
    else:
        pin_error = _pin_rejects_latest_fallback(retrieval_pin, as_of_date)
    if (
        pin_error is not None
        and retrieval_pin is not None
        and retrieval_pin.mode is RetrievalManifestMode.ENFORCE
    ):
        return apply_retrieval_pin_to_result(
            {"error": pin_error}, pin=retrieval_pin, pin_error=pin_error
        )

    if empty_intersection:
        # ``document_key`` and ``ticker`` filtered to no common row: return a
        # clean zero-row result instead of a contradictory eq()+in_() query.
        return apply_retrieval_pin_to_result(
            {
                "dataset": dataset,
                "run_type": run_type if dataset == "documents" else None,
                "date_from": lower.isoformat() if lower is not None else None,
                "date_to": upper.isoformat(),
                "include_prior": include_prior,
                "row_count": 0,
                "limit": capped_limit,
                "offset": safe_offset,
                "rows": [],
            },
            pin=retrieval_pin,
            pin_error=pin_error,
        )

    date_column = _SEARCH_DATE_COLUMN.get(dataset, "date")
    try:
        rows = _search_table(
            client,
            table=dataset,
            columns=_SEARCH_COLUMNS[dataset],
            date_column=date_column,
            date_from=lower,
            date_to=upper,
            eq_filters=eq_filters,
            in_filters=in_filters,
            or_filter=or_filter,
            limit=capped_limit,
            offset=safe_offset,
            house_scoped=dataset in _HOUSE_SCOPED_DATASETS,
        )
    except Exception as exc:  # return structured error to tool caller
        logger.warning("search_research failed for %s: %s", dataset, exc)
        return {"error": f"search_research failed: {exc}"}

    rows = _postprocess_search_rows(
        client,
        rows,
        dataset=dataset,
        retrieval_phase=retrieval_phase,
        full_content=full_content,
        store=store,
    )

    result = {
        "dataset": dataset,
        "run_type": run_type if dataset == "documents" else None,
        "date_from": lower.isoformat() if lower is not None else None,
        "date_to": upper.isoformat(),
        "include_prior": include_prior,
        "row_count": len(rows),
        "limit": capped_limit,
        "offset": safe_offset,
        "rows": rows,
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

    def _fetch_book() -> tuple[Any, Any, Any, Any, Any]:
        book_positions, book_resolved = _positions_for_as_of(
            client,
            as_of_date=effective_as_of,
            ticker=ticker,
        )
        book_nav = _nav_for_as_of(client, as_of_date=effective_as_of)
        book_theses = _theses_for_as_of(client, as_of_date=effective_as_of)
        book_lessons = fetch_recent_lessons(
            client=client,
            run_date=effective_as_of,
            watchlist=watchlist,
        )
        return book_positions, book_resolved, book_nav, book_theses, book_lessons

    try:
        # Same transient retry as query_research (#3299).
        positions, resolved_date, nav, theses, lessons = run_with_supabase_retry(
            _fetch_book,
            operation="query_portfolio",
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
