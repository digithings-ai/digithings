"""Integration-style tests for DigiClaw heartbeat (Phase 3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.mark.unit
def test_run_heartbeat_writes_heartbeat_event_to_audit(tmp_path: Path) -> None:
    """run_heartbeat writes a heartbeat event to AUDIT_LOG_PATH with digigraph_ok and digiquant_ok."""
    audit_path = tmp_path / "events.jsonl"
    os.environ["AUDIT_LOG_PATH"] = str(audit_path)
    os.environ["DIGIGRAPH_URL"] = "http://127.0.0.1:8000"
    os.environ["DIGIQUANT_URL"] = "http://127.0.0.1:8001"
    try:
        from digiclaw.heartbeat_runner import run_heartbeat

        run_heartbeat()
        assert audit_path.exists()
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        data = json.loads(lines[-1])
        assert data["event_type"] == "heartbeat"
        assert data["agent_id"] == "heartbeat_runner"
        assert "digigraph_ok" in data["payload"]
        assert "digiquant_ok" in data["payload"]
    finally:
        os.environ.pop("AUDIT_LOG_PATH", None)
        os.environ.pop("DIGIGRAPH_URL", None)
        os.environ.pop("DIGIQUANT_URL", None)
