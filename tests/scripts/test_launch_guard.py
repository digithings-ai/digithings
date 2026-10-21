#!/usr/bin/env python3
"""Unit tests for the CI launch guard (DIG-4796). Stdlib only:
`/usr/bin/python3 -m unittest test_launch_guard -v`.

The guard is the thing that makes "a seat never runs the runner" true instead of
written down, so the tests here are about the decision, not about the style of
the decision: a seat-shaped run is refused, the launchd daemon and the CI
container are not, and the answer does not move when the shell environment
changes or when `gh` is put on the PATH.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

try:  # the marker puts this file in the CI lane; a plain unittest run does not need it
    import pytest
    pytestmark = pytest.mark.unit
except ImportError:  # pragma: no cover - pytest is not installed in a stdlib-only run
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
_spec = importlib.util.spec_from_file_location(
    "launch_guard", os.path.join(_SCRIPTS, "launch_guard.py"))
_guard = importlib.util.module_from_spec(_spec)
sys.modules["launch_guard"] = _guard
_spec.loader.exec_module(_guard)

_RUNNER = os.path.join(_SCRIPTS, "local_ci.py")
_GUARD_CLI = os.path.join(_SCRIPTS, "launch_guard.py")


def _seat_facts(**overrides):
    """The facts of a run started by a seat's shell: nothing trusted in sight."""
    facts = {
        "runner": os.path.realpath(_RUNNER),
        "pid": 4242,
        "ppid": 99,
        "uid": os.getuid(),
        "ancestors": [
            {"pid": 99, "argv": ["/bin/zsh", "-c", "twelvex_ci.py --pr 368"]},
            {"pid": 1, "argv": ["/sbin/launchd"]},
        ],
        "dockerenv": False,
        "xpc_service_name": None,
        "ci_token": True,
        "launchd_job": None,
    }
    facts.update(overrides)
    return facts


def _launchd_facts(**overrides):
    """The facts of the launchd daemon running the runner file that is running now."""
    facts = _seat_facts(
        ppid=1,
        xpc_service_name="ai.digithings.local-ci",
        ancestors=[{"pid": 1, "argv": ["/sbin/launchd"]}],
        launchd_job={
            "program": "/usr/bin/python3",
            "arguments": ["/usr/bin/python3", os.path.realpath(_RUNNER)],
            "path": os.path.expanduser("~/Library/LaunchAgents/ai.digithings.local-ci.plist"),
        },
    )
    facts.update(overrides)
    return facts


def _container_facts(**overrides):
    """The facts of the CI container: the worker entrypoint, under /opt/local-ci."""
    facts = _seat_facts(
        runner="/opt/local-ci/local_ci.py",
        ppid=1,
        dockerenv=True,
        ancestors=[
            {"pid": 1, "argv": ["/bin/bash", "/opt/local-ci/worker_entrypoint.sh", "--pr", "368"]},
        ],
    )
    facts.update(overrides)
    return facts


class DecisionTests(unittest.TestCase):
    """The decision itself: deny by default, two trusted launchers."""

    def test_a_seat_shaped_run_is_refused(self):
        allowed, reason = _guard.decide(_seat_facts())
        self.assertFalse(allowed)
        self.assertIn("trusted launcher", reason)

    def test_the_launchd_daemon_is_allowed(self):
        allowed, reason = _guard.decide(_launchd_facts())
        self.assertTrue(allowed, reason)

    def test_a_launchd_job_with_extra_arguments_is_refused(self):
        """A job that asks for one PR is not the daemon, even under a trusted label."""
        facts = _launchd_facts()
        facts["launchd_job"]["arguments"] = [
            "/usr/bin/python3", os.path.realpath(_RUNNER), "--pr", "368"]
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("arguments", reason)

    def test_a_launchd_job_that_runs_another_file_is_refused(self):
        facts = _launchd_facts()
        facts["launchd_job"]["arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("different file", reason)

    def test_an_untrusted_service_name_is_refused(self):
        facts = _launchd_facts(xpc_service_name="com.digithings.merge-queue")
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not a trusted runner job", reason)

    def test_a_launchd_claim_from_a_shell_is_refused(self):
        """XPC_SERVICE_NAME alone is not a claim anybody can prove."""
        facts = _launchd_facts(ppid=1234)
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("parent pid", reason)

    def test_a_launchd_job_that_is_not_loaded_is_refused(self):
        facts = _launchd_facts(launchd_job=None)
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not loaded", reason)

    def test_a_launchd_job_loaded_from_another_plist_is_refused(self):
        """The label is not enough: the job has to be the one install.sh wrote."""
        facts = _launchd_facts()
        facts["launchd_job"]["path"] = "/tmp/seat/ai.digithings.local-ci.plist"
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("canonical", reason)

    def test_the_canonical_plist_is_the_one_the_installer_writes(self):
        expected = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                                "ai.digithings.local-ci.plist")
        self.assertEqual(_guard.canonical_plist_path("ai.digithings.local-ci"), expected)
        self.assertEqual(
            _guard.canonical_plist_path("ai.digithings.twelvex-ci"),
            os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents",
                         "ai.digithings.twelvex-ci.plist"))

    def test_the_ci_container_is_allowed(self):
        allowed, reason = _guard.decide(_container_facts())
        self.assertTrue(allowed, reason)

    def test_the_container_without_the_entrypoint_is_refused(self):
        facts = _container_facts()
        facts["ancestors"] = [{"pid": 1, "argv": ["/bin/sh", "-c", "python3 local_ci.py --pr 368"]}]
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("worker entrypoint", reason)

    def test_the_container_without_a_credential_is_refused(self):
        facts = _container_facts(ci_token=False)
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("credential", reason)

    def test_a_runner_outside_the_container_root_is_refused(self):
        facts = _container_facts(runner="/tmp/local_ci.py")
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("/opt/local-ci", reason)


class LaunchctlParsingTests(unittest.TestCase):
    """The parser against the shape launchctl actually prints."""

    REAL = """gui/501/ai.digithings.local-ci-postmerge = {
\tactive count = 1
\tpath = /Users/chrisstefan/Library/LaunchAgents/ai.digithings.local-ci-postmerge.plist
\ttype = LaunchAgent
\tstate = running

\tprogram = /usr/bin/python3
\targuments = {
\t\t/usr/bin/python3
\t\t/Users/chrisstefan/Code/local-ci/postmerge_ci.py
\t}

\tstdout path = /Users/chrisstefan/.config/digithings/logs/local-ci-postmerge/launchd.out
\tenvironment = {
\t\tOSLogRateLimit => 64
\t\tXPC_SERVICE_NAME => ai.digithings.local-ci-postmerge
\t}
\tpid = 47393
\tlast exit code = 0
}
"""

    def test_the_program_the_arguments_and_the_plist_are_read(self):
        job = _guard.parse_launchctl_print(self.REAL)
        self.assertEqual(job["program"], "/usr/bin/python3")
        self.assertEqual(job["arguments"],
                         ["/usr/bin/python3", "/Users/chrisstefan/Code/local-ci/postmerge_ci.py"])
        self.assertTrue(job["path"].endswith("ai.digithings.local-ci-postmerge.plist"))

    def test_a_missing_job_is_not_a_job(self):
        self.assertIsNone(_guard.launchctl_job("ai.digithings.local-ci-not-a-job"))


class EnvironmentIndependenceTests(unittest.TestCase):
    """The answer must not move when the shell environment changes."""

    def _run_cli(self, env, extra=()):
        tmp = tempfile.mkdtemp(prefix="launch-guard-")
        try:
            facts_path = os.path.join(tmp, "facts.json")
            with open(facts_path, "w", encoding="utf-8") as fh:
                json.dump(_seat_facts(), fh)
            child = dict(env)
            child["HOME"] = tmp
            return subprocess.run(
                [sys.executable, _GUARD_CLI, "--runner", _RUNNER, "--facts-json", facts_path]
                + list(extra),
                capture_output=True, text=True, env=child, timeout=60)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _bare_env(self):
        """An environment without a single inherited variable."""
        return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.path.expanduser("~")}

    def test_the_refusal_holds_with_a_bare_environment(self):
        result = self._run_cli(self._bare_env())
        self.assertEqual(result.returncode, _guard.EX_CONFIG, result.stderr)
        self.assertIn("refusing to run", result.stderr)

    def test_the_refusal_holds_with_the_seat_environment(self):
        """BASH_ENV, PAPERCLIP_* and ZDOTDIR are set here and change nothing."""
        env = self._bare_env()
        env.update({
            "BASH_ENV": "/nonexistent/bash_env",
            "ZDOTDIR": "/nonexistent/zd",
            "PAPERCLIP_AGENT_ID": "2d7f158b-f8de-48e1-9764-6ece84797c20",
            "PAPERCLIP_RUN_ID": "run-1",
            "PAPERCLIP_TASK_ID": "5ec14cd7-059e-478c-b8cc-cd8996b1a887",
        })
        result = self._run_cli(env)
        self.assertEqual(result.returncode, _guard.EX_CONFIG, result.stderr)
        self.assertIn("refusing to run", result.stderr)

    def test_both_environments_give_the_same_reason(self):
        bare = self._run_cli(self._bare_env())
        noisy = self._run_cli(dict(self._bare_env(), BASH_ENV="/nonexistent/bash_env",
                                   ZDOTDIR="/nonexistent/zd",
                                   PAPERCLIP_AGENT_ID="seat"))
        self.assertEqual(json.loads(bare.stdout)["reason"], json.loads(noisy.stdout)["reason"])


class NoGitHubTests(unittest.TestCase):
    """The guard must not reach GitHub, and must not even call `gh`."""

    def test_the_guard_never_calls_gh(self):
        tmp = tempfile.mkdtemp(prefix="launch-guard-")
        try:
            marker = os.path.join(tmp, "gh-was-called")
            bindir = os.path.join(tmp, "bin")
            os.makedirs(bindir)
            shim = os.path.join(bindir, "gh")
            with open(shim, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\ntouch '%s'\nexit 0\n" % marker)
            os.chmod(shim, 0o755)
            facts_path = os.path.join(tmp, "facts.json")
            with open(facts_path, "w", encoding="utf-8") as fh:
                json.dump(_seat_facts(), fh)
            env = {"PATH": bindir + ":/usr/bin:/bin", "HOME": tmp}
            result = subprocess.run(
                [sys.executable, _GUARD_CLI, "--runner", _RUNNER, "--facts-json", facts_path],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(result.returncode, _guard.EX_CONFIG, result.stderr)
            self.assertFalse(os.path.exists(marker), "the guard called gh")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_guard_source_mentions_no_shell_tricks(self):
        """No env-var trust, no shell function removal, no gh call in the source."""
        with open(_GUARD_CLI, "r", encoding="utf-8") as fh:
            source = fh.read()
        # The docstring names the variables it refuses to trust; the code must not
        # read them.
        code = source.replace(_guard.__doc__ or "", "")
        for forbidden in ("BASH_ENV", "ZDOTDIR", "PAPERCLIP_AGENT_ID", "PAPERCLIP_RUN_ID",
                          "PAPERCLIP_TASK_ID", "unset -f", "env -u"):
            self.assertNotIn(forbidden, code)


class CliTests(unittest.TestCase):
    """The diagnostic CLI: it decides, it prints, it never runs a check."""

    def test_the_cli_refuses_a_seat_shaped_run(self):
        tmp = tempfile.mkdtemp(prefix="launch-guard-")
        try:
            facts_path = os.path.join(tmp, "facts.json")
            with open(facts_path, "w", encoding="utf-8") as fh:
                json.dump(_seat_facts(), fh)
            env = {"PATH": "/usr/bin:/bin", "HOME": tmp}
            result = subprocess.run(
                [sys.executable, _GUARD_CLI, "--runner", _RUNNER, "--facts-json", facts_path],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(result.returncode, _guard.EX_CONFIG)
            report = json.loads(result.stdout)
            self.assertFalse(report["allowed"])
            self.assertIn("reason", report)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_cli_and_the_decision_agree(self):
        """The CLI is the same decision the runner makes, not a second opinion."""
        facts = _guard.collect_facts(_RUNNER)
        allowed, _reason = _guard.decide(facts)
        expected = 0 if allowed else _guard.EX_CONFIG
        tmp = tempfile.mkdtemp(prefix="launch-guard-")
        try:
            env = {"PATH": "/usr/bin:/bin", "HOME": tmp}
            result = subprocess.run(
                [sys.executable, _GUARD_CLI, "--runner", _RUNNER],
                capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(result.returncode, expected, result.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_cli_needs_a_runner(self):
        result = subprocess.run([sys.executable, _GUARD_CLI], capture_output=True, text=True,
                                timeout=60)
        self.assertEqual(result.returncode, 2)


class RunnerWiringTests(unittest.TestCase):
    """The runner asks the guard first, and stops there when the answer is no."""

    def setUp(self):
        self._spec = importlib.util.spec_from_file_location(
            "local_ci_under_test", _RUNNER)
        self._mod = importlib.util.module_from_spec(self._spec)
        sys.modules["local_ci_under_test"] = self._mod
        self._spec.loader.exec_module(self._mod)
        self._home = tempfile.mkdtemp(prefix="launch-guard-home-")
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home

    def tearDown(self):
        if self._old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._old_home
        shutil.rmtree(self._home, ignore_errors=True)

    def test_the_runner_refuses_before_it_touches_anything(self):
        """No lock, no watchdog, no status: the refusal comes first."""
        touched = []
        self._mod.acquire_lock = lambda: touched.append("lock") or True
        self._mod.watchdog = lambda: touched.append("watchdog")
        self._mod.status = lambda *a, **k: touched.append("status")
        self._mod.list_prs = lambda base: touched.append("list_prs") or []
        original = _guard.collect_facts
        _guard.collect_facts = lambda runner_path: _seat_facts()
        old_argv = sys.argv
        sys.argv = ["local_ci.py", "--pr", "368"]
        try:
            with self.assertRaises(SystemExit) as caught:
                self._mod.main()
        finally:
            sys.argv = old_argv
            _guard.collect_facts = original
        self.assertEqual(caught.exception.code, _guard.EX_CONFIG)
        self.assertEqual(touched, [], "the runner did something before it was refused")

    def test_the_runner_refuses_when_the_guard_module_is_missing(self):
        self._mod.launch_guard = None
        old_argv = sys.argv
        sys.argv = ["local_ci.py", "--pr", "368"]
        try:
            with self.assertRaises(SystemExit) as caught:
                self._mod.main()
        finally:
            sys.argv = old_argv
        self.assertEqual(caught.exception.code, _guard.EX_CONFIG)

    def test_a_refusal_is_written_to_the_log(self):
        original = _guard.collect_facts
        _guard.collect_facts = lambda runner_path: _seat_facts()
        old_argv = sys.argv
        sys.argv = ["local_ci.py", "--pr", "368"]
        try:
            with self.assertRaises(SystemExit):
                self._mod.main()
        finally:
            sys.argv = old_argv
            _guard.collect_facts = original
        path = os.path.join(self._home, ".config", "digithings", "logs", "local-ci",
                            "launch-guard.jsonl")
        self.assertTrue(os.path.exists(path), "the refusal was not recorded")
        with open(path, "r", encoding="utf-8") as fh:
            record = json.loads(fh.read().strip().splitlines()[-1])
        self.assertFalse(record["allowed"])
        self.assertIn("reason", record)


if __name__ == "__main__":
    unittest.main()
