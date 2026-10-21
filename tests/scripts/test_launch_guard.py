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
            # launchd reports the pid of the process the job's program runs in.
            "pid": 4242,
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


# The seat's own attack from 21 Oct, as a shell sets it up: `gh` and every
# shell the guard might spawn point at a marker file, and the shell's own
# variables carry the seat's identity.
_POISON = """\
touch "$LAUNCH_GUARD_POISON_MARKER"
gh() { touch "$LAUNCH_GUARD_MARKER"; }
ps() { touch "$LAUNCH_GUARD_MARKER"; /bin/ps "$@"; }
export -f gh ps
"""

# The child collects the facts for real - no injected facts - and decides.
_COLLECT_CHILD = """\
import json, sys
sys.path.insert(0, sys.argv[1])
import launch_guard as lg
facts = lg.collect_facts(sys.argv[2])
allowed, reason = lg.decide(facts)
print(json.dumps({"allowed": allowed, "reason": reason, "facts": facts}))
"""

# bash sources BASH_ENV before it runs this, so the poison is in place.
_WRAPPER = """\
#!/bin/bash
exec "$1" "$2" "$3" "$4"
"""


def _collect_in_child(case, hostile=False, extra=None):
    """Collect the facts in a child process. Returns (report, markers).

    The report is what the child decided. The markers say whether the poison
    was armed (so the test knows the attack was in place) and whether `gh` was
    called (so the test knows it was not).
    """
    tmp = tempfile.mkdtemp(prefix="launch-guard-")
    case.addCleanup(shutil.rmtree, tmp, True)
    gh_marker = os.path.join(tmp, "gh-was-called")
    poison_marker = os.path.join(tmp, "poison-was-sourced")
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    shim = os.path.join(bindir, "gh")
    with open(shim, "w", encoding="utf-8") as fh:
        fh.write(f"#!/bin/sh\ntouch '{gh_marker}'\nexit 0\n")
    os.chmod(shim, 0o755)
    poison = os.path.join(tmp, "poison.bash")
    with open(poison, "w", encoding="utf-8") as fh:
        fh.write(_POISON)
    child = os.path.join(tmp, "collect.py")
    with open(child, "w", encoding="utf-8") as fh:
        fh.write(_COLLECT_CHILD)
    wrapper = os.path.join(tmp, "wrapper.sh")
    with open(wrapper, "w", encoding="utf-8") as fh:
        fh.write(_WRAPPER)
    env = {
        "PATH": bindir + ":/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": tmp,
        "LAUNCH_GUARD_MARKER": gh_marker,
        "LAUNCH_GUARD_POISON_MARKER": poison_marker,
    }
    if hostile:
        env.update({
            "BASH_ENV": poison,
            "ZDOTDIR": os.path.join(tmp, "zd"),
            "PAPERCLIP_AGENT_ID": "2d7f158b-f8de-48e1-9764-6ece84797c20",
            "PAPERCLIP_RUN_ID": "run-1",
            "PAPERCLIP_TASK_ID": "5ec14cd7-059e-478c-b8cc-cd8996b1a887",
        })
    env.update(extra or {})
    result = subprocess.run(
        ["/bin/bash", wrapper, sys.executable, child, _SCRIPTS, _RUNNER],
        capture_output=True, text=True, env=env, timeout=120, check=False)
    if result.returncode != 0:
        raise AssertionError(f"the collecting child failed: {result.stderr}")
    report = json.loads(result.stdout)
    markers = {"gh": gh_marker, "poison": poison_marker}
    return report, markers


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

    def test_an_orphaned_process_that_forges_the_label_is_refused(self):
        """The bypass this closes: a seat that orphans itself to launchd.

        A double-forked process is reparented to launchd, so its parent pid is
        1 and the tree looks like the daemon's. Claiming the trusted label and
        pointing at the real loaded job is not enough: launchd reports the pid
        of the job's own process, and this run is not that process.
        """
        facts = _launchd_facts(
            pid=78736,
            launchd_job={
                "program": "/usr/bin/python3",
                "arguments": ["/usr/bin/python3", os.path.realpath(_RUNNER)],
                "path": os.path.expanduser(
                    "~/Library/LaunchAgents/ai.digithings.local-ci.plist"),
                "pid": 43944,
            })
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not the job's process", reason)

    def test_a_launchd_job_that_is_not_running_is_refused(self):
        """A job that is loaded but not running did not start this run."""
        facts = _launchd_facts()
        facts["launchd_job"]["pid"] = None
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not running", reason)

    def test_a_claim_whose_process_tree_does_not_start_at_launchd_is_refused(self):
        """The tree is read, not just the parent pid."""
        facts = _launchd_facts(
            ancestors=[{"pid": 4243, "argv": ["/bin/zsh", "-c", "local_ci.py"]},
                       {"pid": 1, "argv": ["/sbin/launchd"]}])
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("process tree", reason)

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

    def test_the_entrypoint_has_to_be_the_runner_parent(self):
        """The worker starts the runner as a direct child of the entrypoint.

        An entrypoint that is only somewhere up the tree is a shell in the
        container that started the runner, not the pipeline.
        """
        facts = _container_facts()
        facts["ancestors"] = [
            {"pid": 42, "argv": ["/bin/sh", "-c", "python3 local_ci.py --pr 368"]},
            {"pid": 1, "argv": ["/bin/bash", "/opt/local-ci/worker_entrypoint.sh"]},
        ]
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


class RefusalWordingTests(unittest.TestCase):
    """Every refusal names the trusted launcher, whichever path the check took.

    The reason is read in a log by a human deciding whether the run may go on,
    so it must not depend on where the run happened: a refusal in the CI
    container and a refusal on a laptop name the trusted launcher the same way.
    """

    def _refusal_facts(self):
        """One set of facts per way the guard can refuse a run."""
        untrusted_label = _seat_facts(xpc_service_name="com.digithings.merge-queue")
        wrong_parent = _launchd_facts(ppid=1234)
        not_loaded = _launchd_facts(launchd_job=None)
        other_file = _launchd_facts()
        other_file["launchd_job"]["arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        container_root = _container_facts(runner="/tmp/local_ci.py")
        container_parent = _container_facts()
        container_parent["ancestors"] = [
            {"pid": 1, "argv": ["/bin/sh", "-c", "python3 local_ci.py --pr 368"]}]
        no_credential = _container_facts(ci_token=False)
        return [_seat_facts(), untrusted_label, wrong_parent, not_loaded, other_file,
                container_root, container_parent, no_credential]

    def test_every_refusal_names_the_trusted_launcher(self):
        for facts in self._refusal_facts():
            allowed, reason = _guard.decide(facts)
            self.assertFalse(allowed, reason)
            self.assertIn("trusted launcher", reason)

    def test_the_refusal_the_container_gives_names_it_too(self):
        """The container path is the one the CI lane walks, so it is checked here."""
        facts = _container_facts(runner="/tmp/local_ci.py")
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("trusted launcher", reason)


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

    def test_the_pid_of_the_running_job_is_read(self):
        """The pid launchd reports is the fact that ties a run to a job."""
        job = _guard.parse_launchctl_print(self.REAL)
        self.assertEqual(job["pid"], 47393)

    def test_a_job_that_is_not_running_has_no_pid(self):
        job = _guard.parse_launchctl_print(self.REAL.replace("\tpid = 47393\n", ""))
        self.assertIsNone(job["pid"])

    def test_a_missing_job_is_not_a_job(self):
        self.assertIsNone(_guard.launchctl_job("ai.digithings.local-ci-not-a-job"))


class EnvironmentIndependenceTests(unittest.TestCase):
    """The answer must not move when the shell environment changes.

    The facts are collected for real here, in a child process, under a bash
    that sources a hostile BASH_ENV: the seat's own attack from 21 Oct, with
    `gh` and `ps` pointed at a marker file. A guard that read BASH_ENV, that
    called `gh`, or that spawned a shell would leave the marker behind.
    """

    def test_the_answer_is_the_same_in_a_bare_and_in_a_hostile_environment(self):
        bare, _markers = _collect_in_child(self)
        hostile, markers = _collect_in_child(self, hostile=True)
        self.assertTrue(os.path.exists(markers["poison"]),
                        "the hostile environment was not in place")
        self.assertFalse(bare["allowed"])
        self.assertFalse(hostile["allowed"])
        self.assertEqual(bare["reason"], hostile["reason"])

    def test_the_facts_do_not_carry_the_hostile_environment(self):
        bare, _markers = _collect_in_child(self)
        hostile, _markers = _collect_in_child(self, hostile=True)
        for key in ("runner", "uid", "dockerenv", "xpc_service_name", "ci_token"):
            self.assertEqual(bare["facts"][key], hostile["facts"][key])
        self.assertEqual(sorted(bare["facts"]), sorted(hostile["facts"]))
        for key in ("BASH_ENV", "ZDOTDIR", "PAPERCLIP_AGENT_ID", "PAPERCLIP_RUN_ID",
                    "PAPERCLIP_TASK_ID"):
            self.assertNotIn(key, json.dumps(hostile["facts"]))

    def test_a_forged_trusted_label_is_refused_in_a_hostile_environment(self):
        """The label is a claim; the pid of the job's own process is the proof."""
        report, _markers = _collect_in_child(
            self, hostile=True, extra={"XPC_SERVICE_NAME": "ai.digithings.local-ci"})
        self.assertFalse(report["allowed"])

    def test_the_refusal_holds_with_a_bare_environment(self):
        report, _markers = _collect_in_child(self)
        self.assertFalse(report["allowed"])
        self.assertIn("trusted launcher", report["reason"])


class NoGitHubTests(unittest.TestCase):
    """The guard must not reach GitHub, and must not even call `gh`."""

    def test_the_guard_never_calls_gh(self):
        """`gh` is on the PATH and in the shell's functions, and is never run."""
        report, markers = _collect_in_child(self, hostile=True)
        self.assertFalse(report["allowed"])
        self.assertTrue(os.path.exists(markers["poison"]),
                        "the hostile environment was not in place")
        self.assertFalse(os.path.exists(markers["gh"]), "the guard called gh")

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
                capture_output=True, text=True, env=env, timeout=60, check=False)
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
                capture_output=True, text=True, env=env, timeout=60, check=False)
            self.assertEqual(result.returncode, expected, result.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_cli_needs_a_runner(self):
        result = subprocess.run([sys.executable, _GUARD_CLI], capture_output=True, text=True,
                                timeout=60, check=False)
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
