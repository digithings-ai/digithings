"""Unit tests for the ledger reconvergence planner (#4010) — dry-run first.

The plan compares the LIVE executed ledger book (holding lots) with a target
committed book (positions) and produces the trades that would converge one onto
the other. Catch-up books one aggregate trade set at the execution date's marks;
backdated walks each book date. Nothing here touches the network: the fake
client carries the canned reads and records inserts.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from digiquant.portfolio.writers import reconvergence as rc
from digiquant.portfolio.writers.execution_io import (
    HOLDING_LOTS,
    close_lot_id,
    paper_execution_id,
)
from digiquant.portfolio.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
)

from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

BOOK_D = date(2026, 9, 10)
EXEC_D = date(2026, 9, 11)
EARLY_D = date(2026, 9, 1)
NEXT_D = date(2026, 9, 2)
NOW = datetime(2026, 9, 11, 13, 30, tzinfo=UTC)


def _stamp(day: date) -> str:
    return datetime.combine(day, time(13, 30), tzinfo=UTC).isoformat()


def _lot(
    symbol: str,
    quantity: str | float,
    *,
    opened_at: str | None = None,
    open_price: str = "150.00",
    execution_id: Any | None = None,
) -> dict[str, Any]:
    execution = execution_id or uuid5(NAMESPACE_URL, f"lot:{symbol}:{quantity}")
    return {
        "id": str(rc.open_lot_id(execution)),
        "opened_by_execution_id": str(execution),
        "closed_by_execution_id": None,
        "run_date": "2026-05-04",
        "symbol": symbol,
        "quantity": quantity,
        "open_price": open_price,
        "status": "open",
        "opened_at": opened_at or "2026-05-04T13:30:00+00:00",
        "closed_at": None,
        "recorded_at": "2026-05-04T13:30:00+00:00",
    }


def _book_rows(day: date, weights: dict[str, float]) -> list[dict[str, Any]]:
    return [
        {"date": day.isoformat(), "ticker": ticker, "weight_pct": weight}
        for ticker, weight in weights.items()
    ]


def _nav_rows(navs: dict[date, float]) -> list[dict[str, Any]]:
    return [{"date": day.isoformat(), "nav": nav} for day, nav in navs.items()]


def _marks(day: str, marks: dict[str, float]) -> list[dict[str, Any]]:
    return [{"date": day, "ticker": ticker, "close": close} for ticker, close in marks.items()]


def _client(
    *,
    positions: list[dict[str, Any]] | None = None,
    navs: list[dict[str, Any]] | None = None,
    prices: list[dict[str, Any]] | None = None,
    lots: list[dict[str, Any]] | None = None,
    commits: list[dict[str, Any]] | None = None,
) -> FakeSupabaseClient:
    canned: dict[str, list[dict[str, Any]]] = {}
    if positions:
        canned["positions"] = positions
    if navs:
        canned["nav_history"] = navs
    if prices:
        canned["price_history"] = prices
    if lots:
        canned[HOLDING_LOTS] = lots
    if commits:
        canned[COMMITS] = commits
    return FakeSupabaseClient(canned_reads=canned)


def test_catch_up_plans_a_buy_to_reach_the_committed_weight() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 5.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"AAA": 100.0}),
        lots=[_lot("AAA", "20")],
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, exec_date=EXEC_D, mode="catch-up")
    assert plan.mode == "catch-up"
    assert [leg.symbol for leg in plan.legs] == ["AAA"]
    leg = plan.legs[0]
    assert leg.side == "buy"
    assert leg.quantity == Decimal("30")
    assert leg.mark == Decimal("100")
    assert plan.buy_notional == Decimal("3000.00")
    assert plan.sell_notional == Decimal("0.00")


def test_catch_up_sells_the_surplus_and_orders_and_renders_legs() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"GLD": 5.0, "AAA": 5.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"GLD": 250.0, "AAA": 100.0}),
        lots=[_lot("GLD", "100")],
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, exec_date=EXEC_D, mode="catch-up")
    assert [(leg.symbol, leg.side) for leg in plan.legs] == [("AAA", "buy"), ("GLD", "sell")]
    sold = next(leg for leg in plan.legs if leg.symbol == "GLD")
    assert sold.side == "sell"
    assert sold.quantity == Decimal("80")
    assert sold.notional == Decimal("20000.00")
    assert plan.sell_notional == Decimal("20000.00")
    assert plan.buy_notional == Decimal("5000.00")
    text = rc.render_plan(plan)
    assert "dry run" in text
    assert "sell GLD 80" in text
    assert "buy AAA 50" in text


def test_catch_up_skips_dust_below_the_min_notional() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 0.1}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"AAA": 100.0}),
    )
    plan = rc.plan_convergence(
        client=client,
        book_date=BOOK_D,
        exec_date=EXEC_D,
        mode="catch-up",
        min_notional=Decimal("500.00"),
    )
    assert plan.legs == ()
    assert any("dust" in warning for warning in plan.warnings)


def test_backdated_walk_carries_running_quantities_across_book_dates() -> None:
    client = _client(
        positions=_book_rows(EARLY_D, {"AAA": 5.0})
        + _book_rows(NEXT_D, {"AAA": 50.0, "BBB": 50.0}),
        navs=_nav_rows({EARLY_D: 100_000.0, NEXT_D: 101_000.0}),
        prices=_marks(EARLY_D.isoformat(), {"AAA": 100.0})
        + _marks(NEXT_D.isoformat(), {"AAA": 100.0, "BBB": 50.0}),
        lots=[_lot("AAA", "100")],
    )
    plan = rc.plan_convergence(
        client=client,
        book_date=NEXT_D,
        mode="backdated",
        since=EARLY_D,
    )
    legs = [(leg.book_date, leg.symbol, leg.side, leg.quantity) for leg in plan.legs]
    assert legs == [
        (EARLY_D, "AAA", "sell", Decimal("50")),
        (NEXT_D, "AAA", "buy", Decimal("455")),
        (NEXT_D, "BBB", "buy", Decimal("1010")),
    ]


def test_apply_is_refused_when_a_reconvergence_commit_already_exists() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 5.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"AAA": 100.0}),
        commits=[
            {
                "id": str(uuid5(NAMESPACE_URL, "prior")),
                "run_date": EXEC_D.isoformat(),
                "policy_version_id": rc.POLICY_VERSION_ID,
                "supersedes_id": None,
                "effective_at": _stamp(EXEC_D),
                "recorded_at": _stamp(EXEC_D),
            }
        ],
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, exec_date=EXEC_D, mode="catch-up")
    applied, reason = rc.apply_catch_up(client=client, plan=plan, now=NOW)
    assert applied is False
    assert "already applied" in reason
    assert client.store.get(COMMITS, []) == []


def test_apply_catch_up_writes_the_labeled_buy_chain() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 5.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"AAA": 100.0}),
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, exec_date=EXEC_D, mode="catch-up")
    applied, reason = rc.apply_catch_up(client=client, plan=plan, now=NOW)
    assert applied is True
    assert reason == "applied"

    commit = client.store[COMMITS][0]
    assert commit["policy_version_id"] == rc.POLICY_VERSION_ID
    assert commit["run_date"] == EXEC_D.isoformat()

    decision = client.store[DECISION_INTENTS][0]
    assert decision["symbol"] == "AAA"
    assert decision["action"] == "add"
    assert decision["reason"] == "new_conviction"

    requested = client.store[REQUESTED_TARGETS][0]
    assert Decimal(requested["requested_quantity"]) == Decimal("50")
    approved = client.store[APPROVED_TARGETS][0]
    assert Decimal(approved["approved_quantity"]) == Decimal("50")

    order = client.store[ORDER_INTENTS][0]
    assert order["status"] == "executed"
    assert Decimal(order["quantity"]) == Decimal("50")

    execution = client.store[PAPER_EXECUTIONS][0]
    assert execution["id"] == str(paper_execution_id(order["id"], EXEC_D))
    assert Decimal(execution["fee"]) == Decimal("0.00")
    assert Decimal(execution["slippage"]) == Decimal("0.00")

    lots = client.store[HOLDING_LOTS]
    assert len(lots) == 1
    assert lots[0]["status"] == "open"
    assert lots[0]["opened_by_execution_id"] == execution["id"]
    assert Decimal(lots[0]["quantity"]) == Decimal("50")


def test_apply_catch_up_closes_lots_fifo_for_a_sell() -> None:
    lineage_execution = uuid5(NAMESPACE_URL, "lineage")
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 2.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(EXEC_D.isoformat(), {"AAA": 100.0}),
        lots=[_lot("AAA", "100", open_price="150.00", execution_id=lineage_execution)],
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, exec_date=EXEC_D, mode="catch-up")
    applied, reason = rc.apply_catch_up(client=client, plan=plan, now=NOW)
    assert applied is True
    assert reason == "applied"

    decision = client.store[DECISION_INTENTS][0]
    assert decision["action"] == "trim"
    assert decision["reason"] == "conviction_reduced"

    order = client.store[ORDER_INTENTS][0]
    assert order["status"] == "executed"
    assert Decimal(order["quantity"]) == Decimal("80")
    execution = client.store[PAPER_EXECUTIONS][0]
    lots = client.store[HOLDING_LOTS]
    assert len(lots) == 1
    closed = lots[0]
    assert closed["status"] == "closed"
    assert Decimal(closed["quantity"]) == Decimal("80")
    assert closed["open_price"] == "150.00"
    assert closed["closed_at"].startswith(EXEC_D.isoformat())
    assert closed["id"] == str(
        close_lot_id(
            closing_execution_id=execution["id"],
            opened_by_execution_id=str(lineage_execution),
        )
    )


def test_apply_refuses_a_backdated_plan_in_v1() -> None:
    client = _client(
        positions=_book_rows(BOOK_D, {"AAA": 5.0}),
        navs=_nav_rows({BOOK_D: 100_000.0}),
        prices=_marks(BOOK_D.isoformat(), {"AAA": 100.0}),
    )
    plan = rc.plan_convergence(client=client, book_date=BOOK_D, mode="backdated", since=BOOK_D)
    with pytest.raises(ValueError, match="backdated"):
        rc.apply_catch_up(client=client, plan=plan, now=NOW)
