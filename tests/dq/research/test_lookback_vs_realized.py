"""Authority boundaries: lookback must not feed realized daily readers (#2598)."""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest
import yaml
from digiquant.dashboard.accounting.engine import compute_period
from digiquant.dashboard.accounting.io import persist_period

from tests.dq.atlas.test_finalize_period_accounting import (
    EFFECTIVE,
    PERIOD,
    MergingFake,
    _final_hold_input,
)
from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]


def _load_metrics_mod():
    stub = types.ModuleType("position_entry_from_events")
    stub.resolve_entry_price = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules.setdefault("position_entry_from_events", stub)
    path = REPO / "digiquant" / "scripts" / "atlas" / "refresh_performance_metrics.py"
    spec = importlib.util.spec_from_file_location("refresh_performance_metrics_2598", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sum_attribution_helper_never_reads_lookback() -> None:
    mod = _load_metrics_mod()
    sb = FakeSupabaseClient(
        canned_reads={
            "current_book_lookback": [
                {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 9.99},
            ],
            "position_attribution": [
                {"date": "2026-06-12", "ticker": "SPY", "contribution_pct": 9.99},
            ],
        }
    )
    assert mod._sum_attribution_pnl(sb, "2026-06-12") is None


def test_lookback_poison_cannot_populate_daily_pnl_pct() -> None:
    """21-day lookback values must not win daily contribution / pnl_pct (#2598)."""
    mod = _load_metrics_mod()
    client = MergingFake()
    client.canned_reads["current_book_lookback"] = [
        {"date": PERIOD.isoformat(), "ticker": "AAPL", "contribution_pct": 9.99},
    ]
    client.canned_reads["position_attribution"] = [
        {"date": PERIOD.isoformat(), "ticker": "AAPL", "contribution_pct": 9.99},
    ]
    client.canned_reads["nav_history"] = [
        {"date": "2026-08-24", "nav": 100.0},
        {"date": PERIOD.isoformat(), "nav": 100.42},
    ]
    client.canned_reads["portfolio_metrics"] = []
    client.canned_reads["positions"] = []
    client.canned_reads["price_history"] = []

    mod.upsert_portfolio_metrics_daily(client, PERIOD.isoformat())
    rows = client.store.get("portfolio_metrics", [])
    assert rows
    assert rows[0]["pnl_pct"] == pytest.approx(0.42, abs=1e-4)


def test_final_accounting_still_beats_lookback_and_nav() -> None:
    mod = _load_metrics_mod()
    client = MergingFake()
    period = compute_period(_final_hold_input())
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    client.canned_reads["current_book_lookback"] = [
        {"date": PERIOD.isoformat(), "ticker": "AAPL", "contribution_pct": 9.99},
    ]
    client.canned_reads["position_attribution"] = [
        {"date": PERIOD.isoformat(), "ticker": "AAPL", "contribution_pct": 9.99},
    ]
    client.canned_reads["nav_history"] = [
        {"date": "2026-08-24", "nav": 100.0},
        {"date": PERIOD.isoformat(), "nav": 101.0},
    ]
    client.canned_reads["portfolio_metrics"] = []
    client.canned_reads["positions"] = [
        {"date": PERIOD.isoformat(), "ticker": "AAPL", "weight_pct": 80.0},
    ]
    client.canned_reads["price_history"] = []

    mod.upsert_portfolio_metrics_daily(client, PERIOD.isoformat())
    rows = client.store.get("portfolio_metrics", [])
    assert rows
    # Final period return: (51000-50000)/50000 * 100 = 2.0 for _final_hold_input
    assert rows[0]["pnl_pct"] == pytest.approx(2.0, abs=1e-6)


def test_workflow_documents_lookback_as_diagnostic() -> None:
    workflow = REPO / ".github" / "workflows" / "pipeline-research-metrics.yml"
    text = workflow.read_text(encoding="utf-8")
    assert "current_book_lookback" in text
    assert "diagnostic" in text.lower()
    spec = yaml.safe_load(text)
    names = [str(step.get("name", "")) for step in spec["jobs"]["refresh"]["steps"]]
    assert any("lookback" in n.lower() for n in names)
    assert isinstance(PERIOD, date)  # period fixture from finalize suite
