"""Unit tests for DigiClaw audit logging (Phase 3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.mark.unit
def test_audit_log_writes_jsonl(tmp_path: Path) -> None:
    """audit_log appends one JSON line per call; redacts secret keys."""
    os.environ["AUDIT_LOG_PATH"] = str(tmp_path / "events.jsonl")
    try:
        from digiclaw.audit import audit_log

        audit_log("test_event", agent_id="test_agent", payload={"foo": "bar", "api_key": "secret"})
        lines = (tmp_path / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_type"] == "test_event"
        assert data["agent_id"] == "test_agent"
        assert data["payload"]["foo"] == "bar"
        assert data["payload"]["api_key"] == "[REDACTED]"
    finally:
        os.environ.pop("AUDIT_LOG_PATH", None)
