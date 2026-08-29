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
            "description": "Run parameter optimization (grid, bayesian, random). Requires data_path or data_dir.",
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


def build_olympus_run_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "olympus_run_policy_replay",
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


def build_olympus_get_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "olympus_get_policy_replay",
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


def build_olympus_get_policy_comparison_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "olympus_get_policy_comparison",
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


def build_olympus_evaluate_policy_gate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "olympus_evaluate_policy_gate",
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


def build_olympus_get_policy_gate_evaluation_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "olympus_get_policy_gate_evaluation",
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
        build_olympus_run_policy_replay_tool(),
        build_olympus_get_policy_replay_tool(),
        build_olympus_get_policy_comparison_tool(),
        build_olympus_evaluate_policy_gate_tool(),
        build_olympus_get_policy_gate_evaluation_tool(),
    ]
