"""Unit tests for execute_at_open.py — the `position_events` ledger writer (#1743).

Regression under test: the comparison book was derived from the previous calendar
Mon–Fri (`_prior_trading_date`) rather than the last date that actually has
`positions` rows. The pipeline does not commit a book every weekday, so on every
gap day the prior weights came back empty — EXIT became unreachable (a dropped
ticker never entered the diff) and every surviving holding was written as an OPEN
with `prev_weight_pct = NULL`. Live evidence: 31 OPEN / 20 TRIM / 8 ADD / 17 HOLD
and **zero** EXIT across the table's entire history.

Fixtures use the real production shape of the 2026-07-29 → 2026-07-31 transition
(2026-07-30 has no `positions` rows because that run was cancelled).

Loaded via importlib.util like the other script-level tests (`digiquant/scripts/`
is not an installed package).
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas" / "execute_at_open.py"
)


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("execute_at_open", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
_prior_book_date = _mod._prior_book_date
_prior_trading_date = _mod._prior_trading_date
_book_weights = _mod._book_weights
build_events_from_positions_book = _mod.build_events_from_positions_book
build_events_from_digest_snapshot = _mod.build_events_from_digest_snapshot
_hold_events_for_positions_not_in_rebalance = _mod._hold_events_for_positions_not_in_rebalance
resolve_rebalance_payload_fallback = _mod.resolve_rebalance_payload_fallback


# ─── Fake PostgREST client ──────────────────────────────────────────────────
#
# Purpose-built rather than reusing ``tests.dq.atlas.test_supabase_io``'s
# ``FakeSupabaseClient``: that fake's ``execute()`` silently drops filter ops it
# does not recognise, and it does not implement ``neq``. ``_prior_book_date``
# issues ``.neq("ticker", "CASH")``, so under the shared fake that filter would be
# ignored — the tests below would still pass against the unfixed source and prove
# nothing. Only the operations execute_at_open.py actually issues are modelled.


@dataclass
class _FakeQuery:
    rows: list[dict[str, Any]]
    upserts: list[dict[str, Any]]
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("neq", col, val))
        return self

    def lt(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lt", col, val))
        return self

    def order(self, col: str, desc: bool = False) -> "_FakeQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> "_FakeQuery":
        self.upserts.append({**row, "_on_conflict": on_conflict})
        return self

    def execute(self) -> Any:
        rows = list(self.rows)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "neq":
                rows = [r for r in rows if r.get(col) != val]
            elif op == "lt":
                rows = [r for r in rows if str(r.get(col, "")) < str(val)]
            else:  # pragma: no cover - guard against an untested op sneaking in
                raise AssertionError(f"unsupported filter op: {op}")
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: str(r.get(col, "")), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeClient:
    """Per-table canned reads plus a captured upsert log."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    upserts: list[dict[str, Any]] = field(default_factory=list)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(rows=list(self.tables.get(name, [])), upserts=self.upserts)


# ─── Production fixture: the 2026-07-29 → 2026-07-31 book transition ────────
#
# 2026-07-30 (the calendar-prior weekday of 07-31) has no rows at all — its run
# was cancelled after 4h. DBO and XLI leave the book; UUP has been held
# continuously since 06-23; FXI, IBIT and VGK are genuine new entries.

_BOOK_0729 = [
    {"date": "2026-07-29", "ticker": "CASH", "weight_pct": "28.1617", "thesis_id": None},
    {"date": "2026-07-29", "ticker": "DBO", "weight_pct": "1.7891", "thesis_id": "oil-fed"},
    {"date": "2026-07-29", "ticker": "IJR", "weight_pct": "5.0", "thesis_id": "cta-risk"},
    {"date": "2026-07-29", "ticker": "UUP", "weight_pct": "39.9226", "thesis_id": "oil-fed"},
    {"date": "2026-07-29", "ticker": "XLE", "weight_pct": "4.9262", "thesis_id": "oil-fed"},
    {"date": "2026-07-29", "ticker": "XLF", "weight_pct": "10.1141", "thesis_id": "vehicle-xlf"},
    {"date": "2026-07-29", "ticker": "XLI", "weight_pct": "4.9745", "thesis_id": "vehicle-xli"},
    {"date": "2026-07-29", "ticker": "XLV", "weight_pct": "5.1118", "thesis_id": "healthcare"},
]

_BOOK_0731 = [
    {"date": "2026-07-31", "ticker": "CASH", "weight_pct": "9.9741", "thesis_id": None},
    {"date": "2026-07-31", "ticker": "FXI", "weight_pct": "10.0", "thesis_id": "usd-stall"},
    {"date": "2026-07-31", "ticker": "IBIT", "weight_pct": "5.0", "thesis_id": "crypto"},
    {"date": "2026-07-31", "ticker": "IJR", "weight_pct": "5.0574", "thesis_id": "vehicle-ijr"},
    {"date": "2026-07-31", "ticker": "UUP", "weight_pct": "25.0", "thesis_id": "usd-stall"},
    {"date": "2026-07-31", "ticker": "VGK", "weight_pct": "15.0", "thesis_id": "usd-stall"},
    {"date": "2026-07-31", "ticker": "XLE", "weight_pct": "4.9685", "thesis_id": "tariff-oil"},
    {"date": "2026-07-31", "ticker": "XLF", "weight_pct": "15.0", "thesis_id": "vehicle-xlf"},
    {"date": "2026-07-31", "ticker": "XLV", "weight_pct": "10.0", "thesis_id": "healthcare"},
]


def _gap_day_client() -> _FakeClient:
    return _FakeClient(tables={"positions": [*_BOOK_0729, *_BOOK_0731]})


def _events_by_ticker(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(e["ticker"]): e for e in events}


# ─── _prior_book_date ───────────────────────────────────────────────────────


class TestPriorBookDate:
    def test_skips_gap_days_and_returns_last_committed_book(self) -> None:
        """07-30 has no rows; the prior book is 07-29, not the prior weekday."""
        assert _prior_book_date(_gap_day_client(), "2026-07-31") == "2026-07-29"

    def test_is_strictly_before_execution_date(self) -> None:
        assert _prior_book_date(_gap_day_client(), "2026-07-29") is None

    def test_none_when_no_earlier_book_exists(self) -> None:
        sb = _FakeClient(tables={"positions": list(_BOOK_0729)})
        assert _prior_book_date(sb, "2026-07-29") is None

    def test_ignores_a_cash_only_date(self) -> None:
        """Defensive: no such date exists in production, but a CASH sweep row is
        not a book and must not become the comparison basis."""
        sb = _FakeClient(
            tables={
                "positions": [
                    *_BOOK_0729,
                    {"date": "2026-07-30", "ticker": "CASH", "weight_pct": "100.0"},
                    *_BOOK_0731,
                ]
            }
        )
        assert _prior_book_date(sb, "2026-07-31") == "2026-07-29"

    def test_truncates_a_timestamp_valued_date(self) -> None:
        sb = _FakeClient(
            tables={"positions": [{"date": "2026-07-29T00:00:00+00:00", "ticker": "UUP"}]}
        )
        assert _prior_book_date(sb, "2026-07-31") == "2026-07-29"

    def test_unparseable_date_returns_none_without_querying(self) -> None:
        """Graceful degradation is preserved: the old calendar helper returned None
        for junk input, so the DB must not be handed an invalid ``date`` filter."""

        class _Exploding:
            def table(self, _name: str) -> Any:
                raise AssertionError("must not query PostgREST with an unparseable date")

        assert _prior_book_date(_Exploding(), "not-a-date") is None
        assert _prior_book_date(_Exploding(), "") is None


class TestBookWeights:
    def test_excludes_cash_and_uppercases_tickers(self) -> None:
        sb = _FakeClient(
            tables={
                "positions": [
                    {"date": "2026-07-29", "ticker": "cash", "weight_pct": "28.0"},
                    {"date": "2026-07-29", "ticker": "uup", "weight_pct": "39.9226"},
                ]
            }
        )
        assert _book_weights(sb, "2026-07-29") == {"UUP": pytest.approx(39.9226)}

    def test_absent_book_date_is_empty(self) -> None:
        assert _book_weights(_gap_day_client(), None) == {}


# ─── build_events_from_positions_book (the tier-3 path every prod row uses) ──


class TestBuildEventsFromPositionsBook:
    def test_exit_fires_for_names_dropped_across_a_gap_day(self) -> None:
        """The headline regression: DBO and XLI left the book on 07-31 and no EXIT
        was ever recorded, because the 07-30 comparison book is empty."""
        events = build_events_from_positions_book(_gap_day_client(), "2026-07-31")
        assert events is not None
        exits = sorted(e["ticker"] for e in events if e["event"] == "EXIT")
        assert exits == ["DBO", "XLI"]

    def test_survivors_are_not_spurious_opens(self) -> None:
        """UUP has been held since 06-23; it must never be written as an OPEN with
        a null prior weight."""
        events = build_events_from_positions_book(_gap_day_client(), "2026-07-31")
        assert events is not None
        by_ticker = _events_by_ticker(events)
        assert by_ticker["UUP"]["event"] == "TRIM"
        assert by_ticker["UUP"]["prev_weight_pct"] == pytest.approx(39.9226)
        opens = sorted(e["ticker"] for e in events if e["event"] == "OPEN")
        assert opens == ["FXI", "IBIT", "VGK"]
        assert all(by_ticker[t]["prev_weight_pct"] is None for t in opens)

    def test_full_classification_against_the_prior_book(self) -> None:
        events = build_events_from_positions_book(_gap_day_client(), "2026-07-31")
        assert events is not None
        assert {t: e["event"] for t, e in _events_by_ticker(events).items()} == {
            "DBO": "EXIT",
            "FXI": "OPEN",
            "IBIT": "OPEN",
            "IJR": "ADD",
            "UUP": "TRIM",
            "VGK": "OPEN",
            "XLE": "ADD",
            "XLF": "ADD",
            "XLI": "EXIT",
            "XLV": "ADD",
        }

    def test_reason_records_the_comparison_book(self) -> None:
        events = build_events_from_positions_book(_gap_day_client(), "2026-07-31")
        assert events is not None
        assert all("prior committed book 2026-07-29" in e["reason"] for e in events)

    def test_first_book_ever_emits_opens_instead_of_nothing(self) -> None:
        """With no earlier book the old code aborted on ``if not prior_d`` only for
        unparseable dates; under book-derivation ``None`` is a legitimate state and
        every held name is a genuine OPEN."""
        sb = _FakeClient(tables={"positions": list(_BOOK_0729)})
        events = build_events_from_positions_book(sb, "2026-07-29")
        assert events is not None
        assert {e["event"] for e in events} == {"OPEN"}
        assert all(e["prev_weight_pct"] is None for e in events)
        assert all("no prior committed book" in e["reason"] for e in events)

    def test_no_book_on_execution_date_returns_none(self) -> None:
        assert build_events_from_positions_book(_gap_day_client(), "2026-08-03") is None


# ─── build_events_from_digest_snapshot (tier 2, same prior-book seam) ────────


class TestBuildEventsFromDigestSnapshot:
    def test_exit_fires_across_a_gap_day(self) -> None:
        sb = _FakeClient(
            tables={
                "positions": list(_BOOK_0729),
                "daily_snapshots": [
                    {
                        "date": "2026-07-31",
                        "snapshot": {
                            "portfolio": {
                                "proposed_positions": [
                                    {"ticker": "CASH", "weight_pct": 9.9741},
                                    {"ticker": "UUP", "weight_pct": 25.0},
                                    {"ticker": "FXI", "weight_pct": 10.0},
                                ]
                            }
                        },
                    }
                ],
            }
        )
        events = build_events_from_digest_snapshot(sb, "2026-07-31")
        assert events is not None
        by_ticker = _events_by_ticker(events)
        assert sorted(t for t, e in by_ticker.items() if e["event"] == "EXIT") == [
            "DBO",
            "IJR",
            "XLE",
            "XLF",
            "XLI",
            "XLV",
        ]
        assert by_ticker["UUP"]["event"] == "TRIM"
        assert by_ticker["UUP"]["prev_weight_pct"] == pytest.approx(39.9226)
        assert by_ticker["FXI"]["event"] == "OPEN"


# ─── HOLD rows (the third positions call site) ───────────────────────────────


class TestHoldEventsPriorWeight:
    def test_hold_prev_weight_comes_from_the_prior_book(self) -> None:
        """Latent half of the same defect: HOLD rows carried a null prior weight on
        every gap day."""
        sb = _gap_day_client()
        holds = _hold_events_for_positions_not_in_rebalance(sb, "2026-07-31", set())
        by_ticker = _events_by_ticker(holds)
        assert {e["event"] for e in holds} == {"HOLD"}
        assert "CASH" not in by_ticker
        assert by_ticker["UUP"]["prev_weight_pct"] == pytest.approx(39.9226)
        assert by_ticker["FXI"]["prev_weight_pct"] is None  # genuinely new


# ─── The document-date walk must keep its calendar semantics ─────────────────


class TestPriorTradingDateStillWalksWeekdays:
    """`_prior_trading_date` is *also* how the PM artifact is resolved
    (`resolve_rebalance_payload_fallback`, ``--prior-trading-day-rebalance``, and
    ``backfill_position_event_reasons._resolve_rebalance_doc_date``). Repointing or
    renaming it would break rebalance-document resolution, so it stays a calendar
    walk and only the positions comparisons moved off it."""

    def test_monday_resolves_to_friday(self) -> None:
        assert _prior_trading_date("2026-07-27") == "2026-07-24"

    def test_weekday_resolves_to_previous_calendar_day(self) -> None:
        assert _prior_trading_date("2026-07-31") == "2026-07-30"

    def test_unparseable_returns_none(self) -> None:
        assert _prior_trading_date("nope") is None

    def test_rebalance_document_lookup_still_walks_back_to_friday(self) -> None:
        payload = {
            "doc_type": "rebalance_decision",
            "body": {"rebalance_table": [{"ticker": "UUP", "action": "HOLD"}]},
        }
        sb = _FakeClient(
            tables={
                "documents": [
                    {
                        "date": "2026-07-24",
                        "document_key": "rebalance-decision.json",
                        "payload": payload,
                    }
                ]
            }
        )
        found_date, found = resolve_rebalance_payload_fallback(sb, "2026-07-27")
        assert found_date == "2026-07-24"
        assert found == payload
