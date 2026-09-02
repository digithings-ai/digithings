"""H4 — deterministic opportunity screener (focus roster).

Builds ``state.phase_portfolio.focus_roster``: prior-book holdings (#936) plus
thesis-mapped vehicles from H3 and technical opportunity candidates. Replaces
``candidates.select_focus_tickers`` for the portfolio fan-out once H4 runs in-graph.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import date
from itertools import zip_longest
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous graph / dict shapes
)

from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.dashboard.overlay.persist import portfolio_document_key
from digiquant.portfolio.budget_controller import assess_budget
from digiquant.portfolio.candidates import holdings_from_prior_book, select_focus_tickers
from digiquant.portfolio.research_attention import h4_phase_attention_update
from digiquant.portfolio.roster_cap import capped_tickers, configured_max_analysts
from digiquant.portfolio.state import PortfolioState
from digiquant.research.state import ExcludedTicker, FocusRosterEntry
from digiquant.research.supabase_io import SupabaseClient, publish_document

logger = logging.getLogger(__name__)

NODE_ID = "portfolio/thesis/opportunity-screener"
PHASE_NAME = "portfolio_h4_opportunity_screener"
OPPORTUNITY_SCREENER_DOCUMENT_KEY = "opportunity-screener"
OPPORTUNITY_SCREENER_PAYLOAD_DOC_TYPE = "opportunity_screen"


def _held_passes_gate(
    ticker: str,
    linked_thesis_id: str | None,
    price_deltas: Mapping[str, float] | None,
) -> bool:
    """Return True if a held ticker should be dispatched to the focus roster.

    Gate is disabled (always-analyze) when ``PORTFOLIO_HELD_GATE=off``.
    Otherwise, a held ticker passes when it has a linked thesis OR its absolute
    price delta meets or exceeds the staleness threshold (``PORTFOLIO_HELD_STALENESS_DELTA``,
    default 0.005 = 0.5%).
    """
    if os.environ.get("PORTFOLIO_HELD_GATE", "on").strip().lower() == "off":
        return True
    if linked_thesis_id:
        return True
    if not price_deltas:
        # No delta signal at all this run (e.g. a baseline/monthly run, where price_deltas
        # is empty) — staleness is unjudgeable, so don't gate; keep full held coverage (#1017).
        return True
    threshold = float(os.environ.get("PORTFOLIO_HELD_STALENESS_DELTA", "0.005"))
    return abs((price_deltas or {}).get(ticker, 0.0)) >= threshold


def extract_thesis_mappings(vehicle_map: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    """Return ``(thesis_id, ticker, rationale)`` triples from an H3 ``thesis_vehicle_map``."""
    if not vehicle_map:
        return []
    body = vehicle_map.get("body") if isinstance(vehicle_map.get("body"), dict) else vehicle_map
    mappings = body.get("mappings") if isinstance(body, dict) else None
    if not isinstance(mappings, list):
        return []
    triples: list[tuple[str, str, str]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        thesis_id = str(mapping.get("thesis_id") or "").strip()
        rationale = str(mapping.get("rationale") or "").strip()
        if not thesis_id:
            continue
        for raw in mapping.get("candidate_tickers") or []:
            ticker = str(raw or "").strip().upper()
            if ticker:
                triples.append((thesis_id, ticker, rationale))
    return triples


def thesis_priority_order(thesis_mappings: Iterable[tuple[str, str, str]]) -> list[str]:
    """Breadth-first round-robin over theses: every thesis's rank-1 vehicle, then rank-2, …

    H3 emits each thesis's ``candidate_tickers`` in within-thesis rank order, and
    nothing in the vehicle map carries a *conviction* signal — ``candidate_rank`` is a
    position inside the mapping, not a score — so "prioritise the thesis map" (#1767)
    can only mean **breadth**: cover as many theses as the budget allows before
    deepening any one of them. Flat truncation would hand the whole budget to the first
    two or three theses and leave the rest with no coverage at all. The absence of a
    conviction signal is a known limitation, recorded in ``portfolio/docs/ARCHITECTURE.md``.
    """
    by_thesis: dict[str, list[str]] = {}
    for thesis_id, ticker, _rationale in thesis_mappings:
        normalized = ticker.strip().upper()
        if not normalized:
            continue
        bucket = by_thesis.setdefault(thesis_id, [])
        if normalized not in bucket:
            bucket.append(normalized)
    order: list[str] = []
    seen: set[str] = set()
    for tier in zip_longest(*by_thesis.values()):
        for ticker in tier:
            if ticker and ticker not in seen:
                seen.add(ticker)
                order.append(ticker)
    return order


def compute_focus_roster(
    *,
    watchlist: Sequence[str],
    held: Collection[str],
    thesis_mappings: Iterable[tuple[str, str, str]] = (),
    price_deltas: Mapping[str, float] | None = None,
    run_date: date | None = None,
    client: SupabaseClient | None = None,
    top_n: int | None = None,
    min_new_candidates: int = 1,
    adaptive_max_analysts: int | None = None,
) -> list[FocusRosterEntry]:
    """Deterministic focus roster: held + thesis-mapped + technical candidates.

    ``min_new_candidates`` (#950): the roster cap expands (if necessary) so
    that at least this many non-held, non-thesis-mapped candidates survive
    when new candidates are available. Prevents roster freeze.

    ``adaptive_max_analysts`` (optional): when not None, overrides the
    ATLAS_MAX_ANALYSTS environment variable as the analyst cap for this
    run. When None, falls back to the env var.
    """
    held_set = {str(t).strip().upper() for t in held if str(t).strip()}
    normalized_watchlist = [str(t).strip().upper() for t in watchlist if str(t).strip()]
    entry_by_ticker: dict[str, FocusRosterEntry] = {}

    thesis_mappings = list(thesis_mappings)

    thesis_by_ticker: dict[str, tuple[str, str]] = {}
    for thesis_id, ticker, rationale in thesis_mappings:
        t = ticker.strip().upper()
        if t and t not in thesis_by_ticker:
            thesis_by_ticker[t] = (thesis_id, rationale)

    def _held_entry(ticker: str) -> FocusRosterEntry:
        tid_rat = thesis_by_ticker.get(ticker)
        return FocusRosterEntry(
            ticker=ticker,
            roster_reason="held",
            linked_market_thesis_id=tid_rat[0] if tid_rat else None,
            rationale=(
                f"held position; {tid_rat[1]}" if tid_rat and tid_rat[1] else "held position"
            ),
        )

    gated_out_held: set[str] = set()
    for ticker in normalized_watchlist:
        if ticker in held_set:
            tid_rat = thesis_by_ticker.get(ticker)
            linked_thesis_id = tid_rat[0] if tid_rat else None
            if _held_passes_gate(ticker, linked_thesis_id, price_deltas):
                entry_by_ticker[ticker] = _held_entry(ticker)
            else:
                gated_out_held.add(ticker)
    for ticker in sorted(held_set):
        if ticker not in entry_by_ticker and ticker not in gated_out_held:
            tid_rat = thesis_by_ticker.get(ticker)
            linked_thesis_id = tid_rat[0] if tid_rat else None
            if _held_passes_gate(ticker, linked_thesis_id, price_deltas):
                entry_by_ticker[ticker] = _held_entry(ticker)
            else:
                gated_out_held.add(ticker)

    for thesis_id, ticker, _rationale in thesis_mappings:
        ticker = ticker.strip().upper()
        if not ticker or ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(
            ticker=ticker,
            roster_reason="thesis_mapped",
            linked_market_thesis_id=thesis_id,
            rationale=_rationale,
        )

    technical_pool = [
        t for t in normalized_watchlist if t not in entry_by_ticker and t not in gated_out_held
    ]
    technical_picks: list[str] = []
    if technical_pool and run_date is not None:
        technical_picks = (
            select_focus_tickers(
                client=client,
                watchlist=technical_pool,
                run_date=run_date,
                top_n=top_n,
                holdings=[],
            )
            if client is not None
            else list(technical_pool)
        )
    for ticker in technical_picks:
        if ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(
            ticker=ticker,
            roster_reason="technical",
            rationale="technical screen: top-ranked watchlist candidate by price/technical signal (no linked thesis)",
        )

    ordered_tickers = [t for t in normalized_watchlist if t in entry_by_ticker]
    for ticker in sorted(held_set):
        if ticker not in ordered_tickers and ticker in entry_by_ticker:
            ordered_tickers.append(ticker)
    for ticker in entry_by_ticker:
        if ticker not in ordered_tickers:
            ordered_tickers.append(ticker)

    # #1767: ``held`` is the prior book ONLY. It used to be unioned with every ticker in
    # the H3 thesis-vehicle map, which pushed the protected set past the cap on every day
    # the map was populated (40 tickers on 2026-07-31 against a cap of 25), drove
    # ``capped_tickers`` into its over-budget #936 branch, and so bypassed the cap by
    # construction. Thesis vehicles are now *prioritised inside* the budget instead of
    # being exempt from it: protection is for positions we own, priority is for
    # conviction we have expressed.
    active_held = held_set - gated_out_held
    capped = capped_tickers(
        ordered_tickers,
        held=active_held,
        min_new=min_new_candidates,
        adaptive_max_analysts=adaptive_max_analysts,
        candidate_priority=thesis_priority_order(thesis_mappings),
    )
    return [entry_by_ticker[t] for t in capped]


def compute_focus_roster_excluded(
    watchlist: Sequence[str],
    roster: list[FocusRosterEntry],
    *,
    held: Collection[str],
    thesis_mapped: Collection[str] = (),
) -> list[ExcludedTicker]:
    """Return exclusion ledger entries for tickers NOT in the focus roster.

    Considers the union of the watchlist, *held*, and *thesis_mapped* — a prior-book
    holding is not necessarily on today's watchlist (the watchlist is the research
    universe; the book is what we own), yet a quiet held name gated out of the roster
    must still be recorded so commit-run can carry it instead of failing closed (#1030).
    Thesis vehicles are likewise not necessarily on the watchlist, and since #1767 they
    can be dropped by the analyst cap, so they need a ledger row of their own.

    For each candidate ticker absent from *roster*:
    - If the ticker is in *held*: reason = "held, no material change (below staleness threshold)".
    - Else if the ticker is in *thesis_mapped*: reason names the analyst cap, because
      "not thesis-mapped and below technical screen" would be a false statement about a
      ticker H3 explicitly nominated — the roster width is what excluded it.
    - Otherwise: reason = "not thesis-mapped and below technical screen".

    Note the ledger is *not* a carry authorisation for these rows: ``commit_io``
    intersects it with held names (``gated_out_tickers``), so a dropped thesis vehicle
    still fails closed if it somehow reaches the book with a weight.
    """
    rostered = {e.ticker for e in roster}
    held_upper = {str(t).strip().upper() for t in held if str(t).strip()}
    thesis_upper = {str(t).strip().upper() for t in thesis_mapped if str(t).strip()}
    candidates = [str(raw).strip().upper() for raw in watchlist]
    # Held / thesis names absent from the watchlist (deduped below); sorted for a
    # deterministic ledger order.
    candidates += sorted(held_upper) + sorted(thesis_upper)
    excluded: list[ExcludedTicker] = []
    seen: set[str] = set()
    for ticker in candidates:
        if not ticker or ticker in rostered or ticker in seen:
            continue
        seen.add(ticker)
        if ticker in held_upper:
            reason = "held, no material change (below staleness threshold)"
        elif ticker in thesis_upper:
            reason = "thesis-mapped vehicle beyond the analyst cap (ATLAS_MAX_ANALYSTS)"
        else:
            reason = "not thesis-mapped and below technical screen"
        excluded.append(ExcludedTicker(ticker=ticker, reason=reason))
    return excluded


def preview_focus_roster_tickers(
    *,
    watchlist: Sequence[str],
    held: Collection[str],
    run_date: date | None = None,
) -> list[str]:
    """Compile-time roster preview for the legacy 7C strangler tail."""
    effective_date = run_date or date(2099, 1, 1)
    return [
        e.ticker
        for e in compute_focus_roster(watchlist=watchlist, held=held, run_date=effective_date)
    ]


def _h4_node_factory(client: SupabaseClient | None):
    def _h4_node(state: PortfolioState) -> dict[str, Any]:
        watchlist = list(state.config.watchlist)
        held = holdings_from_state(state)
        mappings = extract_thesis_mappings(state.phase_portfolio.thesis_vehicle_map)
        static_cap = configured_max_analysts()
        budget, explore_floor, assessment = assess_budget(state, client, static_cap=static_cap)
        roster = compute_focus_roster(
            watchlist=watchlist,
            held=held,
            thesis_mappings=mappings,
            price_deltas=dict(state.price_deltas),
            run_date=state.run_date,
            client=client,
            adaptive_max_analysts=budget,
            min_new_candidates=explore_floor,
        )
        excluded = compute_focus_roster_excluded(
            watchlist,
            roster,
            held=held,
            thesis_mapped={ticker for _, ticker, _ in mappings},
        )
        # Roster width is the dominant cost driver of the whole run (#1767: width 8 → 39
        # tracked $0.86 → $4.00) and until the width breakdown reaches
        # ``atlas_run_diagnostics`` this log line is the only record of it.
        logger.info(
            "H4 focus roster (%d, cap=%d, budget=%d, theses=%d, regime=%s): %s",
            len(roster),
            static_cap,
            budget,
            len({thesis_id for thesis_id, _, _ in mappings}),
            assessment.regime if assessment else "static",
            ", ".join(f"{e.ticker}:{e.roster_reason}" for e in roster),
        )
        logger.info(
            "H4 excluded ledger (%d): %s",
            len(excluded),
            ", ".join(e.ticker for e in excluded),
        )
        phase_update = {
            "phase_portfolio": state.phase_portfolio.model_copy(
                update={"focus_roster": roster, "focus_roster_excluded": excluded}
            ),
        }
        if client is not None:
            try:
                _publish_screener_document(
                    client,
                    state,
                    roster=roster,
                    excluded=excluded,
                )
            except Exception:
                logger.exception(
                    "H4: opportunity-screener document publish failed for %s; continuing",
                    state.run_date,
                )
        planned = state.model_copy(update=phase_update)
        return {**phase_update, **h4_phase_attention_update(planned)}

    return _h4_node


def build_screener_document(
    *,
    run_date: date,
    roster: list[FocusRosterEntry],
    excluded: list[ExcludedTicker],
) -> dict[str, Any]:
    """Envelope the H4 roster for ``OpportunityScreenerDocumentView``."""
    shortlist = [entry.model_dump(mode="json") for entry in roster]
    excluded_rows = [row.model_dump(mode="json") for row in excluded]
    tickers = ", ".join(e.ticker for e in roster) or "none"
    summary = f"Focus roster ({len(roster)}): {tickers}."
    return {
        "schema_version": "1.0",
        "doc_type": OPPORTUNITY_SCREENER_PAYLOAD_DOC_TYPE,
        "date": run_date.isoformat(),
        "body": {
            "summary": summary,
            "shortlist": shortlist,
            "excluded": excluded_rows,
        },
    }


def _screener_markdown(document: dict[str, Any]) -> str:
    body = document.get("body") if isinstance(document.get("body"), dict) else {}
    date_str = str(document.get("date") or "")
    summary = str((body or {}).get("summary") or "").strip()
    shortlist = (body or {}).get("shortlist") or []
    lines = [f"# Opportunity screener {date_str}", ""]
    if summary:
        lines.extend([summary, ""])
    if isinstance(shortlist, list) and shortlist:
        lines.extend(["| Ticker | Reason | Thesis | Rationale |", "| --- | --- | --- | --- |"])
        for row in shortlist:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| {row.get('ticker') or '—'} | {row.get('roster_reason') or '—'} | "
                f"{row.get('linked_market_thesis_id') or '—'} | {row.get('rationale') or '—'} |"
            )
        lines.append("")
    return "\n".join(lines)


def _publish_screener_document(
    client: SupabaseClient,
    state: PortfolioState,
    *,
    roster: list[FocusRosterEntry],
    excluded: list[ExcludedTicker],
) -> None:
    document = build_screener_document(run_date=state.run_date, roster=roster, excluded=excluded)
    date_str = state.run_date.isoformat()
    workspace_id = state.config.workspace_id
    publish_document(
        client=client,
        document_key=portfolio_document_key(OPPORTUNITY_SCREENER_DOCUMENT_KEY, workspace_id),
        payload=document,
        doc_type=None,
        run_type=state.run_type,
        title=f"Opportunity screener {date_str}",
        date_str=date_str,
        category="portfolio",
        segment="opportunity-screener",
        content_markdown=_screener_markdown(document),
        workspace_id=workspace_id,
    )


def holdings_from_state(state: PortfolioState) -> set[str]:
    """Prior-book holdings from preflight ``prior_context.prior_book``."""
    return set(holdings_from_prior_book(state.prior_context.prior_book))


def build_h4_opportunity_screener(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h4_node_factory(client))],
    )
