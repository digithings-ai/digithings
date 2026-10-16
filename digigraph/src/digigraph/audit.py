"""Audit logging for digigraph — thin wrapper over digibase.audit.emit_event."""

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
    """Append one audit event via the digibase emitter. Redacts secret keys."""
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
