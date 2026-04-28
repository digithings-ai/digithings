"""Unit tests for digiquant.data.prices.calendar_sync (issue #337).

The exchange_calendars library is mocked at the boundary so tests never touch
the network and never depend on the package being installed.  Mock fixtures
provide a fixed set of NYSE / NASDAQ session dates aligned with the windows
each test exercises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pytest

from digiquant.data.prices.calendar_sync import (
    ALL_VENUES,
    REASON_HOLIDAY,
    REASON_WEEKEND,
    VENUE_CRYPTO,
    VENUE_FX,
    VENUE_NASDAQ,
    VENUE_NYSE,
    build_crypto_rows,
    build_equity_rows,
    build_fx_rows,
    build_rows,
    build_rows_for_venue,
    parse_end_spec,
    upsert_trading_calendar,
)
from digiquant.data.prices.ticker_venues import (
    ALLOWED_VENUES,
    CORE_TICKER_VENUES,
    venue_for,
)


# ─── Fake exchange_calendars boundary ──────────────────────────────────────


@dataclass
class _FakeSessions:
    """Stand-in for ``pandas.DatetimeIndex`` returned by sessions_in_range.

    Only the iteration protocol used by ``calendar_sync`` is implemented:
    each yielded element exposes a ``.date()`` method that returns a native
    ``datetime.date``.  This deliberately avoids a pandas dependency in tests.
    """

    sessions: list[date]

    def __iter__(self):
        for d in self.sessions:
            yield _FakeTimestamp(d)


@dataclass
class _FakeTimestamp:
    _d: date

    def date(self) -> date:
        return self._d


@dataclass
class _FakeCalendar:
    name: str
    sessions: list[date] = field(default_factory=list)

    def sessions_in_range(self, start: str, end: str) -> _FakeSessions:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end)
        return _FakeSessions([d for d in self.sessions if s <= d <= e])


def _us_business_days(start: date, end: date, *, holidays: set[date] | None = None) -> list[date]:
    """Generate Mon–Fri dates in [start, end] minus an optional holiday set."""
    holidays = holidays or set()
    out: list[date] = []
    cur = start
    one = timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5 and cur not in holidays:
            out.append(cur)
        cur += one
    return out


# Known 2023 NYSE holidays used by ``test_nyse_calendar_excludes_known_holidays``.
NYSE_2023_HOLIDAYS: set[date] = {
    date(2023, 1, 2),  # New Year's (observed)
    date(2023, 1, 16),  # Martin Luther King Jr. Day
    date(2023, 2, 20),  # Presidents' Day
    date(2023, 4, 7),  # Good Friday
    date(2023, 5, 29),  # Memorial Day
    date(2023, 6, 19),  # Juneteenth
    date(2023, 7, 4),  # Independence Day
    date(2023, 9, 4),  # Labor Day
    date(2023, 11, 23),  # Thanksgiving
    date(2023, 12, 25),  # Christmas
}


def _nyse_2023_calendar() -> _FakeCalendar:
    sessions = _us_business_days(date(2023, 1, 1), date(2023, 12, 31), holidays=NYSE_2023_HOLIDAYS)
    return _FakeCalendar(name="XNYS", sessions=sessions)


def _make_get_calendar(calendars: dict[str, _FakeCalendar]):
    def _get(mic: str) -> _FakeCalendar:
        if mic not in calendars:
            raise KeyError(f"unmocked MIC: {mic}")
        return calendars[mic]

    return _get


# ─── parse_end_spec ────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parse_end_spec_iso_date() -> None:
    assert parse_end_spec("2030-12-31") == date(2030, 12, 31)


@pytest.mark.unit
def test_parse_end_spec_relative_years() -> None:
    today = date(2026, 1, 1)
    # +5y == 5*365 days = 1825d after today.
    assert parse_end_spec("+5y", today=today) == today + timedelta(days=5 * 365)


@pytest.mark.unit
def test_parse_end_spec_relative_days_negative() -> None:
    today = date(2026, 4, 27)
    assert parse_end_spec("-30d", today=today) == today - timedelta(days=30)


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "tomorrow", "5y", "+5x", "abc-def-gh"])
def test_parse_end_spec_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_end_spec(bad)


# ─── NYSE / NASDAQ — equity calendars ──────────────────────────────────────


@pytest.mark.unit
def test_nyse_calendar_excludes_known_holidays() -> None:
    """Christmas, MLK Day, and Independence Day are non-trading on NYSE."""
    cal = _nyse_2023_calendar()
    rows = build_equity_rows(
        VENUE_NYSE,
        date(2023, 1, 1),
        date(2023, 12, 31),
        get_calendar=_make_get_calendar({"XNYS": cal}),
    )
    by_date = {r["date"]: r for r in rows}
    # Christmas 2023 was a Monday — non-trading, reason=holiday.
    christmas = by_date["2023-12-25"]
    assert christmas["is_trading_day"] is False
    assert christmas["reason"] == REASON_HOLIDAY
    # MLK Day 2023 (3rd Monday in January) — also reason=holiday.
    mlk = by_date["2023-01-16"]
    assert mlk["is_trading_day"] is False
    assert mlk["reason"] == REASON_HOLIDAY
    # Independence Day 2023 fell on a Tuesday — reason=holiday, not weekend.
    ind = by_date["2023-07-04"]
    assert ind["is_trading_day"] is False
    assert ind["reason"] == REASON_HOLIDAY
    # And a regular trading day (e.g. Wed Jan 4 2023) is True with no reason.
    reg = by_date["2023-01-04"]
    assert reg["is_trading_day"] is True
    assert reg["reason"] is None


@pytest.mark.unit
def test_equity_weekend_tagged_weekend_not_holiday() -> None:
    """Sat/Sun must use reason='weekend' even on equity venues."""
    cal = _nyse_2023_calendar()
    rows = build_equity_rows(
        VENUE_NYSE,
        date(2023, 1, 1),
        date(2023, 1, 8),
        get_calendar=_make_get_calendar({"XNYS": cal}),
    )
    by_date = {r["date"]: r for r in rows}
    # Jan 7 2023 = Sat, Jan 8 = Sun — both weekends.
    assert by_date["2023-01-07"]["reason"] == REASON_WEEKEND
    assert by_date["2023-01-08"]["reason"] == REASON_WEEKEND
    assert by_date["2023-01-07"]["is_trading_day"] is False


@pytest.mark.unit
def test_equity_row_count_equals_calendar_days() -> None:
    """Every date in [start, end] produces exactly one row, regardless of trading status."""
    cal = _nyse_2023_calendar()
    start, end = date(2023, 6, 1), date(2023, 6, 30)
    rows = build_equity_rows(VENUE_NYSE, start, end, get_calendar=_make_get_calendar({"XNYS": cal}))
    expected = (end - start).days + 1
    assert len(rows) == expected
    # date column is unique within venue (PK invariant).
    seen = {r["date"] for r in rows}
    assert len(seen) == expected


@pytest.mark.unit
def test_nasdaq_uses_xnas_mic() -> None:
    """NASDAQ venue dispatches to the XNAS calendar, not XNYS."""
    nyse = _FakeCalendar(name="XNYS", sessions=[date(2024, 1, 2)])
    nasdaq = _FakeCalendar(name="XNAS", sessions=[date(2024, 1, 3)])
    rows = build_equity_rows(
        VENUE_NASDAQ,
        date(2024, 1, 2),
        date(2024, 1, 3),
        get_calendar=_make_get_calendar({"XNYS": nyse, "XNAS": nasdaq}),
    )
    by_date = {r["date"]: r for r in rows}
    # Tue Jan 2 only trades on the NYSE mock (XNYS), not the NASDAQ mock — so
    # routing NASDAQ → XNAS produces is_trading_day=False on Jan 2.
    assert by_date["2024-01-02"]["is_trading_day"] is False
    assert by_date["2024-01-03"]["is_trading_day"] is True


# ─── CRYPTO — synthetic 24x7 ───────────────────────────────────────────────


@pytest.mark.unit
def test_crypto_calendar_is_24_7() -> None:
    """Every date in the range is a trading day with no reason."""
    rows = build_crypto_rows(date(2023, 1, 1), date(2023, 12, 31))
    assert len(rows) == 365
    assert all(r["is_trading_day"] is True for r in rows)
    assert all(r["reason"] is None for r in rows)
    assert all(r["venue"] == VENUE_CRYPTO for r in rows)
    # Specifically: Christmas Day is open on CRYPTO.
    by_date = {r["date"]: r for r in rows}
    assert by_date["2023-12-25"]["is_trading_day"] is True


# ─── FX — synthetic 5-day-week ─────────────────────────────────────────────


@pytest.mark.unit
def test_fx_calendar_excludes_full_weekend() -> None:
    """Both Saturday and Sunday are non-trading on FX."""
    # Sat 2023-01-07 + Sun 2023-01-08.
    rows = build_fx_rows(date(2023, 1, 6), date(2023, 1, 9))
    by_date = {r["date"]: r for r in rows}
    assert by_date["2023-01-06"]["is_trading_day"] is True  # Fri
    assert by_date["2023-01-07"]["is_trading_day"] is False  # Sat
    assert by_date["2023-01-07"]["reason"] == REASON_WEEKEND
    assert by_date["2023-01-08"]["is_trading_day"] is False  # Sun
    assert by_date["2023-01-08"]["reason"] == REASON_WEEKEND
    assert by_date["2023-01-09"]["is_trading_day"] is True  # Mon


@pytest.mark.unit
def test_fx_holiday_dates_still_trading_at_daily_resolution() -> None:
    """FX has no holiday model at daily granularity — only weekend gating."""
    # Christmas 2023 fell on a Monday; FX still flags it as trading at daily
    # resolution because the FX calendar logic intentionally only excludes
    # weekends.  This is documented in ADR-0013 and asserted here so the
    # behaviour is captured.
    rows = build_fx_rows(date(2023, 12, 25), date(2023, 12, 25))
    assert len(rows) == 1
    assert rows[0]["is_trading_day"] is True


# ─── Multi-venue dispatch ──────────────────────────────────────────────────


@pytest.mark.unit
def test_build_rows_dispatches_per_venue() -> None:
    cal = _nyse_2023_calendar()
    rows = build_rows(
        [VENUE_NYSE, VENUE_CRYPTO, VENUE_FX],
        date(2023, 6, 1),
        date(2023, 6, 7),
        get_calendar=_make_get_calendar({"XNYS": cal}),
    )
    # 7 days × 3 venues = 21 rows.
    assert len(rows) == 21
    venues = {r["venue"] for r in rows}
    assert venues == {VENUE_NYSE, VENUE_CRYPTO, VENUE_FX}


@pytest.mark.unit
def test_build_rows_for_venue_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        build_rows_for_venue("LSE", date(2024, 1, 1), date(2024, 1, 2))


# ─── Idempotent upsert ─────────────────────────────────────────────────────


@dataclass
class _FakeResp:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    table_name: str
    store: dict[tuple[str, str], dict[str, Any]]  # (date, venue) → row
    upsert_calls: list[dict[str, Any]] = field(default_factory=list)
    _staged_rows: list[dict[str, Any]] | None = None
    _on_conflict: str | None = None

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str | None = None) -> "_FakeQuery":
        self._staged_rows = list(rows)
        self._on_conflict = on_conflict
        return self

    def execute(self) -> _FakeResp:
        assert self._staged_rows is not None, "execute() called without upsert()"
        # Merge into store keyed by (date, venue) — emulates Postgres upsert
        # semantics on the composite primary key.
        for row in self._staged_rows:
            key = (row["date"], row["venue"])
            self.store[key] = dict(row)
        self.upsert_calls.append(
            {"on_conflict": self._on_conflict, "rows": list(self._staged_rows)}
        )
        return _FakeResp(data=list(self._staged_rows))


@dataclass
class _FakeClient:
    store: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    queries: list[_FakeQuery] = field(default_factory=list)

    def table(self, name: str) -> _FakeQuery:
        q = _FakeQuery(table_name=name, store=self.store)
        self.queries.append(q)
        return q


@pytest.mark.unit
def test_idempotent_upsert() -> None:
    """Running the sync twice yields identical row count and no duplicates."""
    rows = build_rows(
        [VENUE_NYSE, VENUE_CRYPTO, VENUE_FX],
        date(2023, 1, 2),
        date(2023, 1, 8),
        get_calendar=_make_get_calendar({"XNYS": _nyse_2023_calendar()}),
    )
    client = _FakeClient()
    first = upsert_trading_calendar(client, rows, chunk=500)
    second = upsert_trading_calendar(client, rows, chunk=500)
    assert first == second == len(rows)
    # Store is keyed by (date, venue) — second run must not grow it.
    assert len(client.store) == len(rows)
    # All upsert calls must specify on_conflict='date,venue' for PG idempotency.
    assert all(q._on_conflict == "date,venue" for q in client.queries if q.upsert_calls)


@pytest.mark.unit
def test_upsert_chunks_payloads() -> None:
    """Rows larger than the chunk size are split into multiple HTTP calls."""
    rows = build_crypto_rows(date(2023, 1, 1), date(2023, 1, 31))
    client = _FakeClient()
    total = upsert_trading_calendar(client, rows, chunk=10)
    assert total == 31
    # 31 / 10 → ceil 4 chunks.
    upsert_queries = [q for q in client.queries if q.upsert_calls]
    assert len(upsert_queries) == 4
    chunk_sizes = [len(q.upsert_calls[0]["rows"]) for q in upsert_queries]
    assert chunk_sizes == [10, 10, 10, 1]


@pytest.mark.unit
def test_upsert_empty_rows_is_noop() -> None:
    client = _FakeClient()
    assert upsert_trading_calendar(client, []) == 0
    assert client.queries == []


# ─── Ticker venue mapping ─────────────────────────────────────────────────


# Tickers that the daily backfill pipeline writes price_history rows for.  Pulled
# from digiquant/src/digiquant/atlas/config/watchlist.md, excluding the spread-pair and
# macro-indicator sections (those are derived/relative, not directly fetched).
WATCHLIST_PRICE_TICKERS: tuple[str, ...] = (
    # US equities — market cap
    "SPY",
    "QQQ",
    "DIA",
    "IWB",
    "VTI",
    "MDY",
    "IJH",
    "IWM",
    "IJR",
    # Sector
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLRE",
    "XLU",
    "XLY",
    "XLP",
    "XLB",
    "XLC",
    # Intl developed
    "EFA",
    "VEA",
    "VGK",
    "EWJ",
    "EWG",
    "EWU",
    "EWA",
    # EM
    "EEM",
    "VWO",
    "FXI",
    "ASHR",
    "EWZ",
    "EWT",
    "EWY",
    "INDA",
    # Crypto spot pairs
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "BNB-USD",
    "BITO",
    "TRX-USD",
    "DOGE-USD",
    "ADA-USD",
    "AVAX-USD",
    "LINK-USD",
    "DOT-USD",
    "BCH-USD",
    "LTC-USD",
    "NEAR-USD",
    "ATOM-USD",
    "XMR-USD",
    "SUI20947-USD",
    # Crypto ETFs
    "IBIT",
    "FBTC",
    "ETHA",
    "FETH",
    "GBTC",
    # Commodities
    "GLD",
    "IAU",
    "SLV",
    "DBO",
    "USO",
    "BNO",
    "PDBC",
    "DJP",
    "CPER",
    # Fixed income / cash
    "BIL",
    "SHV",
    "SHY",
    "IEF",
    "TLT",
    "AGG",
    "HYG",
    "LQD",
    "TIP",
    "EMB",
    # Macro tradeable
    "UUP",
)


@pytest.mark.unit
def test_ticker_venue_mapping_covers_all_core_tickers() -> None:
    """Every ticker the backfill writes must have an authoritative venue."""
    missing = [t for t in WATCHLIST_PRICE_TICKERS if venue_for(t) is None]
    assert missing == [], f"unmapped tickers: {missing}"


@pytest.mark.unit
def test_ticker_venue_values_within_schema_allowlist() -> None:
    """Every mapped venue is one of {NYSE, NASDAQ, CRYPTO, FX} — what
    migration 025 accepts."""
    out_of_band = {v for v in CORE_TICKER_VENUES.values() if v not in ALLOWED_VENUES}
    assert out_of_band == set()


@pytest.mark.unit
def test_venue_for_is_case_insensitive() -> None:
    assert venue_for("spy") == "NYSE"
    assert venue_for("btc-usd") == "CRYPTO"
    assert venue_for("eurusd") == "FX"
    assert venue_for("") is None
    assert venue_for("UNKNOWN-TICKER") is None


@pytest.mark.unit
def test_all_venues_constant_matches_schema() -> None:
    assert set(ALL_VENUES) == ALLOWED_VENUES
