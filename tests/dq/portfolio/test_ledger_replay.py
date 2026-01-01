"""DIG-2816: the write-side ledger replay and its fail-closed contract.

``positions.weight_pct`` is a drift-carrying ACTUAL written by several independent
writers. ``position_events`` is the ledger of INTENDED targets, and Chris's
2026-10-10 verdict is that the 25-Sep rebalance targets (UUP 15 / DBO 10 / XLV 10)
are correct while the persisted book is not. These tests pin the two properties
the fix depends on, both of which are easy to break silently:

1. FAIL CLOSED — a missing, unreadable, future-dated or unrecognised event never
   invents a weight and never zeroes one. A failed ledger READ is never reported
   as an agreement, which is the failure mode that would let an unreconciled book
   through a gate that believes it passed.
2. NOTHING IS HIDDEN — every unreconciled row, every drift and every conflict is
   counted and named in ``summary()``, so "the ledger agrees" can never be a
   silent no-op.
"""

from __future__ import annotations

from typing import Any

import pytest
from digiquant.portfolio.ledger_replay import (
    LedgerReconcileError,
    fetch_ledger_state,
    is_calendar_date,
    reconcile_book,
    replay_ledger_weights,
    round_pct,
)

pytestmark = pytest.mark.unit

BOOK = "2026-09-25"


def _ev(date: str, ticker: str, event: str, weight: Any = None, **extra: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"date": date, "ticker": ticker, "event": event, "weight_pct": weight}
    row.update(extra)
    return row


class TestReplay:
    def test_open_add_trim_set_targets(self) -> None:
        state = replay_ledger_weights(
            [
                _ev("2026-09-25", "UUP", "OPEN", 15.0),
                _ev("2026-09-25", "DBO", "ADD", 10.0),
                _ev("2026-09-25", "XLV", "TRIM", 10.0),
            ],
            BOOK,
        )
        assert state.covered
        assert {t: tg.weight_pct for t, tg in state.targets.items()} == {
            "UUP": 15.0,
            "DBO": 10.0,
            "XLV": 10.0,
        }
        assert state.applied == 3

    def test_hold_is_not_a_weight_setting_event(self) -> None:
        state = replay_ledger_weights(
            [_ev("2026-09-25", "UUP", "OPEN", 15.0), _ev("2026-09-25", "UUP", "HOLD", 99.0)], BOOK
        )
        assert state.targets["UUP"].weight_pct == 15.0
        assert state.ignored == 1

    def test_exit_removes_the_target_and_records_it(self) -> None:
        state = replay_ledger_weights(
            [_ev("2026-09-24", "UUP", "OPEN", 15.0), _ev("2026-09-25", "UUP", "EXIT")], BOOK
        )
        assert "UUP" not in state.targets
        assert "UUP" in state.exited

    def test_reopening_after_an_exit_clears_the_conflict_flag(self) -> None:
        state = replay_ledger_weights(
            [
                _ev("2026-09-24", "UUP", "OPEN", 15.0),
                _ev("2026-09-24", "UUP", "EXIT"),
                _ev("2026-09-25", "UUP", "OPEN", 12.0),
            ],
            BOOK,
        )
        assert state.targets["UUP"].weight_pct == 12.0
        assert "UUP" not in state.exited

    def test_a_later_event_on_the_same_day_wins(self) -> None:
        state = replay_ledger_weights(
            [_ev("2026-09-25", "UUP", "OPEN", 30.0), _ev("2026-09-25", "UUP", "TRIM", 15.0)], BOOK
        )
        assert state.targets["UUP"].weight_pct == 15.0

    def test_events_after_the_book_date_are_dropped(self) -> None:
        """A committed snapshot must never reconcile against a LATER decision."""
        state = replay_ledger_weights(
            [_ev("2026-09-25", "UUP", "OPEN", 15.0), _ev("2026-09-28", "UUP", "TRIM", 5.0)], BOOK
        )
        assert state.targets["UUP"].weight_pct == 15.0
        assert state.future == 1

    def test_an_unusable_weight_leaves_the_prior_target_standing(self) -> None:
        """The dangerous direction is zeroing: a NULL/NaN/negative weight must never
        silently read as "this position went to zero"."""
        for bad in (None, float("nan"), -1.0):
            state = replay_ledger_weights(
                [_ev("2026-09-24", "UUP", "OPEN", 15.0), _ev("2026-09-25", "UUP", "TRIM", bad)],
                BOOK,
            )
            assert state.unusable_weight == 1
            assert state.targets["UUP"].weight_pct == 15.0

    def test_junk_rows_are_ignored_not_fatal(self) -> None:
        state = replay_ledger_weights(
            [
                "not-a-dict",
                _ev("2026-09-25", "", "OPEN", 15.0),
                _ev("2026-02-31", "DBO", "OPEN", 10.0),
                _ev("2026-09-25", "XLV", "REBALANCED", 10.0),
                _ev("2026-09-25", "IWM", "OPEN", 5.0),
            ],
            BOOK,
        )
        assert set(state.targets) == {"IWM"}
        assert state.ignored == 4

    def test_an_unusable_book_date_yields_an_uncovered_state(self) -> None:
        for bad in (None, "", "not-a-date", "2026-02-31"):
            state = replay_ledger_weights([_ev("2026-09-25", "UUP", "OPEN", 15.0)], bad)
            assert not state.covered
            assert state.targets == {}


class TestHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2026-09-25", True),
            ("2026-02-31", False),
            ("2026-9-5", False),
            ("2026-09-25T00:00", False),
        ],
    )
    def test_is_calendar_date(self, value: str, expected: bool) -> None:
        assert is_calendar_date(value) is expected

    def test_round_pct_is_not_python_bankers_rounding(self) -> None:
        """JS ``Math.round`` rounds half away from zero on both sides; Python's
        ``round`` is banker's rounding and would diverge on a .5 tie."""
        assert round_pct(1.0000005) == 1.000001
        assert round_pct(-1.0000005) == -1.000001


class TestReconcileBook:
    def _state(self):
        return replay_ledger_weights(
            [
                _ev("2026-09-25", "UUP", "OPEN", 15.0),
                _ev("2026-09-25", "DBO", "OPEN", 10.0),
                _ev("2026-09-24", "XLV", "OPEN", 12.0),
                _ev("2026-09-25", "XLV", "EXIT"),
            ],
            BOOK,
        )

    def test_anchor_mode_rewrites_the_drifted_weight(self) -> None:
        rows = [
            {"ticker": "UUP", "weight_pct": 29.9733},
            {"ticker": "CASH", "weight_pct": 55.0},
        ]
        report = reconcile_book(rows, self._state(), writer="t", mode="anchor")
        assert {r["ticker"]: r["weight_pct"] for r in rows} == {
            "UUP": 15.0,
            "CASH": 55.0,
        }
        assert report.anchored == ["UUP"]
        assert report.drift_pp["UUP"] == pytest.approx(14.9733)

    def test_cash_is_never_a_ledger_target(self) -> None:
        """CASH carries a required category row and never appears in the ledger, so
        anchoring it would be a pure no-op that hides a broken ledger read."""
        rows = [{"ticker": "CASH", "weight_pct": 55.0}]
        report = reconcile_book(rows, self._state(), writer="t", mode="anchor")
        assert rows[0]["weight_pct"] == 55.0
        assert report.anchored == []

    def test_a_book_holding_an_exited_ticker_is_a_conflict_in_both_modes(self) -> None:
        """Anchor mode is NOT an escape hatch. Persisting a book that still holds a
        name the ledger EXITed is the DIG-2816 defect itself, so the raise is on by
        default (``strict=True``) whichever mode rewrites weights."""
        for mode in ("anchor", "strict"):
            rows = [{"ticker": "XLV", "weight_pct": 10.0}]
            with pytest.raises(LedgerReconcileError) as excinfo:
                reconcile_book(rows, self._state(), writer="t", mode=mode)
            assert excinfo.value.report.conflicts == ["XLV"]
            assert "CONFLICT=XLV" in str(excinfo.value)

    def test_a_non_strict_call_records_the_conflict_without_raising(self) -> None:
        rows = [{"ticker": "XLV", "weight_pct": 10.0}]
        report = reconcile_book(rows, self._state(), writer="t", mode="anchor", strict=False)
        assert report.conflicts == ["XLV"]
        assert "CONFLICT=XLV" in report.summary()
        assert not report.clean

    def test_strict_mode_does_not_rewrite_weights(self) -> None:
        rows = [{"ticker": "UUP", "weight_pct": 29.9733}]
        report = reconcile_book(rows, self._state(), writer="sync", mode="strict")
        assert rows[0]["weight_pct"] == 29.9733
        assert report.anchored == []
        assert report.drifted() == ["UUP"]

    def test_a_ticker_with_no_ledger_row_is_named_not_hidden(self) -> None:
        rows = [{"ticker": "TLT", "weight_pct": 5.0}]
        report = reconcile_book(rows, self._state(), writer="t", mode="anchor")
        assert report.unreconciled == ["TLT"]
        assert rows[0]["weight_pct"] == 5.0

    def test_a_ledger_target_with_no_book_row_is_reported(self) -> None:
        report = reconcile_book([], self._state(), writer="t", mode="anchor")
        assert report.ledger_only == ["DBO", "UUP"]

    def test_an_uncovered_state_never_rewrites_or_raises(self) -> None:
        """FAIL CLOSED. A ledger read that failed must behave exactly like no ledger:
        the book is written untouched and nothing is reported as reconciled."""
        rows = [{"ticker": "XLV", "weight_pct": 10.0}]
        report = reconcile_book(rows, replay_ledger_weights([], BOOK), writer="t", mode="strict")
        assert rows[0]["weight_pct"] == 10.0
        assert report.anchored == []
        assert report.conflicts == []
        assert not report.clean

    def test_summary_is_one_greppable_line_carrying_every_counter(self) -> None:
        report = reconcile_book(
            [{"ticker": "UUP", "weight_pct": 29.9733}], self._state(), writer="w", mode="anchor"
        )
        summary = report.summary()
        assert summary.startswith("ledger-reconcile[w] mode=anchor")
        assert "\n" not in summary
        for token in (
            "covered=",
            "anchored=",
            "drifted=",
            "unreconciled=",
            "conflicts=",
            "applied=",
        ):
            assert token in summary


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
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            else:
                rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
        return type("R", (), {"data": rows})()


class _FakeClient:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self.tables.get(name, []))


class TestFetchLedgerState:
    def test_reads_the_ledger_up_to_and_including_the_book_date(self) -> None:
        sb = _FakeClient(
            {
                "position_events": [
                    _ev("2026-09-25", "UUP", "OPEN", 15.0, workspace_id="ws-1"),
                    _ev("2026-09-28", "UUP", "TRIM", 5.0, workspace_id="ws-1"),
                ]
            }
        )
        state = fetch_ledger_state(sb, "ws-1", BOOK)
        assert state.covered
        assert state.targets["UUP"].weight_pct == 15.0
        assert state.future == 0

    def test_a_failing_read_is_an_uncovered_state_with_a_read_error(self) -> None:
        """A 500 that returns an empty list would otherwise read as 'the ledger
        agrees' — the exact silent-pass this gate exists to prevent."""

        class _Exploding:
            def table(self, _name: str) -> Any:
                raise RuntimeError("postgrest 500")

        state = fetch_ledger_state(_Exploding(), "ws-1", BOOK)
        assert not state.covered
        assert state.read_error
        assert "READ_ERROR=" in reconcile_book([], state, writer="w").summary()

    def test_a_missing_data_attribute_is_not_an_agreement(self) -> None:
        class _NoData:
            def table(self, _name: str) -> Any:
                return type("Q", (), {"execute": lambda _s: object()})()

        assert not fetch_ledger_state(_NoData(), "ws-1", BOOK).covered
