"""Internal helpers shared across the prices package.

Kept deliberately small — anything exported from here is a private helper
with no external callers.
"""

from __future__ import annotations

import math
from typing import Any


def safe_float(v: Any, decimals: int | None = 4) -> float | None:
    """Coerce a value to a finite Python float, or return ``None``.

    Returns ``None`` for ``NaN`` / ``±inf`` / non-numeric / coercion errors.
    If ``decimals`` is given, the result is rounded; pass ``None`` to skip
    rounding (e.g. for integer-typed volume columns).

    Single source of truth — previously duplicated in both
    ``supabase_writer.py`` and the legacy
    ``digiquant/scripts/atlas/compute-technicals.py`` shim.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, decimals) if decimals is not None else f


def safe_int(v: Any) -> int | None:
    """Coerce a value to an int, or return ``None``.

    Volume columns in Supabase are ``bigint``; postgrest rejects float payloads
    (``"127844500.0"``) with ``22P02`` invalid-syntax errors. yfinance sometimes
    returns volume as float (NaN-coercion, unadjusted closes, pandas extension
    dtypes), so we must cast before serializing.
    """
    f = safe_float(v, decimals=None)
    return int(f) if f is not None else None


__all__ = ["safe_float", "safe_int"]
