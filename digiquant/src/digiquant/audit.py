"""Audit logging (FINRA 2026). Same JSONL format as digiclaw.audit; no cross-package dep."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_PATH = os.environ.get("AUDIT_LOG_PATH", "digiquant/results/audit/events.jsonl")


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def audit_log(
    event_type: str,
    agent_id: str = "",
    payload: dict[str, Any] | None = None,
    *,
    redact: list[str] | None = None,
    key_prefix: str = "",
    tenant: str = "",
    project_id: str = "",
    jti: str = "",
    path: str = "",
) -> None:
    """Append one audit event to JSONL. Redacts secret keys."""
    payload = payload or {}
    redact = redact or ["password", "api_key", "token", "secret"]
    for key in list(payload.keys()):
        if any(r in key.lower() for r in redact):
            payload[key] = "[REDACTED]"
    event: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload,
    }
    if key_prefix:
        event["key_prefix"] = key_prefix
    if tenant:
        event["tenant"] = tenant
    if project_id:
        event["project_id"] = project_id
    if jti:
        event["jti"] = jti
    if path:
        event["path"] = path
    path = os.environ.get("AUDIT_LOG_PATH", _DEFAULT_PATH)
    _ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
