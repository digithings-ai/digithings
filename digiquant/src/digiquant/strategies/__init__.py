# digiquant strategy repository. See digiquant/ARCHITECTURE.md and docs/NAUTILUS_STRATEGIES.md.

from importlib import import_module
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
        macd_trend,
        rsi_momentum,
    )

    # Proprietary strategies live in this package in the monorepo and ship
    # outside the public package (repo split, #6751). Import each one that is
    # present; a bug inside a present module still raises.
    for _private in (
        "digiquant.strategies.m2_liquidity",
        "digiquant.strategies.slapper",
        "digiquant.strategies.rotation.nautilus_strategy",
        "digiquant.strategies.sdca.nautilus_strategy",
    ):
        try:
            _present = find_spec(_private) is not None
        except ModuleNotFoundError:  # parent package absent
            _present = False
        if _present:
            import_module(_private)

from digiquant.strategies.registry import (
    get_strategy,
    list_strategies,
    register,
    resolve_strategy_name,
)

# Repo-split 1.2 (DIG-3691): private strategies (incl. SDCA today, R1 after the
# split) register through the ``digiquant.strategies`` entry-point group
# instead of side-effect imports here. Reference strategies above stay
# direct-imported. Discovery is fail-closed (warn-and-skip).
try:
    from digiquant import plugin as _plugin

    _plugin.register_plugin_strategies(register)
except Exception:  # pragma: no cover — discovery never raises; belt and braces
    pass

__all__ = ["get_strategy", "list_strategies", "register", "resolve_strategy_name"]
