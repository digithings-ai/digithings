"""Trading-calendar fetcher + row-shaper for ``trading_calendar`` (issue #337).

ADR-0013 establishes the venue-keyed ``trading_calendar`` table.  This module
generates the rows that populate it.

Design — pandas at the boundary, Polars/dicts everywhere else
-------------------------------------------------------------

``exchange_calendars`` returns ``pandas.DatetimeIndex``.  We unwrap that into a
``set[datetime.date]`` immediately and never re-export pandas types.  The rest
of the pipeline (Supabase upsert, audit, tests) consumes plain ``list[dict]``
rows that match the migration-025 schema.

Venue handling
--------------

* ``NYSE`` / ``NASDAQ`` — driven by ``exchange_calendars`` (``XNYS`` / ``XNAS``
  ISO MIC codes).  Non-session weekdays are tagged ``reason='holiday'``;
  weekends are ``reason='weekend'``.
* ``CRYPTO`` — synthetic 24x7 calendar.  Every date is ``is_trading_day=True``
  with ``reason=None``.
* ``FX`` — synthetic 5-day-week calendar.  Sat+Sun are ``reason='weekend'``.
  Daily resolution does not capture the Sun-evening session reopen.

The library is imported lazily inside :func:`_calendar_session_dates` so unit
tests can monkeypatch it without forcing the heavy import on package load.

Idempotency
-----------

Row generation is deterministic for a given ``(venue, start, end)`` tuple, and
the upsert path passes ``on_conflict='date,venue'`` — re-running the sync
produces the same rows and the database write is a no-op aside from
``created_at`` columns set by the table default.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

_logger = logging.getLogger(__name__)

# ─── Venue constants ──────────────────────────────────────────────────────

VENUE_NYSE = "NYSE"
VENUE_NASDAQ = "NASDAQ"
VENUE_CRYPTO = "CRYPTO"
VENUE_FX = "FX"

ALL_VENUES: tuple[str, ...] = (VENUE_NYSE, VENUE_NASDAQ, VENUE_CRYPTO, VENUE_FX)

# ISO MIC codes for the equity venues, consumed by ``exchange_calendars``.
_VENUE_TO_MIC: dict[str, str] = {
    VENUE_NYSE: "XNYS",
    VENUE_NASDAQ: "XNAS",
}

# Reason strings — kept short and stable.  ADR-0013 names ``weekend``,
# ``holiday:<name>``, and ``early_close`` as the canonical values.  We do not
# attempt to attach the holiday name (e.g., ``holiday:Christmas``) here because
# ``exchange_calendars`` returns Timestamps without the underlying rule name;
# inferring names by month/day would be brittle and is out of scope for #337.
REASON_WEEKEND = "weekend"
REASON_HOLIDAY = "holiday"

DEFAULT_BACKFILL_START = date(1950, 1, 1)


# ─── End-spec parsing (``+5y`` / ``-30d`` / ISO date) ─────────────────────

_RELATIVE_PATTERN = re.compile(r"^([+-])(\d+)([dwmy])$")


def parse_end_spec(spec: str, *, today: date | None = None) -> date:
    """Parse an end-date spec accepted by ``--end``.

    Accepts:

    * an ISO date (``YYYY-MM-DD``)
    * a relative offset (``+5y``, ``-30d``, ``+18m``, ``+12w``)

    Months are approximated as 30 days and years as 365 days — the calendar
    backfill is intentionally a coarse over-fill (a few extra days at the tail
    are harmless because every consumer filters by venue/date anyway).
    Avoiding ``dateutil.relativedelta`` keeps the package free of an extra
    runtime dependency.
    """
    if today is None:
        today = date.today()
    spec = spec.strip()
    if not spec:
        raise ValueError("end spec must not be empty")
    match = _RELATIVE_PATTERN.match(spec)
    if match:
        sign, n_str, unit = match.groups()
        n = int(n_str) * (1 if sign == "+" else -1)
        if unit == "d":
            days = n
        elif unit == "w":
            days = n * 7
        elif unit == "m":
            days = n * 30
        elif unit == "y":
            days = n * 365
        else:  # pragma: no cover - regex enforces unit set
            raise ValueError(f"unsupported unit in end spec: {spec!r}")
        return today + timedelta(days=days)
    # Fall through to ISO parse.
    try:
        return date.fromisoformat(spec)
    except ValueError as exc:
        raise ValueError(f"end spec is neither ISO date nor relative offset: {spec!r}") from exc


# ─── Date-range helpers ───────────────────────────────────────────────────


def _iter_dates(start: date, end: date) -> Iterable[date]:
    """Inclusive date iterator from ``start`` to ``end``."""
    if end < start:
        return
    cur = start
    one = timedelta(days=1)
    while cur <= end:
        yield cur
        cur += one


def _calendar_session_dates(
    venue: str, start: date, end: date, *, get_calendar: Callable[[str], Any] | None = None
) -> tuple[set[date], date, date]:
    """Return ``(session_dates, effective_start, effective_end)`` for an equity venue.

    Both endpoints are clamped to the library's available data window so callers
    never receive a ``DateOutOfBounds`` error regardless of how far out ``start``
    or ``end`` are. ``effective_start`` may be later than ``start`` (rolling
    ~20-year historical window); ``effective_end`` may be earlier than ``end``
    (library data horizon, currently ~2027).  Callers must iterate
    ``[effective_start, effective_end]`` — not the original arguments.

    ``get_calendar`` is dependency-injected for tests; production code passes
    ``None`` and we import the library lazily.
    """
    if venue not in _VENUE_TO_MIC:
        raise ValueError(f"venue {venue!r} is not driven by exchange_calendars")
    if get_calendar is None:  # pragma: no cover - exercised via tests with injection
        import exchange_calendars as ec  # type: ignore[import-not-found]

        get_calendar = ec.get_calendar
    cal = get_calendar(_VENUE_TO_MIC[venue])
    # exchange_calendars has a rolling ~20-year window. Clamp both endpoints so
    # we never raise DateOutOfBounds regardless of how far out --start/--end are.
    first_available = cal.first_session.date()
    last_available = cal.last_session.date()
    effective_start = max(start, first_available)
    if effective_start != start:
        _logger.info(
            "calendar start clamped from %s to %s for venue %s (exchange_calendars window)",
            start,
            effective_start,
            venue,
        )
    effective_end = min(end, last_available)
    if effective_end != end:
        _logger.warning(
            "calendar end clamped from %s to %s for venue %s (exchange_calendars data horizon)",
            end,
            effective_end,
            venue,
        )
    sessions = cal.sessions_in_range(effective_start.isoformat(), effective_end.isoformat())
    # ``sessions`` is a pandas DatetimeIndex.  Iterating it yields pandas
    # Timestamps which expose ``.date()``.  We flatten to native dates here
    # and discard the pandas object — no pandas types leak past this line.
    return {ts.date() for ts in sessions}, effective_start, effective_end


# ─── Row shaping ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalendarRow:
    """Typed view of a single ``trading_calendar`` row.

    Returned for callers that want a structured value; the public sync API
    returns ``list[dict]`` directly to match the existing Supabase writer
    contract.
    """

    date: date
    venue: str
    is_trading_day: bool
    reason: str | None


def _row_to_dict(row: CalendarRow) -> dict[str, Any]:
    return {
        "date": row.date.isoformat(),
        "venue": row.venue,
        "is_trading_day": row.is_trading_day,
        "reason": row.reason,
    }


def build_equity_rows(
    venue: str,
    start: date,
    end: date,
    *,
    get_calendar: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Build rows for an equity venue (``NYSE`` / ``NASDAQ``).

    Every date in ``[effective_start, effective_end]`` produces exactly one row, where
    ``effective_start`` is clamped to the calendar's earliest available session
    (see :func:`_calendar_session_dates`).  Sessions are tagged
    ``is_trading_day=True``; weekday non-sessions become ``reason='holiday'``;
    Sat/Sun become ``reason='weekend'``.
    """
    sessions, effective_start, effective_end = _calendar_session_dates(venue, start, end, get_calendar=get_calendar)
    rows: list[dict[str, Any]] = []
    for d in _iter_dates(effective_start, effective_end):
        if d in sessions:
            row = CalendarRow(d, venue, True, None)
        elif d.weekday() >= 5:  # Saturday=5, Sunday=6
            row = CalendarRow(d, venue, False, REASON_WEEKEND)
        else:
            row = CalendarRow(d, venue, False, REASON_HOLIDAY)
        rows.append(_row_to_dict(row))
    return rows


def build_crypto_rows(start: date, end: date) -> list[dict[str, Any]]:
    """Build rows for the synthetic 24x7 crypto calendar.

    Every date in ``[start, end]`` is a trading day with ``reason=None``.
    """
    return [_row_to_dict(CalendarRow(d, VENUE_CRYPTO, True, None)) for d in _iter_dates(start, end)]


def build_fx_rows(start: date, end: date) -> list[dict[str, Any]]:
    """Build rows for the synthetic 5-day-week FX calendar.

    Mon–Fri are ``is_trading_day=True``.  Sat+Sun are
    ``is_trading_day=False, reason='weekend'``.  Daily resolution does not
    capture the Sun-evening reopen — see ADR-0013.
    """
    rows: list[dict[str, Any]] = []
    for d in _iter_dates(start, end):
        if d.weekday() >= 5:
            row = CalendarRow(d, VENUE_FX, False, REASON_WEEKEND)
        else:
            row = CalendarRow(d, VENUE_FX, True, None)
        rows.append(_row_to_dict(row))
    return rows


def build_rows_for_venue(
    venue: str,
    start: date,
    end: date,
    *,
    get_calendar: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch to the per-venue row builder."""
    if venue in _VENUE_TO_MIC:
        return build_equity_rows(venue, start, end, get_calendar=get_calendar)
    if venue == VENUE_CRYPTO:
        return build_crypto_rows(start, end)
    if venue == VENUE_FX:
        return build_fx_rows(start, end)
    raise ValueError(f"unknown venue: {venue!r}")


def build_rows(
    venues: Iterable[str],
    start: date,
    end: date,
    *,
    get_calendar: Callable[[str], Any] | None = None,
) -> list[dict[str, Any]]:
    """Build the union of rows for ``venues`` between ``start`` and ``end``."""
    out: list[dict[str, Any]] = []
    for v in venues:
        out.extend(build_rows_for_venue(v, start, end, get_calendar=get_calendar))
    return out


# ─── Supabase upsert ──────────────────────────────────────────────────────


def upsert_trading_calendar(
    client: Any,
    rows: list[dict[str, Any]],
    *,
    chunk: int = 500,
) -> int:
    """Idempotent upsert of ``rows`` into ``trading_calendar``.

    ``on_conflict='date,venue'`` matches the table's composite primary key
    (migration 025).  Re-running the sync produces no duplicate rows.
    Returns the total number of rows written across all batches.
    """
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), chunk):
        batch = rows[i : i + chunk]
        client.table("trading_calendar").upsert(batch, on_conflict="date,venue").execute()
        total += len(batch)
    return total


__all__ = [
    "ALL_VENUES",
    "CalendarRow",
    "DEFAULT_BACKFILL_START",
    "REASON_HOLIDAY",
    "REASON_WEEKEND",
    "VENUE_CRYPTO",
    "VENUE_FX",
    "VENUE_NASDAQ",
    "VENUE_NYSE",
    "build_crypto_rows",
    "build_equity_rows",
    "build_fx_rows",
    "build_rows",
    "build_rows_for_venue",
    "parse_end_spec",
    "upsert_trading_calendar",
]
