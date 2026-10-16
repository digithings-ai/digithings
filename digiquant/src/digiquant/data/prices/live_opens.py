"""Same-day opens via a live fetch (yfinance) — #4053 Task 1.

Sealed dates read the R2 generation; same-day opens have no sealed R2 bar yet,
so the at-open job fetches today's open live instead of reading the retired
intraday Supabase writer. Never raises: any failure is ``None`` (single) or a
skip (batch) so the morning job degrades to ``data_unavailable`` per symbol.
"""

from __future__ import annotations

import math
from datetime import date as _date
from datetime import timedelta as _timedelta
from typing import Any


def _first_scalar(value: Any) -> Any:
    """Unwrap one-or-two-deep ``.iloc[0]`` pandas layers to a scalar."""
    for _ in range(3):
        iloc = getattr(value, "iloc", None)
        if iloc is None:
            break
        try:
            value = iloc[0]
        except Exception:
            break
    return value


def fetch_live_open(ticker: str, d: str) -> float | None:
    """Today's open for ticker via a live fetch (same-day opens have no sealed R2 bar)."""
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except Exception:
        return None
    try:
        # yfinance takes at most two of (period, start, end), and end is
        # exclusive — so the single daily bar for d is [d, d+1). (start=d with
        # end=d returns nothing; adding period="1d" on top is rejected.)
        day = _date.fromisoformat(str(d)[:10])
        end = (day + _timedelta(days=1)).isoformat()
        frame = yf.download(ticker, start=day.isoformat(), end=end, progress=False)
        o = _first_scalar(frame["Open"])
    except Exception:
        return None
    try:
        v = float(o) if o is not None else None
    except (TypeError, ValueError):
        return None
    if v is None or not math.isfinite(v) or v <= 0:
        return None
    return v


def fetch_live_opens(tickers: list[str], d: str) -> dict[str, float]:
    """Batch wrapper: ``{TICKER: open}`` skipping any ticker that fails."""
    out: dict[str, float] = {}
    for ticker in sorted(set(tickers)):
        try:
            v = fetch_live_open(ticker, d)
        except Exception:
            continue
        if v is not None:
            out[str(ticker).upper()] = v
    return out
