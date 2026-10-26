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


class Dig4990QuotedMarkerTest(unittest.TestCase):
    """DIG-4990: a comment that only *shows* or *names* the in-session marker is
    not a review pass.

    Nine CI-triage notes on 26 Oct 2026 described the marker and therefore
    contained it; on #6465 and #6453 that was the only marker comment, so the
    next ``review-applied`` recheck would have posted a success with no review
    having happened. The same shape, one file over, is #6197: text that talks
    about a marker is not the marker.
    """

    MARKER = _mod.AGENT_REVIEW_MARKER

    def _passes(self, body):
        def run_rest(path):
            if path.endswith("/reviews"):
                return []
            return [{"user": {"login": "chrizefan"},
                     "body": body, "created_at": "2026-10-26T07:21:21Z"}]
        return _mod.fetch_review_passes(1, "o/r", lambda argv: None, run_rest)

    def test_a_marker_quoted_in_a_fence_is_not_a_pass(self):
        body = "The review template is:\n\n```\n%s\n```\n" % self.MARKER
        self.assertEqual(self._passes(body), [])

    def test_a_marker_quoted_in_an_inline_span_is_not_a_pass(self):
        body = "It needs a comment with `%s` in it.\n" % self.MARKER
        self.assertEqual(self._passes(body), [])

    def test_a_marker_named_in_a_sentence_is_not_a_pass(self):
        body = "A review pass posts %s and a reviewed:agent claim.\n" % self.MARKER
        self.assertEqual(self._passes(body), [])

    def test_a_marker_on_its_own_line_with_provenance_is_still_a_pass(self):
        body = ("%s <!-- digithings-review agent=c59332b4-a0ef-4a6a-8027-"
                "5c081486f899 head=e6cf8603888c9e877396063a83e6bf87e36510de -->\n"
                "reviewed:agent\n" % self.MARKER)
        passes = self._passes(body)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["kind"], "in-session")

    def test_a_quoted_marker_creates_no_blocking_verdict(self):
        body = ("The note ended:\n\n```\n%s\nReview verdict: changes requested\n```\n"
                % self.MARKER)
        self.assertIsNone(_mod.comment_state(body))
        self.assertEqual(_mod.blocking_verdicts([], [
            {"id": 1, "user": {"login": "chrizefan"}, "body": body,
             "created_at": "2026-10-26T07:21:21Z"}]), [])

    def test_a_marker_named_in_a_sentence_creates_no_blocking_verdict(self):
        body = ("The gate looks for %s and then reads its Review verdict: "
                "changes requested line.\n" % self.MARKER)
        self.assertIsNone(_mod.comment_state(body))

    def test_a_quoted_power_pack_marker_posts_no_verdict(self):
        body = ("```\n<!-- opencode-power-pack:code-review verdict=approve "
                "scope=@6aab1cea -->\n```\n")
        self.assertIsNone(_mod.marker_state(body))
        self.assertIsNone(_mod.comment_state(body))

    def test_a_posted_power_pack_marker_still_posts_a_verdict(self):
        body = "<!-- opencode-power-pack:code-review verdict=approve scope=@6aab1cea -->\n"
        self.assertEqual(_mod.marker_state(body), "APPROVED")

    def test_a_quoted_verdict_line_does_not_clear_a_real_change_request(self):
        # The posted marker is real, so this *is* a review comment. The template
        # it copies into a fence must not outrank the line the reviewer wrote.
        body = ("%s\n\n```\nReview verdict: approve\n```\n\n"
                "Review verdict: changes requested\n" % self.MARKER)
        self.assertEqual(_mod.comment_state(body), "CHANGES_REQUESTED")
        self.assertEqual(
            len(_mod.blocking_verdicts([], [
                {"id": 1, "user": {"login": "seat-b"}, "body": body,
                 "created_at": "2026-10-26T07:21:21Z"}])),
            1,
        )

    def test_a_quoted_verdict_line_creates_no_block(self):
        body = ("%s\n\n```\nReview verdict: changes requested\n```\n\n"
                "Review verdict: approve\n" % self.MARKER)
        self.assertEqual(_mod.comment_state(body), "APPROVED")


class Dig4990StaleHeadPassTest(unittest.TestCase):
    """DIG-4990: a pass that names another head is not a pass for this head.

    On 26 Oct 2026 ``review-applied`` posted success at ``#6451``'s and
    ``#6460``'s new heads on the 10:12Z review pass, which named the heads
    both branches had already left. ``_filter_passes`` only dropped a pass
    posted inside the push window; nothing read the ``head=`` the provenance
    marker carries.
    """

    HEAD = "eeacc41a87acf3cdfdf10ddb7550c1ec46c49c53"
    OLD = "8c43d62fbc236ea69c79e89e377361391b8c89b0"

    def _body(self, head=None):
        provenance = ("<!-- digithings-review agent=c59332b4-a0ef-4a6a-8027-"
                      "5c081486f899 run=ee40d570-48d4-412a-9c43-9b84572c53aa")
        if head:
            provenance += " head=" + head
        provenance += " -->"
        return ("%s\n%s\nreviewed:agent\n\nReview verdict: approve\n"
                % (_mod.AGENT_REVIEW_MARKER, provenance))

    def _context(self):
        return {"login": "chrizefan", "body": "", "identity": {},
                "push_times": {self.HEAD: "2026-10-26T17:40:00Z"},
                "head": self.HEAD}

    def _pass(self, body):
        return {"kind": "in-session", "author": "digiforge-board",
                "has_comments": True, "at": "2026-10-26T10:12:16Z",
                "commit_id": None, "body": body}

    def test_a_pass_naming_another_head_is_dropped(self):
        kept, dropped = _mod._filter_passes(
            [self._pass(self._body(self.OLD))], 6451, self._context())
        self.assertEqual(kept, [])
        self.assertEqual([d["reason"] for d in dropped], ["names another head"])

    def test_a_pass_naming_this_head_is_kept(self):
        kept, dropped = _mod._filter_passes(
            [self._pass(self._body(self.HEAD))], 6451, self._context())
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, [])

    def test_a_short_form_of_this_head_is_kept(self):
        kept, _ = _mod._filter_passes(
            [self._pass(self._body(self.HEAD[:12]))], 6451, self._context())
        self.assertEqual(len(kept), 1)

    def test_a_pass_without_provenance_is_kept(self):
        kept, _ = _mod._filter_passes(
            [self._pass(self._body())], 6451, self._context())
        self.assertEqual(len(kept), 1)

    def test_a_head_quoted_in_code_does_not_drop_a_pass(self):
        body = self._body() + "\nThe head was:\n\n```\nhead=%s\n```\n" % self.OLD
        kept, _ = _mod._filter_passes([self._pass(body)], 6451, self._context())
        self.assertEqual(len(kept), 1)

    def test_an_unknown_head_does_not_drop_a_pass(self):
        context = dict(self._context(), head=None)
        kept, _ = _mod._filter_passes(
            [self._pass(self._body(self.OLD))], 6451, context)
        self.assertEqual(len(kept), 1)

    def test_fetch_keeps_only_the_pass_that_names_the_head(self):
        stale = {"user": {"login": "digiforge-board"},
                 "body": self._body(self.OLD),
                 "created_at": "2026-10-26T10:12:16Z"}
        current = {"user": {"login": "digiforge-board"},
                   "body": self._body(self.HEAD),
                   "created_at": "2026-10-27T09:00:00Z"}

        def run_rest(path):
            if path.endswith("/reviews"):
                return []
            if "/issues/" in path:
                return [stale, current]
            return {"head": {"sha": self.HEAD}, "user": {"login": "chrizefan"},
                    "body": "", "commits": []}

        passes = _mod.fetch_review_passes(6451, "o/r", lambda argv: None, run_rest)
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["at"], "2026-10-27T09:00:00Z")

    def test_only_the_stale_pass_leaves_the_check_red(self):
        def run_rest(path):
            if path.endswith("/reviews"):
                return []
            if "/issues/" in path:
                return [{"user": {"login": "digiforge-board"},
                         "body": self._body(self.OLD),
                         "created_at": "2026-10-26T10:12:16Z"}]
            return {"head": {"sha": self.HEAD}, "user": {"login": "chrizefan"},
                    "body": "", "commits": []}

        passes = _mod.fetch_review_passes(6451, "o/r", lambda argv: None, run_rest)
        ok, message, _ = _mod.evaluate(passes, [])
        self.assertFalse(ok)
        self.assertIn("no review pass", message)


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
        # The corpus is a rolling 24 h window, so the entry is stamped now: a
        # snapshot timestamp would fall out of the window when the producer
        # reads it and the copy would not be detected.
        rpf.record_reviews(5942, [(None, body)], path=corpus)
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


class Dig4646ProducerTest(unittest.TestCase):
    """DIG-4646: the producer reads what the fleet writes, and stops crashing.

    Two defects in the producer half of this branch:

    A. the REST pull payload carries ``commits`` as a *count*, so reading it as
       the list of commits crashed the producer on every PR;
    B. the verdict leg never ran and the producer's own parser could not read
       the fleet's "Review verdict: ..." lines.
    """

    #: The QA lane's real change request (digithings-ai/digithings #5994).
    FLEET_CHANGES_BODY = (
        "<!-- in-session-review -->\n"
        "\n"
        "Review verdict: changes requested — digithings #5994 (DIG-4459) "
        "@ `36fad1f939fbf9c2897894f205bfabc83c61096a`\n"
        "\n"
        "Reviewed: head `36fad1f9` (base `1e82af3f`), 6 files, +206/-6.\n"
    )

    #: The QA lane's real approval (comment 6285506816 on #5990): the verdict
    #: line comes first, the marker below it.
    FLEET_APPROVE_BODY = (
        "Review verdict: approve - digithings #5990 "
        "@ `8e0750df22e626159cc4829b415dbffa2b0fc251`\n"
        "\n"
        "<!-- in-session-review -->\n"
        "\n"
        "Findings here.\n"
    )

    def _comment(self, body, at="2026-10-20T10:00:00Z", cid=1, login="chrizefan"):
        return {"id": cid, "user": {"login": login}, "body": body, "created_at": at}

    def test_the_rest_pull_shape_with_a_commit_count_does_not_crash(self):
        # The REST pull payload carries `commits` as a count, not as the list of
        # commits. Reading the count crashed the producer on every PR.
        def run_rest(path):
            if path.endswith("/pulls/4242"):
                return {"number": 4242, "body": "Work.",
                        "commits": 3,
                        "user": {"login": "chrizefan"}}
            return []

        def run_gh(argv):
            if "commits" in argv[-1]:
                return [{"sha": "a" * 40,
                         "commit": {"committer": {"date": "2026-10-20T09:00:00Z"}}}]
            return None

        context = _mod._pr_context(4242, "o/r", run_gh, run_rest)
        self.assertEqual(context["login"], "chrizefan")
        self.assertEqual(context["identity"], {})

    def test_a_pull_with_a_commit_count_does_not_crash_the_thread_read(self):
        payload = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": []}}}}}

        def run_gh(argv):
            if "graphql" in argv:
                return payload
            if "pulls/4243/commits" in argv[-1]:
                return []
            return {"number": 4243, "body": "", "commits": 3}

        threads = _mod.fetch_threads_graphql(4243, "o/r", run_gh)
        self.assertEqual(threads, [])

    def test_the_fleet_change_request_is_read(self):
        self.assertEqual(_mod.in_session_state(self.FLEET_CHANGES_BODY),
                         "CHANGES_REQUESTED")

    def test_the_fleet_approve_is_read(self):
        self.assertEqual(_mod.in_session_state(self.FLEET_APPROVE_BODY), "APPROVED")

    def test_prose_about_a_verdict_is_not_a_verdict(self):
        self.assertEqual(_mod.in_session_state("The verdict: changes look fine."),
                         "COMMENTED")

    def test_blocking_verdicts_finds_the_fleet_change_request(self):
        blocks = _mod.blocking_verdicts(
            [], [self._comment(self.FLEET_CHANGES_BODY)])
        self.assertEqual(len(blocks), 1)
        self.assertIn("chrizefan", blocks[0])

    def test_an_unnamed_approval_does_not_clear_the_change_request(self):
        # #5975 on 20 Oct 2026: changes requested, changes requested, approve -
        # all under one login, none naming a seat. The approval is another
        # seat's, so the change request still blocks.
        comments = [
            self._comment(self.FLEET_CHANGES_BODY, "2026-10-20T10:00:00Z", 1),
            self._comment(self.FLEET_CHANGES_BODY, "2026-10-20T11:00:00Z", 2),
            self._comment(self.FLEET_APPROVE_BODY, "2026-10-20T12:00:00Z", 3),
        ]
        blocks = _mod.blocking_verdicts([], comments)
        self.assertEqual(len(blocks), 1)

    def test_an_approval_that_names_a_seat_clears_the_change_request(self):
        comments = [
            self._comment(self.FLEET_CHANGES_BODY, "2026-10-20T10:00:00Z", 1),
            self._comment(self.FLEET_APPROVE_BODY + "\n<!-- dt-seat agent=seat-a -->\n",
                          "2026-10-20T12:00:00Z", 2),
        ]
        self.assertEqual(_mod.blocking_verdicts([], comments), [])

    def test_evaluate_fails_closed_on_a_change_request(self):
        ok, msg, open_ids = _mod.evaluate(
            [INSESSION], [], verdict_blocks=["chrizefan (in-session comment 1)"])
        self.assertFalse(ok)
        self.assertIn("changes requested, not cleared", msg)
        self.assertIn("chrizefan", msg)

    def test_evaluate_fails_closed_when_the_verdicts_could_not_be_read(self):
        ok, msg, open_ids = _mod.evaluate(
            [INSESSION], [], verdict_error="the reviews or comments could not be read")
        self.assertFalse(ok)
        self.assertIn("could not read the review verdicts", msg)
        self.assertNotIn("changes requested", msg)

    def test_the_queue_and_the_producer_read_the_same_body(self):
        # One definition of a verdict line: the queue's parser and the
        # producer's parser must not disagree about the fleet's own words.
        #
        # The queue on develop reads a "Review verdict: ..." line (its
        # _PROSE_VERDICT_RE) and a provenance marker's verdict= field; the
        # producer reads the same shapes through the shared parser in
        # scripts/review_pass_filter.py. The two are compared on the bodies the
        # QA lane actually writes.
        mq = _load_merge_queue()
        for body, expected, state in (
            (self.FLEET_CHANGES_BODY, "changes_requested", "CHANGES_REQUESTED"),
            (self.FLEET_APPROVE_BODY, "approve", "APPROVED"),
        ):
            prose = mq._prose_verdict(body)
            self.assertIsNotNone(prose, body)
            self.assertEqual(prose[0], expected, body)
            self.assertEqual(_mod.in_session_state(body), state, body)

    def test_a_verdict_shape_the_queue_cannot_read_is_still_read_by_the_producer(self):
        # The queue on develop reads "Review verdict: ..." lines and markers
        # only. The producer also reads the "**Verdict: CHANGES**" shape, so it
        # is the stricter of the two. The producer's `review-applied` status is
        # a required check on develop, so the stricter reading is the one that
        # gates the merge: a shape the queue cannot read cannot unblock a PR.
        mq = _load_merge_queue()
        body = "**Verdict: CHANGES** (narrow)"
        self.assertIsNone(mq._prose_verdict(body))
        self.assertEqual(_mod.in_session_state(body), "CHANGES_REQUESTED")

    def test_prose_that_only_mentions_a_verdict_is_not_a_verdict(self):
        mq = _load_merge_queue()
        body = "The verdict: changes look fine."
        self.assertIsNone(mq._prose_verdict(body))
        self.assertEqual(_mod.in_session_state(body), "COMMENTED")


def _load_merge_queue():
    """The queue module, loaded by path (scripts/ is not a package)."""
    root = os.path.abspath(os.path.join(_SCRIPTS, "..", ".."))
    spec = importlib.util.spec_from_file_location(
        "merge_queue", os.path.join(root, "scripts", "merge_queue.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["merge_queue"] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
