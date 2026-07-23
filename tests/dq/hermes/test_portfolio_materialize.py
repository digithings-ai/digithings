"""Unit tests for Phase 9D paper-portfolio materialization (#700).

Reads (prior positions / nav / price_history) come from the fake's
``canned_reads``; this run's writes land in ``store`` — so prior-state and
this-run output are cleanly separable.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.portfolio_materialize import (
    MaterializeDeps,
    _default_invalidation,
    _upsert_portfolio_metrics,
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
    state.phase_hermes = PhaseHermesState(
        asset_analysts=analysts,
        deliberation_summaries=debates or {},
    )
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
                },
                "TLT": {
                    "ticker": "TLT",
                    "stance": "hold",
                    "thesis": "duration hedge",
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
            {"SPY": {"ticker": "SPY", "stance": "buy", "thesis": "t"}},
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
        state.phase_hermes = PhaseHermesState(
            asset_analysts=analysts or {},
            deliberation_summaries=debates or {},
        )
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
                preferences={"holding_days": 5, "risk_horizon_days": 30},
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
        assert aapl["horizon_days"] == 21  # decision holding_days does not set risk horizon

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
        # A nonsensical negative risk horizon must not persist — fall back to the default.
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
                preferences={"risk_horizon_days": -5},
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

    def test_enrichment_failure_preserves_thesis_id(self, monkeypatch) -> None:
        # thesis_id is set before enrichment; enrichment failure must not strip it (#814).
        import digiquant.olympus.hermes.portfolio_materialize as pm

        def _boom(*_a, **_k):
            raise RuntimeError("enrichment error")

        monkeypatch.setenv("OLYMPUS_POSITION_RISK_FIELDS", "1")
        monkeypatch.setattr(pm, "sector_bucket", _boom)
        client = FakeSupabaseClient(
            canned_reads={
                "price_history": [{"date": "2026-06-11", "ticker": "SPY", "close": 400.0}]
            }
        )
        build_materialize_node(MaterializeDeps(client=client))(
            self._state([{"ticker": "SPY", "target_pct": 50}])
        )
        spy = self._book(client)["SPY"]
        assert spy.get("thesis_id") == "spy"  # preserved through enrichment failure


@pytest.mark.unit
class TestBookIntegrity:
    """#814 — book-write integrity: thesis_id on positions, invalidation defaults."""

    def _run(self, client, recommended, analysts=None, debates=None) -> None:
        state = AtlasResearchState(
            run_type="delta", run_date=RUN_DATE, baseline_date=date(2026, 6, 9)
        )
        state.phase7d_rebalance = {"recommended_portfolio": recommended, "actions": [], "notes": ""}
        state.phase_hermes = PhaseHermesState(
            asset_analysts=analysts or {},
            deliberation_summaries=debates or {},
        )
        build_materialize_node(MaterializeDeps(client=client))(state)

    # ── Fix 1: thesis_id on positions ──────────────────────────────────────

    def test_non_cash_positions_have_thesis_id(self) -> None:
        client = FakeSupabaseClient()
        self._run(
            client, [{"ticker": "SPY", "target_pct": 60}, {"ticker": "IJR", "target_pct": 40}]
        )
        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert positions["SPY"]["thesis_id"] == "spy"
        assert positions["IJR"]["thesis_id"] == "ijr"

    def test_cash_residual_has_no_thesis_id(self) -> None:
        client = FakeSupabaseClient()
        self._run(client, [{"ticker": "SPY", "target_pct": 70}])
        positions = {r["ticker"]: r for r in client.store["positions"]}
        assert "thesis_id" not in positions["CASH"]

    def test_thesis_id_matches_lowercase_ticker(self) -> None:
        # thesis_id must be ticker.lower() to match the theses table FK (#814).
        client = FakeSupabaseClient()
        self._run(client, [{"ticker": "XLP", "target_pct": 100}])
        xlp = next(r for r in client.store["positions"] if r["ticker"] == "XLP")
        assert xlp["thesis_id"] == "xlp"

    # ── Fix 2: invalidation defaults for ACTIVE theses ─────────────────────

    def test_active_thesis_without_debate_gets_default_invalidation(self) -> None:
        # No debate data → _default_invalidation must fill a non-empty string (#814).
        client = FakeSupabaseClient()
        self._run(
            client,
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"stance": "buy", "thesis": "AI tailwind"}},
            debates={},  # no bear_case
        )
        spy = next(r for r in client.store["theses"] if r["thesis_id"] == "spy")
        assert spy["invalidation"]  # must be non-empty
        assert len(spy["invalidation"]) > 5

    def test_explicit_bear_case_not_overridden(self) -> None:
        # An existing bear_case must be preserved, not replaced by a default (#814).
        client = FakeSupabaseClient()
        self._run(
            client,
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"stance": "buy"}},
            debates={"SPY": {"bear_case": "breaks below 200dma"}},
        )
        spy = next(r for r in client.store["theses"] if r["thesis_id"] == "spy")
        assert spy["invalidation"] == "breaks below 200dma"

    def test_stop_loss_pct_used_in_default_invalidation(self) -> None:
        # When the analyst payload has stop_loss_pct, the default uses it (#814).
        client = FakeSupabaseClient()
        self._run(
            client,
            [{"ticker": "SPY", "target_pct": 100}],
            analysts={"SPY": {"stance": "buy", "stop_loss_pct": -5.0}},
            debates={},
        )
        spy = next(r for r in client.store["theses"] if r["thesis_id"] == "spy")
        assert "5.0%" in spy["invalidation"]

    def test_holding_with_no_analyst_gets_default_invalidation(self) -> None:
        # A held ticker with no analyst payload must still get a non-empty invalidation (#814).
        client = FakeSupabaseClient()
        self._run(client, [{"ticker": "BIL", "target_pct": 100}], analysts={})
        bil = next(r for r in client.store["theses"] if r["thesis_id"] == "bil")
        assert bil["invalidation"]  # non-empty, generated from _default_invalidation

    def test_monitoring_status_also_gets_default_invalidation(self) -> None:
        # MONITORING theses (stance=watch) must also have non-empty invalidation (#814).
        client = FakeSupabaseClient()
        self._run(
            client,
            [{"ticker": "TLT", "target_pct": 100}],
            analysts={"TLT": {"stance": "watch"}},
            debates={},
        )
        tlt = next(r for r in client.store["theses"] if r["thesis_id"] == "tlt")
        assert tlt["status"] == "MONITORING"
        assert tlt["invalidation"]


@pytest.mark.unit
class TestPortfolioMetricsWriter:
    """#953 — portfolio_metrics rows must compute sharpe/vol/drawdown/alpha
    from the nav_history series, not leave them NULL."""

    def test_metrics_computed_from_sufficient_nav_history(self) -> None:
        """With 25 NAV points the writer must populate sharpe, volatility,
        max_drawdown, and alpha (not NULL)."""
        # Build 25 daily NAV values: base 100 with small daily returns.
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.001**d), 6)} for d in range(1, 26)
        ]
        # SPY benchmark for alpha: same window, slightly different return.
        spy_rows = [
            {"date": f"2026-05-{d:02d}", "ticker": "SPY", "close": round(400.0 * (1.0005**d), 6)}
            for d in range(1, 26)
        ]
        client = FakeSupabaseClient(
            canned_reads={"nav_history": nav_rows, "price_history": spy_rows}
        )
        _upsert_portfolio_metrics(
            client=client,
            run_date=date(2026, 5, 25),
        )
        rows = client.store.get("portfolio_metrics", [])
        assert len(rows) == 1
        row = rows[0]
        assert row["date"] == "2026-05-25"
        assert row["pnl_pct"] is not None
        assert row["sharpe"] is not None
        assert row["volatility"] is not None
        assert row["max_drawdown"] is not None
        assert row["alpha"] is not None
        # Sanity: sharpe should be positive for a positive-return series
        assert row["sharpe"] > 0
        assert row["_on_conflict"] == "date"

    def test_metrics_null_when_insufficient_history(self) -> None:
        """With < 20 NAV points, risk metrics must be NULL (not 0)."""
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.001**d), 6)}
            for d in range(1, 6)  # only 5 rows
        ]
        client = FakeSupabaseClient(canned_reads={"nav_history": nav_rows})
        _upsert_portfolio_metrics(
            client=client,
            run_date=date(2026, 5, 5),
        )
        rows = client.store.get("portfolio_metrics", [])
        assert len(rows) == 1
        row = rows[0]
        assert row["sharpe"] is None
        assert row["volatility"] is None
        assert row["max_drawdown"] is None
        assert row["alpha"] is None
        assert row["net_return_pct"] is not None
        assert row["benchmark_return_pct"] is None
        assert row["relative_return_pct"] is None
        # pnl_pct should still be populated (day return)
        assert row["pnl_pct"] is not None

    def test_metrics_idempotent_upsert_on_date(self) -> None:
        """Re-running on the same date produces an upsert (on_conflict='date')."""
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.001**d), 6)} for d in range(1, 6)
        ]
        client = FakeSupabaseClient(canned_reads={"nav_history": nav_rows})
        _upsert_portfolio_metrics(client=client, run_date=date(2026, 5, 5))
        _upsert_portfolio_metrics(client=client, run_date=date(2026, 5, 5))
        for row in client.store["portfolio_metrics"]:
            assert row["_on_conflict"] == "date"

    def test_materialize_node_writes_portfolio_metrics(self) -> None:
        """The materialize node should call _upsert_portfolio_metrics after nav_history."""
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.001**d), 6)} for d in range(1, 26)
        ]
        spy_rows = [
            {"date": f"2026-05-{d:02d}", "ticker": "SPY", "close": round(400.0 * (1.0005**d), 6)}
            for d in range(1, 26)
        ]
        client = FakeSupabaseClient(
            canned_reads={"nav_history": nav_rows, "price_history": spy_rows}
        )
        state = _state([{"ticker": "SPY", "target_pct": 100}])
        state.run_date = date(2026, 5, 25)
        build_materialize_node(MaterializeDeps(client=client))(state)
        assert "portfolio_metrics" in client.store
        row = client.store["portfolio_metrics"][0]
        assert row["date"] == "2026-05-25"

    def test_alpha_positive_when_portfolio_beats_spy(self) -> None:
        """Alpha = portfolio return - benchmark (SPY) return; should be positive
        when portfolio outperforms."""
        # Portfolio grows 0.2%/day, SPY grows 0.05%/day
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.002**d), 6)} for d in range(1, 26)
        ]
        spy_rows = [
            {
                "date": f"2026-05-{d:02d}",
                "ticker": "SPY",
                "close": round(400.0 * (1.0005**d), 6),
            }
            for d in range(1, 26)
        ]
        client = FakeSupabaseClient(
            canned_reads={"nav_history": nav_rows, "price_history": spy_rows}
        )
        _upsert_portfolio_metrics(client=client, run_date=date(2026, 5, 25))
        row = client.store["portfolio_metrics"][0]
        assert row["alpha"] is not None
        assert row["alpha"] > 0  # portfolio beat SPY
        assert row["net_return_pct"] is not None
        assert row["benchmark_return_pct"] is not None
        assert row["relative_return_pct"] == row["alpha"]

    def test_no_spy_data_alpha_none(self) -> None:
        """When SPY price_history is missing, alpha must be None (not crash)."""
        nav_rows = [
            {"date": f"2026-05-{d:02d}", "nav": round(100.0 * (1.001**d), 6)} for d in range(1, 26)
        ]
        client = FakeSupabaseClient(canned_reads={"nav_history": nav_rows, "price_history": []})
        _upsert_portfolio_metrics(client=client, run_date=date(2026, 5, 25))
        row = client.store["portfolio_metrics"][0]
        # sharpe/vol/drawdown should still be computed, but alpha requires SPY
        assert row["sharpe"] is not None
        assert row["alpha"] is None


@pytest.mark.unit
class TestVolatilityScaledInvalidation:
    """#953 — _default_invalidation should use ATR-based stop when available,
    falling back to generic 8% only when ATR data is absent."""

    def test_atr_based_stop_when_available(self) -> None:
        """When atr_pct is present, the stop should be ~2x ATR (volatility-scaled)."""
        analyst = {"entry_price": 100.0, "atr_pct": 2.5}
        result = _default_invalidation(analyst)
        # 2 * 2.5% = 5% stop from entry
        assert "5.0%" in result
        assert (
            "advisory" in result.lower()
            or "atr" in result.lower()
            or "volatility" in result.lower()
        )
        # Should NOT contain the generic 8%
        assert "8%" not in result

    def test_fallback_to_8pct_without_atr(self) -> None:
        """Without ATR data, fall back to the generic 8% stop."""
        analyst = {"entry_price": 100.0}
        result = _default_invalidation(analyst)
        assert "8%" in result

    def test_atr_stop_with_high_vol_asset(self) -> None:
        """High-vol asset (4% daily ATR) → 8% stop (not the generic 8%)."""
        analyst = {"entry_price": 50.0, "atr_pct": 4.0}
        result = _default_invalidation(analyst)
        # 2 * 4% = 8% — but this is ATR-derived, not the generic fallback
        assert "8.0%" in result

    def test_atr_stop_with_low_vol_asset(self) -> None:
        """Low-vol asset like BIL (0.1% daily ATR) → 0.2% stop, not 8%."""
        analyst = {"entry_price": 91.0, "atr_pct": 0.1}
        result = _default_invalidation(analyst)
        # 2 * 0.1% = 0.2% stop — much more sensible for a T-bill ETF
        assert "0.2%" in result
        assert "8%" not in result

    def test_stop_loss_pct_still_takes_priority(self) -> None:
        """Explicit stop_loss_pct from analyst must still take priority over ATR."""
        analyst = {"stop_loss_pct": -5.0, "atr_pct": 2.0, "entry_price": 100.0}
        result = _default_invalidation(analyst)
        assert "5.0%" in result

    def test_zero_atr_falls_back(self) -> None:
        """ATR of 0 is degenerate — fall back to 8% stop."""
        analyst = {"entry_price": 100.0, "atr_pct": 0.0}
        result = _default_invalidation(analyst)
        assert "8%" in result
