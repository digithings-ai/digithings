"""Integration-style tests for digiclaw heartbeat (Phase 3)."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


@pytest.mark.unit
def test_main_exits_nonzero_when_services_unhealthy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """main() returns 1 when health pings fail (REM-073)."""
    audit_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("DIGIGRAPH_URL", "http://127.0.0.1:9")  # likely closed port
    monkeypatch.setenv("DIGIQUANT_URL", "http://127.0.0.1:9")
    from digiclaw.heartbeat_runner import main

    assert main() == 1


@pytest.mark.unit
def test_heartbeat_checklist_finds_digiclaw_docs_path() -> None:
    from digiclaw.heartbeat_runner import _heartbeat_checklist_path

    path = _heartbeat_checklist_path()
    assert path is not None
    assert path.name == "HEARTBEAT.md"
    assert path.is_file()


@pytest.mark.unit
def test_heartbeat_checklist_respects_digi_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REM-072: Docker mounts repo at DIGI_WORKSPACE=/workspace."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("DIGI_WORKSPACE", str(repo_root))
    from digiclaw.heartbeat_runner import _heartbeat_checklist_path

    path = _heartbeat_checklist_path()
    assert path is not None
    assert path == repo_root / "digiclaw" / "docs" / "HEARTBEAT.md"


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


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[ThreadingHTTPServer, str]:
    """Start a daemon HTTP server on an ephemeral port. Caller shuts it down."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}"


@pytest.mark.unit
def test_cross_origin_redirect_does_not_forward_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 302 to another host must fail the call and must not receive the bearer."""
    from digiclaw import heartbeat_runner as runner

    stolen: list[str | None] = []

    class StolenHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            stolen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    class OriginHandler(BaseHTTPRequestHandler):
        location = ""

        def do_GET(self) -> None:
            self.send_response(302)
            self.send_header("Location", OriginHandler.location)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    stolen_server, stolen_base = _serve(StolenHandler)
    OriginHandler.location = f"{stolen_base}/stolen"
    origin_server, origin_base = _serve(OriginHandler)
    try:
        monkeypatch.setattr(runner, "digikey_bearer_token", lambda: "secret-token")
        ok, _detail = runner._request(f"{origin_base}/health", auth=True)
        assert ok is False
        assert stolen == []
    finally:
        origin_server.shutdown()
        stolen_server.shutdown()
        origin_server.server_close()
        stolen_server.server_close()


@pytest.mark.unit
def test_same_origin_redirect_keeps_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiclaw import heartbeat_runner as runner

    seen: list[tuple[str, str | None]] = []

    class OriginHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            seen.append((self.path, self.headers.get("Authorization")))
            if self.path == "/health":
                host, port = self.server.server_address[:2]
                self.send_response(302)
                self.send_header("Location", f"http://{host}:{port}/healthz")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server, base = _serve(OriginHandler)
    try:
        monkeypatch.setattr(runner, "digikey_bearer_token", lambda: "secret-token")
        ok, detail = runner._request(f"{base}/health", auth=True)
        assert ok is True
        assert detail == "200"
        assert seen == [
            ("/health", "Bearer secret-token"),
            ("/healthz", "Bearer secret-token"),
        ]
    finally:
        server.shutdown()
        server.server_close()
