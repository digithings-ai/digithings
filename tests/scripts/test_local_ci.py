#!/usr/bin/env python3
"""Unit tests for the local-ci memory gate parsers (DIG-3783). Stdlib only:
`/usr/bin/python3 -m unittest test_local_ci -v`."""
import ast
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))
if _SCRIPTS not in sys.path:
    # local_ci imports review_applied and pr_template from its own directory; without
    # this the repo's suite would silently exercise the ImportError branch while the
    # host exercises the real modules (DIG-4490 review).
    sys.path.insert(0, _SCRIPTS)
_spec = importlib.util.spec_from_file_location(
    "local_ci", os.path.join(_SCRIPTS, "local_ci.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["local_ci"] = _mod
_spec.loader.exec_module(_mod)


class _AllowedGuard:
    """The launch guard, stubbed to allow the run (DIG-4796).

    The real guard lives in scripts/local-ci/launch_guard.py and is tested in
    test_launch_guard.py. The tests here cover the flow behind it, so the
    guard is stubbed for the whole module: the runner asks the guard at every
    entry point that does work, and a stub that is only in place for one test
    would leave the others refused.
    """

    @staticmethod
    def enforce(runner_path, ctx, facts=None):
        return True


_mod.launch_guard = _AllowedGuard


# vm_stat sample shaped like the 09:20 CEST evidence on DIG-3783: free 3,635 +
# speculative 10,206 + purgeable 7,206 pages read ~345MB while 991,764 inactive
# pages (~15.5GB) sat reclaimable at 69% system-wide free.
VM_STAT_69PCT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                    3635.
Pages active:                                1070908.
Pages inactive:                               991764.
Pages speculative:                             10206.
Pages throttled:                                   0.
Pages wired down:                             316119.
Pages purgeable:                                7206.
"""

PRESSURE_69PCT = """The system has 51539607552 (3145728 pages with a page size of 16384).

System-wide memory free percentage: 69%
"""


class GateParserTest(unittest.TestCase):
    def test_available_counts_inactive_pages(self):
        # (3635 + 10206 + 7206 + 991764) * 16384 / 1MiB == 15825.2
        self.assertEqual(
            _mod.parse_vm_stat_available_mb(VM_STAT_69PCT), 15825.2)

    def test_available_clears_the_mb_gate(self):
        self.assertGreater(
            _mod.parse_vm_stat_available_mb(VM_STAT_69PCT), _mod.MIN_AVAIL_MB)

    def test_old_formula_would_skip_here(self):
        # The DIG-3783 defect, pinned: free + speculative + purgeable only.
        old = round((3635 + 10206 + 7206) * 16384 / (1024 * 1024), 1)
        self.assertEqual(old, 328.9)
        self.assertLess(old, _mod.MIN_AVAIL_MB)

    def test_available_fail_open(self):
        self.assertEqual(_mod.parse_vm_stat_available_mb(""), 99999.0)
        self.assertEqual(_mod.parse_vm_stat_available_mb("garbage"), 99999.0)
        missing = VM_STAT_69PCT.replace("Pages inactive:", "Pages missing:")
        self.assertEqual(_mod.parse_vm_stat_available_mb(missing), 99999.0)

    def test_pressure_pct_parses(self):
        self.assertEqual(_mod.parse_memory_pressure_pct(PRESSURE_69PCT), 69.0)

    def test_pressure_pct_absent_is_none(self):
        self.assertIsNone(_mod.parse_memory_pressure_pct(""))
        self.assertIsNone(_mod.parse_memory_pressure_pct("no such line\n"))

    def test_pressure_gate_threshold(self):
        self.assertEqual(_mod.MIN_FREE_PCT, 20.0)
        self.assertGreater(
            _mod.parse_memory_pressure_pct(PRESSURE_69PCT), _mod.MIN_FREE_PCT)

    def test_skip_prefix_contract_unchanged(self):
        # pending() re-queues PRs whose description starts with this (DIG-3706).
        self.assertEqual(_mod.SKIP_PREFIX, "local-ci skipped:")




class WorkerGateTest(unittest.TestCase):
    def setUp(self):
        self._gh = _mod.gh

    def tearDown(self):
        _mod.gh = self._gh

    def test_apps_glob_matches_nested_not_sibling(self):
        rx = _mod.glob_to_regex("apps/digithings-cron/**")
        self.assertTrue(rx.match("apps/digithings-cron/src/jobs.ts"))
        self.assertIsNone(rx.match("apps/digithings-cron-extra/src/jobs.ts"))

    def test_wrangler_catchall_zero_segment(self):
        rx = _mod.glob_to_regex("apps/**/wrangler.toml")
        self.assertTrue(rx.match("apps/wrangler.toml"))
        self.assertTrue(rx.match("apps/digithings-cron/wrangler.toml"))
        self.assertIsNone(rx.match("apps/digithings-cron/wrangler.toml.bak"))

    def test_root_lockfiles_root_only(self):
        for pat in ("package.json", "package-lock.json"):
            rx = _mod.glob_to_regex(pat)
            self.assertTrue(rx.match(pat))
            self.assertIsNone(rx.match("apps/dashboard-api/" + pat))

    def test_gate_hit_pattern_major(self):
        pats = ["apps/digithings-cron/**", "package-lock.json"]
        self.assertEqual(
            _mod.worker_gate_hit(["docs/a.md", "package-lock.json"], pats),
            ("package-lock.json", "package-lock.json"))
        self.assertIsNone(_mod.worker_gate_hit(["docs/a.md"], pats))

    def test_gate_hit_no_trip_for_nonworker_app(self):
        pats = list(_mod.WORKER_GATE_PATTERNS)
        self.assertIsNone(_mod.worker_gate_hit(["apps/digichat/src/a.ts"], pats))
        self.assertEqual(
            _mod.worker_gate_hit(["apps/dashboard-api/src/i.ts"], pats),
            ("apps/dashboard-api/**", "apps/dashboard-api/src/i.ts"))

    def test_parse_workers_patterns(self):
        text = "changes:\nworkers:\n  - 'apps/a/**'\n  # comment\n  - apps/b/**\n\nother:\n  - x\n"
        self.assertEqual(_mod.parse_workers_patterns(text),
                         ["apps/a/**", "apps/b/**"])
        self.assertEqual(_mod.parse_workers_patterns("nope:\n  - x\n"), [])

    def test_worker_patterns_fallback(self):
        self.assertEqual(_mod.worker_patterns("/nonexistent-wt-4010"),
                         list(_mod.WORKER_GATE_PATTERNS))

    def test_worker_patterns_tmpdir_block_wins(self):
        d = tempfile.mkdtemp(prefix="wt-4010-")
        try:
            os.makedirs(os.path.join(d, "scripts"))
            with open(os.path.join(d, "scripts", "ci_paths.yaml"), "w") as f:
                f.write("workers:\n  - 'apps/only-this/**'\n")
            self.assertEqual(_mod.worker_patterns(d), ["apps/only-this/**"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_changed_file_names_slurp_and_flat(self):
        slurp = [[{"filename": "apps/digithings-cron/src/j.ts", "status": "modified"}],
                 [{"filename": "docs/a.md", "status": "removed"}]]
        self.assertEqual(_mod.changed_file_names(slurp),
                         ["apps/digithings-cron/src/j.ts", "docs/a.md"])
        self.assertEqual(_mod.changed_file_names([{"filename": "x.ts"}]), ["x.ts"])

    def test_changed_file_names_garbage_none(self):
        for bad in (None, {}, "str", [], [{"nope": 1}], [{"filename": ""}]):
            self.assertIsNone(_mod.changed_file_names(bad))

    def test_worker_gate_fetch_fail_closed(self):
        _mod.gh = lambda *a: None
        self.assertEqual(_mod.worker_gate({"number": 42}, "/nonexistent-wt-4010"),
                         (None, None))

    def test_worker_gate_bad_json_closed(self):
        _mod.gh = lambda *a: "not json{"
        self.assertEqual(_mod.worker_gate({"number": 7}, "/nonexistent-wt-4010"),
                         (None, None))

    def test_worker_gate_hit_and_args(self):
        seen = {}
        payload = [[{"filename": "apps/digithings-cron/src/j.ts"}],
                   [{"filename": "package-lock.json"}]]

        def fake_gh(*a):
            seen["args"] = list(a)
            return json.dumps(payload)

        _mod.gh = fake_gh
        n, hit = _mod.worker_gate({"number": 42}, "/nonexistent-wt-4010")
        self.assertEqual(n, 2)
        self.assertEqual(hit, ("apps/digithings-cron/**", "apps/digithings-cron/src/j.ts"))
        self.assertIn("--slurp", seen["args"])
        self.assertTrue(any("pulls/42/files" in x for x in seen["args"]))


class WorkerBuildTest(unittest.TestCase):
    def _rec(self, fails_on=(), npm_ci_ok=True):
        calls = []

        def rec(name, cmd, timeout=1800, cwd=None):
            calls.append((name, cmd, timeout, cwd))
            if name == "worker-build:npm-ci":
                return npm_ci_ok
            return name not in fails_on

        return calls, rec

    def test_build_all_green_runs_one_step_per_app(self):
        calls, rec = self._rec()
        self.assertEqual(_mod.worker_build("/wt-4010", rec), [])
        # One `npm ci`, then one dry run per app. The count is read from the
        # list rather than written down: a hard-coded number went stale when
        # `twelvex-runner` joined the list (DIG-4753) and the suite was red on
        # develop, so the number says what it means and the list says how many.
        self.assertEqual(len(calls), 1 + len(_mod.WORKER_APPS))
        name0, cmd0, t0, cwd0 = calls[0]
        self.assertEqual(name0, "worker-build:npm-ci")
        self.assertEqual(cmd0, ["npm", "ci", "--no-audit", "--no-fund"])
        self.assertEqual(t0, 1800)
        self.assertIsNone(cwd0)
        apps = [c[0].split(":", 1)[1] for c in calls[1:]]
        self.assertEqual(apps, list(_mod.WORKER_APPS))
        for name, cmd, timeout, cwd in calls[1:]:
            self.assertEqual(timeout, _mod.WORKER_DRY_RUN_TIMEOUT)
            self.assertEqual(timeout, 300)
            app = name.split(":", 1)[1]
            self.assertEqual(cwd, os.path.join("/wt-4010", "apps", app))
            self.assertIn("--dry-run", cmd)
            self.assertIn("--containers-rollout=none", cmd)
            self.assertIn("--outdir", cmd)
        outdir = calls[-1][1][calls[-1][1].index("--outdir") + 1]
        self.assertFalse(os.path.exists(outdir))

    def test_build_red_app_recorded_later_apps_run(self):
        calls, rec = self._rec(fails_on=("worker-build:dashboard-api",))
        self.assertEqual(_mod.worker_build("/wt-4010", rec),
                         ["worker-build:dashboard-api"])
        self.assertEqual(len(calls), 1 + len(_mod.WORKER_APPS))

    def test_build_npm_ci_failure_single_call(self):
        calls, rec = self._rec(npm_ci_ok=False)
        self.assertEqual(_mod.worker_build("/wt-4010", rec), ["worker-build:npm-ci"])
        self.assertEqual(len(calls), 1)


class StaticGateWiringTest(unittest.TestCase):
    """The R0 client-literal scan runs in the local-ci static gates (DIG-4043)."""

    def _tree(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py")) as f:
            return ast.parse(f.read())

    def _static_lists(self, tree):
        return [
            node for node in ast.walk(tree)
            if isinstance(node, ast.List)
            and sum(
                isinstance(e, ast.Constant) and e.value == "scripts/check_example_credentials.py"
                for e in node.elts
            ) == 1
        ]

    def test_r0_scan_in_static_gate_list(self):
        found = self._static_lists(self._tree())
        self.assertEqual(len(found), 1)
        names = [e.value for e in found[0].elts if isinstance(e, ast.Constant)]
        self.assertEqual(names.count("scripts/check_r0_no_client_literals.py"), 1)

    def test_static_list_drives_single_step_call(self):
        tree = self._tree()
        found = self._static_lists(tree)
        self.assertEqual(len(found), 1)
        loops = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.For) and node.iter is found[0]
        ]
        self.assertEqual(len(loops), 1)
        steps = [
            node for node in ast.walk(loops[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "step"
        ]
        self.assertEqual(len(steps), 1)

    def test_docstring_names_r0_scan(self):
        self.assertIn("R0 client-literal scan", ast.get_docstring(self._tree()))


class PrepareWorktreeTest(unittest.TestCase):
    """Stale-worktree incident (17 Oct 2026): a silent checkout failure must
    fail closed, never run gates on whatever tree is left in WT."""
    SHA = "a" * 40

    def _run(self, heads, wt_exists=True, own=True):
        import io
        calls = []
        seq = list(heads)
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        if wt_exists:
            os.mkdir(wt)
            if own:  # a worktree this runner created carries its sentinel
                open(os.path.join(wt, ".local-ci-worktree"), "w").write(self.SHA)
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            calls.append(cmd)
            return 0, ""
        _mod.sh = fake_sh
        _mod.wt_head = lambda: seq.pop(0) if seq else None
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            res = _mod.prepare_wt(7, self.SHA, "develop", buf)
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)
        return res, calls, buf.getvalue()

    def test_head_matches_ok(self):
        (ok, why), calls, _ = self._run([self.SHA, self.SHA])
        self.assertTrue(ok)
        self.assertEqual(why, "")
        fetch = calls[0]
        self.assertIn("main", fetch)
        self.assertIn("pull/7/head", fetch)

    def test_checkout_silently_failed_fails_closed(self):
        stale = "b" * 40
        (ok, why), _, text = self._run([stale, stale])
        self.assertFalse(ok)
        self.assertIn("!=", why)
        self.assertIn("no gate ran", text)

    def test_unreadable_worktree_is_rebuilt(self):
        (ok, _), calls, text = self._run([None, self.SHA])
        self.assertTrue(ok)
        self.assertIn("rebuilding", text)
        self.assertTrue(any(c[:3] == ["git", "worktree", "prune"] for c in calls))
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_a_directory_we_did_not_create_is_never_deleted(self):
        """LOCAL_CI_WT is operator-supplied: a typo must not delete someone's tree."""
        (ok, why), calls, _ = self._run([None, self.SHA], own=False)
        self.assertFalse(ok)
        self.assertIn("not a worktree this runner created", why)
        self.assertFalse(any(c[:3] == ["git", "worktree", "prune"] for c in calls))
        self.assertFalse(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_missing_worktree_added(self):
        (ok, _), calls, _ = self._run([self.SHA], wt_exists=False)
        self.assertTrue(ok)
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_process_does_not_run_gates_on_bad_checkout(self):
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("run_checks(pr, out) if ok_wt else", src)
        self.assertIn("run_review_coverage(pr, out) if ok_wt else", src)

class ReviewCoverageShallowTest(unittest.TestCase):
    """DIG-4389: a shallow clone must never yield a false-green promotion gate.

    The local range on a shallow clone stopped at the graft boundary and saw one
    commit instead of ~1000. The daemon now takes the commit set from GitHub's
    compare API on a shallow clone, and fails closed when compare is missing or
    truncated (GitHub caps it at 250 commits)."""

    SHA = "a" * 40

    def _run(self, *, shallow, compare, stdout=None, rc=0):
        import io
        calls = []
        seen = {}
        saved = (_mod.sh, _mod._gh_json, _mod.subprocess.run, _mod.WT, _mod.ENV)
        tmp = tempfile.mkdtemp()
        try:
            _mod.WT = tmp
            _mod.ENV = {}

            def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
                calls.append(cmd)
                if cmd[:3] == ["git", "rev-parse", "--is-shallow-repository"]:
                    return (0, "true\n") if shallow else (0, "false\n")
                return 0, ""

            _mod.sh = fake_sh
            _mod._gh_json = lambda argv: compare

            class FakeProc:
                def __init__(self):
                    self.returncode = rc
                    self.stdout = stdout if stdout is not None else json.dumps(
                        {"commits": [{"sha": "x"}], "unreviewed": []})
                    self.stderr = ""

            def fake_run(cmd, **kw):
                seen["cmd"] = cmd
                if "--commits-json" in cmd:
                    path = cmd[cmd.index("--commits-json") + 1]
                    try:
                        with open(path, encoding="utf-8") as handle:
                            seen["payload"] = json.load(handle)
                    except (OSError, ValueError):
                        seen["payload"] = None
                return FakeProc()

            _mod.subprocess.run = fake_run
            buf = io.StringIO()
            res = _mod.run_review_coverage({"headRefOid": self.SHA}, buf)
        finally:
            (_mod.sh, _mod._gh_json, _mod.subprocess.run,
             _mod.WT, _mod.ENV) = saved
            shutil.rmtree(tmp, ignore_errors=True)
        return res, seen.get("cmd"), seen, buf.getvalue()

    def test_shallow_clone_takes_the_commit_set_from_github_compare(self):
        compare = {"total_commits": 1, "commits": [{"sha": self.SHA}]}
        res, cmd, seen, text = self._run(shallow=True, compare=compare)
        self.assertEqual(res, (True, 1, 0))
        self.assertIn("--commits-json", cmd)
        self.assertNotIn("--base", cmd)
        self.assertIn("--head", cmd)
        self.assertIn(self.SHA, cmd)
        self.assertIn("GitHub compare", text)
        self.assertEqual(seen.get("payload"), compare, "the compare payload must be passed through")
        path = cmd[cmd.index("--commits-json") + 1]
        self.assertFalse(os.path.exists(path), "the temp compare file must be cleaned up")

    def test_shallow_clone_with_unreadable_compare_fails_closed(self):
        res, cmd, _, text = self._run(shallow=True, compare=None)
        self.assertEqual(res, (False, -1, -1))
        self.assertIsNone(cmd, "the gate must not run on an unknown range")
        self.assertIn("FAIL", text)

    def test_shallow_clone_with_truncated_compare_fails_closed(self):
        compare = {"total_commits": 1086, "commits": [{"sha": "b" * 40}]}
        res, cmd, _, text = self._run(shallow=True, compare=compare)
        self.assertEqual(res, (False, -1, -1))
        self.assertIsNone(cmd)
        self.assertIn("truncated", text)

    def test_full_clone_keeps_the_local_range(self):
        res, cmd, _, _ = self._run(shallow=False, compare=None)
        self.assertEqual(res, (True, 1, 0))
        self.assertIn("--base", cmd)
        self.assertIn("origin/main", cmd)
        self.assertIn(self.SHA, cmd)
        self.assertNotIn("--commits-json", cmd)


if __name__ == "__main__":
    unittest.main()


class ProxyEnvTest(unittest.TestCase):
    """DIG-4453: the gate must never inherit the VPN proxy.

    Measured 2026-10-19: `npm exec -- wrangler deploy --dry-run` never returns
    with HTTP_PROXY/HTTPS_PROXY pointing at 127.0.0.1:18450 (the wrangler CLI
    sits idle holding 7 ESTABLISHED sockets to the proxy); with the proxy dropped
    the same command exits 0 in 2.5 s.
    """

    def test_build_env_drops_every_proxy_key(self):
        base = {"HTTP_PROXY": "http://127.0.0.1:18450", "http_proxy": "http://127.0.0.1:18450",
                "HTTPS_PROXY": "http://127.0.0.1:18450", "https_proxy": "http://127.0.0.1:18450",
                "ALL_PROXY": "socks5://127.0.0.1:1", "all_proxy": "socks5://127.0.0.1:1",
                "PATH": "/usr/bin", "KEEP": "1"}
        env = _mod.build_env(base)
        for k in _mod.PROXY_KEYS:
            self.assertNotIn(k, env)
        self.assertEqual(env["KEEP"], "1")
        self.assertTrue(env["PATH"].startswith("/opt/homebrew/bin"))

    def test_build_env_keeps_the_widened_path(self):
        env = _mod.build_env({"PATH": "/usr/bin"})
        self.assertIn("/usr/local/bin", env["PATH"])
        self.assertTrue(env["PATH"].endswith("/usr/bin"))

    def test_the_gate_env_carries_no_proxy(self):
        self.assertEqual(len(_mod.PROXY_KEYS), 6)
        for k in _mod.PROXY_KEYS:
            self.assertNotIn(k, _mod.ENV)


class ShTimeoutTest(unittest.TestCase):
    """DIG-4453: a step timeout must take the whole process tree down.

    `subprocess.run(timeout=)` killed only the direct child, so the wrangler and
    esbuild grandchildren survived, were re-parented to pid 1 and leaked.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._state = _mod.CHILD_STATE
        _mod.CHILD_STATE = os.path.join(self.tmp, "child.json")

    def tearDown(self):
        _mod.CHILD_STATE = self._state
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_timeout_kills_the_grandchild_too(self):
        marker = os.path.join(self.tmp, "pid")
        rc, out = _mod.sh(["/bin/sh", "-c", f"sleep 45 & echo $! > {marker}; sleep 45"], timeout=3)
        self.assertEqual(rc, 124)
        self.assertTrue(os.path.exists(marker))
        with open(marker) as f:
            grandchild = int(f.read().strip())
        time.sleep(1.0)
        try:
            os.kill(grandchild, 0)
            alive = True
        except (ProcessLookupError, PermissionError):
            alive = False
        self.assertFalse(alive, "the grandchild outlived the step timeout")

    def test_a_normal_command_still_works(self):
        rc, out = _mod.sh(["/bin/echo", "hello-local-ci"])
        self.assertEqual(rc, 0)
        self.assertIn("hello-local-ci", out)

    def test_the_child_state_is_cleared_after_a_step(self):
        _mod.sh(["/bin/echo", "x"], timeout=30)
        self.assertIsNone(_mod.read_child_state())


class WatchdogTest(unittest.TestCase):
    """DIG-4453: the watchdog reaps a step that outlived its own budget.

    The lock self-heals only after 7200 s, which is far too long for develop's
    only required context. The age that decides is the OS age of the pid: a
    stale state file must never be able to kill a healthy tick.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._state = _mod.CHILD_STATE
        self._lock = _mod.LOCK
        self._grace = _mod.WATCHDOG_GRACE_SECS
        _mod.CHILD_STATE = os.path.join(self.tmp, "child.json")
        _mod.LOCK = os.path.join(self.tmp, "lock")
        _mod.WATCHDOG_GRACE_SECS = 0
        self.marker = os.path.join(self.tmp, "child.pid")
        self.holder = subprocess.Popen(["/bin/sh", "-c", f"sleep 45 & echo $! > {self.marker}; wait"])
        for _ in range(50):
            if os.path.exists(self.marker) and os.path.getsize(self.marker):
                break
            time.sleep(0.1)
        with open(self.marker) as f:
            self.child = int(f.read().strip())
        os.makedirs(_mod.LOCK, exist_ok=True)
        with open(os.path.join(_mod.LOCK, "pid"), "w") as f:
            f.write(str(self.holder.pid))

    def tearDown(self):
        _mod.WATCHDOG_GRACE_SECS = self._grace
        for pid in (self.holder.pid, self.child):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        _mod.CHILD_STATE = self._state
        _mod.LOCK = self._lock
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def _wait_child_age(self, min_secs):
        """The OS age rounds to whole seconds: wait for a child that is old enough."""
        for _ in range(60):
            if (_mod._ps_etime(self.child) or 0) >= min_secs:
                return True
            time.sleep(0.1)
        return False

    def _state_file(self, age=None, budget=300, pid=None):
        """age=None means 'the age the OS reports for this pid'."""
        if age is None:
            age = _mod._ps_etime(pid or self.child) or 0
        with open(_mod.CHILD_STATE, "w") as f:
            json.dump({"pid": pid or self.child, "name": "worker-build:digithings-cron",
                       "started": time.time() - age, "budget": budget}, f)

    def test_watchdog_kills_a_child_that_outlived_its_budget(self):
        self.assertTrue(self._wait_child_age(1))
        self._state_file(budget=0)
        self.assertTrue(_mod.watchdog())
        self.assertIsNone(_mod.read_child_state(), "the child state must be cleared")
        time.sleep(0.5)
        self.assertFalse(self._alive(self.child), "the overrunning child must be killed")

    def test_watchdog_leaves_a_child_within_budget_alone(self):
        self._state_file(budget=300)
        self.assertFalse(_mod.watchdog())
        self.assertTrue(self._alive(self.child), "a healthy child must not be killed")
        self.assertIsNotNone(_mod.read_child_state(), "state of a live step must survive")

    def test_watchdog_ignores_a_reused_pid(self):
        """The production false positive: a stale state file names a pid the
        kernel handed to another process. The recorded age (1000 s) and the OS
        age of the live pid (~1 s) disagree, so nothing may be killed."""
        self._state_file(age=1000, budget=300)
        self.assertFalse(_mod.watchdog())
        self.assertTrue(self._alive(self.child), "a reused pid must not be killed")
        self.assertIsNone(_mod.read_child_state(), "stale state must be cleared")

    def test_watchdog_ignores_a_pid_that_is_not_running(self):
        self._state_file(age=1000, budget=300, pid=999999)
        self.assertFalse(_mod.watchdog())
        self.assertIsNone(_mod.read_child_state())
        self.assertTrue(self._alive(self.child))


class NoRealNetwork:
    """No test in this file may reach the network or the real token file.

    The app row is posted with a real `gh` call whenever a token exists, and
    the token file is exactly what the App migration will create on this host.
    A test that reaches either one writes a row under another identity on the
    real repository (DIG-4809).
    """

    def _isolate(self):
        self._saved_sh = _mod.sh
        self._saved_log = _mod.log
        self._saved_token_file = _mod.APP_TOKEN_FILE
        self._saved_env = dict(os.environ)
        self._saved_gate_env = _mod.ENV
        self._tmp = tempfile.mkdtemp()
        self.sh_calls = []
        self.log_lines = []
        self.sh_result = (0, "")
        self.sh_stderr = ""
        _mod.sh = self._fake_sh
        _mod.log = self.log_lines.append
        _mod.APP_TOKEN_FILE = os.path.join(self._tmp, "app-token")
        # The gate's own environment is the copy it takes at import time. A test
        # that changes it has to give it back, or the next test inherits it and
        # the order of the suite decides the result (DIG-4809).
        _mod.ENV = dict(_mod.ENV)
        for key in ("LOCAL_CI_APP_TOKEN_FILE", "CI_APP_TOKEN"):
            os.environ.pop(key, None)

    def _unisolate(self):
        _mod.sh = self._saved_sh
        _mod.log = self._saved_log
        _mod.APP_TOKEN_FILE = self._saved_token_file
        _mod.ENV = self._saved_gate_env
        os.environ.clear()
        os.environ.update(self._saved_env)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _fake_sh(self, cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
        """Stand in for the command runner: the `gh` calls are recorded, never
        executed."""
        self.sh_calls.append({"cmd": list(cmd), "env": env, "name": name})
        rc, stdout = self.sh_result
        if out is not None:
            out.write(f"$ {' '.join(cmd)}\n{stdout}{self.sh_stderr}\n[rc={rc}]\n")
        return rc, stdout


class ExplicitPrStateTest(NoRealNetwork, unittest.TestCase):
    """DIG-4812: an explicit --pr N run must evaluate a closed or a merged PR.

    `gh pr list --state open` cannot see a closed or a merged pull request, so
    the explicit path iterated an empty list: the run evaluated nothing,
    reported nothing, and looked like it had done the work. That is how PR
    #6087 lost its verdict unnoticed until the deploy lane broke again.
    """

    def setUp(self):
        self._isolate()
        self._gh = _mod.gh
        self._list_prs = _mod.list_prs
        self._acquire_lock = _mod.acquire_lock
        self._watchdog = _mod.watchdog
        self._process = _mod.process
        self._process_applied = _mod.process_applied
        self._process_review = _mod.process_review
        self._log = _mod.log
        self._argv = list(sys.argv)
        self._env = dict(os.environ)
        # The published runner refuses to start on a checkout that is not a git
        # repository. Point it at this repository so the guard is not the test.
        os.environ["LOCAL_CI_MAIN"] = os.path.abspath(os.path.join(_HERE, "..", ".."))
        os.environ.pop("LOCAL_CI_WT", None)
        self.statuses = {}   # sha -> list of status rows
        self.posts = []      # (sha, state, context, description)
        self.calls = []      # the run legs that were called
        self.logs = []       # the lines the run logged
        self.out = ""        # what the run printed
        self.pr = None       # what `gh pr view` resolves to

    def tearDown(self):
        _mod.gh = self._gh
        _mod.list_prs = self._list_prs
        _mod.acquire_lock = self._acquire_lock
        _mod.watchdog = self._watchdog
        _mod.process = self._process
        _mod.process_applied = self._process_applied
        _mod.process_review = self._process_review
        _mod.log = self._log
        sys.argv = self._argv
        os.environ.clear()
        os.environ.update(self._env)
        self._unisolate()

    # --- fakes -------------------------------------------------------------

    def _fake_gh(self, *a):
        """Stand in for the gh wrapper: resolve a PR in any state, serve status
        rows, record status posts."""
        argv = list(a)
        if argv[0:2] == ["pr", "view"]:
            if self.pr is None:
                return None       # gh exits non-zero on a number that does not exist
            return json.dumps(self.pr)
        if "-X" in argv and "POST" in argv:
            url = [x for x in argv if x.startswith("repos/") and "/statuses/" in x][0]
            sha = url.split("/statuses/")[1]
            fields = {}
            for x in argv:
                if "=" not in x:
                    continue
                k, v = x.split("=", 1)
                if k in ("state", "context", "description"):
                    fields[k] = v
            self.posts.append((sha, fields.get("state"), fields.get("context"),
                               fields.get("description")))
            return "{}"
        url = [x for x in argv if x.startswith("repos/") and "/statuses" in x]
        if url:
            sha = url[0].split("/commits/")[1].split("/statuses")[0]
            return json.dumps(self.statuses.get(sha, []))
        return "[]"

    def _row(self, state, desc, age_secs=0, context=None):
        ts = datetime.now(timezone.utc) - timedelta(seconds=age_secs)
        return {"context": context or _mod.CTX, "state": state, "description": desc,
                "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def _pr(self, number=6087, state="CLOSED", base="develop", cross=False,
            sha="cb8010dfd6dd5638dc12d8ee3b187a1cbba79e76"):
        return {"number": number, "state": state, "headRefOid": sha,
                "headRefName": "fix/deploy-lane-on-develop", "baseRefName": base,
                "title": "fix(deploy): make the merge-to-main deploy lane work from develop",
                "isCrossRepository": cross, "updatedAt": "2026-10-20T23:35:10Z",
                "mergedAt": "2026-10-20T23:35:10Z" if state == "MERGED" else None,
                "closedAt": "2026-10-20T23:35:10Z"}

    def _run(self, number):
        """Run main() for one named PR, with the open PR lists empty.

        The empty lists are the bug: the explicit path used to find the PR
        there and there only.
        """
        _mod.gh = self._fake_gh
        _mod.list_prs = lambda base: []
        _mod.acquire_lock = lambda: True
        _mod.watchdog = lambda: None
        # The launch guard refuses a run that no trusted launcher started
        # (DIG-4796). These tests drive the flow behind that check, so the
        # guard is stubbed; test_launch_guard.py is where it is tested.
        _mod.launch_guard = _AllowedGuard
        _mod.process = lambda pr, dry: (self.calls.append("process"), "success")[1]
        _mod.process_applied = lambda pr, dry: (self.calls.append("process_applied"), "success")[1]
        _mod.process_review = lambda pr, dry: (self.calls.append("process_review"), "success")[1]
        _mod.log = lambda m: self.logs.append(m)
        sys.argv = ["local_ci.py", "--pr", str(number)]
        stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            _mod.main()
        finally:
            self.out = sys.stdout.getvalue()
            sys.stdout = stdout

    # --- the bug: a closed or a merged PR must still get a verdict ----------

    def test_a_closed_pr_ends_with_a_verdict_that_names_it(self):
        pr = self._pr(state="CLOSED")
        self.pr = pr
        self._run(pr["number"])
        self.assertEqual(len(self.posts), 1,
                         "a closed PR must get a verdict, never a silent skip")
        sha, state, context, desc = self.posts[0]
        self.assertEqual(sha, pr["headRefOid"])
        self.assertEqual(context, _mod.CTX)
        self.assertEqual(state, "failure")
        self.assertIn(str(pr["number"]), desc)
        self.assertIn("closed", desc)
        self.assertTrue(desc.startswith(_mod.SKIP_PREFIX),
                        "a skip is re-checkable when the PR comes back")

    def test_a_merged_pr_ends_with_a_verdict_that_names_it(self):
        pr = self._pr(state="MERGED")
        self.pr = pr
        self._run(pr["number"])
        self.assertEqual(len(self.posts), 1,
                         "a merged PR must get a verdict, never a silent skip")
        _sha, _state, _context, desc = self.posts[0]
        self.assertIn(str(pr["number"]), desc)
        self.assertIn("merged", desc)

    def test_the_run_logs_the_pr_and_its_state(self):
        pr = self._pr(state="CLOSED")
        self.pr = pr
        self._run(pr["number"])
        self.assertTrue(any(str(pr["number"]) in m and "CLOSED" in m for m in self.logs),
                        "the log must name the PR and its state")
        self.assertIn(str(pr["number"]), self.out,
                      "a manual run must say what it did")

    def test_an_earned_verdict_is_not_overwritten(self):
        """#6087's head already carries the green row it earned while it was
        open. A closed notice must not repaint that commit red."""
        pr = self._pr(state="MERGED")
        self.pr = pr
        self.statuses[pr["headRefOid"]] = [
            self._row("success", "static gates passed (pytest/audits not gated, see DIG-3605) (1m)")]
        self._run(pr["number"])
        self.assertEqual(self.posts, [], "an earned verdict must never be overwritten")
        self.assertTrue(any(str(pr["number"]) in m and "MERGED" in m for m in self.logs),
                        "the run must still say that the PR is merged")

    def test_a_pr_number_that_does_not_exist_is_reported(self):
        self.pr = None
        self._run(999999)
        self.assertEqual(self.posts, [], "no PR, no head, nothing to post")
        self.assertTrue(any("999999" in m and "not found" in m for m in self.logs))

    # --- the verdict must be terminal, and only an earned one is kept -------

    def test_a_pending_row_is_not_an_earned_verdict(self):
        """A run that died mid-flight leaves a `pending` row behind. That is not
        a verdict, and the head must not stay pending for ever."""
        pr = self._pr(state="CLOSED")
        self.pr = pr
        self.statuses[pr["headRefOid"]] = [
            self._row("pending", "local-ci running on Chris's Mac")]
        self._run(pr["number"])
        self.assertEqual(len(self.posts), 1,
                         "a pending row is not a verdict: the head needs a terminal one")
        _sha, state, context, desc = self.posts[0]
        self.assertEqual(state, "failure")
        self.assertEqual(context, _mod.CTX)
        self.assertIn(str(pr["number"]), desc)

    def test_a_red_verdict_is_kept(self):
        """A head that was gated and failed keeps that verdict: the closed
        notice must not repaint it green or say anything else about it."""
        pr = self._pr(state="MERGED")
        self.pr = pr
        self.statuses[pr["headRefOid"]] = [
            self._row("failure", "local-ci failed: gitleaks (2m)")]
        self._run(pr["number"])
        self.assertEqual(self.posts, [], "an earned verdict must never be overwritten")
        self.assertTrue(any("kept: failure" in m for m in self.logs),
                        "the run must say which verdict it kept")

    def test_a_closed_fork_pr_posts_nothing(self):
        """A fork head is not a commit of this repository: no status can be
        posted for it, so the run must not claim it posted one."""
        pr = self._pr(state="CLOSED", cross=True)
        self.pr = pr
        self._run(pr["number"])
        self.assertEqual(self.posts, [], "a fork head has no status in this repository")
        self.assertTrue(any(str(pr["number"]) in m for m in self.logs),
                        "the run must still name the PR")

    def test_an_open_fork_pr_posts_nothing(self):
        pr = self._pr(state="OPEN", cross=True)
        self.pr = pr
        self._run(pr["number"])
        self.assertEqual(self.posts, [], "fork code never runs on this Mac")
        self.assertNotIn("process", self.calls)

    # --- the behaviour that must not change --------------------------------

    def test_an_open_pr_still_runs_the_gate(self):
        pr = self._pr(state="OPEN")
        self.pr = pr
        self._run(pr["number"])
        self.assertIn("process", self.calls)
        self.assertIn("process_applied", self.calls)
        self.assertEqual(self.posts, [], "the gate posts its own verdict")

    def test_a_promotion_pr_into_main_still_gets_the_review_coverage(self):
        pr = self._pr(state="OPEN", base="main", sha="b84c114e0000000000000000000000000000000")
        pr["title"] = "chore: promote develop to main"
        self.pr = pr
        self._run(pr["number"])
        self.assertIn("process_review", self.calls)
        self.assertNotIn("process", self.calls)


class StatusTargetUrlTest(NoRealNetwork, unittest.TestCase):
    """DIG-4794: the `local-ci` status must name the build that made it green.

    A commit status is worth what its writer is worth - GitHub's own words: any
    person or integration with write permissions can set the state of any status
    check - and both repositories name `local-ci` as their required check. The
    merge queue reads the build back from Woodpecker before it trusts the green,
    so the status has to say which build it is talking about.
    """

    def setUp(self):
        self._gh = _mod.gh
        self.calls = []
        self._isolate()
        os.environ.pop("LOCAL_CI_TARGET_URL", None)
        os.environ.pop("CI_PIPELINE_URL", None)

    def tearDown(self):
        _mod.gh = self._gh
        self._unisolate()

    def _post(self):
        # The stub answers like a successful `gh api`: `status()` reads the
        # answer, and an answer of None is a refused row, so a stub that
        # returns None would leave the success path untested (DIG-4809).
        def fake_gh(*a):
            self.calls.append(list(a))
            return "{}"
        _mod.gh = fake_gh
        _mod.status("abc123", "success", "all gates passed")

    def _target_arg(self):
        for arg in self.calls[0]:
            if arg.startswith("target_url="):
                return arg.split("=", 1)[1]
        return None

    def test_the_explicit_name_is_posted(self):
        os.environ["LOCAL_CI_TARGET_URL"] = "http://localhost:8000/repos/6/pipeline/259"
        self._post()
        self.assertEqual(self._target_arg(), "http://localhost:8000/repos/6/pipeline/259")

    def test_the_pipeline_url_is_used_when_no_name_is_given(self):
        # `CI_PIPELINE_URL` is what Woodpecker injects into every step, so the
        # worker inside the pipeline needs no configuration.
        os.environ["CI_PIPELINE_URL"] = "http://localhost:8000/repos/6/pipeline/260"
        self._post()
        self.assertEqual(self._target_arg(), "http://localhost:8000/repos/6/pipeline/260")

    def test_the_explicit_name_wins_over_the_pipeline_url(self):
        os.environ["LOCAL_CI_TARGET_URL"] = "http://localhost:8000/repos/6/pipeline/259"
        os.environ["CI_PIPELINE_URL"] = "http://localhost:8000/repos/6/pipeline/260"
        self._post()
        self.assertEqual(self._target_arg(), "http://localhost:8000/repos/6/pipeline/259")

    def test_a_host_run_names_no_build(self):
        # A run on the host has no build behind it, and says so: the queue then
        # refuses the status and names the missing build as the reason.
        self._post()
        self.assertIsNone(self._target_arg())
        self.assertIn("context=local-ci", self.calls[0])


class AppStatusRowTest(NoRealNetwork, unittest.TestCase):
    """DIG-4809: the same verdict goes out twice, once per identity.

    The `local-ci` row is posted with the repository token. The `local-ci/app`
    row is posted with the app's own installation token, so its creator is
    digithings-ci[bot]. The token belongs in the child's environment and not in
    its arguments, and with no token there is no app row at all: a row under
    another identity would be worse than no row.
    """

    TOKEN = "ghs_123456_" + "z" * 30
    OTHER_TOKEN = "ghs_999999_" + "q" * 30
    NAMED_TOKEN = "ghs_777777_" + "r" * 30

    def setUp(self):
        self.calls = []
        self._isolate()

    def tearDown(self):
        self._unisolate()

    def _write_token(self, value, path=None):
        with open(path or _mod.APP_TOKEN_FILE, "w") as f:
            f.write(value + "\n")

    def _fields(self, state="success", desc="all gates passed"):
        return _mod.status_fields(state, desc)

    def _arg(self, prefix):
        return [a.split("=", 1)[1] for call in self.sh_calls
                for a in call["cmd"] if a.startswith(prefix + "=")]

    def _app_call(self):
        """The app row's call: the one whose child carries the token."""
        for call in self.sh_calls:
            if call["env"] is not None:
                return call
        return None

    def test_without_a_token_no_app_row_is_posted(self):
        os.environ["CI_PIPELINE_URL"] = "http://localhost:8000/repos/6/pipeline/400"
        self.assertFalse(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])
        self.assertIn("app status: skipped, no app token", self.log_lines)

    def test_an_empty_token_file_posts_no_row(self):
        self._write_token("")
        self.assertFalse(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])

    def test_a_whitespace_only_token_file_posts_no_row(self):
        self._write_token("   \n")
        self.assertFalse(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])

    def test_a_token_file_that_cannot_be_read_posts_no_row(self):
        # A directory where the token file should be: the file cannot be read,
        # so there is no token, so there is no row.
        os.makedirs(_mod.APP_TOKEN_FILE, exist_ok=True)
        self.assertFalse(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])

    def test_only_the_first_line_of_the_token_file_is_the_token(self):
        self._write_token(self.TOKEN + "\nand a second line\n")
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self._app_call()["env"]["GH_TOKEN"], self.TOKEN)

    def test_the_app_row_is_posted_with_the_app_token(self):
        self._write_token(self.TOKEN)
        os.environ["CI_PIPELINE_URL"] = "http://localhost:8000/repos/6/pipeline/400"
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(len(self.sh_calls), 1)
        call = self.sh_calls[0]
        self.assertIn("context=local-ci/app", call["cmd"])
        self.assertIn("target_url=http://localhost:8000/repos/6/pipeline/400",
                      call["cmd"])
        self.assertEqual(call["env"]["GH_TOKEN"], self.TOKEN)
        self.assertEqual(call["env"]["GITHUB_TOKEN"], self.TOKEN)

    def test_the_token_is_never_in_the_arguments(self):
        self._write_token(self.TOKEN)
        _mod.app_status("abc123", self._fields())
        self.assertNotIn(self.TOKEN, " ".join(self.sh_calls[0]["cmd"]))

    def test_the_environment_token_is_the_fallback(self):
        os.environ["CI_APP_TOKEN"] = self.TOKEN
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls[0]["env"]["GH_TOKEN"], self.TOKEN)

    def test_the_token_file_wins_over_the_environment_token(self):
        self._write_token(self.OTHER_TOKEN)
        os.environ["CI_APP_TOKEN"] = self.TOKEN
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls[0]["env"]["GH_TOKEN"], self.OTHER_TOKEN)

    def test_the_named_token_file_wins_over_the_default_file(self):
        self._write_token(self.TOKEN)
        named = os.path.join(self._tmp, "named-token")
        self._write_token(self.NAMED_TOKEN, path=named)
        os.environ["LOCAL_CI_APP_TOKEN_FILE"] = named
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls[0]["env"]["GH_TOKEN"], self.NAMED_TOKEN)

    def test_the_named_token_file_wins_over_the_environment_token(self):
        named = os.path.join(self._tmp, "named-token")
        self._write_token(self.NAMED_TOKEN, path=named)
        os.environ["LOCAL_CI_APP_TOKEN_FILE"] = named
        os.environ["CI_APP_TOKEN"] = self.TOKEN
        self.assertTrue(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls[0]["env"]["GH_TOKEN"], self.NAMED_TOKEN)

    def test_the_repo_row_carries_no_app_token(self):
        self._write_token(self.TOKEN)
        before = dict(_mod.ENV)
        _mod.status("abc123", "success", "all gates passed")
        # The repo row goes out with the gate's own environment, and the gate's
        # environment is not changed by the app row.
        self.assertEqual(self.sh_calls[0]["env"], None)
        self.assertEqual(dict(_mod.ENV), before)

    def test_both_rows_carry_the_same_verdict(self):
        self._write_token(self.TOKEN)
        os.environ["CI_PIPELINE_URL"] = "http://localhost:8000/repos/6/pipeline/400"
        _mod.status("abc123", "success", "all gates passed")
        self.assertEqual(self._arg("context"), ["local-ci", "local-ci/app"])
        self.assertEqual(self._arg("state"), ["success", "success"])
        self.assertEqual(self._arg("description"), ["all gates passed", "all gates passed"])
        targets = self._arg("target_url")
        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0], targets[1])

    def test_a_failing_verdict_is_posted_under_both_identities(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "failure", "one gate failed")
        self.assertEqual(self._arg("context"), ["local-ci", "local-ci/app"])
        self.assertEqual(self._arg("state"), ["failure", "failure"])

    def test_the_description_is_truncated_for_both_rows(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "x" * 200)
        self.assertEqual(self._arg("description"), ["x" * 139, "x" * 139])

    def test_a_failed_post_is_not_a_posted_row(self):
        self._write_token(self.TOKEN)
        _mod.sh = lambda *a, **kw: (1, "")
        self.assertFalse(_mod.app_status("abc123", self._fields()))
        self.assertIn("app status: failed (rc=1)", self.log_lines)


class AppRowFailsClosedTest(NoRealNetwork, unittest.TestCase):
    """DIG-4809: the app row must not cost the repo row, and must not lie.

    The app row is the one that will be compared with the repo row for 48
    hours. A broken token file, a token that is not an app installation token,
    a repo row that was refused - in every one of those cases the app row is
    skipped, and the `local-ci` row still goes out. The tick must not die on
    the way to a verdict (DIG-4809).
    """

    TOKEN = "ghs_123456_" + "z" * 30
    NOT_A_TOKEN = "ghp_" + "y" * 36

    def setUp(self):
        self._isolate()

    def tearDown(self):
        self._unisolate()

    def _write_token(self, value, path=None):
        with open(path or _mod.APP_TOKEN_FILE, "w") as f:
            f.write(value + "\n")

    def _arg(self, prefix):
        return [a.split("=", 1)[1] for call in self.sh_calls
                for a in call["cmd"] if a.startswith(prefix + "=")]

    def _app_call(self):
        for call in self.sh_calls:
            if call["env"] is not None:
                return call
        return None

    # D1: a token file that is not text must not stop the tick.
    def test_a_token_file_that_is_not_text_posts_no_row_and_keeps_the_repo_row(self):
        with open(_mod.APP_TOKEN_FILE, "wb") as f:
            f.write(b"\xff\xfe\x00binary")
        _mod.status("abc123", "success", "all gates passed")
        self.assertEqual(self._arg("context"), ["local-ci"])
        self.assertIn("app status: skipped", " ".join(self.log_lines))

    # D2: the token must not ride along into every child the gate starts.
    def test_the_environment_token_is_not_in_the_gate_environment(self):
        os.environ["CI_APP_TOKEN"] = self.TOKEN
        env = _mod.build_env()
        self.assertNotIn("CI_APP_TOKEN", env)
        self.assertNotIn("CI_APP_TOKEN", _mod.ENV)

    # D3: a named file that does not exist must not end the search.
    def test_a_named_token_file_that_is_missing_falls_through_to_the_default(self):
        self._write_token(self.TOKEN)
        os.environ["LOCAL_CI_APP_TOKEN_FILE"] = os.path.join(self._tmp, "not-there")
        self.assertTrue(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        self.assertEqual(self._app_call()["env"]["GH_TOKEN"], self.TOKEN)

    # D4: a failed row has to be diagnosable, and the token must not be in it.
    def test_a_failed_row_names_the_reason_and_never_the_token(self):
        self._write_token(self.TOKEN)
        self.sh_result = (1, "")
        self.sh_stderr = "HTTP 403: Resource not accessible by integration\n"
        self.assertFalse(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        line = [ln for ln in self.log_lines if ln.startswith("app status: failed")][0]
        self.assertIn("403", line)
        self.assertNotIn(self.TOKEN, line)
        self.assertNotIn(self.TOKEN, " ".join(self.log_lines))

    # D5: a refused repo row leaves no app row behind.
    def test_a_refused_repo_row_posts_no_app_row(self):
        self._write_token(self.TOKEN)
        self.sh_result = (1, "")
        self.assertFalse(_mod.status("abc123", "success", "all gates passed"))
        self.assertEqual(self._arg("context"), ["local-ci"])
        self.assertIsNone(self._app_call())
        self.assertIn("local-ci/app not posted", " ".join(self.log_lines))

    # D6: a head that is not a commit of this repository gets the repo row only.
    def test_the_app_row_can_be_skipped_for_a_head_this_repository_does_not_have(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "failure", "fork code never runs here", app=False)
        self.assertEqual(self._arg("context"), ["local-ci"])

    # D8: a token that is not an app installation token is refused.
    def test_a_token_that_is_not_an_installation_token_posts_no_row(self):
        self._write_token(self.NOT_A_TOKEN)
        self.assertFalse(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        self.assertEqual(self.sh_calls, [])
        self.assertIn("not an app installation token", " ".join(self.log_lines))

    # The token belongs in the child's environment and nowhere else.
    def test_the_token_is_never_in_the_command_name(self):
        self._write_token(self.TOKEN)
        _mod.app_status("abc123", _mod.status_fields("success", "ok"))
        for call in self.sh_calls:
            self.assertNotIn(self.TOKEN, call["name"] or "")
            self.assertNotIn(self.TOKEN, " ".join(call["cmd"]))

    # Both rows name the same commit of the same repository.
    def test_both_rows_name_the_same_commit_of_the_same_repository(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "all gates passed")
        paths = [a for call in self.sh_calls for a in call["cmd"]
                 if a.startswith("repos/") and "/statuses/" in a]
        self.assertEqual(len(paths), 2)
        self.assertEqual(paths[0], paths[1])
        self.assertTrue(paths[0].endswith("/statuses/abc123"))

    # The token GitHub issues is the opaque form; the plan writes it down as
    # ghs_<appid>_<jwt>. Both are app tokens, and both must post the row.
    def test_the_plain_installation_token_posts_the_row(self):
        plain = "ghs_" + "w" * 36
        self._write_token(plain)
        self.assertTrue(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        self.assertEqual(self._app_call()["env"]["GH_TOKEN"], plain)

    def test_the_app_id_token_posts_the_row(self):
        self._write_token(self.TOKEN)
        self.assertTrue(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        self.assertEqual(self._app_call()["env"]["GH_TOKEN"], self.TOKEN)

    # A file holding the wrong secret must not hide a good one behind it.
    def test_a_wrong_token_in_the_named_file_does_not_hide_the_good_one(self):
        named = os.path.join(self._tmp, "named-token")
        self._write_token(self.NOT_A_TOKEN, path=named)
        self._write_token(self.TOKEN)
        os.environ["LOCAL_CI_APP_TOKEN_FILE"] = named
        self.assertTrue(_mod.app_status("abc123", _mod.status_fields("success", "ok")))
        self.assertEqual(self._app_call()["env"]["GH_TOKEN"], self.TOKEN)

    # A FIFO at the token path would block the tick for ever.
    def test_a_fifo_at_the_token_path_does_not_block_the_tick(self):
        fifo = os.path.join(self._tmp, "app-token-fifo")
        os.mkfifo(fifo)
        os.environ["LOCAL_CI_APP_TOKEN_FILE"] = fifo
        result = {}

        def read_it():
            result["token"] = _mod._read_token_file(fifo)

        reader = threading.Thread(target=read_it, daemon=True)
        reader.start()
        reader.join(2)
        self.assertFalse(reader.is_alive(), "the read must not block on a FIFO")
        self.assertEqual(result.get("token", ""), "")

    # A row nobody wanted must not leave a line about a row nobody wanted.
    def test_no_app_row_wanted_means_no_line_about_one(self):
        self.sh_result = (1, "")
        _mod.status("abc123", "failure", "fork code never runs here", app=False)
        self.assertNotIn("local-ci/app not posted", " ".join(self.log_lines))

    # The gate's environment is a copy: a test that changes it gives it back.
    def test_the_isolation_gives_the_gate_environment_its_own_copy(self):
        self.assertIsNot(_mod.ENV, self._saved_gate_env)

    def test_the_isolation_gives_the_gate_environment_back(self):
        saved = self._saved_gate_env
        self._unisolate()
        self.assertIs(_mod.ENV, saved)
        self._isolate()


class ForkRowWiringTest(unittest.TestCase):
    """DIG-4809: a head this repository does not have gets the repo row alone.

    A fork head is not a commit of this repository, so an app row for it is a
    refused post and a log line per open fork per tick. The call sites are
    pinned by reading the source: the suite drives `status()` directly and
    cannot see which caller asked for the app row.
    """

    def _status_calls(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py")) as f:
            tree = ast.parse(f.read())
        return [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "status"]

    def test_every_fork_status_call_posts_the_repo_row_alone(self):
        fork_calls = [c for c in self._status_calls()
                      if any(isinstance(a, ast.Name) and a.id == "FORK_DESC"
                             for a in c.args)]
        self.assertTrue(fork_calls, "the fork call sites must be found")
        for call in fork_calls:
            app = [kw.value for kw in call.keywords if kw.arg == "app"]
            self.assertEqual(len(app), 1, "a fork status call must pass app=False")
            self.assertIsInstance(app[0], ast.Constant)
            self.assertIs(app[0].value, False)

    def test_a_fork_description_written_as_a_literal_is_also_caught(self):
        """A literal in place of the constant would hide the call site.

        The name-based check finds `FORK_DESC`; a site that writes the text
        out instead would not be found, and the app row would be asked for a
        head this repository does not have.
        """
        literal_calls = [c for c in self._status_calls()
                         if any(isinstance(a, ast.Constant) and a.value == _mod.FORK_DESC
                                for a in c.args)]
        for call in literal_calls:
            app = [kw.value for kw in call.keywords if kw.arg == "app"]
            self.assertEqual(len(app), 1,
                             "a fork status call must pass app=False")
            self.assertIsInstance(app[0], ast.Constant)
            self.assertIs(app[0].value, False)


class AppRowLastGapsTest(NoRealNetwork, unittest.TestCase):
    """DIG-4809: the gaps the adversarial pass left in the suite.

    The code is right in every case below; what was missing was a test that
    would notice if it stopped being right. Each test names the behaviour it
    pins.
    """

    TOKEN = "ghs_123456_" + "z" * 30

    def setUp(self):
        self._isolate()

    def tearDown(self):
        self._unisolate()

    def _write_token(self, value, path=None):
        with open(path or _mod.APP_TOKEN_FILE, "w") as f:
            f.write(value + "\n")

    def _app_call(self):
        for call in self.sh_calls:
            if call["env"] is not None:
                return call
        return None

    def _contexts(self):
        return [a.split("=", 1)[1] for call in self.sh_calls
                for a in call["cmd"] if a.startswith("context=")]

    def test_the_token_never_reaches_a_log_line(self):
        """The success path never logged it; only the failure path was pinned."""
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "all gates passed")
        for line in self.log_lines:
            self.assertNotIn(self.TOKEN, line)

    def test_a_failure_reason_that_carries_the_token_is_redacted(self):
        """The redaction is only proven if the reason really carries the token."""
        self._write_token(self.TOKEN)
        self.sh_result = (1, "")
        self.sh_stderr = f"Bad credentials for token {self.TOKEN}\n"
        self.assertFalse(_mod.app_status("abc123", _mod.status_fields("success", "d")))
        logged = " ".join(self.log_lines)
        self.assertIn("<redacted>", logged)
        self.assertNotIn(self.TOKEN, logged)

    def test_the_gate_environment_drops_the_token_at_import_time(self):
        """The gate environment is built at import time.

        It cannot be observed in process, so the protection is pinned by
        reading the source instead of by calling it.
        """
        with open(os.path.join(_SCRIPTS, "local_ci.py")) as f:
            source = f.read()
        self.assertIn('pop("CI_APP_TOKEN"', source)

    def test_the_app_row_carries_the_token_in_the_child_environment(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "all gates passed")
        call = self._app_call()
        self.assertIsNotNone(call, "the app row must have been posted")
        self.assertEqual(call["env"]["GH_TOKEN"], self.TOKEN)
        self.assertEqual(call["env"]["GITHUB_TOKEN"], self.TOKEN)

    def test_the_child_state_record_carries_no_token(self):
        """The child state file records the command that ran."""
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "all gates passed")
        for call in self.sh_calls:
            self.assertNotIn(self.TOKEN, call["name"] or "")
            self.assertNotIn(self.TOKEN, " ".join(call["cmd"]))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root can read a file whatever its mode")
    def test_a_token_file_that_cannot_be_read_posts_no_row(self):
        path = _mod.APP_TOKEN_FILE
        with open(path, "w") as f:
            f.write(self.TOKEN + "\n")
        os.chmod(path, 0o000)
        try:
            _mod.status("abc123", "success", "all gates passed")
        finally:
            os.chmod(path, 0o600)
        self.assertEqual(self._contexts(), ["local-ci"])
