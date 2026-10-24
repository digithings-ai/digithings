#!/usr/bin/env python3
"""Unit tests for the review-pass filter (DIG-4631).

Three shapes of review evidence were counted as a review pass on 20 Oct 2026 and
let five PRs into ``develop`` without a real review:

1. a review thread the PR's own author resolved;
2. a review posted within 60 s of the push it claims to cover;
3. a review whose text repeats a review on another PR.

``tests/scripts/fixtures/dig4631_cutover_reviews.json`` is the read-only
snapshot of the seven PRs that carried the canned review; it is test data.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "review_pass_filter.py"
_spec = importlib.util.spec_from_file_location("review_pass_filter", SCRIPT)
rpf = importlib.util.module_from_spec(_spec)
sys.modules["review_pass_filter"] = rpf
_spec.loader.exec_module(rpf)

FIXTURE = REPO_ROOT / "tests" / "scripts" / "fixtures" / "dig4631_cutover_reviews.json"
with FIXTURE.open(encoding="utf-8") as _handle:
    SNAPSHOT = json.load(_handle)
PRS = {int(pr["number"]): pr for pr in SNAPSHOT["prs"]}

#: The clock the snapshot was taken at. The rolling corpus only keeps entries
#: from the last 24 h, so a test that reads the corpus has to read it at the
#: snapshot's own clock: two days after the snapshot every fixture entry is
#: older than the window and the corpus reads as empty. The corpus code takes
#: ``now=`` for exactly this; the tests pass the snapshot's clock instead of
#: reading the wall clock.
FIXTURE_NOW = rpf.parse_ts("2026-10-20T13:30:00Z")


def _thread(resolved_by, note="Verified: scoped to the cutover slice.", **extra):
    thread = {
        "is_resolved": True,
        "resolved_by": resolved_by,
        "comments": [{"author": "chrizefan", "body": note}],
    }
    thread.update(extra)
    return thread


# --------------------------------------------------------------------------
# Rule 1: a thread resolved by the PR's own author is not a review pass
# --------------------------------------------------------------------------


def test_thread_resolved_by_the_author_login_is_author_resolved():
    thread = _thread("chrizefan")
    assert rpf.thread_resolved_by_author(thread, "chrizefan") is True


def test_thread_resolved_by_another_login_is_not_author_resolved():
    thread = _thread("github-advanced-security[bot]")
    assert rpf.thread_resolved_by_author(thread, "chrizefan") is False


def test_thread_note_naming_another_seat_is_not_author_resolved():
    note = "<!-- dt-seat agent=code-reviewer run=run-2 -->\nFixed on my branch."
    thread = _thread("chrizefan", note)
    author = {"seat": frozenset({"author-seat"})}
    assert rpf.thread_resolved_by_author(thread, "chrizefan", author) is False


def test_thread_note_naming_the_authors_own_seat_is_author_resolved():
    note = "<!-- dt-seat agent=author-seat -->\nFixed on my branch."
    thread = _thread("chrizefan", note)
    author = {"seat": frozenset({"author-seat"})}
    assert rpf.thread_resolved_by_author(thread, "chrizefan", author) is True


def test_an_unknown_author_seat_stays_the_conservative_answer():
    note = "<!-- dt-seat agent=code-reviewer run=run-2 -->\nFixed on my branch."
    thread = _thread("chrizefan", note)
    assert rpf.thread_resolved_by_author(thread, "chrizefan") is True


def test_unresolved_thread_is_never_author_resolved():
    thread = _thread("chrizefan", is_resolved=False)
    assert rpf.thread_resolved_by_author(thread, "chrizefan") is False


def test_thread_keys_are_accepted_in_both_spellings():
    queue_shape = {
        "isResolved": True,
        "resolved_by_login": "chrizefan",
        "comments": [{"author_login": "chrizefan", "body": "done"}],
    }
    assert rpf.thread_resolved_by_author(queue_shape, "chrizefan") is True


def test_fixture_threads_of_5968_are_author_resolved():
    pr = PRS[5968]
    assert pr["threads"]
    for thread in pr["threads"]:
        shaped = {
            "is_resolved": thread["is_resolved"],
            "resolved_by": thread["resolved_by"],
            "comments": [{"author": "chrizefan", "body": thread["comments"][0]["body"]}],
        }
        assert rpf.thread_resolved_by_author(shaped, pr["author"]) is True


def test_fixture_codeql_thread_of_5948_is_not_author_resolved():
    thread = PRS[5948]["threads"][0]
    shaped = {
        "is_resolved": thread["is_resolved"],
        "resolved_by": thread["resolved_by"],
        "comments": [{"author": "chrizefan", "body": thread["comments"][0]["body"]}],
    }
    assert rpf.thread_resolved_by_author(shaped, PRS[5948]["author"]) is False


# --------------------------------------------------------------------------
# Rule 2: a review posted within 60 s of the push it covers is not a review
# --------------------------------------------------------------------------


def test_review_three_seconds_after_the_push_is_too_close():
    assert rpf.review_too_close_to_push("2026-10-20T13:27:20Z", "2026-10-20T13:27:15Z") is True


def test_review_minutes_after_the_push_is_not_too_close():
    assert (
        rpf.review_too_close_to_push("2026-10-20T13:25:56Z", "2026-10-20T13:13:14Z") is False
    )


def test_a_review_before_the_push_is_also_too_close():
    assert rpf.review_too_close_to_push("2026-10-20T13:27:10Z", "2026-10-20T13:27:15Z") is True


def test_fixture_marker_review_of_5968_is_inside_the_push_window():
    pr = PRS[5968]
    marker = pr["reviews"][-1]
    assert marker["commit"] == pr["head_sha"]
    assert rpf.review_too_close_to_push(marker["at"], pr["head_pushed_at"]) is True


def test_fixture_marker_review_of_6013_is_outside_the_push_window():
    pr = PRS[6013]
    marker = pr["reviews"][-1]
    assert marker["commit"] == pr["head_sha"]
    assert rpf.review_too_close_to_push(marker["at"], pr["head_pushed_at"]) is False


# --------------------------------------------------------------------------
# Rule 3: a review copied from another PR is not a review
# --------------------------------------------------------------------------


def test_identical_text_on_another_pr_is_a_duplicate():
    first = PRS[5942]["reviews"][0]
    entries = rpf.corpus_entries(5942, [(first["at"], first["body"])])
    second = PRS[5947]["reviews"][0]
    matches = rpf.duplicate_reviews(
        rpf.normalise_review_text(second["body"]), 5947, entries, now=FIXTURE_NOW
    )
    assert matches
    assert matches[0]["pr"] == 5942
    assert matches[0]["ratio"] >= 0.9


def test_the_same_review_on_its_own_pr_is_not_a_duplicate():
    first = PRS[5942]["reviews"][0]
    entries = rpf.corpus_entries(5942, [(first["at"], first["body"])])
    matches = rpf.duplicate_reviews(
        rpf.normalise_review_text(first["body"]), 5942, entries, now=FIXTURE_NOW
    )
    assert matches == []


def test_a_different_review_is_not_a_duplicate():
    first = PRS[5942]["reviews"][0]
    other = PRS[6013]["reviews"][1]
    entries = rpf.corpus_entries(5942, [(first["at"], first["body"])])
    matches = rpf.duplicate_reviews(
        rpf.normalise_review_text(other["body"]), 6013, entries, now=FIXTURE_NOW
    )
    assert matches == []


def test_every_copy_of_the_canned_review_after_the_first_is_a_duplicate():
    ordered = sorted(PRS.values(), key=lambda pr: pr["reviews"][0]["at"])
    entries = []
    for pr in ordered:
        body = pr["reviews"][0]["body"]
        norm = rpf.normalise_review_text(body)
        matches = rpf.duplicate_reviews(norm, pr["number"], entries, now=FIXTURE_NOW)
        if entries:
            assert matches, "PR %s copies an earlier review" % pr["number"]
        entries.extend(rpf.corpus_entries(pr["number"], [(pr["reviews"][0]["at"], body)]))
    assert len(entries) == len(ordered)


def test_normalising_drops_the_marker_and_the_shas():
    body = "<!-- in-session-review -->\n\nFixed in `cf1b9d750f` (pushed as a fast-forward)."
    norm = rpf.normalise_review_text(body)
    assert "in-session-review" not in norm
    assert "cf1b9d750f" not in norm


# --------------------------------------------------------------------------
# The rolling corpus
# --------------------------------------------------------------------------


def test_corpus_round_trip_with_iso_timestamps(tmp_path):
    path = str(tmp_path / "corpus.json")
    entries = rpf.record_reviews(
        5942,
        [("2026-10-20T13:05:43Z", PRS[5942]["reviews"][0]["body"])],
        path=path,
        now=FIXTURE_NOW,
    )
    assert len(entries) == 1
    assert isinstance(entries[0]["at"], float)
    loaded = rpf.load_corpus(path, now=FIXTURE_NOW)
    assert len(loaded) == 1
    assert loaded[0]["pr"] == 5942


def test_a_broken_corpus_file_is_an_empty_corpus(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text("{not json", encoding="utf-8")
    assert rpf.load_corpus(str(path)) == []


def test_a_missing_corpus_file_is_an_empty_corpus(tmp_path):
    assert rpf.load_corpus(str(tmp_path / "absent.json")) == []


def test_the_corpus_path_can_be_overridden(monkeypatch, tmp_path):
    target = tmp_path / "elsewhere.json"
    monkeypatch.setenv(rpf.CORPUS_PATH_ENV, str(target))
    assert rpf.corpus_path() == str(target)


# --------------------------------------------------------------------------
# The independence arm: strict by default, off the switch for now
# --------------------------------------------------------------------------


def _identity(text):
    return rpf.identity_from_text(text)


def test_a_strict_rule_refuses_a_pr_that_names_no_authoring_seat():
    reason = rpf.independence_reason({}, _identity("<!-- dt-seat agent=seat-b -->"))
    assert reason is not None
    assert "names no authoring seat or session" in reason


def test_the_strict_rule_refuses_a_review_that_names_no_seat():
    reason = rpf.independence_reason(
        _identity("<!-- dt-seat agent=seat-a -->"), _identity("nothing here")
    )
    assert reason is not None
    assert "names no reviewer seat" in reason


def test_the_strict_rule_refuses_a_review_that_shares_the_authoring_seat():
    reason = rpf.independence_reason(
        _identity("<!-- dt-seat agent=seat-a -->"), _identity("<!-- dt-seat agent=seat-a -->")
    )
    assert reason is not None
    assert "authoring seat (seat-a)" in reason


def test_a_missing_marker_does_not_refuse_when_the_switch_is_off():
    assert rpf.independence_reason({}, {}, require_markers=False) is None
    assert (
        rpf.independence_reason(
            _identity("<!-- dt-seat agent=seat-a -->"),
            _identity("nothing here"),
            require_markers=False,
        )
        is None
    )


def test_a_proven_self_review_is_refused_even_when_the_switch_is_off():
    reason = rpf.independence_reason(
        _identity("<!-- dt-seat agent=seat-a -->"),
        _identity("<!-- dt-seat agent=seat-a -->"),
        require_markers=False,
    )
    assert reason is not None
    assert "authoring seat (seat-a)" in reason


# --------------------------------------------------------------------------
# The verdict line: one parser, so the queue and the producer agree (DIG-4646)
# --------------------------------------------------------------------------

#: The QA lane's real change request (digithings-ai/digithings #5994, comment
#: 6280947283 on #5968 is the same shape). The verdict line carries a leading
#: word ("Review") and an em dash before the PR reference.
FLEET_CHANGES_BODY = (
    "<!-- in-session-review -->\n"
    "\n"
    "Review verdict: changes requested — digithings #5994 (DIG-4459) "
    "@ `36fad1f939fbf9c2897894f205bfabc83c61096a`\n"
    "\n"
    "Reviewed: head `36fad1f9` (base `1e82af3f`), 6 files, +206/-6.\n"
)

#: The QA lane's real approval (comment 6285506816 on #5990): the verdict line
#: comes first, then the marker.
FLEET_APPROVE_BODY = (
    "Review verdict: approve - digithings #5990 "
    "@ `8e0750df22e626159cc4829b415dbffa2b0fc251`\n"
    "\n"
    "<!-- in-session-review -->\n"
    "\n"
    "Findings here.\n"
)


def test_the_fleet_change_request_line_is_read():
    assert rpf.in_session_verdict_state(FLEET_CHANGES_BODY) == "CHANGES_REQUESTED"


def test_the_fleet_approve_line_is_read():
    assert rpf.in_session_verdict_state(FLEET_APPROVE_BODY) == "APPROVED"


def test_a_bare_verdict_line_is_read():
    assert rpf.in_session_verdict_state("**Verdict: CHANGES** (narrow)") == "CHANGES_REQUESTED"


def test_prose_about_a_verdict_is_not_a_verdict():
    assert rpf.in_session_verdict_state("The verdict: changes look fine to me.") == "COMMENTED"


def test_a_verdict_identity_is_the_seat_it_names():
    assert rpf.verdict_identity("<!-- dt-seat agent=seat-a -->") == ("seat", "seat-a")


def test_a_verdict_identity_falls_back_to_the_session():
    assert rpf.verdict_identity("<!-- dt-seat session=s-1 -->") == ("session", "s-1")


def test_an_unnamed_verdict_has_no_identity():
    assert rpf.verdict_identity("no marker here") == ("", "")
    assert rpf.verdict_identity("no marker here", {"login": "chrizefan"}) == ("", "")


def test_a_bot_login_is_its_own_identity():
    assert rpf.verdict_identity("bot review", {"login": "coderabbitai[bot]"}) == (
        "bot",
        "coderabbitai",
    )


def test_a_dismissal_clears_only_its_own_change_request():
    assert rpf.clears_change_request("DISMISSED", ("seat", "seat-a"), ("seat", "seat-a"))
    assert not rpf.clears_change_request("DISMISSED", ("seat", "seat-b"), ("seat", "seat-a"))


def test_a_named_change_request_is_cleared_by_the_same_identity_only():
    assert rpf.clears_change_request("APPROVED", ("seat", "seat-a"), ("seat", "seat-a"))
    assert not rpf.clears_change_request("APPROVED", ("seat", "seat-b"), ("seat", "seat-a"))
    assert not rpf.clears_change_request("APPROVED", ("", ""), ("seat", "seat-a"))


def test_an_unnamed_change_request_is_cleared_by_a_verdict_that_names_a_seat():
    assert rpf.clears_change_request("APPROVED", ("seat", "seat-a"), ("", ""))
    assert not rpf.clears_change_request("APPROVED", ("", ""), ("", ""))


def _event(at, seq, login, identity, state):
    return (at, seq, login, identity, state, "review %d" % seq)


def test_an_unnamed_change_request_survives_another_unnamed_approval():
    events = [
        _event("2026-10-20T10:00:00Z", 1, "chrizefan", ("", ""), "CHANGES_REQUESTED"),
        _event("2026-10-20T11:00:00Z", 2, "chrizefan", ("", ""), "APPROVED"),
    ]
    outstanding = rpf.outstanding_change_requests(events)
    assert len(outstanding) == 1
    assert outstanding[0][0] == "chrizefan"


def test_the_same_seats_approval_clears_its_own_change_request():
    events = [
        _event("2026-10-20T10:00:00Z", 1, "chrizefan", ("seat", "seat-a"), "CHANGES_REQUESTED"),
        _event("2026-10-20T11:00:00Z", 2, "chrizefan", ("seat", "seat-a"), "APPROVED"),
    ]
    assert rpf.outstanding_change_requests(events) == []


def test_another_seats_approval_does_not_clear_a_named_change_request():
    events = [
        _event("2026-10-20T10:00:00Z", 1, "chrizefan", ("seat", "seat-a"), "CHANGES_REQUESTED"),
        _event("2026-10-20T11:00:00Z", 2, "chrizefan", ("seat", "seat-b"), "APPROVED"),
    ]
    assert len(rpf.outstanding_change_requests(events)) == 1


def test_only_the_same_login_clears_a_change_request():
    events = [
        _event("2026-10-20T10:00:00Z", 1, "chrizefan", ("seat", "seat-a"), "CHANGES_REQUESTED"),
        _event("2026-10-20T11:00:00Z", 2, "someone-else", ("seat", "seat-a"), "APPROVED"),
    ]
    assert len(rpf.outstanding_change_requests(events)) == 1


def test_a_pull_payload_with_a_commit_count_does_not_crash():
    # The REST pull payload carries `commits` as a count, not as the list of
    # commits. Reading the count crashed the producer on every PR (DIG-4646).
    assert rpf._commit_texts({"commits": 3}) == []
    assert rpf._commit_texts({"commits": 3, "body": "x"}) == []
    assert rpf.author_identity({"commits": 3, "body": "<!-- dt-seat agent=seat-a -->"}) == {
        "seat": frozenset({"seat-a"})
    }
