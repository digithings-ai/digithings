"""digistore list/profile built-in tools."""

from __future__ import annotations

import json
from typing import Any

from digigraph.orchestration.registry import ToolContext

DIGISTORE_LIST_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_list",
        "description": "List datasets stored in this session (read-only). Returns name and row_count for each. Use to discover available dataset_refs before calling visualization_agent, analysis_agent, or data_manipulation_agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "include_row_count": {
                    "type": "boolean",
                    "description": "Include row count per dataset (default true).",
                },
            },
        },
    },
}

DIGISTORE_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "digistore_profile",
        "description": "Get schema and sample rows for a stored dataset (read-only). Use to inspect columns and sample data before visualization or manipulation.",
        "parameters": {
            "type": "object",
            "properties": {
                "dataset_ref": {
                    "type": "string",
                    "description": "Dataset name or ref (e.g. search_1) from digistore_list or a previous search result.",
                },
                "sample_size": {
                    "type": "integer",
                    "description": "Number of sample rows to return (default 5).",
                },
            },
            "required": ["dataset_ref"],
        },
    },
}


def _handle_digistore_list(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_list

    include_row_count = args.get("include_row_count", True)
    datasets = digistore_list(context.session_id, include_row_count=include_row_count)
    return {"content": json.dumps({"datasets": datasets})}


def _handle_digistore_profile(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from digigraph.digistore import digistore_profile

    ref = args.get("dataset_ref")
    if not ref or not str(ref).strip():
        return {"content": json.dumps({"error": "dataset_ref is required."})}
    sample_size = args.get("sample_size", 5)
    try:
        profile = digistore_profile(context.session_id, str(ref), sample_size=sample_size)
        return {"content": json.dumps(profile)}
    except ValueError as e:
        return {"content": json.dumps({"error": str(e)})}
