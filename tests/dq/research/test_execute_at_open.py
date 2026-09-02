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
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
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
_event_tickers_for_date = _mod._event_tickers_for_date
resolve_rebalance_payload_fallback = _mod.resolve_rebalance_payload_fallback


# ─── Fake PostgREST client ──────────────────────────────────────────────────
#
# Purpose-built rather than reusing ``tests.dq.research.test_supabase_io``'s
# ``FakeSupabaseClient``: that fake's ``execute()`` silently drops filter ops it
# does not recognise, and it does not implement ``neq``. ``_prior_book_date``
# issues ``.neq("ticker", "CASH")``, so under the shared fake that filter would be
# ignored — the tests below would still pass against the unfixed source and prove
# nothing. Only the operations execute_at_open.py actually issues are modelled.


@dataclass
class _FakeQuery:
    rows: list[dict[str, Any]]
    upserts: list[dict[str, Any]]
    name: str = ""
    inserts: list[dict[str, Any]] = field(default_factory=list)
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

    def in_(self, col: str, vals: list[Any]) -> "_FakeQuery":
        self._filters.append(("in", col, list(vals)))
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

    def insert(self, rows: list[dict[str, Any]]) -> "_FakeQuery":
        """Append-only writes, stamped with their table and *not* with ``_on_conflict``.

        Kept distinguishable from ``upsert`` on purpose: the migration-069 tables reject
        UPDATE by trigger, so an ``upsert`` reaching one of them is a production failure
        rather than a nuance, and a fake that flattened the two verbs together could not
        show which one the code under test used. Rows are also appended onto the live
        table list so a later select in the same client sees the write (#2589 seed).
        """
        for row in rows:
            self.inserts.append({**row, "_table": self.name})
            self.rows.append(dict(row))
        return self

    def execute(self) -> Any:
        rows = list(self.rows)
        house = str(house_workspace_id())
        for op, col, val in self._filters:
            if op == "eq":
                rows = [
                    r
                    for r in rows
                    if r.get(col) == val
                    or (col == "workspace_id" and val == house and r.get(col) is None)
                ]
            elif op == "neq":
                rows = [r for r in rows if r.get(col) != val]
            elif op == "lt":
                rows = [r for r in rows if str(r.get(col, "")) < str(val)]
            elif op == "in":
                rows = [r for r in rows if r.get(col) in val]
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
    inserts: list[dict[str, Any]] = field(default_factory=list)

    def table(self, name: str) -> _FakeQuery:
        self.tables.setdefault(name, [])
        return _FakeQuery(
            rows=self.tables[name],
            upserts=self.upserts,
            name=name,
            inserts=self.inserts,
        )


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


class TestHouseScopedBookReads:
    """P6: overlay rows on the same calendar date must not shape the house ledger."""

    _OVERLAY = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    def test_event_tickers_ignore_overlay_rows(self) -> None:
        sb = _FakeClient(
            tables={
                "position_events": [
                    {"date": "2026-07-31", "ticker": "UUP", "event": "HOLD"},
                    {
                        "date": "2026-07-31",
                        "ticker": "EVIL",
                        "event": "OPEN",
                        "workspace_id": self._OVERLAY,
                    },
                ]
            }
        )
        tickers = _event_tickers_for_date(sb, "2026-07-31")
        assert "UUP" in tickers
        assert "EVIL" not in tickers

    def test_hold_events_ignore_overlay_positions(self) -> None:
        sb = _FakeClient(
            tables={
                "positions": [
                    *_BOOK_0731,
                    {
                        "date": "2026-07-31",
                        "ticker": "EVIL",
                        "weight_pct": "50.0",
                        "workspace_id": self._OVERLAY,
                    },
                ]
            }
        )
        holds = _hold_events_for_positions_not_in_rebalance(sb, "2026-07-31", set())
        assert "EVIL" not in {e["ticker"] for e in holds}

    def test_prior_book_date_ignores_overlay_only_gap_filler(self) -> None:
        sb = _FakeClient(
            tables={
                "positions": [
                    *_BOOK_0729,
                    {
                        "date": "2026-07-30",
                        "ticker": "EVIL",
                        "weight_pct": "100.0",
                        "workspace_id": self._OVERLAY,
                    },
                    *_BOOK_0731,
                ]
            }
        )
        assert _prior_book_date(sb, "2026-07-31") == "2026-07-29"


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


# ─── The authoritative path: migration-069 fills (#2420, Task 2.4) ──────────
#
# Everything above reconstructs the day's events from prose. These exercise the path
# that reads what the portfolio actually did — one row per fill, written by the process
# that filled it — and the two ways it can decline, which the caller must not conflate.


def _ledger_tables() -> dict[str, str]:
    """The migration-069 table names, imported the way the script imports them.

    Not hard-coded literals: this is the only test asserting the projection reads the real
    ledger tables, so a rename must break it rather than drift past it. The import lives
    in a function because ``digiquant/scripts`` is not a package — ``_ensure_importable``
    is what puts the writers on ``sys.path``, so calling it here also covers that.
    """
    _mod._ensure_importable()
    from digiquant.portfolio.writers import execution_io, ledger_io

    return {
        "commits": ledger_io.COMMITS,
        "decisions": ledger_io.DECISION_INTENTS,
        "requested": ledger_io.REQUESTED_TARGETS,
        "approved": ledger_io.APPROVED_TARGETS,
        "orders": ledger_io.ORDER_INTENTS,
        "executions": ledger_io.PAPER_EXECUTIONS,
        "lots": execution_io.HOLDING_LOTS,
    }


_TABLES = _ledger_tables()

# The decision runs on Thursday 07-30 and fills at Friday 07-31's opens — the production
# shape (`--prior-trading-day-rebalance`), and the reason run_date and executed_date are
# separate parameters all the way down. 07-30 has no `positions` rows, so the prior *book*
# is still 07-29: the ledger names the event, the book only supplies a display delta.
_RUN_D = "2026-07-30"
_EXEC_D = "2026-07-31"
_NOW = datetime(2026, 7, 31, 13, 31, tzinfo=timezone.utc)


def _lid(tag: str) -> str:
    """A stable, readable uuid for fixture rows (the writer computes its own by uuid5)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"digithings/test/2420/{tag}"))


@dataclass
class _Ledger:
    """A migration-069 chain for one run_date, assembled symbol by symbol."""

    decisions: list[dict[str, Any]] = field(default_factory=list)
    requested: list[dict[str, Any]] = field(default_factory=list)
    approved: list[dict[str, Any]] = field(default_factory=list)
    orders: list[dict[str, Any]] = field(default_factory=list)
    lots: list[dict[str, Any]] = field(default_factory=list)
    prices: list[dict[str, Any]] = field(default_factory=list)

    def order(
        self,
        symbol: str,
        action: str,
        quantity: str,
        *,
        weight: str | None = None,
        mark: str | None = None,
    ) -> "_Ledger":
        """A pending order head plus the approved→requested→decision chain above it.

        ``action`` is H7's vocabulary (`add`/`trim`/`exit`), which is deliberately *not*
        the event name: the executor derives direction from it, and the projection derives
        the event from the resulting position. ``mark`` absent means no `price_history.open`
        row, which is how a `data_unavailable` rejection is set up. ``weight`` absent means
        the approved target was expressed as a quantity, so no percent is knowable.
        """
        ids = {p: _lid(f"{p}:{symbol}") for p in ("decision", "requested", "approved", "order")}
        self.decisions.append(
            {"id": ids["decision"], "run_date": _RUN_D, "symbol": symbol, "action": action}
        )
        self.requested.append(
            {
                "id": ids["requested"],
                "decision_intent_id": ids["decision"],
                "run_date": _RUN_D,
                "symbol": symbol,
            }
        )
        self.approved.append(
            {
                "id": ids["approved"],
                "requested_target_id": ids["requested"],
                "run_date": _RUN_D,
                "symbol": symbol,
                "approved_weight": weight,
                "supersedes_id": None,
            }
        )
        self.orders.append(
            {
                "id": ids["order"],
                "approved_target_id": ids["approved"],
                "run_date": _RUN_D,
                "symbol": symbol,
                "quantity": quantity,
                "status": "pending",
                "supersedes_id": None,
            }
        )
        if mark is not None:
            self.prices.append({"ticker": symbol, "date": _EXEC_D, "open": mark})
        return self

    def holding(self, symbol: str, quantity: str, *, open_price: str = "10.0") -> "_Ledger":
        """A lot already on the book before this run — the symbol's prior position."""
        opened_by = _lid(f"prior-exec:{symbol}")
        self.lots.append(
            {
                "id": _lid(f"prior-lot:{symbol}"),
                "opened_by_execution_id": opened_by,
                "closed_by_execution_id": None,
                "run_date": "2026-06-23",
                "symbol": symbol,
                "quantity": quantity,
                "open_price": open_price,
                "status": "open",
                "opened_at": "2026-06-23T13:31:00+00:00",
                "closed_at": None,
            }
        )
        return self

    def client(
        self,
        *,
        with_commit: bool = True,
        books: list[dict[str, Any]] | None = None,
    ) -> _FakeClient:
        position_rows = list(books if books is not None else [*_BOOK_0729, *_BOOK_0731])
        # Opening-snapshot seed (#2589) needs NAV + marks when lots are empty but the prior
        # book is not. Provide them so cold-start auto-ensure succeeds in fixtures that
        # intentionally start with no lots (quiet day, all-rejected, chained fills).
        seed_closes = [
            {"ticker": str(row["ticker"]), "date": "2026-07-29", "close": "100"}
            for row in _BOOK_0729
            if str(row.get("ticker") or "").upper() not in ("", "CASH")
        ]
        return _FakeClient(
            tables={
                "positions": position_rows,
                "nav_history": [{"date": "2026-07-29", "nav": "1000000"}],
                "price_history": list(self.prices) + seed_closes,
                _TABLES["commits"]: (
                    [{"id": _lid("commit"), "run_date": _RUN_D}] if with_commit else []
                ),
                _TABLES["decisions"]: list(self.decisions),
                _TABLES["requested"]: list(self.requested),
                _TABLES["approved"]: list(self.approved),
                _TABLES["orders"]: list(self.orders),
                _TABLES["executions"]: [],
                _TABLES["lots"]: list(self.lots),
            }
        )


def _day() -> _Ledger:
    """The canonical fixture day: one of every event name the projection can produce.

    FXI opens into nothing; UUP adds to a held lot; XLF trims part of one; DBO's `exit`
    consumes all of it. IBIT has a pending order but no declared open, so it is rejected
    rather than filled at a guess. DBO's approved target carries no weight — an exit
    expressed as a quantity — so its percent is unknown rather than zero.
    """
    return (
        _Ledger()
        .order("FXI", "add", "40", weight="0.07", mark="25.00")
        .order("UUP", "add", "20", weight="0.25", mark="27.40")
        .order("XLF", "trim", "10", weight="0.15", mark="52.10")
        .order("DBO", "exit", "30", mark="18.75")
        .order("IBIT", "add", "12", weight="0.05")
        .holding("UUP", "100", open_price="26.00")
        .holding("XLF", "50", open_price="48.00")
        .holding("DBO", "30", open_price="19.20")
    )


@pytest.fixture(autouse=True)
def _ledger_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the kill switch to its default-on state for every test in this module.

    ``ledger_enabled`` reads the process environment and defaults to **on**, so a
    developer with ``DIGIQUANT_PORTFOLIO_LEDGER=0`` (or alias
    ``OLYMPUS_PORTFOLIO_LEDGER=0``) exported would otherwise see the whole
    authoritative path silently skipped and the suite still pass.
    """
    monkeypatch.delenv("OLYMPUS_PORTFOLIO_LEDGER", raising=False)
    monkeypatch.delenv("DIGIQUANT_PORTFOLIO_LEDGER", raising=False)


class TestOpenMarksAreDecimal:
    """The at-open mark becomes a fill price and then a lot's cost basis.

    Every other read in this script feeds `position_events`, which is a display table, and
    is allowed to hand back floats. This one feeds the immutable record of what was bought,
    and the ledger's whole numeric contract is that money never passes through binary
    floating point — so the type is asserted here, not assumed from the annotation.
    """

    @staticmethod
    def _client(rows: list[dict[str, Any]]) -> _FakeClient:
        return _FakeClient(tables={"price_history": rows})

    def test_marks_arrive_as_decimal_not_float(self) -> None:
        marks = self._client([{"ticker": "UUP", "date": _EXEC_D, "open": "27.40"}])
        got = _mod._open_marks(marks, ["UUP"], _EXEC_D)
        assert got == {"UUP": Decimal("27.40")}
        # `Decimal("27.40") == 27.40` is False — Python compares the exact values, and the
        # float is 27.39999999999999857891452847979962825775146484375. So the equality above
        # already fails under a `float(raw)` mutation; this pins the type outright anyway,
        # because a float reaching the executor is a contract break even where it round-trips.
        assert type(got["UUP"]) is Decimal

    def test_a_mark_that_arrives_as_a_json_number_is_not_widened(self) -> None:
        """`Decimal(str(raw))`, never `Decimal(raw)`.

        A `numeric` column comes back as a JSON number when the client parses it that way,
        and `Decimal(1.1)` is 1.10000000000000008881784197001...: the binary expansion of
        the float, not the price anybody declared. Stringifying first keeps the decimal the
        table actually stores, whichever type the driver hands over.
        """
        got = _mod._open_marks(
            self._client([{"ticker": "FXI", "date": _EXEC_D, "open": 1.1}]), ["FXI"], _EXEC_D
        )
        assert got == {"FXI": Decimal("1.1")}

    def test_an_unusable_open_leaves_the_symbol_absent(self) -> None:
        """Absent is the interface: `execute_pending_orders` rejects those orders.

        A missing row, a null open, a non-positive open and an unparseable one are all the
        same answer — no declared price — and the executor turns that into a
        `data_unavailable` rejection on the ledger. Substituting any number here would fill
        the order at a guess, which is the class of invention the ledger exists to stop.
        """
        got = _mod._open_marks(
            self._client(
                [
                    {"ticker": "UUP", "date": _EXEC_D, "open": "27.40"},
                    {"ticker": "IBIT", "date": _EXEC_D, "open": None},
                    {"ticker": "XLF", "date": _RUN_D, "open": "52.10"},  # yesterday's open
                    {"ticker": "DBO", "date": _EXEC_D, "open": "0"},  # not a tradeable price
                    {"ticker": "XLE", "date": _EXEC_D, "open": "n/a"},  # unparseable
                    {"ticker": "GLD", "date": _EXEC_D, "open": "NaN"},  # storable in `numeric`
                    {"ticker": "SLV", "date": _EXEC_D, "open": "Infinity"},
                ]
            ),
            ["UUP", "IBIT", "XLF", "DBO", "XLE", "GLD", "SLV", "VGK"],
            _EXEC_D,
        )
        assert got == {"UUP": Decimal("27.40")}

    @pytest.mark.parametrize("raw", ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity", float("inf")])
    def test_a_non_finite_open_is_absent_rather_than_an_exception(self, raw: Any) -> None:
        """A poisoned price row skips its symbol; it does not take the morning down.

        `price_history.open` is a bare `numeric` with no CHECK, and Postgres `numeric` holds
        `NaN` and `Infinity`. Both survive `Decimal(str(raw))`, and each then fails in its
        own way: `Decimal("NaN") > 0` raises `InvalidOperation`, while `Decimal("Infinity")`
        clears a `> 0` gate and only dies further downstream in `PaperExecution`, whose
        `PositivePrice` sets `allow_inf_nan=False`. `_open_marks` is called as an argument to
        `execute_pending_orders`, which is deliberately *outside* the decline contract, so
        either failure is an uncaught traceback out of the job that books the day's fills —
        one bad row for one symbol, every order left pending.

        Asserting the good mark alongside is what makes this a skip rather than a bail: a
        guard that returned early on the first non-finite row would also raise nothing.
        """
        got = _mod._open_marks(
            self._client(
                [
                    {"ticker": "GLD", "date": _EXEC_D, "open": raw},
                    {"ticker": "UUP", "date": _EXEC_D, "open": "27.40"},
                ]
            ),
            ["GLD", "UUP"],
            _EXEC_D,
        )
        assert got == {"UUP": Decimal("27.40")}

    def test_the_marks_are_one_batched_read(self) -> None:
        """One `in_` over the day's pending symbols — the shape #2484 exists to stop.

        The legacy `_fetch_open` loop issues a round trip per ticker. The symbol list here
        is bounded by the day's pending orders, so it fits in one read, and the count is
        asserted rather than the filter because a per-ticker loop would still produce the
        right marks and pass every value assertion above.
        """
        reads: list[str] = []

        class _Counting(_FakeClient):
            def table(self, name: str) -> _FakeQuery:
                reads.append(name)
                return super().table(name)

        client = _Counting(
            tables={
                "price_history": [
                    {"ticker": t, "date": _EXEC_D, "open": "10.00"} for t in ("FXI", "UUP", "XLF")
                ]
            }
        )
        assert len(_mod._open_marks(client, ["FXI", "UUP", "XLF"], _EXEC_D)) == 3
        assert reads == ["price_history"]

    def test_no_pending_symbols_means_no_read_at_all(self) -> None:
        """A quiet day must not turn into an unfiltered scan of `price_history`."""

        class _NoRead(_FakeClient):
            def table(self, name: str) -> _FakeQuery:
                raise AssertionError(f"read {name} for an empty ticker list")

        assert _mod._open_marks(_NoRead(), [], _EXEC_D) == {}


class TestBuildEventsFromPaperFills:
    def test_event_names_come_from_the_position_not_the_label(self) -> None:
        events, declined = _mod.build_events_from_paper_fills(
            _day().client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert declined == ""
        assert events is not None
        by_ticker = _events_by_ticker(events)
        assert {t: e["event"] for t, e in by_ticker.items()} == {
            "FXI": "OPEN",  # buy into nothing
            "UUP": "ADD",  # buy on top of 100 shares
            "XLF": "TRIM",  # sell 10 of 50
            "DBO": "EXIT",  # sell all 30
        }

    def test_ledger_projection_stamps_authoritative_book_source(self) -> None:
        """#2422: ledger fills must never land unlabeled or as legacy."""
        events, declined = _mod.build_events_from_paper_fills(
            _day().client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert declined == ""
        assert events is not None
        assert events
        assert all(e.get("book_source") == _mod.BOOK_SOURCE_AUTHORITATIVE for e in events)

    def test_a_rejected_order_produces_no_event(self) -> None:
        """No declared open means no fill, and no fill means no invented event row.

        The legacy paths would have written IBIT from the rebalance table's weight at
        whatever price they could find. The ledger records the rejection instead, and the
        projection stays silent about a trade that did not happen.
        """
        events, _ = _mod.build_events_from_paper_fills(_day().client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        assert "IBIT" not in _events_by_ticker(events)

    def test_weight_pct_is_the_approved_weight_in_percent(self) -> None:
        events, _ = _mod.build_events_from_paper_fills(_day().client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        by_ticker = _events_by_ticker(events)
        # The ×100 happens in Decimal. Scaled as a float instead, 0.07 lands on
        # 7.000000000000001 — so this equality is what holds the conversion order in
        # place; 0.25 and 0.15 below would pass either way.
        assert by_ticker["FXI"]["weight_pct"] == 7.0
        assert by_ticker["UUP"]["weight_pct"] == 25.0
        assert by_ticker["XLF"]["weight_pct"] == 15.0
        # DBO's approved target carried no weight: unknown, not zero.
        assert by_ticker["DBO"]["weight_pct"] is None

    def test_price_is_the_fill_price(self) -> None:
        events, _ = _mod.build_events_from_paper_fills(_day().client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        assert _events_by_ticker(events)["UUP"]["price"] == 27.40

    def test_prev_weight_comes_from_the_prior_book_not_the_prior_weekday(self) -> None:
        """07-30 is the decision date and has no book; the delta is against 07-29.

        This is #1743's actual mechanism, and it survives the rewrite: the ledger names
        the event, but `prev_weight_pct` is display-only and still read from `positions`,
        so it still has to skip gap days.
        """
        events, _ = _mod.build_events_from_paper_fills(_day().client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        by_ticker = _events_by_ticker(events)
        assert by_ticker["UUP"]["prev_weight_pct"] == pytest.approx(39.9226)
        assert by_ticker["DBO"]["prev_weight_pct"] == pytest.approx(1.7891)
        assert by_ticker["FXI"]["prev_weight_pct"] is None  # not on the 07-29 book
        assert "07-29" in by_ticker["UUP"]["reason"]
        assert "display only" in by_ticker["UUP"]["reason"]

    def test_dust_fill_with_unchanged_display_weight_is_hold(self) -> None:
        """House 2026-09-01 FXI/VGK/XLF: ~0.05–0.14 share true-ups at the same 5/25/20%.

        Activity names the event from the fill, so a lot-level true-up became ADD/TRIM
        of +0.0pp. OPEN/EXIT still come from residual quantity (#1743); only ADD/TRIM
        whose displayed weight did not move at 1-decimal pp collapse to HOLD.
        """
        ledger = (
            _Ledger()
            .order("IJR", "add", "0.14", weight="0.05", mark="35.36")
            .holding("IJR", "100", open_price="35.00")
        )
        events, declined = _mod.build_events_from_paper_fills(
            ledger.client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert declined == ""
        assert events is not None
        ijr = _events_by_ticker(events)["IJR"]
        assert ijr["event"] == "HOLD"
        assert ijr["weight_pct"] == pytest.approx(5.0)
        assert ijr["prev_weight_pct"] == pytest.approx(5.0)

    def test_a_trim_that_closes_the_position_is_an_exit(self) -> None:
        """The #1743 class of mislabelling, from the other direction.

        H7 said `trim`; the sell consumed every share on the record. Naming the event from
        the action would write TRIM and leave a phantom position in Activity forever —
        which is how the table accumulated 31 OPENs and zero EXITs.
        """
        ledger = (
            _Ledger().order("XLE", "trim", "25", weight="0.0", mark="88.00").holding("XLE", "25")
        )
        events, _ = _mod.build_events_from_paper_fills(ledger.client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        assert _events_by_ticker(events)["XLE"]["event"] == "EXIT"

    def test_a_sell_larger_than_the_recorded_lots_is_an_exit(self) -> None:
        """Residual is *measured* from the lots, so an over-sell reports zero.

        `prior - quantity` would be −20 here, which is still ``<= 0`` and so would happen
        to give EXIT — but it would also make a two-share over-sell of a one-share lot
        arithmetically negative while the position is simply flat. Measuring keeps the
        residual honest, and the executor logs the surplus separately.
        """
        ledger = _Ledger().order("XLI", "exit", "60", mark="41.00").holding("XLI", "40")
        events, _ = _mod.build_events_from_paper_fills(ledger.client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        assert _events_by_ticker(events)["XLI"]["event"] == "EXIT"

    def test_two_orders_on_one_symbol_chain_through_the_same_lots(self) -> None:
        """The second order's prior position is the first one's residual, not the book's.

        VGK starts flat, is opened, and is closed again in the same run. The EXIT is only
        reachable because the sell can see the lot the buy just created: both fills read
        the running lineage state the executor mutates as it goes, so neither sees the
        pre-run book. Naming the second event from `prior - quantity` against the book
        would give 0 - 30 and call a closed position a short.
        """
        ledger = _Ledger().order("VGK", "add", "30", weight="0.15", mark="60.00")
        # A second, independent chain leg for the same symbol on the same run_date.
        ledger.decisions.append(
            {"id": _lid("d2:VGK"), "run_date": _RUN_D, "symbol": "VGK", "action": "trim"}
        )
        ledger.requested.append(
            {
                "id": _lid("r2:VGK"),
                "decision_intent_id": _lid("d2:VGK"),
                "run_date": _RUN_D,
                "symbol": "VGK",
            }
        )
        ledger.approved.append(
            {
                "id": _lid("a2:VGK"),
                "requested_target_id": _lid("r2:VGK"),
                "run_date": _RUN_D,
                "symbol": "VGK",
                "approved_weight": "0.15",
                "supersedes_id": None,
            }
        )
        ledger.orders.append(
            {
                "id": _lid("o2:VGK"),
                "approved_target_id": _lid("a2:VGK"),
                "run_date": _RUN_D,
                "symbol": "VGK",
                "quantity": "30",
                "status": "pending",
                "supersedes_id": None,
            }
        )
        events, _ = _mod.build_events_from_paper_fills(ledger.client(), _RUN_D, _EXEC_D, now=_NOW)
        assert events is not None
        # One row per fill, and `position_events` is unique on (date, ticker) — so the
        # writer's last upsert wins. The sell consumed everything the buy opened, so the
        # surviving row must be the EXIT and not a TRIM against a stale prior.
        assert [e["event"] for e in events if e["ticker"] == "VGK"] == ["OPEN", "EXIT"]

    def test_the_fills_land_as_inserts_on_the_ledger_tables(self) -> None:
        """The projection is a read; the booking underneath it is append-only.

        Asserted here rather than trusted because the fake keeps ``insert`` and ``upsert``
        distinguishable: 069's tables reject UPDATE by trigger, so an upsert reaching one
        of them fails in production and passes every mock that flattens the two.
        """
        sb = _day().client()
        _mod.build_events_from_paper_fills(sb, _RUN_D, _EXEC_D, now=_NOW)
        tables = {row["_table"] for row in sb.inserts}
        assert tables == {_TABLES["executions"], _TABLES["lots"], _TABLES["orders"]}
        assert not sb.upserts  # nothing is upserted until the caller records the events
        assert all("_on_conflict" not in row for row in sb.inserts)


class TestBuildEventsFromPaperFillsDeclines:
    """``(None, reason)`` — the ledger has no opinion, so a prose fallback is legitimate."""

    def test_declines_when_no_commit_row_exists_for_the_run_date(self) -> None:
        events, declined = _mod.build_events_from_paper_fills(
            _day().client(with_commit=False), _RUN_D, _EXEC_D, now=_NOW
        )
        assert events is None
        assert "portfolio_ledger_commits" in declined and _RUN_D in declined

    def test_declines_when_the_kill_switch_is_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLYMPUS_PORTFOLIO_LEDGER", "0")
        events, declined = _mod.build_events_from_paper_fills(
            _day().client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert events is None
        assert "DIGIQUANT_PORTFOLIO_LEDGER" in declined

    def test_declines_when_a_ledger_read_raises(self) -> None:
        """Production's migration tail is 065, so the tables are not there yet.

        `pipeline-digiquant-prices.yml` runs this script daily against `main`, and
        `ledger_enabled` defaults on — so an unguarded probe would crash the live at-open
        job every morning until the migration is approved. It degrades instead.
        """

        class _Exploding(_FakeClient):
            def table(self, name: str) -> _FakeQuery:
                if name.startswith("portfolio_ledger_"):
                    raise RuntimeError('relation "portfolio_ledger_commits" does not exist')
                return super().table(name)

        events, declined = _mod.build_events_from_paper_fills(
            _Exploding(tables={"positions": [*_BOOK_0729, *_BOOK_0731]}),
            _RUN_D,
            _EXEC_D,
            now=_NOW,
        )
        assert events is None
        assert "does not exist" in declined

    def test_a_quiet_authoritative_day_is_an_empty_list_not_a_decline(self) -> None:
        """``([], "")`` — the ledger spoke and nothing traded. Not the same answer.

        This is the state `ledger_is_authoritative` exists to separate: a commit row with
        no pending orders is a genuine no-op day, and reconstructing events from prose
        would invent activity the authority says did not happen.
        """
        events, declined = _mod.build_events_from_paper_fills(
            _Ledger().client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert events == []
        assert declined == ""

    def test_declines_when_a_date_argument_is_not_a_calendar_date(self) -> None:
        """`main` rejects this at exit 2, so reaching here means a programmatic caller.

        The parse lives inside the decline contract rather than at its first use: this
        function promises `(None, reason)` on every way the ledger can fail to speak, and
        an unguarded `date.fromisoformat` would instead raise out of a function documented
        never to — taking the prose fallback down with it.
        """
        events, declined = _mod.build_events_from_paper_fills(
            _day().client(), "2026-07-30T09:35:00", _EXEC_D, now=_NOW
        )
        assert events is None
        assert "ISO-8601" in declined

    def test_declines_when_opening_snapshot_seed_fails(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cold start with a held book must not reach execute if seeding cannot complete."""

        def _fail(_client: Any, _book_date: Any, now: Any = None) -> tuple[bool, str]:
            del _client, _book_date, now
            return False, "nav_history.nav missing or non-positive for 2026-07-29"

        monkeypatch.setattr(
            "digiquant.portfolio.writers.opening_snapshot.ensure_legacy_opening_snapshot",
            _fail,
        )
        # Pending trim, no lots — cold-start without a successful seed.
        ledger = _Ledger().order("XLF", "trim", "10", weight="0.15", mark="52.10")
        events, declined = _mod.build_events_from_paper_fills(
            ledger.client(), _RUN_D, _EXEC_D, now=_NOW
        )
        assert events is None
        assert "nav_history" in declined


class TestBuildEventsOpeningSnapshotSeed:
    """#2589: auto-seed lots so a first trim is not mislabeled EXIT."""

    def test_seeded_prior_quantity_keeps_a_partial_trim_as_trim(self) -> None:
        # No prior lots on the ledger, but the positions book holds XLF. Seed must open
        # lots before execute measures residuals — otherwise prior=0 and TRIM→EXIT.
        ledger = _Ledger().order("XLF", "trim", "10", weight="0.15", mark="52.10")
        client = ledger.client(
            books=[
                {
                    "date": "2026-07-29",
                    "ticker": "XLF",
                    "weight_pct": "10",
                    "entry_price": "50",
                },
                {"date": "2026-07-29", "ticker": "CASH", "weight_pct": "90"},
            ]
        )
        client.tables["nav_history"] = [{"date": "2026-07-29", "nav": "100000"}]
        # price_history close fallback if entry_price were missing; entry_price is set.
        client.tables.setdefault("price_history", []).append(
            {"ticker": "XLF", "date": "2026-07-29", "close": "50"}
        )

        events, declined = _mod.build_events_from_paper_fills(client, _RUN_D, _EXEC_D, now=_NOW)
        assert declined == ""
        assert events is not None
        by_ticker = _events_by_ticker(events)
        assert by_ticker["XLF"]["event"] == "TRIM"


class TestAnAllRejectedDayIsNotAQuietDay:
    """The ledger was authoritative, had orders, and refused every one of them.

    Without this line the run ends on `_record_ledger_events`' "booked no fills" summary,
    which reads exactly like a day with nothing to trade. Only one of the two is worth
    paging on: every order the PM approved was unfillable, which in practice means the
    price feed had no open for any of them that morning.
    """

    def test_the_run_says_so_when_every_order_was_rejected(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Two pending orders, neither with a declared open: both `data_unavailable`.
        ledger = (
            _Ledger()
            .order("FXI", "add", "40", weight="0.07")
            .order("UUP", "add", "20", weight="0.25")
        )
        events, declined = _mod.build_events_from_paper_fills(
            ledger.client(), _RUN_D, _EXEC_D, now=_NOW
        )

        # Not a decline — the ledger spoke. It just filled nothing, so there is no event
        # to project and no prose reconstruction to fall back to.
        assert declined == ""
        assert events == []
        out = capsys.readouterr().out
        assert "rejected all 2 order(s)" in out
        assert "not a quiet day" in out

    def test_a_genuinely_quiet_day_stays_quiet(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The discriminating half: no orders at all must not raise the alarm.

        Asserted because an unconditional warning would satisfy the test above while
        firing on every no-op day — and an alarm that cries on quiet days is one an
        operator learns to scroll past.
        """
        _mod.build_events_from_paper_fills(_Ledger().client(), _RUN_D, _EXEC_D, now=_NOW)
        assert "not a quiet day" not in capsys.readouterr().out

    def test_a_day_that_filled_something_does_not_warn(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`_day()` rejects IBIT and fills four others: one rejection is not the headline.

        The per-rejection line still prints — that is the operator's record of *which*
        order was refused, and it is what makes the summary warning redundant here.
        """
        _mod.build_events_from_paper_fills(_day().client(), _RUN_D, _EXEC_D, now=_NOW)
        out = capsys.readouterr().out
        assert "IBIT" in out and "data_unavailable" in out
        assert "not a quiet day" not in out


class TestMainPrefersTheLedger:
    """`main()`'s wiring: authoritative first, prose only on a decline."""

    def _run(self, monkeypatch: pytest.MonkeyPatch, sb: Any, *argv: str) -> int:
        monkeypatch.setattr(_mod, "_sb", lambda: sb)
        monkeypatch.setattr(sys, "argv", ["execute_at_open.py", *argv])
        return int(_mod.main())

    def test_the_prose_builders_never_run_when_the_ledger_speaks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _forbidden(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("a prose builder ran while the ledger was authoritative")

        monkeypatch.setattr(_mod, "build_events_from_digest_snapshot", _forbidden)
        monkeypatch.setattr(_mod, "build_events_from_positions_book", _forbidden)
        monkeypatch.setattr(_mod, "_rebalance_payload_for_date", _forbidden)
        sb = _day().client()
        rc = self._run(monkeypatch, sb, "--date", _EXEC_D, "--rebalance-date", _RUN_D)
        assert rc == 0
        recorded = {row["ticker"]: row for row in sb.upserts}
        assert recorded["FXI"]["event"] == "OPEN"
        assert recorded["DBO"]["event"] == "EXIT"
        # T0 (#5-T0): migration 097 widened UNIQUE to (workspace_id, date, ticker);
        # the writer stamps house workspace_id and targets that composite key.
        assert all(row["_on_conflict"] == "workspace_id,date,ticker" for row in sb.upserts)
        assert all("workspace_id" in row for row in sb.upserts)

    def test_held_names_still_get_hold_continuity_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The book's untraded lines keep Activity continuous, as they did before.

        IBIT is among them: its order was rejected, so nothing happened to that position
        today and HOLD is the honest row. What must not appear is a fabricated fill.
        """
        sb = _day().client()
        self._run(monkeypatch, sb, "--date", _EXEC_D, "--rebalance-date", _RUN_D)
        holds = {row["ticker"] for row in sb.upserts if row["event"] == "HOLD"}
        assert holds == {"IJR", "VGK", "XLE", "XLV", "IBIT"}

    def test_require_ledger_refuses_to_fall_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Exit 3, the post-cutover lever: a silent prose fallback becomes fatal."""
        sb = _day().client(with_commit=False)
        rc = self._run(
            monkeypatch,
            sb,
            "--date",
            _EXEC_D,
            "--rebalance-date",
            _RUN_D,
            "--require-ledger",
        )
        assert rc == 3
        assert not sb.upserts

    def test_no_ledger_and_require_ledger_are_mutually_exclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exit 2, and before any client is built — the flags contradict outright."""

        def _no_client() -> None:
            raise AssertionError("main() built a Supabase client before rejecting the flags")

        monkeypatch.setattr(_mod, "_sb", _no_client)
        monkeypatch.setattr(
            sys,
            "argv",
            ["execute_at_open.py", "--date", _EXEC_D, "--no-ledger", "--require-ledger"],
        )
        assert _mod.main() == 2

    def test_no_ledger_falls_through_to_the_prose_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The escape hatch: skip the ledger without touching it at all."""

        def _forbidden(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("the ledger was read despite --no-ledger")

        monkeypatch.setattr(_mod, "build_events_from_paper_fills", _forbidden)
        monkeypatch.setattr(_mod, "_rebalance_payload_for_date", lambda *_a, **_k: None)
        monkeypatch.setattr(_mod, "build_events_from_digest_snapshot", lambda *_a, **_k: None)
        monkeypatch.setattr(_mod, "build_events_from_positions_book", lambda *_a, **_k: None)
        sb = _day().client()
        rc = self._run(
            monkeypatch, sb, "--date", _EXEC_D, "--rebalance-date", _RUN_D, "--no-ledger"
        )
        # No events from any source: the prose path's own "nothing to record" exit, which
        # is a clean 0. Pinned exactly rather than `in (0, 1)` — `main` has no `return 1`
        # at all, so the looser form would also pass if this path started raising and the
        # exception were swallowed into a generic failure code somewhere upstream.
        assert rc == 0


class TestMainRejectsMalformedDates:
    """Exit 2, and before a Supabase client exists — a bad date must not fail mid-read.

    Both dates are hand-typed into a `workflow_dispatch`, and neither had a usable gate:
    `--rebalance-date` had no check at all, and `--date`'s only check was the weekday one,
    which parses with `datetime.fromisoformat` and so accepts an ISO *datetime*. Either
    flag could therefore carry a value past the top of `main` that fails much later as a
    traceback out of a read — after the ledger had already been written to.
    """

    def _rc(self, monkeypatch: pytest.MonkeyPatch, *argv: str) -> int:
        def _no_client() -> None:
            raise AssertionError("main() built a Supabase client before rejecting the date")

        monkeypatch.setattr(_mod, "_sb", _no_client)
        monkeypatch.setattr(sys, "argv", ["execute_at_open.py", *argv])
        return int(_mod.main())

    def test_an_iso_datetime_is_not_a_calendar_date(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The exact hole the loose gate left open, named in both directions.

        `2026-07-31T09:35:00` is a Friday, so the weekday check waves it through; every
        consumer downstream parses with `date.fromisoformat`, which rejects it. A gate that
        approves a string nothing after it can use is worse than no gate, because the
        failure surfaces somewhere unrelated.
        """
        assert _mod._trading_day_only("2026-07-31T09:35:00") is True
        assert _mod._is_calendar_date("2026-07-31T09:35:00") is False
        assert self._rc(monkeypatch, "--date", "2026-07-31T09:35:00") == 2

    def test_a_value_that_is_not_a_date_at_all_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self._rc(monkeypatch, "--date", "yesterday") == 2

    def test_the_rebalance_date_is_checked_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """It had no gate whatsoever, and it is the one a human types by hand."""
        assert self._rc(monkeypatch, "--date", _EXEC_D, "--rebalance-date", "2026-07-3") == 2

    def test_the_message_names_the_flag_and_the_value(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """There are two date flags, so "bad date" alone would not tell an operator which."""
        self._rc(monkeypatch, "--date", _EXEC_D, "--rebalance-date", "07/30/2026")
        err = capsys.readouterr().err
        assert "--rebalance-date" in err
        assert "07/30/2026" in err

    def test_the_production_pair_still_gets_past_the_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-vacuous: the guard refuses malformed dates, not all dates.

        Reaching `_sb` *is* the assertion — the sentinel client raises, so a clean `2`
        here would mean the guard had started rejecting the arguments the daily job passes.
        """
        with pytest.raises(AssertionError, match="before rejecting the date"):
            self._rc(monkeypatch, "--date", _EXEC_D, "--rebalance-date", _RUN_D)
