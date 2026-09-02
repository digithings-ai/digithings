"""Unit tests for execution broker mirror sync (K4)."""

# score:allow untyped any
# Fake PostgREST rows are heterogeneous dicts matching Supabase payloads.

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from digiquant.brokers.connections import (
    AuthKind,
    Broker,
    BrokerConnection,
    ConnectionEnv,
    ConnectionStatus,
)
from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderStatus,
    BrokerPosition,
)
from digiquant.execution.router import BROKER_ORDERS, broker_order_status_id
from digiquant.execution.sync import (
    ALPACA_MAX_CALLS_PER_CYCLE,
    BROKER_EXECUTIONS,
    BROKER_POSITION_SNAPSHOTS,
    SyncBudgetExceeded,
    SyncCursor,
    broker_execution_id,
    sync_connection,
)

pytestmark = pytest.mark.unit

_WS = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_CONN = UUID("11111111-2222-3333-4444-555555555555")
_ORDER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_NOW = datetime(2026, 8, 30, 14, 0, tzinfo=UTC)
_CURSOR = SyncCursor(fills_since=datetime(2026, 8, 30, 12, 0, tzinfo=UTC))


class _FakeResult:
    def __init__(self, data: list[dict[str, Any]] | None = None) -> None:
        self.data = data or []


class _FakeQuery:
    def __init__(self, store: dict[str, list[dict[str, Any]]], table: str) -> None:
        self._store = store
        self._table = table
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list[Any]]] = []
        self._pending_insert: list[dict[str, Any]] | None = None

    def select(self, _cols: str) -> _FakeQuery:
        return self

    def eq(self, col: str, val: Any) -> _FakeQuery:
        self._filters.append((col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> _FakeQuery:
        self._in_filters.append((col, list(vals)))
        return self

    def insert(self, rows: list[dict[str, Any]] | dict[str, Any]) -> _FakeQuery:
        self._pending_insert = rows if isinstance(rows, list) else [rows]
        return self

    def execute(self) -> _FakeResult:
        if self._pending_insert is not None:
            table_rows = self._store.setdefault(self._table, [])
            # Simulate UNIQUE collision on broker_executions.id / snapshots.
            existing_ids = {str(r.get("id")) for r in table_rows}
            for row in self._pending_insert:
                if str(row.get("id")) in existing_ids:
                    raise RuntimeError("duplicate key value violates unique constraint")
                table_rows.append(row)
                existing_ids.add(str(row.get("id")))
            inserted = self._pending_insert
            self._pending_insert = None
            return _FakeResult(inserted)
        rows = list(self._store.get(self._table, []))
        for col, val in self._filters:
            rows = [r for r in rows if str(r.get(col)) == str(val)]
        for col, vals in self._in_filters:
            allowed = {str(v) for v in vals}
            rows = [r for r in rows if str(r.get(col)) in allowed]
        return _FakeResult(rows)


class _FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self.store = store

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self.store, name)


def _connection(*, broker: Broker = Broker.ALPACA) -> BrokerConnection:
    return BrokerConnection(
        id=_CONN,
        workspace_id=_WS,
        broker=broker,
        env=ConnectionEnv.PAPER,
        auth_kind=AuthKind.API_KEY,
        ciphertext=b"\x00" * 32,
        nonce=b"\x00" * 12,
        key_id="v1",
        fingerprint="deadbeef",
        scopes=(),
        status=ConnectionStatus.ACTIVE,
        created_at=_NOW,
    )


def _seed_order(*, status: str = "accepted") -> dict[str, Any]:
    return {
        "id": str(_ORDER),
        "workspace_id": str(_WS),
        "connection_id": str(_CONN),
        "order_intent_id": str(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        "client_order_id": "intent-1",
        "external_order_id": "ext-1",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": "5",
        "notional": None,
        "order_type": "market",
        "time_in_force": "day",
        "status": status,
        "supersedes_id": None,
        "raw_payload_sha256": "b" * 64,
        "submitted_at": _NOW.isoformat(),
        "recorded_at": _NOW.isoformat(),
    }


class _SyncAdapter:
    name = "sync-fake"

    def __init__(
        self,
        *,
        status: BrokerOrderStatus = BrokerOrderStatus.FILLED,
        fills: list[BrokerFill] | None = None,
        positions: list[BrokerPosition] | None = None,
        call_log: list[str] | None = None,
    ) -> None:
        self.status = status
        self.fills = fills or []
        self.positions = positions or []
        self.call_log = call_log if call_log is not None else []
        self.submitted: list[Any] = []

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_account(self) -> BrokerAccountSnapshot:
        self.call_log.append("get_account")
        return BrokerAccountSnapshot(
            account_id="acct-1",
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("50000"),
            currency="USD",
            as_of=_NOW,
        )

    def get_positions(self) -> list[BrokerPosition]:
        self.call_log.append("get_positions")
        return list(self.positions)

    def submit_order(self, req: Any) -> BrokerOrderAck:
        self.submitted.append(req)
        raise AssertionError("sync must never submit corrective orders")

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        self.call_log.append(f"get_order:{external_order_id}")
        return BrokerOrderAck(
            external_order_id=external_order_id,
            status=self.status,
            submitted_at=_NOW,
            raw_sha256="c" * 64,
        )

    def cancel_order(self, external_order_id: str) -> None:
        raise AssertionError("sync must never cancel orders")

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        self.call_log.append(f"list_fills:{since.isoformat()}")
        return [f for f in self.fills if f.executed_at >= since]


def _fill(*, fill_id: str = "fill-1", qty: str = "5", when: datetime | None = None) -> BrokerFill:
    return BrokerFill(
        external_fill_id=fill_id,
        symbol="AAPL",
        quantity=Decimal(qty),
        price=Decimal("100"),
        fee=Decimal("0"),
        executed_at=when or (_NOW - timedelta(minutes=5)),
    )


def test_same_fill_twice_one_row() -> None:
    store = {
        BROKER_ORDERS: [_seed_order()],
        BROKER_EXECUTIONS: [],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    fill = _fill()
    adapter = _SyncAdapter(fills=[fill], positions=[])
    client = _FakeClient(store)

    first = sync_connection(
        client=client,
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    assert first.fills_appended == 1
    assert len(store[BROKER_EXECUTIONS]) == 1
    expected_id = broker_execution_id(_CONN, "fill-1")
    assert store[BROKER_EXECUTIONS][0]["id"] == str(expected_id)

    second = sync_connection(
        client=client,
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    assert second.fills_appended == 0
    assert second.fills_already_present == 1
    assert len(store[BROKER_EXECUTIONS]) == 1


def test_status_supersede_chain() -> None:
    store = {
        BROKER_ORDERS: [_seed_order(status="accepted")],
        BROKER_EXECUTIONS: [],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    adapter = _SyncAdapter(status=BrokerOrderStatus.FILLED, fills=[], positions=[])
    result = sync_connection(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    assert result.status_rows_appended == 1
    assert len(store[BROKER_ORDERS]) == 2
    new_row = next(r for r in store[BROKER_ORDERS] if r.get("supersedes_id"))
    assert new_row["supersedes_id"] == str(_ORDER)
    assert new_row["status"] == "filled"
    assert new_row["id"] == str(broker_order_status_id(_ORDER, BrokerOrderStatus.FILLED, _NOW))


def test_cursor_advances_to_latest_fill() -> None:
    later = _NOW - timedelta(minutes=1)
    store = {
        BROKER_ORDERS: [_seed_order()],
        BROKER_EXECUTIONS: [],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    adapter = _SyncAdapter(fills=[_fill(when=later)], positions=[])
    result = sync_connection(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    assert result.cursor is not None
    assert result.cursor.fills_since == later
    assert result.cursor.fills_since > _CURSOR.fills_since


def test_alpaca_budget_guard() -> None:
    """More heads than the Alpaca cycle budget → stop before exceeding the cap."""
    orders = []
    for i in range(ALPACA_MAX_CALLS_PER_CYCLE + 3):
        row = _seed_order()
        row = dict(row)
        row["id"] = str(UUID(int=i + 1))
        row["external_order_id"] = f"ext-{i}"
        orders.append(row)
    store = {
        BROKER_ORDERS: orders,
        BROKER_EXECUTIONS: [],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    call_log: list[str] = []
    adapter = _SyncAdapter(fills=[], positions=[], call_log=call_log)
    result = sync_connection(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(broker=Broker.ALPACA),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    get_order_calls = [c for c in call_log if c.startswith("get_order:")]
    assert len(get_order_calls) <= ALPACA_MAX_CALLS_PER_CYCLE
    assert result.calls_used <= ALPACA_MAX_CALLS_PER_CYCLE
    # Budget exhausted during status pull → fills skipped (no list_fills charge left).
    assert not any(c.startswith("list_fills:") for c in call_log)


def test_reconciliation_never_trades() -> None:
    store = {
        BROKER_ORDERS: [_seed_order(status="filled")],
        BROKER_EXECUTIONS: [
            {
                "id": str(broker_execution_id(_CONN, "fill-1")),
                "workspace_id": str(_WS),
                "broker_order_id": str(_ORDER),
                "external_fill_id": "fill-1",
                "symbol": "AAPL",
                "quantity": "5",
                "price": "100",
                "fee": "0",
                "executed_at": _NOW.isoformat(),
                "recorded_at": _NOW.isoformat(),
            }
        ],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    # Broker reports 3 shares; mirror expects 5 → diverge.
    positions = [
        BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("3"),
            avg_entry_price=Decimal("100"),
            market_value=Decimal("300"),
            unrealized_pl=Decimal("0"),
        )
    ]
    adapter = _SyncAdapter(fills=[], positions=positions)
    result = sync_connection(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=True,
    )
    assert result.reconciliation_diverged is True
    assert result.reconciliation_report is not None
    assert result.reconciliation_report["corrective_orders"] == []
    assert result.refused_corrective_orders is True
    assert adapter.submitted == []
    assert len(store[BROKER_POSITION_SNAPSHOTS]) == 1
    snap = store[BROKER_POSITION_SNAPSHOTS][0]
    assert snap["reconciliation_diverged"] is True


def test_sync_module_has_no_upsert() -> None:
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[4] / "digiquant/src/digiquant/execution/sync.py"
    ).read_text(encoding="utf-8")
    assert ".upsert(" not in text


def test_sync_budget_exceeded_type() -> None:
    assert issubclass(SyncBudgetExceeded, RuntimeError)


def test_orphan_fill_holds_cursor() -> None:
    """Orphan at T1 + linked fill at T2 must not advance cursor past the orphan."""
    t1 = _NOW - timedelta(minutes=10)
    t2 = _NOW - timedelta(minutes=1)
    store = {
        BROKER_ORDERS: [_seed_order(status="filled")],
        BROKER_EXECUTIONS: [],
        BROKER_POSITION_SNAPSHOTS: [],
    }
    # Orphan: symbol with no matching head (MSFT); linked: AAPL.
    orphan = BrokerFill(
        external_fill_id="orphan-1",
        symbol="MSFT",
        quantity=Decimal("1"),
        price=Decimal("50"),
        fee=None,
        executed_at=t1,
    )
    linked = _fill(fill_id="fill-linked", qty="5", when=t2)
    adapter = _SyncAdapter(fills=[orphan, linked], positions=[])
    result = sync_connection(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        cursor=_CURSOR,
        now=_NOW,
        pull_snapshot=False,
    )
    assert result.fills_appended == 1
    assert result.unlinked_fills_held_cursor is True
    assert "orphan-1" in result.unlinked_fill_ids
    assert result.cursor is not None
    # Held at previous cursor so exclusive-since adapters re-read the orphan.
    assert result.cursor.fills_since == _CURSOR.fills_since
    assert result.cursor.fills_since < t2
