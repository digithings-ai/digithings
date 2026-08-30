"""Kairos + tenancy — pre-staging composition proof (local twin of staging E2E).

This module is the **local** end-to-end chain for the epic's composition path. It
exercises the REAL merged Python seams (T2 seed shape → T4 overlay → K4 router/sync
→ K5 notify) with fakes only at external boundaries (PostgREST/Supabase, Mailgun,
broker HTTP). It is **not** a substitute for the staging E2E in
``docs/agent-backlog/kairos-tenancy/DEPLOYMENT.md`` §7 / EPIC.md program acceptance
(signup → Stripe test Checkout → Alpaca connect → overlay → paper fill → digest).

Stripe hop
----------
The webhook handler is Deno/TS (``digiquant/supabase/functions/stripe-webhook/``).
Python has no reachable webhook seam. This chain therefore **starts post-billing**:
we seed ``workspaces`` rows (+ JWT claim shape notes) exactly as a successful
``customer.subscription.updated`` event would leave them after T2 claim sync.
Deno coverage for that hop: ``stripe-webhook.test.ts``.

Lane placement
--------------
Marked ``pytest.mark.unit`` (mirrors ``tests/integration/test_request_id_hops.py``).
Picked up by:

* full-repo ``pytest -m unit`` / ``make test-unit`` (``testpaths`` includes ``tests/``)
* digiquant regression lane when pointed at this path; the WP suites under
  ``tests/dq/olympus/``, ``tests/dq/brokers/``, ``tests/dq/notify`` remain the
  per-component gates

Not the staging E2E workflow; not HTTP; no live services.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any  # score:allow untyped any — heterogeneous PostgREST row dicts
from uuid import UUID, uuid4

import pytest
from digiquant.brokers.alpaca import AlpacaAdapter, ApiKeyAuth
from digiquant.brokers.connections import (
    Broker,
    ConnectionEnv,
    create_connection,
)
from digiquant.brokers.contracts import (
    BrokerAccountSnapshot,
    BrokerFill,
    BrokerOrderAck,
    BrokerOrderRequest,
    BrokerOrderStatus,
    BrokerPosition,
    ExecutionVenue,
    LiveVenueNotAuthorizedError,
    OrderSide,
)
from digiquant.notify.dispatch import dispatch_workspace
from digiquant.notify.entitlements import ArtifactClass, can
from digiquant.notify.entitlements import PlanTier as NotifyPlanTier
from digiquant.notify.mailgun import MailgunConfig
from digiquant.olympus.hermes.models.portfolio_ledger import (
    ApprovedTarget,
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntent,
    OrderIntentStatus,
    PortfolioCommit,
    RequestedTarget,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    REQUESTED_TARGETS,
    _insert,
)
from digiquant.olympus.kairos.router import BROKER_ORDERS, broker_order_id, route_pending_orders
from digiquant.olympus.kairos.sync import (
    BROKER_EXECUTIONS,
    BROKER_POSITION_SNAPSHOTS,
    SyncCursor,
    broker_execution_id,
    sync_connection,
)
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.olympus.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.olympus.research_corpus import ResearchCorpusStore
from digiquant.olympus.tenancy import (
    PlanTier,
    SubscriptionStatus,
    WorkspaceType,
    house_workspace_id,
)
from digiquant.vault.envelope import ApiKeyCredential, MasterKey, fingerprint

from tests.dq.olympus.overlay._sealed import sealed_openai

pytestmark = pytest.mark.unit

# ---------------------------------------------------------------------------
# Fixed clock / identities — deterministic for golden assertions
# ---------------------------------------------------------------------------

_RUN = date(2026, 8, 30)
_NOW = datetime(2026, 8, 30, 14, 30, tzinfo=UTC)
_SYMBOL = "SPY"
_FILL_EXTERNAL_ID = "alpaca-fill-chain-1"

# Synthetic Stripe event shape (T2). Not fed to Python — Deno owns verification.
# See digiquant/supabase/functions/stripe-webhook/stripe-webhook.test.ts.
_STRIPE_SUBSCRIPTION_UPDATED: dict[str, Any] = {
    "id": "evt_chain_test_1",
    "object": "event",
    "type": "customer.subscription.updated",
    "created": 1756550400,
    "data": {
        "object": {
            "id": "sub_chain_custom",
            "object": "subscription",
            "customer": "cus_chain_custom",
            "status": "active",
            "items": {
                "data": [
                    {
                        "price": {
                            "id": "price_custom_monthly",
                            "metadata": {"plan_tier": "custom"},
                        }
                    }
                ]
            },
        }
    },
}


# ---------------------------------------------------------------------------
# External-boundary fakes only (PostgREST + Mailgun + BrokerAdapter protocol)
# ---------------------------------------------------------------------------


@dataclass
class _ChainQuery:
    """Minimal PostgREST chain: select/eq/in_/gte/lt/order/limit/insert/update."""

    store: dict[str, list[dict[str, Any]]]
    table: str
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None
    _pending_insert: list[dict[str, Any]] | None = None
    _pending_update: dict[str, Any] | None = None

    def select(self, _cols: str) -> _ChainQuery:
        return self

    def eq(self, col: str, val: Any) -> _ChainQuery:
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> _ChainQuery:
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col: str, val: Any) -> _ChainQuery:
        self._filters.append(("lt", col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> _ChainQuery:
        self._filters.append(("in", col, list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> _ChainQuery:
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> _ChainQuery:
        self._limit = n
        return self

    def insert(self, rows: list[dict[str, Any]] | dict[str, Any]) -> _ChainQuery:
        self._pending_insert = rows if isinstance(rows, list) else [rows]
        return self

    def update(self, payload: dict[str, Any]) -> _ChainQuery:
        self._pending_update = dict(payload)
        return self

    def _match(self, row: dict[str, Any]) -> bool:
        for op, col, val in self._filters:
            cell = row.get(col)
            if op == "eq" and str(cell) != str(val):
                return False
            if op == "gte" and (cell is None or str(cell) < str(val)):
                return False
            if op == "lt" and (cell is None or str(cell) >= str(val)):
                return False
            if op == "in" and str(cell) not in {str(v) for v in val}:
                return False
        return True

    def execute(self) -> Any:
        table_rows = self.store.setdefault(self.table, [])
        if self._pending_insert is not None:
            inserted: list[dict[str, Any]] = []
            existing_ids = {str(r.get("id")) for r in table_rows if r.get("id") is not None}
            for raw in self._pending_insert:
                row = dict(raw)
                # broker_connections create_connection expects representation + created_at
                if self.table == "broker_connections":
                    row.setdefault("created_at", _NOW.isoformat())
                    row.setdefault("revoked_at", None)
                    row.setdefault("last_used_at", None)
                # notification_log dedupe (K5 insert-first)
                if self.table == "notification_log":
                    for existing in table_rows:
                        if (
                            existing.get("workspace_id") == row.get("workspace_id")
                            and existing.get("event_key") == row.get("event_key")
                            and existing.get("sent_date") == row.get("sent_date")
                        ):
                            raise RuntimeError(
                                "duplicate key value violates unique constraint 23505"
                            )
                rid = row.get("id")
                if rid is not None and str(rid) in existing_ids:
                    raise RuntimeError("duplicate key value violates unique constraint")
                table_rows.append(row)
                inserted.append(dict(row))
                if rid is not None:
                    existing_ids.add(str(rid))
            self._pending_insert = None
            return type("R", (), {"data": inserted})()
        if self._pending_update is not None:
            updated: list[dict[str, Any]] = []
            for row in table_rows:
                if self._match(row):
                    row.update(self._pending_update)
                    updated.append(dict(row))
            self._pending_update = None
            return type("R", (), {"data": updated})()
        rows = [dict(r) for r in table_rows if self._match(r)]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows})()


@dataclass
class ChainFakeSupabase:
    """Store-backed PostgREST stand-in (external boundary only).

    Extends the kairos / notify / brokers fake patterns into one client so the
    whole composition path shares one in-memory DB. Reads and writes hit the
    same ``tables`` dict (unlike atlas ``FakeSupabaseClient``'s canned/store
    split — that courtesy is house-fixture-only and wrong for a chain proof).
    """

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _ChainQuery:
        return _ChainQuery(store=self.tables, table=name)

    def snapshot(self, *names: str) -> dict[str, list[dict[str, Any]]]:
        return {n: copy.deepcopy(self.tables.get(n, [])) for n in names}


class CapturingMailgun:
    """Mailgun transport fake — records sends; never opens a socket."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def is_suppressed(self, email: str) -> bool:
        return False

    def send_message(self, to: str, subject: str, text_body: str, html_body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text_body, "html": html_body})


class MockBrokerAdapter:
    """K0 ``BrokerAdapter`` protocol mock — paper venue only; no HTTP."""

    name = "mock-alpaca-paper"

    def __init__(self) -> None:
        self.submitted: list[BrokerOrderRequest] = []
        self._acks: dict[str, BrokerOrderAck] = {}
        self._fills: list[BrokerFill] = []
        self._positions: list[BrokerPosition] = []

    def connect(self) -> None:
        return None

    def disconnect(self) -> None:
        return None

    def submit_order(self, req: BrokerOrderRequest) -> BrokerOrderAck:
        self.submitted.append(req)
        ext = f"ext-{req.client_order_id[:8]}"
        ack = BrokerOrderAck(
            external_order_id=ext,
            status=BrokerOrderStatus.ACCEPTED,
            submitted_at=_NOW,
            raw_sha256="a" * 64,
        )
        self._acks[ext] = ack
        # Venue will fill this order; sync pulls ack + fill.
        self._acks[ext] = BrokerOrderAck(
            external_order_id=ext,
            status=BrokerOrderStatus.FILLED,
            submitted_at=_NOW,
            raw_sha256="b" * 64,
        )
        qty = req.quantity or Decimal("0")
        self._fills.append(
            BrokerFill(
                external_fill_id=_FILL_EXTERNAL_ID,
                symbol=req.symbol,
                quantity=qty,
                price=Decimal("450.00"),
                fee=Decimal("0"),
                executed_at=_NOW - timedelta(minutes=1),
            )
        )
        self._positions = [
            BrokerPosition(
                symbol=req.symbol,
                quantity=qty,
                avg_entry_price=Decimal("450.00"),
                market_value=qty * Decimal("450.00"),
                unrealized_pl=Decimal("0"),
            )
        ]
        return ack

    def get_order(self, external_order_id: str) -> BrokerOrderAck:
        return self._acks[external_order_id]

    def cancel_order(self, external_order_id: str) -> None:
        raise AssertionError("chain must never cancel orders")

    def list_fills(self, since: datetime) -> list[BrokerFill]:
        return [f for f in self._fills if f.executed_at >= since]

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._positions)

    def get_account(self) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id="paper-acct-chain",
            equity=Decimal("100000"),
            cash=Decimal("55000"),
            buying_power=Decimal("55000"),
            currency="USD",
            as_of=_NOW,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def master_key() -> MasterKey:
    """Test vault master key — never a deploy secret."""
    return MasterKey(key_id="v1", material=bytes([0x42]) * 32)


@pytest.fixture
def custom_ws_id() -> UUID:
    return UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


@pytest.fixture
def free_ws_id() -> UUID:
    return UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


@pytest.fixture
def sb(custom_ws_id: UUID, free_ws_id: UUID, master_key: MasterKey) -> ChainFakeSupabase:
    """Post-billing world: CUSTOM active (as T2 webhook would leave it) + FREE + house."""
    del master_key  # fixture orders sealing elsewhere; listed for clarity
    house = str(house_workspace_id())
    # Stripe hop is Deno — seed the claim-sync outcome the webhook would write.
    assert _STRIPE_SUBSCRIPTION_UPDATED["type"] == "customer.subscription.updated"
    client = ChainFakeSupabase(
        tables={
            "workspaces": [
                {
                    "id": str(custom_ws_id),
                    "slug": "custom-chain",
                    "type": WorkspaceType.USER.value,
                    "name": "Custom Chain",
                    "plan_tier": PlanTier.CUSTOM.value,
                    "subscription_status": SubscriptionStatus.ACTIVE.value,
                    "stripe_customer_id": "cus_chain_custom",
                    "claim_sync_pending": False,
                },
                {
                    "id": str(free_ws_id),
                    "slug": "free-chain",
                    "type": WorkspaceType.USER.value,
                    "name": "Free Chain",
                    "plan_tier": PlanTier.FREE.value,
                    "subscription_status": SubscriptionStatus.NONE.value,
                },
                {
                    "id": house,
                    "slug": "house",
                    "type": WorkspaceType.USER.value,
                    "name": "House",
                    "plan_tier": PlanTier.ENTERPRISE.value,
                    "subscription_status": SubscriptionStatus.ACTIVE.value,
                },
            ],
            # House private book — must remain byte-identical through the chain.
            "positions": [
                {
                    "workspace_id": house,
                    "date": _RUN.isoformat(),
                    "ticker": "TLT",
                    "weight_pct": 40.0,
                },
                {
                    "workspace_id": str(custom_ws_id),
                    "date": _RUN.isoformat(),
                    "ticker": _SYMBOL,
                    "weight_pct": 55.0,
                },
                {
                    "workspace_id": str(free_ws_id),
                    "date": _RUN.isoformat(),
                    "ticker": "QQQ",
                    "weight_pct": 10.0,  # free digest must NOT render weights
                },
            ],
            "nav_history": [
                {
                    "workspace_id": house,
                    "date": _RUN.isoformat(),
                    "nav": 1_000_000,
                    "day_return_pct": 0.1,
                },
                {
                    "workspace_id": str(custom_ws_id),
                    "date": _RUN.isoformat(),
                    "nav": 250_000,
                    "day_return_pct": 0.2,
                },
            ],
            "daily_snapshots": [
                {
                    "date": _RUN.isoformat(),
                    "snapshot": {
                        "regime": {
                            "bias": "neutral",
                            "label": "range",
                            "conviction": "medium",
                            "summary": "chain-test regime",
                        }
                    },
                }
            ],
            "notification_prefs": [
                {
                    "workspace_id": str(custom_ws_id),
                    "email": "custom@example.com",
                    "daily_digest": True,
                    "holding_change_alerts": False,
                    "execution_alerts": True,
                    "digest_hour_utc": 12,
                },
                {
                    "workspace_id": str(free_ws_id),
                    "email": "free@example.com",
                    "daily_digest": True,
                    "holding_change_alerts": False,
                    "execution_alerts": True,  # prefs on — tier gate still denies broker content
                    "digest_hour_utc": 12,
                },
            ],
            "notification_log": [],
            "broker_connections": [],
            BROKER_ORDERS: [],
            BROKER_EXECUTIONS: [],
            BROKER_POSITION_SNAPSHOTS: [],
            COMMITS: [],
            DECISION_INTENTS: [],
            REQUESTED_TARGETS: [],
            APPROVED_TARGETS: [],
            ORDER_INTENTS: [],
            "portfolio_metrics": [],
        }
    )
    return client


def _mailgun_config() -> MailgunConfig:
    return MailgunConfig(
        api_key="test-key",
        domain="mg.example.com",
        from_address="notify@example.com",
        unsubscribe_base="https://example.com/settings",
    )


def _emit_pending_order_chain(
    *,
    client: ChainFakeSupabase,
    workspace_id: UUID,
    symbol: str = _SYMBOL,
    quantity: Decimal = Decimal("10"),
) -> UUID:
    """Append a workspace-stamped decision→…→pending OrderIntent via real writer gate.

    Uses Pydantic ledger contracts + :func:`ledger_io._insert` (the single INSERT
    seam). This is the stub overlay chain's private-phase write — not a fake of
    an internal module.
    """
    stamp = _NOW
    ws_kw = {"workspace_id": workspace_id}
    commit_id = uuid4()
    decision_id = uuid4()
    requested_id = uuid4()
    approved_id = uuid4()
    order_id = uuid4()
    commit = PortfolioCommit(
        id=commit_id,
        run_date=_RUN,
        policy_version_id="hermes-h8-sizing-chain",
        effective_at=stamp,
        recorded_at=stamp,
        **ws_kw,
    )
    decision = DecisionIntent(
        id=decision_id,
        portfolio_commit_id=commit_id,
        run_date=_RUN,
        symbol=symbol,
        action=DecisionAction.ADD,
        reason=DecisionReason.NEW_CONVICTION,
        effective_at=stamp,
        recorded_at=stamp,
        **ws_kw,
    )
    requested = RequestedTarget(
        id=requested_id,
        decision_intent_id=decision_id,
        run_date=_RUN,
        symbol=symbol,
        requested_weight=Decimal("0.55"),
        effective_at=stamp,
        recorded_at=stamp,
        **ws_kw,
    )
    approved = ApprovedTarget(
        id=approved_id,
        requested_target_id=requested_id,
        run_date=_RUN,
        symbol=symbol,
        approved_weight=Decimal("0.55"),
        effective_at=stamp,
        recorded_at=stamp,
        **ws_kw,
    )
    order = OrderIntent(
        id=order_id,
        approved_target_id=approved_id,
        run_date=_RUN,
        symbol=symbol,
        quantity=quantity,
        status=OrderIntentStatus.PENDING,
        effective_at=stamp,
        recorded_at=stamp,
        **ws_kw,
    )
    _insert(client=client, table=COMMITS, rows=[commit.model_dump(mode="json")])
    _insert(client=client, table=DECISION_INTENTS, rows=[decision.model_dump(mode="json")])
    _insert(client=client, table=REQUESTED_TARGETS, rows=[requested.model_dump(mode="json")])
    _insert(client=client, table=APPROVED_TARGETS, rows=[approved.model_dump(mode="json")])
    _insert(client=client, table=ORDER_INTENTS, rows=[order.model_dump(mode="json")])
    return order_id


# ---------------------------------------------------------------------------
# Chain steps
# ---------------------------------------------------------------------------


def test_entitled_overlay_to_paper_fill_to_alert(
    monkeypatch: pytest.MonkeyPatch,
    sb: ChainFakeSupabase,
    custom_ws_id: UUID,
    free_ws_id: UUID,
    master_key: MasterKey,
) -> None:
    """Happy path + woven negatives: house untouched, live raises, sync idempotent."""
    monkeypatch.setenv("OLYMPUS_KAIROS_ROUTING", "1")
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")

    house = str(house_workspace_id())
    house_before = sb.snapshot(
        "positions",
        "nav_history",
        COMMITS,
        ORDER_INTENTS,
        BROKER_ORDERS,
        BROKER_EXECUTIONS,
    )
    house_positions_before = [r for r in house_before["positions"] if r["workspace_id"] == house]
    house_nav_before = [r for r in house_before["nav_history"] if r["workspace_id"] == house]

    # --- 1) Sealed BYOK (real K3 envelope) + Alpaca paper connection (real store) ---
    byok_cred, byok_master = sealed_openai(custom_ws_id)
    broker_cred = ApiKeyCredential(key_id="PK_CHAIN", secret="SK_chain_paper_only")
    connection = create_connection(
        client=sb,
        workspace_id=custom_ws_id,
        broker=Broker.ALPACA,
        env=ConnectionEnv.PAPER,
        credential=broker_cred,
        key=master_key,
    )
    assert connection.env is ConnectionEnv.PAPER
    assert connection.fingerprint == fingerprint(broker_cred)
    assert "SK_chain" not in repr(connection)

    # --- 2) Overlay dispatch entitlement → claim → runner stub emits ledger chain ---
    job_store = MemoryJobRunStore()
    entitlement = WorkspaceEntitlement(
        workspace_id=custom_ws_id,
        plan_tier=PlanTier.CUSTOM,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    byok_ok = ByokProbe(
        present_and_unsealable=True,
        provider="openai",
        fingerprint=byok_cred.fingerprint,
    )
    dispatch = dispatch_overlay_daily(
        store=job_store,
        workspace=entitlement,
        run_date=_RUN,
        byok=byok_ok,
    )
    assert dispatch.claimed is True
    assert dispatch.job.status is JobStatus.RUNNING

    order_intent_id_box: dict[str, UUID] = {}

    def stub_chain(
        *,
        workspace_id: UUID,
        run_date: date,
        requested_version_id: UUID | None,
    ) -> None:
        assert workspace_id == custom_ws_id
        assert run_date == _RUN
        assert requested_version_id is not None
        order_intent_id_box["id"] = _emit_pending_order_chain(client=sb, workspace_id=workspace_id)

    profile_version = uuid4()
    overlay_result = run_overlay(
        request=OverlayRunRequest(
            workspace_id=custom_ws_id,
            run_date=_RUN,
            profile_version_id=profile_version,
            themes=("ai",),
            watchlist=(_SYMBOL,),
        ),
        job=dispatch.job,
        store=job_store,
        corpus=ResearchCorpusStore(),
        byok=byok_ok,
        chain=stub_chain,
        credential=byok_cred,
        vault_key=byok_master,
        house_job_store=MemoryJobRunStore(),  # prove isolation — never written
    )
    assert overlay_result.status is JobStatus.SUCCEEDED
    assert "theme:ai" in overlay_result.published_keys
    assert f"asset:{_SYMBOL.lower()}" in overlay_result.published_keys
    order_intent_id = order_intent_id_box["id"]
    stamped = [r for r in sb.tables[ORDER_INTENTS] if r["id"] == str(order_intent_id)]
    assert stamped and stamped[0]["workspace_id"] == str(custom_ws_id)
    assert stamped[0]["workspace_id"] != house

    # --- 3) K4 router: kill switch ON → mock adapter, client_order_id, paper-only ---
    adapter = MockBrokerAdapter()
    route = route_pending_orders(
        client=sb,
        adapter=adapter,
        connection=connection,
        run_date=_RUN,
        submitted_date=_RUN,
        now=_NOW,
        workspace_id=custom_ws_id,
        active_paper_brokers=[Broker.ALPACA],
    )
    assert route.skipped_paper_internal is False
    assert route.venue is ExecutionVenue.ALPACA_PAPER
    assert len(adapter.submitted) == 1
    assert adapter.submitted[0].client_order_id == str(order_intent_id)
    assert adapter.submitted[0].side is OrderSide.BUY
    assert adapter.submitted[0].symbol == _SYMBOL
    assert len(sb.tables[BROKER_ORDERS]) == 1
    broker_row = sb.tables[BROKER_ORDERS][0]
    assert broker_row["workspace_id"] == str(custom_ws_id)
    assert broker_row["order_intent_id"] == str(order_intent_id)
    assert broker_row["id"] == str(broker_order_id(order_intent_id, Broker.ALPACA, _RUN))
    assert broker_row["client_order_id"] == str(order_intent_id)

    # Negative: live-env construction raises (K1 invariant) — woven at step 3.
    with pytest.raises(LiveVenueNotAuthorizedError):
        AlpacaAdapter(auth=ApiKeyAuth(key_id="PK", secret="SK"), env="live")  # type: ignore[arg-type]

    # --- 4) K4 sync: ack + fill → broker_executions + positions snapshot ---
    cursor = SyncCursor(fills_since=_NOW - timedelta(hours=2))
    sync1 = sync_connection(
        client=sb,
        adapter=adapter,
        connection=connection,
        cursor=cursor,
        now=_NOW,
        pull_snapshot=True,
    )
    assert sync1.fills_appended == 1
    assert sync1.refused_corrective_orders is True
    assert len(sb.tables[BROKER_EXECUTIONS]) == 1
    fill_row = sb.tables[BROKER_EXECUTIONS][0]
    expected_fill_id = broker_execution_id(connection.id, _FILL_EXTERNAL_ID)
    assert fill_row["id"] == str(expected_fill_id)
    assert fill_row["workspace_id"] == str(custom_ws_id)
    assert fill_row["symbol"] == _SYMBOL
    assert sync1.snapshot_id is not None
    assert len(sb.tables[BROKER_POSITION_SNAPSHOTS]) == 1
    assert sb.tables[BROKER_POSITION_SNAPSHOTS][0]["workspace_id"] == str(custom_ws_id)

    # Negative: second sync cycle is idempotent (no duplicate mirror rows).
    sync2 = sync_connection(
        client=sb,
        adapter=adapter,
        connection=connection,
        cursor=cursor,
        now=_NOW,
        pull_snapshot=True,
    )
    assert sync2.fills_appended == 0
    assert sync2.fills_already_present == 1
    assert len(sb.tables[BROKER_EXECUTIONS]) == 1

    # --- 5) K5 notify: CUSTOM execution alert; FREE gets nothing (tier + no fills) ---
    mailgun = CapturingMailgun()
    cfg = _mailgun_config()
    # Tier gate vocabulary (T5 matrix): free cannot see broker_status.
    assert can(NotifyPlanTier.CUSTOM, ArtifactClass.BROKER_STATUS) is True
    assert can(NotifyPlanTier.FREE, ArtifactClass.BROKER_STATUS) is False

    custom_pref = next(
        p for p in sb.tables["notification_prefs"] if p["workspace_id"] == str(custom_ws_id)
    )
    free_pref = next(
        p for p in sb.tables["notification_prefs"] if p["workspace_id"] == str(free_ws_id)
    )

    # Execution alerts only (hour mismatch skips digest) for a clean alert assertion.
    dispatch_workspace(sb, mailgun, cfg, custom_pref, _RUN, hour_utc=99)
    alert_sends = [s for s in mailgun.sent if "Execution alert" in s["subject"]]
    assert len(alert_sends) == 1
    body = alert_sends[0]["text"] + alert_sends[0]["html"]
    assert _SYMBOL in body
    # No PII beyond the recipient email (already on the envelope, not in body).
    assert "SK_chain" not in body
    assert "ciphertext" not in body.lower()
    assert str(connection.id) not in body
    assert byok_cred.fingerprint not in body
    assert "PK_CHAIN" not in body

    mailgun.sent.clear()
    dispatch_workspace(sb, mailgun, cfg, free_pref, _RUN, hour_utc=99)
    assert mailgun.sent == []  # free-tier: no fills in-scope + broker_status entitlement false

    # Digest force path (K5 review: hour mismatch still sends when force_digest).
    mailgun.sent.clear()
    dispatch_workspace(sb, mailgun, cfg, free_pref, _RUN, hour_utc=99, force_digest=True)
    free_digests = [s for s in mailgun.sent if "daily digest" in s["subject"]]
    assert len(free_digests) == 1
    free_body = free_digests[0]["text"] + free_digests[0]["html"]
    assert "Market Regime" in free_body or "chain-test regime" in free_body
    assert "QQQ" not in free_body  # weights gated out for observer
    assert "weight" not in free_body.lower() or "Pipeline" not in free_body

    mailgun.sent.clear()
    # Re-claim digest for custom (execution already claimed; digest still open).
    dispatch_workspace(sb, mailgun, cfg, custom_pref, _RUN, hour_utc=99, force_digest=True)
    custom_digests = [s for s in mailgun.sent if "daily digest" in s["subject"]]
    assert len(custom_digests) == 1
    custom_body = custom_digests[0]["text"] + custom_digests[0]["html"]
    assert _SYMBOL in custom_body or "Market Regime" in custom_body

    # --- House isolation: house rows unchanged by the whole chain ---
    house_after_positions = [r for r in sb.tables["positions"] if r["workspace_id"] == house]
    house_after_nav = [r for r in sb.tables["nav_history"] if r["workspace_id"] == house]
    assert house_after_positions == house_positions_before
    assert house_after_nav == house_nav_before
    assert not any(r.get("workspace_id") == house for r in sb.tables[BROKER_ORDERS])
    assert not any(r.get("workspace_id") == house for r in sb.tables[BROKER_EXECUTIONS])
    assert not any(
        r.get("workspace_id") == house
        for r in sb.tables[ORDER_INTENTS]
        if r.get("symbol") == _SYMBOL
    )


def test_chain_module_is_unit_lane_compatible() -> None:
    """Sanity: this file's mark matches request_id_hops so CI unit lanes can collect it."""
    assert pytestmark.name == "unit" or (
        isinstance(pytestmark, list) and any(m.name == "unit" for m in pytestmark)
    )
