"""Unit tests for refresh_performance_metrics.py (#814 / #2598).

Tests the fixes for:
- Fix 3: pnl_pct from finalized accounting, else nav day return — never
          current_book_lookback / legacy position_attribution SUM (#2598);
          sharpe/vol/max_dd/alpha written as NULL when insufficient history (< 20 rows).
- Fix 4: current_price always written from latest price_history close;
          sanity check warning for implausible entry_price (> 10% deviation).

Loaded via importlib.util like the other script-level tests (scripts/ are not
installed packages).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from digiquant.dashboard.tenancy import house_workspace_id

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "refresh_performance_metrics.py"
)


def _load_module():
    """Load refresh_performance_metrics as a module.

    The script has a non-top-level import (position_entry_from_events) that is
    only available when run from its own directory. We stub it out before loading
    so the import succeeds in the test environment.
    """
    stub = MagicMock()
    stub.patch_positions_entries_for_date = MagicMock(return_value=0)
    sys.modules.setdefault("position_entry_from_events", stub)
    spec = importlib.util.spec_from_file_location("refresh_performance_metrics", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
_sum_attribution_pnl = _mod._sum_attribution_pnl
_nav_history_count = _mod._nav_history_count
_risk_metrics_from_nav_history = _mod._risk_metrics_from_nav_history
upsert_portfolio_metrics_daily = _mod.upsert_portfolio_metrics_daily
refresh_positions_metrics = _mod.refresh_positions_metrics
refresh_event_cumulative = _mod.refresh_event_cumulative
_MIN_HISTORY_ROWS = _mod._MIN_HISTORY_ROWS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_with(tables: dict[str, list[dict[str, Any]]]) -> FakeSupabaseClient:
    return FakeSupabaseClient(canned_reads=tables)


# ---------------------------------------------------------------------------
# Fix 3 / #2598: lookback must never feed daily pnl_pct
# ---------------------------------------------------------------------------


class TestSumAttributionPnl:
    """``_sum_attribution_pnl`` is a closed stub — always None (#2598)."""

    def test_lookback_poison_never_sums(self) -> None:
        sb = _fake_with(
            {
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.40},
                    {"date": "2026-06-12", "ticker": "IJR", "contribution_pct": 0.15},
                    {"date": "2026-06-12", "ticker": "XLP", "contribution_pct": 0.05},
                ],
                "current_book_lookback": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 9.99},
                ],
            }
        )
        assert _sum_attribution_pnl(sb, "2026-06-12") is None

    def test_returns_none_when_no_rows(self) -> None:
        sb = _fake_with({"position_attribution": []})
        assert _sum_attribution_pnl(sb, "2026-06-12") is None


class TestNavHistoryCount:
    def test_counts_rows_up_to_date(self) -> None:
        sb = _fake_with(
            {
                "nav_history": [
                    {"date": "2026-06-10", "nav": 100.0},
                    {"date": "2026-06-11", "nav": 100.5},
                    {"date": "2026-06-12", "nav": 101.0},
                ]
            }
        )
        assert _nav_history_count(sb, "2026-06-12") == 3

    def test_returns_zero_for_empty_table(self) -> None:
        sb = _fake_with({"nav_history": []})
        assert _nav_history_count(sb, "2026-06-12") == 0


class TestUpsertPortfolioMetricsDaily:
    def _make_sb_with_attribution(
        self, contributions: list[float], nav_row_count: int = 25
    ) -> FakeSupabaseClient:
        """Build a fake client with attribution rows and enough nav_history for risk metrics."""
        attribution = [
            {"date": "2026-06-12", "ticker": f"T{i}", "contribution_pct": c}
            for i, c in enumerate(contributions)
        ]
        nav_rows = [
            {"date": f"2026-0{5 if i < 9 else 6}-{i + 1:02d}", "nav": 100.0 + i * 0.1}
            for i in range(nav_row_count)
        ]
        return _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": attribution,
                "nav_history": nav_rows,
                "positions": [
                    {"ticker": "T0", "weight_pct": 60.0},
                    {"ticker": "T1", "weight_pct": 40.0},
                ],
            }
        )

    def test_pnl_pct_ignores_lookback_attribution_sum(self) -> None:
        # Poison lookback with +0.60; without final accounting, pnl must come from
        # nav day return (last two nav rows: 100.0 → ~102.3 over 24 seeded days is
        # not used — _make_sb_with_attribution builds 24 nav rows ending before
        # 2026-06-12). Force an explicit prior + as_of nav so the fallback is clear.
        sb = self._make_sb_with_attribution([0.40, 0.15, 0.05])
        sb.canned_reads["nav_history"] = [
            {"date": f"2026-05-{i + 1:02d}", "nav": 100.0} for i in range(24)
        ] + [
            {"date": "2026-06-11", "nav": 100.0},
            {"date": "2026-06-12", "nav": 100.6},
        ]
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        # Must NOT be 0.60 from lookback; nav day return = +0.6% happens to match
        # the poison magnitude but comes from nav — prove lookback is ignored by
        # also poisoning a divergent sum below.
        assert row["pnl_pct"] == pytest.approx(0.6, abs=1e-4)
        assert row["_on_conflict"] == "workspace_id,date"
        assert row["workspace_id"] == str(house_workspace_id())

    def test_pnl_pct_lookback_cannot_override_nav(self) -> None:
        # Divergent lookback (+9.99) must not win over nav day return (+1.0%).
        nav_rows = [{"date": f"2026-05-{i + 1:02d}", "nav": 100.0} for i in range(24)]
        nav_rows.append({"date": "2026-06-11", "nav": 102.0})
        nav_rows.append({"date": "2026-06-12", "nav": 103.02})
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "POISON", "contribution_pct": 9.99},
                ],
                "current_book_lookback": [
                    {"date": "2026-06-12", "ticker": "POISON", "contribution_pct": 9.99},
                ],
                "nav_history": nav_rows,
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["pnl_pct"] == pytest.approx(1.0, abs=1e-3)

    def test_persists_cumulative_portfolio_and_benchmark_returns(self) -> None:
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [],
                "positions": [],
                "nav_history": [
                    {"date": "2026-06-10", "nav": 100.0},
                    {"date": "2026-06-11", "nav": 105.0},
                    {"date": "2026-06-12", "nav": 110.0},
                ],
                "price_history": [
                    {"date": "2026-06-10", "ticker": "SPY", "close": 400.0},
                    {"date": "2026-06-12", "ticker": "SPY", "close": 420.0},
                ],
            }
        )

        upsert_portfolio_metrics_daily(sb, "2026-06-12")

        row = sb.store["portfolio_metrics"][0]
        assert row["net_return_pct"] == pytest.approx(10.0)
        assert row["benchmark_return_pct"] == pytest.approx(5.0)
        assert row["relative_return_pct"] == pytest.approx(5.0)
        assert row["benchmark_ticker"] == "SPY"

    def test_pnl_pct_falls_back_to_nav_day_return_when_no_attribution(self) -> None:
        # No attribution rows → fall back to day-over-day nav return (#814).
        # nav_prev=100.0, nav=100.6 → (100.6 - 100.0) / 100.0 * 100 = +0.6%.
        # Using (nav - 100) = 0.6 happens to be the same here, but on a later day
        # (e.g. nav_prev=102.0, nav=103.02) the two formulas diverge; this test
        # uses a prior row distinct from 100 to make the correct formula observable.
        nav_rows = [{"date": f"2026-05-{i + 1:02d}", "nav": 100.0} for i in range(24)]
        nav_rows.append({"date": "2026-06-11", "nav": 100.0})  # prev day, nav_prev=100.0
        nav_rows.append({"date": "2026-06-12", "nav": 100.6})  # as_of
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [],
                "nav_history": nav_rows,
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["pnl_pct"] == pytest.approx(0.6, abs=1e-4)

    def test_pnl_pct_nav_fallback_uses_prev_not_inception(self) -> None:
        # Verify the nav fallback uses (nav - nav_prev)/nav_prev not (nav - 100).
        # After some gains nav_prev=102.0, nav=103.02 → day return = +1.0%.
        # (nav - 100) = 3.02, which would be wrong.
        nav_rows = [{"date": f"2026-05-{i + 1:02d}", "nav": 100.0} for i in range(24)]
        nav_rows.append({"date": "2026-06-11", "nav": 102.0})  # prev day
        nav_rows.append({"date": "2026-06-12", "nav": 103.02})  # as_of
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [],
                "nav_history": nav_rows,
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        # day return = (103.02 - 102.0) / 102.0 * 100 ≈ 1.0%
        assert row["pnl_pct"] == pytest.approx(1.0, abs=1e-3)

    def test_pnl_pct_nav_fallback_none_when_no_prior_nav(self) -> None:
        # No prior nav row → pnl_pct must be None (not a misleading value).
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [],
                "nav_history": [{"date": "2026-06-12", "nav": 100.6}],  # only today, no prior
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["pnl_pct"] is None

    def test_risk_metrics_null_when_insufficient_history(self) -> None:
        # < 20 nav_history rows → sharpe / volatility / max_drawdown / alpha must be NULL (#814).
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.3}
                ],
                "nav_history": [{"date": f"2026-06-{i + 1:02d}", "nav": 100.0} for i in range(5)],
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["sharpe"] is None
        assert row["volatility"] is None
        assert row["max_drawdown"] is None
        assert row["alpha"] is None

    def test_computed_from_insufficient_history_when_nav_lt_20(self) -> None:
        # When nav_history < 20 rows, computed_from must be
        # 'refresh_script_insufficient_history' (not 'refresh_script') so callers
        # can surface the marker without reading a DATE column as text (#814).
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.3}
                ],
                "nav_history": [{"date": f"2026-06-{i + 1:02d}", "nav": 100.0} for i in range(5)],
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["computed_from"] == "refresh_script_insufficient_history"

    def test_computed_from_refresh_script_when_sufficient_history(self) -> None:
        # When nav_history >= 20 rows, computed_from must be 'refresh_script'.
        nav_rows = [{"date": f"2026-05-{i + 1:02d}", "nav": 100.0 + i * 0.1} for i in range(25)]
        sb = _fake_with(
            {
                "portfolio_metrics": [],
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.3}
                ],
                "nav_history": nav_rows,
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["computed_from"] == "refresh_script"

    def test_risk_metrics_computed_from_nav_when_sufficient_history(self) -> None:
        # >= 20 rows → sharpe/vol/max_dd are computed from nav_history, not carried forward.
        prev_metrics = [
            {
                "date": "2026-06-11",
                "sharpe": 1.2,
                "volatility": 0.15,
                "max_drawdown": -0.05,
                "alpha": 0.02,
            }
        ]
        nav_rows = [{"date": f"2026-05-{i + 1:02d}", "nav": 100.0 + i * 0.1} for i in range(25)]
        sb = _fake_with(
            {
                "portfolio_metrics": prev_metrics,
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.3}
                ],
                "nav_history": nav_rows + [{"date": "2026-06-12", "nav": 102.0}],
                "positions": [],
            }
        )
        expected = _risk_metrics_from_nav_history(sb, "2026-06-12")
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert expected is not None
        assert row["sharpe"] == pytest.approx(expected["sharpe"], abs=1e-6)
        assert row["volatility"] == pytest.approx(expected["volatility"], abs=1e-6)
        assert row["max_drawdown"] == pytest.approx(expected["max_drawdown"], abs=1e-6)
        assert row["sharpe"] != 1.2
        assert row["volatility"] != 0.15
        assert row["max_drawdown"] != -0.05
        assert row["alpha"] == 0.02

    def test_backfills_returns_without_replacing_tearsheet_metrics(self) -> None:
        existing = {
            "date": "2026-06-12",
            "computed_from": "tearsheet",
            "sharpe": 1.25,
        }
        sb = FakeSupabaseClient(
            store={"portfolio_metrics": [existing]},
            canned_reads={
                "portfolio_metrics": [existing],
                "nav_history": [
                    {"date": "2026-06-10", "nav": 100.0},
                    {"date": "2026-06-12", "nav": 110.0},
                ],
                "price_history": [
                    {"date": "2026-06-10", "ticker": "SPY", "close": 400.0},
                    {"date": "2026-06-12", "ticker": "SPY", "close": 420.0},
                ],
            },
        )

        upsert_portfolio_metrics_daily(sb, "2026-06-12")

        row = sb.store["portfolio_metrics"][0]
        assert len(sb.store["portfolio_metrics"]) == 1
        assert row["computed_from"] == "tearsheet"
        assert row["sharpe"] == 1.25
        assert row["net_return_pct"] == pytest.approx(10.0)
        assert row["benchmark_return_pct"] == pytest.approx(5.0)
        assert row["relative_return_pct"] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Fix 4: current_price + entry_price sanity check
# ---------------------------------------------------------------------------


class TestRefreshPositionsMetrics:
    """Tests for refresh_positions_metrics.

    The FakeSupabaseClient's ``update()`` path mutates rows in ``store``, while
    ``select()`` reads from ``canned_reads``.  So each test must:
    1. Pre-populate ``canned_reads["positions"]`` so the SELECT in
       ``refresh_positions_metrics`` returns rows to iterate over.
    2. Also seed those rows into ``store["positions"]`` so the UPDATE can find
       and mutate them — then assert on ``store["positions"]``.
    """

    def _make_position(self, ticker: str, entry_price: float | None = None) -> dict:
        return {
            "ticker": ticker,
            "date": "2026-06-12",
            "entry_price": entry_price,
            "entry_date": "2026-06-01",
            "unrealized_pnl_pct": None,
            "day_change_pct": None,
            "since_entry_return_pct": None,
            "metrics_as_of": None,
            "current_price": None,
        }

    def _sb_with_position(self, pos: dict, price_rows: list[dict]) -> FakeSupabaseClient:
        sb = FakeSupabaseClient(canned_reads={"positions": [pos], "price_history": price_rows})
        # Pre-seed store so FakeQuery.update() can find and mutate the row.
        sb.store["positions"] = [dict(pos)]
        return sb

    def test_current_price_written_from_latest_close(self) -> None:
        # current_price must be populated from price_history when it exists (#814).
        pos = self._make_position("SPY", entry_price=530.0)
        sb = self._sb_with_position(
            pos,
            [
                {"ticker": "SPY", "date": "2026-06-12", "close": 535.0},
                {"ticker": "SPY", "date": "2026-06-11", "close": 533.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-12")
        updated = [r for r in sb.store["positions"] if r.get("current_price") is not None]
        assert len(updated) == 1
        assert updated[0]["current_price"] == 535.0

    def test_current_price_falls_back_to_prev_when_no_today_close(self) -> None:
        # On a non-trading day the exact date may not exist; fall back to prev close (#814).
        pos = self._make_position("SPY", entry_price=530.0)
        sb = self._sb_with_position(
            pos,
            [
                {"ticker": "SPY", "date": "2026-06-11", "close": 533.0},
                # no 2026-06-12 row
            ],
        )
        refresh_positions_metrics(sb, "2026-06-12")
        updated = [r for r in sb.store["positions"] if r.get("current_price") is not None]
        assert len(updated) == 1
        assert updated[0]["current_price"] == 533.0

    def test_entry_price_sanity_warning_on_large_deviation(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        # SPY entry_price=750 vs close=535 is ~40% deviation → warning to stderr (#814).
        pos = self._make_position("SPY", entry_price=750.33)
        sb = self._sb_with_position(
            pos,
            [
                {"ticker": "SPY", "date": "2026-06-12", "close": 535.0},
                {"ticker": "SPY", "date": "2026-06-11", "close": 533.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-12")
        captured = capsys.readouterr()
        assert "entry_price sanity" in captured.err
        assert "SPY" in captured.err

    def test_no_sanity_warning_on_small_deviation(self, capsys: pytest.CaptureFixture) -> None:
        # entry_price close to current_price → no warning.
        pos = self._make_position("SPY", entry_price=530.0)
        sb = self._sb_with_position(
            pos,
            [
                {"ticker": "SPY", "date": "2026-06-12", "close": 535.0},
                {"ticker": "SPY", "date": "2026-06-11", "close": 533.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-12")
        captured = capsys.readouterr()
        assert "entry_price sanity" not in captured.err

    def test_unrealized_pnl_pct_computed_from_entry_and_close(self) -> None:
        # unrealized_pnl_pct = (close - entry) / entry * 100
        pos = self._make_position("SPY", entry_price=500.0)
        sb = self._sb_with_position(
            pos,
            [
                {"ticker": "SPY", "date": "2026-06-12", "close": 550.0},
                {"ticker": "SPY", "date": "2026-06-11", "close": 540.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-12")
        updated = [r for r in sb.store["positions"] if r.get("unrealized_pnl_pct") is not None]
        assert updated[0]["unrealized_pnl_pct"] == pytest.approx(10.0, abs=1e-4)

    def test_cash_row_is_skipped(self) -> None:
        # CASH rows must be left untouched.
        cash_pos = {
            "ticker": "CASH",
            "date": "2026-06-12",
            "weight_pct": 30.0,
            "entry_price": None,
            "entry_date": None,
            "current_price": None,
        }
        sb = FakeSupabaseClient(canned_reads={"positions": [cash_pos], "price_history": []})
        sb.store["positions"] = [dict(cash_pos)]
        n = refresh_positions_metrics(sb, "2026-06-12")
        assert n == 0
        # No update should have been applied to the CASH row
        assert sb.store["positions"][0]["current_price"] is None


# ---------------------------------------------------------------------------
# #1746: the scheduled (flagless) run must not silently re-process an older date
# ---------------------------------------------------------------------------


class TestCarriedPriceProvenance:
    """A carried close must record the date it came from, never the book date (#1833).

    Prod before this: every non-CASH row on Saturday 2026-08-01 carried
    ``metrics_as_of = 2026-08-01`` while ``current_price`` was that ticker's 2026-07-31 close
    exactly (EWZ 36.65, XLE 59.55, XLV 162.55) — and ``price_history`` has no equity rows on
    08-01. The row asserted a close existed on a day the market never opened.

    Migration 012 already defines the column as "Date of close used for metrics (usually last
    trading day)", and its three sibling percent columns are defined *relative to*
    ``metrics_as_of`` — so a wrong stamp made four definitions wrong at once. This is the same
    principle #1749/#1750 settled for documents: a carried value keeps its source date.
    """

    def _make_position(self, ticker: str, entry_price: float | None = None) -> dict:
        return {
            "ticker": ticker,
            "date": "2026-06-13",
            "entry_price": entry_price,
            "entry_date": "2026-06-01",
            "unrealized_pnl_pct": None,
            "day_change_pct": None,
            "since_entry_return_pct": None,
            "metrics_as_of": None,
            "current_price": None,
        }

    def _sb(self, pos: dict, price_rows: list[dict]) -> FakeSupabaseClient:
        sb = FakeSupabaseClient(canned_reads={"positions": [pos], "price_history": price_rows})
        sb.store["positions"] = [dict(pos)]
        return sb

    # The prior-trading-day reference is resolved from SPY once for the whole book
    # (``_prev_trading_date(sb, "SPY", metrics_date)``), not per ticker. So a carried close for
    # any ticker depends on SPY having a row at that date — true in production, and it has to be
    # in the fixture or the fallback silently cannot fire. Noted rather than fixed: a
    # ticker whose own history lags SPY's gets no close from either candidate date, which is a
    # separate defect (XRT lagged its peers by a day in prod) and a separate PR.
    _SPY_PRIOR = {"ticker": "SPY", "date": "2026-06-12", "close": 535.0}

    def test_a_same_day_close_stamps_the_book_date(self) -> None:
        """The unchanged case: a real trading day marks itself."""
        sb = self._sb(
            self._make_position("SPY", entry_price=530.0),
            [
                {"ticker": "SPY", "date": "2026-06-13", "close": 540.0},
                {"ticker": "SPY", "date": "2026-06-12", "close": 535.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-13")
        row = sb.store["positions"][0]
        assert row["current_price"] == 540.0
        assert row["metrics_as_of"] == "2026-06-13"

    def test_a_carried_close_stamps_the_source_date_not_the_book_date(self) -> None:
        """The Saturday/Sunday case, and the whole point of #1833."""
        sb = self._sb(
            self._make_position("XLV", entry_price=150.0),
            [self._SPY_PRIOR, {"ticker": "XLV", "date": "2026-06-12", "close": 162.55}],
        )
        refresh_positions_metrics(sb, "2026-06-13")
        row = sb.store["positions"][0]
        assert row["current_price"] == 162.55
        assert row["metrics_as_of"] == "2026-06-12", (
            "a carried Friday close stamped with the Sunday book date asserts a close on a day "
            "the market never opened"
        )

    def test_a_carried_close_reports_no_day_change_rather_than_a_fabricated_zero(self) -> None:
        """``c_now`` and ``c_prev`` are the SAME close on a carried day, so the old arithmetic
        produced exactly 0.0% — a measured-looking number for a session that never happened.
        All 11 non-CASH rows on 2026-08-01 carried it. NULL is the honest value; the frontend
        already falls back to a client-side derivation when the column is null."""
        sb = self._sb(
            self._make_position("XLE", entry_price=55.0),
            [self._SPY_PRIOR, {"ticker": "XLE", "date": "2026-06-12", "close": 59.55}],
        )
        refresh_positions_metrics(sb, "2026-06-13")
        row = sb.store["positions"][0]
        assert row["day_change_pct"] is None
        # The other two percentages are still real — they are entry-relative, not session-relative.
        assert row["unrealized_pnl_pct"] is not None

    def test_a_real_session_still_reports_a_day_change(self) -> None:
        """Guard against over-correcting: the NULL applies only to carried days."""
        sb = self._sb(
            self._make_position("SPY", entry_price=530.0),
            [
                {"ticker": "SPY", "date": "2026-06-13", "close": 540.0},
                {"ticker": "SPY", "date": "2026-06-12", "close": 535.0},
            ],
        )
        refresh_positions_metrics(sb, "2026-06-13")
        assert sb.store["positions"][0]["day_change_pct"] == pytest.approx(
            (540.0 - 535.0) / 535.0 * 100.0
        )

    def test_an_unmarkable_row_clears_every_metric_together(self) -> None:
        """No close for either candidate date — real case: XRT's price_history lagged its peers
        by a day. Previously the stale stored price was RETAINED while ``metrics_as_of`` was
        stamped anyway: an old price under a fresh provenance label. All four must go null
        together, because ``valuePosition`` needs both ``current_price`` and ``metrics_as_of``
        to take its close branch — nulling both renders an em-dash, which is honest."""
        stale = self._make_position("XRT", entry_price=70.0)
        stale["current_price"] = 71.11  # left over from an earlier run
        stale["metrics_as_of"] = "2026-06-01"
        sb = self._sb(stale, [])  # price_history has nothing for this ticker
        refresh_positions_metrics(sb, "2026-06-13")
        row = sb.store["positions"][0]
        assert row["current_price"] is None, "a stale price must not survive under a fresh stamp"
        assert row["metrics_as_of"] is None
        assert row["unrealized_pnl_pct"] is None
        assert row["day_change_pct"] is None
        assert row["since_entry_return_pct"] is None

    def test_cash_is_still_skipped(self) -> None:
        cash = self._make_position("CASH")
        sb = self._sb(cash, [])
        refresh_positions_metrics(sb, "2026-06-13")
        assert sb.store["positions"][0]["metrics_as_of"] is None


class TestRefreshEventCumulativeHouseScope:
    """House cron must not patch overlay (or leaked) ``position_events`` by bare ``id``."""

    def test_skips_overlay_workspace_events(self) -> None:
        house = str(house_workspace_id())
        overlay = str(uuid4())
        house_ev = {
            "id": "house-1",
            "date": "2026-06-01",
            "ticker": "SPY",
            "workspace_id": house,
            "cumulative_return_since_event_pct": None,
        }
        overlay_ev = {
            "id": "overlay-1",
            "date": "2026-06-01",
            "ticker": "SPY",
            "workspace_id": overlay,
            "cumulative_return_since_event_pct": None,
        }
        prices = [
            {"ticker": "SPY", "date": "2026-06-01", "close": 500.0},
            {"ticker": "SPY", "date": "2026-06-12", "close": 550.0},
        ]
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [house_ev, overlay_ev],
                "price_history": prices,
            }
        )
        sb.store["position_events"] = [dict(house_ev), dict(overlay_ev)]
        n = refresh_event_cumulative(sb, "2026-06-12")
        assert n == 1
        by_id = {r["id"]: r for r in sb.store["position_events"]}
        assert by_id["house-1"]["cumulative_return_since_event_pct"] == pytest.approx(10.0)
        assert by_id["overlay-1"]["cumulative_return_since_event_pct"] is None


class TestMetricsCronRunsEveryDay:
    """The schedule half of #1833. The book cron is daily; the metrics cron was MON-SAT, so a
    Sunday book was written and then never enriched — NULL permanently, not just until 22:00."""

    def test_the_cron_has_no_weekday_restriction(self) -> None:
        import yaml

        wf = (
            Path(__file__).resolve().parents[3]
            / ".github"
            / "workflows"
            / "pipeline-research-metrics.yml"
        )
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        crons = [s["cron"] for s in doc[True]["schedule"]]  # `on:` parses as boolean True
        assert crons, "the metrics workflow must keep a schedule"
        for cron in crons:
            dow = cron.split()[4]
            assert dow == "*", (
                f"metrics cron day-of-week is {dow!r}; a restricted schedule leaves the book "
                "for an excluded day permanently unenriched (#1833)"
            )

    def test_it_still_runs_after_the_eod_price_ingest(self) -> None:
        """22:00 UTC is load-bearing: the price cron writes closes at 21:00, so an earlier
        metrics run would carry the *previous* day forward on every trading day."""
        import yaml

        wf = (
            Path(__file__).resolve().parents[3]
            / ".github"
            / "workflows"
            / "pipeline-research-metrics.yml"
        )
        doc = yaml.safe_load(wf.read_text(encoding="utf-8"))
        for cron in [s["cron"] for s in doc[True]["schedule"]]:
            minute, hour = cron.split()[0], cron.split()[1]
            assert (int(hour), int(minute)) >= (22, 0), f"{cron} runs before the 21:00 ingest"


class TestResolveScheduledMetricsDate:
    """The flagless cron path resolves *today UTC*, never ``max(positions.date)``.

    Falling back to the latest existing book let ``portfolio_metrics``' upsert
    ``on_conflict='workspace_id,date'`` rewrite an older row: 22 of 33 green prod runs advanced no
    date, and 2026-06-26's row was re-stamped on 2026-07-16.
    """

    @staticmethod
    def _positions_on(*dates: str) -> FakeSupabaseClient:
        return _fake_with({"positions": [{"date": d, "ticker": "SPY"} for d in dates]})

    def test_returns_todays_book_when_it_exists(self) -> None:
        sb = self._positions_on("2026-07-28", "2026-07-29", "2026-07-31")
        assert _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 31)) == "2026-07-31"

    def test_returns_the_book_date_not_the_target_when_a_book_is_ahead(self) -> None:
        """Pins the documented contract: the resolved date is ``max(positions.date)``.

        Prod never books ahead of today UTC, so this branch is unreachable there — but it
        is the only case where returning the book date differs observably from returning
        the target, and the docstring promises "never earlier".
        """
        sb = self._positions_on("2026-07-31")
        assert _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 30)) == "2026-07-31"

    def test_stale_message_does_not_recommend_a_bookless_date(self) -> None:
        """The remediation hint must not send an operator to ``--date <today>``.

        ``--date`` runs ``carry_forward_positions`` first, so pointing at a date with no
        book would clone the previous one — the densification this guard exists to avoid.
        """
        sb = self._positions_on("2026-07-29")
        with pytest.raises(_mod.StaleBookError) as excinfo:
            _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 30))
        message = str(excinfo.value)
        assert "--date 2026-07-29" in message
        assert "Do NOT pass --date 2026-07-30" in message

    def test_raises_when_book_is_one_day_stale(self) -> None:
        # Prod run 30589621216 (2026-07-30): the Olympus run was cancelled after 4h so no
        # 07-30 book existed; the cron re-stamped 07-29 and exited 0 with two green ticks.
        sb = self._positions_on("2026-07-28", "2026-07-29")
        with pytest.raises(_mod.StaleBookError) as excinfo:
            _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 30))
        message = str(excinfo.value)
        assert "2026-07-29" in message and "2026-07-30" in message
        assert "1 day(s)" in message

    def test_raises_across_the_twenty_day_blackout(self) -> None:
        # 2026-06-27..07-16: 17 consecutive green runs all stamped 2026-06-26.
        sb = self._positions_on("2026-06-26")
        with pytest.raises(_mod.StaleBookError) as excinfo:
            _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 16))
        assert "20 day(s)" in str(excinfo.value)

    def test_raises_when_no_positions_exist_at_all(self) -> None:
        sb = self._positions_on()
        with pytest.raises(_mod.StaleBookError):
            _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 31))

    def test_stale_book_writes_nothing(self) -> None:
        """The guard runs *before* any upsert — a stale run leaves the DB untouched."""
        sb = self._positions_on("2026-07-29")
        with pytest.raises(_mod.StaleBookError):
            _mod.resolve_scheduled_metrics_date(sb, date(2026, 7, 30))
        assert sb.store == {}

    def test_exit_code_is_distinct_from_hard_failure(self) -> None:
        # The wrapper maps any other exception to 1; a stale book must be tellable apart.
        assert _mod._EXIT_STALE_BOOK == 3


class TestMetricsWorkflowStepOrder:
    """Pins finalizer → metrics → lookback in ``pipeline-research-metrics.yml``.

    After #2598, ``pnl_pct`` never reads ``current_book_lookback`` / legacy
    ``position_attribution``, so lookback job order cannot alter daily semantics.
    Still keep metrics before the lookback step for operational clarity, and the
    accounting finalizer before metrics so finalized periods are available.
    """

    @staticmethod
    def _step_names() -> list[str]:
        import yaml

        workflow = (
            Path(__file__).resolve().parents[3]
            / ".github"
            / "workflows"
            / "pipeline-research-metrics.yml"
        )
        spec = yaml.safe_load(workflow.read_text(encoding="utf-8"))
        return [str(step.get("name", "")) for step in spec["jobs"]["refresh"]["steps"]]

    def test_finalizer_precedes_metrics_precedes_lookback(self) -> None:
        names = self._step_names()
        finalizer = next(i for i, n in enumerate(names) if "period accounting" in n.lower())
        metrics = next(i for i, n in enumerate(names) if "portfolio_metrics" in n)
        lookback = next(
            i
            for i, n in enumerate(names)
            if "lookback" in n.lower() or "position_attribution" in n or "attribution" in n.lower()
        )
        assert finalizer < metrics < lookback, (
            "finalizer → metrics → lookback: daily pnl must not depend on lookback "
            "order (#2598 / OLY-REV-007)"
        )
