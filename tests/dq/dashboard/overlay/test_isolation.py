"""H1/H3/H5: omitted workspace_id means the house, never every row."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.portfolio.writers.commit_io import _prune_orphan_positions
from digiquant.portfolio.writers.ledger_io import COMMITS, _rows_for_date
from digiquant.research.supabase_io import load_prior_book

from tests.dq.portfolio.test_execution_io import RUN_DATE, _Chain, _run
from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit


def test_house_prune_spares_overlay_positions() -> None:
    house = str(house_workspace_id())
    overlay = str(uuid4())
    date_str = "2026-08-30"
    rows = [
        {"date": date_str, "ticker": "SPY", "weight_pct": 100.0, "workspace_id": house},
        {"date": date_str, "ticker": "AAPL", "weight_pct": 50.0, "workspace_id": overlay},
        {"date": date_str, "ticker": "MSFT", "weight_pct": 10.0, "workspace_id": house},
    ]
    client = FakeSupabaseClient(canned_reads={"positions": rows})
    client.store["positions"] = [dict(r) for r in rows]
    pruned = _prune_orphan_positions(
        client=client, date_str=date_str, keep={"SPY"}, workspace_id=None
    )
    assert "AAPL" not in pruned
    assert "MSFT" in pruned
    remaining = {r["ticker"]: r["workspace_id"] for r in client.store["positions"]}
    assert remaining["AAPL"] == overlay
    assert remaining["SPY"] == house
    assert "MSFT" not in remaining


def test_house_prior_book_ignores_overlay() -> None:
    house = str(house_workspace_id())
    overlay = str(uuid4())
    client = FakeSupabaseClient(
        canned_reads={
            "positions": [
                {
                    "date": "2026-08-29",
                    "ticker": "NVDA",
                    "weight_pct": 20.0,
                    "workspace_id": house,
                    "entry_date": "2026-08-29",
                },
                {
                    "date": "2026-08-29",
                    "ticker": "TSLA",
                    "weight_pct": 80.0,
                    "workspace_id": overlay,
                    "entry_date": "2026-08-29",
                },
            ]
        }
    )
    book = load_prior_book(client, date(2026, 8, 30))
    assert {r["ticker"] for r in book} == {"NVDA"}
    assert all(r.get("workspace_id") == house for r in book)


def test_house_ledger_date_scope_ignores_overlay_commits() -> None:
    house = str(house_workspace_id())
    overlay = str(uuid4())
    client = FakeSupabaseClient(
        canned_reads={
            COMMITS: [
                {"id": "h1", "run_date": "2026-08-30", "workspace_id": house},
                {"id": "o1", "run_date": "2026-08-30", "workspace_id": overlay},
            ]
        }
    )
    rows = _rows_for_date(
        client=client, table=COMMITS, run_date=date(2026, 8, 30), workspace_id=None
    )
    assert [r["id"] for r in rows] == ["h1"]


def test_house_executor_never_fills_overlay_intents() -> None:
    overlay = str(uuid4())
    chain = _Chain()
    house_order = chain.order(symbol="AAPL", action="OPEN", quantity="10")
    overlay_order = str(uuid4())
    chain.orders.append(
        {
            "id": overlay_order,
            "approved_target_id": chain.approved[0]["id"],
            "run_date": RUN_DATE.isoformat(),
            "symbol": "TSLA",
            "quantity": "5",
            "status": "pending",
            "supersedes_id": None,
            "workspace_id": overlay,
        }
    )
    client = chain.client()
    result = _run(client, marks={"AAPL": "100.00", "TSLA": "200.00"})
    filled_symbols = {f.symbol for f in result.fills}
    assert "AAPL" in filled_symbols or house_order
    assert "TSLA" not in filled_symbols
    assert overlay_order not in {str(f.order_intent_id) for f in result.fills}
