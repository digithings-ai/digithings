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
        """With the staleness gate disabled, every held name must appear in the roster."""
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "4")
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
        roster = compute_focus_roster(
            watchlist=list(_BOOK),
            held=_HELD,
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert _HELD.issubset(tickers), f"held dropped from H4 roster: {_HELD - tickers}"

    def test_held_entries_tagged_held(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
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
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
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

    def test_held_ticker_not_in_watchlist_still_in_roster(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """IJR is held but NOT in the watchlist — must still appear in roster."""
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
        roster = compute_focus_roster(
            watchlist=["AAA", "BBB", "CCC"],
            held={"IJR"},
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert "IJR" in tickers, "held ticker absent from watchlist was dropped"

    def test_held_ticker_absent_from_slate_tagged_held(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Held ticker injected into roster must carry roster_reason='held'."""
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
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
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
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
        monkeypatch.setenv("HERMES_HELD_GATE", "off")
        roster = compute_focus_roster(
            watchlist=["SPY", "IJR", "XLP", "NEW1"],
            held={"SPY", "IJR", "XLP"},
            run_date=date(2026, 6, 20),
        )
        tickers = {e.ticker for e in roster}
        assert {"SPY", "IJR", "XLP"}.issubset(tickers)


@pytest.mark.unit
def test_held_ticker_also_thesis_mapped_keeps_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    roster = compute_focus_roster(
        watchlist=["XLE", "SPY"],
        held={"XLE"},
        thesis_mappings=[("T-OIL", "XLE", "oil supply squeeze")],
        run_date=date(2026, 6, 20),
    )
    xle = next(e for e in roster if e.ticker == "XLE")
    assert xle.roster_reason == "held"
    assert xle.linked_market_thesis_id == "T-OIL"  # link no longer lost
    assert xle.rationale  # non-empty


@pytest.mark.unit
def test_technical_entry_carries_rationale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    roster = compute_focus_roster(
        watchlist=["QQQ"],
        held=set(),
        thesis_mappings=[],
        run_date=date(2026, 6, 20),
    )
    qqq = next((e for e in roster if e.ticker == "QQQ"), None)
    if qqq is not None and qqq.roster_reason == "technical":
        assert qqq.rationale  # non-empty, honest "technical screen" reason


@pytest.mark.unit
def test_excluded_ticker_and_state_slot() -> None:
    from digiquant.olympus.atlas.state import ExcludedTicker, PhaseHermesState

    e = ExcludedTicker(ticker="TLT", reason="held, no material change (Δ<0.5%)")
    assert e.ticker == "TLT" and e.reason
    assert PhaseHermesState().focus_roster_excluded == []


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


# ---------------------------------------------------------------------------
# Stage 1b Task 2: held staleness/delta dispatch gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_held_gate_drops_stale_unlinked_held(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    monkeypatch.setenv("HERMES_HELD_STALENESS_DELTA", "0.005")
    roster = compute_focus_roster(
        watchlist=["TLT", "XLE"],
        held={"TLT", "XLE"},
        thesis_mappings=[("T-OIL", "XLE", "oil")],
        price_deltas={"TLT": 0.001, "XLE": 0.0},  # both quiet; XLE thesis-linked
        run_date=date(2026, 6, 20),
    )
    tickers = {e.ticker for e in roster}
    assert "TLT" not in tickers  # stale + unlinked → gated out
    assert "XLE" in tickers  # thesis-linked → kept despite quiet


@pytest.mark.unit
def test_held_gate_keeps_material_move(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HELD_STALENESS_DELTA", "0.005")
    roster = compute_focus_roster(
        watchlist=["TLT"],
        held={"TLT"},
        price_deltas={"TLT": 0.02},
        run_date=date(2026, 6, 20),
    )
    assert "TLT" in {e.ticker for e in roster}  # 2% move >= 0.5% → kept


@pytest.mark.unit
def test_held_gate_off_keeps_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    roster = compute_focus_roster(
        watchlist=["TLT"],
        held={"TLT"},
        price_deltas={"TLT": 0.0},
        run_date=date(2026, 6, 20),
    )
    assert "TLT" in {e.ticker for e in roster}  # kill-switch → always-analyze


# ---------------------------------------------------------------------------
# Stage 1b Task 3: populate + emit the excluded ledger in the H4 node
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_focus_roster_excluded_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    """Watchlist of 3: 1 rostered, 1 gated-out held, 1 below-screen (client returns empty).

    ``compute_focus_roster_excluded`` must return exactly 2 ExcludedTicker
    entries (the non-rostered ones) with non-empty reasons.  The rostered
    ticker must be absent from the ledger.
    """
    from digiquant.olympus.atlas.state import ExcludedTicker
    from digiquant.olympus.hermes.phases.h4_opportunity_screener import (
        compute_focus_roster_excluded,
    )
    from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

    monkeypatch.setenv("HERMES_HELD_STALENESS_DELTA", "0.005")
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")

    # A stub client that selects nothing — QQQ stays below-screen.
    def _stub_select(*, client: object, watchlist: list[str], **kwargs: object) -> list[str]:
        return []

    monkeypatch.setattr(
        "digiquant.olympus.hermes.phases.h4_opportunity_screener.select_focus_tickers",
        _stub_select,
    )

    # Build the roster: SPY is thesis-mapped → rostered; TLT is gated-out held
    # (quiet, no thesis link); QQQ fails the technical screen → excluded.
    watchlist = ["SPY", "TLT", "QQQ"]
    held = {"TLT"}

    roster = compute_focus_roster(
        watchlist=watchlist,
        held=held,
        thesis_mappings=[("T-US", "SPY", "US equity core")],
        price_deltas={"TLT": 0.001},  # below 0.5% threshold → gated out
        run_date=date(2026, 6, 20),
        client=FakeSupabaseClient(),
    )

    rostered_tickers = {e.ticker for e in roster}
    assert "SPY" in rostered_tickers, "thesis-mapped SPY must survive"
    assert "TLT" not in rostered_tickers, "gated-out held TLT must be excluded"
    assert "QQQ" not in rostered_tickers, "below-screen QQQ must be excluded"

    excluded = compute_focus_roster_excluded(watchlist, roster, held=held)

    assert isinstance(excluded, list)
    assert all(isinstance(e, ExcludedTicker) for e in excluded)

    excluded_tickers = {e.ticker for e in excluded}
    assert "SPY" not in excluded_tickers, "rostered ticker must not appear in excluded ledger"
    assert "TLT" in excluded_tickers, "gated-out held must appear in excluded ledger"
    assert "QQQ" in excluded_tickers, "below-screen ticker must appear in excluded ledger"

    # Every excluded entry must carry a non-empty human-readable reason.
    for entry in excluded:
        assert entry.reason, f"empty reason for {entry.ticker}"

    # Reason for gated-out held must hint at the held+staleness cause.
    tlt_entry = next(e for e in excluded if e.ticker == "TLT")
    assert "held" in tlt_entry.reason.lower() or "material" in tlt_entry.reason.lower()
