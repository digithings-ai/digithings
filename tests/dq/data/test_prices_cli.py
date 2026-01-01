"""Regression tests for the `digiquant prices` technicals commands.

`compute-technicals` and `recompute-technicals`: the graceful-exit behaviour
introduced in #558 (an upsert failure must not propagate as a non-zero exit
code), the indicator row-count mismatch handled without raising, and the
recompute window and counters (#1752).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import polars as pl
import pytest
from click.testing import CliRunner
from digiquant.cli.prices import compute_technicals_cmd, recompute_technicals_cmd
from digiquant.data.prices.refresh import RefreshResult

from tests.dq.data.prices_cli_support import CACHE, REFRESH, WRITER, fake_ind, fake_ohlcv

pytestmark = pytest.mark.unit

# Lazy-import patch targets (the CLI uses `from X import Y` inside the function body).
_TECH = "digiquant.data.prices.technicals"
_VENUES = "digiquant.data.prices.ticker_venues"

# ─── compute-technicals ───────────────────────────────────────────────────


def test_compute_technicals_upsert_failure_exits_zero(tmp_path) -> None:
    """A Supabase upsert error in compute-technicals must not propagate."""
    n = 30
    runner = CliRunner()

    with (
        patch(f"{WRITER}.build_supabase_client", return_value=object()),
        patch(f"{WRITER}.upsert_price_technicals", side_effect=RuntimeError("net failure")),
        patch(f"{CACHE}.load_cached", return_value=fake_ohlcv(n)),
        patch(f"{_TECH}.compute_indicators", return_value=fake_ind(n)),
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
        patch(f"{WRITER}.build_supabase_client", return_value=None),
        patch(f"{CACHE}.load_cached", return_value=fake_ohlcv(n_df)),
        patch(f"{_TECH}.compute_indicators", return_value=fake_ind(n_ind)),
        patch(f"{_VENUES}.venue_for", return_value=None),
    ):
        result = runner.invoke(
            compute_technicals_cmd,
            ["--tickers", "SPY", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    # n_ind rows should be reported, not n_df
    assert f"{n_ind:4d} indicator rows" in result.output


def test_compute_technicals_casts_datetime_trading_days_to_date(tmp_path) -> None:
    """Datetime trading_days from Supabase are cast to Date before filtering."""
    n = 40
    runner = CliRunner()
    trading_days_dt = pl.Series([date(2025, 1, 1)]).cast(pl.Datetime)

    with (
        patch(f"{WRITER}.build_supabase_client", return_value=object()),
        patch(f"{WRITER}.upsert_price_technicals", return_value=Mock(rows=n)),
        patch(f"{CACHE}.load_cached", return_value=fake_ohlcv(n)),
        patch(f"{_TECH}.compute_indicators", return_value=fake_ind(n)),
        patch(f"{_VENUES}.venue_for", return_value="NYSE"),
        patch("digiquant.cli.prices._fetch_trading_days", return_value=trading_days_dt),
    ):
        result = runner.invoke(
            compute_technicals_cmd,
            ["--tickers", "SPY", "--supabase", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert f"{n} rows into price_technicals" in result.output


def test_compute_technicals_rejects_a_blank_ticker_list(tmp_path) -> None:
    for tickers in (",", " ", " , "):
        result = CliRunner().invoke(
            compute_technicals_cmd,
            ["--tickers", tickers, "--dry-run", "--cache-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "did not contain any symbols" in result.output


# ─── recompute-technicals (#1752) ─────────────────────────────────────────


def test_recompute_technicals_requires_credentials() -> None:
    with patch(f"{WRITER}.build_supabase_client", return_value=None):
        result = CliRunner().invoke(recompute_technicals_cmd, ["--tickers", "SPY"])
    assert result.exit_code != 0
    assert "Supabase credentials not set" in result.output


def test_recompute_technicals_passes_window_through_and_reports() -> None:
    """--since / --as-of reach the recompute, and every counter is echoed."""
    recomputed = RefreshResult(
        tickers_processed=2,
        rows_upserted=7,
        rows_computed=7,
        history_rows_read=900,
        non_trading_rows_dropped=13,
    )
    with (
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{REFRESH}.recompute_technicals_from_history", return_value=recomputed) as recompute,
    ):
        result = CliRunner().invoke(
            recompute_technicals_cmd,
            ["--tickers", "spy,qqq", "--as-of", "2026-03-01", "--since", "2021-04-08"],
        )
    assert result.exit_code == 0, result.output
    kwargs = recompute.call_args.kwargs
    assert kwargs["tickers"] == ["SPY", "QQQ"]
    assert kwargs["as_of"] == date(2026, 3, 1)
    assert kwargs["since"] == date(2021, 4, 8)
    assert kwargs["dry_run"] is False
    assert "write 2021-04-08..2026-03-01" in result.output
    assert "read 900 OHLCV bars (dropped 13 non-session)" in result.output
    assert "upserted 7 rows into price_technicals" in result.output


def test_recompute_technicals_dry_run_does_not_write() -> None:
    with (
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(
            f"{REFRESH}.recompute_technicals_from_history",
            return_value=RefreshResult(1, 0, rows_computed=4, history_rows_read=40),
        ) as recompute,
    ):
        result = CliRunner().invoke(
            recompute_technicals_cmd, ["--tickers", "SPY", "--dry-run", "--as-of", "2026-03-01"]
        )
    assert result.exit_code == 0, result.output
    assert recompute.call_args.kwargs["dry_run"] is True
    assert "upserted 0 rows into price_technicals" in result.output


def test_recompute_technicals_rejects_malformed_and_inverted_dates() -> None:
    bad_iso = CliRunner().invoke(recompute_technicals_cmd, ["--tickers", "SPY", "--since", "nope"])
    assert bad_iso.exit_code != 0
    assert "--since must be ISO YYYY-MM-DD" in bad_iso.output

    inverted = CliRunner().invoke(
        recompute_technicals_cmd,
        ["--tickers", "SPY", "--as-of", "2026-01-01", "--since", "2026-02-01"],
    )
    assert inverted.exit_code != 0
    assert "must be on or before" in inverted.output


def test_blank_tickers_are_not_an_empty_override(tmp_path) -> None:
    """A comma-only or whitespace ``--tickers`` must not yield an empty universe."""
    from click import UsageError
    from digiquant.cli.prices import _resolve_universe

    watchlist = tmp_path / "watchlist.md"
    watchlist.write_text("| SPY |\n", encoding="utf-8")

    with pytest.raises(UsageError, match="did not contain any symbols"):
        _resolve_universe(",", watchlist, False)
    assert _resolve_universe("   ", watchlist, False) == ["SPY"]
    with pytest.raises(UsageError, match="Provide --watchlist or --tickers"):
        _resolve_universe("   ", None, False)


def test_recompute_technicals_needs_a_universe() -> None:
    result = CliRunner().invoke(recompute_technicals_cmd, [])
    assert result.exit_code != 0
    assert "Provide --watchlist or --tickers" in result.output
