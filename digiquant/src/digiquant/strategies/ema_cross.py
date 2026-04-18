"""Thin wrapper around Nautilus EMACross. See NAUTILUS_WRAPPERS.md."""

from decimal import Decimal

from nautilus_trader.examples.strategies.ema_cross import EMACross
from nautilus_trader.examples.strategies.ema_cross import EMACrossConfig

from digiquant.strategies.registry import register

register(
    "ema_cross",
    EMACross,
    EMACrossConfig,
    {
        "trade_size": Decimal(1000),
        "fast_ema_period": 10,
        "slow_ema_period": 20,
    },
    aliases=["mean_reversion_tech", "momentum_tech"],
    description="EMA crossover, market orders (Nautilus EMACross)",
)
