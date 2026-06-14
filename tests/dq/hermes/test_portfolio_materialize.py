"""Unit tests for Phase 9D paper-portfolio materialization (#700).

Reads (prior positions / nav / price_history) come from the fake's
``canned_reads``; this run's writes land in ``store`` — so prior-state and
this-run output are cleanly separable.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.portfolio_materialize import (
    MaterializeDeps,
    build_materialize_node,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)


def _state(recommended) -> AtlasResearchState:
    state = AtlasResearchState(run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 9))
    state.phase7d_rebalance = {"recommended_portfolio": recommended, "actions": [], "notes": ""}
    return state


def _run(client: FakeSupabaseClient, recommended) -> None:
    build_materialize_node(MaterializeDeps(client=client))(_state(recommended))


class TestFreshSeed:
    def test_first_run_seeds_nav_100_and_writes_positions(self) -> None:
        client = FakeSupabaseClient()  # no prior positions / nav
        _run(client, [{"ticker": "SPY", "target_pct": 60}, {"ticker": "TLT", "target_pct": 40}])

        navs = client.store["nav_history"]
        assert len(navs) == 1
        assert navs[0]["nav"] == 100.0
        assert navs[0]["date"] == "2026-06-12"
        assert navs[0]["invested_pct"] == 100.0
        assert navs[0]["_on_conflict"] == "date"

        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert positions["SPY"]["weight_pct"] == 60.0
        assert positions["TLT"]["weight_pct"] == 40.0
        assert all(r["_on_conflict"] == "date,ticker" for r in client.store["positions"])

    def test_duplicate_tickers_coalesced(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [{"ticker": "SPY", "target_pct": 30}, {"ticker": "SPY", "target_pct": 30}])
        spy = [r for r in client.store["positions"] if r["ticker"] == "SPY"]
        assert len(spy) == 1  # one (date,ticker) row, not two
        assert spy[0]["weight_pct"] == 60.0
        assert client.store["nav_history"][0]["cash_pct"] == 40.0

    def test_overweight_book_scaled_to_fully_invested(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [{"ticker": "SPY", "target_pct": 90}, {"ticker": "QQQ", "target_pct": 60}])
        positions = {r["ticker"]: r["weight_pct"] for r in client.store["positions"]}
        # 90/60 (gross 150) scaled to sum 100, proportions preserved (3:2).
        assert positions["SPY"] == pytest.approx(60.0, abs=1e-3)
        assert positions["QQQ"] == pytest.approx(40.0, abs=1e-3)
        assert "CASH" not in positions
        assert client.store["nav_history"][0]["cash_pct"] == 0.0

    def test_no_position_reset_when_prior_book_pruned_but_nav_persists(self) -> None:
        # nav_history has a prior value but positions were pruned — carry the
        # index forward flat, do not reset to 100 (Copilot review #701).
        client = FakeSupabaseClient(
            canned_reads={"positions": [], "nav_history": [{"date": "2026-06-11", "nav": 142.0}]}
        )
        _run(client, [{"ticker": "SPY", "target_pct": 100}])
        assert client.store["nav_history"][0]["nav"] == pytest.approx(142.0, abs=1e-6)

    def test_cash_residual_row_written(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [{"ticker": "SPY", "target_pct": 70}])

        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert positions["CASH"]["weight_pct"] == 30.0
        assert client.store["nav_history"][0]["cash_pct"] == 30.0


class TestNavChaining:
    def test_second_day_chains_return_from_prior_book(self) -> None:
        # Prior book held SPY 60 / TLT 40 at nav 100; SPY +2%, TLT -1% over the
        # latest trading-day pair. Expected return = .6*.02 + .4*(-.01) = .008.
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-11", "ticker": "SPY", "weight_pct": 60},
                    {"date": "2026-06-11", "ticker": "TLT", "weight_pct": 40},
                ],
                "nav_history": [{"date": "2026-06-11", "nav": 100.0}],
                "price_history": [
                    {"date": "2026-06-11", "ticker": "SPY", "close": 102.0},
                    {"date": "2026-06-10", "ticker": "SPY", "close": 100.0},
                    {"date": "2026-06-11", "ticker": "TLT", "close": 99.0},
                    {"date": "2026-06-10", "ticker": "TLT", "close": 100.0},
                ],
            }
        )
        _run(client, [{"ticker": "SPY", "target_pct": 50}, {"ticker": "TLT", "target_pct": 50}])

        nav = client.store["nav_history"][0]["nav"]
        assert nav == pytest.approx(100.8, abs=1e-6)
        # New book recorded at today's weights (not the prior 60/40).
        positions = {r["ticker"]: r["weight_pct"] for r in client.store["positions"]}
        assert positions["SPY"] == 50.0 and positions["TLT"] == 50.0

    def test_missing_price_delta_treated_as_zero_return(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [{"date": "2026-06-11", "ticker": "SPY", "weight_pct": 100}],
                "nav_history": [{"date": "2026-06-11", "nav": 137.5}],
                "price_history": [],  # no price rows → no delta → flat
            }
        )
        _run(client, [{"ticker": "SPY", "target_pct": 100}])
        assert client.store["nav_history"][0]["nav"] == pytest.approx(137.5, abs=1e-6)


class TestGuards:
    def test_no_rebalance_is_noop(self) -> None:
        client = FakeSupabaseClient()
        state = AtlasResearchState(run_type="delta", run_date=RUN_DATE)
        # phase7d_rebalance left None
        build_materialize_node(MaterializeDeps(client=client))(state)
        assert "positions" not in client.store
        assert "nav_history" not in client.store

    def test_empty_recommended_books_full_cash(self) -> None:
        # The PM ran and chose to hold cash (empty book) → materialize a 100% CASH
        # book, not a no-op. CASH is a first-class position (#713).
        client = FakeSupabaseClient()
        _run(client, [])
        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert set(positions) == {"CASH"}
        assert positions["CASH"]["weight_pct"] == 100.0
        nav = client.store["nav_history"][0]
        assert nav["cash_pct"] == 100.0 and nav["invested_pct"] == 0.0
        assert nav["nav"] == 100.0  # first run seeds the index at 100

    def test_all_cash_or_zero_weights_books_full_cash(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [{"ticker": "CASH", "target_pct": 100}, {"ticker": "SPY", "target_pct": 0}])
        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert set(positions) == {"CASH"} and positions["CASH"]["weight_pct"] == 100.0
        assert client.store["nav_history"][0]["cash_pct"] == 100.0

    def test_rerun_same_date_is_idempotent_upsert(self) -> None:
        client = FakeSupabaseClient()
        rec = [{"ticker": "SPY", "target_pct": 100}]
        _run(client, rec)
        _run(client, rec)
        # Both runs upsert on the same (date,ticker)/date keys — the on_conflict
        # contract makes the DB collapse them; the fake appends, so we just
        # assert every write declares the idempotency key.
        assert all(r["_on_conflict"] == "date" for r in client.store["nav_history"])
        assert all(r["_on_conflict"] == "date,ticker" for r in client.store["positions"])


def _state_with_analysts(recommended, analysts, debates=None) -> AtlasResearchState:
    state = _state(recommended)
    state.phase7c_analysts = analysts
    state.phase7cd_debates = debates or {}
    return state


def _run_full(client, recommended, analysts, debates=None) -> None:
    build_materialize_node(MaterializeDeps(client=client))(
        _state_with_analysts(recommended, analysts, debates)
    )


class TestThesesWrite:
    def test_one_thesis_per_booked_position(self) -> None:
        client = FakeSupabaseClient()
        _run_full(
            client,
            [{"ticker": "SPY", "target_pct": 60}, {"ticker": "TLT", "target_pct": 40}],
            {
                "SPY": {
                    "ticker": "SPY",
                    "stance": "buy",
                    "thesis": "AI capex tailwind",
                    "risks": "valuation",
                },
                "TLT": {
                    "ticker": "TLT",
                    "stance": "hold",
                    "thesis": "duration hedge",
                    "risks": "fiscal supply",
                },
            },
        )
        theses = {r["thesis_id"]: r for r in client.store["theses"]}
        assert set(theses) == {"spy", "tlt"}
        assert theses["spy"]["vehicle"] == "SPY"
        assert theses["spy"]["status"] == "ACTIVE"
        assert "AI capex" in theses["spy"]["notes"]
        assert all(r["_on_conflict"] == "date,thesis_id" for r in client.store["theses"])

    def test_thesis_vehicle_written_per_position(self) -> None:
        client = FakeSupabaseClient()
        _run_full(
            client,
            [{"ticker": "SPY", "target_pct": 100}],
            {"SPY": {"ticker": "SPY", "stance": "buy", "thesis": "t"}},
        )
        vehicles = client.store["thesis_vehicles"]
        assert len(vehicles) == 1
        assert vehicles[0]["thesis_id"] == "spy" and vehicles[0]["ticker"] == "SPY"
        assert vehicles[0]["_on_conflict"] == "date,thesis_id,ticker"

    def test_status_maps_from_stance(self) -> None:
        client = FakeSupabaseClient()
        _run_full(
            client,
            [
                {"ticker": "AAA", "target_pct": 25},
                {"ticker": "BBB", "target_pct": 25},
                {"ticker": "CCC", "target_pct": 25},
                {"ticker": "DDD", "target_pct": 25},
            ],
            {
                "AAA": {"ticker": "AAA", "stance": "buy", "thesis": "x"},
                "BBB": {"ticker": "BBB", "stance": "watch", "thesis": "x"},
                "CCC": {"ticker": "CCC", "stance": "sell", "thesis": "x"},
                "DDD": {"ticker": "DDD", "stance": "hold", "thesis": "x"},
            },
        )
        status = {r["thesis_id"]: r["status"] for r in client.store["theses"]}
        assert status == {
            "aaa": "ACTIVE",
            "bbb": "MONITORING",
            "ccc": "CHALLENGED",
            "ddd": "ACTIVE",
        }

    def test_invalidation_from_debate_bear_case(self) -> None:
        client = FakeSupabaseClient()
        _run_full(
            client,
            [{"ticker": "SPY", "target_pct": 100}],
            {"SPY": {"ticker": "SPY", "stance": "buy", "thesis": "t", "risks": "fallback risk"}},
            {"SPY": {"bear_case": "breaks below 200dma"}},
        )
        spy = next(r for r in client.store["theses"] if r["thesis_id"] == "spy")
        assert spy["invalidation"] == "breaks below 200dma"

    def test_holding_without_analyst_defaults_active(self) -> None:
        # A held ticker with no analyst payload (e.g. a BIL position the PM picked
        # explicitly on conviction) → status ACTIVE, name=ticker.
        client = FakeSupabaseClient()
        _run_full(client, [{"ticker": "BIL", "target_pct": 100}], {})
        bil = next(r for r in client.store["theses"] if r["thesis_id"] == "bil")
        assert bil["status"] == "ACTIVE"
        assert bil["name"] == "BIL"

    def test_no_thesis_for_cash_residual(self) -> None:
        client = FakeSupabaseClient()
        _run_full(
            client,
            [{"ticker": "SPY", "target_pct": 70}],  # 30% CASH residual
            {"SPY": {"ticker": "SPY", "stance": "buy", "thesis": "t"}},
        )
        ids = {r["thesis_id"] for r in client.store["theses"]}
        assert ids == {"spy"}  # CASH residual produces no thesis row

    def test_empty_portfolio_writes_no_theses(self) -> None:
        client = FakeSupabaseClient()
        _run_full(client, [], {"SPY": {"ticker": "SPY", "stance": "buy", "thesis": "t"}})
        assert "theses" not in client.store
