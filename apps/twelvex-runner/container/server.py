"""HTTP entrypoint for the twelvex-runner image.

POST /run/ingest    body {"bucket": "intraday"|"daily"|"weekly"|"quarterly", "dry_run": bool}
POST /run/heartbeat body {"dry_run": bool}
POST /run/session   body {"session": "asia"|"london"|"new_york",
                           "run_date": "YYYY-MM-DD" (optional), "dry_run": bool}

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
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "0.0.0.0"
PORT = 8080
LOG_TAIL = 4000
_LOCK = threading.Lock()
# The FX research sessions the workflow runs. A request string never becomes
# an argument, so the set of sessions is a literal list here.
SESSIONS = ("asia", "london", "new_york")
# The workflow's run_date input: a calendar date, never a timestamp.
RUN_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The characters the Worker's String.trim() removes. Python's str.strip()
# removes more (the file separators U+001C to U+001F), so the two layers would
# disagree on a value such as "\u001c2026-10-01".
JS_WHITESPACE = (
    " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)

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


def command_for(route: str, bucket: str | None, session: str | None = None) -> list[str]:
    if route == "heartbeat":
        return ["python", "-m", "twelve_x.scripts.primemarket_session_heartbeat"]
    if route == "ingest":
        # A request string never becomes an argument. Each bucket is its own literal.
        if bucket == "intraday":
            return ["python", "-m", "twelve_x.scripts.ingest_market_context", "intraday"]
        if bucket == "daily":
            return ["python", "-m", "twelve_x.scripts.ingest_market_context", "daily"]
        if bucket == "weekly":
            return ["python", "-m", "twelve_x.scripts.ingest_market_context", "weekly"]
        if bucket == "quarterly":
            return ["python", "-m", "twelve_x.scripts.ingest_market_context", "quarterly"]
        raise ValueError("invalid bucket")
    if route == "session":
        # The graph is the step that decides the exit code. The session itself
        # travels in the environment, never as an argument, and only as one of
        # the literals the workflow uses.
        if session not in SESSIONS:
            raise ValueError("invalid session")
        return ["python", "-m", "twelve_x.graph"]
    raise ValueError("unknown route")


def validate_run_date(value: object) -> str | None:
    """Accept a calendar date (YYYY-MM-DD) or nothing. Reject anything else.

    The workflow passes its run_date input straight into the graph's RUN_DATE
    env, and an empty input means the forward path. So does an empty string
    here: it is absent, not malformed.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid_run_date")
    trimmed = value.strip(JS_WHITESPACE)
    if trimmed == "":
        return None
    if not RUN_DATE.match(trimmed):
        raise ValueError("invalid_run_date")
    try:
        date.fromisoformat(trimmed)
    except ValueError:
        raise ValueError("invalid_run_date") from None
    return trimmed


def validate_request(route: str, bucket: str | None, session: str | None) -> None:
    """Reject an unknown route, an unknown bucket or an unknown session.

    The order is the Worker's order: route, then bucket, then session. The
    run_date is checked after them, so both layers answer the same error for
    the same body.
    """
    command_for(route, bucket, session)


def steps_for(
    route: str,
    bucket: str | None,
    session: str | None,
    run_date: str | None = None,
) -> list[tuple[list[str], dict[str, str], bool]]:
    """(argv, extra_env, fatal) per step, in order.

    The FX research session mirrors the workflow: the calendar ingest runs
    first and is not fatal (the workflow step carries continue-on-error),
    then the graph decides the exit code.
    """
    if route == "session":
        graph = command_for(route, bucket, session)
        assert session is not None  # command_for accepted only a known literal
        # The workflow always sets RUN_DATE on the graph step, and an empty
        # value is the forward path. The step always carries it, so an ambient
        # RUN_DATE in the container env can never decide the date.
        graph_env = {
            "FX_SESSION": session,
            "TRADE_INTELLIGENCE_MODE": "alongside",
            "RUN_DATE": run_date or "",
        }
        return [
            (["python", "-m", "twelve_x.scripts.ingest_calendar"], {}, False),
            (graph, graph_env, True),
        ]
    return [(command_for(route, bucket, session), {}, True)]


def step_env(extra_env: dict[str, str]) -> dict[str, str]:
    """The environment one step runs in.

    RUN_DATE is never inherited: the container process env must not decide
    the date. A step that sets it (the graph) carries it, empty for the
    forward path, exactly as the workflow does.
    """
    env = {**os.environ, **extra_env}
    if "RUN_DATE" not in extra_env:
        env.pop("RUN_DATE", None)
    return env


def dry_run_requested(body: dict, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    if env.get("DRY_RUN") == "1":
        return True
    return body.get("dry_run") is True


def run_steps(
    steps: list[tuple[list[str], dict[str, str], bool]],
    timeout: int,
    dry_run: bool,
) -> dict:
    """Run the steps in order under one deadline.

    The timeout is the job timeout, like the workflow's job-level timeout:
    the steps share it. A step that is not fatal does not stop the run, and
    the exit code is the one of the last step that ran.
    """
    started = time.monotonic()
    if dry_run:
        plan = " | ".join(" ".join(argv) for argv, _, _ in steps)
        return {
            "ok": True,
            "exit_code": 0,
            "duration_ms": 0,
            "log_tail": redact("dry_run " + plan),
            "dry_run": True,
            "command": steps[-1][0],
        }
    outputs: list[str] = []
    code = 0
    for argv, extra_env, fatal in steps:
        remaining = timeout - int((time.monotonic() - started))
        if remaining < 1:
            outputs.append(f"$ {' '.join(argv)}\nTIMEOUT")
            code = 124
            break
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=remaining,
                check=False,
                env=step_env(extra_env),
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            step_code = completed.returncode
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + (exc.stderr or "") + "\nTIMEOUT"
            if isinstance(output, bytes):
                output = output.decode("utf-8", "replace")
            step_code = 124
        outputs.append(f"$ {' '.join(argv)}\n{output}")
        code = step_code
        if step_code != 0 and fatal:
            break
    duration_ms = int((time.monotonic() - started) * 1000)
    tail = redact("".join(outputs))[-LOG_TAIL:]
    return {
        "ok": code == 0,
        "exit_code": code,
        "duration_ms": duration_ms,
        "log_tail": tail,
        "dry_run": False,
        "command": steps[-1][0],
    }


def run_command(argv: list[str], timeout: int, dry_run: bool) -> dict:
    return run_steps([(argv, {}, True)], timeout, dry_run)


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
            validate_request(route, body.get("bucket"), body.get("session"))
            run_date = validate_run_date(body.get("run_date"))
            steps = steps_for(route, body.get("bucket"), body.get("session"), run_date)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        if not _LOCK.acquire(blocking=False):
            self._json(409, {"error": "busy"})
            return
        try:
            timeout = body.get("timeout_seconds")
            if not isinstance(timeout, int) or timeout < 1:
                if route == "ingest":
                    timeout = 1200
                elif route == "session":
                    timeout = 7200
                else:
                    timeout = 300
            payload = run_steps(steps, timeout, dry_run_requested(body))
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
