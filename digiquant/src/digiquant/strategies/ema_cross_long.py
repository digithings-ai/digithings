"""Thin wrapper around Nautilus EMACrossLongOnly. See NAUTILUS_WRAPPERS.md."""

from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross_long_only import EMACrossLongOnly
from nautilus_trader.examples.strategies.ema_cross_long_only import EMACrossLongOnlyConfig

from digiquant.strategies.registry import register

register(
    "ema_cross_long",
    EMACrossLongOnly,
    EMACrossLongOnlyConfig,
    {
        "trade_size": Decimal(1000),
        "fast_ema_period": 10,
        "slow_ema_period": 20,
    },
    description="Long-only EMA crossover for equities (Nautilus EMACrossLongOnly)",
)
