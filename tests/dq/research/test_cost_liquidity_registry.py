"""Writer/reader tests for the cost/liquidity evidence registry (#2709 / WP7.3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.atlas import cost_liquidity_registry as clr
from digiquant.olympus.hermes.action_cost_inputs import ActionCostInput, ActionCostSide
from digiquant.olympus.hermes.cost_liquidity import (
    estimate_action_cost,
    prospective_observations_from_row,
)
from digiquant.olympus.hermes.models.cost_liquidity import CostOutcomeStatus
from digiquant.olympus.hermes.models.portfolio_ledger import (
    DecisionAction,
    DecisionIntent,
    DecisionReason,
    OrderIntentStatus,
    PaperExecution,
    paper_execution_id,
)
from digiquant.olympus.hermes.risk_policy import resolve_risk_policy

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient, _FakeQuery, _FakeResponse

pytestmark = pytest.mark.unit

TS = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)
CUTOFF = TS + timedelta(hours=1)
SESSION = date(2026, 8, 25)
CURRENCY = "USD"
ORDER_ID = UUID("aaaaaaaa-1111-4111-8111-111111111111")
COMMIT_ID = UUID("bbbbbbbb-2222-4222-8222-222222222222")
DECISION_ID = UUID("cccccccc-3333-4333-8333-333333333333")
EXEC_ID = paper_execution_id(ORDER_ID, SESSION)


@dataclass
class _MergingQuery(_FakeQuery):
    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        merged = list(self.canned) + list(self.store.get(self.table_name, []))
        rows = [r for r in merged if self._matches(r)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class CostRegistryFake(FakeSupabaseClient):
    def table(self, name: str) -> _MergingQuery:
        return _MergingQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )


def _policy():
    return resolve_risk_policy({}, effective_at=TS, source_run_id="run-test").policy


def _bundle():
    action = ActionCostInput(
        portfolio_commit_id=COMMIT_ID,
        decision_intent_id=DECISION_ID,
        order_intent_id=ORDER_ID,
        run_date=SESSION,
        symbol="AAPL",
        side=ActionCostSide.BUY,
        quantity=Decimal("100"),
        notional=Decimal("15000"),
        currency=CURRENCY,
        effective_at=TS,
        recorded_at=TS,
    )
    obs = prospective_observations_from_row(
        session_date=SESSION,
        symbol="AAPL",
        row={
            "close": Decimal("150"),
            "high": Decimal("152"),
            "low": Decimal("148"),
            "volume": 1_000_000,
            "hist_vol_21": Decimal("25"),
        },
        observed_at=TS,
        known_at=TS,
        adv_shares=Decimal("1000000"),
        adv_dollars=Decimal("150000000"),
    )
    return estimate_action_cost(action, obs, _policy(), estimated_at=TS)


def test_persist_writes_snapshot_and_estimate() -> None:
    client = CostRegistryFake()
    bundle = _bundle()
    result = clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)
    assert result.ok
    assert result.snapshots_written == 1
    assert result.estimates_written == 1


def test_exact_retry_is_idempotent() -> None:
    client = CostRegistryFake()
    bundle = _bundle()
    clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)
    second = clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)
    assert second.snapshots_skipped == 1
    assert second.estimates_skipped == 1


def test_get_estimate_respects_cutoff() -> None:
    client = CostRegistryFake()
    bundle = _bundle()
    clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)
    assert clr.get_action_cost_estimate(
        client=client,
        estimate_id=bundle.estimate.estimate_id,
        knowledge_cutoff_at=CUTOFF,
    )
    assert (
        clr.get_action_cost_estimate(
            client=client,
            estimate_id=bundle.estimate.estimate_id,
            knowledge_cutoff_at=TS - timedelta(hours=1),
        )
        is None
    )


def test_resolve_outcome_after_fill() -> None:
    client = CostRegistryFake()
    bundle = _bundle()
    clr.persist_cost_liquidity_bundle(client=client, bundle=bundle)

    requested_id = uuid4()
    approved_id = uuid4()
    client.store["portfolio_ledger_order_intents"] = [
        {
            "id": str(ORDER_ID),
            "approved_target_id": str(approved_id),
            "run_date": SESSION.isoformat(),
            "symbol": "AAPL",
            "quantity": "100",
            "status": OrderIntentStatus.PENDING.value,
            "effective_at": TS.isoformat(),
            "recorded_at": TS.isoformat(),
        }
    ]
    client.store["portfolio_ledger_approved_targets"] = [
        {"id": str(approved_id), "requested_target_id": str(requested_id)}
    ]
    client.store["portfolio_ledger_requested_targets"] = [
        {"id": str(requested_id), "decision_intent_id": str(DECISION_ID)}
    ]
    client.store["portfolio_ledger_decision_intents"] = [
        DecisionIntent(
            id=DECISION_ID,
            portfolio_commit_id=COMMIT_ID,
            run_date=SESSION,
            symbol="AAPL",
            action=DecisionAction.ADD,
            reason=DecisionReason.NEW_CONVICTION,
            effective_at=TS,
            recorded_at=TS,
        ).model_dump(mode="json")
    ]
    client.store[clr.PAPER_EXECUTIONS] = [
        PaperExecution(
            id=EXEC_ID,
            order_intent_id=ORDER_ID,
            executed_date=SESSION,
            symbol="AAPL",
            quantity=Decimal("100"),
            price=Decimal("150"),
            fee=Decimal("1.25"),
            slippage=Decimal("2.50"),
            executed_at=TS,
            recorded_at=TS,
        ).model_dump(mode="json")
    ]

    result = clr.resolve_realized_action_cost_outcomes(
        client=client,
        run_date=SESSION,
        knowledge_cutoff_at=CUTOFF,
        currency=CURRENCY,
    )
    assert result.resolved == 1
    assert client.store[clr.ACTION_COST_OUTCOMES][0]["outcome_body"]["status"] == (
        CostOutcomeStatus.COMPARED.value
    )


def test_missing_fill_stays_pending() -> None:
    client = CostRegistryFake()
    clr.persist_cost_liquidity_bundle(client=client, bundle=_bundle())
    result = clr.resolve_realized_action_cost_outcomes(
        client=client,
        run_date=SESSION,
        knowledge_cutoff_at=CUTOFF,
        currency=CURRENCY,
    )
    assert result.pending == 1
    assert clr.ACTION_COST_OUTCOMES not in client.store
