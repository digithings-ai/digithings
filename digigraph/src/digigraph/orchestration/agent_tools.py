"""Session analytics agent tool handlers (visualization / analysis / data_*)."""

from __future__ import annotations

from typing import Any

from digigraph.orchestration.registry import ToolContext


def _handle_visualization(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.orchestration import builtin as _reg

    result = _reg.run_visualization_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_analysis(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.orchestration import builtin as _reg

    result = _reg.run_analysis_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_prep(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.orchestration import builtin as _reg

    result = _reg.run_data_prep_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_manipulation(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.orchestration import builtin as _reg

    result = _reg.run_data_manipulation_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        second_dataset_ref=args.get("second_dataset_ref"),
        options=args.get("options"),
    )
    return {"content": result}


def _handle_data_engineer(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.orchestration import builtin as _reg

    result = _reg.run_data_engineer_agent(
        dataset_ref=args.get("dataset_ref", ""),
        task=args.get("task", ""),
        session_id=context.session_id,
        additional_dataset_refs=args.get("additional_dataset_refs"),
        options=args.get("options"),
    )
    return {"content": result}
