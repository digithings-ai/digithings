"""Unit tests for #2589 cold-start decline (empty lots + non-empty prior book)."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from digiquant.olympus.hermes.writers.execution_io import (
    COLD_START_DECLINE,
    HOLDING_LOTS,
    cold_start_blocks_ledger,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

BOOK_D = date(2026, 8, 20)


class _Client(FakeSupabaseClient):
    def __init__(
        self,
        *,
        positions: list[dict[str, Any]] | None = None,
        lots: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self._tables = {
            "positions": list(positions or []),
            HOLDING_LOTS: list(lots or []),
        }

    def table(self, name: str) -> Any:  # noqa: ANN401
        rows = self._tables.get(name, [])
        return _Query(rows)


class _Query:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None

    def select(self, *_cols: str) -> _Query:
        return self

    def eq(self, col: str, value: Any) -> _Query:  # noqa: ANN401
        self._filters.append((col, value))
        return self

    def limit(self, n: int) -> _Query:
        self._limit = n
        return self

    def execute(self) -> Any:  # noqa: ANN401
        out = self._rows
        for col, value in self._filters:
            out = [r for r in out if str(r.get(col)) == str(value)]
        if self._limit is not None:
            out = out[: self._limit]

        class _R:
            data = out

        return _R()


def test_cold_start_declines_when_lots_empty_and_book_held() -> None:
    client = _Client(
        positions=[
            {"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()},
            {"ticker": "CASH", "weight_pct": 60, "date": BOOK_D.isoformat()},
        ],
        lots=[],
    )
    assert cold_start_blocks_ledger(client=client, prior_book_date=BOOK_D) == COLD_START_DECLINE


def test_cold_start_allows_when_open_lot_exists() -> None:
    client = _Client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()}],
        lots=[{"id": "lot-1", "status": "open"}],
    )
    assert cold_start_blocks_ledger(client=client, prior_book_date=BOOK_D) is None


def test_cold_start_allows_when_prior_book_empty() -> None:
    client = _Client(positions=[], lots=[])
    assert cold_start_blocks_ledger(client=client, prior_book_date=BOOK_D) is None


def test_cold_start_allows_when_no_prior_book_date() -> None:
    client = _Client(
        positions=[{"ticker": "SPY", "weight_pct": 40, "date": BOOK_D.isoformat()}],
        lots=[],
    )
    assert cold_start_blocks_ledger(client=client, prior_book_date=None) is None
