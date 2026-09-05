"""Authoritative venue-session calendar for deferred execution (#3612).

Pure / I/O-light: callers supply ``trading_calendar`` rows (or synthetic day
status). This module never opens a Supabase client and never imports
``digiquant.brokers`` / live routing.

Fail-closed contract
--------------------
Missing venue mapping, missing calendar rows for equity venues, or an unknown
venue → ``is_open=False`` with ``fail_closed=True``. CRYPTO is open 24×7 without
a row. FX weekends are closed from the weekday alone; when calendar rows are
supplied for FX, a missing weekday row also fails closed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from digiquant.data.prices.ticker_venues import ALLOWED_VENUES, venue_for

_ET = ZoneInfo("America/New_York")

VENUE_NYSE = "NYSE"
VENUE_NASDAQ = "NASDAQ"
VENUE_CRYPTO = "CRYPTO"
VENUE_FX = "FX"

REASON_WEEKEND = "weekend"
REASON_HOLIDAY = "holiday"
REASON_EARLY_CLOSE = "early_close"
REASON_MISSING_CALENDAR = "missing_calendar"
REASON_UNMAPPED_VENUE = "unmapped_venue"
REASON_UNKNOWN_VENUE = "unknown_venue"
REASON_OUTSIDE_SESSION = "outside_session"

_EQUITY_VENUES = frozenset({VENUE_NYSE, VENUE_NASDAQ})
_REGULAR_OPEN = time(9, 30)
_REGULAR_CLOSE = time(16, 0)
_EARLY_CLOSE = time(13, 0)


class SessionState(StrEnum):
    """Coarse open/closed label for deliberation and execution gates."""

    OPEN = "open"
    CLOSED = "closed"


class CalendarDayStatus(BaseModel):
    """One ``trading_calendar`` row, normalized for pure session resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    day: date
    venue: str
    is_trading_day: bool
    reason: str | None = None


class MarketSessionContext(BaseModel):
    """Typed venue session snapshot for PM / execution consumers.

    ``fail_closed`` is True when authoritative calendar data was missing and the
    gate therefore treated the venue as closed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    venue: str
    evaluation_time: datetime
    weekday: int = Field(ge=0, le=6, description="Monday=0 … Sunday=6 in venue local time")
    is_open: bool
    state: SessionState
    session_open: datetime | None = None
    session_close: datetime | None = None
    next_open: datetime | None = None
    reason: str | None = None
    fail_closed: bool = False
    early_close: bool = False

    def model_dump_for_context(self) -> dict[str, Any]:
        """JSON-friendly dict for ``market_context['venue_sessions']``."""
        return self.model_dump(mode="json")


def calendar_day_from_row(row: Mapping[str, Any]) -> CalendarDayStatus:
    """Normalize a PostgREST / dict calendar row into :class:`CalendarDayStatus`."""
    raw_date = row.get("date")
    if isinstance(raw_date, datetime):
        day = raw_date.date()
    elif isinstance(raw_date, date):
        day = raw_date
    else:
        day = date.fromisoformat(str(raw_date)[:10])
    venue = str(row.get("venue") or "").upper()
    reason = row.get("reason")
    return CalendarDayStatus(
        day=day,
        venue=venue,
        is_trading_day=bool(row.get("is_trading_day")),
        reason=str(reason) if reason is not None else None,
    )


def index_calendar_days(
    rows: Iterable[Mapping[str, Any] | CalendarDayStatus],
) -> dict[tuple[str, date], CalendarDayStatus]:
    """Index calendar rows by ``(venue, date)``."""
    out: dict[tuple[str, date], CalendarDayStatus] = {}
    for row in rows:
        status = row if isinstance(row, CalendarDayStatus) else calendar_day_from_row(row)
        out[(status.venue.upper(), status.day)] = status
    return out


def _ensure_aware(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=UTC)
    return when


def _as_et(when: datetime) -> datetime:
    return _ensure_aware(when).astimezone(_ET)


def _is_early_close_reason(reason: str | None) -> bool:
    if not reason:
        return False
    lowered = reason.lower()
    return lowered == REASON_EARLY_CLOSE or lowered.startswith(f"{REASON_EARLY_CLOSE}:")


def _combine_et(day: date, wall: time) -> datetime:
    return datetime.combine(day, wall, tzinfo=_ET)


def equity_session_bounds(
    day: date,
    *,
    early_close: bool = False,
) -> tuple[datetime, datetime]:
    """Regular or early-close session bounds in America/New_York."""
    close = _EARLY_CLOSE if early_close else _REGULAR_CLOSE
    return _combine_et(day, _REGULAR_OPEN), _combine_et(day, close)


def _normalize_calendar(
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None,
) -> dict[tuple[str, date], CalendarDayStatus]:
    if isinstance(calendar_rows, Mapping):
        return dict(calendar_rows)
    if calendar_rows is None:
        return {}
    return index_calendar_days(calendar_rows)


def _lookup_day(
    calendar: Mapping[tuple[str, date], CalendarDayStatus],
    venue: str,
    day: date,
) -> CalendarDayStatus | None:
    return calendar.get((venue.upper(), day))


def _day_is_tradable(
    venue: str,
    day: date,
    calendar: Mapping[tuple[str, date], CalendarDayStatus],
    *,
    require_row: bool,
) -> tuple[bool, bool, str | None, bool]:
    """Return ``(tradable, fail_closed, reason, early_close)`` for a calendar day."""
    venue_key = venue.upper()
    if venue_key == VENUE_CRYPTO:
        return True, False, None, False
    if venue_key == VENUE_FX:
        if day.weekday() >= 5:
            return False, False, REASON_WEEKEND, False
        day_row = _lookup_day(calendar, venue_key, day)
        if day_row is None:
            if require_row and calendar:
                return False, True, REASON_MISSING_CALENDAR, False
            # No rows supplied: weekday FX is tradable by synthetic rule.
            return True, False, None, False
        if not day_row.is_trading_day:
            return False, False, day_row.reason or REASON_HOLIDAY, False
        return True, False, None, False

    # Equity
    day_row = _lookup_day(calendar, venue_key, day)
    if day_row is None:
        return False, True, REASON_MISSING_CALENDAR, False
    if not day_row.is_trading_day:
        reason = day_row.reason or (REASON_WEEKEND if day.weekday() >= 5 else REASON_HOLIDAY)
        return False, False, reason, False
    early = _is_early_close_reason(day_row.reason)
    return True, False, day_row.reason, early


def next_session_open(
    venue: str,
    after: datetime,
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None = None,
    *,
    early_close_dates: set[date] | frozenset[date] | None = None,
    lookahead_days: int = 21,
) -> datetime | None:
    """First eligible session open strictly after ``after``, or None if unknown."""
    venue_key = (venue or "").upper()
    if venue_key not in ALLOWED_VENUES:
        return None
    calendar = _normalize_calendar(calendar_rows)
    early_dates = early_close_dates or frozenset()
    after_et = _as_et(after)
    require_row = venue_key in _EQUITY_VENUES or bool(calendar)

    if venue_key == VENUE_CRYPTO:
        return after_et + timedelta(seconds=1)

    for offset in range(0, lookahead_days + 1):
        day = after_et.date() + timedelta(days=offset)
        tradable, fail_closed, _reason, early = _day_is_tradable(
            venue_key, day, calendar, require_row=require_row
        )
        if fail_closed:
            # Cannot project through a hole in the equity calendar.
            return None
        if not tradable:
            continue
        early = early or day in early_dates
        if venue_key in _EQUITY_VENUES:
            open_at, _close_at = equity_session_bounds(day, early_close=early)
        else:
            open_at = _combine_et(day, time(0, 0))
        if open_at > after_et:
            return open_at
    return None


def resolve_venue_session(
    venue: str,
    when: datetime,
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None = None,
    *,
    early_close_dates: set[date] | frozenset[date] | None = None,
) -> MarketSessionContext:
    """Resolve open/closed state for ``venue`` at ``when``."""
    venue_key = (venue or "").upper()
    when_aware = _ensure_aware(when)
    when_et = _as_et(when_aware)
    weekday = when_et.weekday()
    day = when_et.date()
    calendar = _normalize_calendar(calendar_rows)
    early_dates = early_close_dates or frozenset()

    def _result(
        *,
        is_open: bool,
        reason: str | None,
        fail_closed: bool = False,
        session_open: datetime | None = None,
        session_close: datetime | None = None,
        early_close: bool = False,
    ) -> MarketSessionContext:
        return MarketSessionContext(
            venue=venue_key or "UNKNOWN",
            evaluation_time=when_aware,
            weekday=weekday,
            is_open=is_open,
            state=SessionState.OPEN if is_open else SessionState.CLOSED,
            session_open=session_open,
            session_close=session_close,
            next_open=next_session_open(
                venue_key or VENUE_NYSE,
                when_aware,
                calendar,
                early_close_dates=early_dates,
            )
            if venue_key in ALLOWED_VENUES
            else None,
            reason=reason,
            fail_closed=fail_closed,
            early_close=early_close,
        )

    if not venue_key:
        return _result(is_open=False, reason=REASON_UNMAPPED_VENUE, fail_closed=True)

    if venue_key not in ALLOWED_VENUES:
        return _result(is_open=False, reason=REASON_UNKNOWN_VENUE, fail_closed=True)

    if venue_key == VENUE_CRYPTO:
        return _result(is_open=True, reason=None)

    require_row = venue_key in _EQUITY_VENUES or bool(calendar)
    tradable, fail_closed, day_reason, early = _day_is_tradable(
        venue_key, day, calendar, require_row=require_row
    )
    if fail_closed:
        return _result(is_open=False, reason=REASON_MISSING_CALENDAR, fail_closed=True)
    if not tradable:
        return _result(is_open=False, reason=day_reason or REASON_HOLIDAY)

    early = early or day in early_dates
    if venue_key in _EQUITY_VENUES:
        open_at, close_at = equity_session_bounds(day, early_close=early)
        if when_et < open_at or when_et >= close_at:
            return _result(
                is_open=False,
                reason=REASON_OUTSIDE_SESSION,
                session_open=open_at,
                session_close=close_at,
                early_close=early,
            )
        return _result(
            is_open=True,
            reason=REASON_EARLY_CLOSE if early else None,
            session_open=open_at,
            session_close=close_at,
            early_close=early,
        )

    # FX weekday
    open_at = _combine_et(day, time(0, 0))
    close_at = _combine_et(day, time(23, 59, 59))
    return _result(
        is_open=True,
        reason=None,
        session_open=open_at,
        session_close=close_at,
    )


def resolve_ticker_session(
    ticker: str,
    when: datetime,
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None = None,
    *,
    early_close_dates: set[date] | frozenset[date] | None = None,
) -> MarketSessionContext:
    """Resolve session state for ``ticker`` via :func:`venue_for` (fail closed)."""
    mapped = venue_for(ticker)
    if mapped is None:
        when_aware = _ensure_aware(when)
        when_et = _as_et(when_aware)
        return MarketSessionContext(
            venue="UNKNOWN",
            evaluation_time=when_aware,
            weekday=when_et.weekday(),
            is_open=False,
            state=SessionState.CLOSED,
            next_open=None,
            reason=REASON_UNMAPPED_VENUE,
            fail_closed=True,
        )
    return resolve_venue_session(
        mapped,
        when,
        calendar_rows,
        early_close_dates=early_close_dates,
    )


def venue_sessions_snapshot(
    when: datetime,
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None = None,
    *,
    venues: Sequence[str] = (VENUE_NYSE, VENUE_NASDAQ, VENUE_CRYPTO, VENUE_FX),
    early_close_dates: set[date] | frozenset[date] | None = None,
) -> dict[str, Any]:
    """Build a deliberation-ready ``venue_sessions`` market_context payload."""
    when_aware = _ensure_aware(when)
    sessions = {
        venue: resolve_venue_session(
            venue,
            when_aware,
            calendar_rows,
            early_close_dates=early_close_dates,
        ).model_dump_for_context()
        for venue in venues
    }
    return {
        "evaluation_time": when_aware.isoformat(),
        "weekday": _as_et(when_aware).weekday(),
        "venues": sessions,
    }


def is_execution_eligible(
    ticker: str,
    when: datetime,
    calendar_rows: Mapping[tuple[str, date], CalendarDayStatus]
    | Sequence[Mapping[str, Any] | CalendarDayStatus]
    | None = None,
    *,
    early_close_dates: set[date] | frozenset[date] | None = None,
) -> tuple[bool, MarketSessionContext]:
    """Return ``(eligible, context)`` — closed / fail-closed → not eligible."""
    ctx = resolve_ticker_session(
        ticker,
        when,
        calendar_rows,
        early_close_dates=early_close_dates,
    )
    return ctx.is_open and not ctx.fail_closed, ctx


__all__ = [
    "CalendarDayStatus",
    "MarketSessionContext",
    "REASON_EARLY_CLOSE",
    "REASON_HOLIDAY",
    "REASON_MISSING_CALENDAR",
    "REASON_OUTSIDE_SESSION",
    "REASON_UNKNOWN_VENUE",
    "REASON_UNMAPPED_VENUE",
    "REASON_WEEKEND",
    "SessionState",
    "VENUE_CRYPTO",
    "VENUE_FX",
    "VENUE_NASDAQ",
    "VENUE_NYSE",
    "calendar_day_from_row",
    "equity_session_bounds",
    "index_calendar_days",
    "is_execution_eligible",
    "next_session_open",
    "resolve_ticker_session",
    "resolve_venue_session",
    "venue_sessions_snapshot",
]
