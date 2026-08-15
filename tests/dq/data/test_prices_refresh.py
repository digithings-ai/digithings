"""On-demand technicals recompute (Pillar 1F).

recompute_technicals_from_history reads raw OHLCV from price_history (look-ahead-guarded),
recomputes indicators, and upserts price_technicals — network-free. Tickers below MIN_BARS
are skipped; the read is bounded by .lte(as_of).

#1752 coverage — three invariants that the pre-fix module violated:

* the ``price_history`` read is **paginated** (PostgREST caps a rangeless response at
  1 000 rows, so one request over the watchlist returned ~4 bars per ticker — all below
  MIN_BARS — and the recompute silently processed nothing);
* only rows inside the **write window** are upserted, so a 200-bar indicator warm-up never
  overwrites a previously-valid ``sma_200`` with ``NULL``;
* non-session rows are dropped against ``trading_calendar`` before computing, so weekend
  bars do not become spurious technicals.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from digiquant.data.prices import refresh
from digiquant.data.prices.technicals import MIN_BARS

pytestmark = pytest.mark.unit

AS_OF = date(2026, 3, 1)
POSTGREST_MAX_ROWS = 1000


def _ohlcv(ticker: str, n: int, *, end: date = date(2026, 2, 9)) -> list[dict]:
    """``n`` consecutive daily bars ending on ``end`` (oldest first)."""
    rows = []
    for i in range(n):
        d = end - timedelta(days=n - 1 - i)
        px = 100.0 + i * 0.5
        rows.append(
            {
                "date": d.isoformat(),
                "ticker": ticker,
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px + 0.5,
                "volume": 1_000_000,
            }
        )
    return rows


def _capture_upsert():
    seen: dict[str, list] = {}

    def _fake(_client, rows, **_kw):
        seen["rows"] = rows
        return SimpleNamespace(table="price_technicals", rows=len(rows))

    return seen, _fake


class _FakeHistoryTable:
    """PostgREST-shaped fake: honours ``.range()`` and caps a rangeless read at 1 000 rows.

    Emulating the *server* rather than the current implementation is deliberate — it means
    the unfixed (rangeless) module truncates instead of raising, so the pagination test
    fails on an assertion about missing data rather than on a traceback.
    """

    def __init__(self, rows: list[dict]) -> None:
        self._all = rows
        self._rows = rows
        self._range: tuple[int, int] | None = None
        self.requests = 0

    def select(self, _cols: str) -> _FakeHistoryTable:
        return self

    def in_(self, column: str, values: list[str]) -> _FakeHistoryTable:
        self._rows = [r for r in self._rows if r.get(column) in values]
        return self

    def lte(self, column: str, value: str) -> _FakeHistoryTable:
        self._rows = [r for r in self._rows if str(r.get(column)) <= value]
        return self

    def gte(self, column: str, value: str) -> _FakeHistoryTable:
        self._rows = [r for r in self._rows if str(r.get(column)) >= value]
        return self

    def eq(self, column: str, value: object) -> _FakeHistoryTable:
        self._rows = [r for r in self._rows if r.get(column) == value]
        return self

    def order(self, column: str, **_kw: object) -> _FakeHistoryTable:
        self._rows = sorted(self._rows, key=lambda r: str(r.get(column)))
        return self

    def range(self, start: int, end: int) -> _FakeHistoryTable:
        self._range = (start, end)
        return self

    def execute(self) -> SimpleNamespace:
        self.requests += 1
        rows = self._rows
        if self._range is not None:
            start, end = self._range
            rows = rows[start : min(end + 1, start + POSTGREST_MAX_ROWS)]
        rows = rows[:POSTGREST_MAX_ROWS]
        # Reset the filter chain for the next request, exactly as a fresh builder would.
        self._rows = self._all
        self._range = None
        return SimpleNamespace(data=list(rows))


class _FakeClient:
    def __init__(self, history: list[dict], trading_days: list[date] | None = None) -> None:
        self.history = _FakeHistoryTable(history)
        self.calendar = _FakeHistoryTable(
            [
                {"date": d.isoformat(), "venue": "NYSE", "is_trading_day": True}
                for d in (trading_days or [])
            ]
        )

    def table(self, name: str) -> _FakeHistoryTable:
        if name == "price_history":
            return self.history
        if name == "trading_calendar":
            return self.calendar
        raise AssertionError(f"unexpected table {name}")


def test_recompute_upserts_for_sufficient_history() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 40)),
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF
        )
    assert result.tickers_processed == 1
    assert result.rows_upserted > 0
    assert {"date", "ticker"} <= set(seen["rows"][0])


def test_skips_tickers_below_min_bars() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", MIN_BARS - 1)),
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF
        )
    assert result.tickers_processed == 0
    assert result.rows_upserted == 0
    assert seen["rows"] == []  # upsert called with nothing


def test_empty_tickers_is_noop() -> None:
    with patch.object(refresh, "upsert_price_technicals") as upsert:
        result = refresh.recompute_technicals_from_history(client=object(), tickers=[], as_of=AS_OF)
    assert result == refresh.RefreshResult(0, 0)
    upsert.assert_not_called()


def test_dedupes_tickers_before_read() -> None:
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 40)) as read,
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY", "SPY", ""], as_of=AS_OF
        )
    # Deduped + empties dropped → a single "SPY" passed to the read.
    assert read.call_args.args[1] == ["SPY"]


def test_read_is_look_ahead_guarded() -> None:
    client = MagicMock()
    builder = client.table.return_value
    # A single MagicMock stands in for the whole fluent chain, so every filter method
    # returns the same object and the .lte assertion below is unambiguous.
    for method in ("select", "in_", "lte", "gte", "order", "range"):
        getattr(builder, method).return_value = builder
    builder.execute.return_value.data = []
    refresh.recompute_technicals_from_history(client=client, tickers=["SPY"], as_of=AS_OF)
    client.table.assert_called_with("price_history")
    # The upper bound is run_date — a future price row can never enter the window.
    builder.lte.assert_called_with("date", AS_OF.isoformat())


# ─── #1752: pagination ────────────────────────────────────────────────────


def test_read_paginates_past_the_postgrest_row_cap() -> None:
    """The recompute must reach the freshest bar, not the oldest 1 000 rows.

    Regression proof for #1752 / ``ATLAS_REFRESH_ON_DEMAND``: the unfixed rangeless read
    returned the oldest 1 000 rows of the window, so the newest date written was ~10 months
    stale and the write window held nothing at all.
    """
    latest = date(2026, 2, 28)
    universe = ["SPY", "QQQ", "DIA", "IWM"]
    history = [row for t in universe for row in _ohlcv(t, 400, end=latest)]
    client = _FakeClient(history)

    seen, fake = _capture_upsert()
    with patch.object(refresh, "upsert_price_technicals", side_effect=fake):
        result = refresh.recompute_technicals_from_history(
            client=client, tickers=universe, as_of=AS_OF
        )

    # 4 tickers × ~350 in-window bars ≈ 1 400 rows, so the window cannot fit in one response.
    assert client.history.requests > 1, "a single request cannot exceed PostgREST's row cap"
    assert result.tickers_processed == len(universe)
    # Every ticker reaches the freshest stored bar.
    for ticker in universe:
        dates = [r["date"] for r in seen["rows"] if r["ticker"] == ticker]
        assert dates, f"{ticker} produced no rows"
        assert max(dates) == latest.isoformat()


# ─── #1752: write window vs warm-up ───────────────────────────────────────


def test_warmup_rows_are_never_written() -> None:
    """No emitted row may carry a NULL long-window indicator when history supports one.

    Regression proof for the clobber itself: the unfixed module emitted every computed row,
    including the ~200-bar warm-up prefix where ``sma_200``/``zscore_200`` are NULL, and the
    coalesce-free bulk upsert then replaced good stored values with NULL.
    """
    seen, fake = _capture_upsert()
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 300)),
        patch.object(refresh, "upsert_price_technicals", side_effect=fake),
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF
        )

    assert result.rows_upserted > 0
    nulled = [r["date"] for r in seen["rows"] if r.get("sma_200") is None]
    assert not nulled, f"warm-up rows would clobber stored sma_200: {nulled[:5]}"
    assert all(r.get("zscore_200") is not None for r in seen["rows"])


def test_since_sets_the_write_floor_and_the_read_extends_earlier() -> None:
    with (
        patch.object(refresh, "_read_history", return_value=[]) as read,
        patch.object(refresh, "upsert_price_technicals") as upsert,
    ):
        upsert.return_value = SimpleNamespace(table="price_technicals", rows=0)
        refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF, since=date(2021, 4, 8)
        )
    kwargs = read.call_args.kwargs
    assert kwargs["end"] == AS_OF
    # Read starts a full warm-up before the write floor, so the first written row is valid.
    assert kwargs["start"] == date(2021, 4, 8) - timedelta(days=refresh.WARMUP_CALENDAR_DAYS)


def test_default_write_window_is_recent_only() -> None:
    with (
        patch.object(refresh, "_read_history", return_value=[]) as read,
        patch.object(refresh, "upsert_price_technicals") as upsert,
    ):
        upsert.return_value = SimpleNamespace(table="price_technicals", rows=0)
        refresh.recompute_technicals_from_history(client=object(), tickers=["SPY"], as_of=AS_OF)
    expected_floor = AS_OF - timedelta(days=refresh.DEFAULT_WRITE_WINDOW_DAYS)
    assert read.call_args.kwargs["start"] == expected_floor - timedelta(
        days=refresh.WARMUP_CALENDAR_DAYS
    )


def test_dry_run_computes_without_writing() -> None:
    with (
        patch.object(refresh, "_read_history", return_value=_ohlcv("SPY", 300)),
        patch.object(refresh, "upsert_price_technicals") as upsert,
    ):
        result = refresh.recompute_technicals_from_history(
            client=object(), tickers=["SPY"], as_of=AS_OF, dry_run=True
        )
    upsert.assert_not_called()
    # preflight._refresh_stale_technicals gates on rows_upserted > 0 — a dry run must not
    # look like a successful refresh.
    assert result.rows_upserted == 0
    assert result.rows_computed > 0
    assert result.history_rows_read == 300


# ─── #1752: trading-day filter ────────────────────────────────────────────


def test_non_session_rows_are_dropped_before_computing() -> None:
    """Weekend bars must not become technicals rows the cron path would never write."""
    latest = date(2026, 2, 27)  # Friday
    history = _ohlcv("SPY", 400, end=latest)
    all_dates = [date.fromisoformat(r["date"]) for r in history]
    sessions = [d for d in all_dates if d.weekday() < 5]

    write_floor = AS_OF - timedelta(days=refresh.DEFAULT_WRITE_WINDOW_DAYS)
    read_floor = write_floor - timedelta(days=refresh.WARMUP_CALENDAR_DAYS)
    expected_dropped = [d for d in all_dates if d >= read_floor and d.weekday() >= 5]
    expected_written = [d.isoformat() for d in sessions if d >= write_floor]
    assert expected_dropped and expected_written

    seen, fake = _capture_upsert()
    client = _FakeClient(history, trading_days=sessions)
    with patch.object(refresh, "upsert_price_technicals", side_effect=fake):
        result = refresh.recompute_technicals_from_history(
            client=client, tickers=["SPY"], as_of=AS_OF
        )

    assert result.non_trading_rows_dropped == len(expected_dropped)
    assert sorted(r["date"] for r in seen["rows"]) == sorted(expected_written)


def test_missing_calendar_falls_back_to_all_rows() -> None:
    """An empty trading_calendar must not silently produce zero technicals."""
    history = _ohlcv("SPY", 300, end=date(2026, 2, 27))
    client = _FakeClient(history, trading_days=[])
    seen, fake = _capture_upsert()
    with patch.object(refresh, "upsert_price_technicals", side_effect=fake):
        result = refresh.recompute_technicals_from_history(
            client=client, tickers=["SPY"], as_of=AS_OF
        )
    assert result.non_trading_rows_dropped == 0
    assert result.rows_upserted > 0
    assert seen["rows"]
