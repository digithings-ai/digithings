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
        mappings = [("geo-gold", "GLD"), ("rates", "TLT")]
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
            thesis_mappings=[("geo-gold", "GLD")],
            run_date=date(2026, 6, 20),
        )
        gld = next(e for e in roster if e.ticker == "GLD")
        assert gld.roster_reason == "thesis_mapped"
        assert gld.linked_market_thesis_id == "geo-gold"

    def test_held_over_cap_keeps_all_held(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        with caplog.at_level("WARNING"):
            roster = compute_focus_roster(
                watchlist=list(_BOOK),
                held=_HELD,
                run_date=date(2026, 6, 20),
            )
        tickers = [e.ticker for e in roster]
        assert set(tickers) == _HELD
        assert any(r.levelname == "WARNING" for r in caplog.records)

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
