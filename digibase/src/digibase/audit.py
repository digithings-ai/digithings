"""Audit payload redaction (shared across DigiGraph, DigiClaw, DigiQuant)."""

from __future__ import annotations

from typing import Any

DEFAULT_REDACT_SUBSTRINGS = ("password", "api_key", "token", "secret")


def redact_mapping(
    payload: dict[str, Any],
    redact: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Return a copy of *payload* with sensitive keys replaced by ``[REDACTED]``."""
    keys = tuple(redact) if redact is not None else DEFAULT_REDACT_SUBSTRINGS
    out = dict(payload)
    for key in list(out.keys()):
        if any(r in key.lower() for r in keys):
            out[key] = "[REDACTED]"
    return out


__all__ = ["DEFAULT_REDACT_SUBSTRINGS", "redact_mapping"]
