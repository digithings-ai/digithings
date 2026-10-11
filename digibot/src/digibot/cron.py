"""Standard 5-field cron expression parsing and next-fire calculation.

Supported forms per field: ``*``, ``N``, ``A-B``, ``*/S``, ``A-B/S``, and
comma-separated lists of those. Day-of-week accepts ``0``–``7`` (``0`` and ``7``
are Sunday) plus ``SUN``–``SAT``. Month accepts ``1``–``12`` plus ``JAN``–``DEC``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_MONTH_NAMES = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}
_DOW_NAMES = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}


class CronParseError(ValueError):
    """Structured cron parse failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True, slots=True)
class CronExpression:
    """Parsed 5-field cron expression."""

    minute: frozenset[int]
    hour: frozenset[int]
    day_of_month: frozenset[int]
    month: frozenset[int]
    day_of_week: frozenset[int]
    source: str

    def matches(self, when: datetime) -> bool:
        """Return True if *when* (UTC-normalized) matches this expression."""
        instant = _ensure_utc(when).replace(second=0, microsecond=0)
        if instant.minute not in self.minute:
            return False
        if instant.hour not in self.hour:
            return False
        if instant.month not in self.month:
            return False
        dow = instant.weekday()  # Mon=0 … Sun=6 in datetime
        cron_dow = (dow + 1) % 7  # convert to Sun=0 … Sat=6
        dom_ok = instant.day in self.day_of_month
        dow_ok = cron_dow in self.day_of_week
        # Standard cron: when both DOM and DOW are constrained, either may match.
        dom_star = len(self.day_of_month) == 31
        dow_star = len(self.day_of_week) == 7
        if dom_star and dow_star:
            return True
        if dom_star:
            return dow_ok
        if dow_star:
            return dom_ok
        return dom_ok or dow_ok


def parse_cron(expr: str) -> CronExpression:
    """Parse a standard 5-field cron expression."""
    parts = expr.strip().split()
    if len(parts) != 5:
        raise CronParseError(
            "cron_invalid",
            f"expected 5 fields (minute hour dom month dow), got {len(parts)}: {expr!r}",
        )
    minute, hour, dom, month, dow = parts
    return CronExpression(
        minute=frozenset(_expand_field(minute, 0, 59, names=None)),
        hour=frozenset(_expand_field(hour, 0, 23, names=None)),
        day_of_month=frozenset(_expand_field(dom, 1, 31, names=None)),
        month=frozenset(_expand_field(month, 1, 12, names=_MONTH_NAMES)),
        day_of_week=frozenset(_expand_dow(dow)),
        source=expr.strip(),
    )


def next_cron_time(expr: str | CronExpression, after: datetime) -> datetime:
    """Return the next UTC fire time strictly after *after*."""
    cron = expr if isinstance(expr, CronExpression) else parse_cron(expr)
    cursor = _ensure_utc(after).replace(second=0, microsecond=0) + timedelta(minutes=1)
    # Bound search: 4 years of minute ticks is enough for any valid expression.
    limit = cursor + timedelta(days=366 * 4)
    while cursor <= limit:
        if cron.matches(cursor):
            return cursor
        cursor += timedelta(minutes=1)
    raise CronParseError(
        "cron_no_next",
        f"no next fire time within 4 years for {cron.source!r}",
    )


def _expand_dow(spec: str) -> set[int]:
    values = _expand_field(spec, 0, 7, names=_DOW_NAMES)
    # Normalize 7 → 0 (Sunday).
    return {(0 if v == 7 else v) for v in values}


def _expand_field(
    spec: str,
    lo: int,
    hi: int,
    *,
    names: dict[str, int] | None,
) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            raise CronParseError("cron_invalid", f"empty field token in {spec!r}")
        head, _, raw_step = token.partition("/")
        step = int(raw_step) if raw_step else 1
        if step < 1:
            raise CronParseError("cron_invalid", f"step must be >= 1 in {token!r}")
        if head == "*":
            start, end = lo, hi
        elif "-" in head:
            first_s, _, last_s = head.partition("-")
            start = _parse_atom(first_s, lo, hi, names=names)
            end = _parse_atom(last_s, lo, hi, names=names)
            if start > end:
                raise CronParseError("cron_invalid", f"range start > end in {token!r}")
        else:
            start = end = _parse_atom(head, lo, hi, names=names)
        values.update(range(start, end + 1, step))
    if not values:
        raise CronParseError("cron_invalid", f"field {spec!r} expanded to empty set")
    return values


def _parse_atom(
    raw: str,
    lo: int,
    hi: int,
    *,
    names: dict[str, int] | None,
) -> int:
    token = raw.strip().upper()
    if names and token in names:
        value = names[token]
    else:
        try:
            value = int(token)
        except ValueError as exc:
            raise CronParseError("cron_invalid", f"invalid cron atom {raw!r}") from exc
    if not (lo <= value <= hi):
        raise CronParseError(
            "cron_invalid",
            f"value {value} out of range [{lo}, {hi}] for atom {raw!r}",
        )
    return value


def _ensure_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)
