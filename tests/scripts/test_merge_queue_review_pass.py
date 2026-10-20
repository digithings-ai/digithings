#!/usr/bin/env python3
"""Unit tests for the merge queue's review-pass gate (DIG-4631).

The queue must not accept as a review pass: a review the PR's own author
resolved, a review posted inside the 60 s window of the push it claims to
cover, or a review whose text repeats a review on another PR.

``tests/scripts/fixtures/dig4631_cutover_reviews.json`` is the read-only
snapshot of the seven PRs that carried the canned review on 20 Oct 2026.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "merge_queue.py"
_spec = importlib.util.spec_from_file_location("merge_queue", SCRIPT)
merge_queue = importlib.util.module_from_spec(_spec)
sys.modules["merge_queue"] = merge_queue
_spec.loader.exec_module(merge_queue)

FIXTURE = REPO_ROOT / "tests" / "scripts" / "fixtures" / "dig4631_cutover_reviews.json"
with FIXTURE.open(encoding="utf-8") as _handle:
    SNAPSHOT = json.load(_handle)
PRS = {int(pr["number"]): pr for pr in SNAPSHOT["prs"]}


def _pr(number):
    """The PR as the queue's list projection serves it."""
    snap = PRS[number]
    return {
        "number": number,
        "author": {"login": snap["author"]},
        "body": "Fixes DIG-4506",
        "commits": [{"oid": snap["head_sha"], "committedDate": snap["head_pushed_at"]}],
        "reviews": [
            {
                "body": review["body"],
                "submittedAt": review["at"],
                "commit": {"oid": review["commit"]},
                "state": "COMMENTED",
            }
            for review in snap["reviews"]
        ],
        "comments": [],
    }


def _corpus_of(*numbers):
    entries = []
    for number in numbers:
        snap = PRS[number]
        texts = [(review["at"], review["body"]) for review in snap["reviews"]]
        entries.extend(merge_queue.rpf.corpus_entries(number, texts))
    return entries


# --------------------------------------------------------------------------
# Rule 3: a review copied from another PR is not a review
# --------------------------------------------------------------------------


def test_a_copied_review_is_refused():
    pr = _pr(5947)
    corpus = _corpus_of(5942)
    reasons = merge_queue._gate_review_pass_evidence(pr, corpus)
    assert reasons
    assert "repeats the review on #5942" in reasons[0]


def test_the_first_copy_is_not_a_duplicate_of_anything():
    pr = _pr(5942)
    reasons = merge_queue._gate_review_pass_evidence(pr, [])
    assert reasons == []


def test_a_genuine_review_on_the_pr_is_kept():
    pr = _pr(6013)
    pr["reviews"].append(
        {
            "body": "The lock-session write needs the field on the model too.",
            "submittedAt": "2026-10-20T13:20:31Z",
            "commit": {"oid": "509228c713"},
            "state": "COMMENTED",
        }
    )
    reasons = merge_queue._gate_review_pass_evidence(pr, _corpus_of(5942, 5947))
    assert reasons == []


# --------------------------------------------------------------------------
# Rule 2: a review posted inside the push window is not a review
# --------------------------------------------------------------------------


def test_a_review_inside_the_push_window_is_refused():
    pr = _pr(5968)
    # only the review on the head commit: the ones on older commits cover an
    # earlier tree and are not inside the head push window.
    pr["reviews"] = [pr["reviews"][-1]]
    reasons = merge_queue._gate_review_pass_evidence(pr, [])
    assert reasons
    assert "after the push it claims to cover" in reasons[0]


def test_a_review_on_an_older_commit_is_outside_the_push_window():
    pr = _pr(5968)
    pr["reviews"] = [pr["reviews"][0]]
    reasons = merge_queue._gate_review_pass_evidence(pr, [])
    assert reasons == []


def test_a_review_outside_the_push_window_is_kept():
    pr = _pr(6013)
    reasons = merge_queue._gate_review_pass_evidence(pr, [])
    assert reasons == []


# --------------------------------------------------------------------------
# Rule 1: a thread resolved by the PR's own author stays open
# --------------------------------------------------------------------------


def _thread(resolved_by, body="Verified: scoped to the cutover slice."):
    return {
        "isResolved": True,
        "isOutdated": False,
        "path": "scripts/deploy-digithings-stack-cloudflare.yml",
        "resolved_by_login": resolved_by,
        "comments": [{"author_login": "chrizefan", "body": body, "created_at": "2026-10-20T13:20:31Z"}],
    }


def test_an_author_resolved_thread_stays_open():
    pr = _pr(5968)
    open_threads = merge_queue._open_threads([_thread("chrizefan")], pr)
    assert len(open_threads) == 1


def test_a_thread_resolved_by_a_bot_is_closed():
    pr = _pr(5968)
    open_threads = merge_queue._open_threads([_thread("github-advanced-security[bot]")], pr)
    assert open_threads == []


def test_the_thread_gate_names_the_author_resolved_threads():
    pr = _pr(5968)
    pr["reviewThreads"] = [_thread("chrizefan"), _thread("chrizefan")]
    reasons = merge_queue._gate_review_threads(pr, None)
    assert reasons
    assert "resolved by the PR's own author" in reasons[0]


# --------------------------------------------------------------------------
# The corpus the queue reads
# --------------------------------------------------------------------------


def test_the_queue_corpus_holds_the_reviews_it_has_seen():
    prs = [_pr(5942), _pr(5947)]
    entries = merge_queue._review_corpus(prs)
    numbers = {entry.get("pr") for entry in entries}
    assert 5942 in numbers
    assert 5947 in numbers
    for entry in entries:
        assert entry.get("norm")
        assert isinstance(entry.get("at"), float)
