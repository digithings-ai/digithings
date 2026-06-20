"""Held-ticker survival invariant for the Phase 7C/7CD cap (#936).

HARD INVARIANT: every prior-book holding appears in the Phase 7C/7CD
per-ticker fan-out, regardless of the ``ATLAS_MAX_ANALYSTS`` cap.

Background: ``_capped_tickers`` previously did ``tickers[:max_analysts]``
with no awareness of which tickers are current holdings. On 2026-06-18 prod
a held name (IJR) fell outside the cap window and was dropped from the
fan-out, so the PM auto-exited it. This module pins the fix:

- held tickers always survive the cap (the cap budget is spent on
  non-held candidates);
- if held alone exceed the cap, keep them all (over budget) and warn;
- ``ATLAS_MAX_ANALYSTS=0`` (uncapped) is unchanged;
- the ``held=...`` kwarg threads cleanly through the builders and the
  ``build_hermes_phases`` smoke path.
"""

from __future__ import annotations

import pytest

from digiquant.olympus.hermes.phases import phase7c_analyst, phase7cd_debate
from digiquant.olympus.hermes.phases.phase7c_analyst import (
    _capped_tickers as _capped_7c,
    build_phase7c,
    build_phase7c_specialists,
)
from digiquant.olympus.hermes.phases.phase7cd_debate import (
    _capped_tickers as _capped_7cd,
    build_phase7cd,
)
from digiquant.olympus.hermes.graph import build_hermes_phases


_BOOK = ["SPY", "IJR", "XLP", "AAA", "BBB", "CCC"]
_HELD = {"SPY", "IJR", "XLP"}


@pytest.mark.unit
class TestCappedTickersHeldInvariant:
    """Both phase modules share identical cap semantics; test them in tandem."""

    @pytest.mark.parametrize("capped", [_capped_7c, _capped_7cd])
    def test_held_survive_with_budget_for_candidates(
        self, capped, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cap=4, 3 held -> all 3 held present + exactly 1 candidate (budget 4-3)."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        result = capped(list(_BOOK), held=_HELD)

        assert _HELD.issubset(set(result)), f"held dropped: {_HELD - set(result)}"
        assert len(result) == 4
        non_held = [t for t in result if t not in _HELD]
        assert len(non_held) == 1, f"expected 1 candidate within budget, got {non_held}"

    @pytest.mark.parametrize("capped", [_capped_7c, _capped_7cd])
    def test_held_over_budget_all_kept_and_warns(
        self, capped, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """cap=2 < 3 held -> all 3 held still present (over budget) + a warning."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        with caplog.at_level("WARNING"):
            result = capped(list(_BOOK), held=_HELD)

        assert _HELD.issubset(set(result)), f"held dropped over budget: {_HELD - set(result)}"
        # No non-held candidate may sneak in -- the budget is fully consumed by held.
        assert set(result) == _HELD
        assert any(record.levelname == "WARNING" for record in caplog.records), (
            "expected a warning when held tickers exceed the cap"
        )

    @pytest.mark.parametrize("capped", [_capped_7c, _capped_7cd])
    def test_uncapped_returns_full_list(self, capped, monkeypatch: pytest.MonkeyPatch) -> None:
        """ATLAS_MAX_ANALYSTS=0 -> no capping; the full list passes through."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "0")
        assert capped(list(_BOOK), held=_HELD) == _BOOK

    @pytest.mark.parametrize("capped", [_capped_7c, _capped_7cd])
    def test_default_held_empty_preserves_legacy_slice(
        self, capped, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ``held`` -> identical to the pre-#936 ``tickers[:cap]`` behavior."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        assert capped(list(_BOOK)) == _BOOK[:4]

    @pytest.mark.parametrize("capped", [_capped_7c, _capped_7cd])
    def test_held_preserve_watchlist_order(self, capped, monkeypatch: pytest.MonkeyPatch) -> None:
        """Result preserves input order (held kept where they appear, no reshuffle)."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        result = capped(list(_BOOK), held={"CCC", "SPY"})
        # SPY (idx 0) and CCC (idx 5) are held; budget fills candidates from the head.
        assert result[0] == "SPY"
        assert "CCC" in result
        assert result == sorted(result, key=_BOOK.index)


@pytest.mark.unit
class TestBuilderThreadingHeld:
    """The ``held`` kwarg must reach the cap through every public builder."""

    def test_phase7c_specialists_keeps_held_node(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        phase = build_phase7c_specialists(list(_BOOK), held=_HELD)
        node_names = {n.name for n in phase.nodes}
        # Every held ticker has its 4 axis nodes wired (e.g. technical-analyst-IJR).
        for ticker in _HELD:
            assert f"technical-analyst-{ticker}" in node_names

    def test_build_phase7c_threads_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        specialists, _join = build_phase7c(list(_BOOK), held=_HELD)
        node_names = {n.name for n in specialists.nodes}
        for ticker in _HELD:
            assert f"technical-analyst-{ticker}" in node_names

    def test_build_phase7cd_threads_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        phases = build_phase7cd(list(_BOOK), rounds=1, held=_HELD)
        # Bull round phase carries one node per capped ticker.
        bull = next(p for p in phases if p.name.startswith("phase7cd_bull"))
        bull_tickers = {
            n.name.replace("bull-researcher-", "").rsplit("-r", 1)[0] for n in bull.nodes
        }
        assert _HELD.issubset(bull_tickers), f"held dropped from debate: {_HELD - bull_tickers}"

    def test_build_hermes_phases_smoke_with_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``build_hermes_phases(..., held=...)`` compiles and preserves held nodes."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        phases = build_hermes_phases(watchlist=list(_BOOK), held=_HELD)
        all_node_names = {n.name for phase in phases for n in phase.nodes}
        for ticker in _HELD:
            assert f"technical-analyst-{ticker}" in all_node_names
            assert any(name.startswith(f"bull-researcher-{ticker}") for name in all_node_names)


def test_modules_share_identical_cap_signature() -> None:
    """Sanity: both ``_capped_tickers`` functions accept the new ``held`` param."""
    import inspect

    sig_7c = inspect.signature(phase7c_analyst._capped_tickers)
    sig_7cd = inspect.signature(phase7cd_debate._capped_tickers)
    assert "held" in sig_7c.parameters
    assert "held" in sig_7cd.parameters


@pytest.mark.unit
def test_prior_book_holdings_survive_fan_out(monkeypatch: pytest.MonkeyPatch) -> None:
    """Integration-style: a prior book {SPY, IJR, XLP} survives the fan-out under a tight cap.

    Reproduces the Jun-18 regression shape: held names ranked behind candidates
    in the watchlist still all reach the 7C specialist nodes.
    """
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
    # Held names deliberately interleaved/late in the watchlist.
    watchlist = ["AAA", "BBB", "SPY", "CCC", "IJR", "DDD", "XLP"]
    held = {"SPY", "IJR", "XLP"}
    phases = build_hermes_phases(watchlist=watchlist, held=held)
    specialist_phase = next(p for p in phases if p.name == "phase7c_specialists")
    fan_out_tickers = {
        n.name.split("-analyst-", 1)[1] for n in specialist_phase.nodes if "-analyst-" in n.name
    }
    assert held.issubset(fan_out_tickers), (
        f"PRIOR-BOOK HOLDINGS DROPPED FROM 7C FAN-OUT: {held - fan_out_tickers}"
    )
