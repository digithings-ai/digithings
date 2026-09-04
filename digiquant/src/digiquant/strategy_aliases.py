"""Canonical strategy alias map — shared by registry, optimize specs, export, CLI.

Runtime registration still happens in ``strategies/registry.py`` via
``register(..., aliases=...)``. This module is the **single static source** for
alias → registry-canonical resolution used outside the Nautilus import path
(optimize param specs, export, known-strategy checks).

``resolve_param_spec_name`` maps to ``STRATEGY_PARAM_SPECS`` keys, which differ
from the registry canonical only for SDCA (``btc_sdca`` → ``sdca``).
"""

from __future__ import annotations

# alias → registry canonical name
STRATEGY_ALIASES: dict[str, str] = {
    "ema": "ema_cross",
    "s": "ema_cross",  # test shorthand
    "mean_reversion_tech": "ema_cross",
    "momentum_tech": "ema_cross",
    "mean_reversion_stat_arb": "bollinger_mr",
    "momentum_energy": "rsi_momentum",
    "sdca": "btc_sdca",
    "btc_slapper_mr_trend": "btc_slapper",
    "eth_slapper_mr_trend": "eth_slapper",
    "sol_slapper_mr_trend": "sol_slapper",
}

# registry canonical → STRATEGY_PARAM_SPECS key (when they differ)
PARAM_SPEC_NAMES: dict[str, str] = {
    "btc_sdca": "sdca",
}


def resolve_strategy_name(strategy_name: str) -> str:
    """Resolve an alias to the registry canonical strategy name."""
    return STRATEGY_ALIASES.get(strategy_name, strategy_name)


def resolve_param_spec_name(strategy_name: str) -> str:
    """Resolve an alias or registry name to a ``STRATEGY_PARAM_SPECS`` key."""
    canonical = resolve_strategy_name(strategy_name)
    return PARAM_SPEC_NAMES.get(canonical, canonical)


def aliases_for(canonical: str) -> list[str]:
    """Return static aliases that point at ``canonical`` (sorted)."""
    return sorted(a for a, c in STRATEGY_ALIASES.items() if c == canonical)
