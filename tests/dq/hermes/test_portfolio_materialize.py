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

    def test_empty_recommended_is_noop(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [])
        assert "positions" not in client.store

    def test_all_cash_or_zero_weights_is_noop(self) -> None:
        client = FakeSupabaseClient()
        _run(client, [{"ticker": "CASH", "target_pct": 100}, {"ticker": "SPY", "target_pct": 0}])
        assert "positions" not in client.store
        assert "nav_history" not in client.store

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
