"""Supabase writers for thesis-first Hermes phases."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.thesis import (
    MarketThesisExplorationOutput,
    ThesisReviewOutput,
    ThesisStatusUpdate,
    ThesisVehicleMapOutput,
)

logger = logging.getLogger(__name__)

_VALID_THESIS_STATUSES = frozenset(
    {"ACTIVE", "MONITORING", "CHALLENGED", "CLOSED", "INVALIDATED", "PAUSED", "NEW"}
)


def normalize_thesis_status(raw: str | None) -> str:
    """Map free-text / legacy status onto ``chk_theses_status`` tokens."""
    if not raw:
        return "ACTIVE"
    token = str(raw).strip().upper().replace("-", "_")
    aliases = {
        "CONFIRMED": "ACTIVE",
        "CLOSED_WIN": "CLOSED",
        "CLOSED_LOSS": "CLOSED",
        "EXPIRED": "INVALIDATED",
    }
    token = aliases.get(token, token)
    if token not in _VALID_THESIS_STATUSES:
        return "ACTIVE"
    return token


def apply_invalidation_hits(
    active_theses: list[dict[str, Any]],
    hits: dict[str, list[str]],
) -> list[ThesisStatusUpdate]:
    """Emit ``CHALLENGED`` updates for theses whose invalidation criteria fired."""
    updates: list[ThesisStatusUpdate] = []
    for row in active_theses:
        thesis_id = str(row.get("thesis_id") or "").strip()
        if not thesis_id or thesis_id not in hits:
            continue
        triggered = [str(c).strip() for c in hits[thesis_id] if str(c).strip()]
        if not triggered:
            continue
        prior = normalize_thesis_status(row.get("status"))
        updates.append(
            ThesisStatusUpdate(
                thesis_id=thesis_id,
                prior_status=prior,  # type: ignore[arg-type]
                new_status="CHALLENGED",
                evidence=[f"invalidation criteria hit: {t}" for t in triggered],
                challenged_by=triggered,
            )
        )
    return updates


def merge_review_with_invalidation_hits(
    review: ThesisReviewOutput,
    active_theses: list[dict[str, Any]],
    hits: dict[str, list[str]],
) -> ThesisReviewOutput:
    """Overlay deterministic invalidation hits onto an LLM review (hits win)."""
    forced = apply_invalidation_hits(active_theses, hits)
    by_id = {u.thesis_id: u for u in review.reviewed_theses}
    for update in forced:
        by_id[update.thesis_id] = update
    return review.model_copy(update={"reviewed_theses": list(by_id.values())})


def upsert_thesis_row(
    client: SupabaseClient,
    *,
    run_date: date,
    thesis_id: str,
    name: str,
    status: str,
    vehicle: str | None = None,
    invalidation: str | None = None,
    notes: str | None = None,
    confidence: float | None = None,
    validation_criteria: list[str] | None = None,
    invalidation_criteria: list[str] | None = None,
    horizon: str | None = None,
    thesis_kind: str | None = None,
    linked_market_thesis_id: str | None = None,
) -> None:
    """Upsert one ``theses`` row for ``(date, thesis_id)``."""
    row: dict[str, Any] = {
        "date": run_date.isoformat(),
        "thesis_id": thesis_id,
        "name": name,
        "status": normalize_thesis_status(status),
    }
    if vehicle is not None:
        row["vehicle"] = vehicle
    if invalidation is not None:
        row["invalidation"] = invalidation
    if notes is not None:
        row["notes"] = notes
    if confidence is not None:
        row["confidence"] = confidence
    if validation_criteria is not None:
        row["validation_criteria"] = validation_criteria
    if invalidation_criteria is not None:
        row["invalidation_criteria"] = invalidation_criteria
    if horizon is not None:
        row["horizon"] = horizon
    if thesis_kind is not None:
        row["thesis_kind"] = thesis_kind
    if linked_market_thesis_id is not None:
        row["linked_market_thesis_id"] = linked_market_thesis_id
    client.table("theses").upsert(row, on_conflict="date,thesis_id").execute()


def upsert_thesis_vehicles(
    client: SupabaseClient,
    *,
    run_date: date,
    thesis_id: str,
    tickers: list[str],
    rationale: str = "",
    source_exploration_key: str | None = None,
) -> int:
    """Upsert ``thesis_vehicles`` rows for one thesis mapping."""
    written = 0
    for rank, ticker in enumerate(tickers, start=1):
        row: dict[str, Any] = {
            "date": run_date.isoformat(),
            "thesis_id": thesis_id,
            "ticker": ticker,
            "rationale": rationale,
            "candidate_rank": rank,
        }
        if source_exploration_key:
            row["source_exploration_key"] = source_exploration_key
        try:
            client.table("thesis_vehicles").upsert(
                row, on_conflict="date,thesis_id,ticker"
            ).execute()
            written += 1
        except Exception as exc:  # noqa: BLE001 — enrichment must not block graph
            logger.warning("thesis_vehicles upsert failed for %s/%s (%s)", thesis_id, ticker, exc)
    return written


def persist_thesis_review(
    client: SupabaseClient,
    *,
    run_date: date,
    review: ThesisReviewOutput,
    active_theses: list[dict[str, Any]],
) -> int:
    """Write status updates from H1 onto ``theses`` rows."""
    prior_by_id = {str(r.get("thesis_id")): r for r in active_theses}
    count = 0
    for update in review.reviewed_theses:
        prior_row = prior_by_id.get(update.thesis_id, {})
        name = str(prior_row.get("name") or update.thesis_id)
        invalidation = str(prior_row.get("invalidation") or "")
        notes = "; ".join(update.evidence) if update.evidence else str(prior_row.get("notes") or "")
        upsert_thesis_row(
            client,
            run_date=run_date,
            thesis_id=update.thesis_id,
            name=name,
            status=update.new_status,
            vehicle=prior_row.get("vehicle"),
            invalidation=invalidation or None,
            notes=notes or None,
            confidence=prior_row.get("confidence"),
            validation_criteria=prior_row.get("validation_criteria"),
            invalidation_criteria=prior_row.get("invalidation_criteria"),
            horizon=prior_row.get("horizon"),
            thesis_kind=prior_row.get("thesis_kind"),
            linked_market_thesis_id=prior_row.get("linked_market_thesis_id"),
        )
        count += 1
    return count


def persist_market_thesis_exploration(
    client: SupabaseClient,
    *,
    run_date: date,
    exploration: MarketThesisExplorationOutput,
) -> int:
    """Insert/refresh market theses from H2 proposals."""
    count = 0
    for proposal in exploration.theses:
        invalidation = "; ".join(proposal.invalidation_criteria)
        upsert_thesis_row(
            client,
            run_date=run_date,
            thesis_id=proposal.thesis_id,
            name=proposal.title,
            status="ACTIVE",
            invalidation=invalidation,
            notes=proposal.statement,
            confidence=proposal.confidence,
            validation_criteria=proposal.validation_criteria,
            invalidation_criteria=proposal.invalidation_criteria,
            horizon=proposal.horizon,
            thesis_kind="market",
        )
        count += 1
    return count


def persist_thesis_vehicle_map(
    client: SupabaseClient,
    *,
    run_date: date,
    vehicle_map: ThesisVehicleMapOutput,
    source_exploration_key: str = "market-thesis-exploration",
) -> int:
    """Upsert H3 vehicle mappings."""
    total = 0
    for mapping in vehicle_map.mappings:
        total += upsert_thesis_vehicles(
            client,
            run_date=run_date,
            thesis_id=mapping.thesis_id,
            tickers=list(mapping.candidate_tickers),
            rationale=mapping.rationale,
            source_exploration_key=source_exploration_key,
        )
    return total


def invalidation_hits_from_signals(
    active_theses: list[dict[str, Any]],
    *,
    triggered_criteria: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Resolve which theses have invalidation criteria hits for H1.

    ``triggered_criteria`` maps ``thesis_id`` → criterion strings that fired
    (typically from digest/regime signals or test fixtures).
    """
    if not triggered_criteria:
        return {}
    hits: dict[str, list[str]] = {}
    known_ids = {str(r.get("thesis_id")) for r in active_theses}
    for thesis_id, criteria in triggered_criteria.items():
        if thesis_id not in known_ids:
            continue
        clean = [str(c).strip() for c in criteria if str(c).strip()]
        if clean:
            hits[thesis_id] = clean
    return hits


def upsert_vehicle_thesis_from_analyst(
    client: SupabaseClient,
    *,
    run_date: date,
    ticker: str,
    analyst_payload: dict[str, Any],
) -> None:
    """Create/update a vehicle-local thesis row when H5 covers an unlinked ticker."""
    thesis_id = f"vehicle-{ticker.lower()}"
    invalidation = str(analyst_payload.get("risks") or analyst_payload.get("bear_case") or "")
    upsert_thesis_row(
        client,
        run_date=run_date,
        thesis_id=thesis_id,
        name=f"{ticker} vehicle thesis",
        status="ACTIVE",
        vehicle=ticker,
        invalidation=invalidation[:500] if invalidation else None,
        notes=str(analyst_payload.get("thesis") or "")[:2000] or None,
        thesis_kind="vehicle",
        linked_market_thesis_id=None,
    )
