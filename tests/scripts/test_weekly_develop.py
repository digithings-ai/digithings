#!/usr/bin/env python3
"""Unit tests for the weekly develop checks (CHR-790). Stdlib only:
`/usr/bin/python3 -m unittest test_weekly_develop -v`."""

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import pytest
except ImportError:  # the file also runs as a plain unittest module
    pytest = None
else:
    pytestmark = pytest.mark.unit

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))
_spec = importlib.util.spec_from_file_location(
    "weekly_develop", os.path.join(_SCRIPTS, "weekly_develop.py")
)
wd = importlib.util.module_from_spec(_spec)
sys.modules["weekly_develop"] = wd
_spec.loader.exec_module(wd)

DAY = 24 * 3600
NOW = 1_800_000_000.0
SHA = "a" * 40


class FakeSh:
    """Stands in for local_ci.sh: records calls, fakes git, scores checks."""

    def __init__(self, fail=(), missing=(), fetch_rc=0, add_rc=0):
        self.calls = []
        self.fail = set(fail)
        self.missing = set(missing)
        self.fetch_rc = fetch_rc
        self.add_rc = add_rc

    def __call__(self, cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
        self.calls.append((list(cmd), cwd, name))
        if cmd[0] == "git":
            verb = cmd[3]
            if verb == "fetch":
                return self.fetch_rc, ""
            if verb == "rev-parse":
                return 0, SHA + "\n"
            if verb == "worktree" and cmd[4] == "add":
                if self.add_rc == 0:
                    wt = cmd[-2]
                    for _, argv in wd.CHECKS:
                        if argv[0] in self.missing:
                            continue
                        path = os.path.join(wt, argv[0])
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        open(path, "w").close()
                return self.add_rc, ""
            return 0, ""
        if out is not None:
            out.write("check output for %s\n" % name)
        check = (name or "").split(":", 1)[1]
        return (1 if check in self.fail else 0), ""

    def names(self):
        return [n for _, _, n in self.calls]


class WeeklyDevelopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.logd = os.path.join(self.tmp, "logs")
        self.state = os.path.join(self.tmp, "state", "weekly.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, sh, now=NOW):
        return wd.run("/repo", self.logd, self.state, sh, "/py", now=now)

    def _state(self):
        with open(self.state) as f:
            return json.load(f)

    def _jsonl(self):
        with open(os.path.join(self.logd, "weekly-develop.jsonl")) as f:
            return [json.loads(line) for line in f]

    def _alert(self):
        return os.path.join(os.path.dirname(self.state), "alerts", "weekly-develop.alert")

    def _alert_lines(self):
        with open(self._alert()) as f:
            return f.read().splitlines()

    # --- when a run is due

    def test_due_without_state(self):
        self.assertTrue(wd.due(self.state, NOW))

    def test_due_with_unreadable_state(self):
        os.makedirs(os.path.dirname(self.state))
        with open(self.state, "w") as f:
            f.write("{not json")
        self.assertTrue(wd.due(self.state, NOW))

    def test_not_due_inside_the_week_and_due_after_it(self):
        self._run(FakeSh())
        self.assertFalse(wd.due(self.state, NOW + 6 * DAY))
        self.assertTrue(wd.due(self.state, NOW + 7 * DAY))

    def test_not_due_runs_nothing(self):
        self._run(FakeSh())
        sh = FakeSh()
        self.assertIsNone(self._run(sh, now=NOW + DAY))
        self.assertEqual(sh.calls, [])

    # --- what a run does

    def test_all_three_checks_run_in_the_develop_checkout(self):
        sh = FakeSh()
        record = self._run(sh)
        self.assertEqual(record["failed"], [])
        self.assertEqual(record["sha"], SHA)
        checks = [(c, cwd) for c, cwd, n in sh.calls if c[0] == "/py"]
        self.assertEqual(
            [c[1:] for c, _ in checks],
            [
                ["scripts/check_doc_links.py"],
                ["scripts/check_adr_numbering.py"],
                ["scripts/agents_init.py", "--check"],
            ],
        )
        add = next(c for c, _, n in sh.calls if n == "weekly-develop:checkout")
        self.assertEqual(add[-1], SHA)
        self.assertIn("--detach", add)
        self.assertTrue(all(cwd == add[-2] for _, cwd in checks))

    def test_fetches_develop_before_checking_out(self):
        sh = FakeSh()
        self._run(sh)
        names = sh.names()
        self.assertLess(names.index("weekly-develop:fetch"), names.index("weekly-develop:checkout"))
        fetch = sh.calls[names.index("weekly-develop:fetch")][0]
        self.assertEqual(fetch[-2:], ["origin", "develop"])

    def test_worktree_is_removed_and_temp_dir_gone(self):
        sh = FakeSh(fail=("doc-links",))
        self._run(sh)
        add = next(c for c, _, n in sh.calls if n == "weekly-develop:checkout")
        remove = next(c for c, _, n in sh.calls if n == "weekly-develop:cleanup")
        self.assertEqual(remove[-1], add[-2])
        self.assertFalse(os.path.exists(os.path.dirname(add[-2])))

    def test_a_failing_check_is_named_and_the_others_still_run(self):
        sh = FakeSh(fail=("adr-numbering",))
        record = self._run(sh)
        self.assertEqual(record["failed"], ["adr-numbering"])
        self.assertEqual(len([c for c, _, _ in sh.calls if c[0] == "/py"]), 3)
        self.assertIn("FAIL adr-numbering", wd.summary(record))

    def test_a_missing_check_script_fails_closed(self):
        sh = FakeSh(missing=("scripts/agents_init.py",))
        record = self._run(sh)
        self.assertEqual(record["failed"], ["agents-drift (missing scripts/agents_init.py)"])
        self.assertNotIn("weekly-develop:agents-drift", sh.names())

    def test_records_log_jsonl_and_next_week(self):
        record = self._run(FakeSh(fail=("doc-links",)))
        self.assertEqual(self._jsonl(), [record])
        self.assertEqual(self._state()["next_at"], NOW + wd.WEEK_SECS)
        log = os.path.join(self.logd, "weekly-develop-%s.log" % SHA[:12])
        self.assertEqual(record["log"], log)
        with open(log) as f:
            body = f.read()
        self.assertIn("===== doc-links", body)
        self.assertIn("check output for weekly-develop:doc-links", body)

    def test_an_unreachable_develop_retries_in_an_hour(self):
        sh = FakeSh(fetch_rc=1)
        record = self._run(sh)
        self.assertEqual(record["failed"], ["fetch"])
        self.assertNotIn("weekly-develop:checkout", sh.names())
        self.assertEqual(self._state()["next_at"], NOW + wd.RETRY_SECS)
        self.assertIn("FAIL fetch", wd.summary(record))

    def test_a_failed_checkout_retries_in_an_hour(self):
        sh = FakeSh(add_rc=128)
        record = self._run(sh)
        self.assertEqual(record["failed"], ["checkout"])
        self.assertNotIn("weekly-develop:cleanup", sh.names())
        self.assertEqual(self._state()["next_at"], NOW + wd.RETRY_SECS)

    def test_summary_ok(self):
        self.assertEqual(
            wd.summary({"sha": SHA, "failed": []}),
            "weekly-develop: %s ok (doc-links, adr-numbering, agents-drift)" % SHA[:12],
        )

    # --- the local alert

    def test_a_failed_run_writes_a_timestamped_alert(self):
        self._run(FakeSh(fail=("doc-links",)))
        self.assertTrue(os.path.isfile(self._alert()))
        lines = self._alert_lines()
        self.assertEqual(len(lines), 1)
        when = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW))
        self.assertTrue(lines[0].startswith(when), lines[0])
        self.assertIn("FAIL", lines[0])
        self.assertIn(SHA[:12], lines[0])
        self.assertIn("doc-links", lines[0])

    def test_a_second_failure_appends(self):
        self._run(FakeSh(fail=("doc-links",)))
        self._run(FakeSh(fail=("adr-numbering",)), now=NOW + wd.WEEK_SECS)
        lines = self._alert_lines()
        self.assertEqual(len(lines), 2)
        self.assertIn("doc-links", lines[0])
        self.assertIn("adr-numbering", lines[1])

    def test_a_passing_run_clears_the_alert(self):
        self._run(FakeSh(fail=("doc-links",)))
        self.assertTrue(os.path.exists(self._alert()))
        self._run(FakeSh(), now=NOW + wd.WEEK_SECS)
        self.assertFalse(os.path.exists(self._alert()))

    def test_a_passing_run_without_an_alert_writes_none(self):
        self._run(FakeSh())
        self.assertFalse(os.path.exists(self._alert()))

    def test_an_unreachable_develop_raises_an_alert(self):
        self._run(FakeSh(fetch_rc=1))
        lines = self._alert_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("FAIL", lines[0])
        self.assertIn("unknown", lines[0])
        self.assertIn("fetch", lines[0])

    def test_alert_write_errors_never_fail_the_run(self):
        state_dir = os.path.dirname(self.state)
        os.makedirs(state_dir)
        with open(os.path.join(state_dir, "alerts"), "w") as f:
            f.write("not a directory\n")
        record = self._run(FakeSh(fail=("doc-links",)))
        self.assertEqual(record["failed"], ["doc-links"])
        self.assertTrue(os.path.isfile(self.state))

    # --- interpreter choice

    def test_interpreter_prefers_the_first_executable_candidate(self):
        py = os.path.join(self.tmp, "python")
        with open(py, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(py, 0o755)
        self.assertEqual(wd.interpreter([os.path.join(self.tmp, "nope"), py]), py)

    def test_interpreter_falls_back_to_this_one(self):
        self.assertEqual(wd.interpreter([os.path.join(self.tmp, "nope"), ""]), sys.executable)


def _git(*args, cwd=None):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _real_sh(cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if out is not None:
        out.write(p.stdout + p.stderr)
    return p.returncode, p.stdout


@unittest.skipUnless(shutil.which("git"), "git is required")
class WeeklyDevelopRealGitTest(unittest.TestCase):
    """End to end against a real origin: develop's tip is what gets checked."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        src = os.path.join(self.tmp, "src")
        os.makedirs(os.path.join(src, "scripts"))
        scripts = {
            "check_doc_links.py": "import sys; sys.exit(0)\n",
            "check_adr_numbering.py": "import sys; sys.exit(1)\n",
            "agents_init.py": "import sys; sys.exit(0 if sys.argv[1:] == ['--check'] else 2)\n",
        }
        for name, body in scripts.items():
            with open(os.path.join(src, "scripts", name), "w") as f:
                f.write(body)
        _git("init", "-q", "-b", "develop", cwd=src)
        _git("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", ".", cwd=src)
        _git(
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-q",
            "-m",
            "init",
            cwd=src,
        )
        self.main = os.path.join(self.tmp, "main")
        _git("clone", "-q", src, self.main)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_runs_the_develop_tip_and_cleans_up(self):
        logd = os.path.join(self.tmp, "logs")
        state = os.path.join(self.tmp, "state.json")
        record = wd.run(self.main, logd, state, _real_sh, sys.executable, now=NOW)
        self.assertEqual(record["failed"], ["adr-numbering"])
        self.assertEqual(len(record["sha"]), 40)
        listed = subprocess.run(
            ["git", "-C", self.main, "worktree", "list"], capture_output=True, text=True, check=True
        ).stdout
        self.assertEqual(len(listed.strip().splitlines()), 1, listed)


class LocalCiHookTest(unittest.TestCase):
    """The runner calls the weekly run once per tick, after the PR work."""

    def test_main_calls_the_weekly_run_after_the_producer_guard(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py")) as f:
            tree = ast.parse(f.read())
        main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        calls = [
            n.func.id
            for n in ast.walk(main)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        self.assertIn("weekly_develop_tick", calls)
        self.assertLess(
            calls.index("check_required_context_producers"), calls.index("weekly_develop_tick")
        )


if __name__ == "__main__":
    unittest.main()
