"""Regression tests for the `digiquant prices` CLI commands.

Covers the graceful-exit behaviour introduced in #558: upsert failures must
not propagate as a non-zero exit code, and the indicator row-count mismatch
must be handled without raising.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import Mock, patch

import polars as pl
import pytest
from click.testing import CliRunner
from digiquant.cli.prices import (
    compute_technicals_cmd,
    fetch_quotes_cmd,
    recompute_technicals_cmd,
)
from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices.instrument_metadata import InstrumentMetadataFetchResult
from digiquant.data.prices.refresh import RefreshResult
from digiquant.dashboard.instrument_metadata import InstrumentMetadata

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


def test_fetch_quotes_persists_resolved_instrument_metadata() -> None:
    runner = CliRunner()
    client = object()
    metadata = InstrumentMetadata.fallback("SPY", provider="test")

    with (
        patch(f"{_WRITER}.build_supabase_client", return_value=client),
        patch(f"{_WRITER}.upsert_price_history"),
        patch(f"{_WRITER}.upsert_instruments") as upsert_instruments,
        patch(f"{_CACHE}.incremental_update", return_value={"SPY": _fake_ohlcv(3)}),
        patch(
            "digiquant.data.prices.instrument_metadata.fetch_instrument_metadata",
            return_value=InstrumentMetadataFetchResult(records={"SPY": metadata}, errors={}),
        ),
    ):
        upsert_instruments.return_value.rows = 1
        result = runner.invoke(
            fetch_quotes_cmd,
            ["--tickers", "SPY", "--supabase", "--instrument-metadata"],
        )

    assert result.exit_code == 0, result.output
    upsert_instruments.assert_called_once_with(client, [metadata])
    assert "upserted 1 rows into instruments" in result.output


def test_sector_universe_dedupes_and_includes_single_names() -> None:
    from digiquant.research.sectors_config import sector_universe

    universe = sector_universe()
    assert universe == [t.upper() for t in universe]  # all upper-cased
    assert len(universe) == len(set(universe))  # deduped
    assert "XLK" in universe  # a sector ETF
    assert "NVDA" in universe  # a top single name / sub-segment ticker


def test_fetch_quotes_include_sectors_unions_universe(tmp_path) -> None:
    # --include-sectors must union the sector config's single names + ETFs into the fetch
    # universe so sector research gets single-name technicals (price_technicals was ETF-only;
    # #946).
    from digiquant.research.sectors_config import sector_universe

    captured: dict[str, list[str]] = {}

    def _fake_update(universe, **_):
        captured["universe"] = list(universe)
        return {}

    runner = CliRunner()
    with patch(f"{_CACHE}.incremental_update", side_effect=_fake_update):
        result = runner.invoke(
            fetch_quotes_cmd,
            ["--tickers", "SPY", "--include-sectors", "--dry-run", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    universe = captured["universe"]
    assert "SPY" in universe  # original ticker preserved
    assert set(sector_universe()).issubset(set(universe))  # all sector tickers unioned in
    assert "NVDA" in universe  # a representative single name now present
    assert len(universe) == len(set(universe))  # no duplicates introduced


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


def test_compute_technicals_casts_datetime_trading_days_to_date(tmp_path) -> None:
    """Datetime trading_days from Supabase are cast to Date before filtering."""
    n = 40
    runner = CliRunner()
    trading_days_dt = pl.Series([date(2025, 1, 1)]).cast(pl.Datetime)

    with (
        patch(f"{_WRITER}.build_supabase_client", return_value=object()),
        patch(f"{_WRITER}.upsert_price_technicals", return_value=Mock(rows=n)),
        patch(f"{_CACHE}.load_cached", return_value=_fake_ohlcv(n)),
        patch(f"{_TECH}.compute_indicators", return_value=_fake_ind(n)),
        patch(f"{_VENUES}.venue_for", return_value="NYSE"),
        patch("digiquant.cli.prices._fetch_trading_days", return_value=trading_days_dt),
    ):
        result = runner.invoke(
            compute_technicals_cmd,
            ["--tickers", "SPY", "--supabase", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert f"{n} rows into price_technicals" in result.output


# ─── recompute-technicals (#1752) ─────────────────────────────────────────


_REFRESH = "digiquant.data.prices.refresh"


def test_recompute_technicals_requires_credentials() -> None:
    with patch(f"{_WRITER}.build_supabase_client", return_value=None):
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
        patch(f"{_WRITER}.build_supabase_client", return_value=Mock()),
        patch(
            f"{_REFRESH}.recompute_technicals_from_history", return_value=recomputed
        ) as recompute,
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
        patch(f"{_WRITER}.build_supabase_client", return_value=Mock()),
        patch(
            f"{_REFRESH}.recompute_technicals_from_history",
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


def test_recompute_technicals_needs_a_universe() -> None:
    result = CliRunner().invoke(recompute_technicals_cmd, [])
    assert result.exit_code != 0
    assert "Provide --watchlist or --tickers" in result.output
