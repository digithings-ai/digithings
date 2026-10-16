"""Unit tests for scripts/seed_digiquant_demo.py (#1045).

Verifies that the data generators produce valid, schema-conformant rows
without touching a real Supabase instance.
"""

from __future__ import annotations

import importlib.util
import math
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "seed_digiquant_demo.py"

pytestmark = pytest.mark.unit


def _load_module():
    spec = importlib.util.spec_from_file_location("seed_digiquant_demo", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


class TestNavRows:
    def test_minimum_length(self, mod) -> None:
        rows = mod.generate_nav_rows()
        assert len(rows) >= 2, "nav_history must have >=2 points"

    def test_expected_length(self, mod) -> None:
        rows = mod.generate_nav_rows()
        assert len(rows) == mod._NAV_WEEKS

    def test_required_columns(self, mod) -> None:
        row = mod.generate_nav_rows()[0]
        assert {"date", "nav", "invested_pct", "cash_pct"} <= row.keys()

    def test_nav_positive(self, mod) -> None:
        for row in mod.generate_nav_rows():
            assert row["nav"] > 0, f"NAV must be positive, got {row['nav']}"

    def test_invested_plus_cash_equals_one(self, mod) -> None:
        for row in mod.generate_nav_rows():
            total = round(row["invested_pct"] + row["cash_pct"], 6)
            assert math.isclose(total, 1.0, abs_tol=1e-4), f"invested+cash != 1.0 for {row['date']}"

    def test_dates_weekly_monotonic(self, mod) -> None:
        from datetime import date, timedelta

        rows = mod.generate_nav_rows()
        for i in range(1, len(rows)):
            prev = date.fromisoformat(rows[i - 1]["date"])
            curr = date.fromisoformat(rows[i]["date"])
            assert curr - prev == timedelta(weeks=1), f"gap not 7 days at {curr}"

    def test_deterministic(self, mod) -> None:
        assert mod.generate_nav_rows() == mod.generate_nav_rows()


class TestDecisionRows:
    def test_length(self, mod) -> None:
        rows = mod.generate_decision_rows()
        assert len(rows) == len(mod._DECISIONS)

    def test_required_columns(self, mod) -> None:
        required = {
            "run_id",
            "run_date",
            "ticker",
            "stance",
            "conviction",
            "thesis",
            "benchmark",
            "holding_days",
            "status",
            "actual_return",
            "alpha",
            "reflection",
            "resolved_at",
        }
        for row in mod.generate_decision_rows():
            assert required <= row.keys(), f"missing keys in {row}"

    def test_status_resolved(self, mod) -> None:
        for row in mod.generate_decision_rows():
            assert row["status"] == "resolved"

    def test_run_ids_deterministic_and_unique(self, mod) -> None:
        rows = mod.generate_decision_rows()
        ids = [r["run_id"] for r in rows]
        assert len(ids) == len(set(ids)), "run_ids must be unique"
        assert ids == [r["run_id"] for r in mod.generate_decision_rows()], (
            "run_ids must be deterministic"
        )

    def test_run_ids_valid_uuids(self, mod) -> None:
        for row in mod.generate_decision_rows():
            uuid.UUID(row["run_id"])  # raises ValueError if invalid

    def test_actual_return_and_alpha_populated(self, mod) -> None:
        for row in mod.generate_decision_rows():
            assert row["actual_return"] is not None
            assert row["alpha"] is not None


class TestMetricsRow:
    def test_required_columns(self, mod) -> None:
        nav_rows = mod.generate_nav_rows()
        row = mod.generate_metrics_row(nav_rows)
        required = {"date", "pnl_pct", "sharpe", "volatility", "max_drawdown"}
        assert required <= row.keys()

    def test_max_drawdown_non_positive(self, mod) -> None:
        nav_rows = mod.generate_nav_rows()
        row = mod.generate_metrics_row(nav_rows)
        assert row["max_drawdown"] <= 0.0, "max drawdown must be <=0"

    def test_date_matches_last_nav_row(self, mod) -> None:
        nav_rows = mod.generate_nav_rows()
        metrics = mod.generate_metrics_row(nav_rows)
        assert metrics["date"] == nav_rows[-1]["date"]


class TestDryRun:
    def test_dry_run_exits_cleanly(self, mod, capsys) -> None:
        """--dry-run must not attempt any Supabase call."""
        saved = sys.argv[:]
        try:
            sys.argv = ["seed_digiquant_demo.py", "--dry-run"]
            mod.main()
        finally:
            sys.argv = saved

        out = capsys.readouterr().out
        assert "nav_history rows:" in out
        assert "decision_log rows:" in out


class _RecordingClient:
    """Stands in for the Supabase client; records each upsert's conflict target."""

    def __init__(self) -> None:
        self.conflicts: dict[str, set[str]] = {}

    def table(self, name: str):
        client = self

        class _Table:
            def upsert(self, row, on_conflict: str):
                client.conflicts.setdefault(name, set()).add(on_conflict)
                return self

            def execute(self):
                return self

        return _Table()


def test_decision_log_upsert_targets_the_live_unique_constraint(mod, monkeypatch) -> None:
    """ON CONFLICT must name a unique constraint the schema still has.

    Migration 044 replaced (run_id, ticker) with (run_date, ticker); the seeder
    kept the old target, so every run against a migrated database failed with
    42P10 "no unique or exclusion constraint matching the ON CONFLICT".
    """
    migration = (
        REPO_ROOT / "digiquant/supabase/migrations/engine/044_decision_log_rundate_unique.sql"
    ).read_text()
    # Control: the constraint this test pins is the one 044 actually defines.
    assert "UNIQUE (run_date, ticker)" in migration
    assert "DROP CONSTRAINT IF EXISTS decision_log_run_ticker_unique" in migration

    client = _RecordingClient()
    monkeypatch.setattr(mod, "_build_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["seed_digiquant_demo.py"])
    mod.main()
    assert client.conflicts["decision_log"] == {"run_date,ticker"}


def test_metrics_row_uses_post_035_column_names(mod) -> None:
    """035 dropped portfolio_metrics.cash_pct and renamed total_invested."""
    migration = (
        REPO_ROOT / "digiquant/supabase/migrations/prod/035_drop_derived_duplicate_columns.sql"
    ).read_text()
    # Control: the schema change this test pins is the one 035 makes.
    assert "ALTER TABLE portfolio_metrics DROP COLUMN IF EXISTS cash_pct" in migration
    assert "RENAME COLUMN total_invested TO invested_pct" in migration

    row = mod.generate_metrics_row(mod.generate_nav_rows())
    assert not {"cash_pct", "total_invested"} & row.keys()
    assert "invested_pct" in row
