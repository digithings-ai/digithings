#!/usr/bin/env python3
"""Unit tests for review-applied (DIG-3842). Stdlib only:
`/usr/bin/python3 -m unittest test_review_applied -v`."""
import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.abspath(os.path.join(_HERE, "..", "..", "scripts", "local-ci"))
_spec = importlib.util.spec_from_file_location(
    "review_applied", os.path.join(_SCRIPTS, "review_applied.py"))
_mod = importlib.util.module_from_spec(_spec)
sys.modules["review_applied"] = _mod
_spec.loader.exec_module(_mod)


def thr(tid, resolved, comments):
    return {"id": tid, "is_resolved": resolved, "comments": comments}


def com(author, at):
    return {"author": author, "created_at": at}


BOT = {"kind": "bot", "author": "coderabbitai[bot]", "has_comments": True}
INSESSION = {"kind": "in-session", "author": "chrizefan", "has_comments": True}


class EvaluateTest(unittest.TestCase):
    def test_no_review_fails(self):
        ok, msg, open_ids = _mod.evaluate([], [])
        self.assertFalse(ok)
        self.assertIn("no review pass", msg)

    def test_no_review_with_threads_names_them(self):
        t = thr("PRRT_x", False, [com("coderabbitai[bot]", "2026-10-15T01:00:00Z")])
        ok, msg, open_ids = _mod.evaluate([], [t])
        self.assertFalse(ok)
        self.assertEqual(open_ids, ["PRRT_x"])

    def test_all_resolved_passes(self):
        passes = [BOT]
        threads = [
            thr("PRRT_a", True, [com("coderabbitai[bot]", "2026-10-15T01:00:00Z")]),
            thr("PRRT_b", True, [com("copilot[bot]", "2026-10-15T02:00:00Z")]),
        ]
        ok, msg, open_ids = _mod.evaluate(passes, threads)
        self.assertTrue(ok)
        self.assertEqual(open_ids, [])

    def test_unresolved_no_fix_no_reply_fails(self):
        t = thr("PRRT_x", False, [com("coderabbitai[bot]", "2026-10-15T01:00:00Z")])
        ok, msg, open_ids = _mod.evaluate([BOT], [t])
        self.assertFalse(ok)
        self.assertEqual(open_ids, ["PRRT_x"])
        self.assertIn("PRRT_x", msg)

    def test_fix_commit_and_reply_passes(self):
        t = thr("PRRT_x", False, [
            com("coderabbitai[bot]", "2026-10-15T01:00:00Z"),
            com("chrizefan", "2026-10-15T03:00:00Z"),
        ])
        ok, msg, open_ids = _mod.evaluate(
            [BOT], [t], fix_commit_ats=["2026-10-15T02:00:00Z"],
            reviewer_logins={"coderabbitai[bot]"})
        self.assertTrue(ok)
        self.assertEqual(open_ids, [])

    def test_fix_commit_without_reply_fails(self):
        # AND is pinned: a fix commit alone does not clear the thread.
        t = thr("PRRT_x", False, [com("coderabbitai[bot]", "2026-10-15T01:00:00Z")])
        ok, _, open_ids = _mod.evaluate(
            [BOT], [t], fix_commit_ats=["2026-10-15T02:00:00Z"])
        self.assertFalse(ok)
        self.assertEqual(open_ids, ["PRRT_x"])

    def test_reply_without_fix_commit_fails(self):
        # AND is pinned the other way: a reply alone does not clear it either.
        t = thr("PRRT_x", False, [
            com("coderabbitai[bot]", "2026-10-15T01:00:00Z"),
            com("chrizefan", "2026-10-15T03:00:00Z"),
        ])
        ok, _, open_ids = _mod.evaluate(
            [BOT], [t], reviewer_logins={"coderabbitai[bot]"})
        self.assertFalse(ok)
        self.assertEqual(open_ids, ["PRRT_x"])

    def test_fix_commit_before_comment_does_not_count(self):
        t = thr("PRRT_x", False, [
            com("coderabbitai[bot]", "2026-10-15T05:00:00Z"),
            com("chrizefan", "2026-10-15T06:00:00Z"),
        ])
        ok, _, open_ids = _mod.evaluate(
            [BOT], [t], fix_commit_ats=["2026-10-15T02:00:00Z"],
            reviewer_logins={"coderabbitai[bot]"})
        self.assertFalse(ok)

    def test_bot_followup_is_not_a_reply(self):
        t = thr("PRRT_x", False, [
            com("coderabbitai[bot]", "2026-10-15T01:00:00Z"),
            com("coderabbitai[bot]", "2026-10-15T03:00:00Z"),
        ])
        ok, _, open_ids = _mod.evaluate(
            [BOT], [t], fix_commit_ats=["2026-10-15T02:00:00Z"],
            reviewer_logins={"coderabbitai[bot]"})
        self.assertFalse(ok)


class BotRecognitionTest(unittest.TestCase):
    def test_login_forms(self):
        for login in ("coderabbitai", "coderabbitai[bot]", "Cursor[bot]",
                      "copilot", "github-copilot[bot]", "claude",
                      "github-advanced-security[bot]", "bugbot"):
            self.assertTrue(_mod.is_reviewer_bot(login), login)

    def test_non_reviewers_rejected(self):
        for login in ("chrizefan", "github-actions[bot]", "dependabot[bot]", "", None):
            self.assertFalse(_mod.is_reviewer_bot(login), repr(login))

    def test_human_approval_counts_as_pass(self):
        ok, _, _ = _mod.evaluate(
            [{"kind": "human", "author": "someone", "has_comments": True}], [])
        self.assertTrue(ok)

    def test_commentless_pass_does_not_count(self):
        ok, _, _ = _mod.evaluate(
            [{"kind": "bot", "author": "coderabbitai[bot]", "has_comments": False}], [])
        self.assertFalse(ok)

    def test_bot_check_success_counts(self):
        ok, _, _ = _mod.evaluate(
            [], [], check_runs=[{"name": "Cursor Bugbot", "conclusion": "success"}])
        self.assertTrue(ok)

    def test_bot_check_neutral_does_not_count(self):
        for conclusion in ("neutral", "skipped", "failure", None):
            ok, _, _ = _mod.evaluate(
                [], [], check_runs=[{"name": "Cursor Bugbot", "conclusion": conclusion}])
            self.assertFalse(ok, conclusion)


class FetchTest(unittest.TestCase):
    def test_in_session_marker_pass(self):
        def run_rest(path):
            if path.endswith("/reviews"):
                return []
            return [{"user": {"login": "chrizefan"},
                     "body": "findings below\n<!-- in-session-review -->"}]
        passes = _mod.fetch_review_passes(1, "o/r", lambda argv: None, run_rest)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["kind"], "in-session")

    def test_bot_review_body_pass(self):
        def run_rest(path):
            if path.endswith("/reviews"):
                return [{"state": "COMMENTED", "body": "nit: ...",
                         "user": {"login": "coderabbitai[bot]"}}]
            return []
        passes = _mod.fetch_review_passes(1, "o/r", lambda argv: None, run_rest)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["kind"], "bot")

    def test_empty_review_body_no_pass(self):
        def run_rest(path):
            if path.endswith("/reviews"):
                return [{"state": "COMMENTED", "body": "",
                         "user": {"login": "github-advanced-security[bot]"}}]
            return []
        self.assertEqual(
            _mod.fetch_review_passes(1, "o/r", lambda argv: None, run_rest), [])

    def test_threads_graphql_shape(self):
        payload = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
            {"id": "PRRT_1", "isResolved": True,
             "comments": {"nodes": [
                 {"createdAt": "2026-10-15T01:00:00Z",
                  "author": {"login": "copilot[bot]"}, "body": "x",
                  "commit": {"oid": "a" * 40, "committedDate": "2026-10-15T01:00:00Z"}}]}}]}}}}}
        threads = _mod.fetch_threads_graphql(1, "o/r", lambda argv: payload)
        self.assertEqual(len(threads), 1)
        self.assertTrue(threads[0]["is_resolved"])
        self.assertEqual(threads[0]["comments"][0]["author"], "copilot[bot]")

    def test_threads_graphql_failure_is_none(self):
        self.assertIsNone(_mod.fetch_threads_graphql(1, "o/r", lambda argv: None))


if __name__ == "__main__":
    unittest.main()
