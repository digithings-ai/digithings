"""Health-gate tests for the local self-host stack (DIG-2775, S7).

The load-bearing property is that the gate can FAIL. Every assertion about a
green gate is paired with a server that answers wrong, so a regression that
makes the gate unconditionally pass is caught rather than celebrated.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.localstack import contracts, health

pytestmark = pytest.mark.unit


class _Handler(BaseHTTPRequestHandler):
    """One fake service: routes are declared per-test via ``self.server.routes``."""

    def log_message(self, *args):
        return

    def _respond(self):
        route = self.server.routes.get(self.path.split("?")[0])
        if route is None:
            self.send_response(404)
            self.end_headers()
            return
        status, payload = route
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _respond
    do_POST = _respond


def _serve(routes):
    """Start a fake service on a free port; returns ``(base_url, shutdown)``."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.routes = routes
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def shutdown():
        server.shutdown()
        server.server_close()

    return f"http://127.0.0.1:{server.server_address[1]}", shutdown


def _names(results):
    """Check names out of a tuple of Result objects, for readable assertions."""
    return tuple(r.name for r in results)


def _check(name, url, **kwargs):
    defaults = {
        "kind": "http",
        "url": url,
        "profiles": ("core",),
        "source": "test fixture",
    }
    defaults.update(kwargs)
    return contracts.Check(name=name, **defaults)


# --- the gate passes when the service is genuinely healthy --------------------


def test_http_probe_passes_against_a_healthy_service():
    base, stop = _serve({"/healthz": (200, {"ok": True})})
    try:
        report = health.run_gate((_check("ok", f"{base}/healthz"),), timeout=5.0)
    finally:
        stop()

    assert report.ok, report.to_dict()
    assert _names(report.passed) == ("ok",)
    assert _names(report.failed) == ()
    assert "HTTP 200" in report.results[0].detail


# --- the gate fails: the non-vacuity control ----------------------------------


def test_http_probe_fails_against_an_unhealthy_service():
    base, stop = _serve({"/healthz": (503, {"ok": False})})
    try:
        report = health.run_gate((_check("bad", f"{base}/healthz"),), timeout=5.0)
    finally:
        stop()

    assert not report.ok
    assert _names(report.failed) == ("bad",)
    assert "503" in report.results[0].detail


def test_a_dead_port_fails_rather_than_erroring():
    # 127.0.0.1:1 is closed: a refused connection must be a FAILED result,
    # never an exception out of the gate and never a pass.
    report = health.run_gate((_check("dead", "http://127.0.0.1:1/healthz"),), timeout=2.0)

    assert not report.ok
    assert _names(report.failed) == ("dead",)
    assert report.results[0].status == contracts.FAILED


# --- a refused knob fails the gate and sends no request (DIG-4911) -----------


def test_a_refused_port_never_opens_a_connection(monkeypatch):
    """A refused knob sends no request at all.

    The failure above is about the knob, not about a check that never runs:
    the transport itself is replaced by one that fails the test if it is
    ever used, so the proof is that no request leaves the machine.
    """

    def _no_network(*args, **kwargs):
        raise AssertionError("the gate opened a connection for a refused knob")

    monkeypatch.setattr(health.urllib.request, "urlopen", _no_network)

    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    report = health.run_gate((check,), config={"DT_DIGIGRAPH_PORT": "8000@evil.com"})

    assert not report.ok
    assert _names(report.failed) == ("digigraph",)
    assert _names(report.skipped) == ()
    assert "DT_DIGIGRAPH_PORT" in report.results[0].detail


def test_the_gate_still_probes_a_port_it_accepted(monkeypatch):
    """The control: an accepted port still reaches the probe.

    Without this, a refusal that also swallowed every valid port would pass
    the test above.
    """
    seen = []

    def _record(request, *args, **kwargs):
        seen.append(request.full_url)
        raise AssertionError("the fake transport is the only thing that answers")

    monkeypatch.setattr(health.urllib.request, "urlopen", _record)

    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    health.run_gate((check,), config={"DT_DIGIGRAPH_PORT": "18000"})

    assert seen == ["http://127.0.0.1:18000/healthz"]


def test_gate_fails_when_any_single_check_fails():
    base, stop = _serve({"/healthz": (200, {"ok": True})})
    try:
        checks = (
            _check("good", f"{base}/healthz"),
            _check("missing", f"{base}/absent"),
        )
        report = health.run_gate(checks, timeout=5.0)
    finally:
        stop()

    assert not report.ok
    assert _names(report.passed) == ("good",)
    assert _names(report.failed) == ("missing",)


# --- the three probe kinds ---------------------------------------------------


def test_jsonrpc_probe_requires_a_tools_list():
    base, stop = _serve({"/mcp": (200, {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})})
    try:
        report = health.run_gate((_check("mcp", f"{base}/mcp", kind="jsonrpc"),), timeout=5.0)
    finally:
        stop()

    assert report.ok, report.to_dict()


def test_jsonrpc_probe_fails_on_a_jsonrpc_error_member():
    base, stop = _serve({"/mcp": (200, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601}})})
    try:
        report = health.run_gate((_check("mcp", f"{base}/mcp", kind="jsonrpc"),), timeout=5.0)
    finally:
        stop()

    assert not report.ok, "a JSON-RPC error at HTTP 200 must not read as healthy"
    assert "-32601" in report.results[0].detail


def test_jsonrpc_probe_fails_when_the_result_has_no_tools_list():
    base, stop = _serve({"/mcp": (200, {"jsonrpc": "2.0", "id": 1, "result": {}})})
    try:
        report = health.run_gate((_check("mcp", f"{base}/mcp", kind="jsonrpc"),), timeout=5.0)
    finally:
        stop()

    assert not report.ok


def test_roundtrip_probe_requires_the_nonce_back():
    body = json.dumps({"probe": "abc123"})
    base, stop = _serve({"/roundtrip": (200, body), "/abc123": (200, body)})
    try:
        report = health.run_gate(
            (
                _check(
                    "r2",
                    f"{base}/roundtrip",
                    kind="roundtrip",
                    read_path="/abc123",
                ),
            ),
            timeout=5.0,
            nonce="abc123",
        )
    finally:
        stop()

    assert report.ok, report.to_dict()


def test_roundtrip_probe_fails_on_a_write_only_binding():
    """200 to the write and nothing on the read back is NOT healthy.

    This is the exact shape MinFlare-free local bindings take when the
    namespace is not wired, so it is the case the plan calls out.
    """
    body = json.dumps({"probe": "abc123"})
    base, stop = _serve({"/roundtrip": (200, body)})
    try:
        report = health.run_gate(
            (
                _check(
                    "r2",
                    f"{base}/roundtrip",
                    kind="roundtrip",
                    read_path="/abc123",
                ),
            ),
            timeout=5.0,
            nonce="abc123",
        )
    finally:
        stop()

    assert not report.ok, "a binding that writes but cannot read back must fail"
    assert _names(report.failed) == ("r2",)


def test_roundtrip_probe_fails_when_the_read_back_carries_a_stale_value():
    body = json.dumps({"probe": "STALE"})
    base, stop = _serve({"/roundtrip": (200, body), "/abc123": (200, body)})
    try:
        report = health.run_gate(
            (
                _check(
                    "r2",
                    f"{base}/roundtrip",
                    kind="roundtrip",
                    read_path="/abc123",
                ),
            ),
            timeout=5.0,
            nonce="abc123",
        )
    finally:
        stop()

    assert not report.ok, "a read-back of a different value must not pass"


# --- skip semantics: unconfigured is skipped, never passed -------------------


def test_an_unconfigured_check_is_skipped_and_never_passed():
    unconfigured = contracts.Check(
        name="r2-put-get",
        kind="roundtrip",
        url=None,
        profiles=("all",),
        source="binding ids generated by S3",
        requires="DT_R2_URL",
    )
    report = health.run_gate((unconfigured,), timeout=1.0)

    assert _names(report.passed) == ()
    assert _names(report.skipped) == ("r2-put-get",)
    assert "DT_R2_URL" in report.results[0].detail
    # A skip must not by itself fail the gate: partial local stacks are normal.
    assert report.ok


def test_require_all_turns_a_skip_into_a_failure():
    """With everything else healthy, ``require_all`` is the only thing that bites."""
    base, stop = _serve({"/healthz": (200, {"ok": True})})
    unconfigured = contracts.Check(
        name="mcp-tools-list",
        kind="jsonrpc",
        url=None,
        profiles=("all",),
        source="no declared path",
        requires="DT_MCP_URL",
    )
    try:
        checks = (_check("ok", f"{base}/healthz"), unconfigured)
        lenient = health.run_gate(checks, timeout=5.0)
        strict = health.run_gate(checks, timeout=5.0, require_all=True)
    finally:
        stop()

    assert lenient.ok, f"a skip must not fail a lenient gate: {lenient.to_dict()}"
    assert not strict.ok, "require_all must fail while a check is unverified"
    assert _names(strict.skipped) == ("mcp-tools-list",)
    assert strict.to_dict()["require_all"] is True


def test_roundtrip_probe_fails_when_the_write_is_refused():
    """A binding that rejects the write must fail before any read is attempted.

    ``urlopen`` raises on 4xx/5xx, so this is the write's error arm. Control:
    the same fixture with a 200 write and a good read-back passes in
    ``test_roundtrip_probe_requires_the_nonce_back``.
    """
    base, stop = _serve({"/roundtrip": (500, {"error": "no such binding"})})
    try:
        report = health.run_gate(
            (_check("r2", f"{base}/roundtrip", kind="roundtrip", read_path="/abc123"),),
            timeout=5.0,
            nonce="abc123",
        )
    finally:
        stop()

    assert not report.ok, "a write that was refused must not read as healthy"
    assert "write failed" in report.results[0].detail


def test_roundtrip_probe_fails_on_a_successful_but_empty_read():
    """A 2xx that is not 200 carries no value, so the read-back cannot pass.

    This is the branch a redirect-free 204 takes: ``urlopen`` does not raise
    on it, so the probe has to judge the status itself rather than rely on
    an exception.
    """
    base, stop = _serve({"/roundtrip": (200, {"probe": "abc123"}), "/abc123": (204, "")})
    try:
        report = health.run_gate(
            (_check("r2", f"{base}/roundtrip", kind="roundtrip", read_path="/abc123"),),
            timeout=5.0,
            nonce="abc123",
        )
    finally:
        stop()

    assert not report.ok, "a 204 read-back carries no written value"
    assert "204" in report.results[0].detail


# --- DIG-4905: a port knob that is not a port fails the check, loudly -------


def test_a_port_knob_that_is_not_a_port_fails_the_check():
    """The gate refuses the URL and says which knob is wrong.

    The failure has to be a FAILED check and not a crash: a traceback would
    take the whole gate down, and a SKIP would let the gate read as healthy
    while one surface went unverified. The detail names the knob, so the
    operator knows what to fix.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    report = health.run_gate(
        (check,), config={"DT_DIGIGRAPH_PORT": "8000@evil.com"}, timeout=1.0
    )

    assert not report.ok, "a knob that would point the probe off the machine must fail"
    assert _names(report.failed) == ("digigraph",)
    assert _names(report.skipped) == ()
    assert "DT_DIGIGRAPH_PORT" in report.results[0].detail


def test_a_port_knob_that_is_not_a_port_opens_no_connection():
    """No URL is built, so no request can leave the machine.

    Control: the same check with a real port does build a URL, so the
    refusal above is about the knob and not about a check that never runs.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")
    refused = health.run_gate(
        (check,), config={"DT_DIGIGRAPH_PORT": "8000@evil.com"}, timeout=1.0
    )
    accepted = health.run_gate((check,), config={"DT_DIGIGRAPH_PORT": "18000"}, timeout=1.0)

    assert refused.results[0].url is None
    assert accepted.results[0].url == "http://127.0.0.1:18000/healthz"


def test_a_refused_contract_row_fails_the_check_instead_of_skipping(tmp_path):
    """A contract row whose port is not a port is a FAILED row.

    The same channel as a refused knob: a traceback would take the whole
    gate down, and a SKIP would let the gate read as healthy while one
    surface went unverified. The detail names the value that is wrong.
    """
    (tmp_path / "config" / "contract").mkdir(parents=True)
    (tmp_path / "config" / "contract" / "services.yaml").write_text(
        "services:\n"
        "  - name: digigraph\n"
        "    port: '8000@evil.com'\n"
        "    health_path: /healthz\n",
        encoding="utf-8",
    )
    checks, _origin = contracts.load_checks(tmp_path)
    row = next(c for c in checks if c.name == "digigraph")

    report = health.run_gate((row,), timeout=1.0)

    assert not report.ok, "a contract port that would point off the machine must fail"
    assert _names(report.failed) == ("digigraph",)
    assert _names(report.skipped) == ()
    assert "8000@evil.com" in report.results[0].detail
    # No URL was built, so no request can leave the machine.
    assert report.results[0].url is None
