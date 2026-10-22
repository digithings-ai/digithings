#!/usr/bin/env python3
"""Unit tests for the daily container health check (DIG-2910).

Stdlib only: `/usr/bin/python3 -m unittest test_container_health -v`.

The check is the deep half of the smoke test: the cron probes the worker-only
`/_stack/status`, and this one reads `/healthz` from Chris's Mac, where the answer
says whether the container was awake. The tests are about that decision, because it
is the whole point of the job: a sleeping container is not a failure, a body nobody
recognises is, and a failure is one ticket that recurs as a comment instead of a
second ticket.

The other half of the tests is the plumbing that carries the failure to the board:
the credential has to be an agent credential (a board key is refused by
`dt-create-issue` and would file the comment in Chris's name), the identifier of a
filed ticket has to survive a create whose read-back failed, and a lost state file
must not become a second ticket.
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
from unittest import mock

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

#: The credential the job runs with: an agent key, because dt-create-issue asks
#: /api/agents/me first and refuses anything else.
AGENT_KEY = "agent-key-for-the-tests"


class _FakeResponse:
    """The shape urlopen hands back: a context manager with a status and a body."""

    def __init__(self, status=200, body=b"", url=None):
        self.status = status
        self._body = body
        self.url = url

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

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


def _post_calls_in_source(source):
    """Every url the script POSTs to.

    DIG-2040: a bare POST writes no workspace fields, so the issue lands on
    another issue's worktree. Creation must go through dt-create-issue, so the
    only POST the script may make is a comment.
    """
    tree = ast.parse(source)
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "Request"):
            continue
        method = None
        for keyword in node.keywords:
            if keyword.arg == "method" and isinstance(keyword.value, ast.Constant):
                method = keyword.value.value
        if method != "POST" or not node.args:
            continue
        target = node.args[0]
        if isinstance(target, ast.Constant):
            calls.append(target.value)
        elif isinstance(target, ast.JoinedStr):
            calls.append(
                "".join(
                    part.value
                    for part in target.values
                    if isinstance(part, ast.Constant) and isinstance(part.value, str)
                )
            )
    return calls


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

    def test_a_redirect_off_the_health_path_is_not_healthy(self):
        """A redirect leaves the wake-hygiene path. If it lands on a route that
        boots the container, the daily check starts costing money."""
        opener = _fake_opener(
            {
                _url("graph"): _FakeResponse(
                    200, _CONTAINER_OK.encode(), url="https://graph.digithings.ai/login"
                )
            }
        )
        result = ch.probe("graph", opener=opener)
        self.assertEqual(result["state"], ch.STATE_UNEXPECTED)
        self.assertIn("redirected", result["detail"])

    def test_a_redirect_that_stays_on_the_health_path_is_fine(self):
        opener = _fake_opener(
            {
                _url("graph"): _FakeResponse(
                    200, _CONTAINER_OK.encode(), url="https://graph.digithings.ai/healthz"
                )
            }
        )
        result = ch.probe("graph", opener=opener)
        self.assertEqual(result["state"], ch.STATE_OK)


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

    def test_probing_nothing_is_not_a_green_run(self):
        report = ch.run_probes(hosts=[])
        self.assertEqual(report["overall"], ch.OVERALL_FAILED)
        self.assertEqual(report["results"], [])

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
        self._find = ch.find_existing_ticket
        ch.file_issue = self._fake_file
        ch.comment = self._fake_comment
        ch.find_existing_ticket = lambda *a, **k: None

    def tearDown(self):
        ch.file_issue = self._file
        ch.comment = self._comment
        ch.find_existing_ticket = self._find

    def _fake_file(self, title, description, **kwargs):
        self.filed.append((title, description, kwargs))
        return "DIG-9999"

    def _fake_comment(self, identifier, body, **kwargs):
        self.commented.append((identifier, body))
        return True

    def _report(self, symptom="graph /healthz unreachable", ts="2026-10-22T07:40:00Z"):
        return {
            "ts": ts,
            "overall": ch.OVERALL_FAILED,
            "symptom": symptom,
            "results": [
                {
                    "host": "graph",
                    "url": "https://graph.digithings.ai/healthz",
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
                "last_comment_at": "2026-10-01T07:40:00Z",
                "comments": 1,
            },
        }
        action = ch.handle_failure(state, self._report())
        self.assertEqual(action, "commented")
        self.assertEqual(self.filed, [], "a recurrence must not file a second ticket")
        self.assertEqual(self.commented[0][0], "DIG-1234")
        self.assertEqual(state["ticket"]["comments"], 2)

    def test_a_recurrence_of_the_same_symptom_is_throttled(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "signature": "graph:unreachable:None",
                "created_at": ch.utcnow(),
                "last_comment_at": ch.utcnow(),
                "comments": 1,
            },
        }
        action = ch.handle_failure(state, self._report())
        self.assertEqual(action, "throttled")
        self.assertEqual(self.commented, [], "one comment a day is enough")
        self.assertEqual(self.filed, [])

    def test_a_changed_symptom_is_commented_straight_away(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "signature": "graph:unreachable:None",
                "created_at": ch.utcnow(),
                "last_comment_at": ch.utcnow(),
                "comments": 1,
            },
        }
        report = self._report(symptom="key /healthz HTTP 503")
        report["results"][0]["host"] = "key"
        report["results"][0]["state"] = ch.STATE_HTTP
        report["results"][0]["http_status"] = 503
        action = ch.handle_failure(state, report)
        self.assertEqual(action, "commented")
        self.assertEqual(len(self.commented), 1)

    def test_the_symptom_of_the_first_failure_is_kept(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "signature": "graph:unreachable:None",
                "created_at": "2026-10-21T07:40:00Z",
                "last_comment_at": "2026-10-01T07:40:00Z",
                "comments": 1,
            },
        }
        report = self._report(symptom="key /healthz HTTP 503")
        report["results"][0]["host"] = "key"
        report["results"][0]["state"] = ch.STATE_HTTP
        report["results"][0]["http_status"] = 503
        ch.handle_failure(state, report)
        self.assertEqual(state["ticket"]["symptom"], "graph /healthz unreachable")
        self.assertIn("Symptom when filed: graph /healthz unreachable", self.commented[0][1])
        self.assertIn("Symptom now: key /healthz HTTP 503", self.commented[0][1])

    def test_recovery_is_said_once_per_episode(self):
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "created_at": "2026-10-21T07:40:00Z",
                "last_comment_at": "2026-10-01T07:40:00Z",
                "comments": 1,
            },
        }
        green = self._report()
        green["overall"] = ch.OVERALL_HEALTHY
        green["symptom"] = ""
        self.assertEqual(ch.handle_recovery(state, green), "commented")
        self.assertEqual(ch.handle_recovery(state, green), "skipped")
        self.assertEqual(len(self.commented), 1)
        # A new failure opens a new episode, and the next green run says so again.
        state["ticket"]["signature"] = "graph:unreachable:None"
        state["ticket"]["last_comment_at"] = "2026-10-01T07:40:00Z"
        ch.handle_failure(state, self._report())
        self.assertNotIn("recovered_at", state["ticket"])
        self.assertEqual(ch.handle_recovery(state, green), "commented")
        self.assertEqual(len(self.commented), 3)

    def test_a_failure_that_cannot_be_filed_is_not_a_silent_pass(self):
        ch.file_issue = lambda *a, **k: None
        state = {"version": 1}
        self.assertEqual(ch.handle_failure(state, self._report()), "not-filed")
        self.assertNotIn("ticket", state)

    def test_a_lost_state_file_does_not_file_a_second_ticket(self):
        """The state file is the first record of the ticket; the board is the
        second one. Without the second, a lost state file means one ticket a day."""
        ch.find_existing_ticket = lambda *a, **k: "DIG-4242"
        state = {"version": 1}
        action = ch.handle_failure(state, self._report())
        self.assertEqual(self.filed, [], "the ticket that is already open is used")
        self.assertEqual(state["ticket"]["identifier"], "DIG-4242")
        self.assertEqual(self.commented[0][0], "DIG-4242")
        self.assertEqual(action, "commented")

    def test_a_ticket_that_cannot_be_reached_is_replaced(self):
        """A closed or deleted ticket that refuses every comment would swallow
        every later failure, so after a few refusals a new one is filed."""
        ch.comment = lambda *a, **k: False
        state = {
            "version": 1,
            "ticket": {
                "identifier": "DIG-1234",
                "symptom": "graph /healthz unreachable",
                "signature": "graph:unreachable:None",
                "created_at": "2026-10-21T07:40:00Z",
                "last_comment_at": "2026-10-01T07:40:00Z",
                "comments": 1,
            },
        }
        for _ in range(2):
            self.assertEqual(ch.handle_failure(state, self._report()), "skipped")
        self.assertEqual(self.filed, [])
        self.assertEqual(ch.handle_failure(state, self._report()), "filed")
        self.assertEqual(len(self.filed), 1)
        self.assertEqual(state["ticket"]["identifier"], "DIG-9999")


class FileIssueTests(unittest.TestCase):
    """Creation goes through dt-create-issue, and only through it."""

    def test_the_create_script_is_called_with_the_workspace_fields(self):
        seen = {}

        def runner(cmd, **kwargs):
            seen["cmd"] = cmd
            return type("Proc", (), {"returncode": 0, "stdout": "DIG-4242\n", "stderr": ""})()

        ident = ch.file_issue(
            "title",
            "description",
            create_script="/kit/bin/dt-create-issue",
            runner=runner,
            api_key=AGENT_KEY,
        )
        self.assertEqual(ident, "DIG-4242")
        cmd = seen["cmd"]
        self.assertIn("/kit/bin/dt-create-issue", cmd)
        for flag in ("--title", "--description", "--project", "--parent", "--goal", "--assignee"):
            self.assertIn(flag, cmd)
        # The values matter as much as the flags: a wrong parent files the
        # ticket outside the epic, a wrong assignee files it on nobody.
        self.assertEqual(cmd[cmd.index("--project") + 1], "digithings")
        self.assertEqual(cmd[cmd.index("--parent") + 1], "DIG-2904")
        self.assertEqual(cmd[cmd.index("--goal") + 1], "657cd9ec-cba3-467e-9afb-e2b4df7f8c44")
        self.assertEqual(cmd[cmd.index("--assignee") + 1], "c838b4b0-424b-4b58-a2c6-c140c97a0f87")
        self.assertEqual(cmd[cmd.index("--status") + 1], "todo")
        self.assertEqual(cmd[cmd.index("--priority") + 1], "high")

    def test_a_refused_create_is_not_filed(self):
        def runner(cmd, **kwargs):
            return type("Proc", (), {"returncode": 1, "stdout": "", "stderr": "refused"})()

        self.assertIsNone(ch.file_issue("title", "description", runner=runner, api_key=AGENT_KEY))

    def test_a_create_that_failed_after_the_create_is_still_filed(self):
        """dt-create-issue checks the read-back after the POST, so a non-zero
        exit can mean the ticket exists. The identifier is the evidence."""

        def runner(cmd, **kwargs):
            return type(
                "Proc",
                (),
                {"returncode": 1, "stdout": "DIG-4242  pref=isolated_workspace\n", "stderr": "read-back failed"},
            )()

        self.assertEqual(
            ch.file_issue("title", "description", runner=runner, api_key=AGENT_KEY), "DIG-4242"
        )

    def test_a_create_without_an_identifier_is_not_filed(self):
        def runner(cmd, **kwargs):
            return type("Proc", (), {"returncode": 0, "stdout": "None  pref=isolated_workspace\n", "stderr": ""})()

        self.assertIsNone(ch.file_issue("title", "description", runner=runner, api_key=AGENT_KEY))

    def test_a_create_without_a_credential_is_not_filed(self):
        """A board key is refused by dt-create-issue, and it would file the
        ticket in Chris's name, so the check happens before the call."""
        called = []

        def runner(cmd, **kwargs):
            called.append(cmd)
            return type("Proc", (), {"returncode": 0, "stdout": "DIG-4242\n", "stderr": ""})()

        with mock.patch.dict(os.environ, {"PAPERCLIP_API_KEY": ""}):
            self.assertIsNone(ch.file_issue("title", "description", runner=runner))
        self.assertEqual(called, [])

    def test_the_script_never_creates_an_issue_with_a_bare_post(self):
        """DIG-2040: a bare POST writes no workspace fields, so the issue lands
        on another issue's worktree. Creation must go through dt-create-issue."""
        posts = _post_calls_in_source(open(_SCRIPT, encoding="utf-8").read())
        self.assertTrue(posts, "the script talks to the issue API")
        for path in posts:
            self.assertTrue(
                path.endswith("/comments"),
                f"the script may only POST to a comment endpoint, found: {path}",
            )


class FindExistingTicketTests(unittest.TestCase):
    def test_the_open_run_watch_ticket_is_found(self):
        url = "http://test/api/companies/co-1/issues?limit=50&q=container-health"
        payload = json.dumps(
            [
                {"identifier": "DIG-1", "title": "Cloudflare cost minimum", "issueNumber": 1},
                {
                    "identifier": "DIG-4242",
                    "title": "[run-watch] container-health: graph /healthz unreachable",
                    "issueNumber": 4242,
                },
            ]
        ).encode()
        opener = _fake_opener({url: _FakeResponse(200, payload)})
        found = ch.find_existing_ticket(
            api_base="http://test/api",
            company_id="co-1",
            opener=opener,
            api_key=AGENT_KEY,
        )
        self.assertEqual(found, "DIG-4242")

    def test_no_ticket_means_no_identifier(self):
        url = "http://test/api/companies/co-1/issues?limit=50&q=container-health"
        opener = _fake_opener({url: _FakeResponse(200, b"[]")})
        found = ch.find_existing_ticket(
            api_base="http://test/api",
            company_id="co-1",
            opener=opener,
            api_key=AGENT_KEY,
        )
        self.assertIsNone(found)


class CommentTests(unittest.TestCase):
    def test_the_comment_goes_to_the_api_root_with_the_api_path(self):
        """PAPERCLIP_API_URL names the server; the script appends /api itself.
        Without that, every comment lands on a 404 and the ticket goes quiet."""
        opener = _fake_opener({})
        with mock.patch.dict(os.environ, {"PAPERCLIP_API_URL": "http://127.0.0.1:3100"}):
            ch.comment("DIG-1", "body", opener=opener, api_key=AGENT_KEY)
        # the opener has no answer for the url, so the call failed; the url it
        # asked for is what matters.
        self.assertTrue(opener.calls)
        self.assertEqual(
            opener.calls[0][0], "http://127.0.0.1:3100/api/issues/DIG-1/comments"
        )

    def test_an_api_url_that_already_names_the_api_is_left_alone(self):
        opener = _fake_opener({})
        with mock.patch.dict(os.environ, {"PAPERCLIP_API_URL": "http://127.0.0.1:3100/api"}):
            ch.comment("DIG-1", "body", opener=opener, api_key=AGENT_KEY)
        self.assertEqual(
            opener.calls[0][0], "http://127.0.0.1:3100/api/issues/DIG-1/comments"
        )

    def test_a_comment_without_a_credential_is_not_posted(self):
        opener = _fake_opener({})
        with mock.patch.dict(os.environ, {"PAPERCLIP_API_KEY": ""}):
            self.assertFalse(ch.comment("DIG-1", "body", opener=opener))
        self.assertEqual(opener.calls, [])


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

    def test_the_job_reads_the_agent_credential_and_runs_the_probe(self):
        """The credential has to be the agent key: dt-create-issue asks
        /api/agents/me first and refuses a board key, and a board key would
        file the ticket and the comments in Chris's name."""
        plist = self._rendered()
        command = plist["ProgramArguments"][-1]
        self.assertIn("find-generic-password", command)
        self.assertIn("-a paperclip-api-key ", command)
        self.assertNotIn("paperclip-api-key-board", command)
        self.assertIn("container_health.py", command)
        self.assertIn("export PAPERCLIP_API_KEY", command)

    def test_the_script_path_is_quoted(self):
        """A path with a space would break the job: bash would run the first
        word and exit 127 every day, before the probe ever runs."""
        plist = self._rendered()
        command = plist["ProgramArguments"][-1]
        self.assertIn('"/Users/chrisstefan/Code/digithings/scripts/container-health/container_health.py"', command)

    def test_the_rotation_guard_fails_closed(self):
        """A deadline that cannot be read must withhold the credential, not
        export it: bash compares a non-number as 0, which fails open."""
        plist = self._rendered()
        command = plist["ProgramArguments"][-1]
        self.assertIn("*[!0-9]*", command)
        self.assertIn("paperclip-api-key-rotate-by", command)


class CliTests(unittest.TestCase):
    def test_dry_run_writes_nothing_and_files_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            log_path = os.path.join(tmp, "log.jsonl")
            opener = _fake_opener({_url("graph"): _FakeResponse(200, _CONTAINER_OK.encode())})

            def no_call(*args, **kwargs):
                raise AssertionError("a dry run must not file or comment")

            with mock.patch.object(ch, "file_issue", no_call), mock.patch.object(
                ch, "comment", no_call
            ):
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

    def test_no_hosts_is_an_error_and_not_a_green_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            log_path = os.path.join(tmp, "log.jsonl")
            code = ch.main(
                [
                    "--hosts", " , ",
                    "--state-path", state_path,
                    "--log-path", log_path,
                ],
                opener=_fake_opener({}),
            )
            self.assertEqual(code, 2)
            self.assertFalse(os.path.exists(state_path))
            self.assertFalse(os.path.exists(log_path))

    def test_a_run_that_cannot_write_the_log_still_files_the_ticket(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = os.path.join(tmp, "state.json")
            log_path = os.path.join(tmp, "log.jsonl")
            opener = _fake_opener({_url("graph"): urllib.error.URLError("timed out")})
            filed = []

            def broken_log(report, path):
                raise OSError("no space left on device")

            with mock.patch.object(ch, "append_log", broken_log):
                with mock.patch.object(ch, "file_issue", lambda *a, **k: filed.append(a) or "DIG-9999"):
                    code = ch.main(
                        [
                            "--hosts", "graph",
                            "--state-path", state_path,
                            "--log-path", log_path,
                        ],
                        opener=opener,
                    )
            self.assertEqual(code, 1)
            self.assertEqual(len(filed), 1)
            self.assertEqual(ch.load_state(ch.Path(state_path))["ticket"]["identifier"], "DIG-9999")


if __name__ == "__main__":
    unittest.main()
