"""Centralized policy flags for DigiGraph HTTP and tool execution (enterprise hardening)."""

from __future__ import annotations

import os


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def debug_endpoints_enabled() -> bool:
    """``GET /test_llm``, ``GET /v1/debug/*`` when DIGI_ENABLE_DEBUG_ENDPOINTS is set."""
    return _env_truthy("DIGI_ENABLE_DEBUG_ENDPOINTS")


def thread_api_enabled() -> bool:
    """Thread and file routes when DIGI_ENABLE_THREAD_API is set."""
    return _env_truthy("DIGI_ENABLE_THREAD_API")


def hub_mode() -> str:
    """``legacy`` (default): monolith graph + inline tools; ``federated``: hub delegates to vertical HTTP."""
    return os.environ.get("DIGI_HUB_MODE", "legacy").strip().lower()


def federated_hub_enabled() -> bool:
    """True when ``DIGI_HUB_MODE=federated`` (connector delegate tools registered)."""
    return hub_mode() == "federated"


def code_execution_allowed() -> bool:
    """Sandboxed code paths (e.g. data_engineer) when DIGI_ALLOW_CODE_EXEC is set."""
    return _env_truthy("DIGI_ALLOW_CODE_EXEC")


__all__ = [
    "code_execution_allowed",
    "debug_endpoints_enabled",
    "federated_hub_enabled",
    "hub_mode",
    "thread_api_enabled",
]
