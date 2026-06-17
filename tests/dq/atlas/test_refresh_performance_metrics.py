"""Unit tests for refresh_performance_metrics.py (#814).

Tests the fixes for:
- Fix 3: pnl_pct derived from position_attribution SUM (not hard-coded 0.0);
          sharpe/vol/max_dd/alpha written as NULL when insufficient history (< 20 rows).
- Fix 4: current_price always written from latest price_history close;
          sanity check warning for implausible entry_price (> 10% deviation).

Loaded via importlib.util like the other script-level tests (scripts/ are not
installed packages).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

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
upsert_portfolio_metrics_daily = _mod.upsert_portfolio_metrics_daily
refresh_positions_metrics = _mod.refresh_positions_metrics
_MIN_HISTORY_ROWS = _mod._MIN_HISTORY_ROWS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_with(tables: dict[str, list[dict[str, Any]]]) -> FakeSupabaseClient:
    return FakeSupabaseClient(canned_reads=tables)


# ---------------------------------------------------------------------------
# Fix 3: pnl_pct from attribution
# ---------------------------------------------------------------------------


class TestSumAttributionPnl:
    def test_sums_non_cash_contributions(self) -> None:
        sb = _fake_with(
            {
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.40},
                    {"date": "2026-06-12", "ticker": "IJR", "contribution_pct": 0.15},
                    {"date": "2026-06-12", "ticker": "XLP", "contribution_pct": 0.05},
                ]
            }
        )
        result = _sum_attribution_pnl(sb, "2026-06-12")
        assert result == pytest.approx(0.60, abs=1e-6)

    def test_excludes_cash_rows(self) -> None:
        sb = _fake_with(
            {
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 0.50},
                    {"date": "2026-06-12", "ticker": "CASH", "contribution_pct": 0.0},
                ]
            }
        )
        result = _sum_attribution_pnl(sb, "2026-06-12")
        assert result == pytest.approx(0.50, abs=1e-6)

    def test_returns_none_when_no_rows(self) -> None:
        sb = _fake_with({"position_attribution": []})
        assert _sum_attribution_pnl(sb, "2026-06-12") is None

    def test_returns_none_when_all_cash(self) -> None:
        sb = _fake_with(
            {
                "position_attribution": [
                    {"date": "2026-06-12", "ticker": "CASH", "contribution_pct": 0.0}
                ]
            }
        )
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

    def test_pnl_pct_from_attribution_sum(self) -> None:
        # The real return is +0.60 from position_attribution (#814).
        sb = self._make_sb_with_attribution([0.40, 0.15, 0.05])
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["pnl_pct"] == pytest.approx(0.60, abs=1e-4)

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

    def test_risk_metrics_carried_when_sufficient_history(self) -> None:
        # >= 20 rows → previous sharpe/vol/etc are carried forward.
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
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        row = sb.store["portfolio_metrics"][0]
        assert row["sharpe"] == 1.2
        assert row["volatility"] == 0.15
        assert row["max_drawdown"] == -0.05
        assert row["alpha"] == 0.02

    def test_skips_tearsheet_row(self) -> None:
        # If a 'tearsheet' row exists for the date, must skip (no write).
        sb = _fake_with(
            {
                "portfolio_metrics": [{"date": "2026-06-12", "computed_from": "tearsheet"}],
                "position_attribution": [],
                "nav_history": [],
                "positions": [],
            }
        )
        upsert_portfolio_metrics_daily(sb, "2026-06-12")
        # store should have no NEW rows written (the canned_reads row is the tearsheet one)
        assert len(sb.store.get("portfolio_metrics", [])) == 0


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
