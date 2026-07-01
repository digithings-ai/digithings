"""Unit tests for trading-calendar date alignment in the prices pipeline."""

from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest

from digiquant.data.prices._utils import filter_rows_by_trading_days


@pytest.mark.unit
def test_filter_rows_by_trading_days_datetime_timestamp() -> None:
    """Datetime OHLCV timestamps match pl.Date trading_days without raising."""
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 2, 16, 0),
                datetime(2024, 1, 3, 16, 0),
                datetime(2024, 1, 6, 16, 0),
            ],
            "close": [1.0, 2.0, 3.0],
        }
    )
    trading_days = pl.Series("trading_days", [date(2024, 1, 2), date(2024, 1, 3)])
    out = filter_rows_by_trading_days(df, trading_days)
    assert out.height == 2
    assert out["close"].to_list() == [1.0, 2.0]
