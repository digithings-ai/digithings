"""Unit tests for Olympus EOD accounting persistence (#2597, Task 3.2).

Covers: idempotent exact retry; provisional H9 never selected as final;
incomplete marks remain non-final; restatement supersedes; metrics consume
finalized period; mid-chain failure publishes no partial final.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any  # score:allow untyped any — fake Supabase row dicts in unit tests
from unittest.mock import MagicMock

import pytest
from digiquant.olympus.accounting.engine import compute_period
from digiquant.olympus.accounting.io import (
    CONTRIBUTIONS,
    HOLDINGS,
    PERIODS,
    AccountingPersistError,
    contribution_row_id,
    holding_row_id,
    period_children_complete,
    period_head,
    persist_period,
    select_final_period,
)
from digiquant.olympus.accounting.models import (
    AccountingPolicy,
    MarkObservation,
    OpeningHolding,
    PeriodAccountingInput,
    PeriodStatus,
    QualityReason,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

pytestmark = pytest.mark.unit

PERIOD = date(2026, 8, 25)
POLICY = AccountingPolicy(policy_version_id="accounting-v1")
EFFECTIVE = datetime(2026, 8, 25, 22, 0, tzinfo=UTC)


def _ts(hour: int = 21) -> datetime:
    return datetime(PERIOD.year, PERIOD.month, PERIOD.day, hour, 0, tzinfo=UTC)


def _mark(symbol: str, price: str, *, as_of: date | None = None) -> MarkObservation:
    return MarkObservation(
        symbol=symbol,
        price=Decimal(price),
        as_of=as_of or PERIOD,
        observed_at=_ts(),
    )


def _final_hold_input() -> PeriodAccountingInput:
    return PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("40000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "110"),),
    )


def _incomplete_input() -> PeriodAccountingInput:
    return PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("40000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(),  # missing closing mark → incomplete
    )


@dataclass
class _MergingQuery(_FakeQuery):
    """Reads from store ∪ canned so persist retries see prior INSERTs."""

    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._update_row is not None:
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        # Deduplicate by id when both present.
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for row in merged:
            key = str(row.get("id") or id(row))
            if key in seen:
                continue
            seen.add(key)
            if self._matches(row):
                rows.append(row)
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class MergingFake(FakeSupabaseClient):
    fail_table: str | None = None
    fail_after_n: int = 0
    _insert_counts: dict[str, int] = field(default_factory=dict)

    def table(self, name: str) -> _MergingQuery:
        q = _MergingQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )
        original_insert = q.insert
        client = self

        def gated_insert(row: dict[str, Any] | list[dict[str, Any]]) -> _MergingQuery:
            if client.fail_table == name:
                client._insert_counts[name] = client._insert_counts.get(name, 0) + 1
                if client._insert_counts[name] > client.fail_after_n:
                    raise RuntimeError(f"simulated insert failure on {name}")
            return original_insert(row)

        q.insert = gated_insert  # type: ignore[method-assign]
        return q


def test_persist_writes_period_contributions_and_holdings() -> None:
    client = MergingFake()
    period = compute_period(_final_hold_input())
    result = persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert result.wrote is True
    assert result.repaired is False
    assert len(client.store[PERIODS]) == 1
    assert client.store[PERIODS][0]["status"] == "final"
    assert len(client.store[CONTRIBUTIONS]) == 1
    assert client.store[CONTRIBUTIONS][0]["symbol"] == "AAPL"
    assert client.store[CONTRIBUTIONS][0]["id"] == str(contribution_row_id(period.id, "AAPL"))
    assert len(client.store[HOLDINGS]) == 1
    assert client.store[HOLDINGS][0]["id"] == str(holding_row_id(period.id, "AAPL"))
    # insert only — never upsert
    assert all("_on_conflict" not in r for rows in client.store.values() for r in rows)


def test_exact_retry_is_idempotent_noop() -> None:
    client = MergingFake()
    period = compute_period(_final_hold_input())
    first = persist_period(client=client, period=period, effective_at=EFFECTIVE)
    second = persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert first.wrote is True
    assert second.wrote is False
    assert second.repaired is False
    assert len(client.store[PERIODS]) == 1
    assert len(client.store[CONTRIBUTIONS]) == 1
    assert len(client.store[HOLDINGS]) == 1


def test_mid_chain_failure_publishes_no_partial_final() -> None:
    """Period INSERT succeeds; contributions fail — select_final must return None."""
    client = MergingFake(fail_table=CONTRIBUTIONS, fail_after_n=0)
    period = compute_period(_final_hold_input())
    with pytest.raises(RuntimeError, match="simulated insert failure"):
        persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert len(client.store.get(PERIODS, [])) == 1
    assert client.store.get(CONTRIBUTIONS, []) == []
    assert select_final_period(client=client, period_date=PERIOD) is None
    assert period_children_complete(client=client, period=period) is False

    # Exact retry repairs children and then final is selectable.
    client.fail_table = None
    repaired = persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert repaired.wrote is False
    assert repaired.repaired is True
    final = select_final_period(client=client, period_date=PERIOD)
    assert final is not None
    assert final["id"] == str(period.id)


def test_incomplete_marks_remain_non_final() -> None:
    client = MergingFake()
    period = compute_period(_incomplete_input())
    assert period.status is PeriodStatus.INCOMPLETE
    assert QualityReason.MISSING_CLOSING_MARK in period.quality_reasons
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert period_head(client=client, period_date=PERIOD)["status"] == "incomplete"
    assert select_final_period(client=client, period_date=PERIOD) is None


def test_provisional_h9_nav_cannot_be_selected_as_final() -> None:
    """nav_history continuity rows are not accounting periods."""
    client = MergingFake(
        canned_reads={
            "nav_history": [
                {"date": PERIOD.isoformat(), "nav": 105.0, "cash_pct": 10.0},
            ]
        }
    )
    assert select_final_period(client=client, period_date=PERIOD) is None
    # Even with an incomplete accounting row, provisional NAV must not promote it.
    period = compute_period(_incomplete_input())
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    assert select_final_period(client=client, period_date=PERIOD) is None


def test_restatement_supersedes_prior_head() -> None:
    client = MergingFake()
    first = compute_period(_final_hold_input())
    persist_period(client=client, period=first, effective_at=EFFECTIVE)

    # Different closing mark → different period id; supersedes the prior head.
    restated_inp = PeriodAccountingInput(
        period_date=PERIOD,
        policy=POLICY,
        opening_cash=Decimal("40000"),
        opening_holdings=(OpeningHolding(symbol="AAPL", quantity=Decimal("100")),),
        opening_marks=(_mark("AAPL", "100", as_of=date(2026, 8, 24)),),
        closing_marks=(_mark("AAPL", "112"),),
    )
    second = compute_period(restated_inp)
    assert second.id != first.id
    result = persist_period(client=client, period=second, effective_at=EFFECTIVE)
    assert result.wrote is True
    assert result.superseded_id == first.id
    assert len(client.store[PERIODS]) == 2
    head = period_head(client=client, period_date=PERIOD)
    assert head is not None
    assert head["id"] == str(second.id)
    assert head["supersedes_id"] == str(first.id)
    final = select_final_period(client=client, period_date=PERIOD)
    assert final is not None
    assert final["id"] == str(second.id)


def test_payload_collision_raises() -> None:
    client = MergingFake()
    period = compute_period(_final_hold_input())
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    # Mutate stored opening_equity so exact-id retry sees a divergent payload.
    client.store[PERIODS][0]["opening_equity"] = "99999"
    with pytest.raises(AccountingPersistError, match="different payload"):
        persist_period(client=client, period=period, effective_at=EFFECTIVE)


# ─── metrics consume finalized period ───────────────────────────────────────

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "refresh_performance_metrics.py"
)


def _load_metrics_mod():
    stub = MagicMock()
    stub.patch_positions_entries_for_date = MagicMock(return_value=0)
    sys.modules.setdefault("position_entry_from_events", stub)
    spec = importlib.util.spec_from_file_location("refresh_performance_metrics_2597", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_metrics_prefer_finalized_period_over_attribution() -> None:
    mod = _load_metrics_mod()
    client = MergingFake()
    period = compute_period(_final_hold_input())
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    # Poison attribution with a 21-day-scale number that must NOT win.
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

    # Seed canned period/children for select (MergingFake already has store).
    mod.upsert_portfolio_metrics_daily(client, PERIOD.isoformat())
    rows = client.store.get("portfolio_metrics", [])
    assert rows, "expected portfolio_metrics upsert"
    # Final period return: (51000-50000)/50000 * 100 = 2.0
    assert rows[0]["pnl_pct"] == pytest.approx(2.0, abs=1e-6)


def test_metrics_ignore_incomplete_period() -> None:
    mod = _load_metrics_mod()
    client = MergingFake()
    period = compute_period(_incomplete_input())
    persist_period(client=client, period=period, effective_at=EFFECTIVE)
    client.canned_reads["position_attribution"] = []
    client.canned_reads["nav_history"] = [
        {"date": "2026-08-24", "nav": 100.0},
        {"date": PERIOD.isoformat(), "nav": 101.5},
    ]
    client.canned_reads["portfolio_metrics"] = []
    client.canned_reads["positions"] = []
    client.canned_reads["price_history"] = []
    mod.upsert_portfolio_metrics_daily(client, PERIOD.isoformat())
    rows = client.store.get("portfolio_metrics", [])
    assert rows
    # Falls through to nav day return 1.5%, not accounting.
    assert rows[0]["pnl_pct"] == pytest.approx(1.5, abs=1e-6)


# ─── finalizer script: dry-run / cold decline ────────────────────────────────

_FINALIZE = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "atlas"
    / "finalize_period_accounting.py"
)


def _load_finalize_mod():
    spec = importlib.util.spec_from_file_location("finalize_period_accounting_2597", _FINALIZE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_resolve_mode_dry_run_and_shadow() -> None:
    mod = _load_finalize_mod()
    assert mod.resolve_mode(cli_mode=None, dry_run=True, shadow=False) == "dry-run"
    assert mod.resolve_mode(cli_mode=None, dry_run=False, shadow=True) == "shadow"
    assert mod.resolve_mode(cli_mode="off", dry_run=False, shadow=False) == "off"


def test_cold_ledger_declines_without_write() -> None:
    mod = _load_finalize_mod()
    from digiquant.olympus.hermes.writers.execution_io import HOLDING_LOTS

    client = MergingFake(
        canned_reads={
            HOLDING_LOTS: [],
            "positions": [
                {
                    "date": "2026-08-24",
                    "ticker": "AAPL",
                    "weight_pct": 50.0,
                    "entry_price": 100.0,
                }
            ],
            "nav_history": [{"date": "2026-08-24", "nav": 100.0}],
            "price_history": [],
            PERIODS: [],
        }
    )
    with pytest.raises(mod.FinalizerDeclined, match="ledger cold"):
        mod.finalize_one_day(client=client, period_date=PERIOD, mode="shadow")
    assert client.store.get(PERIODS, []) == []


def test_dry_run_writes_nothing() -> None:
    mod = _load_finalize_mod()
    from digiquant.olympus.hermes.writers.execution_io import HOLDING_LOTS

    client = MergingFake(
        canned_reads={
            HOLDING_LOTS: [],
            "positions": [],
            "nav_history": [],
            "price_history": [],
            PERIODS: [],
        }
    )
    period, result, _ok = mod.finalize_one_day(client=client, period_date=PERIOD, mode="dry-run")
    assert result is None
    assert client.store.get(PERIODS, []) == []
    assert period.status in {
        PeriodStatus.FINAL,
        PeriodStatus.INCOMPLETE,
        PeriodStatus.ESTIMATED,
        PeriodStatus.FAILED,
    }


def test_opening_quantities_pages_past_postgrest_max_rows() -> None:
    """Closed-lot history >1000 must not drop a later open lot (#2776 / WP3 review)."""
    mod = _load_finalize_mod()
    from digiquant.olympus.hermes.models.portfolio_ledger import HoldingLotStatus
    from digiquant.olympus.hermes.writers.execution_io import HOLDING_LOTS

    closed_lots = [
        {
            "id": f"closed-{i}",
            "opened_by_execution_id": f"exec-closed-{i}",
            "opened_at": "2026-01-01T15:00:00+00:00",
            "run_date": "2026-01-01",
            "quantity": "1",
            "status": HoldingLotStatus.CLOSED,
            "closed_at": "2026-01-02T15:00:00+00:00",
            "symbol": f"ZZZ{i:04d}",
        }
        for i in range(1000)
    ]
    open_lot = {
        "id": "open-aapl",
        "opened_by_execution_id": "exec-aapl",
        "opened_at": "2026-08-20T15:00:00+00:00",
        "run_date": "2026-08-20",
        "quantity": "100",
        "status": HoldingLotStatus.OPEN,
        "closed_at": None,
        "symbol": "AAPL",
    }
    client = MergingFake(canned_reads={HOLDING_LOTS: [*closed_lots, open_lot]})
    qty = mod._opening_quantities(client=client, period_date=PERIOD)
    assert qty.get("AAPL") == Decimal("100")
    # Unpaginated PostgREST would return only the first 1000 (all closed) and miss AAPL.
    assert len(closed_lots) == mod._LOT_PAGE_SIZE


def test_legacy_nav_day_return_ignores_overlay_nav() -> None:
    from digiquant.olympus.tenancy import house_workspace_id

    mod = _load_finalize_mod()
    overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    house = str(house_workspace_id())
    client = FakeSupabaseClient(
        canned_reads={
            "nav_history": [
                {"date": "2026-08-25", "nav": 999.0, "workspace_id": overlay},
                {"date": "2026-08-24", "nav": 1.0, "workspace_id": overlay},
                {"date": "2026-08-25", "nav": 101.0, "workspace_id": house},
                {"date": "2026-08-24", "nav": 100.0, "workspace_id": house},
            ]
        }
    )
    got = mod._legacy_nav_day_return_pct(client=client, period_date=PERIOD)
    assert got == Decimal("1")


def test_opening_cash_ignores_overlay_nav_and_cash_weight() -> None:
    from digiquant.olympus.tenancy import house_workspace_id

    mod = _load_finalize_mod()
    overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    house = str(house_workspace_id())
    client = FakeSupabaseClient(
        canned_reads={
            "nav_history": [
                {
                    "date": "2026-08-24",
                    "nav": 999.0,
                    "cash_pct": 99.0,
                    "workspace_id": overlay,
                },
                {
                    "date": "2026-08-24",
                    "nav": 100.0,
                    "workspace_id": house,
                },
            ],
            "positions": [
                {
                    "date": "2026-08-24",
                    "ticker": "CASH",
                    "weight_pct": 99.0,
                    "workspace_id": overlay,
                },
                {
                    "date": "2026-08-24",
                    "ticker": "CASH",
                    "weight_pct": 20.0,
                    "workspace_id": house,
                },
            ],
        }
    )
    got = mod._opening_cash(client=client, period_date=PERIOD)
    assert got == Decimal("20.00")
