"""Strategy registry: maps strategy_name to Nautilus Strategy + Config."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nautilus_trader.trading.strategy import Strategy


@dataclass
class StrategySpec:
    """Spec for a registered strategy."""

    strategy_cls: type
    config_cls: type
    default_params: dict[str, Any]
    description: str


_REGISTRY: dict[str, StrategySpec] = {}
_ALIASES: dict[str, str] = {}  # alias -> canonical name


def register(
    name: str,
    strategy_cls: type,
    config_cls: type,
    default_params: dict[str, Any],
    *,
    aliases: list[str] | None = None,
    description: str = "",
) -> None:
    """Register a strategy with its config and default params."""
    _REGISTRY[name] = StrategySpec(
        strategy_cls=strategy_cls,
        config_cls=config_cls,
        default_params=default_params,
        description=description,
    )
    for alias in aliases or []:
        _ALIASES[alias] = name


def _resolve_name(strategy_name: str) -> str:
    """Resolve alias or unknown name to canonical registry key."""
    return _ALIASES.get(strategy_name, strategy_name)


def get_strategy(
    strategy_name: str,
    instrument_id: Any,
    bar_type: Any,
    trade_size: Decimal | None = None,
    **overrides: Any,
) -> tuple[Strategy, Any]:
    """
    Build Strategy and Config for the given strategy_name.
    Returns (strategy_instance, config). Caller adds strategy to engine.
    """
    canonical = _resolve_name(strategy_name)
    spec = _REGISTRY.get(canonical)
    if spec is None:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. Registered: {list(_REGISTRY.keys())}. "
            "Specify a valid strategy_name."
        )
    params = {**spec.default_params, **overrides}
    params["instrument_id"] = instrument_id
    params["bar_type"] = bar_type
    if trade_size is not None:
        params["trade_size"] = trade_size
    config = spec.config_cls(**params)
    strategy = spec.strategy_cls(config=config)
    return strategy, config


def list_strategies() -> list[dict[str, Any]]:
    """List all registered strategies with name, description, default params."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name, spec in _REGISTRY.items():
        if name in seen:
            continue
        seen.add(name)
        aliases = [a for a, c in _ALIASES.items() if c == name]
        result.append({
            "name": name,
            "aliases": aliases,
            "description": spec.description[:200] if spec.description else "",
            "default_params": spec.default_params,
        })
    return result
