"""Regression: the runner's *default* trade_size must be instrument-aware.

A fixed 1000-unit default over-leverages high-priced instruments (e.g. BTC at
~$10k+ on a $1M account is ~10x+ leverage). Nautilus then halts the whole run
with AccountBalanceNegative after a handful of bars, so every strategy returns
exactly 1 fill and 0 PnL — a silently meaningless backtest. The default is now
notional-based (a small fraction of starting balance / first price), so the run
completes across all bars without the caller having to pass trade_size.

These tests pass NO strategy_params, exercising the default path the repro hits:

    run_backtest(strategy_name="ema_cross", symbols=["BTC-USD"],
                 data_path="digiquant/data/BTC-USD.csv")  # used to print "1 ok"
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from digiquant.nautilus_runner import (
    DEFAULT_NOTIONAL_FRACTION,
    STARTING_BALANCE_USD,
    _default_trade_size,
)

DATA = Path(__file__).resolve().parents[2] / "digiquant" / "data" / "BTC-USD.csv"


@pytest.mark.unit
class TestDefaultTradeSizeHelper:
    def test_high_priced_instrument_sizes_down(self) -> None:
        # BTC ~$13.6k first bar: 2% of $1M / 13657 -> 1 unit (not 1000).
        size = _default_trade_size(13657.2, STARTING_BALANCE_USD, DEFAULT_NOTIONAL_FRACTION)
        assert size == Decimal(1)

    def test_low_priced_instrument_sizes_up(self) -> None:
        # AAPL ~$150: 2% of $1M / 150 -> 133 units, well within the $1M cash account.
        size = _default_trade_size(150.0, STARTING_BALANCE_USD, DEFAULT_NOTIONAL_FRACTION)
        assert size == Decimal(133)

    def test_floor_clamps_to_one_unit(self) -> None:
        # A $100k/unit instrument at 2% rounds to 0 -> must clamp to 1, never 0.
        size = _default_trade_size(100_000.0, STARTING_BALANCE_USD, DEFAULT_NOTIONAL_FRACTION)
        assert size == Decimal(1)

    def test_nonpositive_price_is_safe(self) -> None:
        assert _default_trade_size(0.0, STARTING_BALANCE_USD, DEFAULT_NOTIONAL_FRACTION) == Decimal(
            1
        )


@pytest.mark.unit
class TestDefaultTradeSizeBacktest:
    def test_btc_run_completes_with_default_sizing(self) -> None:
        pytest.importorskip("nautilus_trader")
        from digiquant.backtest import run_backtest  # noqa: PLC0415

        # No strategy_params: exercises the *default* trade_size (the repro's path).
        assert DATA.exists(), f"sample data missing: {DATA}"
        result = run_backtest(
            strategy_name="ema_cross",
            symbols=["BTC-USD"],
            data_path=str(DATA),
        )
        assert result is not None
        assert result.status == "ok", f"backtest did not complete: status={result.status}"
        # Before the fix this was exactly 1 (account blew up after ~48 of 2974 bars).
        # A run that completes the full series trades many times.
        assert result.num_trades > 1, (
            f"default-sized BTC run only traded {result.num_trades}x — the run likely "
            "halted early on AccountBalanceNegative instead of trading across all bars"
        )
