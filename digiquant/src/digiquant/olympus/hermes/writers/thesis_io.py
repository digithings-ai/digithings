"""Supabase writers for thesis-first Hermes phases."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.models.thesis import (
    MarketThesisExplorationOutput,
    ThesisProposal,
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
    topic_key: str | None = None,
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
    if topic_key is not None:
        row["topic_key"] = topic_key
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
    # Never persist a self-referential link (a vehicle/market thesis linked to
    # itself is meaningless and was the shape of ~140 legacy rows, #1563). This
    # single write chokepoint neutralizes every source — the H5 resolver below,
    # and H1's carry-forward of a prior row's stale link (persist_thesis_review).
    if linked_market_thesis_id is not None and linked_market_thesis_id != thesis_id:
        row["linked_market_thesis_id"] = linked_market_thesis_id
    client.table("theses").upsert(row, on_conflict="date,thesis_id").execute()


def resolve_primary_market_thesis(
    client: SupabaseClient,
    *,
    ticker: str,
    run_date: date,
) -> str | None:
    """The market thesis a vehicle ticker primarily expresses, from ``thesis_vehicles``.

    ``thesis_vehicles`` (written by H3) is the reliable ticker → market-thesis map —
    unlike ``theses.linked_market_thesis_id``, which H5 left null and a same-date H3
    back-fill could never populate (the vehicle row doesn't exist at H3 time). Prefer
    the current run's mapping; fall back to the most recent prior mapping so a
    carried held name still links. When a ticker maps to several market theses the
    PRIMARY is the lowest ``candidate_rank`` (ties → lexical ``thesis_id``), matching
    the frontend's primary-attribution rule (#1562). Returns None when unmapped.
    """
    try:
        resp = (
            client.table("thesis_vehicles")
            .select("thesis_id,candidate_rank,date")
            .eq("ticker", ticker)
            .lte("date", run_date.isoformat())
            .order("date", desc=True)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 — linkage is enrichment; never block the graph
        logger.warning("thesis_vehicles lookup failed for %s (%s)", ticker, exc)
        return None
    rows = list(getattr(resp, "data", None) or [])
    if not rows:
        return None
    # All rows share the newest date available at/under run_date (desc order);
    # keep only that date's mappings, then pick the primary by rank then id.
    newest = rows[0].get("date")
    candidates = [r for r in rows if r.get("date") == newest and r.get("thesis_id")]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (r.get("candidate_rank") or 1_000_000, str(r.get("thesis_id"))))
    return str(candidates[0]["thesis_id"])


def upsert_thesis_vehicles(
    client: SupabaseClient,
    *,
    run_date: date,
    thesis_id: str,
    tickers: list[str],
    rationale: str = "",
    source_exploration_key: str | None = None,
) -> int:
    """Upsert ``thesis_vehicles`` rows for one thesis mapping.

    Also back-fills ``theses.linked_market_thesis_id`` on the corresponding
    ``vehicle-{ticker}`` thesis rows so the frontend two-tier hierarchy shows
    real linkage instead of the 'Unlinked expressions' fallback (#1047).
    """
    date_str = run_date.isoformat()
    written = 0
    for rank, ticker in enumerate(tickers, start=1):
        row: dict[str, Any] = {
            "date": date_str,
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
            continue
        # Best-effort re-link of any vehicle-{ticker} row that ALREADY exists for
        # this date (e.g. a prior same-day run). On a fresh date this no-ops (the
        # row is created later by H5) — H5 is now the authoritative linker and
        # resolves from this same ``thesis_vehicles`` map at creation time (#1563).
        try:
            client.table("theses").update({"linked_market_thesis_id": thesis_id}).eq(
                "date", date_str
            ).eq("thesis_id", f"vehicle-{ticker.lower()}").execute()
        except Exception as exc:  # noqa: BLE001 — enrichment must not block graph
            logger.warning(
                "thesis link update failed for vehicle-%s → %s (%s)", ticker, thesis_id, exc
            )
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
            topic_key=prior_row.get("topic_key"),
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


def validate_market_thesis_proposals(
    proposals: list[ThesisProposal],
    active_theses: list[dict[str, Any]],
) -> tuple[list[ThesisProposal], list[str]]:
    """Keep only proposals that preserve one canonical active thesis per topic."""
    active_market = [
        row for row in active_theses if str(row.get("thesis_kind") or "market").lower() == "market"
    ]
    active_by_id = {
        str(row.get("thesis_id") or "").strip(): row
        for row in active_market
        if str(row.get("thesis_id") or "").strip()
    }
    active_ids_by_topic: dict[str, list[str]] = {}
    for thesis_id, row in active_by_id.items():
        topic_key = str(row.get("topic_key") or "").strip()
        if topic_key:
            active_ids_by_topic.setdefault(topic_key, []).append(thesis_id)
    accepted: list[ThesisProposal] = []
    errors: list[str] = []
    proposed_id_by_topic: dict[str, str] = {}
    proposed_ids: set[str] = set()

    for proposal in proposals:
        if proposal.thesis_id in proposed_ids:
            errors.append(f"{proposal.thesis_id}: thesis_id is already proposed in this run")
            continue

        prior_proposal_id = proposed_id_by_topic.get(proposal.topic_key)
        if prior_proposal_id is not None:
            errors.append(
                f"{proposal.thesis_id}: topic '{proposal.topic_key}' is already proposed "
                f"in this run by '{prior_proposal_id}'"
            )
            continue

        active_ids = sorted(active_ids_by_topic.get(proposal.topic_key, []))
        if len(active_ids) > 1:
            errors.append(
                f"{proposal.thesis_id}: topic '{proposal.topic_key}' has multiple active "
                f"theses {active_ids}; consolidate the register before writing"
            )
            continue
        active_id = active_ids[0] if active_ids else None
        if proposal.action == "create":
            if active_id is not None:
                errors.append(
                    f"{proposal.thesis_id}: topic '{proposal.topic_key}' already belongs to "
                    f"active thesis '{active_id}'; update that thesis instead"
                )
                continue
            if proposal.thesis_id in active_by_id:
                errors.append(
                    f"{proposal.thesis_id}: thesis_id already exists; use action='update'"
                )
                continue
        else:
            active_row = active_by_id.get(proposal.thesis_id)
            if active_row is None:
                errors.append(
                    f"{proposal.thesis_id}: action='update' does not reference an active thesis"
                )
                continue
            active_topic = str(active_row.get("topic_key") or "").strip()
            if active_topic and active_topic != proposal.topic_key:
                errors.append(
                    f"{proposal.thesis_id}: topic_key must remain '{active_topic}' when updating"
                )
                continue

        accepted.append(proposal)
        proposed_ids.add(proposal.thesis_id)
        proposed_id_by_topic[proposal.topic_key] = proposal.thesis_id

    return accepted, errors


def persist_market_thesis_exploration(
    client: SupabaseClient,
    *,
    run_date: date,
    exploration: MarketThesisExplorationOutput,
    status_by_id: Mapping[str, str] | None = None,
) -> int:
    """Insert/refresh market theses from H2 proposals."""
    count = 0
    for proposal in exploration.theses:
        invalidation = "; ".join(proposal.invalidation_criteria)
        upsert_thesis_row(
            client,
            run_date=run_date,
            thesis_id=proposal.thesis_id,
            topic_key=proposal.topic_key,
            name=proposal.title,
            status=(status_by_id or {}).get(proposal.thesis_id, "ACTIVE")
            if proposal.action == "update"
            else "ACTIVE",
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
    linked_market_thesis_id: str | None = None,
) -> None:
    """Create/update a vehicle-local thesis row when H5 covers an unlinked ticker.

    The vehicle row is linked to the market thesis it expresses at CREATION time
    (#1563): the caller rarely supplies a valid link, and the legacy same-date H3
    back-fill could never populate it (the row doesn't exist yet at H3), which
    left every vehicle thesis null-linked in prod. Resolve the link from the
    reliable ``thesis_vehicles`` map instead — self-healing, since H5 rewrites a
    fresh vehicle row each run.
    """
    thesis_id = f"vehicle-{ticker.lower()}"
    link = linked_market_thesis_id
    if link is None or link == thesis_id:
        link = resolve_primary_market_thesis(client, ticker=ticker, run_date=run_date)
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
        linked_market_thesis_id=link,
    )
