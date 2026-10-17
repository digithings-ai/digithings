"""The strategy lab: the asset-neutral front door to the digiquant engine.

This package is the reusable strategy-building toolkit. Every technique the
BTC and gold books were built on -- dataset assembly, time-series
optimization, standardization, z-scoring, re-weighting, gating -- lives here as
a function any asset can call. A new asset is a profile, not a code change.

**The contract, in four rules.**

1. *Importing the package is cheap.* ``import digiquant.strategies.lab``
   imports no submodule of its own -- it does not build a ``TypeAdapter``, does
   not configure a logger, and does not register a strategy. Every submodule is
   resolved on first attribute access.

   Read that precisely, because the parent package is not under this file's
   control: ``digiquant.strategies.__init__`` imports the Nautilus wrapper
   whenever ``nautilus_trader`` is installed, so importing *any* submodule here
   already costs whatever the parent costs. What this package guarantees, and
   what ``test_lab_facade.py`` measures, is that the facade adds **nothing** on
   top of that baseline -- and that touching every curated name pulls in no
   Nautilus module at all.
2. *Module identity is preserved.* ``lab.backtest`` *is* the module object that
   ``import digiquant.strategies.lab.backtest`` returns, so ``mock.patch`` on
   either path patches one object. This is why the facade resolves rather than
   re-implements: a re-export would fork the identity the compatibility shim in
   :mod:`digiquant.strategies.sdca` depends on.
3. *The curated names are unambiguous by construction.* The names re-exported
   at this level come from modules that do not collide with each other. Eight
   public names in this package are defined in more than one module --
   ``load_coefficients`` and ``save_coefficients`` (``btc_power_law`` vs
   ``generic_valuation``), ``causal_rolling_z`` (``composite_risk`` vs
   ``indicator_catalog``), ``QuantileCoefficients`` and
   ``MIN_FIT_HISTORY_DAYS`` (``btc_power_law`` vs ``quantile_rails``),
   ``DEFAULT_ROLLING_WINDOW``, ``DEFAULT_TRIAL_CASH`` and ``logger``. Hoisting
   any of them would silently pick a side, so they are reachable only through
   their module and ``tests/dq/strategies/sdca/test_lab_facade.py`` refuses to
   let one back in.
4. *Nautilus lives behind one door.* ``nautilus_strategy`` and
   ``nautilus_evaluator`` import ``nautilus_trader`` at module import time, so
   no curated name is drawn from either. Reach them as
   ``lab.nautilus_strategy.SdcaStrategy`` when you actually want the Nautilus
   wrapper; the rest of the toolkit works with the ``nautilus`` extra absent.

**Why a regular package.** A namespace package cannot carry ``__getattr__``, so
the facade needs this file. Nothing else changes: the directory stays flat (the
engine resolves resources with ``Path(__file__).resolve().parents[1] /
"settings.json"``, which reads a *module* file and is unaffected by a sibling
``__init__.py``), and setuptools' ``packages.find`` discovers the package either
way.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

#: Curated public surface: ``name -> (submodule, attribute)``.
#:
#: Every entry is resolved lazily through its module, never cached, so
#: ``lab.run_backtest is lab.backtest.run_backtest`` holds even after the
#: underlying module is patched. Adding a name here is a contract change: it
#: must be unambiguous across the 38 modules and it must come from a module
#: that does not import Nautilus at import time.
_NAMES: dict[str, tuple[str, str]] = {
    # -- asset profiles: a new asset is data ---------------------------------
    "SdcaAssetProfile": ("asset_profile", "SdcaAssetProfile"),
    "register_profile": ("asset_profile", "register_profile"),
    "get_profile": ("asset_profile", "get_profile"),
    "list_profiles": ("asset_profile", "list_profiles"),
    # -- research: assembling a dataset --------------------------------------
    "load_sdca_ohlcv": ("optimize", "load_sdca_ohlcv"),
    "load_sdca_extra_sources": ("optimize", "load_sdca_extra_sources"),
    "load_sdca_extra_z": ("optimize", "load_sdca_extra_z"),
    "technicals_from_ohlcv": ("asset_profile", "technicals_from_ohlcv"),
    "daily_closes_from_cache": ("asset_profile", "daily_closes_from_cache"),
    "union_date_range": ("asset_profile", "union_date_range"),
    # -- cycles, oscillators, composite weights ------------------------------
    "SdcaCycleWindows": ("cycle_windows", "SdcaCycleWindows"),
    "CycleKind": ("cycle_windows", "CycleKind"),
    "SdcaOscillatorSpec": ("price_oscillators", "SdcaOscillatorSpec"),
    "SdcaCompositeWeights": ("indicator_catalog", "SdcaCompositeWeights"),
    "parse_indicator_weights_json": ("indicator_catalog", "parse_indicator_weights_json"),
    "composite_weights_from_params": ("indicator_catalog", "composite_weights_from_params"),
    # -- composite risk index ------------------------------------------------
    "IndicatorWeight": ("composite_risk", "IndicatorWeight"),
    "compute_composite_risk": ("composite_risk", "compute_composite_risk"),
    "z_to_risk": ("composite_risk", "z_to_risk"),
    "RiskModel": ("risk_model", "RiskModel"),
    "SdcaRiskModelName": ("providers", "SdcaRiskModelName"),
    "resolve_sdca_risk_model": ("providers", "resolve_sdca_risk_model"),
    "RiskIndexBuildResult": ("risk_index", "RiskIndexBuildResult"),
    "build_risk_index": ("risk_index", "build_risk_index"),
    "write_risk_index": ("risk_index", "write_risk_index"),
    # -- the accumulation/distribution curve ---------------------------------
    "AccumDistCurve": ("curve", "AccumDistCurve"),
    "SdcaCurveShape": ("curve_shape", "SdcaCurveShape"),
    "risk50_linear_reference_curve": ("curve_shape", "risk50_linear_reference_curve"),
    "SdcaPreset": ("presets", "SdcaPreset"),
    "list_presets": ("presets", "list_presets"),
    "load_preset": ("presets", "load_preset"),
    # -- backtest ------------------------------------------------------------
    "SdcaBacktestReport": ("backtest", "SdcaBacktestReport"),
    "run_backtest": ("backtest", "run_backtest"),
    "size_trade": ("backtest", "size_trade"),
    # -- optimize / walk-forward ---------------------------------------------
    "SdcaOptimizeObjective": ("walk_forward", "SdcaOptimizeObjective"),
    "SdcaTrialEvaluator": ("walk_forward", "SdcaTrialEvaluator"),
    "make_walk_forward_folds": ("walk_forward", "make_walk_forward_folds"),
    "evaluate_sdca_trial_curve_sim": ("curve_sim", "evaluate_sdca_trial_curve_sim"),
    "SensitivityReport": ("optimize", "SensitivityReport"),
    "SdcaWalkForwardResult": ("optimize", "SdcaWalkForwardResult"),
    "run_sdca_walk_forward": ("optimize", "run_sdca_walk_forward"),
    # -- two-stage fit / regularize ------------------------------------------
    "freeze_weight_params": ("two_stage", "freeze_weight_params"),
    "run_stage_b_frozen": ("two_stage", "run_stage_b_frozen"),
    "persist_two_stage": ("two_stage", "persist_two_stage"),
    "SdcaTwoStageProvenance": ("two_stage", "SdcaTwoStageProvenance"),
    "regularize_weights": ("regularize", "regularize_weights"),
    "regularize_curve_shape": ("regularize", "regularize_curve_shape"),
    # -- publish: overlays the tearsheet and dashboard read -------------------
    "tearsheet_overlays": ("dca_metrics", "tearsheet_overlays"),
    "dca_current_signal": ("dca_metrics", "dca_current_signal"),
    "flat_dca_mark_to_market": ("dca_metrics", "flat_dca_mark_to_market"),
    "breakdown_from_daily": ("dca_metrics", "breakdown_from_daily"),
    # -- evaluation against the baseline -------------------------------------
    "compare_to_baseline": ("baseline_evaluator", "compare_to_baseline"),
    # -- the golden path: research -> backtest -> optimize -> tearsheet -------
    "research_asset": ("golden_path", "research_asset"),
    "backtest_asset": ("golden_path", "backtest_asset"),
    "optimize_asset": ("golden_path", "optimize_asset"),
    "tearsheet_payload": ("golden_path", "tearsheet_payload"),
    "run_golden_path": ("golden_path", "run_golden_path"),
    "persist_golden_path": ("golden_path", "persist_golden_path"),
    "GoldenPathResult": ("golden_path", "GoldenPathResult"),
    "GoldenPathVerdict": ("golden_path", "GoldenPathVerdict"),
    "ResearchStage": ("golden_path", "ResearchStage"),
    "BacktestStage": ("golden_path", "BacktestStage"),
}

#: Star-import yields the toolkit's API, not the 38 module handles.
__all__ = sorted(_NAMES)

_MODULE_NAMES: frozenset[str] | None = None


def _module_names() -> frozenset[str]:
    """Submodule names on disk, walked once and cached.

    ``pkgutil.iter_modules`` only stats the directory, so this stays cheap and
    does not import anything -- the whole point of the facade.
    """
    global _MODULE_NAMES
    if _MODULE_NAMES is None:
        _MODULE_NAMES = frozenset(mod.name for mod in pkgutil.iter_modules(__path__))
    return _MODULE_NAMES


def __getattr__(name: str) -> Any:
    """Resolve a curated name, then a submodule, lazily and without caching.

    Not caching is deliberate. A cached value would answer from this package
    after the owning module was patched, breaking the identity rule that
    ``lab.x is lab.<module>.x``. Attribute access is not a hot path, and
    ``from digiquant.strategies.lab import run_backtest`` binds once anyway.
    """
    if name.startswith("__"):
        raise AttributeError(name)

    target = _NAMES.get(name)
    if target is not None:
        module_name, attribute = target
        module = importlib.import_module(f"{__name__}.{module_name}")
        return getattr(module, attribute)

    if name in _module_names():
        return importlib.import_module(f"{__name__}.{name}")

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}. "
        "Curated names are listed in __all__; any submodule is reachable by its "
        "own name; ambiguous names must come from their module."
    )


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_NAMES) | set(_module_names()))
