"""The honest denominator (DIG-428, L1 of DIG-474; analyzer records in DIG-937).

One function decides which points of a returns/PnL series count toward a sample
size, so a rate, a chart and a guard can never disagree about N. Non-finite and
null values are dropped: a NaN row would change the denominator. Stdlib only.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any  # score:allow untyped any — duck-typed series boundary

_NS_PER_SECOND = 1_000_000_000


def _finite_or_none(value: Any) -> float | None:
    """value as a finite float, or None if null, non-numeric or non-finite."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _record_date(key: Any, ts_event: Any) -> str | None:
    """``YYYY-MM-DD`` for a record's nanosecond timestamp, or None when it has none.

    ``ts_event`` is Unix-epoch nanoseconds on every build that carries one, so the
    date is derived from it. Truncating instead (``str(ns)[:10]``, as the pandas
    shape does) would yield the first ten digits of the epoch, not a date.
    """
    stamp = ts_event if isinstance(ts_event, int) and not isinstance(ts_event, bool) else None
    if stamp is None and isinstance(key, int) and not isinstance(key, bool):
        stamp = key
    if stamp is None:
        return None
    try:
        moment = datetime.fromtimestamp(stamp / _NS_PER_SECOND, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.strftime("%Y-%m-%d")


def _records_from(rows: list[Any]) -> list[tuple[Any, Any, Any]] | None:
    """Reinterpret a list of rows as ``(key, ts_event, value)`` records, or None.

    The pyo3 ``PortfolioAnalyzer`` does not return a series. ``realized_pnls()``
    was ``dict {position_id: pnl}`` through 1.228.0 and became
    ``list[(position_id, ts_event, pnl)]`` on 1.230.0; ``returns()`` is a
    ``{ts_ns: return}`` dict. All of them reach this function unconverted from
    ``nautilus_runner.py``, so they are recognised here, before the series probes.
    The value is the last column, and a 2-column row is read as ``(key, value)``.
    """
    if not rows or not isinstance(rows[0], (tuple, list)) or len(rows[0]) not in (2, 3):
        return None
    return [(row[0], row[1] if len(row) == 3 else None, row[-1]) for row in rows]


def _from_records(records: list[tuple[Any, Any, Any]]) -> tuple[list[str], list[float]] | None:
    """Collapse records to one row per distinct ``(position_id, ts_event)``.

    Last occurrence wins, mirroring the engine's own bookkeeping. That is not a
    guess between builds: 1.223/1.228 key the whole mapping by position id, and
    1.230.0 already folds an ``add_trade`` into a later ``record_trade`` for the
    same pair, so a repeated pair only survives to this point when
    ``record_trade`` was called twice for it — and the return value carries no
    provenance saying which of the two was the recorded one. Taking the later row
    keeps N equal to the number of round trips and never counts one twice.
    """
    collapsed: dict[tuple[Any, Any], Any] = {}
    for key, ts_event, value in records:
        collapsed[(key, ts_event)] = value

    kept: list[str] = []
    values: list[float] = []
    for (key, ts_event), value in collapsed.items():
        number = _finite_or_none(value)
        if number is None:
            continue
        kept.append(_record_date(key, ts_event) or str(len(kept)))
        values.append(number)

    return (kept, values) if values else None


def normalize_series(series: Any) -> tuple[list[str], list[float]] | None:
    """Normalise a PnL/returns series or analyzer records to (dates, finite floats).

    Two input families:

    1. **Analyzer records** — what the pyo3 analyzer actually hands back: the
       ``{position_id: pnl}`` dict, the 1.230.0 ``(position_id, ts_event, pnl)``
       rows, and the ``{ts_ns: return}`` mapping. Collapsed to one row per
       distinct ``(position_id, ts_event)``, last occurrence winning, so N counts
       closed round trips and is never ``None`` merely because the shape was not
       recognised.
    2. **Series** — ``.values`` + ``.index`` (pandas shape, read only — pandas is
       never imported), then ``.to_list()`` (polars), then ``.tolist()``, then a
       plain iterable. Dates are ``str(index)[:10]`` for the pandas shape,
       sequential position strings otherwise.

    An object offering ``.values``/``.index``/``.to_list()``/``.tolist()`` has
    declared itself a series by protocol, so only a mapping or a bare iterable is
    probed for records.

    Non-finite and null values are dropped in both. Returns None for None, an
    empty result, or any failure. No polars, no pandas, no pyarrow. An iterable
    is consumed exactly once.
    """
    if series is None:
        return None

    try:
        if isinstance(series, dict):
            return _from_records([(key, None, value) for key, value in series.items()])

        dates: list[str] | None = None
        records: list[tuple[Any, Any, Any]] | None = None
        if hasattr(series, "values") and hasattr(series, "index"):
            raw_values = list(series.values)
            dates = [str(d)[:10] for d in series.index]
        elif hasattr(series, "to_list"):
            raw_values = series.to_list()
        elif hasattr(series, "tolist"):
            raw_values = series.tolist()
        else:
            raw_values = list(series)
            records = _records_from(raw_values)

        if records is not None:
            return _from_records(records)
        if dates is None:
            dates = [str(i) for i in range(len(raw_values))]

        kept: list[str] = []
        values: list[float] = []
        for date, raw in zip(dates, raw_values, strict=True):
            number = _finite_or_none(raw)
            if number is not None:
                kept.append(date)
                values.append(number)

        return (kept, values) if values else None
    except Exception:
        return None
