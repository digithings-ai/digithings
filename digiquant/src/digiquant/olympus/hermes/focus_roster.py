"""Focus roster helpers shared by H4 and legacy 7C/7CD strangler nodes."""

from __future__ import annotations

from digiquant.olympus.hermes.state import HermesState


def ticker_in_focus_roster(state: HermesState, ticker: str) -> bool:
    """Return whether *ticker* is on the H4 runtime roster (empty roster → allow all)."""
    roster = state.phase_hermes.focus_roster
    if not roster:
        return True
    want = ticker.strip().upper()
    return any(entry.ticker.upper() == want for entry in roster)


def focus_roster_tickers(state: HermesState) -> list[str]:
    """Tickers from H4 ``focus_roster`` in roster order."""
    return [entry.ticker for entry in state.phase_hermes.focus_roster]


def with_fanout_ticker(state: HermesState, ticker: str) -> HermesState:
    """Return a state copy carrying ``ticker`` as the per-Send fan-out cursor (H5/H6 map).

    Used as the ``with_item`` hook of a ``FanOutPhase``: each parallel worker receives this
    copy and reads ``state.hermes_fanout_ticker`` to know which roster ticker it owns.
    """
    return state.model_copy(update={"hermes_fanout_ticker": ticker})
