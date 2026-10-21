#!/usr/bin/env python3
"""Post the code-review verdict marker, and the blocking review that goes with it.

The merge queue reads a verdict out of a pull-request comment, and only from
inside the marker: `scripts/merge_queue.py` (`_posted_verdict`,
`_posted_verdict_reason`) parses
`<!-- opencode-power-pack:code-review ... -->` and treats a `changes_requested`
verdict against a commit that is still on the branch as a block.

Until this script existed, nothing in this company emitted that marker, so the
gate parsed a verdict no producer wrote. A review could say "changes requested"
in prose, be submitted as `COMMENTED`, and the queue merged anyway — which is
what happened on `digithings-ai/twelve-x#347` on 2026-10-07.

Two things this does that the third-party producer it replaces did not:

* it submits the blocking verdict as a real `REQUEST_CHANGES` review, so the
  pull request's review state blocks the merge as well as the marker does;
* it pins the verdict to the reviewed head commit (the marker's `scope=` and
  the review's `commit_id`), so a verdict cannot silently follow the branch
  onto a later head, and it is idempotent per head: re-running it against the
  same head posts no second review.

Deliberately not done here: it never submits an `APPROVE` review. An approval
is a human or in-session-review act, and a tool that auto-approves would hand
the queue a pass nobody earned. An `approved` marker is still posted, because
the queue honours the newest readable verdict, and that is how a block on the
same head is lifted once the findings are addressed.

Usage::

    scripts/post_review_verdict.py --repo digithings-ai/digithings --pr 347 \\
        --head-sha <full-40-char-sha> --verdict changes_requested \\
        --body-file findings.md
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

#: The marker namespace the merge queue parses. Keep it in step with
#: `_MARKER_RE` in `scripts/merge_queue.py` and with the example in
#: `docs/agents/CODE_REVIEW_POLICY.md`.
MARKER_NAMESPACE = "opencode-power-pack:code-review"

#: The queue compares the whole sha against 40-character commit ids, so a
#: short prefix parses and then never matches. Refuse it here rather than post
#: a verdict that silently does nothing.
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: Spellings the queue reads, and the single spelling this script emits.
VERDICT_ALIASES = {
    "changes_requested": "changes_requested",
    "changes-requested": "changes_requested",
    "changes_needed": "changes_requested",
    "changes-needed": "changes_requested",
    "approved": "approved",
    "approve": "approved",
}

BLOCKING_VERDICTS = frozenset({"changes_requested"})

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_OPERATIONAL = 1


class ProducerError(RuntimeError):
    """A failure the caller should see, with the underlying gh output."""

    def __init__(self, message: str, *, stderr: str = "", exit_code: int = EXIT_OPERATIONAL) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.exit_code = exit_code


def marker(verdict: str, head_sha: str) -> str:
    """The marker comment line the queue parses.

    `scope=` carries the reviewed commit as `@<full-40-char-sha>`, which is
    the shape `docs/agents/CODE_REVIEW_POLICY.md` documents. The marker is a
    bare line: a fence does not hide it from the parser, and a quoted example
    of an approval is a live verdict.
    """
    return f"<!-- {MARKER_NAMESPACE} verdict={verdict} scope=@{head_sha} -->"


def comment_body(verdict: str, head_sha: str) -> str:
    """The comment body: the marker first, then one line of prose.

    Nothing else in the body may look like a marker, because the queue reads
    the raw comment and the first readable marker in it wins.
    """
    headline = "changes requested" if verdict in BLOCKING_VERDICTS else "approved"
    return (
        f"{marker(verdict, head_sha)}\n\n"
        f"Code review verdict: **{headline}** (head `{head_sha}`). "
        "The findings are in the review submitted on this pull request."
    )


def _gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `gh` and capture its output. Never raises on a non-zero exit."""
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _gh_json(args: list[str]) -> Any:
    """Run `gh` and parse its stdout as JSON."""
    done = _gh(args)
    if done.returncode != 0:
        raise ProducerError(
            f"gh {' '.join(args)} failed with exit {done.returncode}",
            stderr=done.stderr.strip(),
        )
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise ProducerError(
            f"gh {' '.join(args)} did not return JSON",
            stderr=done.stderr.strip(),
            exit_code=EXIT_OPERATIONAL,
        ) from exc


def authenticated_login() -> str:
    """The login `gh` acts as. A comment or review from anyone else is not ours."""
    payload = _gh_json(["api", "user"])
    login = payload.get("login") if isinstance(payload, dict) else None
    if not login:
        raise ProducerError("gh api user returned no login")
    return str(login)


def list_comments(repo: str, pr: int) -> list[dict[str, Any]]:
    """Every issue comment on the pull request."""
    payload = _gh_json(["api", "--paginate", f"repos/{repo}/issues/{pr}/comments"])
    return [c for c in payload if isinstance(c, dict)] if isinstance(payload, list) else []


def list_reviews(repo: str, pr: int) -> list[dict[str, Any]]:
    """Every review submitted on the pull request."""
    payload = _gh_json(["api", "--paginate", f"repos/{repo}/pulls/{pr}/reviews"])
    return [r for r in payload if isinstance(r, dict)] if isinstance(payload, list) else []


def _comment_login(comment: dict[str, Any]) -> str:
    user = comment.get("user")
    if isinstance(user, dict):
        return str(user.get("login") or "")
    return ""


def _review_login(review: dict[str, Any]) -> str:
    user = review.get("user")
    if isinstance(user, dict):
        return str(user.get("login") or "")
    return ""


def post_or_update_comment(repo: str, pr: int, login: str, body: str) -> str:
    """Put the verdict marker on the pull request exactly once.

    The third-party producer matched the exact marker plus the authenticated
    author: no marker -> POST, identical -> do nothing, changed -> PATCH. The
    same rule applies here, so re-running the producer on one head does not
    leave a trail of duplicate comments.
    """
    marker_line = body.splitlines()[0] if body else ""
    for comment in list_comments(repo, pr):
        if _comment_login(comment) != login:
            continue
        existing = str(comment.get("body") or "")
        if marker_line not in existing:
            continue
        if existing == body:
            return "unchanged"
        comment_id = comment.get("id")
        if comment_id is None:
            continue
        done = _gh(
            [
                "api",
                "--method",
                "PATCH",
                f"repos/{repo}/issues/comments/{comment_id}",
                "-f",
                f"body={body}",
            ]
        )
        if done.returncode != 0:
            raise ProducerError(
                f"could not update the existing verdict comment on {repo}#{pr}",
                stderr=done.stderr.strip(),
            )
        return "updated"

    done = _gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{repo}/issues/{pr}/comments",
            "-f",
            f"body={body}",
        ]
    )
    if done.returncode != 0:
        raise ProducerError(
            f"could not post the verdict comment on {repo}#{pr}",
            stderr=done.stderr.strip(),
        )
    return "posted"


def blocking_review_exists(repo: str, pr: int, login: str, head_sha: str) -> bool:
    """True when this login already requested changes on this exact head."""
    for review in list_reviews(repo, pr):
        if _review_login(review) != login:
            continue
        if str(review.get("state") or "").upper() != "CHANGES_REQUESTED":
            continue
        if str(review.get("commit_id") or "") == head_sha:
            return True
    return False


def submit_blocking_review(repo: str, pr: int, head_sha: str, body: str) -> str:
    """Submit the review that blocks the merge, once per head.

    GitHub refuses `REQUEST_CHANGES` with 422 when the reviewing login
    authored the pull request — a login cannot block its own pull request. In
    that case the verdict is still posted as a comment and the same review is
    submitted as `COMMENT`, saying in the body that the changes are requested
    but this login cannot block its own pull request.
    """
    done = _gh(
        [
            "api",
            "--method",
            "POST",
            f"repos/{repo}/pulls/{pr}/reviews",
            "-f",
            f"body={body}",
            "-f",
            "event=REQUEST_CHANGES",
            "-f",
            f"commit_id={head_sha}",
        ]
    )
    if done.returncode == 0:
        return "submitted"

    stderr = done.stderr.strip()
    if "422" in stderr and "own pull request" in stderr:
        fallback_body = (
            f"{body}\n\n"
            "The changes are requested, but this login authored this pull request, "
            "so it cannot block its own pull request with a `CHANGES_REQUESTED` "
            "review. The verdict marker on this pull request is the blocking record."
        )
        fallback = _gh(
            [
                "api",
                "--method",
                "POST",
                f"repos/{repo}/pulls/{pr}/reviews",
                "-f",
                f"body={fallback_body}",
                "-f",
                "event=COMMENT",
                "-f",
                f"commit_id={head_sha}",
            ]
        )
        if fallback.returncode == 0:
            return "submitted-as-comment"
        raise ProducerError(
            f"could not submit the blocking review on {repo}#{pr}",
            stderr=fallback.stderr.strip(),
        )

    raise ProducerError(
        f"could not submit the blocking review on {repo}#{pr}",
        stderr=stderr,
    )


def produce(
    repo: str,
    pr: int,
    head_sha: str,
    verdict: str,
    body: str,
    *,
    login: str | None = None,
) -> dict[str, str]:
    """Post the verdict marker and, when the verdict blocks, the review."""
    if not FULL_SHA_RE.match(head_sha):
        raise ProducerError(
            f"head sha {head_sha!r} is not a full 40-character lowercase sha; "
            "the queue compares the whole string against commit ids, so a short "
            "prefix posts a verdict that never matches",
            exit_code=EXIT_USAGE,
        )
    normalised = VERDICT_ALIASES.get(verdict.strip().lower())
    if normalised is None:
        raise ProducerError(
            f"unknown verdict {verdict!r}; use one of {', '.join(sorted(VERDICT_ALIASES))}",
            exit_code=EXIT_USAGE,
        )

    who = login or authenticated_login()
    comment = comment_body(normalised, head_sha)
    result = {
        "verdict": normalised,
        "head_sha": head_sha,
        "comment": post_or_update_comment(repo, pr, who, comment),
        "review": "not-submitted",
    }

    if normalised in BLOCKING_VERDICTS:
        if blocking_review_exists(repo, pr, who, head_sha):
            result["review"] = "already-present"
        else:
            result["review"] = submit_blocking_review(repo, pr, head_sha, body)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="post_review_verdict.py",
        description="Post the merge-queue verdict marker and the blocking review.",
    )
    parser.add_argument("--repo", required=True, help="owner/name of the repository")
    parser.add_argument("--pr", required=True, type=int, help="pull request number")
    parser.add_argument(
        "--head-sha",
        required=True,
        help="full 40-character lowercase sha of the reviewed head commit",
    )
    parser.add_argument(
        "--verdict",
        required=True,
        help="changes_requested or approved",
    )
    parser.add_argument(
        "--body-file",
        help="file with the review body (the findings); defaults to a short pointer",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be posted without calling the API",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as handle:
                body = handle.read().strip()
        except OSError as exc:
            print(f"post_review_verdict: cannot read {args.body_file}: {exc}", file=sys.stderr)
            return EXIT_USAGE
    else:
        body = "The findings are in the review comment on this pull request."

    if args.dry_run:
        normalised = VERDICT_ALIASES.get(args.verdict.strip().lower())
        if normalised is None:
            print(f"post_review_verdict: unknown verdict {args.verdict!r}", file=sys.stderr)
            return EXIT_USAGE
        print(
            json.dumps(
                {
                    "repo": args.repo,
                    "pr": args.pr,
                    "verdict": normalised,
                    "head_sha": args.head_sha,
                    "comment_body": comment_body(normalised, args.head_sha),
                    "review_body": body,
                },
                indent=2,
            )
        )
        return EXIT_OK

    try:
        result = produce(args.repo, args.pr, args.head_sha, args.verdict, body)
    except ProducerError as exc:
        print(f"post_review_verdict: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        return exc.exit_code

    print(json.dumps(result, indent=2))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
