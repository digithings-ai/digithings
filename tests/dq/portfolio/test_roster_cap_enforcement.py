"""ATLAS_MAX_ANALYSTS is actually enforced, and thesis vehicles are prioritised (#1767).

Before this fix ``compute_focus_roster`` passed ``active_held ∪ every thesis-map ticker``
as ``held``, so on any day the H3 vehicle map was populated the protected set exceeded the
cap, ``capped_tickers`` took its over-budget #936 branch, and the cap was bypassed by
construction. The decisive production shape is reproduced in
:func:`test_populated_thesis_map_no_longer_bypasses_the_cap`.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.portfolio.phases.h4_opportunity_screener import (
    compute_focus_roster,
    compute_focus_roster_excluded,
    thesis_priority_order,
)
from digiquant.portfolio.roster_cap import capped_tickers, configured_max_analysts

_RUN_DATE = date(2026, 7, 31)


def _prod_shape() -> tuple[list[str], set[str], list[tuple[str, str, str]]]:
    """The 2026-07-31 run: an 8-position book, 27 live theses, 40 mapped vehicles.

    Thesis ids are emitted in order and each carries 1-2 vehicles, matching the H3
    output shape (``candidate_tickers`` in within-thesis rank order).
    """
    held = {f"H{i:02d}" for i in range(8)}
    mappings: list[tuple[str, str, str]] = []
    for thesis in range(27):
        vehicles = 2 if thesis < 13 else 1  # 13*2 + 14 = 40 distinct vehicles
        for rank in range(vehicles):
            mappings.append((f"T{thesis:02d}", f"V{thesis:02d}{rank}", "rationale"))
    watchlist = sorted(held) + [ticker for _, ticker, _ in mappings]
    return watchlist, held, mappings


@pytest.mark.unit
class TestCapIsEnforced:
    def test_populated_thesis_map_no_longer_bypasses_the_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """8 held + 40 thesis vehicles under a cap of 30 must yield 30, not 48."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "30")
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
        watchlist, held, mappings = _prod_shape()

        roster = compute_focus_roster(
            watchlist=watchlist,
            held=held,
            thesis_mappings=mappings,
            run_date=_RUN_DATE,
        )

        assert len(roster) == 30, (
            f"cap bypassed: {len(roster)} analysts dispatched against ATLAS_MAX_ANALYSTS=30"
        )
        # Every held name still survives — the cap must not be paid for out of #936.
        assert held.issubset({e.ticker for e in roster})

    def test_cap_invariant_only_the_book_may_overshoot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``len(result) <= max(cap, len(held))`` — the single #1767 invariant.

        Held = 29 under a cap of 30 with an explore floor of 8: the pre-#1767 branch
        computed ``budget = max(30 - 29, 8) = 8`` and returned 37.
        """
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "30")
        held = [f"H{i:02d}" for i in range(29)]
        tickers = held + [f"N{i:02d}" for i in range(20)]

        kept = capped_tickers(tickers, held=set(held), min_new=8)

        assert len(kept) <= max(30, len(held))
        assert len(kept) == 30
        assert set(held).issubset(set(kept))

    def test_explore_floor_is_clamped_not_expanding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dispersion-regime explore floor above the budget must not widen the cap."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        kept = capped_tickers([f"T{i}" for i in range(10)], held=(), min_new=8)
        assert len(kept) == 4

    def test_book_wider_than_cap_keeps_book_and_nothing_else(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#936 still wins, but by exactly the width of the book — no bonus slots.

        Pre-#1767 this returned 4 (3 held + 1 reserved new candidate) under a cap of 3.
        """
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        held = {"SPY", "IJR", "XLP"}
        kept = capped_tickers(["SPY", "IJR", "XLP", "NEW1", "NEW2"], held=held, min_new=1)
        assert kept == ["SPY", "IJR", "XLP"]

    def test_uncapped_and_under_cap_paths_untouched(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "0")
        assert capped_tickers(["A", "B", "C"], held={"A"}) == ["A", "B", "C"]
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "5")
        assert capped_tickers(["A", "B", "C"], held={"A"}) == ["A", "B", "C"]

    def test_malformed_env_is_treated_as_no_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "thirty")
        assert configured_max_analysts() == 0
        assert capped_tickers(["A", "B", "C"], held=()) == ["A", "B", "C"]


@pytest.mark.unit
class TestThesisPrioritisation:
    def test_priority_order_is_round_robin_across_theses(self) -> None:
        mappings = [
            ("T1", "A1", ""),
            ("T1", "A2", ""),
            ("T1", "A3", ""),
            ("T2", "B1", ""),
            ("T2", "B2", ""),
            ("T3", "C1", ""),
        ]
        assert thesis_priority_order(mappings) == ["A1", "B1", "C1", "A2", "B2", "A3"]

    def test_priority_order_dedupes_and_normalizes(self) -> None:
        mappings = [("T1", " a1 ", ""), ("T2", "A1", ""), ("T2", "b1", ""), ("T3", "", "")]
        assert thesis_priority_order(mappings) == ["A1", "B1"]

    def test_priority_order_empty(self) -> None:
        assert thesis_priority_order([]) == []

    def test_tight_budget_spreads_across_theses_rather_than_deepening_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Breadth-first: 3 slots over 3 theses of 3 vehicles each → one per thesis.

        Flat truncation would spend all three on T0 and leave two theses uncovered.
        """
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        mappings = [
            (f"T{thesis}", f"V{thesis}{rank}", "") for thesis in range(3) for rank in range(3)
        ]
        watchlist = [ticker for _, ticker, _ in mappings]

        roster = compute_focus_roster(
            watchlist=watchlist,
            held=set(),
            thesis_mappings=mappings,
            run_date=_RUN_DATE,
        )

        covered = {e.linked_market_thesis_id for e in roster}
        assert len(roster) == 3
        assert covered == {"T0", "T1", "T2"}

    def test_thesis_vehicles_outrank_technical_picks_within_the_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        roster = compute_focus_roster(
            watchlist=["TECH1", "TECH2", "GLD", "TLT"],
            held=set(),
            thesis_mappings=[("geo-gold", "GLD", "gold hedge"), ("rates", "TLT", "duration")],
            run_date=_RUN_DATE,
        )
        assert {e.ticker for e in roster} == {"GLD", "TLT"}

    def test_roster_order_still_follows_the_watchlist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Priority decides *which* candidates survive, never the dispatch order."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        watchlist = ["AAA", "GLD", "BBB", "TLT", "CCC"]
        roster = compute_focus_roster(
            watchlist=watchlist,
            held={"AAA"},
            thesis_mappings=[("geo-gold", "GLD", ""), ("rates", "TLT", "")],
            price_deltas={"AAA": 0.10},
            run_date=_RUN_DATE,
        )
        tickers = [e.ticker for e in roster]
        assert tickers == ["AAA", "GLD", "TLT"]
        assert tickers == sorted(tickers, key=watchlist.index)


@pytest.mark.unit
class TestCapDropsAreVisible:
    def test_dropped_thesis_vehicle_lands_in_the_excluded_ledger(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A vehicle the cap dropped must not be labelled "not thesis-mapped"."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "1")
        mappings = [("T1", "GLD", ""), ("T2", "TLT", "")]
        watchlist = ["GLD", "TLT"]

        roster = compute_focus_roster(
            watchlist=watchlist,
            held=set(),
            thesis_mappings=mappings,
            run_date=_RUN_DATE,
        )
        assert len(roster) == 1

        excluded = compute_focus_roster_excluded(
            watchlist,
            roster,
            held=set(),
            thesis_mapped={ticker for _, ticker, _ in mappings},
        )
        dropped = next(e for e in excluded if e.ticker == "TLT")
        assert "analyst cap" in dropped.reason
        assert "not thesis-mapped" not in dropped.reason

    def test_thesis_vehicle_absent_from_watchlist_still_gets_a_ledger_row(self) -> None:
        excluded = compute_focus_roster_excluded([], [], held=set(), thesis_mapped={"OFFLIST"})
        assert [e.ticker for e in excluded] == ["OFFLIST"]

    def test_ledger_signature_is_backward_compatible(self) -> None:
        """Callers that pass no ``thesis_mapped`` keep the pre-#1767 wording."""
        excluded = compute_focus_roster_excluded(["QQQ"], [], held=set())
        assert excluded[0].reason == "not thesis-mapped and below technical screen"


@pytest.mark.unit
class TestRosterBreakdownContributor:
    """The width contributor for ``atlas_run_diagnostics.breakdown`` (#1767).

    Tested by direct call: the ``_BREAKDOWN_CONTRIBUTORS`` seam it plugs into is owned
    by PR #1774 and is not on ``develop``, so nothing registers it yet.
    """

    @staticmethod
    def _state(roster_len: int) -> object:
        from digiquant.research.state import (
            AtlasConfigBundle,
            ExcludedTicker,
            FocusRosterEntry,
            PhaseHermesState,
        )
        from digiquant.portfolio.state import HermesState

        state = HermesState(
            run_type="delta",
            run_date=_RUN_DATE,
            config=AtlasConfigBundle(watchlist=[]),
        )
        state.phase_hermes = PhaseHermesState(
            focus_roster=[
                FocusRosterEntry(
                    ticker=f"T{i}",
                    roster_reason="held" if i < 2 else "thesis_mapped",
                    linked_market_thesis_id=None if i < 2 else f"TH{i}",
                )
                for i in range(roster_len)
            ],
            focus_roster_excluded=[ExcludedTicker(ticker="X1", reason="capped")],
        )
        return state

    def test_breakdown_reports_width_by_reason_and_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.portfolio.roster_diagnostics import roster_breakdown

        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "30")
        payload = roster_breakdown(self._state(5))["roster"]
        assert payload == {
            "width": 5,
            "by_reason": {"held": 2, "thesis_mapped": 3},
            "theses_covered": 3,
            "excluded": 1,
            "max_analysts": 30,
            "over_cap": False,
        }

    def test_breakdown_flags_a_breach(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digiquant.portfolio.roster_diagnostics import roster_breakdown

        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        assert roster_breakdown(self._state(5))["roster"]["over_cap"] is True

    def test_breakdown_never_flags_a_breach_without_a_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.portfolio.roster_diagnostics import roster_breakdown

        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "0")
        payload = roster_breakdown(self._state(5))["roster"]
        assert payload["max_analysts"] == 0
        assert payload["over_cap"] is False

    def test_breakdown_tolerates_a_stateless_object(self) -> None:
        """Contributors run on the run-summary path and must never raise."""
        from digiquant.portfolio.roster_diagnostics import roster_breakdown

        payload = roster_breakdown(object())["roster"]  # type: ignore[arg-type]
        assert payload["width"] == 0
        assert payload["by_reason"] == {}
