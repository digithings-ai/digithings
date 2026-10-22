"""Regression tests for the `digiquant prices fetch-fx-intraday` command.

The grading candles the twelve-x path reads, and the upsert chunk size that
keeps the request count down (DIG-1835).
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from digiquant.cli.prices import fetch_fx_intraday_cmd

from tests.dq.data.prices_cli_support import WRITER

pytestmark = pytest.mark.unit

_FETCH_INTRADAY = "digiquant.data.prices.macro_ingest.fetch_fx_intraday"


def _fake_candles(interval: str = "1h"):
    from datetime import UTC, datetime

    from digiquant.data.prices.macro_ingest import CandleObservation

    return [
        CandleObservation(
            series_id="FX/EUR",
            interval=interval,
            ts=datetime(2025, 4, 1, 13, tzinfo=UTC),
            open=1.08,
            high=1.10,
            low=1.07,
            close=1.09,
        ),
        CandleObservation(
            series_id="FX/EUR",
            interval=interval,
            ts=datetime(2025, 4, 1, 14, tzinfo=UTC),
            open=1.09,
            high=1.11,
            low=1.08,
            close=1.10,
        ),
    ]


# ─── fetch-fx-intraday (twelve-x grading candles) ─────────────────────────


def test_fetch_fx_intraday_dry_run_summarizes_without_credentials() -> None:
    with patch(_FETCH_INTRADAY, return_value=_fake_candles()):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--dry-run"])

    assert result.exit_code == 0, result.output
    assert "fx intraday: 2 candles" in result.output
    assert '"FX/EUR": 2' in result.output


def test_fetch_fx_intraday_upserts_candles_as_rows() -> None:
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)) as upsert,
    ):
        result = CliRunner().invoke(
            fetch_fx_intraday_cmd, ["--supabase", "--interval", "30m", "--period", "60d"]
        )

    assert result.exit_code == 0, result.output
    assert "upserted 2 rows into fx_intraday_observations" in result.output
    rows = upsert.call_args.args[1]
    assert rows[0] == {
        "source": "yahoo",
        "series_id": "FX/EUR",
        "interval": "30m",
        "ts": "2025-04-01T13:00:00+00:00",
        "open": 1.08,
        "high": 1.10,
        "low": 1.07,
        "close": 1.09,
    }
    assert {r["interval"] for r in rows} == {"30m"}


def test_fetch_fx_intraday_defaults_interval_to_1h_in_rows() -> None:
    """--interval is the single source of truth: the default '1h' is persisted."""
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles("5m")) as fetch,
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)) as upsert,
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase"])

    assert result.exit_code == 0, result.output
    assert fetch.call_args.kwargs["interval"] == "1h"
    rows = upsert.call_args.args[1]
    assert {r["interval"] for r in rows} == {"1h"}


def test_fetch_fx_intraday_help_documents_persisted_interval() -> None:
    """The --interval help must say the value is persisted, not config-only."""
    result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--help"])

    assert result.exit_code == 0, result.output
    assert "persisted" in result.output
    assert "fx_intraday_observations.interval" in result.output


def test_fetch_fx_intraday_requires_credentials() -> None:
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=None),
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase"])

    assert result.exit_code != 0
    assert "Supabase credentials not set" in result.output


# ─── fetch-fx-intraday upsert chunk size (DIG-1835) ───────────────────────
#
# Measured on core: /rest/v1/fx_intraday_observations took 2,265 requests in
# the 12h before the egress restriction, ~2,209 of them POST upserts, from
# python-httpx with the service role. At DEFAULT_CHUNK=500 that is roughly
# 1.1M rows moved per 12h window, and every one of those rows is also echoed
# back by PostgREST (see DIG-2112). Request COUNT is the lever here: a wider
# chunk is strictly fewer round trips for the same rows.


def test_fetch_fx_intraday_passes_default_chunk_to_writer() -> None:
    """The CLI must plumb an explicit chunk, not silently inherit DEFAULT_CHUNK."""
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)) as upsert,
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase"])

    assert result.exit_code == 0, result.output
    chunk = upsert.call_args.kwargs.get("chunk")
    assert chunk is not None, "fetch-fx-intraday must pass chunk= to the writer"
    assert chunk > 0


def test_fetch_fx_intraday_chunk_exceeds_writer_default() -> None:
    """The whole point: fewer requests than DEFAULT_CHUNK=500 for the same rows."""
    from digiquant.data.prices.supabase_writer import DEFAULT_CHUNK

    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)) as upsert,
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase"])

    assert result.exit_code == 0, result.output
    chunk = upsert.call_args.kwargs.get("chunk")
    assert chunk is not None, "fetch-fx-intraday must pass chunk= to the writer"
    assert chunk > DEFAULT_CHUNK, f"chunk {chunk} must beat DEFAULT_CHUNK {DEFAULT_CHUNK}"


def test_fetch_fx_intraday_chunk_flag_overrides_default() -> None:
    """An operator can drop to a small chunk on a constrained gateway."""
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)) as upsert,
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase", "--chunk", "250"])

    assert result.exit_code == 0, result.output
    assert upsert.call_args.kwargs.get("chunk") == 250


def test_fetch_fx_intraday_chunk_rejects_non_positive() -> None:
    """A zero or negative chunk would spin forever in _chunks()."""
    with (
        patch(_FETCH_INTRADAY, return_value=_fake_candles()),
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_fx_intraday_observations", return_value=Mock(rows=2)),
    ):
        result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--supabase", "--chunk", "0"])

    assert result.exit_code != 0
    # Must reject the VALUE, not merely reject --chunk as an unknown option.
    assert "No such option" not in result.output, result.output


def test_fetch_fx_intraday_help_documents_chunk() -> None:
    result = CliRunner().invoke(fetch_fx_intraday_cmd, ["--help"])

    assert result.exit_code == 0, result.output
    assert "--chunk" in result.output
