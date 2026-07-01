"""Shared helpers for sub-agent runners."""

from __future__ import annotations

import json
from typing import Any, Callable  # noqa: ANN401 — tool runner JSON payloads

from digigraph.run_storage import resolve_dataset_ref

_DATASET_REF_ERRORS = (ValueError, OSError, FileNotFoundError)
_TOOL_ERRORS = (
    ValueError,
    OSError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    RuntimeError,
)


def load_dataset_path(session_id: str | None, dataset_ref: str) -> tuple[str | None, str | None]:
    """Return ``(path, error_json)``. On success ``error_json`` is None."""
    try:
        return str(resolve_dataset_ref(session_id, dataset_ref)), None
    except _DATASET_REF_ERRORS as e:
        return None, json.dumps({"error": str(e)})


def run_tool_safe(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return fn()
    except _TOOL_ERRORS as e:
        return {"error": str(e)}


def finalize_agent_output(
    last_tool_output: dict[str, Any] | None,
    content: str | None,
    *,
    no_tool_error: str,
    fallback_message: str,
) -> str:
    if last_tool_output is not None:
        payload = dict(last_tool_output)
        if content and isinstance(content, str) and content.strip():
            payload["message"] = content.strip()
        return json.dumps(payload, default=str)
    return json.dumps({"error": no_tool_error, "message": (content or fallback_message)})
