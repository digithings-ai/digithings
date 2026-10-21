"""Pin the first-party code-review verdict producer (DIG-2281).

The merge queue reads a verdict out of a pull-request comment, and only from
inside the `opencode-power-pack:code-review` marker. Before this producer
existed nothing in this company wrote that marker, so the gate parsed a
verdict no producer emitted: a review could say "changes requested" in prose,
be submitted as `COMMENTED`, and the queue merged anyway. That is what
happened on `digithings-ai/twelve-x#347` on 2026-10-07.

The failure directions pinned here:

* a blocking verdict must post the marker AND submit a `REQUEST_CHANGES`
  review — a comment alone leaves the review state empty, so the queue sees
  nothing to block on;
* the marker must be a bare line carrying the full 40-character lowercase
  head sha — the queue compares the whole string against commit ids, so a
  short prefix posts a verdict that never matches, and a fenced marker is
  still read as a live verdict;
* the marker the producer writes must be the marker the queue parses
  (round-trip against `scripts/merge_queue.py`, not a copy of its regex);
* re-running against one head must not stack a second review or a second
  comment, and a new head must be able to receive its own review;
* a pull request the reviewing login authored cannot be blocked with
  `REQUEST_CHANGES` (GitHub answers 422), so the verdict has to fall back to
  a `COMMENT` review instead of failing;
* an approval must post a marker and submit no review at all — a tool that
  auto-approves hands the queue a pass nobody earned.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.scripts.conftest import GhStub, gh_rule

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "post_review_verdict.py"
QUEUE_SCRIPT = REPO_ROOT / "scripts" / "merge_queue.py"

REPO = "digithings-ai/digithings"
PR = 17
HEAD_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_SHA = "89abcdef0123456789abcdef0123456789abcdef"
LOGIN = "chrizefan"

EXIT_OK = 0
EXIT_USAGE = 2


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _run(*args: str, body: str = "One finding blocks approval.") -> subprocess.CompletedProcess[str]:
    """Run the producer as a command, the way a review step would."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", REPO, "--pr", str(PR), *args],
        capture_output=True,
        text=True,
    )


def _run_with_body(tmp_path: Path, *args: str, body: str = "One finding blocks approval."):
    findings = tmp_path / "findings.md"
    findings.write_text(body, encoding="utf-8")
    return _run(*args, body=body)


def _base_rules() -> list[dict[str, Any]]:
    """Rules for the reads the producer always does, plus a comment POST."""
    return [
        gh_rule(r"api user", stdout={"login": LOGIN}),
        gh_rule(r"--paginate repos/[^ ]*/issues/%d/comments" % PR, stdout=[]),
        gh_rule(r"--paginate repos/[^ ]*/pulls/%d/reviews" % PR, stdout=[]),
        gh_rule(r"--method POST repos/[^ ]*/issues/%d/comments" % PR, stdout={"id": 4242}),
    ]


def _review_post_rule(**kwargs: Any) -> dict[str, Any]:
    return gh_rule(r"event=REQUEST_CHANGES", stdout={"id": 99}, **kwargs)


def _posted_comment_body(stub: GhStub) -> str:
    """The body the producer posted as a pull-request comment."""
    calls = stub.matching("--method POST repos/%s/issues/%d/comments" % (REPO, PR))
    assert len(calls) == 1, calls
    argv = calls[0]
    field = argv[argv.index("-f") + 1]
    assert field.startswith("body=")
    return field[len("body=") :]


def _comment_post_count(stub: GhStub) -> int:
    return len(stub.matching("--method POST repos/%s/issues/%d/comments" % (REPO, PR)))


def _review_post_count(stub: GhStub) -> int:
    return len(stub.matching("event=REQUEST_CHANGES"))


def test_blocking_verdict_posts_the_marker_and_a_changes_requested_review(
    tmp_path: Path, gh_stub: Any
) -> None:
    """The gate needs both halves: the marker and the review state."""
    stub = gh_stub(*_base_rules(), _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    result = json.loads(done.stdout)
    assert result["verdict"] == "changes_requested"
    assert result["comment"] == "posted"
    assert result["review"] == "submitted"

    body = _posted_comment_body(stub)
    assert body.splitlines()[0] == (
        "<!-- opencode-power-pack:code-review "
        f"verdict=changes_requested scope=@{HEAD_SHA} -->"
    )

    review_calls = stub.matching("event=REQUEST_CHANGES")
    assert len(review_calls) == 1
    argv = review_calls[0]
    assert f"repos/{REPO}/pulls/{PR}/reviews" in " ".join(argv)
    assert f"commit_id={HEAD_SHA}" in argv


def test_the_marker_written_is_the_marker_the_merge_queue_parses(tmp_path: Path) -> None:
    """Round-trip against the queue's own parser, not a copy of its regex."""
    producer = _load(SCRIPT, "post_review_verdict_under_test")
    queue = _load(QUEUE_SCRIPT, "merge_queue_under_test")

    body = producer.comment_body("changes_requested", HEAD_SHA)
    assert queue._posted_verdict({"body": body}) == ("changes_requested", HEAD_SHA)

    approved = producer.comment_body("approved", HEAD_SHA)
    assert queue._posted_verdict({"body": approved}) == ("approved", HEAD_SHA)


def test_the_marker_is_a_bare_line_carrying_the_full_head_sha(tmp_path: Path) -> None:
    """A fence does not hide the marker, so a quoted example is a live verdict."""
    producer = _load(SCRIPT, "post_review_verdict_bare_line")
    body = producer.comment_body("changes_requested", HEAD_SHA)
    assert "```" not in body
    assert body.count("<!--") == 1
    assert HEAD_SHA in body.splitlines()[0]


def test_a_short_sha_is_refused(tmp_path: Path, gh_stub: Any) -> None:
    """The queue compares the whole string; a prefix posts a verdict that never matches."""
    stub = gh_stub(*_base_rules(), _review_post_rule())
    done = _run(
        "--head-sha",
        HEAD_SHA[:7],
        "--verdict",
        "changes_requested",
    )
    assert done.returncode == EXIT_USAGE
    assert "40-character" in done.stderr
    assert _comment_post_count(stub) == 0


def test_an_unknown_verdict_is_refused(tmp_path: Path, gh_stub: Any) -> None:
    """A misspelled verdict neither blocks nor clears; refuse it at the source."""
    stub = gh_stub(*_base_rules(), _review_post_rule())
    done = _run("--head-sha", HEAD_SHA, "--verdict", "looks-fine-to-me")
    assert done.returncode == EXIT_USAGE
    assert "unknown verdict" in done.stderr
    assert _comment_post_count(stub) == 0


def test_rerunning_on_one_head_does_not_stack_a_second_review(
    tmp_path: Path, gh_stub: Any
) -> None:
    """Idempotency per head: the same head must not collect reviews."""
    rules = _base_rules()
    rules[1] = gh_rule(
        r"--paginate repos/[^ ]*/issues/%d/comments" % PR,
        stdout=[],
    )
    rules[2] = gh_rule(
        r"--paginate repos/[^ ]*/pulls/%d/reviews" % PR,
        stdout=[
            {
                "id": 7,
                "state": "CHANGES_REQUESTED",
                "commit_id": HEAD_SHA,
                "user": {"login": LOGIN},
            }
        ],
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    result = json.loads(done.stdout)
    assert result["review"] == "already-present"
    assert _review_post_count(stub) == 0


def test_a_new_head_may_receive_its_own_review(tmp_path: Path, gh_stub: Any) -> None:
    """A review is pinned to a head: the next head is a new verdict to post."""
    rules = _base_rules()
    rules[2] = gh_rule(
        r"--paginate repos/[^ ]*/pulls/%d/reviews" % PR,
        stdout=[
            {
                "id": 7,
                "state": "CHANGES_REQUESTED",
                "commit_id": OTHER_SHA,
                "user": {"login": LOGIN},
            }
        ],
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert json.loads(done.stdout)["review"] == "submitted"
    assert _review_post_count(stub) == 1


def test_a_review_by_another_login_does_not_count_as_ours(
    tmp_path: Path, gh_stub: Any
) -> None:
    """Only our own review on this head blocks a repeat of ours."""
    rules = _base_rules()
    rules[2] = gh_rule(
        r"--paginate repos/[^ ]*/pulls/%d/reviews" % PR,
        stdout=[
            {
                "id": 7,
                "state": "CHANGES_REQUESTED",
                "commit_id": HEAD_SHA,
                "user": {"login": "someone-else"},
            }
        ],
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert json.loads(done.stdout)["review"] == "submitted"
    assert _review_post_count(stub) == 1


def test_a_self_authored_pull_request_falls_back_to_a_comment_review(
    tmp_path: Path, gh_stub: Any
) -> None:
    """GitHub answers 422 when the reviewing login authored the pull request."""
    rules = _base_rules()
    rules.append(
        gh_rule(
            r"event=REQUEST_CHANGES",
            stderr=(
                "HTTP 422: Validation Failed "
                "(https://api.github.com/repos/o/r/pulls/17/reviews) "
                "Can not request changes on your own pull request"
            ),
            exit_code=1,
        )
    )
    rules.append(gh_rule(r"event=COMMENT", stdout={"id": 100}))
    stub = gh_stub(*rules)
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    result = json.loads(done.stdout)
    assert result["review"] == "submitted-as-comment"
    # The marker is still posted: it is the record the queue can see.
    assert _comment_post_count(stub) == 1
    assert _review_post_count(stub) == 1
    assert stub.matching("event=COMMENT")


def test_an_approval_posts_a_marker_and_no_review(tmp_path: Path, gh_stub: Any) -> None:
    """A tool that auto-approves hands the queue a pass nobody earned."""
    stub = gh_stub(*_base_rules())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "approved",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    result = json.loads(done.stdout)
    assert result["verdict"] == "approved"
    assert result["review"] == "not-submitted"
    assert _comment_post_count(stub) == 1
    assert not stub.matching("pulls/%d/reviews" % PR)


def test_an_identical_marker_comment_is_not_reposted(tmp_path: Path, gh_stub: Any) -> None:
    """One marker per head: re-running must not leave duplicate comments."""
    producer = _load(SCRIPT, "post_review_verdict_idempotent")
    existing = producer.comment_body("changes_requested", HEAD_SHA)
    rules = _base_rules()
    rules[1] = gh_rule(
        r"--paginate repos/[^ ]*/issues/%d/comments" % PR,
        stdout=[{"id": 5, "body": existing, "user": {"login": LOGIN}}],
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert json.loads(done.stdout)["comment"] == "unchanged"
    assert _comment_post_count(stub) == 0


def test_a_changed_marker_comment_is_updated_in_place(tmp_path: Path, gh_stub: Any) -> None:
    """A changed body is patched, not posted twice."""
    producer = _load(SCRIPT, "post_review_verdict_patch")
    existing = producer.comment_body("changes_requested", HEAD_SHA).replace(
        "changes requested", "previously changes requested"
    )
    rules = _base_rules()
    rules[1] = gh_rule(
        r"--paginate repos/[^ ]*/issues/%d/comments" % PR,
        stdout=[{"id": 5, "body": existing, "user": {"login": LOGIN}}],
    )
    rules.append(
        gh_rule(
            r"--method PATCH repos/[^ ]*/issues/comments/5",
            stdout={"id": 5},
        )
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert json.loads(done.stdout)["comment"] == "updated"
    assert _comment_post_count(stub) == 0
    assert stub.matching("--method PATCH repos/%s/issues/comments/5" % REPO)


def test_a_marker_from_another_login_is_not_ours_to_update(
    tmp_path: Path, gh_stub: Any
) -> None:
    """A comment by someone else is not ours to patch; post our own."""
    producer = _load(SCRIPT, "post_review_verdict_other_login")
    existing = producer.comment_body("changes_requested", HEAD_SHA)
    rules = _base_rules()
    rules[1] = gh_rule(
        r"--paginate repos/[^ ]*/issues/%d/comments" % PR,
        stdout=[{"id": 5, "body": existing, "user": {"login": "someone-else"}}],
    )
    stub = gh_stub(*rules, _review_post_rule())
    done = _run_with_body(
        tmp_path,
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--body-file",
        str(tmp_path / "findings.md"),
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert json.loads(done.stdout)["comment"] == "posted"
    assert _comment_post_count(stub) == 1


def test_the_dry_run_writes_nothing(tmp_path: Path, gh_stub: Any) -> None:
    """A dry run shows the exact marker without touching the pull request."""
    stub = gh_stub()
    done = _run(
        "--head-sha",
        HEAD_SHA,
        "--verdict",
        "changes_requested",
        "--dry-run",
    )
    assert done.returncode == EXIT_OK, done.stderr
    payload = json.loads(done.stdout)
    assert payload["comment_body"].splitlines()[0] == (
        "<!-- opencode-power-pack:code-review "
        f"verdict=changes_requested scope=@{HEAD_SHA} -->"
    )
    assert not stub.calls
