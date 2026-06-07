"""End-to-end backtest of btc_slapper on sample BTC data.

This is the FIRST and ONLY test that exercises the Slapper strategy's `on_bar`
trading path: indicators warm up, signals fire, orders submit, positions flip.
Tasks 6-7 only covered config defaults + instantiation, which skip on CI without
Nautilus and never touch the trading loop.

Baseline (observed on digiquant/data/BTC-USD.csv, 2974 daily bars 2018-2026,
Nautilus 1.223.0, trade_size=1 BTC):
    btc_slapper: num_trades=74, total_return_pct=+19.42%
    eth_slapper: num_trades=84, total_return_pct=+8.48%
    sol_slapper: num_trades=84, total_return_pct=+8.48% (identical params to eth)
A large divergence (e.g. ~1 trade, or a 10x swing in trade count) in future runs
signals a regression in the on_bar / signal / order path. Full TradingView numeric
parity is intentionally not asserted (fill-timing and percent_of_equity sizing
differences make an exact match unlikely); this test only guards that the strategy
actually trades across the full series.

NOTE ON SIZING: the runner's default ``trade_size`` is 1000 units, which on a
$1M account at BTC's ~$10k+ price is ~10x over-leverage — the account goes
negative and Nautilus halts the entire run after ~48 bars, yielding exactly one
fill. We pass ``trade_size=1`` so the run completes over all 2974 bars and the
``num_trades > 0`` assertion is meaningful rather than a single-entry artifact.
The unscaled default is an instrument-agnostic footgun tracked separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nautilus_trader")

from digiquant.backtest import run_backtest  # noqa: E402

DATA = Path(__file__).resolve().parents[3] / "digiquant" / "data" / "BTC-USD.csv"


@pytest.mark.unit
class TestSlapperBacktest:
    def test_btc_slapper_runs_and_trades(self) -> None:
        assert DATA.exists(), f"sample data missing: {DATA}"
        result = run_backtest(
            strategy_name="btc_slapper",
            symbols=["BTC-USD"],
            data_path=str(DATA),
            strategy_params={"trade_size": 1},  # see SIZING note in module docstring
        )
        # The strategy must actually trade — zero trades means signals never
        # fired (indicator init bug) or orders never flipped (sizing bug).
        assert result.status == "ok", f"backtest did not complete: status={result.status}"
        assert result.num_trades > 0, (
            f"btc_slapper produced no trades — on_bar path broken (status={result.status})"
        )
        # Guard against the over-leverage blowup that halts the run after ~48 bars
        # (which yields exactly 1 fill). A healthy run trades dozens of times.
        assert result.num_trades > 10, (
            f"btc_slapper only traded {result.num_trades}x — run likely halted early "
            "(account blowup) rather than trading across the full series"
        )

    def test_eth_and_sol_variants_run_without_raising(self) -> None:
        # Same data, different param profiles — must complete without raising.
        for name in ("eth_slapper", "sol_slapper"):
            result = run_backtest(
                strategy_name=name,
                symbols=["BTC-USD"],
                data_path=str(DATA),
                strategy_params={"trade_size": 1},
            )
            assert result is not None
            assert result.status == "ok"
