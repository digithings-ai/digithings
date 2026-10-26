#!/usr/bin/env python3
"""DIG-4507 guard tests: one required context, one producer.

Fixtures are built in a tempdir so the test never touches the real repos and
never hardcodes a context name: every case builds its own.
"""

import importlib.util
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))

try:
    import pytest
except ImportError:  # the file also runs as a plain unittest module
    pytest = None
else:
    pytestmark = pytest.mark.unit

_spec = importlib.util.spec_from_file_location(
    "check_required_context_producers",
    os.path.join(_SCRIPTS, "check_required_context_producers.py"))
g = importlib.util.module_from_spec(_spec)
sys.modules["check_required_context_producers"] = g
_spec.loader.exec_module(g)

CTX = "Some Required Context Name"


def prot(contexts, checks=()):
    return {
        "required_status_checks": {
            "contexts": list(contexts),
            "checks": [dict(c) for c in checks],
        }
    }


def reader_for(payload, readable=True):
    def _r(repo):
        return readable, payload
    return _r


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rcp-guard-")
        self.wf = os.path.join(self.tmp, "wt", ".github", "workflows")
        os.makedirs(self.wf)
        self.spec = {"repo": "o/r", "workflows": os.path.join("wt", ".github", "workflows")}

    def write(self, rel, text):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_single_workflow_producer_passes(self):
        self.write("wt/.github/workflows/ci-x.yml", "jobs:\n  j:\n    name: %s\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(rep["violations"], [])

    def test_workflow_plus_host_copy_is_a_violation(self):
        self.write("wt/.github/workflows/ci-x.yml", "jobs:\n  j:\n    name: %s\n" % CTX)
        self.write("host.py", "CTX = %r\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(len(rep["violations"]), 1)
        self.assertEqual(rep["violations"][0]["reason"], "not exactly one producer")

    def test_mention_only_file_is_not_a_producer(self):
        # a repo file that mentions the name, and a host file with a different name
        self.write("wt/.github/workflows/ci-x.yml", "jobs:\n  j:\n    name: %s\n" % CTX)
        self.write("wt/scripts/other.py", "# mentions %s only\n" % CTX)
        self.write("host.py", "OTHER = 1\n")
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(rep["violations"], [])

    def test_host_only_producer_for_app_pinned_context_is_a_violation(self):
        self.write("host.py", "CTX = %r\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp,
                    reader=reader_for(prot([CTX], [{"context": CTX, "app_id": 15368}])))
        self.assertEqual(len(rep["violations"]), 1)
        self.assertIn("pinned to an app", rep["violations"][0]["reason"])

    def test_unreadable_protection_is_reported_not_failed(self):
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(None, readable=False))
        self.assertEqual(rep["violations"], [])
        self.assertFalse(rep["repos"][0]["readable"])

    def test_a_workflow_level_name_is_not_a_producer(self):
        """`name:` at the top of the file names the workflow, not a check run."""
        self.write("wt/.github/workflows/ci-x.yml", "name: %s\njobs:\n  j:\n    runs-on: ubuntu-latest\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(len(rep["violations"]), 1, rep["repos"])

    def test_a_step_name_is_not_a_producer(self):
        """A step's `- name:` names the step, not a job, so it is not a check run."""
        self.write("wt/.github/workflows/ci-x.yml",
                   "jobs:\n  j:\n    runs-on: ubuntu-latest\n    steps:\n      - name: %s\n        run: true\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(len(rep["violations"]), 1, rep["repos"])

    def test_a_job_id_is_the_check_run_name_when_the_job_has_no_name(self):
        """GitHub falls back to the job id, so a producer may carry no `name:`."""
        self.write("wt/.github/workflows/ci-x.yml", "jobs:\n  %s:\n    runs-on: ubuntu-latest\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(rep["violations"], [])

    def test_no_producer_at_all_is_a_violation(self):
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(len(rep["violations"]), 1)

    def test_host_source_without_the_name_is_not_a_producer(self):
        self.write("host.py", "import json\ndef gh(*a):\n    return None\n")
        self.write("wt/.github/workflows/ci-x.yml", "jobs:\n  j:\n    name: %s\n" % CTX)
        rep = g.run(repos=[self.spec], host_dir=self.tmp, reader=reader_for(prot([CTX])))
        self.assertEqual(rep["violations"], [])

    def test_required_contexts_merges_contexts_and_checks(self):
        got = g.required_contexts(prot([CTX], [{"context": CTX, "app_id": 15368}]))
        self.assertEqual(got, [(CTX, 15368)])

    def test_default_repos_finds_the_repository_layout(self):
        """The published module runs from a checkout: `<repo>/.github/workflows`."""
        repo = os.path.join(self.tmp, "repo")
        mod_dir = os.path.join(repo, "scripts", "local-ci")
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        os.makedirs(mod_dir)
        here = g.__file__
        try:
            g.__file__ = os.path.join(mod_dir, "check_required_context_producers.py")
            repos = g.default_repos()
        finally:
            g.__file__ = here
        self.assertEqual([r["repo"] for r in repos], [g.DIGITHINGS])
        self.assertEqual(repos[0]["workflows"],
                         os.path.join(repo, ".github", "workflows"))

    def test_default_repos_skips_a_repo_with_no_workflow_tree(self):
        """The repository checkout must not claim to guard twelve-x."""
        repo = os.path.join(self.tmp, "repo")
        mod_dir = os.path.join(repo, "scripts", "local-ci")
        os.makedirs(os.path.join(repo, ".github", "workflows"))
        os.makedirs(mod_dir)
        here = g.__file__
        try:
            g.__file__ = os.path.join(mod_dir, "check_required_context_producers.py")
            repos = g.default_repos()
        finally:
            g.__file__ = here
        self.assertNotIn(g.TWELVE_X, [r["repo"] for r in repos])


if __name__ == "__main__":
    unittest.main()
