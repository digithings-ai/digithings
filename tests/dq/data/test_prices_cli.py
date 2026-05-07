"""Regression tests for the `digiquant prices` CLI commands.

Covers the graceful-exit behaviour introduced in #558: upsert failures must
not propagate as a non-zero exit code, and the indicator row-count mismatch
must be handled without raising.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import polars as pl
import pytest
from click.testing import CliRunner

from digiquant.cli.prices import compute_technicals_cmd, fetch_quotes_cmd
from digiquant.data.prices import TECHNICAL_COLUMNS

pytestmark = pytest.mark.unit

# Lazy-import patch targets (the CLI uses `from X import Y` inside the function body).
_WRITER = "digiquant.data.prices.supabase_writer"
_CACHE = "digiquant.data.prices.history_cache"
_TECH = "digiquant.data.prices.technicals"
_VENUES = "digiquant.data.prices.ticker_venues"


# ─── helpers ──────────────────────────────────────────────────────────────


def _fake_ohlcv(n: int = 30) -> pl.DataFrame:
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


def _fake_ind(n: int) -> pl.DataFrame:
    return pl.DataFrame({c: [1.0] * n for c in TECHNICAL_COLUMNS})


# ─── fetch-quotes ─────────────────────────────────────────────────────────


def test_fetch_quotes_dry_run_exits_zero(tmp_path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        fetch_quotes_cmd, ["--tickers", "SPY", "--dry-run", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output


def test_fetch_quotes_upsert_failure_exits_zero() -> None:
    """A Supabase upsert error must not propagate as a non-zero exit code."""
    runner = CliRunner()

    with (
        patch(f"{_WRITER}.build_supabase_client", return_value=object()),
        patch(f"{_WRITER}.upsert_price_history", side_effect=RuntimeError("net failure")),
        patch(f"{_CACHE}.incremental_update", return_value={"SPY": _fake_ohlcv(3)}),
    ):
        result = runner.invoke(fetch_quotes_cmd, ["--tickers", "SPY", "--supabase"])

    assert result.exit_code == 0
    combined = (result.output or "") + (result.stderr or "")
    assert "warning" in combined.lower()


# ─── compute-technicals ───────────────────────────────────────────────────


def test_compute_technicals_upsert_failure_exits_zero(tmp_path) -> None:
    """A Supabase upsert error in compute-technicals must not propagate."""
    n = 30
    runner = CliRunner()

    with (
        patch(f"{_WRITER}.build_supabase_client", return_value=object()),
        patch(f"{_WRITER}.upsert_price_technicals", side_effect=RuntimeError("net failure")),
        patch(f"{_CACHE}.load_cached", return_value=_fake_ohlcv(n)),
        patch(f"{_TECH}.compute_indicators", return_value=_fake_ind(n)),
        patch(f"{_VENUES}.venue_for", return_value=None),
    ):
        result = runner.invoke(
            compute_technicals_cmd,
            ["--tickers", "SPY", "--supabase", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    combined = (result.output or "") + (result.stderr or "")
    assert "warning" in combined.lower()


def test_compute_technicals_row_mismatch_trims_both_sides(tmp_path) -> None:
    """When ind.height != df.height, both are trimmed to min length without raising."""
    n_df, n_ind = 40, 33  # must exceed MIN_BARS (30); ind shorter simulates warm-up drops
    runner = CliRunner()

    with (
        patch(f"{_WRITER}.build_supabase_client", return_value=None),
        patch(f"{_CACHE}.load_cached", return_value=_fake_ohlcv(n_df)),
        patch(f"{_TECH}.compute_indicators", return_value=_fake_ind(n_ind)),
        patch(f"{_VENUES}.venue_for", return_value=None),
    ):
        result = runner.invoke(
            compute_technicals_cmd,
            ["--tickers", "SPY", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    # n_ind rows should be reported, not n_df
    assert f"{n_ind:4d} indicator rows" in result.output
