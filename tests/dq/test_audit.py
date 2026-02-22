"""Unit tests for DigiQuant audit logging (Phase 3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.mark.unit
def test_digiquant_audit_log_writes_jsonl_and_redacts(tmp_path: Path) -> None:
    """audit_log appends one JSON line per call; redacts secret keys."""
    audit_path = tmp_path / "events.jsonl"
    os.environ["AUDIT_LOG_PATH"] = str(audit_path)
    try:
        from digiquant.audit import audit_log

        audit_log("run_backtest", agent_id="digiquant", payload={"run_id": "x", "api_key": "secret"})
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_type"] == "run_backtest"
        assert data["agent_id"] == "digiquant"
        assert data["payload"]["run_id"] == "x"
        assert data["payload"]["api_key"] == "[REDACTED]"
    finally:
        os.environ.pop("AUDIT_LOG_PATH", None)


@pytest.mark.unit
def test_api_run_backtest_and_run_optimize_write_audit(tmp_path: Path) -> None:
    """POST /run_backtest and /run_optimize produce audit log entries when Nautilus available."""
    pytest.importorskip("nautilus_trader")
    os.environ["AUDIT_LOG_PATH"] = str(tmp_path / "events.jsonl")
    try:
        from fastapi.testclient import TestClient

        from digiquant.server import app

        client = TestClient(app)
        client.post("/run_backtest", json={"strategy_name": "x", "symbols": ["AAPL"]})
        client.post("/run_optimize", json={"strategy_name": "x", "symbols": ["AAPL"]})
        lines = (tmp_path / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) >= 2
        event_types = [json.loads(ln)["event_type"] for ln in lines]
        assert "run_backtest" in event_types
        assert "run_optimize" in event_types
    finally:
        os.environ.pop("AUDIT_LOG_PATH", None)
