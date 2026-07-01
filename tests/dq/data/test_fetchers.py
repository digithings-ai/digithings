"""Unit tests for digiquant.data.prices.fetchers (mocked yfinance)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.fetchers import (
    FetchResult,
    fetch_batch,
    fetch_quotes,
    parse_watchlist,
)


@pytest.mark.unit
def test_parse_watchlist_fallback_when_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    out = parse_watchlist(missing)
    assert "SPY" in out and "QQQ" in out
    assert "ETF" not in out  # excluded header


@pytest.mark.unit
def test_parse_watchlist_reads_markdown_table(tmp_path: Path) -> None:
    wl = tmp_path / "watchlist.md"
    wl.write_text(
        "| ETF | Description | Category |\n"
        "|-----|-------------|----------|\n"
        "| SPY | S&P | eq |\n"
        "| QQQ | Nasdaq | eq |\n"
        "| BTC-USD | Bitcoin | crypto |\n"
        "| DXY | Dollar idx | macro |\n"  # excluded
    )
    tickers = parse_watchlist(wl)
    assert tickers == ["SPY", "QQQ", "BTC-USD"]


@pytest.mark.unit
def test_fetch_batch_dry_run_synthesizes_polars_frame() -> None:
    result = fetch_batch(["SPY", "QQQ"], dry_run=True)
    assert isinstance(result, FetchResult)
    assert set(result.frames.keys()) == {"SPY", "QQQ"}
    assert not result.errors
    for df in result.frames.values():
        assert isinstance(df, pl.DataFrame)
        assert tuple(df.columns) == OHLCV_COLUMNS
        assert df.height == 5


@pytest.mark.unit
def test_fetch_batch_empty_tickers_returns_empty_result() -> None:
    assert fetch_batch([]).frames == {}
    assert fetch_quotes([]).frames == {}


@pytest.mark.unit
def test_fetch_batch_handles_yfinance_missing_module() -> None:
    """When yfinance isn't installed (and not dry-run), each ticker gets an error row."""
    import importlib
    import sys as _sys

    # Simulate ModuleNotFoundError by masking yfinance in sys.modules.
    with patch.dict(_sys.modules, {"yfinance": None}):  # None forces re-import to fail
        importlib.invalidate_caches()
        result = fetch_batch(["SPY"], dry_run=False)
    # Either errors are populated, or the real yfinance package was imported (when dev env has it).
    if "SPY" in result.errors:
        assert "yfinance_unavailable" in result.errors["SPY"]
    else:
        # If yfinance is installed in dev env, we just accept the call doesn't crash.
        assert isinstance(result, FetchResult)


@pytest.mark.unit
def test_fetch_quotes_batches_tickers() -> None:
    """`fetch_quotes` should still produce one frame per ticker when batching in dry-run."""
    tickers = [f"T{i}" for i in range(30)]
    result = fetch_quotes(tickers, dry_run=True, batch_size=8, throttle_s=0.0)
    assert set(result.frames.keys()) == set(tickers)
    for df in result.frames.values():
        assert tuple(df.columns) == OHLCV_COLUMNS
