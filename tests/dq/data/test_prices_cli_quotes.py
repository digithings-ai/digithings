"""Regression tests for the `digiquant prices fetch-quotes` command.

The graceful-exit behaviour introduced in #558 (an upsert failure must not
propagate as a non-zero exit code), the resolved instrument metadata that
gets persisted, and the sector universe union (#946).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from click.testing import CliRunner
from digiquant.cli.prices import fetch_quotes_cmd
from digiquant.dashboard.instrument_metadata import InstrumentMetadata
from digiquant.data.prices.instrument_metadata import InstrumentMetadataFetchResult

from tests.dq.data.prices_cli_support import CACHE, WRITER, fake_ohlcv

pytestmark = pytest.mark.unit

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
        patch(f"{WRITER}.build_supabase_client", return_value=object()),
        patch(f"{WRITER}.upsert_price_history", side_effect=RuntimeError("net failure")),
        patch(f"{CACHE}.incremental_update", return_value={"SPY": fake_ohlcv(3)}),
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
        patch(f"{WRITER}.build_supabase_client", return_value=client),
        patch(f"{WRITER}.upsert_price_history"),
        patch(f"{WRITER}.upsert_instruments") as upsert_instruments,
        patch(f"{CACHE}.incremental_update", return_value={"SPY": fake_ohlcv(3)}),
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
    assert "NVDA" in universe


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
    with patch(f"{CACHE}.incremental_update", side_effect=_fake_update):
        result = runner.invoke(
            fetch_quotes_cmd,
            ["--tickers", "SPY", "--include-sectors", "--dry-run", "--cache-dir", str(tmp_path)],
        )

    assert result.exit_code == 0, result.output
    universe = captured["universe"]
    assert "SPY" in universe  # original ticker preserved
    assert set(sector_universe()).issubset(set(universe))  # all sector tickers unioned in
    assert "NVDA" in universe  # a representative single name now present
    assert len(universe) == len(set(universe))
