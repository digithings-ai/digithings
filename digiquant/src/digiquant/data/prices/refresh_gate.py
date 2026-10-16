"""Staleness gate for the R2 market-data cache (#3780, Task 6).

Refuses a manifest whose seal is more than ``bound_trading_days`` trading
days behind the run date. Pure date math so the pipeline (Task 7) and the
refresh cron share one definition: pass an explicit trading-day calendar
(Supabase ``trading_calendar`` rows, fetched by the caller) or fall back to
Mon-Fri counting.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


def _to_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def trading_days_between(
    start: str | date,
    end: str | date,
    trading_days: Iterable[str | date] | None = None,
) -> int:
    """Count trading days in ``(start, end]`` (seal-exclusive, run-inclusive).

    With ``trading_days`` given, counts the calendar entries in range (covers
    exchange holidays); otherwise counts Mon-Fri weekdays. A run date at or
    before the seal is fresh (0 open days), never negative.
    """
    start_d = _to_date(start)
    end_d = _to_date(end)
    if end_d <= start_d:
        return 0
    if trading_days is not None:
        days = {_to_date(d) for d in trading_days}
        return sum(1 for d in days if start_d < d <= end_d)
    count = 0
    day = start_d + timedelta(days=1)
    while day <= end_d:
        if day.weekday() < 5:
            count += 1
        day += timedelta(days=1)
    return count


def staleness_gate(
    manifest_as_of: str | date,
    run_date: str | date,
    bound_trading_days: int = 5,
    trading_days: Iterable[str | date] | None = None,
) -> dict[str, object]:
    """``{"ok", "stale_days"}``: fresh iff open trading days <= bound."""
    open_days = trading_days_between(manifest_as_of, run_date, trading_days)
    return {"ok": open_days <= bound_trading_days, "stale_days": open_days}


__all__ = ["staleness_gate", "trading_days_between"]
