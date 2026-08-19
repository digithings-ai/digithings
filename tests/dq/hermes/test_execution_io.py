"""Task 2.4 — authoritative paper-fill writer tests (#2420).

These tests pin the properties that make the fill record trustworthy: it is written
append-only, it is idempotent under retry, its direction comes from the recorded decision
chain rather than from a diff of mutable state, and it declines to speak when the ledger
has no chain for the date.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from digiquant.olympus.hermes.models.portfolio_ledger import (
    HoldingLotStatus,
    OrderIntentStatus,
    OrderRejectionReason,
    paper_execution_id,
)
from digiquant.olympus.hermes.writers import execution_io
from digiquant.olympus.hermes.writers.execution_io import (
    HOLDING_LOTS,
    close_lot_id,
    execute_pending_orders,
    executed_intent_id,
    open_lot_id,
)
from digiquant.olympus.hermes.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 12)
# Deliberately the *next* day: the at-open executor fills the morning after the decision,
# which is precisely the gap that makes the composite supersession FK easy to violate.
EXECUTED_DATE = date(2026, 6, 15)
NOW = datetime(2026, 6, 15, 13, 31, tzinfo=UTC)


def _uuid(tag: str) -> UUID:
    """Stable, readable ids so a failure message points at the row that broke."""
    return UUID(int=abs(hash(tag)) % (1 << 128), version=5)


class _Chain:
    """Builds one run_date's worth of canned ledger rows for a fake client."""

    def __init__(self) -> None:
        self.commits: list[dict[str, Any]] = [
            {"id": str(_uuid("commit")), "run_date": RUN_DATE.isoformat()}
        ]
        self.decisions: list[dict[str, Any]] = []
        self.requested: list[dict[str, Any]] = []
        self.approved: list[dict[str, Any]] = []
        self.orders: list[dict[str, Any]] = []
        self.executions: list[dict[str, Any]] = []
        self.lots: list[dict[str, Any]] = []

    def order(
        self,
        *,
        symbol: str,
        action: str,
        quantity: str,
        status: str = "pending",
        supersedes_id: str | None = None,
        approved_superseded_by: str | None = None,
        run_date: date = RUN_DATE,
        tag: str = "",
    ) -> str:
        """Append a full decision→order chain leg and return the order intent id."""
        key = f"{symbol}:{action}:{tag or status}"
        decision_id = str(_uuid(f"decision:{key}"))
        requested_id = str(_uuid(f"requested:{key}"))
        approved_id = str(_uuid(f"approved:{key}"))
        order_id = str(_uuid(f"order:{key}"))
        rd = run_date.isoformat()
        self.decisions.append(
            {"id": decision_id, "run_date": rd, "symbol": symbol, "action": action}
        )
        self.requested.append(
            {
                "id": requested_id,
                "decision_intent_id": decision_id,
                "run_date": rd,
                "symbol": symbol,
            }
        )
        self.approved.append(
            {
                "id": approved_id,
                "requested_target_id": requested_id,
                "run_date": rd,
                "symbol": symbol,
                "supersedes_id": None,
            }
        )
        if approved_superseded_by is not None:
            # A later approval for the same symbol/day replaced this one.
            self.approved.append(
                {
                    "id": approved_superseded_by,
                    "requested_target_id": requested_id,
                    "run_date": rd,
                    "symbol": symbol,
                    "supersedes_id": approved_id,
                }
            )
        self.orders.append(
            {
                "id": order_id,
                "approved_target_id": approved_id,
                "run_date": rd,
                "symbol": symbol,
                "quantity": quantity,
                "status": status,
                "supersedes_id": supersedes_id,
            }
        )
        return order_id

    def lot(
        self,
        *,
        symbol: str,
        quantity: str,
        open_price: str,
        opened_at: str,
        tag: str,
        closed: str | None = None,
    ) -> str:
        """Append an open lot lineage, optionally with a prior partial close against it."""
        execution_id = str(_uuid(f"open-exec:{symbol}:{tag}"))
        self.lots.append(
            {
                "id": str(open_lot_id(UUID(execution_id))),
                "opened_by_execution_id": execution_id,
                "closed_by_execution_id": None,
                "run_date": date(2026, 5, 4).isoformat(),
                "symbol": symbol,
                "quantity": quantity,
                "open_price": open_price,
                "status": "open",
                "opened_at": opened_at,
                "closed_at": None,
            }
        )
        if closed is not None:
            self.lots.append(
                {
                    "id": str(_uuid(f"prior-close:{symbol}:{tag}")),
                    "opened_by_execution_id": execution_id,
                    "closed_by_execution_id": str(_uuid(f"prior-close-exec:{symbol}:{tag}")),
                    "run_date": date(2026, 5, 4).isoformat(),
                    "symbol": symbol,
                    "quantity": closed,
                    "open_price": open_price,
                    "status": "closed",
                    "opened_at": opened_at,
                    "closed_at": "2026-06-01T13:31:00+00:00",
                }
            )
        return execution_id

    def client(self, *, with_commit: bool = True) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={
                COMMITS: self.commits if with_commit else [],
                DECISION_INTENTS: self.decisions,
                REQUESTED_TARGETS: self.requested,
                APPROVED_TARGETS: self.approved,
                ORDER_INTENTS: self.orders,
                PAPER_EXECUTIONS: self.executions,
                HOLDING_LOTS: self.lots,
            }
        )


def _run(
    client: FakeSupabaseClient, marks: dict[str, str] | None = None
) -> execution_io.ExecutionResult:
    return execute_pending_orders(
        client=client,
        run_date=RUN_DATE,
        executed_date=EXECUTED_DATE,
        marks={k: Decimal(v) for k, v in (marks or {"AAPL": "100.00"}).items()},
        now=NOW,
    )


class TestAuthority:
    """The ledger must be able to say "I have no opinion about this date"."""

    def test_no_commit_row_means_not_authoritative_and_writes_nothing(self) -> None:
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client(with_commit=False)

        result = _run(client)

        assert result.authoritative is False
        assert result.fills == []
        # Nothing at all — a caller falling back to a legacy projection must not also
        # find half-written ledger rows.
        assert client.store == {}

    def test_commit_with_no_pending_orders_is_authoritative_and_empty(self) -> None:
        """The distinction that matters: a real no-op day, not a missing chain."""
        client = _Chain().client()

        result = _run(client)

        assert result.authoritative is True
        assert result.fills == []
        assert client.store == {}

    def test_kill_switch_off_writes_nothing_and_is_not_authoritative(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()
        monkeypatch.setenv("OLYMPUS_PORTFOLIO_LEDGER", "0")

        result = _run(client)

        assert result.authoritative is False
        assert client.store == {}


class TestBuyFill:
    def test_add_books_fill_lot_and_terminal_order(self) -> None:
        chain = _Chain()
        order_id = chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        result = _run(client, {"AAPL": "195.50"})

        assert [f.symbol for f in result.fills] == ["AAPL"]
        fill = client.store[PAPER_EXECUTIONS][0]
        assert fill["id"] == str(paper_execution_id(UUID(order_id), EXECUTED_DATE))
        assert fill["order_intent_id"] == order_id
        assert fill["executed_date"] == EXECUTED_DATE.isoformat()
        assert Decimal(fill["quantity"]) == Decimal("10")
        assert Decimal(fill["price"]) == Decimal("195.50")

        lot = client.store[HOLDING_LOTS][0]
        assert lot["status"] == HoldingLotStatus.OPEN
        assert lot["closed_by_execution_id"] is None
        assert lot["opened_by_execution_id"] == fill["id"]
        assert Decimal(lot["open_price"]) == Decimal("195.50")

        order = client.store[ORDER_INTENTS][0]
        assert order["status"] == OrderIntentStatus.EXECUTED
        assert order["supersedes_id"] == order_id
        assert order["rejection_reason"] is None

    def test_executed_row_carries_the_pending_rows_run_date_not_the_fill_date(self) -> None:
        """Regression guard for migration 069's *composite* supersession FK.

        ``order_intents`` declares
        ``FOREIGN KEY (supersedes_id, run_date, symbol) REFERENCES (id, run_date, symbol)``,
        so the executed row must repeat the superseded row's ``run_date``. Stamping it
        with ``executed_date`` — the obvious reading of "when did this execute" — is an
        FK violation every time the fill lands on a later day than the decision, which
        for an at-open executor is *always*.
        """
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        order = client.store[ORDER_INTENTS][0]
        assert RUN_DATE != EXECUTED_DATE, "the test is vacuous if the dates coincide"
        assert order["run_date"] == RUN_DATE.isoformat()

    def test_zero_fee_and_slippage_are_written_explicitly_not_left_null(self) -> None:
        """Migration 070: a paper fill at the declared open has *measured* zero cost.

        NULL is reserved for rows written before cost tracking existed, and the
        append-only trigger makes those unbackfillable — so a writer that omits the
        columns would forge that "predates 070" meaning onto a fill it fully measured.
        """
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        fill = client.store[PAPER_EXECUTIONS][0]
        assert fill["fee"] is not None
        assert fill["slippage"] is not None
        assert Decimal(fill["fee"]) == Decimal(0)
        assert Decimal(fill["slippage"]) == Decimal(0)

    def test_writes_use_insert_never_upsert(self) -> None:
        """The append-only trigger rejects UPDATE, so ``upsert`` would fail in production.

        The fake stamps ``_on_conflict`` on upserted rows only, which makes the verb the
        writer actually used observable.
        """
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        written = [r for rows in client.store.values() for r in rows]
        assert written
        assert all("_on_conflict" not in row for row in written)


class TestSellClosesLots:
    def test_partial_trim_closes_only_the_trimmed_quantity(self) -> None:
        """A trim appends a partial ``closed`` row — it does not invent a residual lot.

        Live size is ``opened - sum(closed)``, so the trimmed 4 of 10 leaves 6 without
        any row being rewritten.
        """
        chain = _Chain()
        opening_execution = chain.lot(
            symbol="AAPL",
            quantity="10",
            open_price="150.00",
            opened_at="2026-05-04T13:31:00+00:00",
            tag="a",
        )
        chain.order(symbol="AAPL", action="trim", quantity="4")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        lots = client.store[HOLDING_LOTS]
        assert len(lots) == 1
        assert lots[0]["status"] == HoldingLotStatus.CLOSED
        assert Decimal(lots[0]["quantity"]) == Decimal("4")
        assert lots[0]["opened_by_execution_id"] == opening_execution
        # Cost basis and open date come from the lineage, not from today's fill.
        assert Decimal(lots[0]["open_price"]) == Decimal("150.00")
        assert lots[0]["opened_at"].startswith("2026-05-04")
        assert lots[0]["closed_at"].startswith("2026-06-15")

    def test_prior_partial_close_reduces_what_is_available(self) -> None:
        """The closed rows *are* the state. Ignoring them would double-sell the lot."""
        chain = _Chain()
        chain.lot(
            symbol="AAPL",
            quantity="10",
            open_price="150.00",
            opened_at="2026-05-04T13:31:00+00:00",
            tag="a",
            closed="7",
        )
        chain.order(symbol="AAPL", action="exit", quantity="5")
        client = chain.client()

        with_caplog = client
        _run(with_caplog, {"AAPL": "195.50"})

        lots = client.store[HOLDING_LOTS]
        # Only 3 remained live, so only 3 can be closed; the surplus 2 has no lot.
        assert [Decimal(row["quantity"]) for row in lots] == [Decimal("3")]

    def test_exit_across_two_lineages_closes_both_fifo(self) -> None:
        chain = _Chain()
        first = chain.lot(
            symbol="AAPL",
            quantity="4",
            open_price="150.00",
            opened_at="2026-05-04T13:31:00+00:00",
            tag="a",
        )
        second = chain.lot(
            symbol="AAPL",
            quantity="6",
            open_price="160.00",
            opened_at="2026-05-20T13:31:00+00:00",
            tag="b",
        )
        chain.order(symbol="AAPL", action="exit", quantity="7")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        lots = client.store[HOLDING_LOTS]
        by_lineage = {row["opened_by_execution_id"]: Decimal(row["quantity"]) for row in lots}
        # FIFO: the older lineage is consumed whole, the newer one partially.
        assert by_lineage == {first: Decimal("4"), second: Decimal("3")}
        assert all(row["status"] == HoldingLotStatus.CLOSED for row in lots)

    def test_two_sells_in_one_run_cannot_consume_the_same_shares(self) -> None:
        """In-run bookkeeping, not just a per-fill read of the DB."""
        chain = _Chain()
        chain.lot(
            symbol="AAPL",
            quantity="10",
            open_price="150.00",
            opened_at="2026-05-04T13:31:00+00:00",
            tag="a",
        )
        chain.order(symbol="AAPL", action="trim", quantity="6", tag="first")
        chain.order(symbol="AAPL", action="trim", quantity="6", tag="second")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        closed = sum(Decimal(row["quantity"]) for row in client.store[HOLDING_LOTS])
        assert closed == Decimal("10"), "closed more shares than the lineage ever held"

    def test_sell_beyond_recorded_lots_books_the_fill_and_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The fill happened, so it is recorded; the missing lot is an error, not a silent drop."""
        chain = _Chain()
        chain.order(symbol="AAPL", action="exit", quantity="5")
        client = chain.client()

        with caplog.at_level(logging.ERROR, logger=execution_io.__name__):
            result = _run(client, {"AAPL": "195.50"})

        assert len(result.fills) == 1
        assert client.store.get(HOLDING_LOTS, []) == []
        assert "exceeds recorded open lots" in caplog.text

    def test_over_closed_lineage_is_reported_not_clamped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        chain = _Chain()
        chain.lot(
            symbol="AAPL",
            quantity="10",
            open_price="150.00",
            opened_at="2026-05-04T13:31:00+00:00",
            tag="a",
            closed="12",
        )
        chain.order(symbol="AAPL", action="trim", quantity="1")
        client = chain.client()

        with caplog.at_level(logging.ERROR, logger=execution_io.__name__):
            _run(client, {"AAPL": "195.50"})

        assert "over-closed" in caplog.text


class TestRejections:
    def test_missing_mark_is_rejected_with_no_fill_row(self) -> None:
        """A fill needs a price. Guessing one is the read-time invention this task removes."""
        chain = _Chain()
        order_id = chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        result = _run(client, {"MSFT": "400.00"})

        assert [r.reason for r in result.rejections] == [OrderRejectionReason.DATA_UNAVAILABLE]
        assert client.store.get(PAPER_EXECUTIONS, []) == []
        assert client.store.get(HOLDING_LOTS, []) == []
        rejected = client.store[ORDER_INTENTS][0]
        assert rejected["status"] == OrderIntentStatus.REJECTED
        assert rejected["rejection_reason"] == OrderRejectionReason.DATA_UNAVAILABLE
        assert rejected["supersedes_id"] == order_id
        assert rejected["run_date"] == RUN_DATE.isoformat()

    def test_order_from_a_superseded_approval_is_stale_not_filled(self) -> None:
        """H8 re-approved a different target for the day; this order is an artefact."""
        chain = _Chain()
        chain.order(
            symbol="AAPL",
            action="add",
            quantity="10",
            approved_superseded_by=str(_uuid("approved-v2")),
        )
        client = chain.client()

        result = _run(client, {"AAPL": "195.50"})

        assert [r.reason for r in result.rejections] == [OrderRejectionReason.STALE_TARGET]
        assert client.store.get(PAPER_EXECUTIONS, []) == []

    def test_no_op_decision_carrying_an_order_is_rejected_never_guessed(self) -> None:
        """``no_op`` has no direction. Inferring one from the positions book is the bug."""
        chain = _Chain()
        chain.order(symbol="AAPL", action="no_op", quantity="10")
        client = chain.client()

        result = _run(client, {"AAPL": "195.50"})

        assert [r.reason for r in result.rejections] == [OrderRejectionReason.DATA_UNAVAILABLE]
        assert client.store.get(PAPER_EXECUTIONS, []) == []


class TestHeadsOnly:
    def test_a_superseded_pending_order_is_not_filled(self) -> None:
        """``supersedes_id IS NULL`` is the wrong head test — see ``ledger_io._heads``.

        After a recommit the *root* is the stale row, so a root-based filter would fill
        the order that was already replaced.
        """
        chain = _Chain()
        stale_id = chain.order(symbol="AAPL", action="add", quantity="10", tag="stale")
        fresh_id = chain.order(
            symbol="AAPL", action="add", quantity="4", tag="fresh", supersedes_id=stale_id
        )
        client = chain.client()

        result = _run(client, {"AAPL": "195.50"})

        assert [str(f.order_intent_id) for f in result.fills] == [fresh_id]
        assert Decimal(client.store[PAPER_EXECUTIONS][0]["quantity"]) == Decimal("4")

    def test_one_executed_row_per_pending_order_so_the_chain_cannot_fork(self) -> None:
        chain = _Chain()
        chain.order(symbol="AAPL", action="add", quantity="10")
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        supersedes = [row["supersedes_id"] for row in client.store[ORDER_INTENTS]]
        assert len(supersedes) == len(set(supersedes))


class TestIdempotency:
    def test_rerun_with_the_fill_already_booked_writes_no_duplicate(self) -> None:
        chain = _Chain()
        order_id = chain.order(symbol="AAPL", action="add", quantity="10")
        execution_id = paper_execution_id(UUID(order_id), EXECUTED_DATE)
        chain.executions.append(
            {
                "id": str(execution_id),
                "order_intent_id": order_id,
                "executed_date": EXECUTED_DATE.isoformat(),
                "symbol": "AAPL",
                "quantity": "10",
                "price": "195.50",
            }
        )
        chain.lots.append(
            {
                "id": str(open_lot_id(execution_id)),
                "opened_by_execution_id": str(execution_id),
                "closed_by_execution_id": None,
                "run_date": RUN_DATE.isoformat(),
                "symbol": "AAPL",
                "quantity": "10",
                "open_price": "195.50",
                "status": "open",
                "opened_at": NOW.isoformat(),
                "closed_at": None,
            }
        )
        client = chain.client()

        result = _run(client, {"AAPL": "195.50"})

        assert result.already_booked == ["AAPL"]
        assert result.fills == []
        assert client.store.get(PAPER_EXECUTIONS, []) == []
        assert client.store.get(HOLDING_LOTS, []) == []

    def test_crash_between_the_fill_and_the_status_row_is_repaired(self) -> None:
        """The fill is immutable and already on the record; only the status was missing.

        Leaving it ``pending`` would make a filled order look unfilled forever, and the
        append-only trigger means the pending row can never be edited — so the repair is
        to append the executed row that the crashed run never wrote.
        """
        chain = _Chain()
        order_id = chain.order(symbol="AAPL", action="add", quantity="10")
        chain.executions.append(
            {
                "id": str(paper_execution_id(UUID(order_id), EXECUTED_DATE)),
                "order_intent_id": order_id,
                "executed_date": EXECUTED_DATE.isoformat(),
                "symbol": "AAPL",
                "quantity": "10",
                "price": "195.50",
            }
        )
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        repaired = client.store[ORDER_INTENTS]
        assert [row["status"] for row in repaired] == [OrderIntentStatus.EXECUTED]
        assert repaired[0]["id"] == str(executed_intent_id(UUID(order_id), EXECUTED_DATE))
        assert repaired[0]["supersedes_id"] == order_id

    def test_repair_is_skipped_when_the_executed_row_already_exists(self) -> None:
        chain = _Chain()
        order_id = chain.order(symbol="AAPL", action="add", quantity="10")
        chain.executions.append(
            {
                "id": str(paper_execution_id(UUID(order_id), EXECUTED_DATE)),
                "order_intent_id": order_id,
                "executed_date": EXECUTED_DATE.isoformat(),
                "symbol": "AAPL",
                "quantity": "10",
                "price": "195.50",
            }
        )
        chain.orders.append(
            {
                "id": str(executed_intent_id(UUID(order_id), EXECUTED_DATE)),
                "approved_target_id": chain.orders[0]["approved_target_id"],
                "run_date": RUN_DATE.isoformat(),
                "symbol": "AAPL",
                "quantity": "10",
                "status": "executed",
                "supersedes_id": order_id,
            }
        )
        client = chain.client()

        _run(client, {"AAPL": "195.50"})

        assert client.store == {}


class TestDeterministicIds:
    def test_execution_and_lot_ids_are_stable_across_calls(self) -> None:
        """``holding_lots`` has no UNIQUE constraint, so a randomized lot id would let a
        retry silently double the position. The id must be a function of the fill."""
        order_id = uuid4()
        execution_id = paper_execution_id(order_id, EXECUTED_DATE)
        assert open_lot_id(execution_id) == open_lot_id(execution_id)
        assert executed_intent_id(order_id, EXECUTED_DATE) == executed_intent_id(
            order_id, EXECUTED_DATE
        )

    def test_ids_differ_across_families_and_dates(self) -> None:
        order_id = uuid4()
        execution_id = paper_execution_id(order_id, EXECUTED_DATE)
        other = uuid4()
        assert open_lot_id(execution_id) != close_lot_id(
            closing_execution_id=execution_id, opened_by_execution_id=other
        )
        assert executed_intent_id(order_id, EXECUTED_DATE) != executed_intent_id(
            order_id, date(2026, 6, 16)
        )
        assert executed_intent_id(order_id, EXECUTED_DATE) != paper_execution_id(
            order_id, EXECUTED_DATE
        )

    def test_one_sell_against_two_lineages_yields_two_distinct_lot_rows(self) -> None:
        execution_id = paper_execution_id(uuid4(), EXECUTED_DATE)
        first, second = uuid4(), uuid4()
        assert close_lot_id(
            closing_execution_id=execution_id, opened_by_execution_id=first
        ) != close_lot_id(closing_execution_id=execution_id, opened_by_execution_id=second)
