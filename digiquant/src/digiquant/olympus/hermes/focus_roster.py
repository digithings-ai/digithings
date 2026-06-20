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
