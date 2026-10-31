#!/usr/bin/env python3
"""Unit tests for pr-template (DIG-3842 scope update). Stdlib only:
`/usr/bin/python3 -m unittest test_pr_template -v`."""
import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))
_spec = importlib.util.spec_from_file_location(
    "pr_template", os.path.join(_SCRIPTS, "pr_template.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["pr_template"] = _mod
_spec.loader.exec_module(_mod)

FULL = """## Linked issue

Fixes #3842

---

## Component

- [x] config / infra

## Change Type

- [x] chore — build, CI, deps

## Summary

Adds a template check to local-ci and drops the DCO gate per the scope update.

---

## Review

n/a

---

## Testing Evidence

```
Ran 12 tests in 0.001s

OK
```

---

## Documentation Updated

- [ ] n/a

---

## Human Gate

**Is human review required?** No
"""


class TemplateTest(unittest.TestCase):
    def test_full_body_passes(self):
        ok, failures = _mod.check_template(FULL)
        self.assertTrue(ok, failures)
        self.assertEqual(failures, [])

    def test_empty_body_fails_every_section(self):
        ok, failures = _mod.check_template("")
        self.assertFalse(ok)
        self.assertEqual(len(failures), 6)

    def test_bare_template_fails(self):
        body = ("## Linked issue\n\nFixes #\n\n## Component\n\n- [ ] digigraph\n\n"
                "## Change Type\n\n- [ ] feat\n\n## Summary\n\n<!-- 2-4 sentences -->\n\n"
                "## Testing Evidence\n\n```\n# Paste output\n\n```\n\n"
                "## Human Gate\n\n**Is human review required?** Yes / No\n")
        ok, failures = _mod.check_template(body)
        self.assertFalse(ok)
        self.assertIn("linked-issue: 'Fixes #' names no issue number", failures)
        self.assertIn("component: no checked box", failures)
        self.assertIn("summary: no prose (need ~2-4 sentences)", failures)

    def test_closes_and_resolves_accepted(self):
        for word in ("Closes #12", "Resolves #34"):
            b = FULL.replace("Fixes #3842", word)
            ok, failures = _mod.check_template(b)
            self.assertTrue(ok, (word, failures))

    def test_paperclip_dig_linkage_accepted(self):
        # A Paperclip-tracked leaf legitimately has no GitHub issue number;
        # "Fixes DIG-3845" must satisfy linked-issue (DIG-3845 scope fix).
        for word in ("Fixes DIG-3845", "Closes DIG-12", "Resolves DIG-34"):
            b = FULL.replace("Fixes #3842", word)
            ok, failures = _mod.check_template(b)
            self.assertTrue(ok, (word, failures))
        # A bare "Fixes DIG-" with no number still fails.
        b = FULL.replace("Fixes #3842", "Fixes DIG-")
        ok, failures = _mod.check_template(b)
        self.assertFalse(ok)
        self.assertIn(
            "linked-issue: no 'Fixes|Closes|Resolves #<number>' line", failures)

    def test_summary_threshold(self):
        b = FULL.replace(
            "Adds a template check to local-ci and drops the DCO gate per the scope update.",
            "Too short.")
        ok, failures = _mod.check_template(b)
        self.assertFalse(ok)
        self.assertIn("summary: no prose (need ~2-4 sentences)", failures)

    def test_empty_evidence_fails(self):
        b = FULL.replace("Ran 12 tests in 0.001s\n\nOK\n", "")
        ok, failures = _mod.check_template(b)
        self.assertFalse(ok)
        self.assertIn("testing-evidence: fenced block is empty", failures)

    def test_human_gate_must_answer(self):
        for answer in ("Yes", "No", "yes", "NO"):
            b = FULL.replace("**Is human review required?** No",
                              "**Is human review required?** " + answer)
            ok, failures = _mod.check_template(b)
            self.assertTrue(ok, (answer, failures))
        b = FULL.replace("**Is human review required?** No",
                          "**Is human review required?**")
        ok, failures = _mod.check_template(b)
        self.assertFalse(ok)
        self.assertIn("human-gate: 'Is human review required?' unanswered (Yes/No)",
                      failures)

    def test_each_section_pins_its_own_failure(self):
        # Drop exactly one piece at a time; exactly that failure must appear.
        cases = [
            (FULL.replace("Fixes #3842", "see above"),
             "linked-issue: no 'Fixes|Closes|Resolves #<number>' line"),
            (FULL.replace("- [x] config / infra", "- [ ] config / infra"),
             "component: no checked box"),
            (FULL.replace("- [x] chore — build, CI, deps", "- [ ] chore — build, CI, deps"),
             "change-type: no checked box"),
        ]
        for body, want in cases:
            ok, failures = _mod.check_template(body)
            self.assertFalse(ok, want)
            self.assertIn(want, failures)


class SeverityTest(unittest.TestCase):
    """Only the Human Gate blocks; every other finding is a warning (plan P1-2)."""

    GATE_YES_WITH_BOX = FULL.replace(
        "## Human Gate\n",
        "## Human Gate\n\n- [x] Auth or crypto modified (digikey signing)\n")

    def test_paperwork_findings_are_warnings(self):
        _ok, failures = _mod.check_template(FULL.replace("Fixes #3842", "Fixes #"))
        blocking, warnings = _mod.split_findings(failures)
        self.assertEqual(blocking, [])
        self.assertEqual(warnings, ["linked-issue: 'Fixes #' names no issue number"])

    def test_the_bare_template_blocks_only_on_the_human_gate(self):
        tpl = os.path.join(_SCRIPTS, "..", "..", ".github", "PULL_REQUEST_TEMPLATE.md")
        with open(tpl) as f:
            _ok, failures = _mod.check_template(f.read())
        blocking, warnings = _mod.split_findings(failures)
        self.assertEqual([b.split(":")[0] for b in blocking], ["human-gate"])
        self.assertIn("linked-issue: 'Fixes #' names no issue number", warnings)

    def test_unanswered_human_gate_blocks(self):
        b = FULL.replace("**Is human review required?** No", "**Is human review required?**")
        _ok, failures = _mod.check_template(b)
        blocking, _warnings = _mod.split_findings(failures)
        self.assertEqual(len(blocking), 1)

    def test_untouched_yes_slash_no_is_unanswered(self):
        b = FULL.replace("required?** No", "required?** Yes / No")
        _ok, failures = _mod.check_template(b)
        self.assertIn("human-gate: 'Is human review required?' unanswered (Yes/No)",
                      _mod.split_findings(failures)[0])

    def test_checked_box_answered_no_blocks(self):
        """#6603 / #6601: a checked Human Gate box must not ride through on 'No'."""
        _ok, failures = _mod.check_template(self.GATE_YES_WITH_BOX)
        self.assertEqual(_mod.split_findings(failures)[0],
                         ["human-gate: a Human Gate box is checked but the answer is No"])

    def test_checked_box_answered_yes_passes(self):
        b = self.GATE_YES_WITH_BOX.replace("required?** No", "required?** Yes")
        ok, failures = _mod.check_template(b)
        self.assertTrue(ok, failures)

    def test_full_body_has_no_findings(self):
        self.assertEqual(_mod.split_findings(_mod.check_template(FULL)[1]), ([], []))


if __name__ == "__main__":
    unittest.main()
