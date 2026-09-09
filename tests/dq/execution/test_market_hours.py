"""Unit tests for digiquant.execution.market_hours (#3612)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from digiquant.execution.market_hours import (
    REASON_EARLY_CLOSE,
    REASON_HOLIDAY,
    REASON_MISSING_CALENDAR,
    REASON_OUTSIDE_SESSION,
    REASON_UNMAPPED_VENUE,
    REASON_WEEKEND,
    CalendarDayStatus,
    SessionState,
    equity_session_bounds,
    index_calendar_days,
    is_execution_eligible,
    next_session_open,
    resolve_ticker_session,
    resolve_venue_session,
    venue_sessions_snapshot,
)

pytestmark = pytest.mark.unit

_ET = ZoneInfo("America/New_York")


def _et(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=_ET)


def _nyse_rows(*days: tuple[date, bool, str | None]) -> list[CalendarDayStatus]:
    return [
        CalendarDayStatus(day=d, venue="NYSE", is_trading_day=open_, reason=reason)
        for d, open_, reason in days
    ]


class TestEquitySessions:
    def test_weekday_open_at_0935(self) -> None:
        day = date(2026, 6, 15)  # Monday
        rows = _nyse_rows((day, True, None))
        ctx = resolve_venue_session("NYSE", _et(2026, 6, 15, 9, 35), rows)
        assert ctx.is_open is True
        assert ctx.state is SessionState.OPEN
        assert ctx.fail_closed is False
        assert ctx.session_open == _et(2026, 6, 15, 9, 30)
        assert ctx.session_close == _et(2026, 6, 15, 16, 0)

    def test_weekend_closed(self) -> None:
        sat = date(2026, 6, 13)
        rows = _nyse_rows((sat, False, REASON_WEEKEND))
        ctx = resolve_venue_session("NYSE", _et(2026, 6, 13, 10, 0), rows)
        assert ctx.is_open is False
        assert ctx.reason == REASON_WEEKEND
        assert ctx.fail_closed is False

    def test_holiday_closed(self) -> None:
        # 2026-07-03 observed Independence Day Friday close pattern —
        # use a known holiday weekday.
        day = date(2026, 1, 1)
        rows = _nyse_rows((day, False, "holiday:New Years Day"))
        ctx = resolve_venue_session("NYSE", _et(2026, 1, 1, 10, 0), rows)
        assert ctx.is_open is False
        assert ctx.reason == "holiday:New Years Day"
        assert "holiday" in (ctx.reason or "")

    def test_missing_calendar_row_fail_closed(self) -> None:
        # Index has other days but not the evaluation day.
        rows = _nyse_rows((date(2026, 6, 12), True, None))
        ctx = resolve_venue_session("NYSE", _et(2026, 6, 15, 10, 0), rows)
        assert ctx.is_open is False
        assert ctx.fail_closed is True
        assert ctx.reason == REASON_MISSING_CALENDAR

    def test_empty_calendar_fail_closed_for_equity(self) -> None:
        ctx = resolve_venue_session("NYSE", _et(2026, 6, 15, 10, 0), [])
        assert ctx.is_open is False
        assert ctx.fail_closed is True
        assert ctx.reason == REASON_MISSING_CALENDAR

    def test_early_close_open_before_1300(self) -> None:
        day = date(2026, 11, 27)  # day-after-Thanksgiving style
        rows = _nyse_rows((day, True, REASON_EARLY_CLOSE))
        ctx = resolve_venue_session("NYSE", _et(2026, 11, 27, 11, 0), rows)
        assert ctx.is_open is True
        assert ctx.early_close is True
        assert ctx.session_close == _et(2026, 11, 27, 13, 0)

    def test_early_close_closed_after_1300(self) -> None:
        day = date(2026, 11, 27)
        rows = _nyse_rows((day, True, REASON_EARLY_CLOSE))
        ctx = resolve_venue_session("NYSE", _et(2026, 11, 27, 14, 0), rows)
        assert ctx.is_open is False
        assert ctx.reason == REASON_OUTSIDE_SESSION
        assert ctx.early_close is True

    def test_dst_spring_forward_bounds_remain_et_wall_clock(self) -> None:
        # 2026-03-08 is DST start in US; session still 09:30–16:00 ET wall clock.
        day = date(2026, 3, 9)  # Monday after spring forward
        rows = _nyse_rows((day, True, None))
        open_at, close_at = equity_session_bounds(day)
        assert open_at.tzinfo == _ET
        assert open_at.hour == 9 and open_at.minute == 30
        ctx = resolve_venue_session("NYSE", _et(2026, 3, 9, 9, 35), rows)
        assert ctx.is_open is True
        assert ctx.session_open == open_at
        assert ctx.session_close == close_at

    def test_dst_fall_back_bounds_remain_et_wall_clock(self) -> None:
        day = date(2026, 11, 2)  # Monday after fall back
        rows = _nyse_rows((day, True, None))
        ctx = resolve_venue_session("NYSE", _et(2026, 11, 2, 9, 35), rows)
        assert ctx.is_open is True
        assert ctx.session_open == _et(2026, 11, 2, 9, 30)

    def test_before_open_outside_session(self) -> None:
        day = date(2026, 6, 15)
        rows = _nyse_rows((day, True, None))
        ctx = resolve_venue_session("NYSE", _et(2026, 6, 15, 8, 0), rows)
        assert ctx.is_open is False
        assert ctx.reason == REASON_OUTSIDE_SESSION
        assert ctx.next_open == _et(2026, 6, 15, 9, 30)

    def test_nasdaq_uses_same_equity_rules(self) -> None:
        day = date(2026, 6, 15)
        rows = [CalendarDayStatus(day=day, venue="NASDAQ", is_trading_day=True, reason=None)]
        ctx = resolve_venue_session("NASDAQ", _et(2026, 6, 15, 10, 0), rows)
        assert ctx.is_open is True


class TestCryptoAndFx:
    def test_crypto_open_24x7_without_calendar(self) -> None:
        ctx = resolve_venue_session("CRYPTO", _et(2026, 6, 14, 3, 0), [])  # Sunday
        assert ctx.is_open is True
        assert ctx.fail_closed is False

    def test_fx_weekend_closed_without_calendar(self) -> None:
        ctx = resolve_venue_session("FX", _et(2026, 6, 14, 10, 0), None)
        assert ctx.is_open is False
        assert ctx.reason == REASON_WEEKEND

    def test_fx_weekday_open_without_calendar(self) -> None:
        ctx = resolve_venue_session("FX", _et(2026, 6, 15, 10, 0), None)
        assert ctx.is_open is True

    def test_fx_missing_row_fail_closed_when_calendar_supplied(self) -> None:
        rows = [
            CalendarDayStatus(day=date(2026, 6, 12), venue="FX", is_trading_day=True, reason=None)
        ]
        ctx = resolve_venue_session("FX", _et(2026, 6, 15, 10, 0), rows)
        assert ctx.is_open is False
        assert ctx.fail_closed is True
        assert ctx.reason == REASON_MISSING_CALENDAR


class TestTickerAndNextOpen:
    def test_spy_maps_to_nyse(self) -> None:
        day = date(2026, 6, 15)
        rows = _nyse_rows((day, True, None))
        eligible, ctx = is_execution_eligible("SPY", _et(2026, 6, 15, 9, 35), rows)
        assert eligible is True
        assert ctx.venue == "NYSE"

    def test_btc_open_on_weekend(self) -> None:
        eligible, ctx = is_execution_eligible("BTC-USD", _et(2026, 6, 14, 12, 0), [])
        assert eligible is True
        assert ctx.venue == "CRYPTO"

    def test_unmapped_ticker_fail_closed(self) -> None:
        eligible, ctx = is_execution_eligible("ZZZZNOTREAL", _et(2026, 6, 15, 10, 0), [])
        assert eligible is False
        assert ctx.fail_closed is True
        assert ctx.reason == REASON_UNMAPPED_VENUE

    def test_next_open_skips_weekend_to_monday(self) -> None:
        fri = date(2026, 6, 12)
        sat = date(2026, 6, 13)
        sun = date(2026, 6, 14)
        mon = date(2026, 6, 15)
        rows = _nyse_rows(
            (fri, True, None),
            (sat, False, REASON_WEEKEND),
            (sun, False, REASON_WEEKEND),
            (mon, True, None),
        )
        nxt = next_session_open("NYSE", _et(2026, 6, 12, 16, 1), rows)
        assert nxt == _et(2026, 6, 15, 9, 30)

    def test_next_open_skips_holiday(self) -> None:
        day = date(2026, 1, 1)
        nxt_day = date(2026, 1, 2)
        rows = _nyse_rows(
            (day, False, REASON_HOLIDAY),
            (nxt_day, True, None),
        )
        nxt = next_session_open("NYSE", _et(2026, 1, 1, 10, 0), rows)
        assert nxt == _et(2026, 1, 2, 9, 30)

    def test_venue_sessions_snapshot_shape(self) -> None:
        day = date(2026, 6, 15)
        rows = index_calendar_days(
            _nyse_rows((day, True, None))
            + [
                CalendarDayStatus(day=day, venue="NASDAQ", is_trading_day=True, reason=None),
                CalendarDayStatus(day=day, venue="FX", is_trading_day=True, reason=None),
            ]
        )
        snap = venue_sessions_snapshot(_et(2026, 6, 15, 9, 35), rows)
        assert "venues" in snap
        assert snap["venues"]["NYSE"]["is_open"] is True
        assert snap["venues"]["CRYPTO"]["is_open"] is True
        assert snap["venues"]["FX"]["is_open"] is True


class TestNaiveDatetime:
    def test_naive_treated_as_utc(self) -> None:
        day = date(2026, 6, 15)
        rows = _nyse_rows((day, True, None))
        # 13:35 UTC == 09:35 EDT — deliberately naive to exercise UTC defaulting.
        naive = datetime(2026, 6, 15, 13, 35)  # noqa: DTZ001
        ctx = resolve_ticker_session("SPY", naive, rows)
        assert ctx.is_open is True
