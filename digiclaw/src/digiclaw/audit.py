"""
Audit logging for FINRA 2026 / regulatory compliance. Phase 3.
Every MCP call, workflow run, and critical action should be logged (secrets redacted).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
import urllib.error
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from digibase.audit import redact_mapping
from digibase.util import ensure_dir

# Default: write to digiquant/results/audit (or AUDIT_LOG_PATH env)
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
    """
    Append a single audit event to the JSONL log. Secrets in payload can be redacted by key.
    Optional DigiKey trace fields are written at the top level when non-empty.
    """
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
    line = json.dumps(event) + "\n"
    with open(path, "a", encoding="utf-8") as f:
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
