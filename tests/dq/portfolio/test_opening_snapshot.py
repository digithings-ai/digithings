"""Unit tests for #2589 legacy_opening_snapshot seed and cold-start guard."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any  # score:allow untyped any — heterogeneous fake-row / fixture dicts

import pytest
from digiquant.dashboard.tenancy import house_workspace_id
from digiquant.portfolio.writers.ledger_io import (
    APPROVED_TARGETS,
    COMMITS,
    DECISION_INTENTS,
    ORDER_INTENTS,
    PAPER_EXECUTIONS,
    REQUESTED_TARGETS,
)
from digiquant.portfolio.writers.opening_snapshot import (
    COLD_START_DECLINE,
    HOLDING_LOTS,
    POLICY_VERSION_ID,
    cold_start_requires_seed,
    ensure_legacy_opening_snapshot,
)

pytestmark = pytest.mark.unit

BOOK_D = date(2026, 8, 20)
NOW = datetime(2026, 8, 21, 13, 30, tzinfo=UTC)


class _StoreClient:
    """Minimal fake: selects and inserts share one per-table list (write-then-read)."""

    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {
            "positions": [],
            "nav_history": [],
            "price_history": [],
            COMMITS: [],
            DECISION_INTENTS: [],
            REQUESTED_TARGETS: [],
            APPROVED_TARGETS: [],
            ORDER_INTENTS: [],
            PAPER_EXECUTIONS: [],
            HOLDING_LOTS: [],
        }
        if tables:
            for name, rows in tables.items():
                self.store[name] = list(rows)

    def table(self, name: str) -> _Query:
        self.store.setdefault(name, [])
        return _Query(self.store, name)


class _Query:
    def __init__(self, store: dict[str, list[dict[str, Any]]], name: str) -> None:
        self._store = store
        self._name = name
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._insert_rows: list[dict[str, Any]] | None = None

    def select(self, *_cols: str) -> _Query:
        return self

    def eq(self, col: str, value: Any) -> _Query:
        self._filters.append(("eq", col, value))
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def insert(self, row: dict[str, Any] | list[dict[str, Any]]) -> _Query:
        self._insert_rows = [dict(r) for r in row] if isinstance(row, list) else [dict(row)]
        return self

    def execute(self) -> Any:
        if self._insert_rows is not None:
            self._store.setdefault(self._name, []).extend(self._insert_rows)
            data = list(self._insert_rows)

            class _R:
                pass

            out = _R()
            out.data = data
            return out

        rows = list(self._store.get(self._name, []))
        house = str(house_workspace_id())
        for op, col, value in self._filters:
            if op == "eq" and col == "workspace_id":
                # TEST-FAKE courtesy: legacy house fixtures omit workspace_id.
                rows = [
                    r
                    for r in rows
                    if str(r.get(col)) == str(value) or (r.get(col) is None and str(value) == house)
                ]
            elif op == "eq":
                rows = [r for r in rows if str(r.get(col)) == str(value)]
        if self._limit is not None:
            rows = rows[: self._limit]

        class _R:
            pass

        out = _R()
        out.data = rows
        return out


def _book_client(
    *,
    positions: list[dict[str, Any]] | None = None,
    lots: list[dict[str, Any]] | None = None,
    nav: str = "100000",
    prices: dict[str, str] | None = None,
) -> _StoreClient:
    prices = prices or {"SPY": "500"}
    return _StoreClient(
        {
            "positions": list(positions or []),
            HOLDING_LOTS: list(lots or []),
            "nav_history": [{"date": BOOK_D.isoformat(), "nav": nav}],
            "price_history": [
                {"ticker": t, "date": BOOK_D.isoformat(), "close": p} for t, p in prices.items()
            ],
        }
    )


def test_cold_start_requires_seed_when_lots_empty_and_book_held() -> None:
    client = _book_client(
        positions=[
            {"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()},
            {"ticker": "CASH", "weight_pct": 60, "date": BOOK_D.isoformat()},
        ]
    )
    assert cold_start_requires_seed(client=client, book_date=BOOK_D) is True


def test_cold_start_false_when_open_lot_exists() -> None:
    client = _book_client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()}],
        lots=[{"id": "lot-1", "status": "open"}],
    )
    assert cold_start_requires_seed(client=client, book_date=BOOK_D) is False


def test_cold_start_false_when_prior_book_empty() -> None:
    client = _book_client(positions=[], lots=[])
    assert cold_start_requires_seed(client=client, book_date=BOOK_D) is False


def test_cold_start_false_when_no_prior_book_date() -> None:
    client = _book_client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()}],
        lots=[],
    )
    assert cold_start_requires_seed(client=client, book_date=None) is False


def test_ensure_is_noop_when_open_lots_exist() -> None:
    client = _book_client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "entry_price": "500"}],
        lots=[{"id": "lot-1", "status": "open"}],
    )
    ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok is True
    assert reason == "already seeded"
    assert client.store[COMMITS] == []
    assert client.store[HOLDING_LOTS] == [{"id": "lot-1", "status": "open"}]


def test_ensure_is_noop_when_book_empty() -> None:
    client = _book_client(positions=[{"ticker": "CASH", "weight_pct": 100}])
    ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok is True
    assert reason == "empty book"
    assert client.store[HOLDING_LOTS] == []


def test_ensure_writes_open_lots_matching_book() -> None:
    client = _book_client(
        positions=[
            {
                "ticker": "SPY",
                "weight_pct": 40,
                "entry_price": "500",
                "date": BOOK_D.isoformat(),
            },
            {
                "ticker": "QQQ",
                "weight_pct": 10,
                "entry_price": "400",
                "date": BOOK_D.isoformat(),
            },
            {"ticker": "CASH", "weight_pct": 50, "date": BOOK_D.isoformat()},
        ],
        prices={"SPY": "500", "QQQ": "400"},
    )
    ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok is True
    assert "seeded 2" in reason

    commits = client.store[COMMITS]
    assert len(commits) == 1
    assert commits[0]["policy_version_id"] == POLICY_VERSION_ID

    lots = [r for r in client.store[HOLDING_LOTS] if r.get("status") == "open"]
    assert {r["symbol"] for r in lots} == {"SPY", "QQQ"}
    by_symbol = {r["symbol"]: Decimal(str(r["quantity"])) for r in lots}
    # (40/100)*100000/500 = 80; (10/100)*100000/400 = 25
    assert by_symbol["SPY"] == Decimal("80.000000")
    assert by_symbol["QQQ"] == Decimal("25.000000")

    fills = client.store[PAPER_EXECUTIONS]
    assert all(Decimal(str(f["fee"])) == 0 for f in fills)
    assert all(Decimal(str(f["slippage"])) == 0 for f in fills)
    assert all(r["status"] == "executed" for r in client.store[ORDER_INTENTS])

    # Idempotent retry
    ok2, reason2 = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok2 is True
    assert reason2 == "already seeded"
    assert len(client.store[HOLDING_LOTS]) == 2


def test_ensure_fails_when_nav_missing() -> None:
    client = _book_client(
        positions=[
            {
                "ticker": "SPY",
                "weight_pct": 40,
                "entry_price": "500",
                "date": BOOK_D.isoformat(),
            }
        ],
    )
    client.store["nav_history"] = []
    ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok is False
    assert "nav_history" in reason
    assert client.store[HOLDING_LOTS] == []


def test_ensure_fails_when_prices_missing() -> None:
    client = _book_client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()}],
        prices={},
    )
    client.store["price_history"] = []
    ok, reason = ensure_legacy_opening_snapshot(client, BOOK_D, now=NOW)
    assert ok is False
    assert "SPY" in reason
    assert client.store[HOLDING_LOTS] == []


def test_cold_start_decline_constant_names_seed_policy() -> None:
    assert "legacy_opening_snapshot" in COLD_START_DECLINE
    assert "#2589" in COLD_START_DECLINE
