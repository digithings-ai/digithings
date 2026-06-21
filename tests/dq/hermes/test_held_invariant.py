"""Held-ticker cap invariant tests (#936) — H4/H5/H6 roster cap."""

from __future__ import annotations

import inspect

import pytest

from digiquant.olympus.hermes.phases.h5_asset_analyst import build_h5_asset_analyst
from digiquant.olympus.hermes.phases.h6_deliberation import build_h6_deliberation
from digiquant.olympus.hermes.roster_cap import capped_tickers

_BOOK = ("AAA", "BBB", "SPY", "CCC", "IJR", "XLP")
_HELD = {"SPY", "IJR", "XLP"}


@pytest.mark.unit
class TestHeldInvariantCap:
    def test_capped_tickers_keeps_all_held_when_over_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        kept = capped_tickers(list(_BOOK), held=_HELD)
        assert set(_HELD).issubset(set(kept))
        # With min_new=1 (default), one non-held candidate is also reserved (#950).
        non_held = [t for t in kept if t not in _HELD]
        assert len(non_held) >= 1

    def test_h5_nodes_cover_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        phase = build_h5_asset_analyst(list(_BOOK), held=_HELD)
        names = {n.name for n in phase.nodes}
        for ticker in _HELD:
            assert f"hermes/portfolio/asset-analyst-{ticker}" in names

    def test_h6_nodes_cover_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        phase = build_h6_deliberation(list(_BOOK), held=_HELD)
        names = {n.name for n in phase.nodes}
        for ticker in _HELD:
            assert f"hermes/portfolio/deliberation-{ticker}" in names

    def test_roster_cap_signatures_align(self) -> None:
        sig = inspect.signature(capped_tickers)
        assert "held" in sig.parameters
