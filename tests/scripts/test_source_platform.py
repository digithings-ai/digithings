#!/usr/bin/env python3
"""Unit tests for the warn-only source-platform check. Stdlib only, from
tests/scripts: `/usr/bin/python3 -m unittest test_source_platform -v`."""

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
_SCRIPTS = os.path.join(_ROOT, "scripts", "local-ci")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_SCRIPTS, filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sp = _load("source_platform", "source_platform.py")
pr_template = _load("pr_template", "pr_template.py")
# A private name, so this file never replaces the module test_local_ci loads.
local_ci = _load("local_ci_for_source_platform", "local_ci.py")

TEMPLATE = os.path.join(_ROOT, ".github", "PULL_REQUEST_TEMPLATE.md")


def msg(*trailers, subject="feat(x): a change", body="Why it changes."):
    text = f"{subject}\n\n{body}\n"
    if trailers:
        text += "\n" + "\n".join(trailers) + "\n"
    return text


class TrailerTests(unittest.TestCase):
    def test_each_platform_is_accepted(self):
        for platform in sp.PLATFORMS:
            with self.subTest(platform=platform):
                self.assertEqual(sp.check_commit("a" * 40, msg(f"Source-Platform: {platform}")), [])

    def test_the_platforms_are_exactly_claude_cursor_grok_paperclip(self):
        self.assertEqual(sorted(sp.PLATFORMS), ["claude", "cursor", "grok", "paperclip"])

    def test_the_value_is_matched_without_regard_to_case(self):
        for value in ("Grok", "CLAUDE", "Cursor", "PaperClip"):
            with self.subTest(value=value):
                self.assertEqual(sp.check_commit("a" * 40, msg(f"Source-Platform: {value}")), [])
        self.assertEqual(
            sp.check_commit("a" * 40, msg("Source-Platform: Grok"), "grok@local.invalid"), []
        )

    def test_a_trailer_inside_a_code_fence_does_not_count(self):
        message = "feat(x): y\n\nWhy.\n\n```\nSource-Platform: grok\n```\n"
        self.assertEqual(sp.trailer_values(message), [])
        unclosed = "feat(x): y\n\n```\nexample\n\nSource-Platform: grok\n"
        self.assertEqual(sp.trailer_values(unclosed), [])

    def test_control_characters_are_stripped_before_logging(self):
        value = "gr\x1b[31mok\x07\u202e\x00"
        for warnings in (
            sp.check_commit("a" * 40, msg(f"Source-Platform: {value}x")),
            sp.check_body(f"Source-Platform: {value}x\n"),
        ):
            self.assertEqual(len(warnings), 1, warnings)
            self.assertIn("'Source-Platform: gr[31mokx'", warnings[0])
            for ch in ("\x1b", "\x07", "\u202e", "\x00"):
                self.assertNotIn(ch, warnings[0])

    def test_a_long_value_is_cut_before_logging(self):
        warnings = sp.check_body("Source-Platform: " + "x" * 500 + "\n")
        self.assertEqual(len(warnings), 1)
        self.assertLess(len(warnings[0]), 200)
        self.assertIn("x" * 40 + "...", warnings[0])

    def test_the_key_is_matched_without_regard_to_case(self):
        self.assertEqual(sp.trailer_values(msg("source-platform: grok")), ["grok"])

    def test_it_reads_the_trailer_among_other_trailers(self):
        message = msg(
            "Co-authored-by: a <a@local.invalid>",
            "Paperclip-Run-Id: r-1",
            "Source-Platform: paperclip",
        )
        self.assertEqual(sp.check_commit("b" * 40, message), [])

    def test_a_missing_trailer_warns(self):
        warnings = sp.check_commit("c" * 40, msg())
        self.assertEqual(len(warnings), 1)
        self.assertIn("no 'Source-Platform:' trailer", warnings[0])
        self.assertTrue(warnings[0].startswith("c" * 12 + ":"))

    def test_an_invalid_value_warns(self):
        for value in ("opencode", "grok bot", "chatgpt", ""):
            with self.subTest(value=value):
                warnings = sp.check_commit("d" * 40, msg(f"Source-Platform: {value}"))
                self.assertTrue(warnings, value)

    def test_a_trailer_in_the_body_not_the_last_paragraph_does_not_count(self):
        message = "feat(x): y\n\nSource-Platform: grok\n\nMore prose after it.\n"
        self.assertEqual(sp.trailer_values(message), [])
        self.assertTrue(sp.check_commit("e" * 40, message))

    def test_a_subject_only_commit_has_no_trailer(self):
        self.assertEqual(sp.trailer_values("Source-Platform: grok"), [])

    def test_two_different_values_warn(self):
        warnings = sp.check_commit(
            "f" * 40, msg("Source-Platform: grok", "Source-Platform: cursor")
        )
        self.assertTrue(any("2 different" in w for w in warnings))

    def test_a_trailer_that_disagrees_with_the_committer_warns(self):
        warnings = sp.check_commit("1" * 40, msg("Source-Platform: cursor"), "grok@local.invalid")
        self.assertEqual(len(warnings), 1)
        self.assertIn("committed as grok@local.invalid", warnings[0])

    def test_a_matching_or_unrelated_committer_is_fine(self):
        self.assertEqual(
            sp.check_commit("2" * 40, msg("Source-Platform: grok"), "grok@local.invalid"), []
        )
        self.assertEqual(
            sp.check_commit("3" * 40, msg("Source-Platform: grok"), "chris@local.invalid"), []
        )
        self.assertEqual(
            sp.check_commit("4" * 40, msg("Source-Platform: grok"), "someone@example.com"), []
        )


class GitLogTests(unittest.TestCase):
    def test_it_parses_the_format_it_asks_git_for(self):
        with tempfile.TemporaryDirectory() as root:
            env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

            def run(*a):
                return subprocess.run(
                    ["git", *a], cwd=root, env=env, check=True, capture_output=True, text=True
                ).stdout

            run("init", "-q")
            for who, message in (
                ("grok", msg("Source-Platform: grok")),
                ("cursor", msg()),
            ):
                run(
                    "-c",
                    f"user.name={who}",
                    "-c",
                    f"user.email={who}@local.invalid",
                    "commit",
                    "-q",
                    "--allow-empty",
                    "-m",
                    message,
                )
            log = run("log", "--format=" + sp.GIT_LOG_FORMAT)
            commits = sp.parse_git_log(log)
            self.assertEqual(
                [c[1] for c in commits], ["cursor@local.invalid", "grok@local.invalid"]
            )
            warnings = sp.check_commits(commits)
            self.assertEqual(len(warnings), 1)
            self.assertIn("no 'Source-Platform:' trailer", warnings[0])


class BodyTests(unittest.TestCase):
    def test_a_filled_field_is_fine(self):
        self.assertEqual(sp.check_body("## Source platform\n\nSource-Platform: grok\n"), [])

    def test_a_missing_or_empty_field_warns(self):
        self.assertTrue(sp.check_body(""))
        self.assertTrue(sp.check_body("## Source platform\n\nSource-Platform:\n"))

    def test_the_comment_does_not_count_as_the_field(self):
        self.assertTrue(sp.check_body("<!-- Source-Platform: grok -->\nSource-Platform:\n"))

    def test_an_empty_field_does_not_read_the_next_line(self):
        # \s* spanning the newline used to read `---` as the value.
        self.assertEqual(sp.body_values("Source-Platform:\n\n---\n"), [])
        self.assertEqual(sp.body_values("Source-Platform:   \ngrok\n"), [])
        warnings = sp.check_body("Source-Platform:\n\n---\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no 'Source-Platform:' line", warnings[0])

    def test_lines_inside_code_fences_do_not_count(self):
        for body in (
            "```\nSource-Platform: grok\n```\n",
            "~~~text\nSource-Platform: grok\n~~~\n",
            "````\n```\nSource-Platform: grok\n```\n````\n",
            "```\nnever closed\nSource-Platform: grok\n",
        ):
            with self.subTest(body=body):
                self.assertEqual(sp.body_values(body), [])
                self.assertTrue(sp.check_body(body))
        fenced_bad = "Source-Platform: grok\n\n```\nSource-Platform: chatgpt\n```\n"
        self.assertEqual(sp.check_body(fenced_bad), [])

    def test_the_body_value_is_matched_without_regard_to_case(self):
        self.assertEqual(sp.check_body("Source-Platform: Claude\n"), [])

    def test_an_invalid_value_warns(self):
        warnings = sp.check_body("Source-Platform: chatgpt\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("not one of", warnings[0])


def _filled_template():
    with open(TEMPLATE, encoding="utf-8") as f:
        text = f.read()
    text = text.replace("Fixes #\n", "Fixes #1\n", 1)
    text = text.replace("Source-Platform:\n", "Source-Platform: grok\n", 1)
    text = text.replace("- [ ] config / infra", "- [x] config / infra", 1)
    text = text.replace("- [ ] chore", "- [x] chore", 1)
    text = text.replace(
        "## Summary\n",
        "## Summary\n\nAdds the Source-Platform field to the template and a warn-only check.\n",
        1,
    )
    text = text.replace("```\n", "```\npytest: 1 passed\n", 1)
    text = text.replace(
        "**Is human review required?** Yes / No", "**Is human review required?** No", 1
    )
    return text


class TemplateTests(unittest.TestCase):
    def test_the_template_has_the_field_and_the_section(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("## Source platform", text)
        self.assertIn("\nSource-Platform:\n", text)
        # Unfilled, the new field warns, the way the unfilled template should.
        self.assertTrue(sp.check_body(text))

    def test_an_untouched_template_reads_as_empty(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(sp.body_values(text), [])
        self.assertEqual(
            sp.check_body(text),
            ["PR body: no 'Source-Platform:' line (one of claude, cursor, grok, paperclip)"],
        )

    def test_the_template_and_contributing_name_the_same_platforms(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            template = f.read()
        with open(os.path.join(_ROOT, "CONTRIBUTING.md"), encoding="utf-8") as f:
            contributing = f.read()
        self.assertIn("claude, cursor, grok or paperclip", template)
        self.assertIn("`claude`, `cursor`, `grok` or `paperclip`", contributing)
        for text in (template, contributing, sp.__doc__):
            self.assertNotIn("opencode", text)

    def test_contributing_says_which_value_each_seat_uses(self):
        with open(os.path.join(_ROOT, "CONTRIBUTING.md"), encoding="utf-8") as f:
            contributing = " ".join(f.read().split())
        self.assertIn("`grok` means Grok Bot", contributing)
        self.assertIn("Paperclip board seats use `paperclip`", contributing)

    def test_the_docs_say_the_value_is_not_evidence(self):
        with open(os.path.join(_ROOT, "CONTRIBUTING.md"), encoding="utf-8") as f:
            contributing = f.read()
        self.assertIn("unverified, self-declared claim", contributing)
        self.assertIn("No gate may\never treat it as evidence", contributing)
        self.assertIn("unverified, self-declared claim", sp.__doc__)
        self.assertIn("No gate may ever treat it as evidence", sp.__doc__)

    def test_a_filled_template_still_passes_the_template_gate(self):
        ok, failures = pr_template.check_template(_filled_template())
        self.assertTrue(ok, failures)
        self.assertEqual(sp.check_body(_filled_template()), [])

    def test_the_new_section_does_not_swallow_the_component_or_human_gate(self):
        body = _filled_template().replace("- [x] config / infra", "- [ ] config / infra", 1)
        ok, failures = pr_template.check_template(body)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("component") for f in failures))
        body = _filled_template().replace(
            "**Is human review required?** No", "**Is human review required?**", 1
        )
        ok, failures = pr_template.check_template(body)
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("human-gate") for f in failures))


class RunnerTests(unittest.TestCase):
    """The runner logs warnings and never turns them into a failure."""

    def setUp(self):
        self._sh, self._wt = local_ci.sh, local_ci.WT

    def tearDown(self):
        local_ci.sh, local_ci.WT = self._sh, self._wt

    def _fake_sh(self, log, shallow="false", log_rc=0):
        calls = []

        def fake(cmd, cwd=None, **kwargs):
            calls.append(cmd)
            if cmd[:2] == ["git", "rev-parse"]:
                return 0, shallow + "\n"
            if cmd[:2] == ["git", "log"]:
                return log_rc, log
            raise AssertionError(f"unexpected command {cmd}")

        local_ci.sh = fake
        return calls

    def test_it_warns_for_a_commit_without_the_trailer(self):
        log = (
            "a" * 40
            + "\x1fgrok@local.invalid\x1f"
            + msg("Source-Platform: grok")
            + "\x1e"
            + "b" * 40
            + "\x1fgrok@local.invalid\x1f"
            + msg()
            + "\x1e"
        )
        calls = self._fake_sh(log)
        out = io.StringIO()
        warnings = local_ci.source_platform_warnings(
            "Source-Platform: grok\n", "develop", "c" * 40, out
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("source-platform WARN: " + "b" * 12, out.getvalue())
        self.assertNotIn("FAIL", out.getvalue())
        self.assertIn("origin/develop.." + "c" * 40, calls[-1])
        self.assertIn("--no-merges", calls[-1])

    def test_a_clean_pr_writes_nothing(self):
        self._fake_sh(
            "a" * 40 + "\x1fgrok@local.invalid\x1f" + msg("Source-Platform: grok") + "\x1e"
        )
        out = io.StringIO()
        self.assertEqual(
            local_ci.source_platform_warnings("Source-Platform: grok", "develop", "c" * 40, out), []
        )
        self.assertEqual(out.getvalue(), "")

    def test_a_shallow_clone_or_unreadable_body_is_a_warning_not_an_error(self):
        self._fake_sh("", shallow="true")
        out = io.StringIO()
        warnings = local_ci.source_platform_warnings(None, "develop", "c" * 40, out)
        self.assertEqual(len(warnings), 2)
        self.assertIn("shallow clone", out.getvalue())

    def test_an_exception_is_swallowed_into_a_warning(self):
        def boom(*a, **k):
            raise RuntimeError("x")

        local_ci.sh = boom
        out = io.StringIO()
        warnings = local_ci.source_platform_warnings(
            "Source-Platform: grok", "develop", "c" * 40, out
        )
        self.assertEqual(warnings, ["not checked: RuntimeError"])

    def test_a_body_fetch_happens_inside_the_try(self):
        self._fake_sh("")
        saved = local_ci.pr_body

        def boom(pr):
            raise RuntimeError("gh broke")

        try:
            local_ci.pr_body = boom
            out = io.StringIO()
            warnings = local_ci.source_platform_warnings(
                None, "develop", "c" * 40, out, pr={"number": 1}
            )
            self.assertEqual(warnings, ["not checked: RuntimeError"])
            local_ci.pr_body = lambda pr: "Source-Platform: grok\n"
            out = io.StringIO()
            self.assertEqual(
                local_ci.source_platform_warnings(None, "develop", "c" * 40, out, pr={"number": 1}),
                [],
            )
        finally:
            local_ci.pr_body = saved

    def test_run_checks_never_calls_pr_body_outside_the_try(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn("else pr_body(pr), base, sha, out)", source)
        self.assertIn("source_platform_warnings(None, base, sha, out, pr=pr)", source)

    def test_the_runner_never_adds_it_to_the_failures(self):
        with open(os.path.join(_SCRIPTS, "local_ci.py"), encoding="utf-8") as f:
            source = f.read()
        self.assertNotIn('fails.append("source-platform', source)
        self.assertNotIn("source-platform FAIL", source)
        self.assertNotIn("source-platform", local_ci.METADATA_GATES)


if __name__ == "__main__":
    unittest.main()
