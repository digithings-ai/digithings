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


class Dig4631ReviewPassTest(unittest.TestCase):
    """DIG-4631: evidence that must not count as a review pass.

    Three shapes were counted as a review pass on 20 Oct 2026 and let five PRs
    into ``develop``: a thread the PR's own author resolved, a review posted
    inside the 60 s window of the push it covers, and a review whose text
    repeats a review on another PR.
    """

    def _context(self, pushed_at="2026-10-20T13:27:15Z", commit="a3b894ebb1"):
        return {
            "login": "chrizefan",
            "body": "Fixes DIG-4506",
            "identity": {},
            "push_times": {commit: pushed_at},
        }

    def test_a_pass_inside_the_push_window_is_dropped(self):
        passes = [
            {
                "kind": "in-session",
                "author": "chrizefan",
                "has_comments": True,
                "at": "2026-10-20T13:27:20Z",
                "commit_id": "a3b894ebb1",
                "body": "The lock-session write needs the field on the model too.",
            }
        ]
        kept, dropped = _mod._filter_passes(passes, 5968, self._context())
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)

    def test_a_pass_outside_the_push_window_survives(self):
        passes = [
            {
                "kind": "in-session",
                "author": "chrizefan",
                "has_comments": True,
                "at": "2026-10-20T13:20:31Z",
                "commit_id": "509228c713",
                "body": "The lock-session write needs the field on the model too.",
            }
        ]
        context = self._context("2026-10-20T13:13:14Z", "509228c713")
        kept, dropped = _mod._filter_passes(passes, 6013, context)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_a_copied_pass_is_dropped(self):
        import tempfile

        import review_pass_filter as rpf

        body = (
            "**Cutover slice review** (local source-control loop, sctl). Scope: the "
            "twelve-x Cloudflare cutover and the deploy lane it needs."
        )
        folder = tempfile.mkdtemp()
        corpus = os.path.join(folder, "corpus.json")
        rpf.record_reviews(5942, [("2026-10-20T13:05:43Z", body)], path=corpus)
        previous = os.environ.get(rpf.CORPUS_PATH_ENV)
        os.environ[rpf.CORPUS_PATH_ENV] = corpus
        try:
            passes = [
                {
                    "kind": "in-session",
                    "author": "chrizefan",
                    "has_comments": True,
                    "at": "2026-10-20T13:06:49Z",
                    "commit_id": "181b357f05",
                    "body": body,
                }
            ]
            context = self._context("2026-10-20T13:11:49Z", "1f0f9ee6b1")
            kept, dropped = _mod._filter_passes(passes, 5947, context)
        finally:
            if previous is None:
                os.environ.pop(rpf.CORPUS_PATH_ENV, None)
            else:
                os.environ[rpf.CORPUS_PATH_ENV] = previous
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)

    def test_an_author_resolved_thread_is_not_cleared(self):
        thread = {
            "id": "PRRT_x",
            "is_resolved": True,
            "author_resolved": True,
            "comments": [
                {"author": "chrizefan", "created_at": "2026-10-20T13:20:31Z"}
            ],
        }
        ok, msg, open_ids = _mod.evaluate([INSESSION], [thread])
        self.assertFalse(ok)
        self.assertIn("unresolved thread", msg)
        self.assertEqual(open_ids, ["PRRT_x"])
