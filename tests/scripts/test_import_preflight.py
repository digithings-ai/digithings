#!/usr/bin/env python3
"""Unit tests for the install preflight (DIG-5585). Stdlib only:
`/usr/bin/python3 -m unittest test_import_preflight -v`."""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
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
    "import_preflight", os.path.join(_SCRIPTS, "import_preflight.py"))
_preflight = importlib.util.module_from_spec(_spec)
sys.modules["import_preflight"] = _preflight
_spec.loader.exec_module(_preflight)

#: A checkout shaped like the install: the runner next to its helpers, the
#: shared review rules one directory up. Only the import graph matters here.
RUNNER = '''#!/usr/bin/env python3
try:
    import review_applied
except ImportError:
    review_applied = None
try:
    import pr_template
except ImportError:
    pr_template = None
'''

REVIEW_APPLIED = '''#!/usr/bin/env python3
try:
    import review_pass_filter
except ImportError:
    review_pass_filter = None
'''

REVIEW_RULES = '''#!/usr/bin/env python3
VALUE = 1
'''

PR_TEMPLATE = '''#!/usr/bin/env python3
VALUE = 2
'''

PRODUCER_GUARD = '''#!/usr/bin/env python3
import json
'''

_FILES = {
    ("scripts", "local-ci", "local_ci.py"): RUNNER,
    ("scripts", "local-ci", "review_applied.py"): REVIEW_APPLIED,
    ("scripts", "local-ci", "pr_template.py"): PR_TEMPLATE,
    ("scripts", "local-ci", "check_required_context_producers.py"): PRODUCER_GUARD,
    ("scripts", "review_pass_filter.py"): REVIEW_RULES,
}


class Checkout:
    """A fixture runner checkout that a test can break one file at a time."""

    def __init__(self):
        self.root = tempfile.mkdtemp()
        for parts, text in _FILES.items():
            self.write(parts, text)

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    @property
    def runner(self):
        return self.path("scripts", "local-ci", "local_ci.py")

    def write(self, parts, text):
        path = self.path(*parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def remove(self, *parts):
        os.remove(self.path(*parts))

    def cleanup(self):
        shutil.rmtree(self.root, ignore_errors=True)


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.checkout = Checkout()

    def tearDown(self):
        self.checkout.cleanup()

    def missing(self):
        problems = _preflight.check(self.checkout.runner)
        return {p["module"]: p for p in problems}

    def run_cli(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(_SCRIPTS, "import_preflight.py"),
             self.checkout.runner],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_a_complete_checkout_resolves(self):
        self.assertEqual(self.missing(), {})

    def test_the_real_runner_tree_resolves(self):
        """The repository tree is a complete install of the runner."""
        self.assertEqual(_preflight.check(os.path.join(_SCRIPTS, "local_ci.py")), [])

    def test_a_module_deleted_from_the_checkout_is_refused(self):
        """The 24 Oct shape: the shared rules were never copied in.

        The runner bound ``review_pass_filter`` to None, so every PR read as
        "no review pass left comments". The refusal must name the module and
        the module that imports it, not the review.
        """
        self.checkout.remove("scripts", "review_pass_filter.py")
        missing = self.missing()
        self.assertIn("review_pass_filter", missing)
        self.assertEqual(missing["review_pass_filter"]["importer"], "review_applied.py")

    def test_a_helper_that_was_never_copied_in_is_named(self):
        self.checkout.remove("scripts", "local-ci", "review_applied.py")
        missing = self.missing()
        self.assertIn("review_applied", missing)
        self.assertEqual(missing["review_applied"]["importer"], "local_ci.py")

    def test_a_module_loaded_by_path_is_checked(self):
        """importlib loads the producer guard by path; an import scan misses it."""
        self.checkout.remove("scripts", "local-ci", "check_required_context_producers.py")
        self.assertIn("check_required_context_producers", self.missing())

    def test_a_module_that_does_not_parse_is_reported(self):
        self.checkout.write(("scripts", "local-ci", "pr_template.py"),
                            "def main(:\n    pass\n")
        missing = self.missing()
        self.assertIn("pr_template", missing)
        self.assertIn("cannot be parsed", missing["pr_template"]["why"])

    def test_the_cli_refuses_with_ex_config_and_a_loud_line(self):
        self.checkout.remove("scripts", "review_pass_filter.py")
        rc, _out, err = self.run_cli()
        self.assertEqual(rc, _preflight.EXIT_CONFIG)
        self.assertIn("refusing to tick", err)
        self.assertIn("review_pass_filter", err)
        self.assertIn("imported by review_applied.py", err)

    def test_the_cli_exits_zero_on_a_complete_checkout(self):
        rc, out, err = self.run_cli()
        self.assertEqual(rc, 0, err)
        self.assertIn("every module the runner imports resolves", out)


class ReportTest(unittest.TestCase):
    def test_a_clean_check_reports_nothing(self):
        self.assertEqual(_preflight.report([], "/tmp/local_ci.py"), [])

    def test_the_report_names_every_missing_module(self):
        problems = [{"module": "review_pass_filter", "importer": "review_applied.py",
                     "why": "not in the runner checkout and not in the stdlib"},
                    {"module": "pr_template", "importer": "local_ci.py",
                     "why": "not in the runner checkout and not in the stdlib"}]
        lines = _preflight.report(problems, "/tmp/runner/local_ci.py")
        text = "\n".join(lines)
        self.assertIn("review_pass_filter", text)
        self.assertIn("pr_template", text)
        self.assertIn("refusing to tick", lines[0])
        self.assertIn("binds to None", text)


class RootsTest(unittest.TestCase):
    def test_the_shared_scripts_directory_is_searched(self):
        roots = _preflight.roots_for("/opt/local-ci/scripts/local-ci/local_ci.py")
        self.assertEqual(
            roots,
            ("/opt/local-ci/scripts/local-ci", "/opt/local-ci/scripts"))

    def test_a_std_module_is_not_reported_as_missing(self):
        """`sys` and `time` are compiled in: they have no file on the path."""
        self.assertIn("sys", _preflight._stdlib_names())
        self.assertIn("time", _preflight._stdlib_names())
        self.assertIn("json", _preflight._stdlib_names())


if __name__ == "__main__":
    unittest.main()
