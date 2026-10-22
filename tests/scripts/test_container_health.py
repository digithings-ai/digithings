#!/usr/bin/env python3
"""Unit tests for the daily container health check (DIG-2910).

Stdlib only: `/usr/bin/python3 -m unittest test_container_health -v`.

The check is the deep half of the smoke test: the cron probes the worker-only
`/_stack/status`, and this one reads `/healthz` from Chris's Mac, where the answer
says whether the container was awake. The tests are about that decision, because it
is the whole point of the job: a sleeping container is not a failure, a body nobody
recognises is, and a failure is one ticket that recurs as a comment instead of a
second ticket.
"""
import ast
import importlib.util
import io
import json
import os
import plistlib
import sys
import tempfile
import unittest
import urllib.error
import urllib.request

try:  # the marker puts this file in the CI lane; a plain unittest run does not need it
    import pytest
    pytestmark = pytest.mark.unit
except ImportError:  # pragma: no cover - pytest is not installed in a stdlib-only run
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_SCRIPT_DIR = os.path.join(_ROOT, "scripts", "container-health")
_SCRIPT = os.path.join(_SCRIPT_DIR, "container_health.py")
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)
_spec = importlib.util.spec_from_file_location("container_health", _SCRIPT)
ch = importlib.util.module_from_spec(_spec)
sys.modules["container_health"] = ch
_spec.loader.exec_module(ch)

_TEMPLATE = os.path.join(_SCRIPT_DIR, "com.digithings.container-health.plist.template")

_CONTAINER_OK = '{"ok": true}'
_SLEEPING = '{"status":"ok","service":"digithings-stack","container":"sleeping"}'


class _FakeResponse:
    """The shape urlopen hands back: a context manager with a status and a body."""

    def __init__(self, status=200, body=b""):
        self.status = status
        self._body = body

    def getcode(self):
        return self.status

    def read(self, _amt=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_opener(answers):
    """An opener that answers from a dict of url -> response or exception."""
    calls = []

    def opener(request, timeout=None):
        url = getattr(request, "full_url", request)
        calls.append((url, timeout, getattr(request, "headers", {})))
        answer = answers.get(url)
        if answer is None:
            raise urllib.error.URLError("no answer for " + url)
        if isinstance(answer, Exception):
            raise answer
        return answer

    opener.calls = calls
    return opener


def _url(host):
    return f"https://{host}.digithings.ai/healthz"


def _issue_paths_in_source(source):
    """Every string the script builds that names an issue API path.

    Docstrings are skipped: they talk about the rule, they do not call it.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    paths = []
    joined_parts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    joined_parts.add(id(part))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in docstrings or id(node) in joined_parts:
                continue
            if "/issues" in node.value:
                paths.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if "/issues" in text:
                paths.append(text)
    return paths


class ClassificationTests(unittest.TestCase):
    def test_container_answer_is_healthy(self):
        state, detail = ch.classify(200, _CONTAINER_OK)
        self.assertEqual(state, ch.STATE_OK)
        self.assertIn("container", detail)

    def test_sleeping_answer_is_healthy(self):
        state, _detail = ch.classify(200, _SLEEPING)
        self.assertEqual(state, ch.STATE_SLEEPING)
        self.assertIn(ch.STATE_SLEEPING, ch.HEALTHY_STATES)

    def test_non_200_is_a_failure(self):
        state, detail = ch.classify(503, "upstream is down")
        self.assertEqual(state, ch.STATE_HTTP)
        self.assertEqual(detail, "HTTP 503")
        self.assertNotIn(state, ch.HEALTHY_STATES)

    def test_unknown_body_is_a_failure(self):
        state, _detail = ch.classify(200, '{"ok": "yes"}')
        self.assertEqual(state, ch.STATE_UNEXPECTED)

    def test_body_that_is_not_json_is_a_failure(self):
        state, _detail = ch.classify(200, "<html>hello</html>")
        self.assertEqual(state, ch.STATE_UNEXPECTED)

    def test_a_json_array_is_a_failure(self):
        state, _detail = ch.classify(200, "[1, 2, 3]")
        self.assertEqual(state, ch.STATE_UNEXPECTED)


class ProbeTests(unittest.TestCase):
    def test_probe_reads_the_container_answer(self):
        opener = _fake_opener({_url("graph"): _FakeResponse(200, _CONTAINER_OK.encode())})
        result = ch.probe("graph", opener=opener)
        self.assertEqual(result["state"], ch.STATE_OK)
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(opener.calls[0][0], _url("graph"))

    def test_probe_reads_the_sleeping_answer(self):
        opener = _fake_opener({_url("key"): _FakeResponse(200, _SLEEPING.encode())})
        result = ch.probe("key", opener=opener)
        self.assertEqual(result["state"], ch.STATE_SLEEPING)

    def test_probe_reports_an_http_error(self):
        err = urllib.error.HTTPError(
            _url("search"), 503, "Service Unavailable", {}, io.BytesIO(b'{"detail":"down"}')
        )
        opener = _fake_opener({_url("search"): err})
        result = ch.probe("search", opener=opener)
        self.assertEqual(result["state"], ch.STATE_HTTP)
        self.assertEqual(result["http_status"], 503)

    def test_probe_reports_an_unreachable_host(self):
        opener = _fake_opener({_url("graph"): urllib.error.URLError("connection refused")})
        result = ch.probe("graph", opener=opener)
        self.assertEqual(result["state"], ch.STATE_UNREACHABLE)
        self.assertIsNone(result["http_status"])

    def test_the_probe_names_itself(self):
        """The edge answers Python-urllib with 403 (measured 2026-10-22), so a
        probe that does not name itself reads the firewall, not the stack."""
        opener = _fake_opener({_url("graph"): _FakeResponse(200, _CONTAINER_OK.encode())})
        ch.probe("graph", opener=opener)
        headers = {k.lower(): v for k, v in opener.calls[0][2].items()}
        self.assertEqual(headers.get("user-agent"), ch.USER_AGENT)


class RunTests(unittest.TestCase):
    def test_all_three_hosts_answering_is_healthy(self):
        opener = _fake_opener(
            {
                _url("graph"): _FakeResponse(200, _CONTAINER_OK.encode()),
                _url("key"): _FakeResponse(200, _CONTAINER_OK.encode()),
                _url("search"): _FakeResponse(200, _SLEEPING.encode()),
            }
        )
        report = ch.run_probes(opener=opener)
        self.assertEqual(report["overall"], ch.OVERALL_HEALTHY)
        self.assertEqual(report["symptom"], "")

    def test_one_unreachable_host_fails_the_run(self):
        opener = _fake_opener(
            {
                _url("graph"): urllib.error.URLError("timed out"),
                _url("key"): _FakeResponse(200, _CONTAINER_OK.encode()),
                _url("search"): _FakeResponse(200, _SLEEPING.encode()),
            }
        )
        report = ch.run_probes(opener=opener)
        self.assertEqual(report["overall"], ch.OVERALL_FAILED)
        self.assertEqual(report["symptom"], "graph /healthz unreachable")

    def test_an_unknown_body_degrades_but_does_not_overstate(self):
        opener = _fake_opener(
            {
                _url("graph"): _FakeResponse(200, b'{"moved": true}'),
                _url("key"): _FakeResponse(200, _CONTAINER_OK.encode()),
                _url("search"): _FakeResponse(200, _CONTAINER_OK.encode()),
            }
        )
        report = ch.run_probes(opener=opener)
        self.assertEqual(report["overall"], ch.OVERALL_DEGRADED)
        self.assertIn("unexpected body", report["symptom"])

    def test_the_symptom_signature_names_the_class(self):
        results = [
            {"host": "graph", "state": ch.STATE_UNREACHABLE, "http_status": None},
            {"host": "key", "state": ch.STATE_OK, "http_status": 200},
        ]
        self.assertEqual(ch.symptom_signature(results), "graph:unreachable:None")


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.filed = []
        self.commented = []
        self._file = ch.file_issue
        self._comment = ch.comment
        ch.file_issue = self._fake_file
        ch.comment = self._fake_comment

    def tearDown(self):
        ch.file_issue = self._file
        ch.comment = self._comment

    def _fake_file(self, title, description, **kwargs):
        self.filed.append((title, description, kwargs))
        return "DIG-9999"

    def _fake_comment(self, identifier, body, **kwargs):
        self.commented.append((identifier, body))
        return True

    def _report(self):
        return {
            "ts": "2026-10-22T07:40:00Z",
            "overall": ch.OVERALL_FAILED,
            "symptom": "graph /healthz unreachable",
            "results": [
                {
                    "host": "graph",
                    "state": ch.STATE_UNREACHABLE,
                    "http_status": None,
                    "elapsed_ms": 120,
                    "detail": "URLError: timed out",
                    "body": "",
                }
            ],
        }

    def test_the_first_failure_files_one_ticket(self):
        state = {"version": 1}
        action = ch.handle_failure(state, self._report())
        self.assertEqual(action, "filed")
        self.assertEqual(len(self.filed), 1)
        self.assertEqual(state["ticket"]["identifier"], "DIG-9999")
        self.assertTrue(self.filed[0][0].startswith("[run-watch] container-health: "))

    def test_a_recurrence_comments_on_the_same_ticket(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "signature": "graph:unreachable:None",
                "created_at": "2026-10-21T07:40:00Z",
                "last_comment_at": "2026-10-21T07:40:00Z",
                "comments": 1,
            },
        }
        action = ch.handle_failure(state, self._report())
        self.assertEqual(action, "commented")
        self.assertEqual(self.filed, [], "a recurrence must not file a second ticket")
        self.assertEqual(self.commented[0][0], "DIG-1234")
        self.assertEqual(state["ticket"]["comments"], 2)

    def test_recovery_is_said_once_on_the_ticket(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "created_at": "2026-10-21T07:40:00Z",
                "last_comment_at": "2026-10-21T07:40:00Z",
                "comments": 1,
            },
        }
        report = self._report()
        report["overall"] = ch.OVERALL_HEALTHY
        report["symptom"] = ""
        self.assertEqual(ch.handle_recovery(state, report), "commented")
        self.assertEqual(ch.handle_recovery(state, report), "skipped")
        self.assertEqual(len(self.commented), 1)
        self.assertEqual(self.commented[0][0], "DIG-1234")

    def test_a_failure_that_cannot_be_filed_is_not_a_silent_pass(self):
        ch.file_issue = lambda *a, **k: None
        state = {"version": 1}
        self.assertEqual(ch.handle_failure(state, self._report()), "not-filed")
        self.assertNotIn("ticket", state)


class FileIssueTests(unittest.TestCase):
    """Creation goes through dt-create-issue, and only through it."""

    def test_the_create_script_is_called_with_the_workspace_fields(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen["cmd"] = cmd
            return type("Proc", (), {"returncode": 0, "stdout": "DIG-4242\n", "stderr": ""})()

        ident = ch.file_issue("title", "description", create_script="/kit/bin/dt-create-issue", runner=runner)
        self.assertEqual(ident, "DIG-4242")
        cmd = seen["cmd"]
        self.assertIn("/kit/bin/dt-create-issue", cmd)
        for flag in ("--title", "--description", "--project", "--parent", "--goal", "--assignee"):
            self.assertIn(flag, cmd)

    def test_a_refused_create_is_not_filed(self):
        def runner(cmd, **kwargs):
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "refused"})()

        self.assertIsNone(ch.file_issue("title", "description", runner=runner))

    def test_a_create_without_an_identifier_is_not_filed(self):
        def runner(cmd, **kwargs):
            return type("Proc", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        self.assertIsNone(ch.file_issue("title", "description", runner=runner))

    def test_the_script_never_creates_an_issue_with_a_bare_post(self):
        """DIG-2040: a bare POST writes no workspace fields, so the issue lands
        on another issue's worktree. Creation must go through dt-create-issue."""
        paths = _issue_paths_in_source(open(_SCRIPT, encoding="utf-8").read())
        self.assertTrue(paths, "the script talks to the issue API")
        for path in paths:
            self.assertTrue(
                path.endswith("/comments"),
                f"the script may only POST to a comment endpoint, found: {path}",
            )


class StateTests(unittest.TestCase):
    def test_the_state_survives_a_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state", "container-health.json")
            state = {"version": 1, "ticket": {"identifier": "DIG-1"}}
            ch.save_state(state, ch.Path(path))
            self.assertEqual(ch.load_state(ch.Path(path)), state)

    def test_a_broken_state_file_is_an_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            self.assertEqual(ch.load_state(ch.Path(path)), {"version": 1})


class PlistTests(unittest.TestCase):
    def _rendered(self):
        with open(_TEMPLATE, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("__CHECKOUT__", "/Users/chrisstefan/Code/digithings")
        text = text.replace("__HOME__", "/Users/chrisstefan")
        return plistlib.loads(text.encode("utf-8"))

    def test_the_plist_is_a_valid_plist(self):
        plist = self._rendered()
        self.assertEqual(plist["Label"], "com.digithings.container-health")

    def test_the_job_runs_daily_and_not_at_load(self):
        plist = self._rendered()
        self.assertFalse(plist["RunAtLoad"])
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 7, "Minute": 40})

    def test_the_job_reads_the_credential_and_runs_the_probe(self):
        plist = self._rendered()
        command = plist["ProgramArguments"][-1]
        self.assertIn("find-generic-password", command)
        self.assertIn("paperclip-api-key-board", command)
        self.assertIn("container_health.py", command)
        self.assertIn("export PAPERCLIP_API_KEY", command)


class CliTests(unittest.TestCase):
    def test_dry_run_writes_nothing_and_files_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            log_path = os.path.join(tmp, "log.jsonl")
            opener = _fake_opener({_url("graph"): _FakeResponse(200, _CONTAINER_OK.encode())})
            code = ch.main(
                [
                    "--hosts", "graph",
                    "--state-path", state_path,
                    "--log-path", log_path,
                    "--dry-run",
                ],
                opener=opener,
            )
            self.assertEqual(code, 0)
            self.assertFalse(os.path.exists(state_path))
            self.assertFalse(os.path.exists(log_path))

    def test_a_failing_run_writes_the_state_and_the_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            log_path = os.path.join(tmp, "log.jsonl")
            opener = _fake_opener({_url("graph"): urllib.error.URLError("timed out")})
            filed = []
            original = ch.file_issue
            ch.file_issue = lambda *a, **k: filed.append(a) or "DIG-9999"
            try:
                code = ch.main(
                    [
                        "--hosts", "graph",
                        "--state-path", state_path,
                        "--log-path", log_path,
                    ],
                    opener=opener,
                )
            finally:
                ch.file_issue = original
            self.assertEqual(code, 1)
            self.assertEqual(len(filed), 1)
            self.assertTrue(filed[0][0].startswith("[run-watch] container-health: "))
            state = ch.load_state(ch.Path(state_path))
            self.assertEqual(state["last_run"]["overall"], ch.OVERALL_FAILED)
            self.assertEqual(state["ticket"]["identifier"], "DIG-9999")
            with open(log_path, encoding="utf-8") as handle:
                lines = [json.loads(line) for line in handle.read().splitlines() if line]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0]["overall"], ch.OVERALL_FAILED)


if __name__ == "__main__":
    unittest.main()
