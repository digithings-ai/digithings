"""Strategy registry: maps strategy_name to Nautilus Strategy + Config."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from digiquant.strategy_aliases import (
    STRATEGY_ALIASES,
    aliases_for,
)

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
_ALIASES: dict[str, str] = {}  # runtime aliases from register() — merged with STRATEGY_ALIASES


def register(
    name: str,
    strategy_cls: type,
    config_cls: type,
    default_params: dict[str, Any],
    *,
    aliases: list[str] | None = None,
    description: str = "",
) -> None:
    """Register a strategy with its config and default params.

    Prefer declaring static aliases in ``digiquant.strategy_aliases.STRATEGY_ALIASES``
    so optimize/export/CLI resolve without importing Nautilus. ``aliases=`` still
    registers runtime aliases for ``list_strategies`` and late-bound names.
    """
    _REGISTRY[name] = StrategySpec(
        strategy_cls=strategy_cls,
        config_cls=config_cls,
        default_params=default_params,
        description=description,
    )
    for alias in aliases or []:
        _ALIASES[alias] = name


def resolve_strategy_name(strategy_name: str) -> str:
    """Resolve alias → registry canonical (static map + runtime ``register`` aliases)."""
    if strategy_name in STRATEGY_ALIASES:
        return STRATEGY_ALIASES[strategy_name]
    return _ALIASES.get(strategy_name, strategy_name)


def _resolve_name(strategy_name: str) -> str:
    """Resolve alias or unknown name to canonical registry key."""
    return resolve_strategy_name(strategy_name)


def _config_fields(config_cls: type) -> frozenset[str]:
    """Declared field names on a Nautilus ``StrategyConfig`` (msgspec struct)."""
    fields = getattr(config_cls, "__struct_fields__", None)
    if fields:
        return frozenset(fields)
    return frozenset(getattr(config_cls, "__annotations__", {}))


def config_declares_field(strategy_name: str, field: str) -> bool:
    """True when the registered config class has ``field`` (e.g. ``trade_size``).

    Publish-path injection (#3170) must not pass ``trade_size`` into configs
    that do not declare it (``SdcaStrategyConfig``, and ``M2LiquidityConfig``
    when it is registered). Inspect the class, never a strategy-name allowlist.
    """
    canonical = _resolve_name(strategy_name)
    spec = _REGISTRY.get(canonical)
    if spec is None:
        raise ValueError(
            f"Unknown strategy: {strategy_name}. Registered: {list(_REGISTRY.keys())}."
        )
    return field in _config_fields(spec.config_cls)


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
    if trade_size is not None and "trade_size" in _config_fields(spec.config_cls):
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
        static = aliases_for(name)
        runtime = [a for a, c in _ALIASES.items() if c == name and a not in static]
        aliases = sorted({*static, *runtime})
        result.append(
            {
                "name": name,
                "aliases": aliases,
                "description": spec.description[:200] if spec.description else "",
                "default_params": spec.default_params,
            }
        )
    return result


__all__ = [
    "StrategySpec",
    "config_declares_field",
    "get_strategy",
    "list_strategies",
    "register",
    "resolve_strategy_name",
]
