"""Regression tests for the R2 cutover gate on the `digiquant prices` writers.

Under DIGIQUANT_MARKET_DATA_BACKEND=r2 the writers fail LOUD (never silent),
with fedprob the documented exception: prediction-market odds have no R2
generation, so fedprob-only runs keep writing Supabase under r2.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from digiquant.cli.prices import (
    compute_technicals_cmd,
    fetch_macro_cmd,
    fetch_quotes_cmd,
    recompute_technicals_cmd,
)
from digiquant.data.prices.refresh import RefreshResult

from tests.dq.data.prices_cli_support import REFRESH, WRITER

pytestmark = pytest.mark.unit

# ─── R2 cutover writers-stop, second attempt (#3780, Task 7b) ─────────────
# The Task 7 fix round reverted the stop to dual-write (bulk readers were
# still Supabase-only). With every reader on the R2 seams, the writers stop
# again: covered sources refuse LOUD under r2. fedprob is the documented
# exception — prediction-market odds have no R2 generation, so fedprob-only
# runs keep writing Supabase under r2.


def test_supabase_writers_refuse_under_r2_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Under DIGIQUANT_MARKET_DATA_BACKEND=r2 the writers fail LOUD (never silent)."""
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    runner = CliRunner()
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series: []\n")
    cases = [
        (fetch_quotes_cmd, ["--tickers", "SPY", "--supabase"]),
        (
            compute_technicals_cmd,
            ["--tickers", "SPY", "--supabase", "--cache-dir", str(tmp_path)],
        ),
        (recompute_technicals_cmd, ["--tickers", "SPY"]),
        (
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--supabase", "--sources", "fred"],
        ),
        (
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--supabase"],
        ),  # default fred,yahoo
        (
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--supabase", "--sources", "fred,fedprob"],
        ),  # mixed runs still refuse (fred is R2-owned)
    ]
    for cmd, args in cases:
        result = runner.invoke(cmd, args)
        assert result.exit_code != 0, (cmd.name, result.output)
        assert "writes are stopped" in result.output, (cmd.name, result.output)


def test_fetch_macro_fedprob_only_proceeds_under_r2_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """fedprob-only runs are exempt: no R2 generation exists for them."""
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    runner = CliRunner()
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series: []\n")
    with (
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(f"{WRITER}.upsert_macro_observations", return_value=Mock(rows=2)),
        patch(
            "digiquant.data.prices.fed_probabilities.fetch_fed_prob_kalshi",
            return_value=[],
        ),
        patch(
            "digiquant.data.prices.fed_probabilities.fetch_fed_prob_polymarket",
            return_value=[],
        ),
    ):
        result = runner.invoke(
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--supabase", "--sources", "fedprob"],
        )
    assert result.exit_code == 0, result.output


def test_supabase_writers_stay_active_by_default(tmp_path, monkeypatch) -> None:
    """Without the flag the gates are inert (dry-run paths exit zero, no network)."""
    from digiquant.cli.prices import _supabase_writes_disabled

    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    assert _supabase_writes_disabled() is False  # flag default is supabase
    runner = CliRunner()
    result = runner.invoke(
        fetch_quotes_cmd, ["--tickers", "SPY", "--dry-run", "--cache-dir", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    with (
        patch(f"{WRITER}.build_supabase_client", return_value=Mock()),
        patch(
            f"{REFRESH}.recompute_technicals_from_history",
            return_value=RefreshResult(1, 0, rows_computed=4, history_rows_read=40),
        ),
    ):
        result = runner.invoke(
            recompute_technicals_cmd, ["--tickers", "SPY", "--dry-run", "--as-of", "2026-03-01"]
        )
    assert result.exit_code == 0, result.output
