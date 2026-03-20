"""Strategy param specs for auto-inferred optimization ranges. Per-strategy bounds and defaults."""

from __future__ import annotations

import itertools
import logging
import os
import random
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Mtime cache for YAML spec file: (path_str, mtime, result).
# Avoids re-parsing on every get_param_specs() call; invalidated when file changes on disk.
_yaml_cache: tuple[str, float, dict[str, dict[str, tuple]]] | None = None


def _load_yaml_specs() -> dict[str, dict[str, tuple]]:
    """Load extra strategy specs from DIGIQUANT_STRATEGY_SPECS_PATH YAML file, if set.

    YAML format::

        strategies:
          my_strategy:
            param_name: [min, max, default, step_hint, type]
            ...

    Returns an empty dict if the env var is unset or the file cannot be loaded.
    Results are cached by file mtime; the cache is invalidated automatically when the file changes.
    """
    global _yaml_cache
    path_str = os.environ.get("DIGIQUANT_STRATEGY_SPECS_PATH")
    if not path_str:
        return {}
    path = Path(path_str)
    if not path.exists():
        logger.warning("DIGIQUANT_STRATEGY_SPECS_PATH=%s not found; ignoring.", path_str)
        return {}
    try:
        mtime = path.stat().st_mtime
        if _yaml_cache is not None and _yaml_cache[0] == path_str and _yaml_cache[1] == mtime:
            return _yaml_cache[2]
        import yaml  # type: ignore[import-untyped]
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        strategies = data.get("strategies") or {}
        result: dict[str, dict[str, tuple]] = {}
        for strat_name, params in strategies.items():
            if not isinstance(params, dict):
                continue
            result[strat_name] = {
                pname: tuple(pspec) for pname, pspec in params.items()
            }
        _yaml_cache = (path_str, mtime, result)
        return result
    except Exception as exc:
        logger.warning("Failed to load strategy specs YAML from %s: %s", path_str, exc)
        return {}

# Hard cap on grid size to prevent accidental combinatorial explosion.
MAX_GRID_SIZE = 10_000

# Alias -> canonical strategy name (must match registry)
_ALIAS_TO_CANONICAL: dict[str, str] = {
    "ema": "ema_cross",
    "s": "ema_cross",  # test shorthand
    "mean_reversion_tech": "ema_cross",
    "momentum_tech": "ema_cross",
    "mean_reversion_stat_arb": "bollinger_mr",
    "momentum_energy": "rsi_momentum",
}

# Param spec: (min, max, default, step_hint, type_str)
# step_hint: suggested step for grid; None = use 1 or 0.5 based on type
STRATEGY_PARAM_SPECS: dict[str, dict[str, tuple[float, float, Any, float | None, str]]] = {
    "bollinger_mr": {
        "period": (10.0, 50.0, 20, 5.0, "int"),
        "std_dev": (1.0, 3.0, 2.0, 0.5, "float"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
    "rsi_momentum": {
        "rsi_period": (7.0, 21.0, 14, 1.0, "int"),
        "oversold": (20.0, 40.0, 30.0, 5.0, "float"),
        "overbought": (60.0, 80.0, 70.0, 5.0, "float"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
    "macd_trend": {
        "fast_period": (8.0, 16.0, 12, 2.0, "int"),
        "slow_period": (20.0, 32.0, 26, 2.0, "int"),
        "signal_period": (7.0, 12.0, 9, 1.0, "int"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
    "ema_cross": {
        "fast_ema_period": (5.0, 12.0, 10, 2.0, "int"),   # must be < slow
        "slow_ema_period": (15.0, 30.0, 20, 5.0, "int"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
    "ema_cross_long": {
        "fast_ema_period": (5.0, 12.0, 10, 2.0, "int"),
        "slow_ema_period": (15.0, 30.0, 20, 5.0, "int"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
    "ema_cross_trailing": {
        "fast_ema_period": (5.0, 12.0, 10, 2.0, "int"),
        "slow_ema_period": (15.0, 30.0, 20, 5.0, "int"),
        "atr_period": (10.0, 20.0, 14, 2.0, "int"),
        "trailing_atr_multiple": (1.0, 3.0, 2.0, 0.5, "float"),
        "trade_size": (1.0, 10000.0, 1000, None, "int"),
    },
}

def _resolve_strategy_name(strategy_name: str) -> str:
    """Resolve alias to canonical strategy name."""
    return _ALIAS_TO_CANONICAL.get(strategy_name, strategy_name)


def get_param_specs(strategy_name: str) -> dict[str, tuple[float, float, Any, float | None, str]]:
    """Return param specs for strategy. Raises KeyError for unknown strategies.

    Built-in specs in :data:`STRATEGY_PARAM_SPECS` are merged with any extra specs
    loaded from the YAML file at ``DIGIQUANT_STRATEGY_SPECS_PATH``; YAML specs take
    precedence for overlapping param names.
    """
    canonical = _resolve_strategy_name(strategy_name)
    yaml_specs = _load_yaml_specs()
    combined = dict(STRATEGY_PARAM_SPECS)
    for strat, params in yaml_specs.items():
        if strat in combined:
            combined[strat] = {**combined[strat], **params}
        else:
            combined[strat] = params  # type: ignore[assignment]
    if canonical not in combined:
        raise KeyError(
            f"Unknown strategy: {strategy_name}. No param specs. Registered: {list(combined.keys())}."
        )
    return dict(combined[canonical])


def infer_param_grid(
    strategy_name: str,
    base_params: dict[str, float | int | str] | None = None,
    num_points_per_param: int = 3,
    exclude_params: set[str] | None = None,
) -> list[dict[str, float | int | str]]:
    """
    Auto-generate param grid from strategy specs.
    Uses num_points_per_param values per param (linear spacing).
    base_params are merged; exclude_params (e.g. trade_size) skipped for grid.
    """
    exclude = exclude_params or {"trade_size"}
    specs = get_param_specs(strategy_name)
    base = dict(base_params or {})

    param_values: dict[str, list[float | int | str]] = {}
    for name, (lo, hi, default, step_hint, type_str) in specs.items():
        if name in exclude:
            continue
        if num_points_per_param <= 1:
            # Degenerate case: return a single default value for every param
            param_values[name] = [default]
            continue
        if type_str == "int":
            lo, hi = int(lo), int(hi)
            step = step_hint if step_hint is not None else max(1, (hi - lo) // (num_points_per_param - 1))
            vals = list(range(lo, hi + 1, max(1, int(step))))
            if len(vals) > num_points_per_param:
                # Sample evenly
                idx = [i * (len(vals) - 1) // (num_points_per_param - 1) for i in range(num_points_per_param)]
                vals = [vals[i] for i in idx]
            param_values[name] = vals if vals else [default]
        else:
            vals = [lo + (hi - lo) * i / (num_points_per_param - 1) for i in range(num_points_per_param)]
            param_values[name] = [round(v, 2) for v in vals]

    if not param_values:
        return [base]

    names = list(param_values.keys())
    value_lists = [param_values[n] for n in names]
    # Guard against combinatorial explosion before materialising the full product.
    estimated_size = 1
    for vl in value_lists:
        estimated_size *= len(vl)
    if estimated_size > MAX_GRID_SIZE:
        raise ValueError(
            f"Param grid would have {estimated_size:,} combinations, exceeding MAX_GRID_SIZE={MAX_GRID_SIZE:,}. "
            f"Reduce num_points_per_param, add more exclude_params, or use method='bayesian'."
        )
    grids: list[dict[str, float | int | str]] = []
    for combo in itertools.product(*value_lists):
        grids.append({**base, **dict(zip(names, combo))})
    logger.debug("Generated param grid: %d combinations for strategy '%s'", len(grids), strategy_name)
    return grids


def sample_random_params(
    strategy_name: str,
    n: int,
    base_params: dict[str, float | int | str] | None = None,
    exclude_params: set[str] | None = None,
    rng: random.Random | None = None,
) -> list[dict[str, float | int | str]]:
    """Sample n random param combinations from strategy search space."""
    rng = rng or random.Random()
    exclude = exclude_params or {"trade_size"}
    specs = get_param_specs(strategy_name)
    base = dict(base_params or {})

    grids: list[dict[str, float | int | str]] = []
    for _ in range(n):
        params = dict(base)
        for name, (lo, hi, default, _step, type_str) in specs.items():
            if name in exclude:
                continue
            if type_str == "int":
                params[name] = rng.randint(int(lo), int(hi))
            else:
                params[name] = round(rng.uniform(lo, hi), 2)
        grids.append(params)
    return grids


def get_search_space_for_optuna(
    strategy_name: str,
    base_params: dict[str, float | int | str] | None = None,
    exclude_params: set[str] | None = None,
) -> dict[str, tuple[str, Any, Any, Any]]:
    """
    Return Optuna-compatible search space: {param_name: (suggest_type, low, high, step)}.
    For trial.suggest_int(name, low, high) or trial.suggest_float(name, low, high, step=step).
    """
    exclude = exclude_params or {"trade_size"}
    specs = get_param_specs(strategy_name)
    base = dict(base_params or {})
    space: dict[str, tuple[str, Any, Any, Any]] = {}

    for name, (lo, hi, _default, step_hint, type_str) in specs.items():
        if name in exclude or name in base:
            continue
        if type_str == "int":
            step = 1 if step_hint is None else int(step_hint)
            space[name] = ("int", int(lo), int(hi), step)
        else:
            step = 0.1 if step_hint is None else step_hint
            space[name] = ("float", lo, hi, step)
    return space
