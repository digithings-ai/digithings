"""HTTP entrypoint for the twelvex-runner image.

POST /run/ingest    body {"bucket": "intraday"|"daily"|"weekly"|"quarterly", "dry_run": bool}
POST /run/heartbeat body {"dry_run": bool}

Runs the same argv as the GitHub Actions steps. DRY_RUN=1 or "dry_run": true
returns exit 0 and does not start the command, so nothing is written.
The response is JSON: exit_code, duration_ms, log_tail, command. Log text is
redacted before it leaves the process.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = 8080
LOG_TAIL = 4000
BUCKETS = {"intraday", "daily", "weekly", "quarterly"}
_LOCK = threading.Lock()

_SECRET = re.compile(
    r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]+"
    r"|((?:token|key|secret|password|authorization)\s*[=:]\s*)(?!bearer\b)\S+"
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"
)


def redact(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        if match.group(1):
            return match.group(1) + "[redacted]"
        if match.group(2):
            return match.group(2) + "[redacted]"
        return "[redacted]"

    return _SECRET.sub(repl, text)


def command_for(route: str, bucket: str | None) -> list[str]:
    if route == "heartbeat":
        return ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"]
    if route == "ingest":
        if bucket not in BUCKETS:
            raise ValueError("invalid bucket")
        return ["python", "-m", "twelve_x.scripts.ingest_market_context", bucket]
    raise ValueError("unknown route")


def dry_run_requested(body: dict, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    if env.get("DRY_RUN") == "1":
        return True
    return body.get("dry_run") is True


def run_command(argv: list[str], timeout: int, dry_run: bool) -> dict:
    started = time.monotonic()
    if dry_run:
        return {
            "ok": True,
            "exit_code": 0,
            "duration_ms": 0,
            "log_tail": redact("dry_run " + " ".join(argv)),
            "dry_run": True,
            "command": argv,
        }
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "") + "\nTIMEOUT"
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        code = 124
    duration_ms = int((time.monotonic() - started) * 1000)
    tail = redact(output)[-LOG_TAIL:]
    return {
        "ok": code == 0,
        "exit_code": code,
        "duration_ms": duration_ms,
        "log_tail": tail,
        "dry_run": False,
        "command": argv,
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/healthz":
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/") or "/"
        route = path.removeprefix("/run/")
        if path == route or "/" in route:
            self._json(404, {"error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b""
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        if not isinstance(body, dict):
            self._json(400, {"error": "invalid_json"})
            return
        try:
            argv = command_for(route, body.get("bucket"))
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        if not _LOCK.acquire(blocking=False):
            self._json(409, {"error": "busy"})
            return
        try:
            timeout = body.get("timeout_seconds")
            if not isinstance(timeout, int) or timeout < 1:
                timeout = 1200 if route == "ingest" else 300
            payload = run_command(argv, timeout, dry_run_requested(body))
        finally:
            _LOCK.release()
        self._json(200, payload)

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
