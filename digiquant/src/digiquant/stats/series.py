"""The honest denominator (DIG-428, L1 of DIG-474).

One function decides which points of a returns/PnL series count toward a sample
size, so a rate, a chart and a guard can never disagree about N. Non-finite and
null values are dropped: a NaN row would change the denominator. Stdlib only.
"""

from __future__ import annotations

import math
from typing import Any  # score:allow untyped any — duck-typed series boundary


def _finite_or_none(value: Any) -> float | None:
    """value as a finite float, or None if null, non-numeric or non-finite."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize_series(series: Any) -> tuple[list[str], list[float]] | None:
    """Normalise a PnL/returns series to (dates, finite float values).

    Duck-typing order matches the historical ``_extract_frame``: ``.values`` +
    ``.index`` (pandas shape, read only — pandas is never imported), then
    ``.to_list()`` (polars), then ``.tolist()``, then a plain iterable. Dates
    are ``str(index)[:10]`` for the pandas shape, sequential position strings
    otherwise. Returns None for None, an empty result, or any failure. No
    polars, no pandas, no pyarrow. An iterable is consumed exactly once.
    """
    if series is None:
        return None

    try:
        dates: list[str] | None = None
        if hasattr(series, "values") and hasattr(series, "index"):
            raw_values = list(series.values)
            dates = [str(d)[:10] for d in series.index]
        elif hasattr(series, "to_list"):
            raw_values = series.to_list()
        elif hasattr(series, "tolist"):
            raw_values = series.tolist()
        else:
            raw_values = list(series)
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
