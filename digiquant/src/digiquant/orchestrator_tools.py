"""OpenAI-style orchestrator tool definitions for digiquant.

digigraph fetches these via ``POST /v1/orchestrator_tools`` and executes via
``POST /v1/orchestrator_invoke`` so quant tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any


def _pipeline_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "strategy_name": {"type": "string", "description": "Registered strategy name"},
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ticker symbols",
            },
            "data_path": {"type": "string", "description": "Single OHLCV CSV path (optional)"},
            "data_dir": {"type": "string", "description": "Directory of {SYMBOL}.csv (optional)"},
            "strategy_params": {"type": "object", "description": "Optional initial params"},
            "export_target": {"type": "string", "description": "e.g. nautilus"},
            "run_optimize": {"type": "boolean", "default": True},
            "run_export": {"type": "boolean", "default": True},
            "method": {"type": "string", "default": "grid"},
            "n_trials": {"type": "integer", "default": 50},
            "constraints": {"type": "object", "description": "OptimizationConstraints fields"},
        },
        "required": ["strategy_name", "symbols"],
    }


def build_digiquant_list_strategies_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_list_strategies",
            "description": "List registered Nautilus strategies (name, aliases, description, default_params).",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def build_digiquant_run_backtest_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_backtest",
            "description": "Run a Nautilus backtest for a strategy and symbols. Requires data_path or data_dir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                    "data_path": {"type": "string"},
                    "data_dir": {"type": "string"},
                    "strategy_params": {"type": "object"},
                    "tearsheet_path": {"type": "string"},
                    "full_tearsheet": {"type": "boolean", "default": True},
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def build_digiquant_run_optimize_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_optimize",
            "description": (
                "Run parameter optimization (grid, bayesian, random). "
                "strategy_name='sdca' is Stage B walk-forward (vs-flat-DCA); "
                "freeze Stage A weights via strategy_params *_weight keys. "
                "Requires data_path or data_dir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                    "data_path": {"type": "string"},
                    "data_dir": {"type": "string"},
                    "param_grid": {"type": "array", "items": {"type": "object"}},
                    "method": {"type": "string", "default": "grid"},
                    "n_trials": {"type": "integer", "default": 50},
                    "objective": {"type": "string", "default": "sharpe"},
                    "constraints": {"type": "object"},
                    "strategy_params": {
                        "type": "object",
                        "description": (
                            "Base/frozen params. For sdca Stage B, pass "
                            "valuation_weight / weekly_rsi_weight / ... from "
                            "digiquant_fit_sdca_weights.regularized_weight_params."
                        ),
                    },
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def build_digiquant_run_export_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_export",
            "description": "Export strategy + params to a target artifact (e.g. nautilus).",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "params": {"type": "object", "description": "Best params from optimize"},
                    "target": {"type": "string", "default": "nautilus"},
                },
                "required": ["strategy_name"],
            },
        },
    }


def build_digiquant_run_pipeline_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_pipeline",
            "description": "Run validate → backtest → optional optimize → optional export via internal LangGraph pipeline.",
            "parameters": _pipeline_parameters(),
        },
    }


def build_digiquant_pipeline_delegate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_pipeline_delegate",
            "description": "digigraph hub alias for digiquant_run_pipeline (same HTTP /v1/workflow behavior).",
            "parameters": _pipeline_parameters(),
        },
    }



def build_digiquant_fetch_coinbase_ohlcv_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_coinbase_ohlcv",
            "description": (
                "Fetch daily OHLCV from Coinbase (CCXT) into the price-history "
                "cache. Fail-soft per symbol."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols_json": {
                        "type": "string",
                        "description": "JSON array of CCXT symbols, e.g. [\"BTC/USD\"]",
                    },
                    "start": {"type": "string"},
                    "cache_dir": {"type": "string"},
                },
            },
        },
    }


def build_digiquant_fit_btc_power_law_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fit_btc_power_law",
            "description": (
                "Fit SDCA BTC power-law (RAQQR) rails from cached daily prices "
                "via history_cache.py (not a bespoke fetch)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "default": "BTC-USD"},
                    "cache_dir": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                    "output_path": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
        },
    }


def build_digiquant_build_sdca_risk_index_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_build_sdca_risk_index",
            "description": (
                "Build the SDCA date/risk parquet from a RiskModel + cached "
                "prices. profile=btc_v1|eth_research_v1 applies SdcaAssetProfile "
                "rails/oscillators/allowlist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "default": "BTC-USD"},
                    "cache_dir": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                    "risk_model": {"type": "string", "default": "btc_power_law"},
                    "profile": {"type": "string"},
                    "profile_json": {"type": "string"},
                    "coefficients_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "indicator_weights": {"type": "string", "default": "{}"},
                    "m2_path": {"type": "string"},
                    "dxy_path": {"type": "string"},
                    "eth_ticker": {"type": "string", "default": "ETH-USD"},
                    "valuation_form": {"type": "string", "default": "log_quadratic"},
                    "rolling_window": {"type": "integer", "default": 90},
                },
            },
        },
    }


def build_digiquant_fetch_bitview_series_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_bitview_series",
            "description": (
                "Fetch Bitview/BRK on-chain day1 series (mvrv, asopr_24h, "
                "puell_multiple, rhodl_ratio) into data/onchain/bitview. "
                "JSON API only; nupl refused (dual-count). Fail-soft. "
                "CM community CC BY-NC is not fetched. Refs #1086."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series_ids_json": {
                        "type": "string",
                        "description": "JSON array of BRK series ids",
                    },
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "number", "default": 30},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                },
            },
        },
    }


def build_digiquant_fit_sdca_weights_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fit_sdca_weights",
            "description": (
                "Stage A: fit SDCA composite weights so risk overlaps the "
                "asset's cycle windows, then regularize. Stage B is "
                "digiquant_run_optimize strategy_name=sdca. Not a second "
                "optimizer product. No live-trading."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "default": "btc_v1"},
                    "profile_json": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "coefficients_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "m2_path": {"type": "string"},
                    "dxy_path": {"type": "string"},
                    "eth_ticker": {"type": "string", "default": "ETH-USD"},
                    "valuation_form": {"type": "string", "default": "log_quadratic"},
                    "rolling_window": {"type": "integer", "default": 90},
                },
            },
        },
    }


def build_dashboard_run_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_run_policy_replay",
            "description": (
                "Register a policy replay run against a stored pair. Returns summary "
                "IDs/status only. Never activates or promotes production policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pair_content_hash": {
                        "type": "string",
                        "description": "64-hex content hash of a stored ReplayPairSpec",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional stable run id (generated if omitted)",
                    },
                },
                "required": ["pair_content_hash"],
            },
        },
    }


def build_dashboard_get_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_replay",
            "description": "Fetch a policy replay run summary by run_id (fail closed if unknown).",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                },
                "required": ["run_id"],
            },
        },
    }


def build_dashboard_get_policy_comparison_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_comparison",
            "description": (
                "Fetch a policy comparison summary (artifact IDs and status only — "
                "no confidential evidence)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison_id": {"type": "string"},
                },
                "required": ["comparison_id"],
            },
        },
    }


def build_dashboard_evaluate_policy_gate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_evaluate_policy_gate",
            "description": (
                "Evaluate immutable human-authored gate criteria against a comparison. "
                "Returns eligibility for human review only — never activates policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison_id": {"type": "string"},
                    "criteria_version_id": {"type": "string"},
                },
                "required": ["comparison_id", "criteria_version_id"],
            },
        },
    }


def build_dashboard_get_policy_gate_evaluation_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_gate_evaluation",
            "description": "Fetch a gate-evaluation summary by evaluation_id (fail closed if unknown).",
            "parameters": {
                "type": "object",
                "properties": {
                    "evaluation_id": {"type": "string"},
                },
                "required": ["evaluation_id"],
            },
        },
    }


def build_orchestrator_tool_manifest() -> list[dict[str, Any]]:
    """Return the full digiquant orchestrator tool surface."""
    return [
        build_digiquant_list_strategies_tool(),
        build_digiquant_run_backtest_tool(),
        build_digiquant_run_optimize_tool(),
        build_digiquant_run_export_tool(),
        build_digiquant_run_pipeline_tool(),
        build_digiquant_pipeline_delegate_tool(),
        build_digiquant_fetch_coinbase_ohlcv_tool(),
        build_digiquant_fit_btc_power_law_tool(),
        build_digiquant_build_sdca_risk_index_tool(),
        build_digiquant_fetch_bitview_series_tool(),
        build_digiquant_fit_sdca_weights_tool(),
        build_dashboard_run_policy_replay_tool(),
        build_dashboard_get_policy_replay_tool(),
        build_dashboard_get_policy_comparison_tool(),
        build_dashboard_evaluate_policy_gate_tool(),
        build_dashboard_get_policy_gate_evaluation_tool(),
    ]
