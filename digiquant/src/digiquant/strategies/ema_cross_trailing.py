"""Thin wrapper around Nautilus EMACrossTrailingStop. See NAUTILUS_WRAPPERS.md."""

from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross_trailing_stop import EMACrossTrailingStop
from nautilus_trader.examples.strategies.ema_cross_trailing_stop import (
    EMACrossTrailingStopConfig,
)

from digiquant.strategies.registry import register

register(
    "ema_cross_trailing",
    EMACrossTrailingStop,
    EMACrossTrailingStopConfig,
    {
        "trade_size": Decimal(1000),
        "fast_ema_period": 10,
        "slow_ema_period": 20,
        "atr_period": 14,
        "trailing_atr_multiple": 2.0,
        "trailing_offset_type": "PRICE",
        "trigger_type": "BID_ASK",
    },
    description="EMA crossover + ATR trailing stop (Nautilus EMACrossTrailingStop)",
)
