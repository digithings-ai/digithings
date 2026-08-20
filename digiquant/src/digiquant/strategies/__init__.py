# digiquant strategy repository. See digiquant/ARCHITECTURE.md and docs/NAUTILUS_STRATEGIES.md.

# Side-effect imports register each strategy with the registry on load. All of these
# strategies wrap NautilusTrader, which is an optional dependency in the core install —
# skip registration rather than fail the whole package import when it's missing, so
# Nautilus-free submodules (e.g. strategies.sdca, see #1080) stay importable.
try:
    from digiquant.strategies import (
        bollinger_mr,
        ema_cross,
        ema_cross_long,
        ema_cross_trailing,
        m2_liquidity,
        macd_trend,
        rsi_momentum,
        slapper,
    )
except ImportError:
    pass

from digiquant.strategies.registry import get_strategy, list_strategies, register

__all__ = ["get_strategy", "list_strategies", "register"]
