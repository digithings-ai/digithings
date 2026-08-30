"""K4 sync batch tail — execution-alert dispatch hook."""

from __future__ import annotations

from datetime import UTC, datetime
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
from digiquant.brokers.contracts import BrokerAccountSnapshot, BrokerOrderStatus
from digiquant.brokers.stubs import AlpacaAdapterStub
from digiquant.olympus.kairos.sync import SyncCursor, run_sync_batch

pytestmark = pytest.mark.unit

_CONN = UUID("11111111-2222-3333-4444-555555555555")
_WS = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
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
        self._pending_insert: list[dict[str, Any]] | None = None

    def select(self, _cols: str) -> _FakeQuery:
        return self

    def eq(self, col: str, val: Any) -> _FakeQuery:
        self._filters.append((col, val))
        return self

    def insert(self, rows: list[dict[str, Any]] | dict[str, Any]) -> _FakeQuery:
        self._pending_insert = rows if isinstance(rows, list) else [rows]
        return self

    def execute(self) -> _FakeResult:
        if self._pending_insert is not None:
            self._store.setdefault(self._table, []).extend(self._pending_insert)
            self._pending_insert = None
            return _FakeResult([])
        rows = list(self._store.get(self._table, []))
        for col, val in self._filters:
            rows = [r for r in rows if r.get(col) == val]
        return _FakeResult(rows)


class _FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]]) -> None:
        self._store = store

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self._store, name)


class _MinimalAdapter(AlpacaAdapterStub):
    """Adapter that returns empty mirror reads without NotImplementedError."""

    def get_order(self, external_order_id: str) -> Any:
        from digiquant.brokers.contracts import BrokerOrderAck

        return BrokerOrderAck(
            external_order_id=external_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            submitted_at=_NOW,
            raw_sha256="a" * 64,
        )

    def list_fills(self, since: datetime) -> list:
        return []

    def get_positions(self) -> list:
        return []

    def get_account(self) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id="paper",
            equity=Decimal("100000"),
            cash=Decimal("100000"),
            buying_power=Decimal("100000"),
            currency="USD",
            as_of=_NOW,
        )


def test_run_sync_batch_dispatches_execution_alerts_fail_soft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _boom(*_a: object, **_k: object) -> None:
        calls.append("dispatch")
        raise RuntimeError("mailgun down")

    monkeypatch.setattr(
        "digiquant.notify.dispatch.dispatch_execution_alerts",
        _boom,
    )

    connection = BrokerConnection(
        id=_CONN,
        workspace_id=_WS,
        broker=Broker.ALPACA,
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
    client = _FakeClient({"broker_orders": []})

    results = run_sync_batch(
        client=client,
        cycles=[(_MinimalAdapter(), connection, _CURSOR)],
        now=_NOW,
        pull_snapshot=True,
    )
    assert len(results) == 1
    assert calls == ["dispatch"]
