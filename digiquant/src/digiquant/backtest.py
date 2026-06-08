"""Backtest entrypoint: NautilusTrader only. No stub; requires digiquant[nautilus] and OHLCV data."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

from digiquant.models import BacktestResult
from digiquant.nautilus_runner import run_nautilus_backtest
from digiquant.strategies.registry import _ALIASES as _REGISTRY_ALIASES
from digiquant.strategies.registry import _REGISTRY
from digiquant.strategy_specs import STRATEGY_PARAM_SPECS, _ALIAS_TO_CANONICAL

# Lazily populated on first call to run_backtest. Importing digiquant.strategies at module
# level would pull in nautilus_trader (via bollinger_mr etc.) which breaks non-Nautilus tests.
_KNOWN_STRATEGIES: frozenset[str] | None = None


def _get_known_strategies() -> frozenset[str]:
    global _KNOWN_STRATEGIES
    if _KNOWN_STRATEGIES is None:
        import digiquant.strategies  # noqa: F401, PLC0415 — side-effect: populates _REGISTRY
        _KNOWN_STRATEGIES = (
            frozenset(STRATEGY_PARAM_SPECS.keys())
            | frozenset(_ALIAS_TO_CANONICAL.keys())
            | frozenset(_REGISTRY.keys())
            | frozenset(_REGISTRY_ALIASES.keys())
        )
    return _KNOWN_STRATEGIES

logger = logging.getLogger(__name__)

NAUTILUS_UNAVAILABLE_MSG = (
    "Nautilus backtest unavailable. Install digiquant[nautilus]."
)
DATA_REQUIRED_MSG = (
    "Backtest requires data_path (single OHLCV CSV) or data_dir with symbols. "
    "Specify strategy, symbols, and data source."
)
DATA_NOT_FOUND_MSG = (
    "Backtest failed: no OHLCV data found for symbol(s) (check data_path exists or data_dir "
    "contains {symbol}.csv), or NautilusTrader not installed (pip install digiquant[nautilus])."
)

# In-memory backtest result cache keyed by SHA-256 of (strategy, symbols, params, data source).
# Skipped when tearsheet_path is set. Disable with DIGIQUANT_BACKTEST_CACHE=false.
_CACHE_ENABLED = os.environ.get("DIGIQUANT_BACKTEST_CACHE", "true").strip().lower() not in (
    "0", "false", "no"
)
def _backtest_cache_max() -> int:
    raw = (os.environ.get("DIGIQUANT_BACKTEST_CACHE_MAX") or "128").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 128
_backtest_cache: dict[str, BacktestResult] = {}
_backtest_cache_order: list[str] = []


def _cache_key(
    strategy_name: str,
    symbols: list[str],
    params: dict | None,
    data_path: str | Path | None,
    data_dir: str | Path | None,
) -> str:
    payload = {
        "strategy_name": strategy_name,
        "symbols": sorted(symbols),
        "params": dict(sorted((params or {}).items())),
        "data_path": str(data_path) if data_path else None,
        "data_dir": str(data_dir) if data_dir else None,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _evict_backtest_cache_if_needed() -> None:
    """Drop oldest entries when the LRU table exceeds :data:`_BACKTEST_CACHE_MAX`."""
    while len(_backtest_cache) > _backtest_cache_max():
        oldest = _backtest_cache_order.pop(0)
        _backtest_cache.pop(oldest, None)


def clear_backtest_cache() -> int:
    """Clear the in-memory backtest cache. Returns number of entries removed."""
    n = len(_backtest_cache)
    _backtest_cache.clear()
    _backtest_cache_order.clear()
    return n


def run_backtest(
    strategy_name: str,
    symbols: list[str],
    data_path: str | Path | None = None,
    data_dir: str | Path | None = None,
    tearsheet_path: str | Path | None = None,
    strategy_params: dict | None = None,
    full_tearsheet: bool = True,
) -> BacktestResult:
    """
    Entrypoint for backtest. Used by HTTP API and MCP tool.
    Requires strategy_name, symbols, and data_path or data_dir. Fails if data unavailable.

    Results are cached in-memory by (strategy, symbols, params, data source) hash.
    Cache is skipped when tearsheet_path is set (tearsheet must be written to disk).
    Disable caching with DIGIQUANT_BACKTEST_CACHE=false.
    """
    known = _get_known_strategies()
    if strategy_name not in known:
        raise ValueError(
            f"Unknown strategy: {strategy_name!r}. Known strategies: {sorted(known)}"
        )
    if not symbols:
        raise RuntimeError("symbols required (non-empty list).")
    if data_path is None and data_dir is None:
        raise RuntimeError(DATA_REQUIRED_MSG)

    key = _cache_key(strategy_name, symbols, strategy_params, data_path, data_dir)
    if _CACHE_ENABLED and tearsheet_path is None:
        cached = _backtest_cache.get(key)
        if cached is not None:
            if key in _backtest_cache_order:
                _backtest_cache_order.remove(key)
            _backtest_cache_order.append(key)
            logger.debug("Backtest cache hit: strategy=%s symbols=%s", strategy_name, symbols)
            return cached

    result = run_nautilus_backtest(
        strategy_name=strategy_name,
        symbols=symbols,
        data_path=data_path,
        data_dir=data_dir,
        tearsheet_path=tearsheet_path,
        strategy_params=strategy_params,
        full_tearsheet=full_tearsheet,
    )
    if result is not None:
        if _CACHE_ENABLED and tearsheet_path is None:
            if key in _backtest_cache_order:
                _backtest_cache_order.remove(key)
            _backtest_cache[key] = result
            _backtest_cache_order.append(key)
            _evict_backtest_cache_if_needed()
        return result
    raise RuntimeError(DATA_NOT_FOUND_MSG)
