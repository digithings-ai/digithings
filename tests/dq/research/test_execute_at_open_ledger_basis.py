"""DIG-2816: ``execute_at_open`` must compare against the LEDGER, not the stored book.

The regression: every ``prev_weight_pct`` this writer stamps came from the previous
committed ``positions`` book, and that table is written by several independent
writers with no check against ``position_events``. So a stale row became the
comparison basis and the 28-Sep events replayed the 25-Sep rebalance. These tests
pin the replacement (``_comparison_book_weights``) together with its two
non-negotiable properties: it FAILS CLOSED to the stored book, and it never invents
a holding that the book does not contain.

Loaded via importlib.util like the sibling ``test_execute_at_open.py`` — the script
lives in ``digiquant/scripts/``, which is not an installed package.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from digiquant.dashboard.tenancy import house_workspace_id

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "scripts"
    / "research"
    / "execute_at_open.py"
)


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("execute_at_open_ledger_basis", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
_comparison_book_weights = _mod._comparison_book_weights

_WS = str(house_workspace_id())
_BOOK = "2026-09-25"


class _FakeQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self._filters: list[tuple[str, str, Any]] = []

    def select(self, *_cols: str) -> "_FakeQuery":
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def lte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def order(self, *_a: Any) -> "_FakeQuery":
        return self

    def execute(self) -> Any:
        rows = list(self.rows)
        for op, col, val in self._filters:
            # A null ``workspace_id`` matches the house filter, exactly as the
            # sibling test's fake does — the column is nullable in production.
            if op == "eq":
                rows = [
                    r
                    for r in rows
                    if r.get(col) == val or (col == "workspace_id" and r.get(col) is None)
                ]
            else:
                rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
        return type("R", (), {"data": rows})()


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> _FakeQuery:
        if name not in self.tables:
            raise AssertionError(f"unexpected table read: {name}")
        return _FakeQuery(self.tables[name])


def _pos(ticker: str, weight: Any, date: str = _BOOK) -> dict[str, Any]:
    return {"date": date, "ticker": ticker, "weight_pct": weight}


def _event(date: str, ticker: str, event: str, weight: Any) -> dict[str, Any]:
    return {
        "date": date,
        "ticker": ticker,
        "event": event,
        "weight_pct": weight,
        "prev_weight_pct": None,
    }


class TestLedgerWins:
    def test_the_ledger_target_overrides_the_drifted_stored_weight(self) -> None:
        """The DIG-2816 symptom: the stored book says 29.97, the ledger says 15.0.
        ``prev_weight_pct`` must be 15.0, or every event derived from it is wrong."""
        sb = _FakeClient(
            {
                "positions": [_pos("UUP", 29.9733), _pos("DBO", 4.7194)],
                "position_events": [
                    _event("2026-09-25", "UUP", "TRIM", 15.0),
                    _event("2026-09-25", "DBO", "TRIM", 10.0),
                ],
            }
        )
        assert _comparison_book_weights(sb, _BOOK) == {"UUP": 15.0, "DBO": 10.0}

    def test_a_later_event_is_ignored(self) -> None:
        sb = _FakeClient(
            {
                "positions": [_pos("UUP", 29.9733)],
                "position_events": [
                    _event("2026-09-25", "UUP", "TRIM", 15.0),
                    _event("2026-09-28", "UUP", "TRIM", 5.0),
                ],
            }
        )
        assert _comparison_book_weights(sb, _BOOK)["UUP"] == 15.0

    def test_cash_is_excluded(self) -> None:
        sb = _FakeClient(
            {
                "positions": [_pos("UUP", 29.9733), _pos("CASH", 55.0)],
                "position_events": [_event("2026-09-25", "UUP", "TRIM", 15.0)],
            }
        )
        assert set(_comparison_book_weights(sb, _BOOK)) == {"UUP"}


class TestFailsClosed:
    def test_an_empty_ledger_leaves_the_stored_book_untouched(self) -> None:
        sb = _FakeClient({"positions": [_pos("UUP", 29.9733)], "position_events": []})
        assert _comparison_book_weights(sb, _BOOK) == {"UUP": 29.9733}

    def test_a_failing_ledger_read_leaves_the_stored_book_untouched(self) -> None:
        """A read that RAISES must not be mistaken for a ledger that agrees — the
        stored book stands and the next writer still sees the same drift."""

        class _Exploding:
            def table(self, name: str) -> Any:
                if name == "positions":
                    return _FakeQuery([_pos("UUP", 29.9733)])
                raise RuntimeError("postgrest 503")

        assert _comparison_book_weights(_Exploding(), _BOOK) == {"UUP": 29.9733}

    def test_no_book_date_means_no_comparison_book(self) -> None:
        sb = _FakeClient(
            {
                "positions": [_pos("UUP", 1.0)],
                "position_events": [_event("2026-09-25", "UUP", "TRIM", 15.0)],
            }
        )
        assert _comparison_book_weights(sb, None) == {}
        assert _comparison_book_weights(sb, "") == {}


class TestInvariants:
    def test_a_ledger_only_ticker_is_not_invented_into_the_book(self) -> None:
        """The ledger mentions XLV but the book does not hold it. It was not held, so
        adding it would stamp a fabricated ``prev_weight_pct`` into the ledger."""
        sb = _FakeClient(
            {
                "positions": [_pos("UUP", 29.9733)],
                "position_events": [
                    _event("2026-09-25", "UUP", "TRIM", 15.0),
                    _event("2026-09-25", "XLV", "OPEN", 10.0),
                ],
            }
        )
        assert set(_comparison_book_weights(sb, _BOOK)) == {"UUP"}

    def test_a_null_weight_stays_none_rather_than_becoming_zero(self) -> None:
        """``_event_kind_from_order_delta`` reads ``None`` as "no prior book" and lets
        the lot side decide OPEN vs ADD; ``0.0`` would be read as a real prior weight
        and reclassify the event."""
        sb = _FakeClient({"positions": [_pos("UUP", None)], "position_events": []})
        assert _comparison_book_weights(sb, _BOOK) == {"UUP": None}

    def test_tickers_are_uppercased(self) -> None:
        sb = _FakeClient(
            {
                "positions": [_pos("uup", 29.9733)],
                "position_events": [_event("2026-09-25", "UUP", "TRIM", 15.0)],
            }
        )
        assert _comparison_book_weights(sb, _BOOK) == {"UUP": 15.0}
