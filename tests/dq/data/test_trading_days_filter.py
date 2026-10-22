"""Unit tests for trading-calendar date alignment in the prices pipeline."""

from __future__ import annotations

import logging
from datetime import date, datetime

import polars as pl
import pytest
from digiquant.data.prices._utils import filter_rows_by_trading_days
from digiquant.data.prices.technicals import compute_indicators


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


def _ohlcv_frame(dates: list[date]) -> pl.DataFrame:
    """Minimal OHLCV frame for the given dates (values don't matter for filter tests)."""
    n = len(dates)
    close = [100.0 + i for i in range(n)]
    open_ = [c - 0.5 for c in close]
    high = [c + 1.0 for c in close]
    low = [c - 1.0 for c in close]
    volume = [1_000_000 + i * 100 for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


@pytest.mark.unit
def test_trading_days_filter_drops_non_trading_rows() -> None:
    """Rows outside trading_days are excluded before computation."""
    # 2024-01-02 = Tuesday (trading), 2024-01-06 = Saturday, 2024-01-07 = Sunday
    dates = [date(2024, 1, 2), date(2024, 1, 6), date(2024, 1, 7)]
    df = _ohlcv_frame(dates)
    trading_days = pl.Series("trading_days", [date(2024, 1, 2)])

    result = compute_indicators(df, trading_days=trading_days)
    assert result.height == 1


@pytest.mark.unit
def test_trading_days_filter_keeps_all_matching_rows() -> None:
    """All rows in trading_days are retained."""
    dates = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)]
    df = _ohlcv_frame(dates)
    # All four days are trading days
    trading_days = pl.Series("trading_days", dates)

    result = compute_indicators(df, trading_days=trading_days)
    assert result.height == 4


@pytest.mark.unit
def test_empty_trading_days_uses_all_rows(caplog) -> None:
    """Empty trading_days logs a warning and retains all rows (graceful fallback)."""
    dates = [date(2024, 1, 2), date(2024, 1, 3)]
    df = _ohlcv_frame(dates)
    empty_filter = pl.Series("trading_days", [], dtype=pl.Date)

    with caplog.at_level(logging.WARNING, logger="digiquant.data.prices.technicals"):
        result = compute_indicators(df, trading_days=empty_filter)

    assert result.height == 2
    assert "trading_days filter is empty" in caplog.text


@pytest.mark.unit
def test_trading_days_no_timestamp_column_uses_all_rows(caplog) -> None:
    """If the DataFrame has no 'timestamp' column, filter is skipped with a warning."""
    # Build a frame without a timestamp column (only OHLCV)
    df = pl.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000, 2000],
        }
    )
    trading_days = pl.Series("trading_days", [date(2024, 1, 2)])

    with caplog.at_level(logging.WARNING, logger="digiquant.data.prices.technicals"):
        result = compute_indicators(df, trading_days=trading_days)

    assert result.height == 2
    assert "no 'timestamp' column" in caplog.text
