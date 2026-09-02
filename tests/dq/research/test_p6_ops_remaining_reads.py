"""P6: remaining house ops Group A reads ignore overlay same-date rows."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path
from typing import Any  # score:allow untyped any — PostgREST row dicts in fixtures

import pytest
from digiquant.dashboard.tenancy import house_workspace_id

from tests.fixtures.fake_supabase import FakeSupabaseClient

pytestmark = pytest.mark.unit

_SCRIPTS = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas"
_HOUSE = str(house_workspace_id())
_OVERLAY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def _load(name: str) -> Any:
    path = _SCRIPTS / f"{name}.py"
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    sys.modules.pop("position_entry_from_events", None)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pos(
    d: str,
    ticker: str,
    *,
    workspace_id: str,
    weight_pct: float = 10.0,
    thesis_id: str | None = None,
    entry_price: float | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": d,
        "ticker": ticker,
        "weight_pct": weight_pct,
        "workspace_id": workspace_id,
    }
    if thesis_id is not None:
        row["thesis_id"] = thesis_id
    if entry_price is not None:
        row["entry_price"] = entry_price
    return row


class TestRepairIgnoresOverlay:
    def test_zero_weight_select_and_delete_stay_on_house(self) -> None:
        mod = _load("repair_supabase_portfolio_data")
        rows = [
            _pos("2026-08-31", "IAU", workspace_id=_HOUSE, weight_pct=0),
            _pos("2026-08-31", "EVIL", workspace_id=_OVERLAY, weight_pct=0),
            _pos("2026-08-31", "CASH", workspace_id=_HOUSE, weight_pct=0),
        ]
        sb = FakeSupabaseClient(
            canned_reads={"positions": rows},
            store={"positions": [dict(r) for r in rows]},
        )
        found = {r["ticker"] for r in mod.house_zero_weight_non_cash(sb)}
        assert found == {"IAU"}
        mod.delete_house_zero_weight_non_cash(sb)
        remaining = {r["ticker"] for r in sb.store["positions"]}
        assert remaining == {"EVIL", "CASH"}


class TestSeedLedgerIgnoresOverlay:
    def test_latest_positions_date_ignores_later_overlay_row(self) -> None:
        mod = _load("seed_ledger_opening_snapshot")
        sb = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    _pos("2026-08-01", "IAU", workspace_id=_HOUSE),
                    _pos("2026-08-31", "EVIL", workspace_id=_OVERLAY),
                ]
            }
        )
        assert mod._latest_positions_date(sb) == date(2026, 8, 1)

    def test_overlay_only_book_is_not_a_house_seed_date(self) -> None:
        mod = _load("seed_ledger_opening_snapshot")
        sb = FakeSupabaseClient(
            canned_reads={"positions": [_pos("2026-08-31", "EVIL", workspace_id=_OVERLAY)]}
        )
        assert mod._latest_positions_date(sb) is None


class TestBackfillPositionEventsIgnoresOverlay:
    def test_max_event_date_ignores_later_overlay_row(self) -> None:
        mod = _load("backfill_position_events")
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [
                    {"date": "2026-08-01", "ticker": "IAU", "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "ticker": "EVIL", "workspace_id": _OVERLAY},
                ]
            }
        )
        assert str(mod._max_event_date(sb))[:10] == "2026-08-01"


class TestEnsureActivityIgnoresOverlay:
    def test_max_event_date_ignores_later_overlay_row(self) -> None:
        mod = _load("ensure_position_activity_through_today")
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [
                    {"date": "2026-08-01", "ticker": "IAU", "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "ticker": "EVIL", "workspace_id": _OVERLAY},
                ]
            }
        )
        assert mod._max_event_date(sb) == "2026-08-01"


class TestBackfillEntryFromEventsIgnoresOverlay:
    def test_distinct_dates_ignore_overlay_only_day(self) -> None:
        mod = _load("backfill_positions_entry_from_events")
        sb = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    _pos("2026-08-01", "IAU", workspace_id=_HOUSE),
                    _pos("2026-08-31", "EVIL", workspace_id=_OVERLAY),
                ]
            }
        )
        assert mod._distinct_position_dates(sb) == ["2026-08-01"]


class TestValidateDbFirstIgnoresOverlay:
    def test_zero_weight_check_ignores_overlay_row(self) -> None:
        mod = _load("validate_db_first")
        sb = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    _pos("2026-08-31", "IAU", workspace_id=_HOUSE, weight_pct=10),
                    _pos("2026-08-31", "EVIL", workspace_id=_OVERLAY, weight_pct=0),
                ]
            }
        )
        assert mod.house_zero_weight_non_cash_on_date(sb, "2026-08-31") == []

    def test_latest_nav_and_metrics_ignore_later_overlay_rows(self) -> None:
        mod = _load("validate_db_first")
        sb = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-08-01", "nav": 100.0, "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "nav": 999.0, "workspace_id": _OVERLAY},
                ],
                "portfolio_metrics": [
                    {"date": "2026-08-01", "sharpe": 1.0, "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "sharpe": 9.0, "workspace_id": _OVERLAY},
                ],
            }
        )
        assert mod.latest_house_nav_date(sb) == "2026-08-01"
        assert mod.latest_house_metrics_date(sb) == "2026-08-01"


class TestExportStateIgnoresOverlay:
    def test_positions_export_drops_overlay_rows(self) -> None:
        mod = _load("backfill_export_state")
        sb = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    _pos("2026-08-15", "IAU", workspace_id=_HOUSE),
                    _pos("2026-08-15", "EVIL", workspace_id=_OVERLAY),
                ]
            }
        )
        rows = mod.house_positions_in_range(sb, "2026-08-01", "2026-08-31")
        assert [r["ticker"] for r in rows] == ["IAU"]


class TestBackfillPmThesisMapIsHouseScoped:
    def test_source_pins_eq_house_workspace(self) -> None:
        text = (_SCRIPTS / "backfill_pm_rebalance_and_activity.py").read_text(encoding="utf-8")
        assert 'eq_house_workspace(sb.table("positions").select("ticker,thesis_id"))' in text
        assert 'sb.table("positions").select("ticker,thesis_id").eq("date", d)' not in text


class TestBackfillEventReasonsIgnoresOverlay:
    def test_house_event_page_drops_overlay_listed_first(self) -> None:
        mod = _load("backfill_position_event_reasons")
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [
                    {
                        "id": "ov",
                        "date": "2026-08-31",
                        "ticker": "EVIL",
                        "event": "HOLD",
                        "reason": "HOLD",
                        "workspace_id": _OVERLAY,
                    },
                    {
                        "id": "hs",
                        "date": "2026-08-31",
                        "ticker": "IAU",
                        "event": "HOLD",
                        "reason": "HOLD",
                        "workspace_id": _HOUSE,
                    },
                ]
            }
        )
        rows = mod._house_event_page(sb, 0, 800)
        assert [r["ticker"] for r in rows] == ["IAU"]
        assert [r["id"] for r in rows] == ["hs"]


class TestAuditCoverageIgnoresOverlay:
    def test_group_a_max_date_ignores_later_overlay_row(self) -> None:
        mod = _load("audit_activity_coverage_api")
        sb = FakeSupabaseClient(
            canned_reads={
                "position_events": [
                    {"date": "2026-08-01", "ticker": "IAU", "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "ticker": "EVIL", "workspace_id": _OVERLAY},
                ],
                "positions": [
                    _pos("2026-08-01", "IAU", workspace_id=_HOUSE),
                    _pos("2026-08-31", "EVIL", workspace_id=_OVERLAY),
                ],
                "nav_history": [
                    {"date": "2026-08-01", "nav": 100.0, "workspace_id": _HOUSE},
                    {"date": "2026-08-31", "nav": 999.0, "workspace_id": _OVERLAY},
                ],
            }
        )
        assert mod._max_date(sb, "position_events") == "2026-08-01"
        assert mod._max_date(sb, "positions") == "2026-08-01"
        assert mod._max_date(sb, "nav_history") == "2026-08-01"
