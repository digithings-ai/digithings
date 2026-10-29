"""local-ci's npm workspace gate: which workspaces a change must test.

Fixture trees only: no network, no npm, no subprocess. The mapping is the part
that can silently under-cover, so it is pinned here; the run itself goes
through the same `step`/pool plumbing every other gate uses.
"""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

import pytest

pytestmark = pytest.mark.unit

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_SCRIPTS = os.path.join(_ROOT, "scripts", "local-ci")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
if "local_ci" in sys.modules:
    lc = sys.modules["local_ci"]
else:
    _spec = importlib.util.spec_from_file_location("local_ci", os.path.join(_SCRIPTS, "local_ci.py"))
    lc = importlib.util.module_from_spec(_spec)
    sys.modules["local_ci"] = lc
    _spec.loader.exec_module(lc)

CI_PATHS = """\
digichat:
  - apps/digichat/**
  - packages/ui/**
  - packages/design/**
  - package.json
  - .github/workflows/test-digichat.yml

dashboard:
  - apps/dashboard/**
  - packages/ui/**
  - .github/workflows/test-dashboard.yml

web:
  - apps/digithings-web/**
  - apps/twelvex-runner/**
  - infra/docker/Dockerfile.twelvex-runner
  - packages/ui/**
  - packages/hero-banner/**
  - .github/workflows/test-web.yml

workers:
  - apps/twelvex-runner/**
"""

PKGS = {
    "apps/digichat": {"name": "digichat", "scripts": {"test": "vitest run"},
                      "dependencies": {"@digithings/ui": "*", "react": "19"}},
    "apps/dashboard": {"name": "dashboard", "scripts": {"test": "vitest run"},
                       "devDependencies": {"@digithings/ui": "*"}},
    "apps/digithings-web": {"name": "digithings-web", "scripts": {"test": "vitest run"},
                            "dependencies": {"@digithings/chat-ui": "*"}},
    "apps/twelvex-runner": {"name": "twelvex-runner", "scripts": {"test": "vitest run"}},
    "apps/no-tests": {"name": "no-tests", "scripts": {"build": "x"},
                      "dependencies": {"@digithings/design": "*"}},
    "packages/ui": {"name": "@digithings/ui", "scripts": {"test": "vitest run"},
                    "dependencies": {"@digithings/design": "*"}},
    "packages/chat-ui": {"name": "@digithings/chat-ui", "scripts": {"test": "vitest run"},
                         "peerDependencies": {"@digithings/ui": "*"}},
    "packages/design": {"name": "@digithings/design"},
    "packages/hero-banner": {"name": "@digithings/hero-banner", "scripts": {"test": "bun test"}},
}

ALL_VITEST = ["apps/dashboard", "apps/digichat", "apps/digithings-web",
              "apps/twelvex-runner", "packages/chat-ui", "packages/ui"]


class NpmPlanTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.wt = self._tmp.name
        self._write("package.json", {"name": "root", "workspaces": ["apps/*", "packages/*"]})
        for d, pkg in PKGS.items():
            self._write(f"{d}/package.json", pkg)
        self._text("scripts/ci_paths.yaml", CI_PATHS)

    def tearDown(self):
        self._tmp.cleanup()

    def _text(self, rel, text):
        p = os.path.join(self.wt, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def _write(self, rel, obj):
        self._text(rel, json.dumps(obj))

    def dirs(self, files):
        plan, why, error = lc.npm_plan(files, self.wt)
        return [d for d, _ in plan], why, error

    def test_docs_only_change_runs_nothing(self):
        dirs, _, error = self.dirs(["docs/readme.md", "digigraph/src/x.py"])
        self.assertEqual(dirs, [])
        self.assertIsNone(error)

    def test_app_change_runs_only_that_app(self):
        dirs, why, _ = self.dirs(["apps/digichat/src/page.tsx"])
        self.assertEqual(dirs, ["apps/digichat"])
        self.assertEqual(why["apps/digichat"], "touched apps/digichat/src/page.tsx")

    def test_prefix_of_another_workspace_does_not_match(self):
        # apps/digichat must not swallow apps/digichat-cloudflare.
        self._write("apps/digichat-cloudflare/package.json",
                    {"name": "digichat-cloudflare", "scripts": {"test": "vitest run"}})
        dirs, _, _ = self.dirs(["apps/digichat-cloudflare/src/w.ts"])
        self.assertEqual(dirs, ["apps/digichat-cloudflare"])

    def test_shared_package_runs_every_transitive_dependent(self):
        dirs, why, _ = self.dirs(["packages/design/tokens.css"])
        # design has no test; ui depends on it; digichat, dashboard (dev dep)
        # and chat-ui (peer dep) depend on ui; digithings-web depends on chat-ui.
        self.assertEqual(dirs, ["apps/dashboard", "apps/digichat", "apps/digithings-web",
                                "packages/chat-ui", "packages/ui"])
        self.assertEqual(why["apps/digithings-web"], "depends on a touched workspace")

    def test_root_install_inputs_run_every_workspace(self):
        for f in ("package-lock.json", "package.json", ".npmrc", "eslint.base.mjs"):
            with self.subTest(f=f):
                dirs, why, _ = self.dirs([f])
                self.assertEqual(dirs, ALL_VITEST)
                self.assertTrue(why["apps/digichat"].startswith("root install input"))

    def test_nested_package_json_is_not_a_root_input(self):
        dirs, _, _ = self.dirs(["apps/twelvex-runner/package.json"])
        self.assertEqual(dirs, ["apps/twelvex-runner"])

    def test_lane_path_outside_workspaces_runs_that_lanes_workspaces(self):
        dirs, why, _ = self.dirs(["infra/docker/Dockerfile.twelvex-runner"])
        self.assertEqual(dirs, ["apps/digithings-web", "apps/twelvex-runner", "packages/ui"])
        self.assertEqual(why["apps/twelvex-runner"],
                         "web lane path infra/docker/Dockerfile.twelvex-runner")

    def test_lane_workflow_file_runs_that_lane(self):
        dirs, _, _ = self.dirs([".github/workflows/test-dashboard.yml"])
        self.assertEqual(dirs, ["apps/dashboard", "packages/ui"])

    def test_bun_and_testless_workspaces_are_left_out(self):
        dirs, why, _ = self.dirs(["packages/hero-banner/src/a.ts", "apps/no-tests/x.ts"])
        self.assertEqual(dirs, [])
        self.assertIn("packages/hero-banner", why)  # selected, then filtered

    def test_plan_is_deterministic_and_sorted(self):
        files = ["packages/ui/a.ts", "apps/digichat/b.ts", "apps/dashboard/c.ts"]
        first = lc.npm_plan(files, self.wt)
        self.assertEqual(lc.npm_plan(list(reversed(files)), self.wt), first)
        self.assertEqual([d for d, _ in first[0]], sorted(d for d, _ in first[0]))

    def test_unreadable_workspace_manifest_fails_closed(self):
        self._text("apps/digichat/package.json", "{not json")
        dirs, _, error = self.dirs(["docs/readme.md"])
        self.assertIn("apps/digichat/package.json unreadable", error)
        # Everything the tolerant reader can still see runs.
        self.assertEqual(dirs, [d for d in ALL_VITEST if d != "apps/digichat"])

    def test_missing_lane_block_fails_closed(self):
        self._text("scripts/ci_paths.yaml", CI_PATHS.replace("dashboard:", "dashbored:"))
        dirs, _, error = self.dirs(["docs/readme.md"])
        self.assertIn("`dashboard:`", error)
        self.assertEqual(dirs, ALL_VITEST)

    def test_missing_ci_paths_fails_closed(self):
        os.remove(os.path.join(self.wt, "scripts", "ci_paths.yaml"))
        dirs, _, error = self.dirs(["apps/digichat/x.ts"])
        self.assertIn("ci_paths.yaml unreadable", error)
        self.assertEqual(dirs, ALL_VITEST)

    def test_root_without_workspaces_fails_closed(self):
        self._write("package.json", {"name": "root"})
        dirs, _, error = self.dirs(["apps/digichat/x.ts"])
        self.assertIn("names no workspaces", error)
        self.assertEqual(dirs, ALL_VITEST)


class NpmRunTest(unittest.TestCase):
    PLAN = [("apps/digichat", "digichat"), ("packages/ui", "@digithings/ui")]

    def _run(self, plan, installed=None, step_ok=True):
        steps, pooled, fails = [], [], []

        def step(name, cmd, timeout=1800, cwd=None, env=None, stall_rcs=(), budget=None):
            steps.append((name, cmd))
            return step_ok

        def pool(specs, out, limit=None):
            pooled.extend(specs)
            return []

        ran = lc.run_npm_suites("/wt", step, io.StringIO(), fails, plan,
                                installed=installed, pool=pool)
        return ran, steps, pooled, fails

    def test_installs_once_then_runs_each_workspace_test(self):
        ran, steps, pooled, fails = self._run(self.PLAN)
        self.assertEqual(steps, [("npm-ci", ["npm", "ci", "--no-audit", "--no-fund"])])
        self.assertEqual([s[1] for s in pooled],
                         [["npm", "run", "test", "--workspace", "digichat"],
                          ["npm", "run", "test", "--workspace", "@digithings/ui"]])
        self.assertEqual([s[0] for s in pooled], ["npm-test:digichat", "npm-test:ui"])
        self.assertEqual(ran, ["digichat", "ui"])
        self.assertEqual(fails, [])

    def test_reuses_the_worker_build_install(self):
        _, steps, pooled, _ = self._run(self.PLAN, installed=True)
        self.assertEqual(steps, [])
        self.assertEqual(len(pooled), 2)

    def test_failed_worker_build_install_is_a_named_failure(self):
        ran, steps, pooled, fails = self._run(self.PLAN, installed=False)
        self.assertEqual((ran, steps, pooled), ([], [], []))
        self.assertEqual(fails, ["npm-suites: npm ci failed"])

    def test_failed_install_runs_no_suite(self):
        ran, _, pooled, _ = self._run(self.PLAN, step_ok=False)
        self.assertEqual((ran, pooled), ([], []))

    def test_empty_plan_installs_nothing(self):
        self.assertEqual(self._run([]), ([], [], [], []))

    def test_suites_run_without_credentials_and_with_ci_set(self):
        env = lc.npm_env({"PATH": "/bin", "OPENAI_API_KEY": "x", "GH_TOKEN": "x",
                          "CHEAPERINFERENCE_BASE_URL": "x", "MY_SECRET": "x", "HOME": "/h"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h", "CI": "1"})
        _, _, pooled, _ = self._run(self.PLAN)
        for spec in pooled:
            self.assertEqual(spec[3], "/wt")
            self.assertNotIn("OPENAI_API_KEY", spec[4])
            self.assertEqual(spec[4]["CI"], "1")

    def test_npm_steps_have_their_own_budget(self):
        self.assertEqual(lc.step_budget("npm-test:digichat", lc.NPM_TEST_TIMEOUT), 600)
        self.assertEqual(lc.step_budget("npm-ci", 1800), 600)


class NpmReceiptTest(unittest.TestCase):
    def test_receipt_names_npm_suites(self):
        desc = lc.success_desc(4, {"ran": []}, {"ran": ["digichat", "ui"]})
        self.assertIn("npm 2/2: digichat, ui", desc)
        self.assertIn("bun: none", desc)
        self.assertLessEqual(len(desc), 139)

    def test_receipt_says_none_for_both(self):
        desc = lc.success_desc(2, {"ran": []}, {"ran": []})
        self.assertIn("bun: none; npm: none", desc)
        self.assertIn(lc.GATED_NOTE, desc)

    def test_long_receipt_drops_names(self):
        desc = lc.success_desc(9, {"ran": ["digichat-tui"] * 3}, {"ran": [f"ws-{i}" * 3 for i in range(15)]})
        self.assertLessEqual(len(desc), 139)
        self.assertIn("npm 15/15", desc)
        self.assertIn("suites in the log", desc)


def test_run_checks_wires_the_npm_gate():
    src = open(os.path.join(_SCRIPTS, "local_ci.py")).read()
    assert "npm_gate(pr, WT)" in src
    assert "run_npm_suites(WT, step, out, fails, npm_suites, installed=npm_installed)" in src
    assert 'summary["npm"]' in src
    assert 'success_desc(mins, summary.get("bun"), summary.get("npm"))' in src


def test_live_tree_mapping_has_no_error():
    """The real scripts/ci_paths.yaml and manifests map without falling back."""
    plan, why, error = lc.npm_plan(["apps/digichat/src/app/layout.tsx"], _ROOT)
    assert error is None, error
    assert ("apps/digichat", "digichat") in plan


def test_live_tree_shared_ui_runs_its_consumers():
    plan, _, error = lc.npm_plan(["packages/ui/src/index.ts"], _ROOT)
    names = {n for _, n in plan}
    assert error is None, error
    assert {"@digithings/ui", "digichat", "dashboard", "digithings-web"} <= names
    assert not any(n.endswith(("hero-banner", "surface-config", "tui-frame")) for n in names)
