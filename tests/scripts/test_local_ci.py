#!/usr/bin/env python3
"""Unit tests for the local-ci memory gate parsers (DIG-3783). Stdlib only:
`/usr/bin/python3 -m unittest test_local_ci -v`."""
import ast
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

# The CI lane runs `pytest tests/scripts/ ... -m "unit or baseline"`. A file
# without a marker is deselected, so every test in this file would never run
# in the lane (DIG-4809).
try:
    import pytest
except ImportError:  # the file also runs as a plain unittest module
    pytest = None
else:
    pytestmark = pytest.mark.unit

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))

def _git_env(env):
    """A git environment that needs no identity from the machine it runs on."""
    return dict(env, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com",
                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.com")

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


class _Clock:
    """`time` with a `time()` that runs ahead of the wall clock.

    The ageing rules ask how long something has been held. Moving the clock
    answers that without backdating a record, which would also change what
    the record says about the process that wrote it.
    """

    def __init__(self, now):
        self._now = now

    def time(self):
        return self._now

    def __getattr__(self, name):
        return getattr(time, name)


class _NoReplace:
    """`os` without `os.replace`, to show what an atomic write buys."""

    def __getattr__(self, name):
        return getattr(os, name)

    def replace(self, *a, **k):
        raise OSError("the move into place did not happen")


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


class InstallPreflightTest(unittest.TestCase):
    """DIG-5585: a tick never starts on an install that is missing a module.

    The runner's helpers are optional imports bound to None and fail closed,
    so a helper that was never copied in produced a false verdict on every PR
    (eight red `review-applied` rows on 24 Oct) instead of stopping the tick.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._saved_log = _mod.log
        self.log_lines = []
        _mod.log = self.log_lines.append
        self.checkout = os.path.join(self.tmp, "checkout")
        runner_dir = os.path.join(self.checkout, "scripts", "local-ci")
        os.makedirs(runner_dir)
        for name in os.listdir(_SCRIPTS):
            if name.endswith(".py"):
                shutil.copy(os.path.join(_SCRIPTS, name), os.path.join(runner_dir, name))
        shutil.copy(os.path.join(_SCRIPTS, "..", "review_pass_filter.py"),
                    os.path.join(self.checkout, "scripts", "review_pass_filter.py"))
        self.runner = os.path.join(runner_dir, "local_ci.py")

    def tearDown(self):
        _mod.log = self._saved_log
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _refuse(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            with self.assertRaises(SystemExit) as caught:
                _mod._require_install(self.runner)
        return caught.exception.code, err.getvalue()

    def test_a_checkout_missing_a_shared_module_is_refused(self):
        os.remove(os.path.join(self.checkout, "scripts", "review_pass_filter.py"))
        code, err = self._refuse()
        self.assertEqual(code, 78, "an incomplete install is EX_CONFIG, like a refused run")
        self.assertIn("review_pass_filter", err)
        self.assertIn("refusing to tick", err)
        self.assertTrue(
            any("review_pass_filter" in line for line in self.log_lines),
            "the refusal must reach the runner's log, not only stderr")

    def test_a_checkout_missing_a_runner_module_is_refused(self):
        os.remove(os.path.join(self.checkout, "scripts", "local-ci", "review_applied.py"))
        code, err = self._refuse()
        self.assertEqual(code, 78)
        self.assertIn("review_applied", err)

    def test_a_complete_checkout_starts(self):
        _mod._require_install(self.runner)  # no SystemExit

    def test_every_entry_point_that_asks_the_guard_asks_the_install_check(self):
        """The post-merge driver never goes through main(); it still gets checked."""

        class _Broken:
            @staticmethod
            def check(runner_path):
                return [{"module": "review_pass_filter",
                         "importer": "review_applied.py", "why": "not there"}]

            @staticmethod
            def report(problems, runner_path):
                return ["local-ci: missing module review_pass_filter"]

        saved_module = _mod.import_preflight
        saved_checked = _mod._INSTALL_CHECKED
        _mod.import_preflight = _Broken
        _mod._INSTALL_CHECKED = False
        try:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    _mod._guard()
        finally:
            _mod.import_preflight = saved_module
            _mod._INSTALL_CHECKED = saved_checked
        self.assertEqual(caught.exception.code, 78)
        self.assertIn("review_pass_filter", err.getvalue())


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

    def test_build_skips_an_app_the_tree_has_retired(self):
        """A retirement PR deletes the app; the fixed WORKER_APPS still names it.

        #6530 retires apps/digitrace-langfuse (DIG-5136) and could not go green:
        the runner changed into the app directory and wrangler failed on a
        project with no config. An app with no wrangler.toml in the tree is
        retired in that tree and is not built; the rest still are.
        """
        with tempfile.TemporaryDirectory() as wt:
            live = _mod.WORKER_APPS[0]
            retired = _mod.WORKER_APPS[-1]
            for app in (live, _mod.WORKER_APPS[1]):
                os.makedirs(os.path.join(wt, "apps", app))
                open(os.path.join(wt, "apps", app, "wrangler.toml"), "w").close()
            # The retired app's directory can survive a checkout (ignored
            # node_modules), so the filter must key on wrangler.toml, not the dir.
            os.makedirs(os.path.join(wt, "apps", retired))
            calls, rec = self._rec()
            self.assertEqual(_mod.worker_build(wt, rec), [])
            built = [c[0].split(":", 1)[1] for c in calls[1:]]
            self.assertEqual(built, [live, _mod.WORKER_APPS[1]])
            self.assertNotIn(retired, built)

    def test_build_with_no_apps_dir_builds_the_fixed_list(self):
        """A unit fixture or an odd tree says nothing about retirement: build all."""
        with tempfile.TemporaryDirectory() as wt:
            self.assertEqual(_mod.buildable_worker_apps(wt), list(_mod.WORKER_APPS))
            calls, rec = self._rec()
            self.assertEqual(_mod.worker_build(wt, rec), [])
            self.assertEqual(len(calls), 1 + len(_mod.WORKER_APPS))

    def test_a_tree_with_no_buildable_worker_fails_loudly(self):
        """Every app retired is a broken checkout, not a clean tree.

        Skipping each app because its wrangler.toml is absent would turn a
        half-checked-out worktree into a green required check. Only a tree that
        still has at least one buildable Worker is treated as a real tree.
        """
        with tempfile.TemporaryDirectory() as wt:
            for app in _mod.WORKER_APPS:
                os.makedirs(os.path.join(wt, "apps", app))
            self.assertEqual(_mod.buildable_worker_apps(wt), list(_mod.WORKER_APPS))


class BunSuiteGateTest(unittest.TestCase):
    """The bun suites run in local-ci, and the receipt says which ones (DIG-5203).

    Before this gate the required `local-ci` check ran no bun test at all: the
    suites only ever ran in the GitHub lanes retired with Actions, so a
    clients/** PR carried a green receipt that proved nothing (#6271, where
    digichat-tui's 71 tests only ran by hand). The receipt must name the suites
    that ran, and say `bun: none` when none did, so a skipped suite is visible.
    """

    def _suite(self, root, rel, deps=False, lock=True, test_script="bun test"):
        d = os.path.join(root, rel)
        os.makedirs(d, exist_ok=True)
        pkg = {"name": rel.replace("/", "-"), "scripts": {"test": test_script}}
        if deps:
            pkg["devDependencies"] = {"@opentui/react": "0.5.14"}
        with open(os.path.join(d, "package.json"), "w") as f:
            json.dump(pkg, f)
        if lock:
            with open(os.path.join(d, "bun.lock"), "w") as f:
                f.write("# lock\n")
        return d

    def _wt(self, suites):
        root = tempfile.mkdtemp(prefix="wt-bun-")
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "scripts"))
        globs = "".join(f"  - {s}/**\n" for s in suites)
        with open(os.path.join(root, "scripts", "ci_paths.yaml"), "w") as f:
            f.write(f"bun_suites:\n{globs}\nworkers:\n  - apps/x/**\n")
        # `packages/*` are workspaces of the root package.json; the clients are
        # standalone bun packages with their own lockfile (the repo's own split).
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({"workspaces": ["apps/*", "packages/*"]}, f)
        for s in suites:
            workspace = s.startswith("packages/")
            self._suite(root, s, deps=not workspace, lock=not workspace)
        return root

    def _step(self, calls, fails, fail_on=()):
        def step(name, cmd, timeout=1800, cwd=None):
            calls.append((name, cmd, timeout, cwd))
            if name in fail_on:
                fails.append(name)
                return False
            return True
        return step

    def _real_ci_paths(self):
        return open(os.path.join(_SCRIPTS, "..", "ci_paths.yaml")).read()

    def test_real_ci_paths_names_every_suite(self):
        dirs = _mod.bun_suite_dirs(_mod.parse_ci_paths_block(self._real_ci_paths(), "bun_suites"))
        for suite in ("clients/digichat-tui", "clients/digiquant-tui", "clients/digivoice-tui",
                      "clients/digichat-devkit", "packages/surface-config",
                      "packages/hero-banner"):
            self.assertIn(suite, dirs)

    def test_non_suite_entries_fire_the_gate_but_name_no_suite(self):
        pats = ["clients/a/**", ".github/workflows/test-bun-suites.yml", "packages/*/b"]
        self.assertEqual(_mod.bun_suite_dirs(pats), ["clients/a"])

    def test_suite_patterns_fall_back_when_the_block_is_absent(self):
        root = tempfile.mkdtemp(prefix="wt-nocipaths-")
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(_mod.bun_suite_patterns(root),
                         [f"{d}/**" for d in _mod.BUN_SUITE_DIRS])

    def test_gate_hits_a_client_path_only(self):
        root = self._wt(["clients/digichat-tui", "packages/surface-config"])
        pats = _mod.bun_suite_patterns(root)
        self.assertEqual(
            _mod.path_gate_hit(["clients/digichat-tui/src/read.ts"], pats),
            ("clients/digichat-tui/**", "clients/digichat-tui/src/read.ts"))
        self.assertIsNone(_mod.path_gate_hit(["apps/digichat/src/a.ts"], pats))

    def test_gate_fails_closed_when_the_file_list_cannot_be_read(self):
        saved = _mod.gh
        try:
            _mod.gh = lambda *a: None
            self.assertEqual(_mod.bun_gate({"number": 7}, "/nonexistent-wt"), (None, None))
        finally:
            _mod.gh = saved

    def test_standalone_suites_install_and_workspace_packages_do_not(self):
        root = self._wt(["clients/digichat-tui", "packages/hero-banner"])
        calls, fails = [], []
        ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        self.assertEqual(ran, ["digichat-tui", "hero-banner"])
        self.assertEqual(fails, [])
        names = [c[0] for c in calls]
        # `packages/*` is a workspace of the root package.json: `bun install`
        # there walks up and installs the whole monorepo (the retired lane
        # exempted it for that reason), so only the client is installed.
        self.assertEqual(names, ["bun-install:digichat-tui", "bun:digichat-tui",
                                 "bun:hero-banner"])
        test = calls[1]
        self.assertEqual(test[1][1:], ["run", "test"])
        self.assertEqual(test[2], _mod.BUN_TEST_TIMEOUT)
        self.assertEqual(test[3], os.path.join(root, "clients", "digichat-tui"))

    def test_one_red_suite_does_not_hide_the_others(self):
        root = self._wt(["clients/digichat-tui", "clients/digiquant-tui"])
        calls, fails = [], []
        ran = _mod.run_bun_suites(root, self._step(calls, fails, fail_on=("bun:digichat-tui",)),
                                  io.StringIO(), fails)
        self.assertEqual(ran, ["digichat-tui", "digiquant-tui"])
        self.assertEqual(fails, ["bun:digichat-tui"])
        self.assertIn("bun:digiquant-tui", [c[0] for c in calls])

    def test_a_standalone_suite_without_a_lockfile_fails_before_it_runs(self):
        root = self._wt(["clients/digichat-tui"])
        os.remove(os.path.join(root, "clients", "digichat-tui", "bun.lock"))
        calls, fails = [], []
        ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        self.assertEqual(ran, [])
        self.assertEqual(fails, ["bun-install:digichat-tui (no bun.lock)"])
        self.assertEqual(calls, [])

    def test_only_root_workspace_globs_are_exempt_from_install(self):
        globs = ["apps/*", "packages/*"]
        self.assertTrue(_mod.is_root_workspace("packages/hero-banner", globs))
        self.assertTrue(_mod.is_root_workspace("apps/corpus-index", globs))
        self.assertFalse(_mod.is_root_workspace("clients/digichat-tui", globs))
        self.assertFalse(_mod.is_root_workspace("packages", globs))
        self.assertEqual(_mod.root_workspace_globs("/nonexistent-wt"), [])

    def test_a_new_client_with_a_bun_suite_is_gated_without_a_list_edit(self):
        """The list is not the only source: a client that lands with a bun suite
        runs on its first PR, so nobody has to remember to add it (DIG-5203)."""
        root = self._wt(["clients/digichat-tui"])
        self._suite(root, "clients/new-tui", deps=True)
        self.assertIn("clients/new-tui", _mod.bun_suites_to_run(root))
        calls, fails = [], []
        ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        self.assertEqual(ran, ["digichat-tui", "new-tui"])
        self.assertEqual(fails, [])

    def test_a_client_with_a_vitest_suite_is_not_a_bun_suite(self):
        """`apps/*` and any client on vitest belong to the web lane, not here."""
        root = self._wt(["clients/digichat-tui"])
        self._suite(root, "clients/web-tui", deps=True, test_script="vitest run")
        self.assertEqual(_mod.bun_test_packages(root), ["clients/digichat-tui"])
        calls, fails = [], []
        ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        self.assertEqual(ran, ["digichat-tui"])

    def test_clients_glob_fires_the_gate_but_names_no_suite(self):
        root = tempfile.mkdtemp(prefix="wt-bun-clients-")
        self.addCleanup(shutil.rmtree, root, True)
        os.makedirs(os.path.join(root, "scripts"))
        with open(os.path.join(root, "scripts", "ci_paths.yaml"), "w") as f:
            f.write("bun_suites:\n  - clients/**\n  - packages/hero-banner/**\n")
        with open(os.path.join(root, "package.json"), "w") as f:
            json.dump({"workspaces": ["apps/*", "packages/*"]}, f)
        pats = _mod.bun_suite_patterns(root)
        self.assertEqual(_mod.bun_suite_dirs(pats), ["packages/hero-banner"])
        self.assertEqual(
            _mod.path_gate_hit(["clients/brand-new-tui/src/a.ts"], pats),
            ("clients/**", "clients/brand-new-tui/src/a.ts"))

    def test_discovery_does_not_duplicate_or_reorder_listed_suites(self):
        root = self._wt(["clients/digichat-tui", "packages/hero-banner"])
        self.assertEqual(_mod.bun_suites_to_run(root),
                         ["clients/digichat-tui", "packages/hero-banner"])

    def test_no_bun_on_the_host_names_the_gate_not_the_suites(self):
        root = self._wt(["clients/digichat-tui"])
        saved = _mod.bun_bin
        _mod.bun_bin = lambda: None
        try:
            calls, fails = [], []
            ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        finally:
            _mod.bun_bin = saved
        self.assertEqual(ran, [])
        self.assertEqual(fails, ["bun-suites: bun not found"])
        self.assertEqual(calls, [])

    def test_a_bun_that_is_not_the_pinned_version_runs_no_suite(self):
        """#1701/#1705/#1711: an unpinned tool changing under a green build."""
        root = self._wt(["clients/digichat-tui"])
        saved = (_mod.bun_bin, _mod.sh)
        _mod.bun_bin = lambda: "/fake/bun"
        _mod.sh = lambda *a, **k: (0, "1.9.9\n")
        try:
            calls, fails = [], []
            ran = _mod.run_bun_suites(root, self._step(calls, fails), io.StringIO(), fails)
        finally:
            _mod.bun_bin, _mod.sh = saved
        self.assertEqual(ran, [])
        self.assertEqual(fails, [f"bun-version 1.9.9 != {_mod.BUN_PIN}"])
        self.assertEqual(calls, [])

    def test_receipt_names_every_suite_that_ran(self):
        ran = ["digichat-tui", "digiquant-tui", "digivoice-tui"]
        desc = _mod.success_desc(8, {"ran": ran})
        for name in ran:
            self.assertIn(name, desc)
        self.assertLessEqual(len(desc), 139)

    def test_receipt_says_none_when_no_suite_path_changed(self):
        desc = _mod.success_desc(3, {"hit": None, "ran": []})
        self.assertIn("bun: none", desc)
        self.assertIn(_mod.GATED_NOTE, desc)

    def test_receipt_drops_names_rather_than_cutting_them_in_half(self):
        ran = [f"suite-{i}" * 4 for i in range(12)]
        desc = _mod.success_desc(9, {"ran": ran})
        self.assertLessEqual(len(desc), 139)
        self.assertIn("suites in the log", desc)

    def test_run_checks_wires_the_gate_and_the_summary(self):
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("run_bun_suites(WT, step, out, fails)", src)
        self.assertIn('summary["bun"]', src)


class ScopedPytestGateTest(unittest.TestCase):
    """local-ci runs the pytest suite of every module a PR touches (DIG-3605)."""

    def _real_root(self):
        return os.path.abspath(os.path.join(_SCRIPTS, "..", ".."))

    def _modules(self, files, root=None):
        return [m for m, _hit in _mod.pytest_suites_for(files, root or self._real_root())]

    def test_a_docs_only_change_runs_no_suite(self):
        self.assertEqual(self._modules(["docs/README.md", "apps/digichat/src/a.ts"]), [])

    def test_a_module_change_runs_only_that_module(self):
        self.assertEqual(self._modules(["digikey/src/digikey/jwt.py"]), ["digikey"])
        self.assertEqual(self._modules(["tests/dg/test_x.py"]), ["digigraph"])

    def test_triggers_come_from_ci_paths_yaml(self):
        """config/** is digigraph's trigger in ci_paths.yaml, so it fires digigraph."""
        mods = self._modules(["config/model_modes.yaml"])
        self.assertIn("digigraph", mods)
        self.assertNotIn("digikey", mods)

    def test_gate_code_runs_the_scripts_suite(self):
        self.assertEqual(self._modules(["scripts/local-ci/local_ci.py"]), ["scripts"])

    def test_a_root_pytest_input_runs_every_suite(self):
        for f in ("uv.lock", "pytest.ini", "conftest.py", "digibase/pyproject.toml"):
            self.assertEqual(self._modules([f]), list(_mod.PYTEST_SUITES), f)

    def test_patterns_fall_back_to_the_module_dir(self):
        root = tempfile.mkdtemp(prefix="wt-py-")
        self.addCleanup(shutil.rmtree, root, True)
        self.assertEqual(_mod.pytest_suite_patterns(root, "digikey"), ["digikey/**"])
        self.assertIn("scripts/**", _mod.pytest_suite_patterns(root, "scripts"))

    def test_every_suite_path_exists_in_the_tree(self):
        root = self._real_root()
        for module, args in _mod.PYTEST_SUITES.items():
            for a in args:
                if not a.startswith("-") and "/" in a:
                    self.assertTrue(os.path.exists(os.path.join(root, a)), f"{module}: {a}")

    def test_unit_marker_keeps_network_and_paid_tests_out(self):
        for module, args in _mod.PYTEST_SUITES.items():
            if module in ("digillm", "digifetch"):
                # Offline by construction and unmarked (test-digillm.yml).
                self.assertNotIn("-m", args)
            else:
                self.assertIn("-m", args, module)
                self.assertIn("unit", args[args.index("-m") + 1], module)

    def test_env_scrubs_every_credential_and_the_paid_inference_base(self):
        env = _mod.pytest_env({"PATH": "/bin", "CHEAPERINFERENCE_API_KEY": "x",
                               "CHEAPERINFERENCE_API_BASE": "https://example.invalid",
                               "OPENAI_API_KEY": "x", "GH_TOKEN": "x",
                               "SOME_SECRET": "x", "HOME": "/h"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h"})

    def test_gate_fails_closed_when_the_file_list_cannot_be_read(self):
        saved = _mod.gh
        try:
            _mod.gh = lambda *a: None
            self.assertEqual(_mod.pytest_gate({"number": 7}, "/nonexistent-wt"), (None, None))
        finally:
            _mod.gh = saved

    def _run(self, suites, fail_on=()):
        calls, fails = [], []

        def step(name, cmd, timeout=1800, cwd=None, env=None):
            calls.append((name, cmd, env))
            if name in fail_on:
                fails.append(name)
                return False
            return True
        ran = _mod.run_pytest_suites(self._real_root(), step, io.StringIO(), fails, suites)
        return ran, calls, fails

    def test_every_selected_suite_runs_even_after_a_red_one(self):
        suites = [("digikey", ("digikey/**", "digikey/a.py")),
                  ("digibase", ("digibase/**", "digibase/a.py"))]
        ran, calls, fails = self._run(suites, fail_on=("pytest:digikey",))
        self.assertEqual(ran, ["digikey", "digibase"])
        self.assertEqual(fails, ["pytest:digikey"])
        self.assertIn("pytest tests/dk -m unit", calls[0][1])
        self.assertIn("uv run --frozen --no-sync", calls[0][1])
        self.assertNotIn("OPENAI_API_KEY", calls[0][2])

    def test_a_suite_with_no_test_path_fails_by_name(self):
        saved = dict(_mod.PYTEST_SUITES)
        _mod.PYTEST_SUITES["ghost"] = ["tests/no-such-dir", "-m", "unit"]
        try:
            ran, calls, fails = self._run([("ghost", ("ghost/**", "ghost/a.py"))])
        finally:
            _mod.PYTEST_SUITES.clear()
            _mod.PYTEST_SUITES.update(saved)
        self.assertEqual(ran, [])
        self.assertEqual(calls, [])
        self.assertEqual(fails, ["pytest:ghost (no test path)"])

    def test_receipt_names_the_pytest_suites(self):
        desc = _mod.success_desc(4, {"ran": []}, {"ran": ["digikey", "scripts"]})
        self.assertIn("pytest 2/2: digikey, scripts", desc)
        self.assertIn("bun: none", desc)
        self.assertNotIn(_mod.GATED_NOTE, desc)

    def test_receipt_says_pytest_none_when_nothing_ran(self):
        desc = _mod.success_desc(2, None, None)
        self.assertIn("pytest: none", desc)
        self.assertNotIn("pytest/audits not gated", desc)

    def test_run_checks_wires_the_gate_and_the_summary(self):
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("run_pytest_suites(WT, step, out, fails, py_suites)", src)
        self.assertIn('summary["pytest"]', src)
        self.assertIn('summary.get("pytest")', src)


class TemplateWarningTest(unittest.TestCase):
    """pr-template paperwork warns; only the Human Gate fails (plan P1-2)."""

    def _run(self, body):
        saved = {name: getattr(_mod, name) for name in (
            "WT", "sh", "_guard", "wt_is_ours", "pr_body", "gitleaks_log_opts",
            "ruff_paths_for_tree", "ruff_paths_fallback", "worker_gate", "bun_gate",
            "pytest_gate", "npm_gate")}
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        out, summary = io.StringIO(), {}
        try:
            _mod.WT = tmp
            _mod.sh = lambda *a, **k: (0, "")
            _mod._guard = lambda: None
            _mod.wt_is_ours = lambda path: True
            _mod.pr_body = lambda pr: body
            _mod.gitleaks_log_opts = lambda base, sha, out: "--no-walk"
            _mod.ruff_paths_for_tree = lambda wt: (["tests"], "fixture")
            _mod.ruff_paths_fallback = lambda wt: None
            _mod.worker_gate = lambda pr, wt: (0, None)
            _mod.bun_gate = lambda pr, wt: (0, None)
            _mod.pytest_gate = lambda pr, wt: (0, [])
            _mod.npm_gate = lambda pr, wt: (0, [], {}, None)
            pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "develop",
                  "baseCommit": "b" * 40, "title": "fix(ci): fixture"}
            fails = _mod.run_checks(pr, out, summary)
        finally:
            for name, value in saved.items():
                setattr(_mod, name, value)
        return fails, out.getvalue(), summary

    def test_paperwork_only_body_is_green_with_warnings(self):
        body = "## Human Gate\n\n**Is human review required?** No\n"
        fails, log, summary = self._run(body)
        self.assertNotIn("pr-template", fails)
        self.assertIn("pr-template WARN: linked-issue", log)
        self.assertGreater(summary["template_warnings"], 0)

    def test_unanswered_human_gate_is_red(self):
        fails, log, _summary = self._run("Fixes #1\n")
        self.assertIn("pr-template", fails)
        self.assertIn("pr-template FAIL: human-gate", log)

    def test_receipt_counts_template_warnings(self):
        desc = _mod.success_desc(3, {"ran": []}, template_warnings=4)
        self.assertIn("template: 4 warning(s)", desc)
        self.assertLessEqual(len(desc), 139)
        self.assertNotIn("template:", _mod.success_desc(3, {"ran": []}))


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

    def test_r0_allowance_gate_in_static_gate_list(self):
        """A PR that grows the R0 allowance is refused here (DIG-5762).

        The growth gate lived only in the host runner, so #6500 grew the
        baseline (1997 -> 2030), merged green, and the post-merge run caught it
        13 h later. The list entry is a string concatenation, so it is not an
        ast.Constant: pin the command and the base-ref wiring in the source.
        """
        found = self._static_lists(self._tree())
        self.assertEqual(len(found), 1)
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn(
            '"scripts/check_r0_client_literals_baseline_growth.py --base-ref " + r0_base',
            src,
        )
        # The base is the PR's own base branch, or a caller's exact commit.
        self.assertIn('re.fullmatch(r"[0-9a-f]{40}", base_commit)', src)
        self.assertIn('r0_base = "origin/" + base', src)

    def test_supabase_freeze_gate_in_static_gate_list(self):
        """New Supabase usage is refused on the PR, not after merge (DIG-2887 S0)."""
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn('"scripts/check_supabase_freeze.py --base-ref " + r0_base', src)

    def test_run_checks_executes_the_allowance_gate(self):
        """Functionally: a grown baseline makes `run_checks` return the gate.

        The source pins above prove the command is written down; this proves the
        static pool actually executes it and reports its non-zero exit as a
        failed gate. That is the property #6500 merged without: the gate was
        absent from run_checks, so a grown baseline changed nothing.
        """
        tmp = tempfile.mkdtemp()
        gate = "scripts/check_r0_client_literals_baseline_growth.py"
        os.makedirs(os.path.join(tmp, "scripts"))
        with open(os.path.join(tmp, gate), "w") as f:
            f.write("# fixture: existence is all run_checks tests\n")

        saved = {name: getattr(_mod, name) for name in (
            "WT", "sh", "_guard", "wt_is_ours", "pr_body", "gitleaks_log_opts",
            "ruff_paths_for_tree", "ruff_paths_fallback", "worker_gate",
            "bun_gate", "pytest_gate")}
        commands: list[str] = []

        def fake_sh(cmd, cwd=None, timeout=None, out=None, name=None, env=None):
            text = cmd if isinstance(cmd, str) else " ".join(str(p) for p in cmd)
            commands.append(text)
            if gate in text:
                if out is not None:
                    out.write("r0-client-literal-baseline-growth: 1 finding(s)\n")
                return 1, ""
            return 0, ""

        try:
            _mod.WT = tmp
            _mod.sh = fake_sh
            _mod._guard = lambda: None
            _mod.wt_is_ours = lambda path: True
            _mod.pr_body = lambda pr: "Fixes DIG-5762\n"
            _mod.gitleaks_log_opts = lambda base, sha, out: None
            _mod.ruff_paths_for_tree = lambda wt: ("", "fixture")
            _mod.ruff_paths_fallback = lambda wt: None
            _mod.worker_gate = lambda pr, wt: (None, None)
            _mod.bun_gate = lambda pr, wt: (0, None)
            _mod.pytest_gate = lambda pr, wt: (0, [])
            pr = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "develop",
                  "baseCommit": "b" * 40, "title": "fix(ci): fixture"}
            fails = _mod.run_checks(pr, io.StringIO())
        finally:
            for name, value in saved.items():
                setattr(_mod, name, value)
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIn(gate, fails)
        self.assertTrue(
            any(f"{gate} --base-ref {'b' * 40}" in c for c in commands),
            "the gate must compare against the caller's base commit",
        )

    def test_static_list_drives_single_step_call(self):
        """Each entry becomes exactly one spec, and the specs are what runs.

        The list used to drive one `step(...)` call per entry. It now drives one
        `scan_specs.append(...)` per entry, because the independent gates run in
        a bounded pool (STEP_POOL); the property this pins is unchanged - every
        entry in the list is executed exactly once, with its own command.
        """
        tree = self._tree()
        found = self._static_lists(tree)
        self.assertEqual(len(found), 1)
        loops = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.For) and node.iter is found[0]
        ]
        self.assertEqual(len(loops), 1)
        appends = [
            node for node in ast.walk(loops[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "scan_specs"
        ]
        self.assertEqual(len(appends), 1)
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("fails.extend(run_step_pool(scan_specs, out))", src)

    def test_docstring_names_r0_scan(self):
        self.assertIn("R0 client-literal scan", ast.get_docstring(self._tree()))


class StepPoolTest(unittest.TestCase):
    """The independent gates run in a bounded pool (STEP_POOL)."""

    def test_pool_runs_specs_concurrently_and_reports_in_declared_order(self):
        import threading
        barrier = threading.Barrier(2, timeout=5)
        seen = []

        def fake_sh(cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
            seen.append(name)
            barrier.wait()          # deadlocks (BrokenBarrierError) if serialised
            if name == "second":
                if out:
                    out.write("boom\n")
                return 1, ""
            return 0, ""

        specs = [("first", ["true"], 30, None, None, ()),
                 ("second", ["false"], 30, None, None, ())]
        log = io.StringIO()
        saved = _mod.sh
        _mod.sh = fake_sh
        try:
            fails = _mod.run_step_pool(specs, log, limit=2)
        finally:
            _mod.sh = saved
        self.assertEqual(sorted(seen), ["first", "second"], "both specs must run")
        self.assertEqual(fails, ["second"], "only the failing step is reported")
        text = log.getvalue()
        self.assertLess(text.index("===== first"), text.index("===== second"),
                        "the log keeps the declared order, not the finish order")

    def test_pool_stops_at_the_specs_it_was_given(self):
        calls = []

        def fake_sh(cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
            calls.append(name)
            return 0, ""

        saved = _mod.sh
        _mod.sh = fake_sh
        try:
            fails = _mod.run_step_pool([("only", ["true"], 30, None, None, ())],
                                       io.StringIO(), limit=6)
        finally:
            _mod.sh = saved
        self.assertEqual(fails, [])
        self.assertEqual(calls, ["only"])

    def test_child_state_holds_every_live_step(self):
        saved = _mod.CHILD_STATE
        tmp = tempfile.mkdtemp()
        _mod.CHILD_STATE = os.path.join(tmp, "child.json")
        try:
            _mod._write_child_state(111, "one", 30)
            _mod._write_child_state(222, "two", 30)
            self.assertEqual(len(_mod.read_child_state()["children"]), 2)
            _mod._clear_child_state(111)
            left = _mod.read_child_state()["children"]
            self.assertEqual([c["pid"] for c in left], [222])
            _mod._clear_child_state()
            self.assertIsNone(_mod.read_child_state())
        finally:
            _mod._clear_child_state()
            _mod.CHILD_STATE = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_watchdog_reads_a_state_file_written_before_the_pool(self):
        saved = _mod.CHILD_STATE
        tmp = tempfile.mkdtemp()
        _mod.CHILD_STATE = os.path.join(tmp, "child.json")
        try:
            with open(_mod.CHILD_STATE, "w") as f:
                json.dump({"pid": 999999, "name": "old", "started": time.time(),
                           "budget": 300}, f)
            st = _mod.read_child_state()
            self.assertEqual(st["children"][0]["pid"], 999999)
        finally:
            _mod.CHILD_STATE = saved
            shutil.rmtree(tmp, ignore_errors=True)


class PrepareWorktreeTest(unittest.TestCase):
    """Stale-worktree incident (17 Oct 2026): a silent checkout failure must
    fail closed, never run gates on whatever tree is left in WT."""
    SHA = "a" * 40

    def _run(self, heads, wt_exists=True, own=True):
        import io
        calls = []
        seq = list(heads)
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        def make_wt():
            os.makedirs(wt, exist_ok=True)
            # a linked worktree of MAIN names a gitdir under MAIN's worktrees dir
            owner = common if own else os.path.join(tmp, "other")
            os.makedirs(os.path.join(owner, "worktrees"), exist_ok=True)
            with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
                fh.write(f"gitdir: {os.path.join(owner, 'worktrees', 'wt')}\n")
        if wt_exists:
            make_wt()
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            calls.append(cmd)
            if cmd[:3] == ["git", "worktree", "add"]:
                make_wt()  # git creates the worktree
            elif cmd[:3] == ["git", "worktree", "remove"]:
                shutil.rmtree(wt, ignore_errors=True)
            elif cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
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
        # three reads of HEAD: the worktree-is-it-readable read, the read after
        # the checkout, and the final one before the gates (DIG-5285)
        (ok, why), calls, _ = self._run([self.SHA, self.SHA, self.SHA])
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
        (ok, _), calls, text = self._run([None, self.SHA, self.SHA])
        self.assertTrue(ok)
        self.assertIn("rebuilding", text)
        self.assertTrue(any(c[:3] == ["git", "worktree", "remove"] for c in calls))
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_a_directory_we_did_not_create_is_never_deleted(self):
        """LOCAL_CI_WT is operator-supplied: a typo must not delete someone's tree."""
        (ok, why), calls, _ = self._run([None, self.SHA], own=False)
        self.assertFalse(ok)
        self.assertIn("not a worktree this runner created", why)
        self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in calls))
        self.assertFalse(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_missing_worktree_added(self):
        (ok, _), calls, _ = self._run([self.SHA, self.SHA], wt_exists=False)
        self.assertTrue(ok)
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in calls))

    def test_process_does_not_run_gates_on_bad_checkout(self):
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("run_checks(pr, out, summary) if ok_wt else", src)
        self.assertIn("run_review_coverage(pr, out) if ok_wt else", src)


class WorktreeSelfHealTest(unittest.TestCase):
    """DIG-5285: a stalled checkout must not fail the whole check.

    The post-merge run on develop tip 9581532dc712 spent 900 s inside
    `git checkout` and then failed the check, on a worktree that checks out in
    under a second, and the check named one opaque step. A checkout that does
    not land is retried, the reason carries the rc and both HEADs, and a work
    the runner does not own is never destroyed.
    """

    SHA = "a" * 40
    STALE = "b" * 40

    def _run(self, checkouts, own=True, add_rc=0, remove_rc=0):
        """checkouts: what each `git checkout` does - "land", "stall", "wrong" or "err"."""
        calls = []
        state = {"head": self.STALE, "outs": list(checkouts)}
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        def make_wt():
            os.makedirs(wt, exist_ok=True)
            owner = common if own else os.path.join(tmp, "other")
            os.makedirs(os.path.join(owner, "worktrees"), exist_ok=True)
            with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
                fh.write(f"gitdir: {os.path.join(owner, 'worktrees', 'wt')}\n")
        make_wt()
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            calls.append((cmd, timeout))
            if cmd[:2] == ["git", "checkout"]:
                outcome = state["outs"].pop(0) if state["outs"] else "land"
                if outcome == "land":
                    state["head"] = self.SHA
                    return 0, ""
                if outcome == "stall":
                    return 124, ""
                if outcome == "wrong":
                    return 0, ""  # rc 0 but the HEAD did not move
                return 1, ""
            if cmd[:3] == ["git", "worktree", "add"]:
                if add_rc != 0:
                    return add_rc, ""
                make_wt()  # git creates the worktree and checks the commit out
                state["head"] = self.SHA
                return 0, ""
            if cmd[:3] == ["git", "worktree", "remove"]:
                if remove_rc != 0:
                    return remove_rc, ""
                shutil.rmtree(wt, ignore_errors=True)
                return 0, ""
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
            return 0, ""
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        _mod.sh = fake_sh
        _mod.wt_head = lambda: state["head"]
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            res = _mod.prepare_wt(7, self.SHA, "develop", buf)
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)
        return res, calls, buf.getvalue()

    def _cmds(self, calls):
        return [c for c, _ in calls]

    def _checkouts(self, calls):
        return [c for c, _ in calls if c[:2] == ["git", "checkout"]]

    def test_a_stalled_checkout_is_retried_in_place(self):
        """A stall is git fetching a blob over a slow network. A rebuild fetches
        it all again, so the second attempt stays where it is."""
        (ok, why), calls, text = self._run(["stall", "land"])
        self.assertTrue(ok, why)
        self.assertEqual(why, "")
        self.assertEqual(len(self._checkouts(calls)), 2)
        self.assertIn("retrying in place", text)
        self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in self._cmds(calls)))

    def test_a_stall_that_does_not_clear_is_reported_as_a_stall(self):
        (ok, why), calls, text = self._run(["stall", "stall"])
        self.assertFalse(ok)
        self.assertIn("stalled", why)
        self.assertIn("no gate ran", text)
        self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in self._cmds(calls)),
                         "a stall must not throw the worktree away")

    def test_a_broken_worktree_is_rebuilt_and_the_checkout_is_not_repeated(self):
        """`git worktree add --detach -f` checks the commit out itself."""
        (ok, why), calls, _ = self._run(["wrong"])
        self.assertTrue(ok, why)
        self.assertEqual(len(self._checkouts(calls)), 1, "the rebuild already lands the commit")
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in self._cmds(calls)))

    def test_a_failed_checkout_is_rebuilt(self):
        (ok, why), calls, _ = self._run(["err"])
        self.assertTrue(ok, why)
        self.assertTrue(any(c[:3] == ["git", "worktree", "remove"] for c in self._cmds(calls)))
        self.assertTrue(any(c[:3] == ["git", "worktree", "add"] for c in self._cmds(calls)))

    def test_a_failed_rebuild_is_reported(self):
        (ok, why), _, text = self._run(["err"], add_rc=1)
        self.assertFalse(ok)
        self.assertIn("the worktree add failed", why)
        self.assertIn("no gate ran", text)

    def test_the_retry_is_bounded(self):
        (ok, why), calls, _ = self._run(["stall", "stall"])
        self.assertFalse(ok)
        self.assertEqual(len(self._checkouts(calls)), 2, "a wedged git must not loop")

    def test_the_failure_carries_the_evidence(self):
        (ok, why), _, text = self._run(["stall", "stall"])
        self.assertFalse(ok)
        self.assertIn("rc=124", why)
        self.assertIn(self.SHA[:12], why)
        self.assertIn("no gate ran", text)

    def test_the_lock_is_released_before_the_remove(self):
        """git does not remove a locked worktree: the lock has to go first."""
        _, calls, _ = self._run(["err"])
        cmds = self._cmds(calls)
        unlock = next(i for i, c in enumerate(cmds) if c[:3] == ["git", "worktree", "unlock"])
        remove = next(i for i, c in enumerate(cmds) if c[:3] == ["git", "worktree", "remove"])
        self.assertLess(unlock, remove, "the unlock has to come before the remove")

    def test_the_remove_is_scoped_to_this_worktree(self):
        """`git worktree prune` is repository-wide: it would take the admin entry
        of an operator's worktree on an unmounted volume with it."""
        _, calls, _ = self._run(["err"])
        self.assertFalse(any(c[:3] == ["git", "worktree", "prune"] for c in self._cmds(calls)))
        self.assertTrue(any(c[:3] == ["git", "worktree", "remove"] for c in self._cmds(calls)))

    def test_a_worktree_we_did_not_create_is_never_rebuilt(self):
        (ok, why), calls, _ = self._run(["err"], own=False)
        self.assertFalse(ok)
        self.assertIn("not a worktree this runner created", why)
        self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in self._cmds(calls)))
        self.assertFalse(any(c[:3] == ["git", "worktree", "add"] for c in self._cmds(calls)))

    def test_the_budgets_are_pinned(self):
        self.assertEqual(_mod.WT_CHECKOUT_TIMEOUT, 300)
        self.assertEqual(_mod.WT_REBUILD_TIMEOUT, 600)
        self.assertEqual(_mod.WT_META_TIMEOUT, 60)

    def test_every_step_of_the_rebuild_has_its_own_budget(self):
        """The defaults are 1800 s: the rebuild path must not inherit them."""
        _, calls, _ = self._run(["err"])
        for cmd, timeout in calls:
            if cmd[:3] in (["git", "worktree", "remove"], ["git", "worktree", "unlock"],
                           ["git", "worktree", "add"]) or cmd[:2] == ["git", "checkout"]:
                self.assertLessEqual(timeout, _mod.WT_REBUILD_TIMEOUT, f"{cmd} has no budget")

    def test_the_caches_survive_a_rebuild(self):
        """A rebuild that drops node_modules and .venv costs a full npm ci and
        uv sync, which turns a stall into an hour-long check."""
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        os.makedirs(os.path.join(common, "worktrees"), exist_ok=True)
        os.makedirs(wt, exist_ok=True)
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
            fh.write(f"gitdir: {os.path.join(common, 'worktrees', 'wt')}\n")
        for name in ("node_modules", ".venv"):
            os.makedirs(os.path.join(wt, name), exist_ok=True)
            with open(os.path.join(wt, name, "marker"), "w", encoding="utf-8") as fh:
                fh.write(name)
        state = {"head": self.STALE}
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            if cmd[:2] == ["git", "checkout"]:
                return 1, ""
            if cmd[:3] == ["git", "worktree", "add"]:
                os.makedirs(wt, exist_ok=True)
                with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
                    fh.write(f"gitdir: {os.path.join(common, 'worktrees', 'wt')}\n")
                state["head"] = self.SHA
                return 0, ""
            if cmd[:3] == ["git", "worktree", "remove"]:
                shutil.rmtree(wt, ignore_errors=True)
                return 0, ""
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
            return 0, ""
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        _mod.sh = fake_sh
        _mod.wt_head = lambda: state["head"]
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            ok, why = _mod.prepare_wt(7, self.SHA, "develop", buf)
            self.assertTrue(ok, why)
            for name in ("node_modules", ".venv"):
                self.assertTrue(os.path.isfile(os.path.join(wt, name, "marker")),
                                f"{name} did not survive the rebuild")
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_worktree_keeps_the_mark_that_makes_it_ours(self):
        """With LOCAL_CI_WT set the marker is the only thing that says the
        directory belongs to the runner; without it a later stall cannot heal."""
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        os.makedirs(os.path.join(common, "worktrees"), exist_ok=True)
        os.makedirs(wt, exist_ok=True)
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
            fh.write(f"gitdir: {os.path.join(common, 'worktrees', 'wt')}\n")
        state = {"head": self.SHA}
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            if cmd[:3] == ["git", "worktree", "add"]:
                os.makedirs(wt, exist_ok=True)
                with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
                    fh.write(f"gitdir: {os.path.join(common, 'worktrees', 'wt')}\n")
                return 0, ""
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
            return 0, ""
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        _mod.sh = fake_sh
        _mod.wt_head = lambda: state["head"]
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            ok, why = _mod.prepare_wt(7, self.SHA, "develop", buf)
            self.assertTrue(ok, why)
            self.assertTrue(os.path.isfile(os.path.join(wt, ".local-ci-worktree")))
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_real_directory_that_is_not_a_worktree_is_never_rebuilt(self):
        """The sentinel file alone must not authorise a rebuild: the runner
        writes it into whatever directory LOCAL_CI_WT names (DIG-5285)."""
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        os.makedirs(wt, exist_ok=True)
        os.makedirs(common, exist_ok=True)
        with open(os.path.join(wt, ".local-ci-worktree"), "w", encoding="utf-8") as fh:
            fh.write(self.SHA)
        calls = []
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            calls.append(cmd)
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
            return 0, ""
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        _mod.sh = fake_sh
        _mod.wt_head = lambda: self.STALE
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            ok, why = _mod.prepare_wt(7, self.SHA, "develop", buf)
            self.assertFalse(ok)
            self.assertIn("not a worktree this runner created", why)
            self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in calls))
            self.assertTrue(os.path.isdir(wt), "the directory has to survive")
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_worktree_with_uncommitted_changes_is_not_removed(self):
        """That is somebody's work, not checkout material (DIG-4490)."""
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        common = os.path.join(tmp, "common")
        os.makedirs(wt, exist_ok=True)
        os.makedirs(os.path.join(common, "worktrees"), exist_ok=True)
        with open(os.path.join(wt, ".git"), "w", encoding="utf-8") as fh:
            fh.write(f"gitdir: {os.path.join(common, 'worktrees', 'wt')}\n")
        calls = []
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            calls.append(cmd)
            if cmd[:2] == ["git", "checkout"]:
                return 1, ""  # the checkout failed, so the rebuild is considered
            if cmd[:2] == ["git", "status"]:
                return 0, " M file.py\n"
            if cmd[:2] == ["git", "rev-parse"] and len(cmd) > 2 and cmd[2] == "--git-common-dir":
                return 0, common
            return 0, ""
        saved = (_mod.sh, _mod.wt_head, _mod.WT, _mod.log)
        _mod.sh = fake_sh
        _mod.wt_head = lambda: self.STALE
        _mod.WT = wt
        _mod.log = lambda m: None
        try:
            buf = io.StringIO()
            ok, why = _mod.prepare_wt(7, self.SHA, "develop", buf)
            self.assertFalse(ok)
            self.assertIn("uncommitted changes", why)
            self.assertFalse(any(c[:3] == ["git", "worktree", "remove"] for c in calls))
            self.assertTrue(os.path.isdir(wt), "the directory has to survive")
        finally:
            _mod.sh, _mod.wt_head, _mod.WT, _mod.log = saved
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_gates_do_not_run_when_the_worktree_fails(self):
        """The reason is in the status description, so a failed check says why."""
        ran = []
        tmp = tempfile.mkdtemp()
        saved = (_mod.prepare_wt, _mod.run_checks, _mod.log, _mod.ci_status, _mod.LOGD)
        _mod.prepare_wt = lambda n, sha, base, out: (False, "git stalled in the worktree checkout")
        _mod.run_checks = lambda pr, out: ran.append(1) or []
        _mod.log = lambda m: None
        _mod.ci_status = lambda sha: ("pending", "")
        _mod.LOGD = tmp
        try:
            st = _mod.process({"number": 999999, "headRefOid": "a" * 40,
                               "baseRefName": "develop"}, True)
        finally:
            (_mod.prepare_wt, _mod.run_checks, _mod.log, _mod.ci_status, _mod.LOGD) = saved
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(ran, [], "run_checks must not be called when the worktree failed")
        self.assertEqual(st, "failure")
        src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
        self.assertIn("fails = run_checks(pr, out, summary) if ok_wt else", src)
        self.assertIn('f"worktree checkout ({why})"', src)

    def test_the_rebuild_leaves_the_worktree_marked_as_ours(self):
        """With LOCAL_CI_WT set the sentinel is the only thing that says the
        directory is the runner's: without it a later stall can never heal."""
        tmp = tempfile.mkdtemp()
        wt = os.path.join(tmp, "wt")
        os.mkdir(wt)
        def fake_sh(cmd, cwd=None, timeout=1800, out=None, **kw):
            if cmd[:3] == ["git", "worktree", "add"]:
                os.makedirs(wt, exist_ok=True)  # git creates the worktree
            return 0, ""
        saved = (_mod.sh, _mod.WT)
        _mod.sh = fake_sh
        _mod.WT = wt
        try:
            self.assertTrue(_mod._wt_rebuild(self.SHA, io.StringIO()))
            sentinel = os.path.join(wt, ".local-ci-worktree")
            self.assertTrue(os.path.exists(sentinel))
            self.assertEqual(open(sentinel).read().strip(), self.SHA)
        finally:
            _mod.sh, _mod.WT = saved
            shutil.rmtree(tmp, ignore_errors=True)

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


class InstallMarkerTest(unittest.TestCase):
    """install.sh names the checkout the runner may keep current (DIG-5135).

    The runner may only move a checkout the operator marked as its own, so
    the install is what writes the marker. A linked worktree is installed
    with the update turned off: that checkout is somebody else's.
    """

    def _sandbox(self):
        tmp = tempfile.mkdtemp(prefix="install-marker-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        stub = os.path.join(bindir, "launchctl")
        with open(stub, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(stub, 0o755)
        if shutil.which("plutil") is None:
            # plutil is macOS-only and the install lints the rendered plist
            # with it. Without a stub the install cannot be exercised on the
            # Linux CI lane, and the test would fail there and pass on the
            # Mac (DIG-5135).
            stub = os.path.join(bindir, "plutil")
            with open(stub, "w") as f:
                f.write("#!/bin/sh\nexit 0\n")
            os.chmod(stub, 0o755)
        env = dict(os.environ, HOME=home,
                   PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        return tmp, home, env

    def _clone(self, tmp, env):
        """A real clone on develop, with the runner in it.

        A clone and not a working tree: the runner may only keep a checkout
        current that carries nothing of its own, so the checkout here has a
        clean tree, no commits beyond origin/develop and an `origin` to
        compare with.
        """
        checkout = os.path.join(tmp, "checkout")
        os.makedirs(checkout)
        git_env = _git_env(env)
        subprocess.check_call(["git", "init", "-q", "-b", "develop", checkout])
        os.makedirs(os.path.join(checkout, "scripts", "local-ci"))
        # The install refuses a checkout that carries the runner without the
        # guard (DIG-4796), and one where a module the runner imports does not
        # resolve (DIG-5585). The clone therefore carries every module next to
        # the runner, plus the shared module in `scripts/`, one directory up.
        # Copying every `.py` keeps these cases about the marker: a helper
        # added to the runner is in the clone without editing this list.
        for name in os.listdir(_SCRIPTS):
            if name.endswith(".py"):
                shutil.copy(os.path.join(_SCRIPTS, name),
                            os.path.join(checkout, "scripts", "local-ci", name))
        shutil.copy(os.path.join(_SCRIPTS, "..", "review_pass_filter.py"),
                    os.path.join(checkout, "scripts", "review_pass_filter.py"))
        subprocess.check_call(["git", "-C", checkout, "add", "-A"], env=git_env)
        subprocess.check_call(["git", "-C", checkout, "commit", "-q", "-m", "x"], env=git_env)
        subprocess.check_call(["git", "-C", checkout, "remote", "add", "origin", checkout],
                              env=git_env)
        subprocess.check_call(["git", "-C", checkout, "fetch", "-q", "origin", "develop"],
                              env=git_env)
        return checkout

    def _marker(self, home):
        path = os.path.join(home, ".config/digithings/state/local-ci-runner.json")
        with open(path) as f:
            return json.load(f)

    def test_the_install_marks_the_checkout_as_the_runners_own(self):
        """The operator's word is what allows the runner to move a checkout."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"),
                              "--self-update", checkout], env=env)
        self.assertEqual(rc, 0, "the install must succeed")
        marker = self._marker(home)
        self.assertEqual(marker.get("main"), checkout,
                         "the marker must name the checkout the runner was installed from")
        self.assertTrue(marker.get("self_update"),
                        "a clone on develop may be kept current by the runner")

    def test_a_dry_run_renders_the_interpreter_the_job_will_run(self):
        """The plist must name the same interpreter the install check used.

        A `ProgramArguments` entry left as a placeholder lints cleanly and
        fails only when launchd tries to spawn it, so a render that never
        substituted the interpreter reads as an installed job and runs nothing
        (DIG-5725).
        """
        tmp, _home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        done = subprocess.run(["sh", os.path.join(_SCRIPTS, "install.sh"),
                               "--dry-run", checkout],
                              env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotIn("__", done.stdout,
                         "an unsubstituted placeholder is a plist launchd cannot run")
        self.assertIn("<string>/usr/bin/python3</string>", done.stdout,
                      "the job must run under the interpreter the install check used")

    def test_a_checkout_without_the_guard_is_refused(self):
        """An installer must not point the daemon at a pre-guard checkout.

        The runner refuses to run without `launch_guard.py` next to it (exit
        78), so installing that checkout would stop the only pre-merge
        producer. The install refuses it up front instead (DIG-4796).
        """
        tmp, _home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        os.remove(os.path.join(checkout, "scripts", "local-ci", "launch_guard.py"))
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"), checkout], env=env)
        self.assertNotEqual(rc, 0, "a runner that cannot be guarded must not be installed")

    def test_a_checkout_without_the_install_check_is_refused(self):
        """An installer must not point the daemon at a checkout with no preflight.

        The runner exits 78 on every tick when `import_preflight.py` is absent
        (`_require_install`, DIG-5585), so installing from a stale checkout
        leaves the daemon running and the gate dark. The install refuses the
        tree before it writes anything (DIG-5725).
        """
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        os.remove(os.path.join(checkout, "scripts", "local-ci", "import_preflight.py"))
        done = subprocess.run(["sh", os.path.join(_SCRIPTS, "install.sh"), checkout],
                              env=env, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0,
                            "a checkout without the install check must not be installed")
        self.assertIn("import_preflight.py", done.stderr,
                      "the refusal must name the module the checkout is missing")
        self.assertFalse(os.path.exists(os.path.join(
            home, "Library", "LaunchAgents", "ai.digithings.local-ci.plist")),
            "a refused install must not write a plist")

    def test_a_checkout_missing_an_imported_module_is_refused(self):
        """A stale checkout can look complete: refuse it by import, not by name.

        The runner imports `pr_template` and fails closed when it is None, so a
        checkout that carries the runner but not a helper it imports still
        looks installable. The install asks the checkout's own preflight, which
        resolves every import, and refuses with the module named (DIG-5725).
        """
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        os.remove(os.path.join(checkout, "scripts", "local-ci", "pr_template.py"))
        done = subprocess.run(["sh", os.path.join(_SCRIPTS, "install.sh"), checkout],
                              env=env, capture_output=True, text=True)
        self.assertNotEqual(done.returncode, 0,
                            "a checkout missing an imported module must not be installed")
        self.assertIn("pr_template", done.stderr,
                      "the refusal must name the module that could not be resolved")
        self.assertFalse(os.path.exists(os.path.join(
            home, "Library", "LaunchAgents", "ai.digithings.local-ci.plist")),
            "a refused install must not write a plist")

    def test_a_clone_without_the_word_is_never_moved_by_the_runner(self):
        """Without --self-update the runner keeps the commit it was installed on."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"), checkout], env=env)
        self.assertEqual(rc, 0, "the install must succeed")
        marker = self._marker(home)
        self.assertEqual(marker.get("main"), checkout,
                         "the marker must still name the checkout")
        self.assertFalse(marker.get("self_update"),
                         "the runner may only move a checkout the operator marked")

    def test_a_linked_worktree_is_installed_with_the_update_turned_off(self):
        """A linked worktree is somebody else's checkout: the runner may not move it."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        linked = os.path.join(tmp, "linked")
        subprocess.check_call(["git", "-C", checkout, "worktree", "add", "-q",
                               "--detach", linked], env=_git_env(env))
        os.makedirs(os.path.join(linked, "scripts", "local-ci"), exist_ok=True)
        shutil.copy(os.path.join(_SCRIPTS, "local_ci.py"),
                    os.path.join(linked, "scripts", "local-ci", "local_ci.py"))
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"),
                              "--self-update", "--allow-worktree", linked], env=env)
        self.assertEqual(rc, 0, "the install must succeed")
        marker = self._marker(home)
        self.assertFalse(marker.get("self_update"),
                         "a linked worktree must never be moved by the runner")

    def test_a_working_tree_with_uncommitted_changes_is_not_moved_by_the_runner(self):
        """A tree somebody works in must not be fast-forwarded under them."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        with open(os.path.join(checkout, "notes.txt"), "w") as f:
            f.write("work in progress\n")
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"),
                              "--self-update", checkout], env=env)
        self.assertEqual(rc, 0, "the install must succeed")
        marker = self._marker(home)
        self.assertFalse(marker.get("self_update"),
                         "a tree with uncommitted changes must not be moved by the runner")

    def test_a_checkout_with_commits_of_its_own_is_not_moved_by_the_runner(self):
        """A commit of its own means the checkout is somebody's work, not the runner's home."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        git_env = _git_env(env)
        subprocess.check_call(["git", "-C", checkout, "commit", "-q", "--allow-empty",
                               "-m", "local work"], env=git_env)
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"),
                              "--self-update", checkout], env=env)
        self.assertEqual(rc, 0, "the install must succeed")
        marker = self._marker(home)
        self.assertFalse(marker.get("self_update"),
                         "a checkout with commits of its own must not be moved by the runner")

    def test_a_failed_bootstrap_leaves_the_previous_marker_in_place(self):
        """The marker belongs to the job that is running: a failed install must not change it."""
        tmp, home, env = self._sandbox()
        checkout = self._clone(tmp, env)
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"), checkout], env=env)
        self.assertEqual(rc, 0, "the first install must succeed")
        marker_path = os.path.join(home, ".config/digithings/state/local-ci-runner.json")
        with open(marker_path) as f:
            before = f.read()
        stub = os.path.join(env["PATH"].split(os.pathsep)[0], "launchctl")
        with open(stub, "w") as f:
            f.write('#!/bin/sh\ncase "$1" in bootstrap) exit 1 ;; esac\nexit 0\n')
        os.chmod(stub, 0o755)
        rc = subprocess.call(["sh", os.path.join(_SCRIPTS, "install.sh"),
                              "--self-update", checkout], env=env)
        self.assertNotEqual(rc, 0, "a failed bootstrap must fail the install")
        with open(marker_path) as f:
            self.assertEqual(f.read(), before,
                             "the marker of the job that is running must be kept")


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
        self._logd = _mod.LOGD
        _mod.CHILD_STATE = os.path.join(self.tmp, "child.json")
        _mod.LOCK = os.path.join(self.tmp, "lock")
        _mod.LOGD = os.path.join(self.tmp, "logs")
        os.makedirs(_mod.LOGD, exist_ok=True)
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
        _mod.LOGD = self._logd
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

    def _production_ticks(self):
        """How many "watchdog: tick" records the production log holds.

        The production log is derived from the module's HOME, never from LOGD:
        LOGD is the variable this fix redirects, so counting through it would
        count the test's own record (DIG-5255, review round 2). A missing log
        counts as zero.
        """
        path = os.path.join(_mod.HOME, ".config", "digithings", "logs", "local-ci",
                            "local-ci.log")
        try:
            with open(path) as f:
                return sum(1 for line in f if "watchdog: tick" in line)
        except OSError:
            return 0

    def test_the_decision_is_recorded_in_the_test_log(self):
        """The watchdog's line must land in the test's own log, never in production.

        The logger resolves LOGD at call time, and this class patches the child
        state, the lock and the grace but not the log directory: every pytest
        run wrote a synthetic "watchdog: tick ... over budget 0s" record into
        the production log ~/.config/digithings/logs/local-ci/local-ci.log (446
        such records measured 2026-10-22 09:03, one per test run). That log is
        the forensic trail the receipt producer is attributed from, so a test
        record there is a false lead about who produced a receipt.

        The assertion has to be able to fail (DIG-5255, review round 2): the
        record is read from the path the test owns, and the production log is
        counted from the module's HOME - never from LOGD, which is the variable
        this fix redirects, so reading it back would assert the fix against
        itself. The production log is counted around the watchdog call itself,
        so a concurrent run on another branch cannot make this flaky.
        """
        self.assertTrue(os.path.abspath(_mod.LOGD).startswith(os.path.abspath(self.tmp)),
                        "the log directory must be redirected into the test's own directory")
        self.assertTrue(self._wait_child_age(1))
        self._state_file(budget=0)

        ticks_before = self._production_ticks()
        self.assertTrue(_mod.watchdog())
        ticks_after = self._production_ticks()

        with open(os.path.join(self.tmp, "logs", "local-ci.log")) as f:
            record = f.read()
        self.assertIn("watchdog: tick", record)
        self.assertIn("worker-build:digithings-cron", record)
        self.assertEqual(ticks_before, ticks_after,
                         "the watchdog record must not reach the production log")


class RuffPathResolverTest(unittest.TestCase):
    """DIG-4602: the ruff path list must come from the tree under test.

    A module rename (digiclaw -> digibot) moved a path out from under the
    hardcoded list, and ruff 0.16 fails on a missing path (E902), so a stale
    list turns every other PR red.
    """

    CI = (
        "jobs:\n"
        "  lint:\n"
        "    steps:\n"
        "      - name: Ruff (all src + tests)\n"
        "        run: |\n"
        "          uv run --frozen --no-sync ruff check \\\n"
        "            digibase/src %s digigraph/src \\\n"
        "            digisearch/src digitrace/src tests\n"
    )

    def _tree(self, body):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, ".github", "workflows"))
        with open(os.path.join(d, ".github", "workflows", "ci.yml"), "w") as f:
            f.write(body)
        return d

    def test_list_comes_from_the_tree_own_ci_yml(self):
        tree = self._tree(self.CI % "digiclaw/src")
        paths, note = _mod.ruff_paths_for_tree(tree)
        self.assertEqual(paths, ["digibase/src", "digiclaw/src", "digigraph/src",
                                 "digisearch/src", "digitrace/src", "tests"])
        self.assertIn("ci.yml", note)

    def test_a_renamed_module_resolves_to_its_new_name(self):
        tree = self._tree(self.CI % "digibot/src")
        paths, _ = _mod.ruff_paths_for_tree(tree)
        self.assertIn("digibot/src", paths)
        self.assertNotIn("digiclaw/src", paths)

    def test_missing_ci_yml_falls_back_loudly(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        paths, note = _mod.ruff_paths_for_tree(d)
        self.assertIsNone(paths)
        self.assertIn("ci.yml", note)

    def test_two_different_lists_are_refused(self):
        body = self.CI % "digibot/src" + "          uv run --frozen --no-sync ruff check tests\n"
        tree = self._tree(body)
        paths, note = _mod.ruff_paths_for_tree(tree)
        self.assertIsNone(paths)
        self.assertIn("single", note)

    def test_a_path_outside_the_tree_is_refused(self):
        tree = self._tree(self.CI % "/etc")
        paths, _ = _mod.ruff_paths_for_tree(tree)
        self.assertIsNone(paths)

    def test_the_fallback_keeps_only_paths_that_exist_in_the_tree(self):
        """The fallback drops a path the tree does not have.

        ruff 0.16 fails on a missing path (E902), so a fallback that named a
        retired module directory would turn every other PR red. Linting fewer
        paths only under-lints, and this branch only runs when the tree's
        ci.yml cannot be read.
        """
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "digibot", "src"))
        os.makedirs(os.path.join(d, "tests"))
        paths = _mod.ruff_paths_fallback(d)
        self.assertEqual(sorted(paths), ["digibot/src", "tests"])

    def test_the_fallback_names_no_retired_module(self):
        self.assertNotIn("digiclaw", " ".join(_mod.RUFF_PATHS_CANDIDATES))

    def test_the_fallback_is_empty_when_the_tree_has_no_candidate(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        self.assertIsNone(_mod.ruff_paths_fallback(d))

    def test_the_gate_no_longer_hardcodes_a_module_name(self):
        import inspect
        src = inspect.getsource(_mod.run_checks)
        self.assertIn("ruff_paths_for_tree(WT)", src)
        self.assertNotIn("digiclaw/src", src)

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


class ReviewCoverageEvidenceTest(unittest.TestCase):
    """DIG-4507: the promotion judgement is evidence, not a second producer.

    The runner used to post `Every commit reaching main was reviewed` as a
    commit status with a user token while `ci-review-coverage.yml` posted the
    same context as an app-owned check run. Two implementations of one required
    context disagree, and the user-token row can never satisfy an app pin. The
    workflow is the single producer; the runner keeps its per-PR log only.
    """

    SHA = "b84c114e0000000000000000000000000000000"

    def setUp(self):
        self._logd = _mod.LOGD
        self._prepare_wt = _mod.prepare_wt
        self._run_review_coverage = _mod.run_review_coverage
        self._gh = _mod.gh
        self.tmp = tempfile.mkdtemp()
        _mod.LOGD = self.tmp
        self.gh_calls = []
        _mod.gh = lambda *a: self.gh_calls.append(list(a)) or "{}"

    def tearDown(self):
        _mod.LOGD = self._logd
        _mod.prepare_wt = self._prepare_wt
        _mod.run_review_coverage = self._run_review_coverage
        _mod.gh = self._gh
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _pr(self, number=6400, updated="2026-10-25T10:00:00Z"):
        return {"number": number, "headRefOid": self.SHA, "baseRefName": "main",
                "title": "chore: promote develop to main", "isCrossRepository": False,
                "updatedAt": updated}

    def _log(self, number=6400, age_secs=0):
        p = os.path.join(self.tmp, f"pr{number}-review-{self.SHA[:12]}.log")
        with open(p, "w") as f:
            f.write("judged\n")
        old = time.time() - age_secs
        os.utime(p, (old, old))
        return p

    def test_the_queue_keys_on_the_judgement_log_not_a_status_row(self):
        pr = self._pr()
        self.assertEqual(_mod.pending_reviews([pr]), [pr],
                         "a head with no judgement log has not been judged")
        self._log()
        self.assertEqual(_mod.pending_reviews([pr]), [],
                         "a fresh judgement is evidence and satisfies the hourly re-check")

    def test_a_judgement_older_than_an_hour_is_rechecked(self):
        pr = self._pr()
        self._log(age_secs=_mod.REVIEW_RECHECK_SECS + 60)
        self.assertEqual(_mod.pending_reviews([pr]), [pr])

    def test_judging_a_promotion_posts_no_status(self):
        pr = self._pr()
        _mod.prepare_wt = lambda n, sha, base, out: (True, "ok")
        _mod.run_review_coverage = lambda p, out: (True, 3, 0)
        self.assertEqual(_mod.process_review(pr, dry=False), "success")
        self.assertEqual(self.gh_calls, [],
                         "the judgement is evidence: it must not publish a status row")
        self.assertTrue(os.path.exists(
            os.path.join(self.tmp, f"pr{pr['number']}-review-{self.SHA[:12]}.log")))

    def test_the_runner_names_no_second_producer(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("Every commit reaching main was reviewed", src,
                         "the workflow is the single producer of main's review context (DIG-4507)")
        self.assertNotIn("def review_status(", src)
        self.assertNotIn("def review_ci_status(", src)


class ProducerGuardTickTest(NoRealNetwork, unittest.TestCase):
    """DIG-4507: the tick asks the producer guard once, and survives its report.

    The guard's own `main()` prints UNREADABLE, but the daemon calls `run()`,
    so the per-tick call site owns the reporting. A tick that logged `ok` while
    the protection could not be read would be a silent pass: healthy-looking
    logs over a guard that cannot see. These tests pin the call itself, because
    deleting it would otherwise leave the suite green.
    """

    def setUp(self):
        self._isolate()
        self._saved = {}
        self.logs = []
        self._saved_env = dict(os.environ)
        os.environ["LOCAL_CI_MAIN"] = os.path.abspath(os.path.join(_HERE, "..", ".."))
        os.environ.pop("LOCAL_CI_WT", None)
        self._saved_argv = list(sys.argv)

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(_mod, name, value)
        sys.argv = self._saved_argv
        self._unisolate()

    def _stub(self, name, value):
        if name not in self._saved:
            self._saved[name] = getattr(_mod, name)
        setattr(_mod, name, value)

    def _run_tick(self):
        """main() with every side effect stubbed: only the guard stays real."""
        self._stub("_guard", lambda *a, **kw: None)
        self._stub("watchdog", lambda: None)
        self._stub("acquire_lock", lambda: True)
        self._stub("release_lock", lambda: None)
        self._stub("prune_claims", lambda: None)
        self._stub("refresh_checkout", lambda: None)
        self._stub("list_prs", lambda base: [])
        self._stub("skip_reason", lambda: None)
        self._stub("pending", lambda prs, applied, dry=False: [])
        self._stub("pending_applied", lambda prs: [])
        self._stub("pending_reviews", lambda prs: [])
        self._stub("log", lambda msg: self.logs.append(msg))
        self._stub("gh", lambda *a: None)          # protection unreadable
        sys.argv = ["local_ci.py"]
        stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            _mod.main()
        finally:
            sys.stdout = stdout

    def test_the_tick_asks_the_guard_once(self):
        calls = []
        self._stub("check_required_context_producers", lambda: calls.append(1))
        self._run_tick()
        self.assertEqual(calls, [1], "the tick must ask the guard exactly once")

    def test_an_unreadable_protection_is_reported_and_never_logged_ok(self):
        self._run_tick()
        self.assertTrue(any("UNREADABLE (not failed)" in m for m in self.logs), self.logs)
        self.assertFalse(any(m.startswith("required-context producers: ok") for m in self.logs),
                         self.logs)

    def test_a_guard_error_is_logged_and_never_raised(self):
        def boom(*a):
            raise RuntimeError("boom")
        self._stub("log", lambda msg: self.logs.append(msg))
        self._stub("gh", boom)
        _mod.check_required_context_producers()   # must not raise
        self.assertTrue(any("guard error" in m for m in self.logs), self.logs)


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
        self.assertIsNone(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])
        self.assertIn("app status: skipped, no app token", self.log_lines)

    def test_an_empty_token_file_posts_no_row(self):
        self._write_token("")
        self.assertIsNone(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])

    def test_a_whitespace_only_token_file_posts_no_row(self):
        self._write_token("   \n")
        self.assertIsNone(_mod.app_status("abc123", self._fields()))
        self.assertEqual(self.sh_calls, [])

    def test_a_token_file_that_cannot_be_read_posts_no_row(self):
        # A directory where the token file should be: the file cannot be read,
        # so there is no token, so there is no row.
        os.makedirs(_mod.APP_TOKEN_FILE, exist_ok=True)
        self.assertIsNone(_mod.app_status("abc123", self._fields()))
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

    def _status_calls(self, source=None):
        if source is None:
            with open(os.path.join(_SCRIPTS, "local_ci.py")) as f:
                source = f.read()
        tree = ast.parse(source)
        return [node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "status"]

    def _fork_calls(self, source=None):
        """The status calls that carry a fork's verdict.

        A fork site names the constant `FORK_DESC` or writes its text out. A
        check that only knows the name would miss the second form, and that
        site would ask for an app row on a head this repository does not have.
        """
        calls = []
        for call in self._status_calls(source):
            for arg in call.args:
                if isinstance(arg, ast.Name) and arg.id == "FORK_DESC":
                    calls.append(call)
                    break
                if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and _mod.FORK_DESC in arg.value):
                    calls.append(call)
                    break
        return calls

    def _fork_calls_without_the_app_row(self, source=None):
        out = []
        for call in self._fork_calls(source):
            app = [kw.value for kw in call.keywords if kw.arg == "app"]
            if (len(app) != 1 or not isinstance(app[0], ast.Constant)
                    or app[0].value is not False):
                out.append(call)
        return out

    def test_every_fork_status_call_posts_the_repo_row_alone(self):
        fork_calls = self._fork_calls()
        self.assertTrue(fork_calls, "the fork call sites must be found")
        self.assertEqual(self._fork_calls_without_the_app_row(), [])

    def test_a_fork_description_written_as_a_literal_is_also_caught(self):
        """A literal in place of the constant would hide the call site.

        The checker has to find both forms, and this proves it: a source that
        writes the description out is reported, so such a site cannot slip
        through unnoticed.
        """
        literal = ("def f(p):\n"
                   "    status(p, 'failure', %r)\n" % _mod.FORK_DESC)
        found = self._fork_calls(literal)
        self.assertEqual(len(found), 1,
                         "the checker must find a fork site that writes the text out")
        self.assertEqual(len(self._fork_calls_without_the_app_row(literal)), 1,
                         "a fork site without app=False must be reported")
        self.assertEqual(self._fork_calls_without_the_app_row(), [])


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

    def test_the_app_row_carries_the_token_in_the_child_environment(self):
        self._write_token(self.TOKEN)
        _mod.status("abc123", "success", "all gates passed")
        call = self._app_call()
        self.assertIsNotNone(call, "the app row must have been posted")
        self.assertEqual(call["env"]["GH_TOKEN"], self.TOKEN)
        self.assertEqual(call["env"]["GITHUB_TOKEN"], self.TOKEN)

    def test_the_child_state_record_carries_no_token(self):
        """The record the watchdog reads holds the command, not the token.

        The record is written by the real command runner, so the file is read
        in the moment it is written. A stubbed runner never writes it, and a
        test against a stub proves nothing about the record.
        """
        state = os.path.join(self._tmp, "child.json")
        saved_state = _mod.CHILD_STATE
        _mod.CHILD_STATE = state
        seen = {}
        original = _mod._write_child_state

        def spy(pid, name, budget):
            original(pid, name, budget)
            try:
                with open(state) as f:
                    seen["record"] = f.read()
            except OSError:
                seen["record"] = ""

        _mod._write_child_state = spy
        try:
            env = dict(os.environ)
            env["GH_TOKEN"] = self.TOKEN
            env["GITHUB_TOKEN"] = self.TOKEN
            rc, _ = self._saved_sh(["/bin/sh", "-c", "exit 0"], timeout=30, env=env)
        finally:
            _mod._write_child_state = original
            _mod.CHILD_STATE = saved_state
        self.assertEqual(rc, 0)
        self.assertIn("record", seen, "the child state record must have been written")
        self.assertNotIn(self.TOKEN, seen["record"])

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


class ClaimLedgerTest(NoRealNetwork, unittest.TestCase):
    """DIG-5135: a run that dies must not cost a PR its receipt for ever.

    A run posts a `pending` row before it starts the gates. When the run dies
    - the Mac sleeps, a gate takes the tick down, an installer boots the job
    out mid-run - the row stays and nobody queues the head again, so the PR
    sat blocked on a required check that never came. The ledger names the
    holder of every claim, so a head whose holder is gone is owed its receipt
    and is queued; a head whose holder is alive is left alone.
    """

    def setUp(self):
        self._isolate()
        self._claims = _mod.CLAIMS
        self._logd = _mod.LOGD
        self._gh = _mod.gh
        self._status = _mod.status
        self._app_status = _mod.app_status
        self._prepare_wt = _mod.prepare_wt
        self._run_checks = _mod.run_checks
        _mod.CLAIMS = os.path.join(self._tmp, "claims")
        _mod.LOGD = os.path.join(self._tmp, "logs")
        os.makedirs(_mod.LOGD, exist_ok=True)
        self.rows = {}      # sha -> list of status rows
        self.posts = []     # (sha, state, description)
        self.body = "Fixes DIG-5695\n<!-- test body -->\n"
        self.bodies = {}    # pr number -> body, when a test needs its own
        _mod.gh = self._fake_gh

    def tearDown(self):
        _mod.CLAIMS = self._claims
        _mod.LOGD = self._logd
        _mod.gh = self._gh
        _mod.status = self._status
        _mod.app_status = self._app_status
        _mod.prepare_wt = self._prepare_wt
        _mod.run_checks = self._run_checks
        self._unisolate()

    # --- fakes -------------------------------------------------------------

    def _fake_gh(self, *a):
        argv = list(a)
        url = [x for x in argv if x.startswith("repos/") and "/commits/" in x]
        if url:
            sha = url[0].split("/commits/")[1].split("/statuses")[0]
            return json.dumps(self.rows.get(sha, []))
        if argv[:2] == ["pr", "view"]:
            return self.bodies.get(argv[2], self.body)
        return "[]"

    def _row(self, state, desc, age_secs=0):
        ts = datetime.now(timezone.utc) - timedelta(seconds=age_secs)
        return {"context": _mod.CTX, "state": state, "description": desc,
                "created_at": ts.strftime("%Y-%m-%dT%H:%M:%SZ")}

    def _pr(self, number=6252, sha="aa11bb22cc33dd44ee55ff6677889900aabbccdd",
            updated="2026-10-20T10:00:00Z", created=None):
        return {"number": number, "headRefOid": sha, "headRefName": f"feat/{number}",
                "baseRefName": "develop", "title": "fix(x): something",
                "isCrossRepository": False, "updatedAt": updated,
                "createdAt": created or updated}

    def _stamp(self, offset_secs=0):
        """An ISO timestamp `offset_secs` from now, the shape GitHub returns."""
        ts = datetime.now(timezone.utc) + timedelta(seconds=offset_secs)
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _dead_pid(self):
        """A pid that is certainly gone: a process we started and reaped."""
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def _clock(self, offset):
        """Run the module's clock `offset` seconds ahead of the wall clock.

        The ageing rules are about how long a claim has been held, and a
        claim that is backdated names a pid the kernel has handed on - a
        different rule. Moving the clock keeps the two apart.
        """
        shim = _Clock(time.time() + offset)
        _mod.time = shim
        self.addCleanup(setattr, _mod, "time", time)
        return shim

    def _write_claim(self, sha, pid, pr=6252, started=None):
        os.makedirs(_mod.CLAIMS, exist_ok=True)
        with open(os.path.join(_mod.CLAIMS, sha), "w") as f:
            f.write(json.dumps({"pid": pid, "pr": pr,
                                "started": time.time() if started is None else started}))

    # --- the queue ---------------------------------------------------------

    def test_a_pending_row_whose_holder_is_gone_is_queued_again(self):
        """The run died: the head is owed a receipt."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("pending", "local-ci running on Chris's Mac")]
        self._write_claim(pr["headRefOid"], self._dead_pid())
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a claim whose holder is gone must be queued again")

    def test_a_pending_row_whose_holder_is_alive_is_left_alone(self):
        """The run is still working on it: a second run would collide.

        The row is older than the stale window on purpose. A row that is young
        would pass on the age rule alone, and the test would not pin the thing
        it names: a living holder keeps its head whatever age the row carries.
        """
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [
            self._row("pending", "local-ci running on Chris's Mac",
                      age_secs=_mod.CLAIM_STALE_SECS + 600)]
        _mod.write_claim(pr["headRefOid"], pr["number"])
        self.assertEqual(_mod.pending([pr], False), [],
                         "a claim whose holder is alive must not be queued again")

    def test_an_old_pending_row_with_no_ledger_entry_is_queued_again(self):
        """A row posted by a runner that predates the ledger is recovered too."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [
            self._row("pending", "local-ci running on Chris's Mac",
                      age_secs=_mod.CLAIM_STALE_SECS + 600)]
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a pending row nobody holds and that is old enough is lost")

    def test_a_young_pending_row_with_no_ledger_entry_is_left_alone(self):
        """No ledger entry and no age: the run may still be starting up."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [
            self._row("pending", "local-ci running on Chris's Mac", age_secs=60)]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a young pending row must not be taken over")

    def test_a_terminal_verdict_is_not_queued_again(self):
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-title (1m)")]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a red verdict the pull request has not outlived is the head's own answer")

    # --- metadata-only failures (DIG-5695) ---------------------------------

    def _judge(self, sha, revision):
        """Record a metadata revision the way a verdict does."""
        with open(os.path.join(_mod.LOGD, f"metadata-recheck-{sha}"), "w") as f:
            f.write(revision + "\n")

    def test_a_metadata_failure_re_queues_when_the_title_or_body_was_fixed(self):
        """The remedy for a metadata gate does not touch the tree (PR #6513).

        The author corrected the title and the body after the row went out, so
        the same head is worth one more look. No commit, and no review becomes
        stale for it.
        """
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [
            self._row("failure", "local-ci failed: pr-title, pr-template (1m)", age_secs=300)]
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a corrected title or body must re-check the same head")

    def test_the_judged_metadata_is_not_re_queued_again(self):
        """One re-check per change, not one per tick."""
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-title (1m)",
                                                 age_secs=300)]
        self._judge(pr["headRefOid"], _mod.metadata_revision(pr["title"], self.body))
        self.assertEqual(_mod.pending([pr], False), [],
                         "the metadata already judged must not queue the head again")

    def test_a_metadata_edit_after_the_judged_revision_re_queues(self):
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-template (1m)",
                                                 age_secs=300)]
        self._judge(pr["headRefOid"], "0000000000000000")
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a revision the gates have not judged is worth a look")

    def test_the_revision_covers_the_body_and_the_title(self):
        """The digest must tell a corrected title or body from the same one.

        This is the part the rule turns on: a digest that ignores the body does
        not re-queue the `pr-template` fix, and a constant digest never re-queues
        anything after the first verdict. Both are asserted here directly, so a
        later edit to `metadata_revision` cannot quietly take either shape.
        """
        self.assertNotEqual(_mod.metadata_revision("fix(x): a", "body one"),
                            _mod.metadata_revision("fix(x): a", "body two"),
                            "the digest must change with the body")
        self.assertNotEqual(_mod.metadata_revision("fix(x): a", "same"),
                            _mod.metadata_revision("fix(y): b", "same"),
                            "the digest must change with the title")

    def test_a_body_only_correction_re_queues_a_judged_head(self):
        """The body is the remedy for `pr-template` (PR #6513): it must re-queue."""
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [
            self._row("failure", "local-ci failed: pr-template (1m)", age_secs=300)]
        self._judge(pr["headRefOid"], _mod.metadata_revision(pr["title"], self.body))
        self.bodies[str(pr["number"])] = (
            self.body + "\n## Testing Evidence\n```\nfixed\n```\n")
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a body-only correction must re-check the same head")

    def test_a_title_only_correction_re_queues_a_judged_head(self):
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-title (1m)",
                                                 age_secs=300)]
        self._judge(pr["headRefOid"], _mod.metadata_revision(pr["title"], self.body))
        pr["title"] = "fix(x): the corrected title"
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a title-only correction must re-check the same head")

    def test_a_metadata_failure_the_pull_request_has_not_outlived_is_left_alone(self):
        """No recorded revision and no edit after the row: nothing to re-check."""
        pr = self._pr(updated=self._stamp(-600))
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-title (1m)",
                                                 age_secs=60)]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a row younger than every edit is the head's own answer")

    def test_a_code_failure_is_never_re_queued(self):
        """A code gate's remedy is a commit, so its row stays terminal."""
        pr = self._pr(updated=self._stamp(-60))
        for desc in ("local-ci failed: ruff (1m)",
                     "local-ci failed: pr-title, ruff (1m)",
                     "local-ci failed: pr-template, bun:digichat-tui (1m)"):
            self.rows[pr["headRefOid"]] = [self._row("failure", desc, age_secs=300)]
            self.assertEqual(_mod.pending([pr], False), [],
                             f"a code failure must stay terminal: {desc!r}")

    def test_a_missing_pr_template_checker_is_not_a_metadata_failure(self):
        """A runner defect must not buy a lane on every metadata edit."""
        pr = self._pr(updated=self._stamp(-60))
        desc = "local-ci failed: pr-template:checker-missing (0m)"
        self.rows[pr["headRefOid"]] = [self._row("failure", desc, age_secs=300)]
        self.assertIsNone(_mod.metadata_failure_gates(desc))
        self.assertEqual(_mod.pending([pr], False), [],
                         "a missing checker module is not author metadata")

    def test_a_stalled_metadata_gate_is_not_re_queued(self):
        """A stall names no plain gate: it is a code verdict about the runner."""
        pr = self._pr(updated=self._stamp(-60))
        self.rows[pr["headRefOid"]] = [
            self._row("failure", "local-ci failed: pr-template exceeded 1800s and was killed (30m)",
                      age_secs=300)]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a stall must not be mistaken for a metadata failure")

    def test_a_metadata_verdict_records_the_revision_the_gates_judged(self):
        """The queue must be able to tell a fixed title or body from the same one."""
        pr = self._pr()
        self._run_process(pr, fails=["pr-title"], revision="0123456789abcdef")
        path = os.path.join(_mod.LOGD, f"metadata-recheck-{pr['headRefOid']}")
        with open(path) as f:
            self.assertEqual(f.read().strip(), "0123456789abcdef",
                             "the verdict must record the metadata it judged")

    def test_a_code_verdict_records_no_metadata_revision(self):
        pr = self._pr()
        self._run_process(pr, fails=["ruff"], revision="0123456789abcdef")
        self.assertFalse(os.path.exists(
            os.path.join(_mod.LOGD, f"metadata-recheck-{pr['headRefOid']}")),
            "a code verdict is terminal and must record no metadata revision")

    def test_a_head_with_no_row_at_all_is_queued(self):
        pr = self._pr()
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]])

    def test_the_queue_is_oldest_first(self):
        """The head that has waited longest is served first (DIG-5135).

        The queue used to be newest-first, so a PR that arrived early sat
        behind every later arrival and could wait for days for a required
        check.
        """
        old = self._pr(number=1, sha="0" * 40, updated="2026-10-01T10:00:00Z")
        mid = self._pr(number=2, sha="1" * 40, updated="2026-10-10T10:00:00Z")
        new = self._pr(number=3, sha="2" * 40, updated="2026-10-20T10:00:00Z")
        order = [p["number"] for p in _mod.pending([new, mid, old], False)]
        self.assertEqual(order, [1, 2, 3], "the queue must be oldest first")

    def test_two_heads_updated_at_the_same_moment_are_ordered_by_number(self):
        a = self._pr(number=7, sha="3" * 40, updated="2026-10-20T10:00:00Z")
        b = self._pr(number=8, sha="4" * 40, updated="2026-10-20T10:00:00Z")
        order = [p["number"] for p in _mod.pending([b, a], False)]
        self.assertEqual(order, [7, 8], "the tie-break must be the PR number")

    # --- the runner takes and releases the claim ----------------------------

    def _run_process(self, pr, verdict_posts=True, fails=(), revision=None):
        """Run process() with the gates stubbed out; record what was posted."""
        self.posts = []
        seen = {}

        def fake_status(sha, state, desc, app=True):
            self.posts.append((sha, state, desc))
            if state == "pending":
                seen["claim_at_pending"] = os.path.exists(os.path.join(_mod.CLAIMS, sha))
            if state != "pending" and not verdict_posts:
                return False
            return True

        def fake_run_checks(pr, out, summary=None):
            if summary is not None and revision is not None:
                summary["metadata_revision"] = revision
            return list(fails)

        _mod.status = fake_status
        _mod.prepare_wt = lambda n, sha, base, out: (True, "")
        _mod.run_checks = fake_run_checks
        _mod.process(pr, False)
        return seen

    def test_the_claim_is_taken_before_the_pending_row_and_released_after_the_verdict(self):
        pr = self._pr()
        seen = self._run_process(pr)
        self.assertTrue(seen.get("claim_at_pending"),
                        "the claim must be taken before the pending row goes out")
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                         "the claim is spent once the verdict is posted")

    def test_a_claim_survives_a_verdict_that_could_not_be_posted(self):
        """A head with no verdict is owed a receipt, so the claim stays."""
        pr = self._pr()
        self._run_process(pr, verdict_posts=False)
        self.assertTrue(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                        "a verdict that could not be posted must leave the claim in place")

    # --- the ledger, in detail ----------------------------------------------

    def test_a_live_holder_keeps_its_head_however_old_the_row_is(self):
        """A run that takes longer than the stale window is still in flight."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [
            self._row("pending", "local-ci running on Chris's Mac",
                      age_secs=_mod.CLAIM_STALE_SECS + 600)]
        _mod.write_claim(pr["headRefOid"], pr["number"])
        self.assertEqual(_mod.pending([pr], False), [],
                         "a living holder keeps its head, whatever age the row carries")

    def test_a_live_claim_with_no_row_at_all_is_left_alone(self):
        """The row never went out: the run is still working on the head."""
        pr = self._pr()
        _mod.write_claim(pr["headRefOid"], pr["number"])
        self.assertEqual(_mod.pending([pr], False), [],
                         "a head whose claim is held by a living run is not queued")

    def test_a_claim_older_than_the_worst_case_run_is_lost(self):
        """A claim held past the worst case of a gate run names a run nobody waits for.

        The clock runs ahead instead of the claim being backdated: a claim
        written in the past names a pid the kernel has handed on, which is a
        different rule. Only the age of the claim itself can make this head
        lose its place.
        """
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("pending", "local-ci running on Chris's Mac")]
        self._write_claim(pr["headRefOid"], os.getpid(), started=time.time())
        self._clock(_mod.CLAIM_MAX_SECS + 60)
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a claim past the worst case of a run is lost")

    def test_a_claim_outlives_the_tick_lock(self):
        """The claim is void later than the lock, so a live run keeps its head.

        The tick lock is taken over after two hours, the claim after the worst
        case of a gate run. If the claim were void first, a tick that took
        over a stale lock would hand a live run's head to a second run, and
        two producers would write two `local-ci` rows on one head.
        """
        self.assertGreater(_mod.CLAIM_MAX_SECS, _mod.LOCK_MAX_AGE,
                           "a claim must outlive the tick lock")

    def test_a_claim_whose_pid_was_reused_is_lost(self):
        """The pid the claim names belongs to another process now."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("pending", "local-ci running on Chris's Mac")]
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(1.2)      # let the process show up in the process table
            # The claim was written before this process started: the pid was reused.
            self._write_claim(pr["headRefOid"], p.pid, started=time.time() - 600)
            self.assertEqual([q["number"] for q in _mod.pending([pr], False)], [pr["number"]],
                             "a claim whose pid was reused must not hold the head")
        finally:
            p.kill()
            p.wait()

    def test_the_pid_check_asks_the_system_ps_and_not_the_one_on_the_path(self):
        """A `ps` that somebody put first on the PATH must not decide whose run this is.

        launch_guard.py answers the same question the same way, for the same
        reason: a wrong answer there lets a hand-run post a receipt, and a
        wrong answer here lets a fake `ps` hold a head or release one.
        """
        seen = []
        real_run = _mod.subprocess.run

        def fake_run(cmd, *a, **kw):
            seen.append(list(cmd))
            return real_run(cmd, *a, **kw)

        pr = self._pr()
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            time.sleep(1.2)
            self._write_claim(pr["headRefOid"], p.pid, started=time.time() - 600)
            _mod.subprocess.run = fake_run
            try:
                _mod.holder_is_the_run(pr["headRefOid"], p.pid)
            finally:
                _mod.subprocess.run = real_run
        finally:
            p.kill()
            p.wait()
        self.assertTrue(seen, "the pid check must ask the process table")
        self.assertEqual(seen[0][0], "/bin/ps",
                         "the pid check must use the system ps, not the one on the PATH")

    def test_a_terminal_verdict_does_not_release_a_live_claim(self):
        """The queue is not the owner of the claim and must not release it."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("failure", "local-ci failed: pr-title (1m)")]
        _mod.write_claim(pr["headRefOid"], pr["number"])
        _mod.pending([pr], False)
        self.assertTrue(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                        "the claim of a living run is not the queue's to release")

    def test_a_spent_claim_is_released_when_the_verdict_is_in(self):
        """The run is gone and the verdict is in: the claim is spent."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("success", "all gates passed")]
        self._write_claim(pr["headRefOid"], self._dead_pid())
        _mod.pending([pr], False)
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                         "a claim whose holder is gone and whose verdict is in is spent")

    def test_a_row_without_a_readable_timestamp_is_not_treated_as_old(self):
        """An unknown timestamp is not an old one: no hot loop."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [{"context": _mod.CTX, "state": "pending",
                                        "description": "local-ci running on Chris's Mac",
                                        "created_at": None}]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a row nobody can date is left alone")

    def test_prune_claims_drops_a_dead_claim_and_keeps_a_live_one(self):
        dead = self._pr(sha="0" * 40)["headRefOid"]
        live = self._pr(sha="1" * 40)["headRefOid"]
        self._write_claim(dead, self._dead_pid())
        self._write_claim(live, os.getpid())
        old = time.time() - 90000
        for sha in (dead, live):
            os.utime(os.path.join(_mod.CLAIMS, sha), (old, old))
        _mod.prune_claims()
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, dead)),
                         "a dead claim nothing touched for a day is dropped")
        self.assertTrue(os.path.exists(os.path.join(_mod.CLAIMS, live)),
                        "a live claim is never dropped")

    def test_prune_claims_drops_a_claim_it_cannot_read(self):
        """A claim file that is not JSON is not a claim anybody holds."""
        sha = self._pr(sha="2" * 40)["headRefOid"]
        os.makedirs(_mod.CLAIMS, exist_ok=True)
        path = os.path.join(_mod.CLAIMS, sha)
        with open(path, "w") as f:
            f.write("{this is not json")
        old = time.time() - 90000
        os.utime(path, (old, old))
        _mod.prune_claims()
        self.assertFalse(os.path.exists(path),
                         "a claim nobody can read and that nothing touched for a day is dropped")

    def test_prune_claims_keeps_a_file_that_is_not_a_claim(self):
        """Only a claim file is the ledger's to drop."""
        os.makedirs(_mod.CLAIMS, exist_ok=True)
        path = os.path.join(_mod.CLAIMS, "notes.txt")
        with open(path, "w") as f:
            f.write("not a claim\n")
        old = time.time() - 90000
        os.utime(path, (old, old))
        _mod.prune_claims()
        self.assertTrue(os.path.exists(path),
                        "a file that is not a claim is not the ledger's to drop")

    def test_a_claim_named_for_something_that_is_not_a_sha_is_refused(self):
        """A name that is not a head sha would write outside the ledger."""
        self.assertIsNone(_mod.claim_path("not-a-sha"),
                          "a name that is not a sha has no place in the ledger")
        _mod.write_claim("not-a-sha", 6252)
        self.assertEqual(os.listdir(_mod.CLAIMS) if os.path.isdir(_mod.CLAIMS) else [],
                         [], "a claim for a name that is not a sha must not be written")

    def test_a_claim_that_cannot_be_moved_into_place_leaves_no_claim(self):
        """The claim is written to a temporary name and moved into place.

        A write that is cut in half leaves a claim file nobody can read, and
        the head then waits for the stale window instead of being recovered.
        """
        sha = self._pr()["headRefOid"]
        _mod.os = _NoReplace()
        self.addCleanup(setattr, _mod, "os", os)
        _mod.write_claim(sha, 6252)
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, sha)),
                         "a claim that could not be moved into place must not exist")
        self.assertEqual([n for n in os.listdir(_mod.CLAIMS) if n.endswith(".tmp")], [],
                         "a failed claim write must not leave a temporary file behind")

    def test_a_refused_app_row_does_not_hold_the_head(self):
        """The app row is a second context; the required check is the repo row."""
        pr = self._pr()
        _mod.app_status = lambda sha, fields: False
        self.addCleanup(setattr, _mod, "app_status", self._app_status)
        self.assertTrue(_mod.status(pr["headRefOid"], "success", "all gates passed"),
                        "a refused app row must not take the repo row down with it")

    def test_a_refused_app_row_releases_the_claim(self):
        """The head earned its receipt on the required context: the claim is spent."""
        pr = self._pr()
        _mod.app_status = lambda sha, fields: False
        self.addCleanup(setattr, _mod, "app_status", self._app_status)
        _mod.prepare_wt = lambda n, sha, base, out: (True, "")
        _mod.run_checks = lambda pr, out, summary=None: []
        _mod.process(pr, False)
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                         "a refused app row must not keep a head in the queue for ever")

    def test_a_row_that_says_the_post_failed_is_queued_again(self):
        """An `error` row is not a verdict: the head is owed its receipt."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("error", "could not post the row")]
        self._write_claim(pr["headRefOid"], self._dead_pid())
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a row that says the post failed must be queued again")
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                         "the claim of a head whose row failed is spent")

    # --- the ledger ---------------------------------------------------------

    def test_a_dry_run_does_not_release_a_claim(self):
        """A preview changes nothing: not even the ledger."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("success", "all gates passed")]
        self._write_claim(pr["headRefOid"], self._dead_pid())
        _mod.pending([pr], False, dry=True)
        self.assertTrue(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                        "a dry run must not release a claim")

    def test_a_spent_claim_is_released_when_the_queue_sees_the_verdict(self):
        """The queue releases a claim nobody holds any more."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("success", "all gates passed")]
        self._write_claim(pr["headRefOid"], self._dead_pid())
        _mod.pending([pr], False)
        self.assertFalse(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                         "a claim whose holder is gone is spent once the verdict is in")

    def test_a_taken_over_run_does_not_release_the_new_holder_s_claim(self):
        """The run that was replaced must not delete the claim of the run that replaced it."""
        pr = self._pr()
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(holder.kill)
        os.makedirs(_mod.CLAIMS, exist_ok=True)
        with open(os.path.join(_mod.CLAIMS, pr["headRefOid"]), "w") as f:
            f.write(json.dumps({"pid": holder.pid, "pr": pr["number"],
                                "started": time.time()}))
        _mod.clear_claim(pr["headRefOid"])
        self.assertTrue(os.path.exists(os.path.join(_mod.CLAIMS, pr["headRefOid"])),
                        "a claim a living run holds is that run's to release")

    @unittest.skipUnless(hasattr(os, "fork"), "a zombie needs a POSIX fork")
    def test_a_claim_held_by_a_zombie_is_lost(self):
        """A process that has exited and is not reaped is not running the gate."""
        pr = self._pr()
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        self.addCleanup(self._reap, pid)
        self._wait_for_zombie(pid)
        self.rows[pr["headRefOid"]] = [self._row("pending", "local-ci running on Chris's Mac")]
        self._write_claim(pr["headRefOid"], pid)
        self.assertEqual([p["number"] for p in _mod.pending([pr], False)], [pr["number"]],
                         "a claim held by a zombie must go back to the queue")

    def _reap(self, pid):
        try:
            os.waitpid(pid, os.WNOHANG)
        except OSError:
            pass

    def _wait_for_zombie(self, pid, timeout=5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            out = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)],
                                 capture_output=True, text=True).stdout.strip()
            if out.startswith("Z"):
                return True
            time.sleep(0.05)
        return False

    def test_a_pending_row_inside_the_slowest_gate_is_left_alone(self):
        """A producer may still be gating 4.7 h into a run: the head is not taken."""
        pr = self._pr()
        self.rows[pr["headRefOid"]] = [self._row("pending", "local-ci running on Chris's Mac",
                                                  age_secs=17000)]
        self.assertEqual(_mod.pending([pr], False), [],
                         "a row inside the slowest gate must not be taken away")

    def test_an_explicit_run_does_not_start_on_a_head_another_run_holds(self):
        """Two runs on one head post two rows on the required check."""
        pr = self._pr(number=6262)
        holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(holder.kill)
        self._write_claim(pr["headRefOid"], holder.pid)
        ran = []
        process, applied, gh = _mod.process, _mod.process_applied, _mod.gh
        self.addCleanup(setattr, _mod, "process", process)
        self.addCleanup(setattr, _mod, "process_applied", applied)
        self.addCleanup(setattr, _mod, "gh", gh)

        def fake_gh(*a):
            return json.dumps(pr) if "view" in list(a) else "[]"

        _mod.gh = fake_gh
        _mod.process = lambda p, dry: ran.append(p) or "success"
        _mod.process_applied = lambda p, dry: None
        _mod.explicit_run(pr["number"], False)
        self.assertEqual(ran, [], "an explicit run must not start on a head another run holds")

    def test_prune_claims_drops_a_stale_temporary_file(self):
        """A run killed between the write and the move leaves a file behind."""
        os.makedirs(_mod.CLAIMS, exist_ok=True)
        tmp = os.path.join(_mod.CLAIMS, "a" * 40 + ".1234.tmp")
        with open(tmp, "w") as f:
            f.write("{}")
        old = time.time() - 7200
        os.utime(tmp, (old, old))
        _mod.prune_claims()
        self.assertFalse(os.path.exists(tmp), "a stale temporary claim must be dropped")

    def test_the_review_applied_queue_is_ordered_by_arrival(self):
        """The review-applied lane is served oldest first as well."""
        old = self._pr(number=1, sha="0" * 40, created="2026-10-01T10:00:00Z",
                       updated="2026-10-01T10:00:00Z")
        new = self._pr(number=2, sha="1" * 40, created="2026-10-20T10:00:00Z",
                       updated="2026-10-20T10:00:00Z")
        # The row has to be old enough for the re-check rule, and "old enough"
        # is measured against the clock of the machine that runs the test: a
        # fixed date makes the test fail on a clock that lags behind it.
        aged = (datetime.now(timezone.utc)
                - timedelta(seconds=_mod.REVIEW_RECHECK_SECS + 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for pr in (old, new):
            pr["_head_reviewed"] = True  # both heads carry a review
            self.rows[pr["headRefOid"]] = [
                {"context": "review-applied", "state": "failure",
                 "description": "review-applied: no review pass left comments",
                 "created_at": aged}]
        self.assertEqual([p["number"] for p in _mod.pending_applied([new, old])], [1, 2],
                         "the review-applied lane is served in arrival order")

    # --- review-applied waits for a review (plan P1-3) -----------------------

    def _with_reviews(self, reviews):
        """Answer the review read for every PR with ``reviews`` (None: unreadable)."""
        gh = _mod.gh
        self.addCleanup(setattr, _mod, "gh", gh)

        def fake(*a):
            argv = list(a)
            if any("/reviews" in x for x in argv):
                return "" if reviews is None else json.dumps(reviews)
            if any("/issues/" in x and "/comments" in x for x in argv):
                return "" if reviews is None else "[]"
            return gh(*a)
        _mod.gh = fake

    def test_an_unreviewed_head_is_not_queued_for_review_applied(self):
        self._with_reviews([])
        self.assertEqual(_mod.pending_applied([self._pr(number=7)]), [],
                         "no review of the head: review-applied posts nothing")

    def test_a_reviewed_head_is_queued_for_review_applied(self):
        pr = self._pr(number=7)
        self._with_reviews([{"state": "APPROVED", "commit_id": pr["headRefOid"],
                             "user": {"login": "reviewer"}, "body": ""}])
        self.assertEqual([p["number"] for p in _mod.pending_applied([pr])], [7])

    def test_a_review_of_an_earlier_head_does_not_queue_the_new_one(self):
        self._with_reviews([{"state": "APPROVED", "commit_id": "f" * 40,
                             "user": {"login": "reviewer"}, "body": ""}])
        self.assertEqual(_mod.pending_applied([self._pr(number=7)]), [])

    def test_an_unreadable_review_record_is_still_checked(self):
        """Unreadable is not "no review": the run fails closed with the reason."""
        self._with_reviews(None)
        self.assertEqual([p["number"] for p in _mod.pending_applied([self._pr(number=7)])], [7])

    def test_the_skip_path_posts_nothing_on_an_unreviewed_head(self):
        """main() posts "local-ci skipped" only to heads pending_applied returns."""
        self._with_reviews([])
        posted = []
        applied_status = _mod.applied_status
        self.addCleanup(setattr, _mod, "applied_status", applied_status)
        _mod.applied_status = lambda sha, st, desc: posted.append((sha, st))
        for p in _mod.pending_applied([self._pr(number=7)]):
            _mod.applied_status(p["headRefOid"], "failure", "local-ci skipped: x")
        self.assertEqual(posted, [])

    def test_process_applied_posts_no_row_before_a_review(self):
        self._with_reviews([])
        posted = []
        applied_status = _mod.applied_status
        self.addCleanup(setattr, _mod, "applied_status", applied_status)
        _mod.applied_status = lambda sha, st, desc: posted.append((sha, st))
        self.assertEqual(_mod.process_applied(self._pr(number=7), False), "skipped")
        self.assertEqual(posted, [], "not pending, not failure: no row at all")

    # --- the order ----------------------------------------------------------

    def test_the_queue_is_ordered_by_arrival_and_not_by_last_activity(self):
        """A PR that is commented on is not pushed back to the end."""
        old = self._pr(number=1, sha="0" * 40, created="2026-10-01T10:00:00Z",
                       updated="2026-10-01T10:00:00Z")
        new = self._pr(number=2, sha="1" * 40, created="2026-10-20T10:00:00Z",
                       updated="2026-10-21T10:00:00Z")
        order = [p["number"] for p in _mod.pending([new, old], False)]
        self.assertEqual(order, [1, 2], "the order must be by arrival, not by last activity")


class RefreshCheckoutTest(NoRealNetwork, unittest.TestCase):
    """DIG-5135: the runner must post receipts from the code it should post them from.

    The daemon runs from its own checkout. A checkout left on an old commit
    produces old receipts, so the runner refreshes it - but only a real clone,
    only the `develop` branch, and only when the update is a fast-forward.
    """

    def setUp(self):
        self._isolate()
        self._main = _mod.MAIN
        self._refresh_state = _mod.REFRESH_STATE
        self._runner_marker = _mod.RUNNER_MARKER
        self._sh = _mod.sh
        _mod.MAIN = os.path.join(self._tmp, "main")
        _mod.REFRESH_STATE = os.path.join(self._tmp, "state", "refresh")
        _mod.RUNNER_MARKER = os.path.join(self._tmp, "state", "runner.json")
        self.cmds = []
        self.timeouts = []
        self.results = {}
        # The guard is read with the same git command as the runner, and it has
        # to answer for itself: a guard without the interface the runner calls
        # would stop the only producer of the receipt. The key names the whole
        # command, so the cat-file check for the same file still answers for
        # itself.
        self.results["show FETCH_HEAD:scripts/local-ci/launch_guard.py"] = (
            0, "def enforce(runner_path, ctx, facts=None):\n    return True\n")
        _mod.sh = self._fake_sh

    def tearDown(self):
        _mod.MAIN = self._main
        _mod.REFRESH_STATE = self._refresh_state
        _mod.RUNNER_MARKER = self._runner_marker
        _mod.sh = self._sh
        self._unisolate()

    # --- fakes -------------------------------------------------------------

    def _fake_sh(self, cmd, cwd=None, timeout=1800, out=None, name=None, env=None):
        cmd = list(cmd)
        self.cmds.append(cmd)
        self.timeouts.append(timeout)
        joined = " ".join(cmd)
        # The most specific key wins: the guard and the runner are read with
        # the same git command, and each needs its own answer.
        for key in sorted(self.results, key=len, reverse=True):
            if key in joined:
                return self.results[key]
        return (0, "")

    def _clone(self):
        """A checkout that looks like a clone: `.git` is a directory."""
        os.makedirs(os.path.join(_mod.MAIN, ".git"), exist_ok=True)

    def _linked_worktree(self):
        """A checkout that is a linked worktree: `.git` is a file."""
        os.makedirs(_mod.MAIN, exist_ok=True)
        with open(os.path.join(_mod.MAIN, ".git"), "w") as f:
            f.write("gitdir: /Users/somebody/else/.git/worktrees/x\n")

    def _ran(self, needle):
        return [c for c in self.cmds if needle in " ".join(c)]

    def _mark_runner(self, main=None, self_update=True):
        """Write the marker install.sh writes: the runner's own checkout."""
        os.makedirs(os.path.dirname(_mod.RUNNER_MARKER), exist_ok=True)
        with open(_mod.RUNNER_MARKER, "w") as f:
            json.dump({"main": main or _mod.MAIN, "self_update": self_update}, f)

    def _runner_source(self, text="def main():\n    pass\n"):
        return (0, text)

    # --- the tests ----------------------------------------------------------

    def test_a_checkout_that_is_not_marked_is_never_touched(self):
        """The runner moves only the checkout the operator marked as its own.

        `MAIN` may point at somebody's working tree, and the runner has no
        business moving a working tree.
        """
        self._clone()
        self.results["rev-parse"] = (0, "develop\n")
        _mod.refresh_checkout()
        self.assertEqual(self.cmds, [], "a checkout nobody marked must not be touched")
        self.assertTrue(any("not marked" in line for line in self.log_lines),
                        "the runner must say that it is running the commit it was installed on")

    def test_a_marker_that_names_another_checkout_is_not_touched(self):
        """The marker names one checkout: a different one is somebody else's."""
        self._clone()
        self._mark_runner(main=os.path.join(self._tmp, "somewhere-else"))
        self.results["rev-parse"] = (0, "develop\n")
        _mod.refresh_checkout()
        self.assertEqual(self.cmds, [], "a checkout the marker does not name must not be touched")

    def test_a_marker_that_forbids_the_update_is_not_touched(self):
        """A linked worktree is installed with the update turned off."""
        self._clone()
        self._mark_runner(self_update=False)
        self.results["rev-parse"] = (0, "develop\n")
        _mod.refresh_checkout()
        self.assertEqual(self.cmds, [], "a checkout the marker forbids is not moved")

    def test_a_linked_worktree_is_never_refreshed(self):
        """That is somebody else's checkout: it is not ours to move."""
        self._linked_worktree()
        self._mark_runner()
        _mod.refresh_checkout()
        self.assertEqual(self.cmds, [], "a linked worktree must not be touched at all")
        self.assertTrue(any("not a clone" in line for line in self.log_lines),
                        "the runner must say that it is running an old commit")

    def test_a_checkout_that_is_not_on_develop_is_left_alone(self):
        """The refresh only ever moves the develop branch."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "feature-x\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("fetch"), [], "a checkout on another branch is not fetched")
        self.assertTrue(any("not develop" in line for line in self.log_lines),
                        "the runner must say that the checkout is on another branch")

    def test_a_clone_on_develop_is_fast_forwarded(self):
        """The checkout is brought to origin/develop, and the window is recorded."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        _mod.refresh_checkout()
        self.assertEqual(len(self._ran("fetch")), 1, "the clone must be fetched")
        self.assertEqual(len(self._ran("merge")), 1, "the clone must be fast-forwarded")
        self.assertTrue(os.path.exists(_mod.REFRESH_STATE),
                        "a successful refresh records that the next one waits its turn")

    def test_a_checkout_that_does_not_fast_forward_is_left_alone(self):
        """A local commit or an overlapping dirty file: the checkout stays."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        self.results["merge"] = (1, "not possible\n")
        _mod.refresh_checkout()
        self.assertEqual(len(self._ran("merge")), 1, "the merge must be tried")
        self.assertTrue(os.path.exists(_mod.REFRESH_STATE),
                        "a refused merge consumes the window: the refresh holds the tick "
                        "lock, so it is not tried again on every tick")

    def test_a_fetch_that_fails_leaves_the_checkout_alone(self):
        """No network, no update: the runner keeps the checkout it has."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["fetch"] = (1, "could not resolve host\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("merge"), [], "a failed fetch must not merge anything")
        self.assertTrue(os.path.exists(_mod.REFRESH_STATE),
                        "a failed fetch consumes the window: a fetch that always fails "
                        "would otherwise run on every tick and hold the tick lock")

    def test_a_fetch_that_always_fails_is_not_retried_on_the_next_tick(self):
        """The throttle is what stops a broken fetch from eating the producer."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["fetch"] = (1, "could not resolve host\n")
        _mod.refresh_checkout()
        self.assertEqual(len(self._ran("fetch")), 1, "the first attempt fetches")
        _mod.refresh_checkout()
        self.assertEqual(len(self._ran("fetch")), 1,
                         "the second tick must wait for the window, not fetch again")

    def test_an_incoming_runner_that_does_not_compile_is_not_merged(self):
        """The runner is the only producer of the receipt: it may not be broken."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = (0, "def main(:\n    pass\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("merge"), [], "a runner that does not compile is not merged in")
        self.assertTrue(os.path.exists(_mod.REFRESH_STATE),
                        "a refused update consumes the window: the next tick retries it")

    def test_a_guard_the_runner_cannot_call_is_not_merged(self):
        """The runner refuses to run without a guard it can call."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        self.results["show FETCH_HEAD:scripts/local-ci/launch_guard.py"] = (
            0, "def enforce(ctx):\n    return True\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("merge"), [],
                         "a guard without the runner's interface is not merged in")

    def test_a_guard_that_only_names_the_interface_in_a_comment_is_not_merged(self):
        """A comment is not an interface.

        The runner calls `enforce(runner_path, ctx)`. A guard whose source
        mentions that signature in a comment but whose callable takes
        something else would pass a text search and raise a TypeError on the
        next tick, so the check has to read the function, not the text.
        """
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        self.results["show FETCH_HEAD:scripts/local-ci/launch_guard.py"] = (
            0, "# old interface: def enforce(runner_path, ctx)\n"
               "def enforce(ctx):\n    return True\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("merge"), [],
                         "a guard that only names the interface in a comment is not merged in")

    def test_an_incoming_commit_without_a_launch_guard_is_not_merged(self):
        """Without the guard the next tick would post receipts unchallenged."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        self.results["cat-file"] = (1, "not found\n")
        _mod.refresh_checkout()
        self.assertEqual(self._ran("merge"), [], "a commit without a guard is not merged in")

    def test_the_refresh_git_commands_are_bounded(self):
        """A hung fetch must not hold the tick lock for half an hour."""
        self._clone()
        self._mark_runner()
        self.results["rev-parse"] = (0, "develop\n")
        self.results["show"] = self._runner_source()
        _mod.refresh_checkout()
        for cmd, timeout in zip(self.cmds, self.timeouts):
            if "fetch" in " ".join(cmd) or "merge" in " ".join(cmd):
                self.assertLessEqual(timeout, 600,
                                     "the refresh's git commands must not wait for ever")


class LockHeartbeatTest(unittest.TestCase):
    """DIG-5135: a working tick must not be killed as a wedge.

    The host's liveness supervisor (com.digithings.daemon-liveness) reads the
    mtime of the tick lock directory and kills a live holder that has held it
    for 1800 s. A tick that gates one PR runs far longer than that - the
    runner's own step timeouts sum to about 17100 s - so the supervisor killed
    healthy runners mid-run. Measured on 2026-10-22: five kills between 05:39
    and 08:01, each one a receipt that never landed and a PR that lost its
    required check. The runner renews the lock while it works, so a working
    tick stays fresh and a runner that has really wedged stops renewing and is
    killed exactly as before.
    """

    # The rule the supervisor applies, named here so the test measures the same
    # thing the host measures: the age of the lock directory.
    SUPERVISOR_MAX_HOLDER_SECS = 1800

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._lock = _mod.LOCK
        self._logd = _mod.LOGD
        self._interval = _mod.LOCK_HEARTBEAT_SECS
        _mod.LOCK = os.path.join(self.tmp, "local-ci.lock")
        _mod.LOGD = os.path.join(self.tmp, "logs")
        os.makedirs(_mod.LOGD, exist_ok=True)
        _mod.LOCK_HEARTBEAT_SECS = 0.05

    def tearDown(self):
        _mod._stop_lock_heartbeat()
        _mod.LOCK = self._lock
        _mod.LOGD = self._logd
        _mod.LOCK_HEARTBEAT_SECS = self._interval
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers -----------------------------------------------------------

    def _make_lock(self, pid=None):
        """A lock directory held by `pid` (this process by default)."""
        os.makedirs(_mod.LOCK, exist_ok=True)
        with open(os.path.join(_mod.LOCK, "pid"), "w") as f:
            f.write(str(os.getpid() if pid is None else pid))
        return os.stat(_mod.LOCK).st_ino

    def _dead_pid(self):
        """A pid that is certainly gone: a process we started and reaped."""
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        return p.pid

    def _supervisor_age(self):
        """The age the host's supervisor reads: the mtime of the lock directory."""
        return time.time() - os.path.getmtime(_mod.LOCK)

    def _age_the_lock(self, secs):
        """Make the lock look as old as a tick that has been gating for `secs`."""
        stamp = time.time() - secs
        os.utime(_mod.LOCK, (stamp, stamp))

    # --- the tests ---------------------------------------------------------

    def test_a_working_tick_renews_the_lock_before_the_supervisor_calls_it_wedged(self):
        inode = self._make_lock()
        self._age_the_lock(self.SUPERVISOR_MAX_HOLDER_SECS + 100)
        self.assertGreater(self._supervisor_age(), self.SUPERVISOR_MAX_HOLDER_SECS,
                           "the lock must look old before the renewal")
        self.assertTrue(_mod.renew_lock(_mod.LOCK, inode))
        self.assertLess(self._supervisor_age(), self.SUPERVISOR_MAX_HOLDER_SECS,
                        "a renewed lock must not look wedged to the supervisor")

    def test_the_lock_of_another_holder_is_never_renewed(self):
        inode = self._make_lock(pid=self._dead_pid())
        before = os.path.getmtime(_mod.LOCK)
        self.assertFalse(_mod.renew_lock(_mod.LOCK, inode))
        self.assertEqual(os.path.getmtime(_mod.LOCK), before,
                         "another holder's lock must not be touched")

    def test_a_lock_that_was_taken_over_is_never_renewed(self):
        inode = self._make_lock()
        # Somebody else took the lock over: the same path, a new directory.
        shutil.rmtree(_mod.LOCK, ignore_errors=True)
        self._make_lock(pid=self._dead_pid())
        before = os.path.getmtime(_mod.LOCK)
        self.assertFalse(_mod.renew_lock(_mod.LOCK, inode))
        self.assertEqual(os.path.getmtime(_mod.LOCK), before,
                         "a lock that was taken over must not be renewed by the old holder")

    def test_the_heartbeat_renews_the_lock_while_the_tick_works(self):
        self._make_lock()
        self._age_the_lock(self.SUPERVISOR_MAX_HOLDER_SECS + 100)
        _mod._start_lock_heartbeat(_mod.LOCK, 0.05)
        deadline = time.time() + 5
        while (time.time() < deadline
               and self._supervisor_age() > self.SUPERVISOR_MAX_HOLDER_SECS):
            time.sleep(0.05)
        self.assertLess(self._supervisor_age(), self.SUPERVISOR_MAX_HOLDER_SECS,
                        "the heartbeat must keep a working tick out of the wedge rule")

    def test_the_heartbeat_says_so_in_the_log(self):
        """The supervisor also warns when the log has not advanced for three
        intervals, so the tick has to say that it is alive."""
        self._make_lock()
        _mod._start_lock_heartbeat(_mod.LOCK, 0.05)
        deadline = time.time() + 5
        said = False
        while time.time() < deadline and not said:
            time.sleep(0.05)
            try:
                with open(os.path.join(_mod.LOGD, "local-ci.log")) as f:
                    said = "lock: renewed" in f.read()
            except FileNotFoundError:
                said = False
        self.assertTrue(said, "a working tick must say that it is alive in the log")

    def test_the_heartbeat_stops_when_the_tick_releases_the_lock(self):
        self._make_lock()
        _mod._start_lock_heartbeat(_mod.LOCK, 0.05)
        _mod.release_lock()
        self.assertIsNone(_mod._lock_heartbeat_thread)
        self.assertFalse(os.path.exists(_mod.LOCK))
        time.sleep(0.3)
        self.assertFalse(os.path.exists(_mod.LOCK),
                         "a released lock must not be brought back by the heartbeat")

    def test_taking_the_lock_starts_the_heartbeat_and_releasing_it_stops_it(self):
        self.assertTrue(_mod.acquire_lock())
        self.assertIsNotNone(_mod._lock_heartbeat_thread)
        self.assertTrue(_mod._lock_heartbeat_thread.daemon,
                        "the heartbeat must never hold the process open")
        _mod.release_lock()
        self.assertIsNone(_mod._lock_heartbeat_thread)

    def test_a_lock_whose_holder_is_gone_is_still_taken_over(self):
        """The renewal keeps the lock fresh, so a dead holder must not be
        mistaken for a busy one."""
        self._make_lock(pid=self._dead_pid())
        self._age_the_lock(10)
        self.assertTrue(_mod.acquire_lock(),
                        "a lock whose holder is gone must be taken over")
        self.assertEqual(_mod.lock_holder_alive(), os.getpid())
        _mod.release_lock()



class WorktreeRootGuardTest(unittest.TestCase):
    """A gate must not run in a directory that is not there.

    2026-10-26: the runner ran a tick with its worktree root resolved to "/"
    and posted sixteen failures -- every check ran from `/` and none of them
    was a finding. The tick has to refuse instead of producing that verdict.
    """

    PR = {"number": 1, "headRefOid": "a" * 40, "baseRefName": "develop",
          "title": "fix(x): y"}

    def setUp(self):
        self._saved = (_mod.WT, _mod._guard)
        _mod._guard = lambda: None

    def tearDown(self):
        _mod.WT, _mod._guard = self._saved

    def test_run_checks_refuses_a_root_that_is_not_our_worktree(self):
        # The observed failure: the root resolved to "/", which IS a directory,
        # so an isdir check would have passed it and run every gate from root.
        _mod.WT = "/"
        with self.assertRaises(SystemExit) as ctx:
            _mod.run_checks(self.PR, io.StringIO())
        self.assertIn("is not this runner's worktree", str(ctx.exception))
        self.assertIn("refusing to run gates", str(ctx.exception))

    def test_run_checks_refuses_a_missing_root(self):
        _mod.WT = "/nonexistent-worktree-root-for-test"
        with self.assertRaises(SystemExit):
            _mod.run_checks(self.PR, io.StringIO())

    def test_pool_step_with_a_missing_directory_fails_without_executing(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        _mod.WT = tmp
        ran = []
        saved_sh = _mod.sh
        _mod.sh = lambda *a, **kw: (ran.append(a), (0, ""))[1]
        try:
            fails = _mod.run_step_pool(
                [("probe", ["true"], 5, "/nonexistent-worktree-root-for-test", None, ())],
                io.StringIO(),
            )
        finally:
            _mod.sh = saved_sh
        self.assertIn("probe", fails)
        self.assertEqual(ran, [], "the pool must not execute a step with no cwd")

    def test_pool_step_without_an_explicit_cwd_runs_in_the_worktree_root(self):
        """The regression: the pool passed cwd=None, so the child inherited
        launchd's "/" and every check looked for `//scripts/...`."""
        import tempfile
        tmp = tempfile.mkdtemp()
        _mod.WT = tmp
        seen = []
        saved = _mod.sh
        _mod.sh = lambda cmd, cwd=None, **kw: (seen.append(cwd), (0, ""))[1]
        try:
            _mod.run_step_pool([("probe", ["true"], 5, None, None, ())], io.StringIO())
        finally:
            _mod.sh = saved
        self.assertEqual(seen, [tmp], "a step with no cwd must run in the worktree root")

class StepBudgetTest(unittest.TestCase):
    """Every gate step has a wall-clock ceiling of its own (2026-10-26).

    The evidence was in the runner's own logs: a check that measures 10 s alone
    had the tick recorded at 32 m and 44 m, while every step idle together took
    99.6 s. The cost was a step hanging and the runner waiting on it, so the
    ceiling is per step and the kill takes the whole process group. A red check
    keeps its plain name: only an overrun is reported as an overrun.
    """

    def setUp(self):
        self.out = io.StringIO()
        self.fails = []

    def _step_seconds(self, text):
        """The duration the runner measured, read back from the log line."""
        m = re.search(r"^step=(\S+) seconds=([\d.]+) rc=(-?\d+)", text, re.M)
        self.assertIsNotNone(m, f"no `step=... seconds=... rc=...` line in:\n{text}")
        return m.group(1), float(m.group(2)), int(m.group(3))

    def test_a_step_that_overruns_its_budget_is_killed_and_named(self):
        started = time.monotonic()
        ok = _mod.run_step("scripts/check_slow.py", ["/bin/sleep", "60"], 60,
                           self.out, self.fails, budget=1)
        took = time.monotonic() - started
        self.assertFalse(ok)
        self.assertLess(took, 20, "the step must be killed at its budget, not waited on")
        self.assertEqual(self.fails, ["scripts/check_slow.py exceeded 1s and was killed"])
        text = self.out.getvalue()
        self.assertIn("scripts/check_slow.py exceeded 1s and was killed", text)
        self.assertIn("[rc=124]", text, "the existing [rc=...] block must stay")
        name, seconds, rc = self._step_seconds(text)
        self.assertEqual((name, rc), ("scripts/check_slow.py", 124))
        self.assertLess(seconds, 20, "the duration must be the measured one, not the budget")

    def test_the_tick_moves_on_to_the_next_step(self):
        _mod.run_step("hung", ["/bin/sleep", "60"], 60, self.out, self.fails, budget=1)
        ok = _mod.run_step("quick", ["/usr/bin/true"], 60, self.out, self.fails, budget=60)
        self.assertTrue(ok)
        self.assertEqual(self.fails, ["hung exceeded 1s and was killed"],
                         "the next step must run and must not inherit the failure")
        self.assertIn("step=quick seconds=", self.out.getvalue())

    def test_a_step_under_its_budget_is_untouched(self):
        ok = _mod.run_step("quick", ["/bin/sh", "-c", "sleep 0.2; exit 0"], 60,
                           self.out, self.fails)
        self.assertTrue(ok, "a healthy step must not be touched by the watchdog")
        self.assertEqual(self.fails, [])
        name, seconds, rc = self._step_seconds(self.out.getvalue())
        self.assertEqual((name, rc), ("quick", 0))
        self.assertGreaterEqual(seconds, 0.2, "the measured time must be reported")
        self.assertNotIn("exceeded", self.out.getvalue())

    def test_a_genuine_failure_still_reads_as_a_failure(self):
        ok = _mod.run_step("ruff", ["/bin/sh", "-c", "exit 1"], 60, self.out, self.fails)
        self.assertFalse(ok)
        self.assertEqual(self.fails, ["ruff"],
                         "a red check is still named plainly, not called a stall")
        self.assertNotIn("exceeded", self.out.getvalue())
        self.assertNotIn("was killed", self.out.getvalue())

    def test_a_stalled_step_is_not_retried_into_a_second_window(self):
        ok = _mod.run_step("scripts/check_slow.py", ["/bin/sleep", "60"], 60,
                           self.out, self.fails, budget=1, stall_rcs=(124, 3))
        self.assertFalse(ok)
        text = self.out.getvalue()
        self.assertEqual(text.count("===== scripts/check_slow.py"), 1,
                         "a step killed for overrunning must not get a second window")
        self.assertEqual(self.fails, ["scripts/check_slow.py exceeded 1s and was killed"])
        self.assertIn("step=scripts/check_slow.py seconds=", text)

    def test_the_retry_cap_is_enforced(self):
        started = time.monotonic()
        ok = _mod.run_step("scripts/check_guard.py", ["/bin/sh", "-c", "exit 3"], 60,
                           self.out, self.fails, stall_rcs=(124, 3))
        self.assertFalse(ok)
        text = self.out.getvalue()
        self.assertEqual(text.count("===== scripts/check_guard.py"), _mod.RETRY_CAP,
                         "the attempt cap must be the only bound on the retry loop")
        self.assertIn(f"attempts={_mod.RETRY_CAP}/{_mod.RETRY_CAP}", text,
                      "the log must say how many attempts ran")
        self.assertEqual(self.fails, ["scripts/check_guard.py:stall"])
        self.assertLess(time.monotonic() - started, 20)

    def test_the_duration_line_is_emitted_for_every_step_including_failures(self):
        _mod.run_step("green", ["/usr/bin/true"], 60, self.out, self.fails)
        _mod.run_step("red", ["/bin/sh", "-c", "exit 1"], 60, self.out, self.fails)
        _mod.run_step("hung", ["/bin/sleep", "60"], 60, self.out, self.fails, budget=1)
        lines = [ln for ln in self.out.getvalue().splitlines() if ln.startswith("step=")]
        self.assertEqual([ln.split()[0] for ln in lines],
                         ["step=green", "step=red", "step=hung"],
                         "one duration line per step, in the order the steps ran")
        self.assertEqual([ln.rsplit("rc=", 1)[1] for ln in lines], ["0", "1", "124"])

    def test_the_kill_takes_the_whole_process_group_down(self):
        """A hung step is a tree: the shell that hung and the grandchild it left."""
        tmp = tempfile.mkdtemp(prefix="local-ci-kill-")
        pidfile = os.path.join(tmp, "grandchild.pid")
        try:
            cmd = ["/bin/sh", "-c", f"sleep 60 & echo $! > {pidfile}; wait"]
            _mod.run_step("hung-tree", cmd, 60, self.out, self.fails, budget=1)
            with open(pidfile) as f:
                grandchild = int(f.read().strip())
            deadline = time.monotonic() + 2
            while _mod.pid_alive(grandchild) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(_mod.pid_alive(grandchild),
                             "a grandchild must not survive the step's budget")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_default_budget_and_the_per_step_overrides(self):
        self.assertEqual(_mod.STEP_BUDGET, 180)
        for heavy in ("uv-sync", "mypy", "gitleaks", "worker-build:npm-ci"):
            self.assertGreater(_mod.STEP_BUDGETS[heavy], _mod.STEP_BUDGET,
                               f"{heavy} legitimately needs more than the default")
        for light in ("actionlint", "pr-title"):
            self.assertNotIn(light, _mod.STEP_BUDGETS,
                             f"{light} is measured in seconds; it takes the default")

    def test_a_tree_scanner_budget_is_the_scan_timeout(self):
        """The scanners are not in STEP_BUDGETS, so before DIG-5724 they took
        the 180 s default and a clean tree false-red at 182-183 s (PR #6525)."""
        spec = _mod.scan_spec("scripts/scan_customer_pii.py",
                              "python3 scripts/scan_customer_pii.py")
        self.assertEqual(spec[2], _mod.SCAN_TIMEOUT,
                         "SCAN_TIMEOUT is the scanner's caller ceiling")
        self.assertEqual(spec[6], _mod.SCAN_TIMEOUT,
                         "and its step budget, not the 180 s STEP_BUDGET default")
        self.assertGreaterEqual(_mod.SCAN_TIMEOUT, 3 * 183,
                                "the budget keeps a 3x margin over the worst "
                                "measured clean-tree runtime (183 s, PR #6525)")

    def test_the_scan_timeout_env_raises_a_scanners_budget(self):
        """LOCAL_CI_SCAN_TIMEOUT must reach the budget, not only the ceiling."""
        code = (
            "import importlib.util, sys;"
            f"sys.path.insert(0, {_SCRIPTS!r});"
            "s=importlib.util.spec_from_file_location('local_ci_scan_env', "
            f"{os.path.join(_SCRIPTS, 'local_ci.py')!r});"
            "m=importlib.util.module_from_spec(s);sys.modules['local_ci_scan_env']=m;"
            "s.loader.exec_module(m);"
            "print(m.SCAN_TIMEOUT, m.scan_spec('scripts/check_doc_links.py', 'true')[6])"
        )
        env = dict(os.environ, LOCAL_CI_SCAN_TIMEOUT="900")
        env.pop("LOCAL_CI_STEP_BUDGET", None)
        got = subprocess.check_output([sys.executable, "-c", code], env=env,
                                      text=True, cwd=_SCRIPTS).strip()
        self.assertEqual(got, "900 900",
                         "the env knob must raise the ceiling and the budget together")

    def test_both_scanner_waves_take_the_scan_budget(self):
        """A wave that calls gate_spec directly silently loses the scan budget."""
        import inspect
        src = inspect.getsource(_mod.run_checks)
        self.assertGreaterEqual(src.count("scan_spec("), 2,
                                "the pre-uv-sync and post-uv-sync scanner waves must both "
                                "use scan_spec (DIG-5724)")

    def test_the_budget_is_per_step_and_never_above_the_caller_ceiling(self):
        self.assertEqual(_mod.step_budget("actionlint", 300), 180,
                         "a non-scanner step still takes the 180 s default")
        self.assertEqual(_mod.step_budget("uv-sync", 1800), _mod.STEP_BUDGETS["uv-sync"])
        self.assertEqual(_mod.step_budget("bun:digichat-tui", 1800), _mod.STEP_BUDGETS["bun:*"])
        self.assertEqual(_mod.step_budget("uv-sync", 120), 120,
                         "a tighter caller ceiling still wins")
        self.assertEqual(_mod.step_budget("anything", 1800, budget=7), 7)
        self.assertEqual(_mod.gate_spec("anything", "true", 1800, budget=7)[6], 7,
                         "gate_spec must pass an explicit budget through")

    def test_run_checks_routes_every_step_through_the_budgeted_runner(self):
        """A step that bypasses run_step has no budget, so the gate cannot
        prevent the next 44 m tick."""
        import inspect
        src = inspect.getsource(_mod.run_checks)
        self.assertIn("return run_step(", src)
        self.assertEqual(src.count("sh("), 0,
                         "run_checks must not call sh directly: every step takes a budget")
