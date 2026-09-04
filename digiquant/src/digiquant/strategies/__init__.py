# digiquant strategy repository. See digiquant/ARCHITECTURE.md and docs/NAUTILUS_STRATEGIES.md.

from importlib.util import find_spec

# Side-effect imports register each strategy with the registry on load. All of these
# strategies wrap NautilusTrader, which is an optional dependency in the core install —
# gate on its presence rather than fail the whole package import when it's missing, so
# Nautilus-free submodules (e.g. strategies.sdca, see #1080) stay importable. Gating on
# find_spec (not a broad except ImportError) means a genuine bug inside one of these
# modules still raises loudly instead of leaving the registry silently incomplete.
if find_spec("nautilus_trader") is not None:
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
    from digiquant.strategies.rotation import nautilus_strategy as rs_rotation_nautilus_strategy
    from digiquant.strategies.sdca import nautilus_strategy as sdca_nautilus_strategy

from digiquant.strategies.registry import (
    get_strategy,
    list_strategies,
    register,
    resolve_strategy_name,
)

__all__ = ["get_strategy", "list_strategies", "register", "resolve_strategy_name"]
