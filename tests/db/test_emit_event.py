"""Unit tests for digibase.audit.emit_event (CHR-151 / #1193)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digibase.audit import AuditEvent, emit_event
from pydantic import ValidationError


@pytest.mark.unit
def test_emit_event_writes_jsonl_and_returns_model(tmp_path: Path) -> None:
    """emit_event appends one JSON line and returns a validated AuditEvent."""
    dest = tmp_path / "events.jsonl"
    event = emit_event(
        "workflow_start",
        agent_id="digigraph",
        payload={"workflow_id": "w-1", "request_id": "r-1"},
        key_prefix="dgk_ab",
        tenant="default",
        log_path=str(dest),
    )
    assert isinstance(event, AuditEvent)
    assert event.event_type == "workflow_start"
    assert event.agent_id == "digigraph"
    assert event.payload == {"workflow_id": "w-1", "request_id": "r-1"}
    assert event.key_prefix == "dgk_ab"
    assert event.tenant == "default"
    assert event.jti is None

    lines = dest.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    # Wire shape: required keys present; empty optionals omitted.
    assert set(data.keys()) == {
        "ts",
        "event_type",
        "agent_id",
        "payload",
        "key_prefix",
        "tenant",
    }
    assert data["event_type"] == "workflow_start"
    assert data["agent_id"] == "digigraph"
    assert data["payload"]["workflow_id"] == "w-1"
    assert "jti" not in data
    assert "path" not in data
    # Round-trip through the Pydantic schema.
    AuditEvent.model_validate(data)


@pytest.mark.unit
def test_emit_event_redacts_secrets_no_pii_leak(tmp_path: Path) -> None:
    """Default payloads redact secret-bearing keys before persistence."""
    dest = tmp_path / "events.jsonl"
    event = emit_event(
        "run_backtest",
        agent_id="digiquant",
        payload={
            "run_id": "x",
            "api_key": "sk-live-should-not-leak",
            "access_token": "bearer-secret",
            "nested": {"password": "hunter2", "ok": True},
        },
        log_path=str(dest),
    )
    assert event.payload["api_key"] == "[REDACTED]"
    assert event.payload["access_token"] == "[REDACTED]"
    assert event.payload["nested"]["password"] == "[REDACTED]"
    assert event.payload["nested"]["ok"] is True
    assert event.payload["run_id"] == "x"

    raw = dest.read_text()
    assert "sk-live-should-not-leak" not in raw
    assert "bearer-secret" not in raw
    assert "hunter2" not in raw
    assert "[REDACTED]" in raw


@pytest.mark.unit
def test_audit_event_rejects_unknown_fields() -> None:
    """Schema is closed — stray keys fail validation (extra=forbid)."""
    with pytest.raises(ValidationError):
        AuditEvent.model_validate(
            {
                "ts": "2026-01-01T00:00:00+00:00",
                "event_type": "x",
                "agent_id": "",
                "payload": {},
                "email": "user@example.com",
            }
        )
