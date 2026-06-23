"""H4 opportunity screener — focus roster held invariant (#936)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import FocusRosterEntry
from digiquant.olympus.hermes.phases.h4_opportunity_screener import compute_focus_roster

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


_BOOK = ["AAA", "BBB", "SPY", "CCC", "IJR", "DDD", "XLP"]
_HELD = {"SPY", "IJR", "XLP"}


@pytest.mark.unit
class TestH4FocusRosterHeldInvariant:
    def test_held_always_in_roster(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held=_HELD,
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert _HELD.issubset(tickers), f"held dropped from H4 roster: {_HELD - tickers}"

    def test_held_entries_tagged_held(self) -> None:
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held=_HELD,
            run_date=date(2026, 6, 20),
        )
        held_entries = [e for e in roster if e.ticker in _HELD]
        assert len(held_entries) == len(_HELD)
        assert all(e.roster_reason == "held" for e in held_entries)

    def test_thesis_mapped_never_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        mappings = [("geo-gold", "GLD", "gold hedge"), ("rates", "TLT", "duration play")]
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held=set(),
            thesis_mappings=mappings,
            run_date=date(2026, 6, 20),
        )
        mapped = {e.ticker for e in roster if e.roster_reason == "thesis_mapped"}
        assert {"GLD", "TLT"}.issubset(mapped)

    def test_thesis_mapped_carries_linked_id(self) -> None:
        roster = compute_focus_roster(
            watchlist=["SPY", "GLD"],
            held=set(),
            thesis_mappings=[("geo-gold", "GLD", "gold hedge")],
            run_date=date(2026, 6, 20),
        )
        gld = next(e for e in roster if e.ticker == "GLD")
        assert gld.roster_reason == "thesis_mapped"
        assert gld.linked_market_thesis_id == "geo-gold"

    def test_held_over_cap_keeps_all_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held=_HELD,
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        # All held survive even though they exceed the cap (#936).
        assert _HELD.issubset(tickers)
        # At least 1 new candidate is also reserved (#950).
        non_held = [e for e in roster if e.roster_reason != "held"]
        assert len(non_held) >= 1

    def test_roster_preserves_watchlist_order_among_survivors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held={"SPY", "CCC"},
            run_date=date(2026, 6, 20),
        )
        tickers = [e.ticker for e in roster]
        assert tickers == sorted(tickers, key=_BOOK.index)


@pytest.mark.unit
def test_focus_roster_entry_model() -> None:
    entry = FocusRosterEntry(ticker="SPY", roster_reason="held")
    assert entry.linked_market_thesis_id is None


@pytest.mark.unit
def test_compute_focus_roster_passes_client_to_technical_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H4 technical picks forward the Supabase client to select_focus_tickers."""
    client = FakeSupabaseClient()
    seen: dict[str, object] = {}

    def stub_select(*, client: object, watchlist: list[str], **kwargs: object) -> list[str]:
        seen["client"] = client
        seen["watchlist"] = watchlist
        return watchlist[:1]

    monkeypatch.setattr(
        "digiquant.olympus.hermes.phases.h4_opportunity_screener.select_focus_tickers",
        stub_select,
    )
    roster = compute_focus_roster(
        watchlist=["AAA", "BBB", "CCC"],
        held=set(),
        run_date=date(2026, 6, 20),
        client=client,
    )
    assert seen["client"] is client
    assert len(roster) == 1


@pytest.mark.unit
class TestHeldAbsentFromSlate:
    """AC #3 (#950): a held name absent from the raw slate still appears."""

    def test_held_ticker_not_in_watchlist_still_in_roster(self) -> None:
        """IJR is held but NOT in the watchlist — must still appear in roster."""
        roster = compute_focus_roster(
            watchlist=["AAA", "BBB", "CCC"],
            held={"IJR"},
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert "IJR" in tickers, "held ticker absent from watchlist was dropped"

    def test_held_ticker_absent_from_slate_tagged_held(self) -> None:
        """Held ticker injected into roster must carry roster_reason='held'."""
        roster = compute_focus_roster(
            watchlist=["AAA", "BBB"],
            held={"XLF"},
            run_date=date(2026, 6, 20),
        )
        xlf = next((e for e in roster if e.ticker == "XLF"), None)
        assert xlf is not None, "XLF missing from roster"
        assert xlf.roster_reason == "held"


@pytest.mark.unit
def test_focus_roster_entry_has_rationale_default_empty() -> None:
    e = FocusRosterEntry(ticker="SPY", roster_reason="held")
    assert e.rationale == ""
    e2 = FocusRosterEntry(
        ticker="XLE",
        roster_reason="thesis_mapped",
        linked_market_thesis_id="T1",
        rationale="energy thesis",
    )
    assert e2.rationale == "energy thesis"


@pytest.mark.unit
class TestNewCandidateReservation:
    """AC #2 (#950): reserve >=1 roster slot for non-held new candidates."""

    def test_new_candidate_survives_tight_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Cap=4, 3 held — at least 1 non-held technical candidate must survive."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        roster = compute_focus_roster(
            watchlist=["SPY", "IJR", "XLP", "AAA", "BBB", "CCC"],
            held={"SPY", "IJR", "XLP"},
            run_date=date(2026, 6, 20),
        )
        non_held = [e for e in roster if e.roster_reason != "held"]
        assert len(non_held) >= 1, (
            f"no new candidates survived cap; roster={[e.ticker for e in roster]}"
        )

    def test_new_candidate_slot_reserved_when_held_fills_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cap=4, 4 held + 3 new candidates — cap should expand to fit >=1 new."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        roster = compute_focus_roster(
            watchlist=["H1", "H2", "H3", "H4", "NEW1", "NEW2", "NEW3"],
            held={"H1", "H2", "H3", "H4"},
            run_date=date(2026, 6, 20),
        )
        non_held = [e for e in roster if e.roster_reason != "held"]
        assert len(non_held) >= 1, (
            f"new candidates squeezed out; roster={[e.ticker for e in roster]}"
        )

    def test_no_new_candidates_available_does_not_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cap=3, 3 held, 0 non-held watchlist — held-only roster is fine."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "3")
        roster = compute_focus_roster(
            watchlist=["SPY", "IJR", "XLP"],
            held={"SPY", "IJR", "XLP"},
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert tickers == {"SPY", "IJR", "XLP"}

    def test_held_exceeds_cap_no_room_for_new_keeps_all_held(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cap=2, 3 held, new candidates exist — held must not be dropped.

        When held alone exceed the cap the roster goes over-budget (#936)
        and no new candidates can be reserved; that is acceptable.
        """
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        roster = compute_focus_roster(
            watchlist=["SPY", "IJR", "XLP", "NEW1"],
            held={"SPY", "IJR", "XLP"},
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert {"SPY", "IJR", "XLP"}.issubset(tickers)


@pytest.mark.unit
def test_extract_thesis_mappings_carries_rationale() -> None:
    from digiquant.olympus.hermes.phases.h4_opportunity_screener import extract_thesis_mappings

    vmap = {
        "body": {
            "mappings": [
                {
                    "thesis_id": "T1",
                    "candidate_tickers": ["XLE", "USO"],
                    "rationale": "oil supply squeeze",
                },
            ]
        }
    }
    out = extract_thesis_mappings(vmap)
    assert ("T1", "XLE", "oil supply squeeze") in out
    assert ("T1", "USO", "oil supply squeeze") in out
