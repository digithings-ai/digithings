"""
Audit logging for FINRA 2026 / regulatory compliance.

Thin wrapper over digibase.audit.emit_event (sole JSONL + optional sink emitter).
Heartbeat event *types* and payload shapes are unchanged (#1193 out of scope).
"""

from __future__ import annotations

from typing import Any

from digibase.audit import emit_event


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
    Append a single audit event via digibase. Secrets in payload are redacted by key.
    Optional digikey trace fields are written at the top level when non-empty.
    """
    emit_event(
        event_type,
        agent_id=agent_id,
        payload=payload,
        redact=redact,
        key_prefix=key_prefix,
        tenant=tenant,
        project_id=project_id,
        jti=jti,
        path=path,
    )
