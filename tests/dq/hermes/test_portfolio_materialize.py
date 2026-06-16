"""Unit tests for Phase 9D paper-portfolio materialization (#700).

Reads (prior positions / nav / price_history) come from the fake's
``canned_reads``; this run's writes land in ``store`` — so prior-state and
this-run output are cleanly separable.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState
from digiquant.olympus.hermes.portfolio_materialize import (
    MaterializeDeps,
    build_materialize_node,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)

# Mirrors the chk_positions_category CHECK constraint (migration 002_schema_hardening.sql).
# The FakeSupabaseClient does not enforce CHECK constraints, so we assert against this set
# explicitly — a category outside it (e.g. a bare "cash") is rejected by Postgres and blocks
# the positions write (#772).
_POSITIONS_CATEGORY_ALLOWED = frozenset(
    {
        "commodity_gold",
        "commodity_oil",
        "commodity_broad",
        "equity_sector",
        "equity_broad",
        "equity_international",
        "fixed_income_cash",
        "fixed_income_short",
        "fixed_income_long",
        "crypto",
        "forex",
        "other",
    }
)


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
        # Regression (#772): the cash row's category must satisfy chk_positions_category —
        # a bare "cash" is rejected by Postgres and blocks the positions write.
        assert positions["CASH"]["category"] == "fixed_income_cash"
        assert positions["CASH"]["category"] in _POSITIONS_CATEGORY_ALLOWED


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


@pytest.mark.unit
class TestPositionRiskFields:
    """Pillar 2E — advisory per-position risk fields, gated by OLYMPUS_POSITION_RISK_FIELDS
    (off → exact prior book shape; on → entry/stop/target/conviction/sector/horizon)."""

    def _state(self, recommended, *, analysts=None, debates=None, preferences=None):
        state = AtlasResearchState(
            run_type="delta",
            run_date=RUN_DATE,
            baseline_date=date(2026, 6, 9),
            config=AtlasConfigBundle(preferences=preferences or {}),
        )
        state.phase7d_rebalance = {"recommended_portfolio": recommended, "actions": [], "notes": ""}
        state.phase7c_analysts = analysts or {}
        state.phase7cd_debates = debates or {}
        return state

    def _book(self, client: FakeSupabaseClient) -> dict:
        return {r["ticker"]: r for r in client.store["positions"]}

    def test_off_by_default_writes_no_new_fields(self, monkeypatch) -> None:
        monkeypatch.delenv("OLYMPUS_POSITION_RISK_FIELDS", raising=False)
        client = FakeSupabaseClient()
        build_materialize_node(MaterializeDeps(client=client))(
            self._state([{"ticker": "SPY", "target_pct": 50}])
        )
        spy = self._book(client)["SPY"]
        for f in ("entry_price", "entry_date", "conviction", "sector_bucket", "stop_loss_pct"):
            assert f not in spy

    def test_on_enriches_first_open(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "AAPL", "close": 200.0}],
                "price_technicals": [{"date": "2026-06-11", "ticker": "AAPL", "atr_pct": 2.0}],
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "AAPL", "target_pct": 40}],
                analysts={"AAPL": {"conviction_score": 4, "stance": "buy"}},
                debates={"AAPL": {"conviction_delta": 1}},
                preferences={"holding_days": 30},
            )
        )
        aapl = self._book(client)["AAPL"]
        assert aapl["entry_price"] == 200.0  # seeded at today's close (first open)
        assert aapl["entry_date"] == "2026-06-12"
        assert aapl["conviction"] == 5.0  # 4 + 1
        assert aapl["sector_bucket"] == "sector-technology"
        assert aapl["horizon_days"] == 30
        assert aapl["stop_loss_pct"] == -4.0  # -2 × atr_pct
        assert aapl["target_pct_gain"] == 6.0  # 3 × atr_pct

    def test_on_carries_entry_forward_on_hold(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {
                        "date": "2026-06-11",
                        "ticker": "AAPL",
                        "weight_pct": 40,
                        "entry_price": 150.0,
                        "entry_date": "2026-06-01",
                    }
                ],
                "price_history": [{"date": "2026-06-11", "ticker": "AAPL", "close": 200.0}],
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "AAPL", "target_pct": 40}],
                analysts={"AAPL": {"conviction_score": 4}},
            )
        )
        aapl = self._book(client)["AAPL"]
        assert aapl["entry_price"] == 150.0  # carried, NOT reset to today's 200 close
        assert aapl["entry_date"] == "2026-06-01"
        assert aapl["horizon_days"] == 21  # default when preferences omit holding_days

    def test_on_without_atr_skips_stop_target(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "AAPL", "close": 200.0}],
                "price_technicals": [],
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "AAPL", "target_pct": 40}], analysts={"AAPL": {"conviction_score": 4}}
            )
        )
        aapl = self._book(client)["AAPL"]
        assert "stop_loss_pct" not in aapl and "target_pct_gain" not in aapl
        assert aapl["entry_price"] == 200.0  # entry still seeded

    def test_on_without_analyst_skips_conviction(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={"price_history": [{"date": "2026-06-11", "ticker": "GLD", "close": 50.0}]}
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state([{"ticker": "GLD", "target_pct": 40}])  # no analyst payload
        )
        gld = self._book(client)["GLD"]
        assert "conviction" not in gld
        assert gld["sector_bucket"] == "commodity"  # GLD → commodity (asset_classes.yaml)

    def test_cash_row_is_never_enriched(self, monkeypatch) -> None:
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "SPY", "close": 400.0}]
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "SPY", "target_pct": 60}], analysts={"SPY": {"conviction_score": 3}}
            )
        )
        cash = self._book(client)["CASH"]
        for f in ("entry_price", "conviction", "sector_bucket", "stop_loss_pct"):
            assert f not in cash

    def test_negative_horizon_defaults_to_21(self, monkeypatch) -> None:
        # A nonsensical negative holding_days must not persist — fall back to the default.
        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "SPY", "close": 400.0}]
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "SPY", "target_pct": 50}],
                analysts={"SPY": {"conviction_score": 3}},
                preferences={"holding_days": -5},
            )
        )
        assert self._book(client)["SPY"]["horizon_days"] == 21

    def test_enrichment_failure_books_plain_weights(self, monkeypatch) -> None:
        # An enrichment error (e.g. malformed asset_classes.yaml → sector_bucket raises) must
        # never block the book: it degrades to plain {date,ticker,weight_pct} rows.
        import digiquant.olympus.hermes.portfolio_materialize as pm

        def _boom(*_a, **_k):
            raise RuntimeError("asset_classes.yaml parse error")

        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        monkeypatch.setattr(pm, "sector_bucket", _boom)
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "SPY", "close": 400.0}]
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state(
                [{"ticker": "SPY", "target_pct": 50}], analysts={"SPY": {"conviction_score": 3}}
            )
        )
        spy = self._book(client)["SPY"]
        assert spy["weight_pct"] == 50.0  # book still materialized
        for f in ("entry_price", "conviction", "sector_bucket", "stop_loss_pct"):
            assert f not in spy  # partial enrichment stripped after the failure
