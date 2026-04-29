"""yfinance adapter — Polars-only, no pandas on the public surface.

Ported from ``digiquant/scripts/atlas/fetch-quotes.py``.

yfinance itself returns a ``pandas.DataFrame``. We treat that as a private
implementation detail and immediately convert to Polars via the canonical
``OHLCV_COLUMNS`` contract. ``fetch_batch`` and ``fetch_quotes`` never leak a
pandas object to callers.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from digiquant.data.prices import OHLCV_COLUMNS

_WATCHLIST_RE = re.compile(r"^\|\s*([A-Z][A-Z0-9]{1,9}(?:-[A-Z]{2,4})?)\s*\|", re.MULTILINE)
_EXCLUDE_TICKERS = frozenset({"ETF", "DXY", "VIX"})

# Single source of truth for the ETF rotation baseline universe, used when
# ``watchlist.md`` is missing. Kept in sync with Atlas's
# ``config/watchlist.md`` snapshot at the time of the Wave-1-E migration.
_FALLBACK_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLI",
    "XLRE",
    "XLU",
    "XLY",
    "XLP",
    "XLB",
    "XLC",
    "TLT",
    "GLD",
    "IAU",
    "SLV",
    "USO",
    "DBO",
    "IBIT",
    "FBTC",
    "BIL",
    "SHY",
    "EFA",
    "EEM",
    "FXI",
    "EWJ",
    "EWZ",
)


@dataclass(frozen=True)
class FetchResult:
    """Result of a yfinance fetch: ticker → Polars OHLCV DataFrame."""

    frames: dict[str, pl.DataFrame]
    errors: dict[str, str]


def parse_watchlist(path: str | Path) -> list[str]:
    """Extract unique tickers from a watchlist markdown table.

    Falls back to a baked-in ETF universe if the file is missing. Tickers in
    ``{"ETF", "DXY", "VIX"}`` are excluded (header rows / macro-only entries).
    """
    p = Path(path)
    if not p.exists():
        return list(_FALLBACK_UNIVERSE)
    text = p.read_text(encoding="utf-8")
    seen: set[str] = set()
    out: list[str] = []
    for ticker in _WATCHLIST_RE.findall(text):
        if ticker in _EXCLUDE_TICKERS or ticker in seen:
            continue
        seen.add(ticker)
        out.append(ticker)
    return out


def _pandas_to_polars(pdf, ticker: str) -> pl.DataFrame:
    """Convert a yfinance pandas frame (Date-indexed) into the canonical Polars
    OHLCV layout. Keeps a ``timestamp`` column instead of an index."""
    # Defer pandas import — fetchers is the only module that touches pandas,
    # and only at the conversion boundary.
    import pandas as pd  # type: ignore[import-not-found]

    if pdf is None or getattr(pdf, "empty", True):
        return pl.DataFrame({c: pl.Series(c, [], dtype=pl.Float64) for c in OHLCV_COLUMNS})

    pdf = pdf.copy()
    pdf.columns = [str(c).lower() for c in pdf.columns]
    pdf = pdf.reset_index().rename(columns={"date": "timestamp", "Date": "timestamp"})
    # Strip timezone to a naive daily date column (yfinance returns tz-aware).
    # Parse with utc=True to coerce all inputs (tz-aware, tz-naive, string)
    # to a UTC-aware DatetimeIndex, then drop the tz in a single call.
    ts = pd.to_datetime(pdf["timestamp"], utc=True).dt.tz_convert(None)
    pdf["timestamp"] = ts

    # Ensure all 5 OHLCV cols present
    for col in ("open", "high", "low", "close", "volume"):
        if col not in pdf.columns:
            pdf[col] = float("nan")

    pdf["symbol"] = ticker
    pdf = pdf[[*OHLCV_COLUMNS]]
    return pl.from_pandas(pdf)


def fetch_batch(
    tickers: list[str],
    *,
    period: str = "3mo",
    start: str | None = None,
    end: str | None = None,
    dry_run: bool = False,
) -> FetchResult:
    """Download OHLCV for a batch of tickers via yfinance.

    Parameters
    ----------
    tickers : list[str]
    period : str
        yfinance period (e.g. ``"3mo"``, ``"2y"``). Ignored if ``start`` given.
    start, end : str | None
        ISO date range (``end`` exclusive, yfinance convention).
    dry_run : bool
        If True, synthesize a deterministic 5-row fixture per ticker and skip
        the network call entirely. Used by CLI ``--dry-run`` and tests.
    """
    if not tickers:
        return FetchResult(frames={}, errors={})

    if dry_run:
        return FetchResult(frames={t: _synthetic_ohlcv(t, rows=5) for t in tickers}, errors={})

    # Lazy import — yfinance is an optional dep.
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError as e:
        return FetchResult(frames={}, errors={t: f"yfinance_unavailable: {e}" for t in tickers})

    import pandas as pd  # type: ignore[import-not-found]

    kwargs: dict = {"progress": False, "threads": True}
    if start:
        kwargs["start"] = start
        if end:
            kwargs["end"] = end
    else:
        kwargs["period"] = period

    try:
        raw = yf.download(tickers, **kwargs)
    except Exception as e:  # yfinance is brittle; treat transport errors as per-ticker
        return FetchResult(frames={}, errors={t: f"batch_download_failed: {e}" for t in tickers})

    frames: dict[str, pl.DataFrame] = {}
    errors: dict[str, str] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for ticker in tickers:
            try:
                pdf = raw.xs(ticker, level=1, axis=1).dropna(how="all")
                frames[ticker] = _pandas_to_polars(pdf, ticker)
            except KeyError:
                errors[ticker] = "no_data"
    else:
        ticker = tickers[0]
        pdf = raw.dropna(how="all")
        frames[ticker] = _pandas_to_polars(pdf, ticker)

    return FetchResult(frames=frames, errors=errors)


def fetch_quotes(
    tickers: list[str],
    *,
    period: str = "3mo",
    dry_run: bool = False,
    batch_size: int = 25,
    throttle_s: float = 0.5,
) -> FetchResult:
    """Chunk ``tickers`` into batches of ``batch_size`` and call :func:`fetch_batch`.

    Returns a merged :class:`FetchResult`.
    """
    if not tickers:
        return FetchResult(frames={}, errors={})
    merged_frames: dict[str, pl.DataFrame] = {}
    merged_errors: dict[str, str] = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        result = fetch_batch(batch, period=period, dry_run=dry_run)
        merged_frames.update(result.frames)
        merged_errors.update(result.errors)
        if i + batch_size < len(tickers) and not dry_run:
            time.sleep(throttle_s)
    return FetchResult(frames=merged_frames, errors=merged_errors)


def _synthetic_ohlcv(symbol: str, *, rows: int = 5, start: str = "2026-01-02") -> pl.DataFrame:
    """Deterministic OHLCV fixture for ``--dry-run`` / tests. No network."""
    base = 100.0 + (sum(ord(c) for c in symbol) % 50)
    import datetime as _dt

    start_d = _dt.date.fromisoformat(start)
    timestamps = [start_d + _dt.timedelta(days=i) for i in range(rows)]
    opens = [base + (i % 10) - 5.0 for i in range(rows)]
    highs = [opens[i] + 1.0 for i in range(rows)]
    lows = [opens[i] - 1.0 for i in range(rows)]
    closes = [(highs[i] + lows[i]) / 2 for i in range(rows)]
    vols = [1000.0 + i * 10 for i in range(rows)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": vols,
            "symbol": [symbol] * rows,
        }
    )


__all__ = [
    "FetchResult",
    "OHLCV_COLUMNS",
    "fetch_batch",
    "fetch_quotes",
    "parse_watchlist",
]
