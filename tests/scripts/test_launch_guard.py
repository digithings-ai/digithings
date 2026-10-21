#!/usr/bin/env python3
"""Unit tests for the CI launch guard (DIG-4796). Stdlib only:
`/usr/bin/python3 -m unittest test_launch_guard -v`.

The guard is the thing that makes "a seat never runs the runner" true instead of
written down, so the tests here are about the decision, not about the style of
the decision: a seat-shaped run is refused, the launchd daemon and the CI
container are not, and the answer does not move when the shell environment
changes, when `gh` is put on the PATH, or when a fake `launchctl` is put there
too.
"""
import ast
import importlib.util
import io
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
            {"pid": 99, "argv": ["/bin/zsh", "-c", "local_ci.py --pr 368"]},
            {"pid": 1, "argv": ["/sbin/launchd"]},
        ],
        "dockerenv": False,
        "xpc_service_name": None,
        "ci_token": True,
        "launchd_label": None,
        "launchd_job": None,
        "installed_arguments": None,
    }
    facts.update(overrides)
    return facts


def _launchd_facts(**overrides):
    """The facts of the launchd daemon running the runner file that is running now."""
    facts = _seat_facts(
        ppid=1,
        xpc_service_name="ai.digithings.local-ci",
        ancestors=[{"pid": 1, "argv": ["/sbin/launchd"]}],
        # The label comes from launchd's own job table, never from the environment.
        launchd_label="ai.digithings.local-ci",
        launchd_job={
            "program": "/usr/bin/python3",
            "arguments": ["/usr/bin/python3", os.path.realpath(_RUNNER)],
            "path": os.path.expanduser("~/Library/LaunchAgents/ai.digithings.local-ci.plist"),
            # launchd reports the pid of the process the job's program runs in.
            "pid": 4242,
        },
        installed_arguments=["/usr/bin/python3", os.path.realpath(_RUNNER)],
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

# A fake launchctl, first on the PATH. It answers the guard the way a seat
# wants it to be answered, for both questions the guard asks launchd: `launchctl
# list` reports a row with the pid of whoever asked under the trusted label,
# and `launchctl print` reports the canonical plist path, the runner's own path
# as the job's argument, and the pid of whoever asked. A guard that ran this
# would believe every word of it.
_FAKE_LAUNCHCTL = r"""#!/bin/sh
touch "$LAUNCH_GUARD_LAUNCHCTL_MARKER"
if [ "$1" = "list" ]; then
  printf 'PID\tStatus\tLabel\n%s\t0\tai.digithings.local-ci\n' "$PPID"
  exit 0
fi
printf 'gui/501/ai.digithings.local-ci = {\n\tpath = %s/Library/LaunchAgents/ai.digithings.local-ci.plist\n\tprogram = /usr/bin/python3\n\targuments = {\n\t\t/usr/bin/python3\n\t\t%s\n\t}\n\tpid = %s\n}\n' "$HOME" "$LAUNCH_GUARD_RUNNER" "$PPID"
"""

# A fake ps, first on the PATH. It only says that it was asked.
_FAKE_PS = r"""#!/bin/sh
touch "$LAUNCH_GUARD_PS_MARKER"
exec /bin/ps "$@"
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
    was armed (so the test knows the attack was in place), whether `gh` was
    called (so the test knows it was not), and whether a fake `launchctl` or
    `ps` from the PATH was run (so the test knows the guard did not believe
    the PATH).
    """
    tmp = tempfile.mkdtemp(prefix="launch-guard-")
    case.addCleanup(shutil.rmtree, tmp, True)
    gh_marker = os.path.join(tmp, "gh-was-called")
    poison_marker = os.path.join(tmp, "poison-was-sourced")
    launchctl_marker = os.path.join(tmp, "launchctl-was-called")
    ps_marker = os.path.join(tmp, "ps-was-called")
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    shim = os.path.join(bindir, "gh")
    with open(shim, "w", encoding="utf-8") as fh:
        fh.write(f"#!/bin/sh\ntouch '{gh_marker}'\nexit 0\n")
    os.chmod(shim, 0o755)
    fake_launchctl = os.path.join(bindir, "launchctl")
    with open(fake_launchctl, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_LAUNCHCTL)
    os.chmod(fake_launchctl, 0o755)
    fake_ps = os.path.join(bindir, "ps")
    with open(fake_ps, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_PS)
    os.chmod(fake_ps, 0o755)
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
        "LAUNCH_GUARD_LAUNCHCTL_MARKER": launchctl_marker,
        "LAUNCH_GUARD_PS_MARKER": ps_marker,
        "LAUNCH_GUARD_RUNNER": os.path.realpath(_RUNNER),
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
    markers = {"gh": gh_marker, "poison": poison_marker,
               "launchctl": launchctl_marker, "ps": ps_marker}
    return report, markers


# The child that orphans itself: it forks, the parent leaves, and the process
# that is left is reparented to launchd, so its parent pid is 1 - the shape a
# launchd job's process has. That is the shape a seat would use to pretend to
# be the daemon.
_ORPHAN_CHILD = """\
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
runner = sys.argv[2]
out = sys.argv[3]
pid = os.fork()
if pid > 0:
    os._exit(0)
for _ in range(500):
    if os.getppid() == 1:
        break
    time.sleep(0.01)
report = {"pid": os.getpid(), "ppid": os.getppid()}
try:
    import launch_guard as lg
    facts = lg.collect_facts(runner)
    allowed, reason = lg.decide(facts)
    report["allowed"] = allowed
    report["reason"] = reason
    report["facts"] = facts
except BaseException as exc:
    report["allowed"] = None
    report["reason"] = repr(exc)
    report["facts"] = {}
with open(out, "w", encoding="utf-8") as fh:
    json.dump(report, fh)
"""


def _collect_in_orphan(case, extra=None):
    """Collect the facts from a process that orphaned itself to launchd.

    Returns (report, markers). The report is the orphan's decision; the markers
    say whether the fake launchctl from the PATH was run.
    """
    tmp = tempfile.mkdtemp(prefix="launch-guard-orphan-")
    case.addCleanup(shutil.rmtree, tmp, True)
    launchctl_marker = os.path.join(tmp, "launchctl-was-called")
    ps_marker = os.path.join(tmp, "ps-was-called")
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir)
    fake_launchctl = os.path.join(bindir, "launchctl")
    with open(fake_launchctl, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_LAUNCHCTL)
    os.chmod(fake_launchctl, 0o755)
    fake_ps = os.path.join(bindir, "ps")
    with open(fake_ps, "w", encoding="utf-8") as fh:
        fh.write(_FAKE_PS)
    os.chmod(fake_ps, 0o755)
    child = os.path.join(tmp, "orphan.py")
    with open(child, "w", encoding="utf-8") as fh:
        fh.write(_ORPHAN_CHILD)
    out = os.path.join(tmp, "report.json")
    env = {
        "PATH": bindir + ":/usr/bin:/bin:/usr/sbin:/sbin",
        "HOME": tmp,
        "LAUNCH_GUARD_LAUNCHCTL_MARKER": launchctl_marker,
        "LAUNCH_GUARD_PS_MARKER": ps_marker,
        "LAUNCH_GUARD_RUNNER": os.path.realpath(_RUNNER),
    }
    env.update(extra or {})
    result = subprocess.run(
        [sys.executable, child, _SCRIPTS, _RUNNER, out],
        capture_output=True, text=True, env=env, timeout=120, check=False)
    if result.returncode != 0:
        raise AssertionError(f"the orphaning child failed: {result.stderr}")
    if not os.path.exists(out):
        raise AssertionError(f"the orphaning child wrote no report: {result.stdout}")
    with open(out, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    markers = {"launchctl": launchctl_marker, "ps": ps_marker}
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
        arguments = ["/usr/bin/python3", os.path.realpath(_RUNNER), "--pr", "368"]
        facts["launchd_job"]["arguments"] = arguments
        facts["installed_arguments"] = arguments
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("arguments", reason)

    def test_a_launchd_job_that_runs_another_file_is_refused(self):
        facts = _launchd_facts()
        facts["launchd_job"]["arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        facts["installed_arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("neither the runner", reason)

    def test_an_untrusted_launchd_job_is_refused(self):
        """launchd may be running this process for a job that is not a runner job."""
        facts = _launchd_facts(launchd_label="com.digithings.merge-queue")
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not a trusted runner job", reason)

    def test_a_forged_label_in_the_environment_is_refused(self):
        """The label in the environment is a claim; launchd's job table is the proof.

        This is the 21 Oct shape: the seat sets XPC_SERVICE_NAME to a trusted
        label and runs the runner by hand. Nothing in the environment may make
        the guard believe it.
        """
        facts = _launchd_facts(launchd_label=None, launchd_job=None,
                               installed_arguments=None,
                               xpc_service_name="ai.digithings.local-ci")
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("no launchd job is running this process", reason)

    def test_the_environment_never_decides(self):
        """Swapping the label in the environment cannot move the decision."""
        honest = _launchd_facts()
        forged = dict(honest)
        forged["xpc_service_name"] = "com.digithings.merge-queue"
        self.assertEqual(_guard.decide(honest), _guard.decide(forged))

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

    def test_the_loaded_job_has_to_agree_with_the_installed_plist(self):
        """The installed plist is what the house says the job runs."""
        facts = _launchd_facts()
        facts["installed_arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("not the installed one", reason)

    def test_a_job_without_an_installed_plist_is_refused(self):
        """A job whose canonical plist is missing was not installed by the org."""
        facts = _launchd_facts(installed_arguments=None)
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("missing or unreadable", reason)

    def test_the_installed_plist_may_not_carry_extra_arguments(self):
        """The house jobs run the runner with no arguments of their own."""
        facts = _launchd_facts()
        arguments = ["/usr/bin/python3", os.path.realpath(_RUNNER), "--pr", "368"]
        facts["installed_arguments"] = arguments
        facts["launchd_job"]["arguments"] = arguments
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("arguments", reason)

    def test_a_job_that_does_not_run_a_python_interpreter_is_refused(self):
        """The house jobs run the runner with a python interpreter."""
        facts = _launchd_facts()
        arguments = ["/usr/bin/ruby", os.path.realpath(_RUNNER)]
        facts["installed_arguments"] = arguments
        facts["launchd_job"]["arguments"] = arguments
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("python interpreter", reason)

    def test_the_post_merge_driver_next_to_the_runner_is_trusted(self):
        """The live post-merge job runs postmerge_ci.py, which drives the runner.

        That is the same launcher as far as the org is concerned, so the driver
        has to be accepted - and only when it sits in the runner's own
        directory and is one of the known driver scripts.
        """
        driver = os.path.join(os.path.dirname(os.path.realpath(_RUNNER)),
                              "postmerge_ci.py")
        facts = _launchd_facts(
            launchd_label="ai.digithings.local-ci-postmerge",
            launchd_job={
                "program": "/usr/bin/python3",
                "arguments": ["/usr/bin/python3", driver],
                "path": os.path.expanduser(
                    "~/Library/LaunchAgents/ai.digithings.local-ci-postmerge.plist"),
                "pid": 4242,
            },
            installed_arguments=["/usr/bin/python3", driver])
        allowed, reason = _guard.decide(facts)
        self.assertTrue(allowed, reason)

    def test_a_driver_outside_the_runner_directory_is_refused(self):
        driver = "/tmp/seat/postmerge_ci.py"
        facts = _launchd_facts(
            launchd_label="ai.digithings.local-ci-postmerge",
            launchd_job={
                "program": "/usr/bin/python3",
                "arguments": ["/usr/bin/python3", driver],
                "path": os.path.expanduser(
                    "~/Library/LaunchAgents/ai.digithings.local-ci-postmerge.plist"),
                "pid": 4242,
            },
            installed_arguments=["/usr/bin/python3", driver])
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("neither the runner", reason)

    def test_a_script_that_is_not_a_known_driver_is_refused(self):
        """A job may not point at a script of its own, next to the runner or not."""
        script = os.path.join(os.path.dirname(os.path.realpath(_RUNNER)), "seat_ci.py")
        facts = _launchd_facts(
            launchd_job={
                "program": "/usr/bin/python3",
                "arguments": ["/usr/bin/python3", script],
                "path": os.path.expanduser(
                    "~/Library/LaunchAgents/ai.digithings.local-ci.plist"),
                "pid": 4242,
            },
            installed_arguments=["/usr/bin/python3", script])
        allowed, reason = _guard.decide(facts)
        self.assertFalse(allowed)
        self.assertIn("neither the runner", reason)

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

    def test_a_command_line_that_only_mentions_the_entrypoint_is_refused(self):
        """The parent has to BE the entrypoint, not mention it on the way.

        A command line that carries the path somewhere in it is some other
        process that happens to know the name.
        """
        for argv in (
            ["/bin/sh", "-c", "echo /opt/local-ci/worker_entrypoint.sh; python3 local_ci.py"],
            ["/bin/sh -c 'echo /opt/local-ci/worker_entrypoint.sh'"],
        ):
            facts = _container_facts()
            facts["ancestors"] = [{"pid": 1, "argv": argv}]
            allowed, reason = _guard.decide(facts)
            self.assertFalse(allowed, argv)
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
        untrusted_label = _launchd_facts(launchd_label="com.digithings.merge-queue")
        forged_label = _seat_facts(xpc_service_name="ai.digithings.local-ci")
        wrong_parent = _launchd_facts(ppid=1234)
        not_loaded = _launchd_facts(launchd_job=None)
        other_file = _launchd_facts()
        other_file["launchd_job"]["arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        other_file["installed_arguments"] = ["/usr/bin/python3", "/tmp/seat/local_ci.py"]
        container_root = _container_facts(runner="/tmp/local_ci.py")
        container_parent = _container_facts()
        container_parent["ancestors"] = [
            {"pid": 1, "argv": ["/bin/sh", "-c", "python3 local_ci.py --pr 368"]}]
        no_credential = _container_facts(ci_token=False)
        return [_seat_facts(), untrusted_label, forged_label, wrong_parent, not_loaded,
                other_file, container_root, container_parent, no_credential]

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


class LaunchctlListTests(unittest.TestCase):
    """The job table launchctl prints: this is where the label comes from.

    The label in the environment is forgeable, so the guard reads the label out
    of launchd's own table and only believes a job whose pid is this process's
    pid.
    """

    REAL = """PID\tStatus\tLabel
47393\t0\tai.digithings.local-ci-postmerge
-\t0\tai.digithings.local-ci
1234\t-9\tcom.digithings.merge-queue
"""

    def test_the_pid_of_every_running_job_is_read(self):
        jobs = _guard.parse_launchctl_list(self.REAL)
        self.assertEqual(jobs[47393], "ai.digithings.local-ci-postmerge")
        self.assertEqual(jobs[1234], "com.digithings.merge-queue")

    def test_a_job_that_is_not_running_has_no_pid(self):
        jobs = _guard.parse_launchctl_list(self.REAL)
        self.assertNotIn("-", jobs)
        self.assertNotIn("ai.digithings.local-ci", jobs.values())

    def test_the_header_is_not_a_job(self):
        jobs = _guard.parse_launchctl_list(self.REAL)
        self.assertNotIn("PID", jobs.values())
        self.assertNotIn("Label", jobs.values())

    def test_the_table_is_read_from_the_system_launchctl(self):
        """The real table on this machine has to parse, and the guard's own pid
        is in it or is not - either way the parse must not raise."""
        jobs = _guard.launchctl_job_labels()
        if jobs is not None:
            self.assertIsInstance(jobs, dict)
            for pid, label in jobs.items():
                self.assertIsInstance(pid, int)
                self.assertIsInstance(label, str)


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


class SystemToolTests(unittest.TestCase):
    """The guard asks the system about the system, never the PATH.

    A seat that puts its own `launchctl` or `ps` first on the PATH would
    otherwise answer the guard's own question: the forged job reports the
    seat's pid, the forged plist path looks canonical, and the forged
    arguments match the file that is running.
    """

    def test_the_tools_the_guard_uses_are_system_files(self):
        for name in ("launchctl", "ps"):
            path = _guard.trusted_tool(name)
            if path is not None:
                self.assertTrue(os.path.isabs(path), path)
                self.assertTrue(_guard._is_system_binary(path), path)
        self.assertIsNone(_guard.trusted_tool("definitely-not-a-tool"))

    def test_a_file_the_seat_owns_is_not_a_system_tool(self):
        tmp = tempfile.mkdtemp(prefix="launch-guard-")
        try:
            mine = os.path.join(tmp, "launchctl")
            with open(mine, "w", encoding="utf-8") as fh:
                fh.write("#!/bin/sh\nexit 0\n")
            self.assertFalse(_guard._is_system_binary(mine))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_guard_does_not_run_a_launchctl_from_the_path(self):
        """A fake launchctl on the PATH is never run."""
        report, markers = _collect_in_child(
            self, hostile=True, extra={"XPC_SERVICE_NAME": "ai.digithings.local-ci"})
        self.assertIs(report["allowed"], False, report.get("reason"))
        self.assertFalse(os.path.exists(markers["launchctl"]),
                         "the guard ran a launchctl from the PATH")

    def test_the_guard_does_not_run_a_ps_from_the_path(self):
        report, markers = _collect_in_child(self, hostile=True)
        self.assertIs(report["allowed"], False, report.get("reason"))
        self.assertFalse(os.path.exists(markers["ps"]), "the guard ran a ps from the PATH")

    def test_an_orphaned_process_with_a_shadowed_launchctl_is_refused(self):
        """The whole attack, end to end: the shape the 21 Oct bypass would take.

        The child orphans itself to launchd, so its parent pid is 1; it claims
        the trusted label; and the launchctl on its PATH reports a job with its
        own pid, the canonical plist path and the runner's own path. A guard
        that believed the PATH would call this the daemon.
        """
        report, markers = _collect_in_orphan(
            self, extra={"XPC_SERVICE_NAME": "ai.digithings.local-ci"})
        self.assertNotEqual(report["ppid"], os.getpid(), "the child was not orphaned")
        if sys.platform == "darwin":
            self.assertEqual(report["ppid"], 1, "the orphan was not reparented to launchd")
        self.assertIs(report["allowed"], False, report.get("reason"))
        self.assertFalse(os.path.exists(markers["launchctl"]),
                         "the guard ran a launchctl from the PATH")


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
        _guard.reset_decisions()
        self._spec = importlib.util.spec_from_file_location(
            "local_ci_under_test", _RUNNER)
        self._mod = importlib.util.module_from_spec(self._spec)
        sys.modules["local_ci_under_test"] = self._mod
        self._spec.loader.exec_module(self._mod)
        self._home = tempfile.mkdtemp(prefix="launch-guard-home-")
        self._old_home = os.environ.get("HOME")
        os.environ["HOME"] = self._home

    def tearDown(self):
        _guard.reset_decisions()
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

    # --- the path the live post-merge job takes -----------------------------
    #
    # The post-merge launchd job runs postmerge_ci.py, which imports the runner
    # and calls run_checks() in-process. It never goes through main(), so a
    # guard that only lived in main() would not be asked on the path the live
    # job takes - and that path takes the worktree, the log and the checks.

    def _refuse(self, call):
        """Run `call` with seat-shaped facts and return the exit code."""
        original = _guard.collect_facts
        _guard.collect_facts = lambda runner_path: _seat_facts()
        _guard.reset_decisions()
        try:
            with self.assertRaises(SystemExit) as caught:
                call()
            return caught.exception.code
        finally:
            _guard.collect_facts = original
            _guard.reset_decisions()

    def test_the_post_merge_path_asks_the_guard(self):
        """run_checks() is the entry point the live post-merge job uses."""
        out = io.StringIO()
        pr = {"headRefOid": "0" * 40, "baseRefName": "develop",
              "title": "chore(develop): post-merge tip check"}
        code = self._refuse(lambda: self._mod.run_checks(pr, out))
        self.assertEqual(code, _guard.EX_CONFIG)
        self.assertEqual(out.getvalue(), "", "the checks ran before they were refused")

    def test_the_lock_asks_the_guard(self):
        code = self._refuse(self._mod.acquire_lock)
        self.assertEqual(code, _guard.EX_CONFIG)
        self.assertFalse(
            os.path.exists(os.path.join(self._home, ".config", "digithings", "state",
                                        "local-ci.lock")),
            "the lock was taken before the run was refused")

    def test_the_worktree_asks_the_guard(self):
        out = io.StringIO()
        code = self._refuse(lambda: self._mod.prepare_wt(368, "0" * 40, "develop", out))
        self.assertEqual(code, _guard.EX_CONFIG)
        self.assertEqual(out.getvalue(), "", "the worktree ran before it was refused")

    def test_every_entry_point_that_does_work_asks_the_guard(self):
        """The guard is asked where the work happens, not only in main()."""
        with open(_RUNNER, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        functions = {node.name: node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef)}
        for name in ("main", "acquire_lock", "prepare_wt", "run_checks"):
            self.assertIn(name, functions, f"the runner has no {name}()")
            calls = [node for node in ast.walk(functions[name])
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name)
                     and node.func.id == "_guard"]
            self.assertTrue(calls, f"{name}() does not ask the guard")

    def test_the_guard_is_asked_before_the_first_side_effect(self):
        """In main() the ask comes before the lock, the watchdog and GitHub."""
        with open(_RUNNER, "r", encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        main = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
        asked_at = None
        for index, statement in enumerate(main.body):
            for node in ast.walk(statement):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_guard"):
                    asked_at = index
        self.assertIsNotNone(asked_at, "main() does not ask the guard")
        for index, statement in enumerate(main.body):
            if index >= asked_at:
                continue
            for node in ast.walk(statement):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("acquire_lock", "watchdog", "status",
                                             "list_prs")):
                    self.fail("main() does something before it asks the guard")


class EnforceCacheTests(unittest.TestCase):
    """The decision is asked for once per process and then remembered.

    The runner asks the guard at every entry point that does work, and the
    facts cannot change under it, so the guard asks the system once.
    """

    def setUp(self):
        _guard.reset_decisions()

    def tearDown(self):
        _guard.reset_decisions()

    def test_the_second_ask_does_not_ask_the_system_again(self):
        calls = []

        def counting_collect(runner_path):
            calls.append(runner_path)
            return _seat_facts()

        original = _guard.collect_facts
        _guard.collect_facts = counting_collect
        try:
            with self.assertRaises(SystemExit):
                _guard.enforce(_RUNNER, "local-ci")
            with self.assertRaises(SystemExit):
                _guard.enforce(_RUNNER, "local-ci")
        finally:
            _guard.collect_facts = original
        self.assertEqual(len(calls), 1, "the guard asked the system twice")

    def test_an_allowed_decision_is_remembered(self):
        original = _guard.collect_facts
        _guard.collect_facts = lambda runner_path: _launchd_facts()
        try:
            self.assertTrue(_guard.enforce(_RUNNER, "local-ci"))
            self.assertTrue(_guard.enforce(_RUNNER, "local-ci"))
        finally:
            _guard.collect_facts = original


if __name__ == "__main__":
    unittest.main()
