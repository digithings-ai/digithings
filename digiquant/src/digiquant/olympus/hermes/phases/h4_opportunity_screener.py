"""H4 — deterministic opportunity screener (focus roster).

Builds ``state.phase_hermes.focus_roster``: prior-book holdings (#936) plus
thesis-mapped vehicles from H3 and technical opportunity candidates. Replaces
``candidates.select_focus_tickers`` for the Hermes fan-out once H4 runs in-graph.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import ExcludedTicker, FocusRosterEntry
from digiquant.olympus.atlas.supabase_io import SupabaseClient
from digiquant.olympus.hermes.candidates import select_focus_tickers
from digiquant.olympus.hermes.roster_cap import capped_tickers
from digiquant.olympus.hermes.state import HermesState

logger = logging.getLogger(__name__)

NODE_ID = "hermes/thesis/opportunity-screener"
PHASE_NAME = "hermes_h4_opportunity_screener"


def _held_passes_gate(
    ticker: str,
    linked_thesis_id: str | None,
    price_deltas: Mapping[str, float] | None,
) -> bool:
    """Return True if a held ticker should be dispatched to the focus roster.

    Gate is disabled (always-analyze) when ``HERMES_HELD_GATE=off``.
    Otherwise, a held ticker passes when it has a linked thesis OR its absolute
    price delta meets or exceeds the staleness threshold (``HERMES_HELD_STALENESS_DELTA``,
    default 0.005 = 0.5%).
    """
    if os.environ.get("HERMES_HELD_GATE", "on").strip().lower() == "off":
        return True
    if linked_thesis_id:
        return True
    threshold = float(os.environ.get("HERMES_HELD_STALENESS_DELTA", "0.005"))
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
) -> list[FocusRosterEntry]:
    """Deterministic focus roster: held + thesis-mapped + technical candidates.

    ``min_new_candidates`` (#950): the roster cap expands (if necessary) so
    that at least this many non-held, non-thesis-mapped candidates survive
    when new candidates are available. Prevents roster freeze.
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

    active_held = held_set - gated_out_held
    protected = active_held | {ticker for _, ticker, _ in thesis_mappings}
    capped = capped_tickers(ordered_tickers, held=protected, min_new=min_new_candidates)
    return [entry_by_ticker[t] for t in capped]


def compute_focus_roster_excluded(
    watchlist: Sequence[str],
    roster: list[FocusRosterEntry],
    *,
    held: Collection[str],
) -> list[ExcludedTicker]:
    """Return exclusion ledger entries for watchlist tickers NOT in the focus roster.

    For each normalized watchlist ticker absent from *roster*:
    - If the ticker is in *held*: reason = "held, no material change (below staleness threshold)".
    - Otherwise: reason = "not thesis-mapped and below technical screen".
    """
    rostered = {e.ticker for e in roster}
    held_upper = {str(t).strip().upper() for t in held if str(t).strip()}
    excluded: list[ExcludedTicker] = []
    for raw in watchlist:
        ticker = str(raw).strip().upper()
        if not ticker or ticker in rostered:
            continue
        if ticker in held_upper:
            reason = "held, no material change (below staleness threshold)"
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
    def _h4_node(state: HermesState) -> dict[str, Any]:
        watchlist = list(state.config.watchlist)
        held = holdings_from_state(state)
        mappings = extract_thesis_mappings(state.phase_hermes.thesis_vehicle_map)
        roster = compute_focus_roster(
            watchlist=watchlist,
            held=held,
            thesis_mappings=mappings,
            price_deltas=dict(state.price_deltas),
            run_date=state.run_date,
            client=client,
        )
        excluded = compute_focus_roster_excluded(watchlist, roster, held=held)
        logger.info(
            "H4 focus roster (%d): %s",
            len(roster),
            ", ".join(f"{e.ticker}:{e.roster_reason}" for e in roster),
        )
        logger.info(
            "H4 excluded ledger (%d): %s",
            len(excluded),
            ", ".join(e.ticker for e in excluded),
        )
        return {
            "phase_hermes": state.phase_hermes.model_copy(
                update={"focus_roster": roster, "focus_roster_excluded": excluded}
            ),
        }

    return _h4_node


def holdings_from_state(state: HermesState) -> set[str]:
    """Prior-book holdings from preflight ``prior_context.prior_book``."""
    from digiquant.olympus.hermes.candidates import holdings_from_prior_book

    return set(holdings_from_prior_book(state.prior_context.prior_book))


def build_h4_opportunity_screener(*, client: SupabaseClient | None = None) -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h4_node_factory(client))],
    )
