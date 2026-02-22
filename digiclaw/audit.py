"""
Audit logging for FINRA 2026 / regulatory compliance. Phase 3.
Every MCP call, workflow run, and critical action should be logged (secrets redacted).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default: write to digiquant/results/audit (or AUDIT_LOG_PATH env)
_DEFAULT_PATH = os.environ.get("AUDIT_LOG_PATH", "digiquant/results/audit/events.jsonl")


def _ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def audit_log(
    event_type: str,
    agent_id: str = "",
    payload: dict[str, Any] | None = None,
    *,
    redact: list[str] | None = None,
) -> None:
    """
    Append a single audit event to the JSONL log. Secrets in payload can be redacted by key.
    """
    payload = payload or {}
    redact = redact or ["password", "api_key", "token", "secret"]
    for key in list(payload.keys()):
        if any(r in key.lower() for r in redact):
            payload[key] = "[REDACTED]"
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload,
    }
    path = os.environ.get("AUDIT_LOG_PATH", _DEFAULT_PATH)
    _ensure_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
