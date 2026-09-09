"""Audit payload redaction and JSONL event emission (shared fleet-wide)."""

from __future__ import annotations

import json
import os
import urllib.error
from datetime import datetime, timezone
from typing import Any
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, Field

from digibase.util import ensure_dir

DEFAULT_REDACT_SUBSTRINGS = ("password", "api_key", "token", "secret")
_DEFAULT_LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "digiquant/results/audit/events.jsonl")


def _key_is_sensitive(key: str, keys: tuple[str, ...]) -> bool:
    lowered = key.lower()
    return any(r in lowered for r in keys)


def _redact_value(value: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(value, dict):
        return redact_mapping(value, redact=keys)
    if isinstance(value, list):
        return [_redact_value(item, keys) for item in value]
    return value


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
        else:
            out[key] = _redact_value(value, keys)
    return out


class AuditEvent(BaseModel):
    """Canonical audit JSONL line schema (FINRA 2026 / regulatory trail).

    Optional digikey correlation fields are omitted from the wire dict when empty
    so existing consumers keep a stable, sparse shape.
    """

    model_config = ConfigDict(extra="forbid")

    ts: str = Field(..., description="UTC ISO-8601 timestamp when the event was emitted")
    event_type: str = Field(..., description="Stable event name, e.g. workflow_start")
    agent_id: str = Field(default="", description="Emitting agent or service id")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Redacted event details — never raw prompts, JWTs, or document bodies",
    )
    key_prefix: str | None = Field(default=None, description="digikey API key prefix (not secret)")
    tenant: str | None = Field(default=None, description="Tenant id from digikey JWT")
    project_id: str | None = Field(default=None, description="Project id from digikey JWT")
    jti: str | None = Field(default=None, description="JWT id for post-hoc correlation")
    path: str | None = Field(
        default=None,
        description="Optional request path correlation (not the audit log file path)",
    )

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Serialize for append — drop unset optional correlation fields."""
        return self.model_dump(exclude_none=True)


def emit_event(
    event_type: str,
    agent_id: str = "",
    payload: dict[str, Any] | None = None,
    *,
    redact: list[str] | tuple[str, ...] | None = None,
    key_prefix: str = "",
    tenant: str = "",
    project_id: str = "",
    jti: str = "",
    path: str = "",
    log_path: str | None = None,
) -> AuditEvent:
    """Append one redacted audit event to the JSONL log (sole fleet emitter).

    Secrets in *payload* are redacted via :func:`redact_mapping` before persistence.
    When ``AUDIT_SINK_URL`` is set, a best-effort fire-and-forget POST mirrors the
    same NDJSON line (failures are swallowed so callers are not blocked).

    Component ``audit_log`` helpers must call this function rather than writing
    their own JSONL emitters.
    """
    r_tuple = tuple(redact) if redact else None
    safe_payload = redact_mapping(dict(payload or {}), redact=r_tuple)
    event = AuditEvent(
        ts=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        agent_id=agent_id,
        payload=safe_payload,
        key_prefix=key_prefix or None,
        tenant=tenant or None,
        project_id=project_id or None,
        jti=jti or None,
        path=path or None,
    )
    wire = event.to_jsonl_dict()
    dest = log_path or os.environ.get("AUDIT_LOG_PATH", _DEFAULT_LOG_PATH)
    ensure_dir(dest)
    line = json.dumps(wire) + "\n"
    with open(dest, "a", encoding="utf-8") as f:
        f.write(line)

    sink = (os.environ.get("AUDIT_SINK_URL") or "").strip()
    if sink:
        try:
            req = UrlRequest(
                sink,
                data=line.encode("utf-8"),
                headers={"Content-Type": "application/x-ndjson"},
                method="POST",
            )
            urlopen(req, timeout=3)
        except (OSError, urllib.error.URLError, ValueError):
            # AUDIT_SINK_URL is fire-and-forget — local JSONL write already succeeded.
            pass
    return event


__all__ = [
    "DEFAULT_REDACT_SUBSTRINGS",
    "AuditEvent",
    "emit_event",
    "redact_mapping",
]
