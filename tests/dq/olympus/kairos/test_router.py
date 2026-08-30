"""Unit tests for Kairos venue policy + order-intent router (K4)."""

# score:allow untyped any, notimplementederror stub
# Fake BrokerAdapter unused methods raise; fake PostgREST rows are untyped dicts.

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from digiquant.brokers.connections import (
    AuthKind,
    Broker,
    BrokerConnection,
    ConnectionEnv,
    ConnectionStatus,
)
from digiquant.brokers.contracts import (
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    ExecutionVenue,
    LiveVenueNotAuthorizedError,
    OrderSide,
)
from digiquant.olympus.hermes.models.portfolio_ledger import DecisionAction
from digiquant.olympus.kairos.policy import (
    AmbiguousVenueError,
    InconsistentOrderChainError,
    resolve_venue,
    routing_enabled,
)
from digiquant.olympus.kairos.router import (
    BROKER_ORDERS,
    broker_order_id,
    route_pending_orders,
    side_from_action,
)
from digiquant.olympus.tenancy import house_workspace_id

pytestmark = pytest.mark.unit

_WS = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_CONN = UUID("11111111-2222-3333-4444-555555555555")
_RUN = date(2026, 8, 29)
_NOW = datetime(2026, 8, 30, 13, 30, tzinfo=UTC)


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
        payload = rows if isinstance(rows, list) else [rows]
        self._pending_insert = payload
        return self

    def execute(self) -> _FakeResult:
        if self._pending_insert is not None:
            self._store.setdefault(self._table, []).extend(self._pending_insert)
            inserted = self._pending_insert
            self._pending_insert = None
            return _FakeResult(inserted)
        rows = list(self._store.get(self._table, []))
        house = str(house_workspace_id())
        for col, val in self._filters:
            rows = [
                r
                for r in rows
                if str(r.get(col)) == str(val)
                or (col == "workspace_id" and str(val) == house and r.get(col) is None)
            ]
        for col, vals in self._in_filters:
            allowed = {str(v) for v in vals}
            rows = [r for r in rows if str(r.get(col)) in allowed]
        return _FakeResult(rows)


class _FakeClient:
    def __init__(self, store: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.store = store or {}

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self.store, name)


class _FakeAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.submitted: list[BrokerOrderRequest] = []

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def get_account(self) -> Any:
        raise NotImplementedError

    def get_positions(self) -> list[Any]:
        raise NotImplementedError

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        self.submitted.append(req)
        return BrokerOrderAck(
            external_order_id=f"ext-{req.client_order_id[:8]}",
            status=BrokerOrderStatus.ACCEPTED,
            submitted_at=_NOW,
            raw_sha256="a" * 64,
        )

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        raise NotImplementedError

    def cancel_order(self, external_order_id: str) -> None:
        raise NotImplementedError

    def list_fills(self, since: datetime) -> list[Any]:
        raise NotImplementedError


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


@pytest.fixture(autouse=True)
def _clear_routing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_KAIROS_ROUTING", raising=False)


def test_routing_enabled_defaults_off() -> None:
    assert routing_enabled() is False


def test_routing_enabled_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    assert routing_enabled() is True


def test_house_workspace_always_paper_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    assert (
        resolve_venue(None, active_paper_brokers=[Broker.ALPACA]) is ExecutionVenue.PAPER_INTERNAL
    )


def test_kill_switch_off_forces_paper_internal() -> None:
    assert resolve_venue(_WS, active_paper_brokers=[Broker.ALPACA]) is ExecutionVenue.PAPER_INTERNAL


def test_active_alpaca_paper_when_routing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "on")
    assert resolve_venue(_WS, active_paper_brokers=[Broker.ALPACA]) is ExecutionVenue.ALPACA_PAPER


def test_active_ibkr_paper_when_routing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "true")
    assert resolve_venue(_WS, active_paper_brokers=["ibkr"]) is ExecutionVenue.IBKR_PAPER


def test_ambiguous_brokers_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    with pytest.raises(AmbiguousVenueError):
        resolve_venue(_WS, active_paper_brokers=[Broker.ALPACA, Broker.IBKR])


def test_live_venue_raises() -> None:
    """Test-pinned invariant: resolve_venue never returns *_LIVE."""
    from digiquant.olympus.kairos import policy as policy_mod

    with pytest.raises(LiveVenueNotAuthorizedError):
        policy_mod._assert_not_live(ExecutionVenue.ALPACA_LIVE)
    with pytest.raises(LiveVenueNotAuthorizedError):
        policy_mod._assert_not_live(ExecutionVenue.IBKR_LIVE)


def test_side_from_action_mapping() -> None:
    assert side_from_action(DecisionAction.ADD) is OrderSide.BUY
    assert side_from_action(DecisionAction.TRIM) is OrderSide.SELL
    assert side_from_action(DecisionAction.EXIT) is OrderSide.SELL
    with pytest.raises(InconsistentOrderChainError):
        side_from_action(DecisionAction.NO_OP)
    with pytest.raises(InconsistentOrderChainError):
        side_from_action(DecisionAction.REJECT)


def test_broker_order_id_deterministic_collision() -> None:
    intent = uuid4()
    a = broker_order_id(intent, Broker.ALPACA, _RUN)
    b = broker_order_id(intent, Broker.ALPACA, _RUN)
    assert a == b
    assert a != broker_order_id(intent, Broker.IBKR, _RUN)
    assert a != broker_order_id(intent, Broker.ALPACA, date(2026, 8, 28))


def _chain_store(
    *,
    action: DecisionAction,
    order_id: UUID | None = None,
    quantity: str = "10",
    workspace_id: UUID = _WS,
) -> tuple[dict[str, list[dict[str, Any]]], UUID]:
    """Minimal ledger chain: decision → requested → approved → pending order."""
    decision_id = uuid4()
    requested_id = uuid4()
    approved_id = uuid4()
    oid = order_id or uuid4()
    ws = str(workspace_id)
    store: dict[str, list[dict[str, Any]]] = {
        "portfolio_ledger_decision_intents": [
            {
                "id": str(decision_id),
                "run_date": _RUN.isoformat(),
                "symbol": "AAPL",
                "action": action.value,
                "workspace_id": ws,
            }
        ],
        "portfolio_ledger_requested_targets": [
            {
                "id": str(requested_id),
                "run_date": _RUN.isoformat(),
                "decision_intent_id": str(decision_id),
                "symbol": "AAPL",
                "workspace_id": ws,
            }
        ],
        "portfolio_ledger_approved_targets": [
            {
                "id": str(approved_id),
                "run_date": _RUN.isoformat(),
                "requested_target_id": str(requested_id),
                "symbol": "AAPL",
                "supersedes_id": None,
                "workspace_id": ws,
            }
        ],
        "portfolio_ledger_order_intents": [
            {
                "id": str(oid),
                "run_date": _RUN.isoformat(),
                "approved_target_id": str(approved_id),
                "symbol": "AAPL",
                "quantity": quantity,
                "status": "pending",
                "supersedes_id": None,
                "workspace_id": ws,
            }
        ],
        "portfolio_ledger_commits": [
            {"id": str(uuid4()), "run_date": _RUN.isoformat(), "workspace_id": ws},
        ],
        BROKER_ORDERS: [],
    }
    return store, oid


def _merge_stores(
    *stores: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    merged: dict[str, list[dict[str, Any]]] = {}
    for store in stores:
        for table, rows in store.items():
            merged.setdefault(table, []).extend(rows)
    return merged


def test_route_skips_when_paper_internal() -> None:
    store, _ = _chain_store(action=DecisionAction.ADD)
    adapter = _FakeAdapter()
    result = route_pending_orders(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=_WS,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert result.skipped_paper_internal is True
    assert adapter.submitted == []
    assert store[BROKER_ORDERS] == []


def test_route_submits_and_mirrors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, oid = _chain_store(action=DecisionAction.ADD)
    adapter = _FakeAdapter()
    result = route_pending_orders(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=_WS,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert result.skipped_paper_internal is False
    assert result.venue is ExecutionVenue.ALPACA_PAPER
    assert len(adapter.submitted) == 1
    assert adapter.submitted[0].client_order_id == str(oid)
    assert adapter.submitted[0].side is OrderSide.BUY
    assert len(store[BROKER_ORDERS]) == 1
    row = store[BROKER_ORDERS][0]
    assert row["id"] == str(broker_order_id(oid, Broker.ALPACA, _RUN))
    assert row["order_intent_id"] == str(oid)


def test_route_refuses_inconsistent_noop_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, oid = _chain_store(action=DecisionAction.NO_OP)
    adapter = _FakeAdapter()
    result = route_pending_orders(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=_WS,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert adapter.submitted == []
    assert store[BROKER_ORDERS] == []
    assert any(oid_str == str(oid) for oid_str, _ in result.refused)


def test_route_deterministic_id_collision_on_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, _oid = _chain_store(action=DecisionAction.TRIM)
    adapter = _FakeAdapter()
    client = _FakeClient(store)
    first = route_pending_orders(
        client=client,
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=_WS,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert len(first.routed) == 1
    assert first.routed[0].already_mirrored is False
    assert adapter.submitted[0].side is OrderSide.SELL
    assert len(store[BROKER_ORDERS]) == 1

    second = route_pending_orders(
        client=client,
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=_WS,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert len(second.routed) == 1
    assert second.routed[0].already_mirrored is True
    assert len(adapter.submitted) == 1
    assert len(store[BROKER_ORDERS]) == 1


def test_router_module_has_no_upsert() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parents[4] / "digiquant/src/digiquant/olympus/kairos"
    for path in src.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert ".upsert(" not in text, f"upsert forbidden in {path.name}"


# --- Review probes (authority boundary) -----------------------------------------


def test_foreign_workspace_intents_never_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tenant-A connection must not submit tenant-B's same-date pending intents."""
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    ws_a = _WS
    ws_b = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    store_a, oid_a = _chain_store(action=DecisionAction.ADD, workspace_id=ws_a)
    store_b, oid_b = _chain_store(action=DecisionAction.ADD, workspace_id=ws_b)
    # Give B a distinct symbol so a mistaken cross-submit is obvious in side/symbol.
    store_b["portfolio_ledger_order_intents"][0]["symbol"] = "MSFT"
    store_b["portfolio_ledger_decision_intents"][0]["symbol"] = "MSFT"
    store_b["portfolio_ledger_requested_targets"][0]["symbol"] = "MSFT"
    store_b["portfolio_ledger_approved_targets"][0]["symbol"] = "MSFT"
    store = _merge_stores(store_a, store_b)
    adapter = _FakeAdapter()
    result = route_pending_orders(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),  # workspace A
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=ws_a,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert result.skipped_paper_internal is False
    submitted_ids = {req.client_order_id for req in adapter.submitted}
    assert str(oid_a) in submitted_ids
    assert str(oid_b) not in submitted_ids
    assert all(req.symbol == "AAPL" for req in adapter.submitted)


def test_workspace_none_never_substituted_with_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """workspace_id=None must stay house ⇒ PAPER_INTERNAL (no connection.workspace remap)."""
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, _ = _chain_store(action=DecisionAction.ADD)
    adapter = _FakeAdapter()
    result = route_pending_orders(
        client=_FakeClient(store),
        adapter=adapter,
        connection=_connection(),
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=None,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert result.venue is ExecutionVenue.PAPER_INTERNAL
    assert result.skipped_paper_internal is True
    assert adapter.submitted == []


def test_house_and_system_uuids_never_route_externally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digiquant.olympus.tenancy import house_workspace_id, system_workspace_id

    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    assert (
        resolve_venue(house_workspace_id(), active_paper_brokers=[Broker.ALPACA])
        is ExecutionVenue.PAPER_INTERNAL
    )
    assert (
        resolve_venue(system_workspace_id(), active_paper_brokers=[Broker.IBKR])
        is ExecutionVenue.PAPER_INTERNAL
    )


def test_live_env_connection_with_explicit_brokers_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, _ = _chain_store(action=DecisionAction.ADD)
    adapter = _FakeAdapter()
    live_conn = BrokerConnection(
        id=_CONN,
        workspace_id=_WS,
        broker=Broker.ALPACA,
        env=ConnectionEnv.LIVE,
        auth_kind=AuthKind.API_KEY,
        ciphertext=b"\x00" * 32,
        nonce=b"\x00" * 12,
        key_id="v1",
        fingerprint="deadbeef",
        scopes=(),
        status=ConnectionStatus.ACTIVE,
        created_at=_NOW,
    )
    with pytest.raises(LiveVenueNotAuthorizedError):
        route_pending_orders(
            client=_FakeClient(store),
            adapter=adapter,
            connection=live_conn,
            run_date=_RUN,
            submitted_date=_RUN,
            now=_NOW,
            workspace_id=_WS,
            active_paper_brokers=[Broker.ALPACA],
        )
    assert adapter.submitted == []


def test_public_resolve_venue_raises_live_venue_not_authorized() -> None:
    with pytest.raises(LiveVenueNotAuthorizedError):
        resolve_venue(_WS, active_paper_brokers=["alpaca_live"])
    with pytest.raises(LiveVenueNotAuthorizedError):
        resolve_venue(_WS, active_paper_brokers=[ExecutionVenue.ALPACA_LIVE])
    with pytest.raises(LiveVenueNotAuthorizedError):
        resolve_venue(_WS, active_paper_brokers=[ExecutionVenue.IBKR_LIVE])


def test_pending_missing_workspace_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    store, _ = _chain_store(action=DecisionAction.ADD)
    store["portfolio_ledger_order_intents"][0].pop("workspace_id")
    adapter = _FakeAdapter()
    from digiquant.olympus.kairos.policy import ForeignWorkspaceIntentError

    with pytest.raises(ForeignWorkspaceIntentError):
        route_pending_orders(
            client=_FakeClient(store),
            adapter=adapter,
            connection=_connection(),
            run_date=_RUN,
            submitted_date=_RUN,
            now=_NOW,
            workspace_id=_WS,
            active_paper_brokers=[Broker.ALPACA],
        )
    assert adapter.submitted == []
