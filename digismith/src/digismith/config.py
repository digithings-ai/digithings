"""Environment-driven tracing configuration (no secrets in API responses)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from pydantic import BaseModel, Field


def default_langsmith_endpoint() -> str:
    """Return LANGSMITH_ENDPOINT or LangSmith default API URL."""
    return os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").strip()


def langsmith_sdk_importable() -> bool:
    try:
        import langsmith  # noqa: F401

        return True
    except ImportError:
        return False


def tracing_enabled() -> bool:
    """True when an API key is set and the langsmith package is installed."""
    key = (os.environ.get("LANGSMITH_API_KEY") or "").strip()
    return bool(key) and langsmith_sdk_importable()


def langsmith_host_sanitized() -> str | None:
    """Hostname of the configured LangSmith API (no path, credentials, or query)."""
    raw = default_langsmith_endpoint()
    if not raw:
        return None
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname
    return host


class SmithStatus(BaseModel):
    """Public status for GET /v1/status."""

    version: str = Field(description="DigiSmith package version")
    tracing_configured: bool = Field(
        description="LangSmith tracing would activate (key + langsmith installed)"
    )
    langsmith_sdk_installed: bool = Field(description="langsmith Python package is importable")
    langsmith_host: str | None = Field(
        default=None,
        description="Sanitized API host from LANGSMITH_ENDPOINT (no secrets)",
    )
    request_id: str | None = Field(
        default=None,
        description="X-Request-ID of the call that produced this status (echoed for correlation)",
    )
