"""Audit payload redaction (shared across DigiGraph, DigiClaw, DigiQuant)."""

from __future__ import annotations

from typing import Any

DEFAULT_REDACT_SUBSTRINGS = ("password", "api_key", "token", "secret")


def _key_is_sensitive(key: str, keys: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(r in lowered for r in keys)


def redact_mapping(
    payload: dict[str, Any],
    redact: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of *payload* with sensitive keys replaced by ``[REDACTED]`` (recursive)."""
    keys = tuple(redact) if redact is not None else DEFAULT_REDACT_SUBSTRINGS
    out: dict[str, Any] = {}
    for key, value in payload.items():
        if _key_is_sensitive(key, keys):
            out[key] = "[REDACTED]"
            continue
        if isinstance(value, dict):
            out[key] = redact_mapping(value, redact=keys)
        elif isinstance(value, list):
            out[key] = [
                redact_mapping(item, redact=keys) if isinstance(item, dict) else item for item in value
            ]
        else:
            out[key] = value
    return out


__all__ = ["DEFAULT_REDACT_SUBSTRINGS", "redact_mapping"]
