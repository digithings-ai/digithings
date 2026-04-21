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
    ``apps/digiquant-atlas/scripts/compute-technicals.py`` shim.
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, decimals) if decimals is not None else f


__all__ = ["safe_float"]
