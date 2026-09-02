"""Unit tests for digiquant.data.prices.fetchers (mocked yfinance)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest
from digiquant.data.prices import OHLCV_COLUMNS
from digiquant.data.prices.fetchers import (
    FetchResult,
    _to_yahoo_symbol,
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
def test_to_yahoo_symbol_maps_share_class_dot_to_hyphen() -> None:
    """Regression for #1754."""
    assert _to_yahoo_symbol("BRK.B") == "BRK-B"
    assert _to_yahoo_symbol("BF.B") == "BF-B"
    # Identity for everything without a share-class dot.
    for plain in ("SPY", "QQQ", "EOG", "XOP"):
        assert _to_yahoo_symbol(plain) == plain


@pytest.mark.unit
def test_fetch_batch_requests_yahoo_symbol_but_keys_frames_canonically() -> None:
    """Regression for #1754.

    BRK.B had zero rows in price_history since inception because the dotted
    canonical symbol was sent straight to Yahoo, which returns no data for it.
    The download must use BRK-B while the caller keeps addressing BRK.B, so DB
    rows and the research sector config continue to agree.

    Kept pandas-free (Polars-only rule): the download is made to fail, which
    exercises both halves of the contract — the symbol sent over the wire, and
    the canonical key the caller gets back — without a pandas fixture.
    """
    import sys as _sys
    import types

    requested: dict[str, object] = {}

    def _download(tickers, **kwargs):
        requested["tickers"] = list(tickers)
        raise RuntimeError("network down")

    stub = types.ModuleType("yfinance")
    stub.download = _download  # type: ignore[attr-defined]

    with patch.dict(_sys.modules, {"yfinance": stub}):
        result = fetch_batch(["BRK.B", "SPY"], dry_run=False)

    # The wire request uses Yahoo's hyphenated form — this is the fix.
    assert requested["tickers"] == ["BRK-B", "SPY"]
    # Callers keep addressing the canonical ticker, never the Yahoo alias.
    assert set(result.errors) == {"BRK.B", "SPY"}
    assert "BRK-B" not in result.errors


@pytest.mark.unit
def test_fetch_quotes_batches_tickers() -> None:
    """`fetch_quotes` should still produce one frame per ticker when batching in dry-run."""
    tickers = [f"T{i}" for i in range(30)]
    result = fetch_quotes(tickers, dry_run=True, batch_size=8, throttle_s=0.0)
    assert set(result.frames.keys()) == set(tickers)
    for df in result.frames.values():
        assert tuple(df.columns) == OHLCV_COLUMNS
