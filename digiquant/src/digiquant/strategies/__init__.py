# DigiQuant strategy repository. See digiquant/ARCHITECTURE.md and docs/NAUTILUS_STRATEGIES.md.

from digiquant.strategies.registry import get_strategy, list_strategies, register

# Import wrappers to trigger registration
from digiquant.strategies import ema_cross  # noqa: F401
from digiquant.strategies import ema_cross_long  # noqa: F401
from digiquant.strategies import ema_cross_trailing  # noqa: F401
from digiquant.strategies import rsi_momentum  # noqa: F401
from digiquant.strategies import bollinger_mr  # noqa: F401
from digiquant.strategies import macd_trend  # noqa: F401

__all__ = ["get_strategy", "list_strategies", "register"]
