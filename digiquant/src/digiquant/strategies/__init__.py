# DigiQuant strategy repository. See digiquant/ARCHITECTURE.md and docs/NAUTILUS_STRATEGIES.md.

from digiquant.strategies.registry import get_strategy, list_strategies, register

# Side-effect imports register each strategy with the registry on load.
from digiquant.strategies import (  # noqa: F401
    bollinger_mr,
    ema_cross,
    ema_cross_long,
    ema_cross_trailing,
    macd_trend,
    rsi_momentum,
    slapper,
)

__all__ = ["get_strategy", "list_strategies", "register"]
