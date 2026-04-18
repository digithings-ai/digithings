"""Audit logging (FINRA 2026). Same JSONL format as digiclaw; no cross-package dep."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from digibase.audit import redact_mapping
from digibase.util import ensure_dir

_DEFAULT_PATH = os.environ.get("AUDIT_LOG_PATH", "digiquant/results/audit/events.jsonl")


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
    r_tuple = tuple(redact) if redact else None
    payload = redact_mapping(dict(payload or {}), redact=r_tuple)
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
    ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
