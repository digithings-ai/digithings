"""P6: house ops writers stamp workspace_id and target widened UNIQUEs."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — PostgREST row dicts in fixtures

import pytest
from digiquant.olympus.tenancy import house_workspace_id

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas"
_HOUSE = str(house_workspace_id())


def _load(name: str):
    path = _SCRIPTS / f"{name}.py"
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    # Other atlas tests stub this sibling as a MagicMock at collection time.
    sys.modules.pop("position_entry_from_events", None)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _rebalance_doc(d: str, positions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "document_key": "rebalance-decision.json",
        "date": d,
        "workspace_id": _HOUSE,
        "payload": {
            "doc_type": "rebalance_decision",
            "body": {"proposed_portfolio": {"positions": positions, "cash_residual_pct": 5}},
        },
    }


class TestSyncPositionsFromRebalance:
    def test_upserts_house_workspace_conflict(self) -> None:
        mod = _load("sync_positions_from_rebalance")
        mod.first_open_add_mark = lambda *_a, **_k: (None, None)
        d = "2026-08-31"
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [_rebalance_doc(d, [{"ticker": "IAU", "weight_pct": 20}])],
                "position_events": [],
                "positions": [],
            }
        )
        n = mod.sync_positions_for_date(sb, d)
        assert n == 2  # IAU + CASH residual
        rows = sb.store["positions"]
        assert all(r["_on_conflict"] == "workspace_id,date,ticker" for r in rows)
        assert all(r["workspace_id"] == _HOUSE for r in rows)
        tickers = {r["ticker"] for r in rows}
        assert tickers == {"IAU", "CASH"}

    def test_dry_run_does_not_write(self) -> None:
        mod = _load("sync_positions_from_rebalance")
        mod.first_open_add_mark = lambda *_a, **_k: (None, None)
        d = "2026-08-31"
        sb = FakeSupabaseClient(
            canned_reads={
                "documents": [_rebalance_doc(d, [{"ticker": "GLD", "weight_pct": 10}])],
                "position_events": [],
            }
        )
        n = mod.sync_positions_for_date(sb, d, dry_run=True)
        assert n == 2
        assert "positions" not in sb.store


class TestUpdateTearsheetPush:
    def test_group_a_tables_use_widened_conflict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        if str(_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS))
        import update_tearsheet as ut

        sb = FakeSupabaseClient()
        monkeypatch.setattr(ut, "supabase_configured", lambda: True)
        monkeypatch.setattr(ut, "_get_supabase_client", lambda: sb)
        parsed = [
            {
                "date": "2026-08-31",
                "positions": [{"ticker": "IAU", "weight": 20, "name": "Gold"}],
            }
        ]
        ut.push_to_supabase(
            parsed,
            docs=[],
            history=[{"date": "2026-08-31", "nav": 100.0}],
            metrics={"date": "2026-08-31", "computed_from": "tearsheet"},
            pj_positions=[],
        )
        pos = sb.store["positions"]
        assert pos[0]["_on_conflict"] == "workspace_id,date,ticker"
        assert pos[0]["workspace_id"] == _HOUSE
        nav = sb.store["nav_history"]
        assert nav[0]["_on_conflict"] == "workspace_id,date"
        assert nav[0]["workspace_id"] == _HOUSE
        metrics = sb.store["portfolio_metrics"]
        assert metrics[0]["_on_conflict"] == "workspace_id,date"
        assert metrics[0]["workspace_id"] == _HOUSE
        events = sb.store["position_events"]
        assert events[0]["_on_conflict"] == "workspace_id,date,ticker"
        assert events[0]["workspace_id"] == _HOUSE


class TestMaterializeSnapshotPositions:
    def test_positions_stamp_house(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mod = _load("materialize_snapshot")
        sb = FakeSupabaseClient()
        monkeypatch.setattr(mod, "_sb", lambda: sb)
        snapshot = {
            "date": "2026-08-31",
            "run_type": "baseline",
            "portfolio": {"positions": [{"ticker": "IAU", "weight_pct": 15}]},
        }
        mod._upsert_snapshot(snapshot, None)
        rows = [r for r in sb.store.get("positions", []) if r.get("ticker") == "IAU"]
        assert rows
        assert rows[0]["_on_conflict"] == "workspace_id,date,ticker"
        assert rows[0]["workspace_id"] == _HOUSE


class TestBackfillExecutionPrices:
    def test_upserts_house_workspace_conflict(self) -> None:
        mod = _load("backfill_execution_prices")
        d = "2026-08-31"
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [
                    {
                        "workspace_id": _HOUSE,
                        "date": d,
                        "ticker": "IAU",
                        "event": "OPEN",
                        "price": None,
                        "weight_pct": 10,
                    }
                ],
                "price_history": [{"ticker": "IAU", "date": d, "open": 42.5}],
            }
        )
        n = mod.backfill_prices_for_date(sb, d)
        assert n == 1
        row = sb.store["position_events"][0]
        assert row["_on_conflict"] == "workspace_id,date,ticker"
        assert row["workspace_id"] == _HOUSE
        assert row["price"] == 42.5


class TestLegacyConflictTargetsGone:
    def test_group_a_book_upserts_target_workspace_id(self) -> None:
        widened = {
            "sync_positions_from_rebalance.py": 'on_conflict="workspace_id,date,ticker"',
            "backfill_execution_prices.py": 'on_conflict="workspace_id,date,ticker"',
            "reconcile_position_events_from_positions.py": 'on_conflict="workspace_id,date,ticker"',
            "materialize_snapshot.py": 'on_conflict="workspace_id,date,ticker"',
            "update_tearsheet.py": 'on_conflict="workspace_id,date"',
        }
        for name, needle in widened.items():
            text = (_SCRIPTS / name).read_text(encoding="utf-8")
            assert needle in text, f"{name} missing {needle}"
        tear = (_SCRIPTS / "update_tearsheet.py").read_text(encoding="utf-8")
        assert 'on_conflict="date,ticker"' not in tear
        assert 'nav_history").upsert(chunk, on_conflict="date")' not in tear
        assert 'portfolio_metrics").upsert([metrics], on_conflict="date")' not in tear
        sync = (_SCRIPTS / "sync_positions_from_rebalance.py").read_text(encoding="utf-8")
        assert 'on_conflict="date,ticker"' not in sync
