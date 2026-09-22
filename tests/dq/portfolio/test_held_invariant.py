"""Held-ticker cap invariant tests (#936) — screener/analyst/deliberation roster cap."""

from __future__ import annotations

import inspect

import pytest
from digiquant.portfolio.phases.analyst import build_analyst
from digiquant.portfolio.phases.deliberation import build_deliberation
from digiquant.portfolio.roster_cap import capped_tickers

_BOOK = ("AAA", "BBB", "SPY", "CCC", "IJR", "XLP")
_HELD = {"SPY", "IJR", "XLP"}


@pytest.mark.unit
class TestHeldInvariantCap:
    def test_capped_tickers_keeps_all_held_when_over_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "3")
        kept = capped_tickers(list(_BOOK), held=_HELD)
        assert set(_HELD).issubset(set(kept))
        # #1767: when the book alone fills the cap, #950's new-candidate reservation is
        # NOT honoured — it used to expand the cap, which is how DIGIQUANT_MAX_ANALYSTS
        # stopped capping. The book is the only sanctioned overshoot.
        assert len(kept) <= max(3, len(_HELD))
        assert [t for t in kept if t not in _HELD] == []

    def test_analyst_nodes_cover_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "3")
        phase = build_analyst(list(_BOOK), held=_HELD)
        names = {n.name for n in phase.nodes}
        for ticker in _HELD:
            assert f"portfolio/asset-analyst-{ticker}" in names

    def test_deliberation_nodes_cover_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGIQUANT_MAX_ANALYSTS", "3")
        phase = build_deliberation(list(_BOOK), held=_HELD)
        names = {n.name for n in phase.nodes}
        for ticker in _HELD:
            assert f"portfolio/deliberation-{ticker}" in names

    def test_roster_cap_signatures_align(self) -> None:
        sig = inspect.signature(capped_tickers)
        assert "held" in sig.parameters
