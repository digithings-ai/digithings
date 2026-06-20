"""H4 — deterministic opportunity screener (focus roster).

Builds ``state.phase_hermes.focus_roster``: prior-book holdings (#936) plus
thesis-mapped vehicles from H3 and technical opportunity candidates. Replaces
``candidates.select_focus_tickers`` for the Hermes fan-out once H4 runs in-graph.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Sequence
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digigraph.graph.pipeline_builder import NodeSpec, PipelinePhase

from digiquant.olympus.atlas.state import FocusRosterEntry
from digiquant.olympus.hermes.candidates import select_focus_tickers
from digiquant.olympus.hermes.roster_cap import capped_tickers
from digiquant.olympus.hermes.state import HermesState

logger = logging.getLogger(__name__)

NODE_ID = "hermes/thesis/opportunity-screener"
PHASE_NAME = "hermes_h4_opportunity_screener"


def extract_thesis_mappings(vehicle_map: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Return ``(thesis_id, ticker)`` pairs from an H3 ``thesis_vehicle_map`` payload."""
    if not vehicle_map:
        return []
    body = vehicle_map.get("body") if isinstance(vehicle_map.get("body"), dict) else vehicle_map
    mappings = body.get("mappings") if isinstance(body, dict) else None
    if not isinstance(mappings, list):
        return []
    pairs: list[tuple[str, str]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        thesis_id = str(mapping.get("thesis_id") or "").strip()
        tickers = mapping.get("candidate_tickers") or []
        if not thesis_id:
            continue
        for raw in tickers:
            ticker = str(raw or "").strip().upper()
            if ticker:
                pairs.append((thesis_id, ticker))
    return pairs


def compute_focus_roster(
    *,
    watchlist: Sequence[str],
    held: Collection[str],
    thesis_mappings: Iterable[tuple[str, str]] = (),
    run_date: date | None = None,
    client: Any = None,
    top_n: int | None = None,
) -> list[FocusRosterEntry]:
    """Deterministic focus roster: held + thesis-mapped + technical candidates."""
    held_set = {str(t).strip().upper() for t in held if str(t).strip()}
    normalized_watchlist = [str(t).strip().upper() for t in watchlist if str(t).strip()]
    entry_by_ticker: dict[str, FocusRosterEntry] = {}

    for ticker in normalized_watchlist:
        if ticker in held_set:
            entry_by_ticker[ticker] = FocusRosterEntry(ticker=ticker, roster_reason="held")
    for ticker in sorted(held_set):
        if ticker not in entry_by_ticker:
            entry_by_ticker[ticker] = FocusRosterEntry(ticker=ticker, roster_reason="held")

    for thesis_id, ticker in thesis_mappings:
        ticker = ticker.strip().upper()
        if not ticker or ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(
            ticker=ticker,
            roster_reason="thesis_mapped",
            linked_market_thesis_id=thesis_id,
        )

    technical_pool = [t for t in normalized_watchlist if t not in entry_by_ticker]
    technical_picks: list[str] = []
    if technical_pool and run_date is not None:
        if client is not None:
            technical_picks = select_focus_tickers(
                client=client,
                watchlist=technical_pool,
                run_date=run_date,
                top_n=top_n,
                holdings=[],
            )
        else:
            technical_picks = list(technical_pool)
    for ticker in technical_picks:
        if ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(ticker=ticker, roster_reason="technical")

    ordered_tickers = [t for t in normalized_watchlist if t in entry_by_ticker]
    for ticker in sorted(held_set):
        if ticker not in ordered_tickers and ticker in entry_by_ticker:
            ordered_tickers.append(ticker)
    for ticker in entry_by_ticker:
        if ticker not in ordered_tickers:
            ordered_tickers.append(ticker)

    protected = set(held_set) | {ticker for _, ticker in thesis_mappings}
    capped = capped_tickers(ordered_tickers, held=protected)
    return [entry_by_ticker[t] for t in capped]


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


def _h4_node(state: HermesState) -> dict[str, Any]:
    mappings = extract_thesis_mappings(state.phase_hermes.thesis_vehicle_map)
    roster = compute_focus_roster(
        watchlist=list(state.config.watchlist),
        held=holdings_from_state(state),
        thesis_mappings=mappings,
        run_date=state.run_date,
    )
    logger.info(
        "H4 focus roster (%d): %s",
        len(roster),
        ", ".join(f"{e.ticker}:{e.roster_reason}" for e in roster),
    )
    return {
        "phase_hermes": state.phase_hermes.model_copy(update={"focus_roster": roster}),
    }


def holdings_from_state(state: HermesState) -> set[str]:
    """Prior-book holdings from preflight ``prior_context.prior_book``."""
    from digiquant.olympus.hermes.candidates import holdings_from_prior_book

    return set(holdings_from_prior_book(state.prior_context.prior_book))


def build_h4_opportunity_screener() -> PipelinePhase:
    return PipelinePhase(
        name=PHASE_NAME,
        nodes=[NodeSpec(name=NODE_ID, run=_h4_node)],
    )
