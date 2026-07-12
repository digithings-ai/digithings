"""Unit tests for DigiQuant audit logging (Phase 3)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.dq.conftest import SKIP_NATIVE_CRASH


@pytest.mark.unit
def test_digiquant_audit_log_writes_jsonl_and_redacts(tmp_path: Path) -> None:
    """audit_log appends one JSON line per call; redacts secret keys."""
    audit_path = tmp_path / "events.jsonl"
    os.environ["AUDIT_LOG_PATH"] = str(audit_path)
    try:
        from digiquant.audit import audit_log

        audit_log(
            "run_backtest", agent_id="digiquant", payload={"run_id": "x", "api_key": "secret"}
        )
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
# Runs two real engines (backtest + optimize) in one process — see SKIP_NATIVE_CRASH.
@SKIP_NATIVE_CRASH
def test_api_run_backtest_and_run_optimize_write_audit(tmp_path: Path) -> None:
    """POST /run_backtest and /run_optimize produce audit log entries when Nautilus available."""
    pytest.importorskip("nautilus_trader")

    from digiquant.data.loader import generate_synthetic_ohlcv

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    generate_synthetic_ohlcv(["AAPL"], freq="1d").write_csv(data_dir / "AAPL.csv")
    os.environ["AUDIT_LOG_PATH"] = str(tmp_path / "events.jsonl")
    # REM-055 path containment rejects data outside DIGIQUANT_DATA_ROOT.
    os.environ["DIGIQUANT_DATA_ROOT"] = str(tmp_path)
    try:
        from fastapi.testclient import TestClient

        from digiquant.server import app
        from tests.digi_test_jwt import auth_headers

        client = TestClient(app, headers=auth_headers())
        payload = {"strategy_name": "ema_cross", "symbols": ["AAPL"], "data_dir": str(data_dir)}
        client.post("/run_backtest", json=payload)
        client.post("/run_optimize", json=payload)
        lines = (tmp_path / "events.jsonl").read_text().strip().split("\n")
        assert len(lines) >= 2
        event_types = [json.loads(ln)["event_type"] for ln in lines]
        assert "run_backtest" in event_types
        assert "run_optimize" in event_types
    finally:
        os.environ.pop("AUDIT_LOG_PATH", None)
        os.environ.pop("DIGIQUANT_DATA_ROOT", None)
