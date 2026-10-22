"""Shared fixtures for the `digiquant prices` CLI tests.

The commands share the same patch targets and the same synthetic OHLCV and
indicator frames. They live here so each command module holds its own tests
and nothing else.
"""

from __future__ import annotations

from datetime import date, timedelta

import polars as pl
from digiquant.data.prices import TECHNICAL_COLUMNS

# Lazy-import patch targets (the CLI uses `from X import Y` inside the function body).
WRITER = "digiquant.data.prices.supabase_writer"
CACHE = "digiquant.data.prices.history_cache"
REFRESH = "digiquant.data.prices.refresh"


def fake_ohlcv(n: int = 30) -> pl.DataFrame:
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": dates,
            "open": [100.0] * n,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "close": [100.5] * n,
            "volume": [1_000_000.0] * n,
            "symbol": ["SPY"] * n,
        }
    )


def fake_ind(n: int) -> pl.DataFrame:
    return pl.DataFrame({c: [1.0] * n for c in TECHNICAL_COLUMNS})
