"""A review verdict applies only to the head SHA it was made against.

`digithings-ai/digithings#6263` was approved at 01:01 on head `177278b680f4`
and handed back at 01:05 because a `changes_requested` written against
`a87fc55760e9` still stood. A verdict is a statement about one commit: a block
on a commit the PR no longer stands at is a statement about code that is no
longer here, and it must neither hold the current head nor ask the seat that
posted it to review work it never saw.

These are the five behaviours the rule promises, one test each. They live
beside `test_merge_queue.py` rather than inside it so the #6263 shape reads as
one subject.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "merge_queue.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("merge_queue", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["merge_queue"] = module
    spec.loader.exec_module(module)
    return module


mq = _load()

# The #6263 shape: the head the approve named, and the older head the block named.
HEAD_6263 = "177278b680f4" + "0" * 28
STALE_6263 = "a87fc55760e9" + "0" * 28

REVIEWER_SEAT = "c59332b4-a0ef-4a6a-8027-5c081486f899"
SECURITY_SEAT = "77fd6c7a-97b1-41f7-be9d-859cf5d7af33"


def _pr(
    number: int,
    *,
    head_sha: str = HEAD_6263,
    comments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A mergeable `develop` PR, carrying only the review record under test."""
    return {
        "number": number,
        "title": f"work for #{number}",
        "headRefName": f"DIG-{number}-work",
        "headRefOid": head_sha,
        "baseRefName": "develop",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "test",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            },
            {
                "__typename": "StatusContext",
                "context": "local-ci",
                "state": "SUCCESS",
                "startedAt": "2026-10-23T01:00:00Z",
                "targetUrl": "https://ci.invalid/build/1",
            },
        ],
        # A native non-author approval, so the coverage gate has its evidence and
        # the verdict gate is the only thing left to judge.
        "reviewDecision": "",
        "author": {"login": "chrizefan"},
        "createdAt": "2026-10-23T00:40:00Z",
        "reviews": [{"author": {"login": "reviewer"}, "state": "APPROVED"}],
        "comments": list(comments or []),
        "commits": [{"oid": head_sha}],
        "labels": [{"name": "reviewed:agent"}],
    }


def _seat_verdict(
    *, seat: str, verdict: str, head_sha: str, created: str, withdraws: str = ""
) -> dict[str, Any]:
    """A fleet verdict comment: provenance marker names the seat, scope names the head."""
    body = (
        f"<!-- digithings-review agent={seat} "
        f"run=00000000-0000-0000-0000-000000000000 head={head_sha} -->\n"
        f"<!-- opencode-power-pack:code-review verdict={verdict} scope=@{head_sha} -->\n\n"
        f"Review verdict: {verdict.replace('_', ' ')}\n"
    )
    if withdraws:
        body += f"Withdraws: changes requested on {withdraws}\n"
    return {
        "id": f"IC_kwDO{seat[:8]}_{created}",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "body": body,
        "createdAt": created,
    }


def _in_session_review(head_sha: str, created: str = "2026-10-23T01:00:30Z") -> dict[str, Any]:
    """Coverage evidence on the head: the marker the coverage gate reads."""
    return {
        "id": f"IC_kwDOin_session_{head_sha[:8]}",
        "author": {"login": "reviewer"},
        "authorAssociation": "MEMBER",
        "body": (
            "<!-- in-session-review -->\n"
            "<!-- digithings-review agent=" + REVIEWER_SEAT + " "
            "run=22222222-2222-2222-2222-222222222222 "
            f"head={head_sha} -->\n\nOne finding, addressed.\n"
        ),
        "createdAt": created,
    }


# 1. A review verdict applies only to the head SHA it was made against.


def test_a_verdict_applies_only_to_the_head_it_was_made_against() -> None:
    """The rule in one call: the same verdict applies to its head and no other."""
    verdict = mq.PostedVerdict(
        verdict="changes_requested",
        source="a `verdict=` marker",
        scope=STALE_6263,
        bindings=(STALE_6263,),
        comment_id="1",
        author="chrizefan",
        at="2026-10-23T00:50:00Z",
    )
    assert mq.verdict_applies_to_head(verdict, STALE_6263)
    assert not mq.verdict_applies_to_head(verdict, HEAD_6263)
    # A verdict that names no head at all cannot be stale, so it keeps the
    # treatment it had before this rule: it counts.
    unscoped = replace(verdict, scope="", bindings=())
    assert mq.verdict_applies_to_head(unscoped, HEAD_6263)


# 2. A `changes_requested` whose head is not the current head must not block.


def test_a_stale_seat_block_does_not_hold_the_current_head() -> None:
    """The #6263 shape: the security desk blocked a head the PR had left."""
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="changes_requested",
                head_sha=STALE_6263,
                created="2026-10-23T00:50:00Z",
            ),
            _seat_verdict(
                seat=REVIEWER_SEAT,
                verdict="approve",
                head_sha=HEAD_6263,
                created="2026-10-23T01:01:00Z",
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


def test_a_stale_unseated_block_does_not_hold_the_current_head() -> None:
    """The same rule where the seat cannot be read, so the newest verdict decides."""
    pr = _pr(
        6263,
        comments=[
            {
                "id": "IC_kwDOprose_6263",
                "author": {"login": "chrizefan"},
                "authorAssociation": "MEMBER",
                # A prose verdict with no sha in it would block (names no head);
                # this one names the stale head, and only that head.
                "body": f"Review verdict: changes requested ({STALE_6263})\n",
                "createdAt": "2026-10-23T00:50:00Z",
            }
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


def test_a_stale_native_block_does_not_hold_the_current_head() -> None:
    """`reviewDecision` keeps saying CHANGES_REQUESTED after the head moves.

    GitHub's aggregate is not scoped to a commit, and the review that fed it
    was made against the commit it names. A native block on a head the PR has
    left is as stale as a posted one — and on this org it is permanent, because
    the one login that posted it is the only login that could approve.
    """
    pr = _pr(6263, comments=[_in_session_review(HEAD_6263)])
    pr["reviewDecision"] = "CHANGES_REQUESTED"
    pr["reviews"].append(
        {
            "author": {"login": "reviewer"},
            "state": "CHANGES_REQUESTED",
            "commit": {"oid": STALE_6263},
        }
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


# 3. A `changes_requested` on the CURRENT head must still block, exactly as today.


def test_a_block_on_the_current_head_still_holds() -> None:
    """The regression the staleness rule must not open: this head is blocked."""
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="changes_requested",
                head_sha=HEAD_6263,
                created="2026-10-23T01:01:00Z",
            ),
            _seat_verdict(
                seat=REVIEWER_SEAT,
                verdict="approve",
                head_sha=HEAD_6263,
                created="2026-10-23T01:02:00Z",
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any(
        SECURITY_SEAT in r and "changes_requested" in r and HEAD_6263[:12] in r
        for r in verdict.reasons
    )


def test_an_unseated_block_on_the_current_head_still_holds() -> None:
    """Clause 2 keeps its block too: a stale-scope fix is not a review-softening."""
    pr = _pr(
        6263,
        comments=[
            {
                "id": "IC_kwDOprose_6263",
                "author": {"login": "chrizefan"},
                "authorAssociation": "MEMBER",
                "body": f"Review verdict: changes requested ({HEAD_6263})\n",
                "createdAt": "2026-10-23T01:01:00Z",
            }
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("changes_requested" in r and HEAD_6263[:12] in r for r in verdict.reasons)


def test_a_native_block_on_the_current_head_still_holds() -> None:
    """The native arm keeps its block when the review names this head."""
    pr = _pr(6263, comments=[_in_session_review(HEAD_6263)])
    pr["reviewDecision"] = "CHANGES_REQUESTED"
    pr["reviews"].append(
        {
            "author": {"login": "reviewer"},
            "state": "CHANGES_REQUESTED",
            "commit": {"oid": HEAD_6263},
        }
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("review has outstanding change requests" in r for r in verdict.reasons)


# 4. An `approve` on the current head, withdrawing the block, clears it.


def test_an_approve_on_the_current_head_withdrawing_the_block_clears_it() -> None:
    """The seat that blocked the head is the seat that can clear it — by naming it.

    Since DIG-5246 the approve on an unchanged head also has to say it
    withdraws the block; that rule is tested on its own in
    `test_merge_queue.py`, and this fixture carries the `Withdraws:` line so
    this test keeps testing the head-scope rule.
    """
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="changes_requested",
                head_sha=HEAD_6263,
                created="2026-10-23T00:50:00Z",
            ),
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="approve",
                head_sha=HEAD_6263,
                created="2026-10-23T01:01:00Z",
                withdraws=HEAD_6263,
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


# 5. An `approve` on an OLD head must NOT clear a `changes_requested` on the
#    current head: an old verdict must not vouch for new code.


def test_an_approve_on_an_old_head_does_not_clear_a_block_on_the_current_head() -> None:
    """The seat approved a commit the PR has left; its block on this head stands."""
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="changes_requested",
                head_sha=HEAD_6263,
                created="2026-10-23T00:50:00Z",
            ),
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="approve",
                head_sha=STALE_6263,
                created="2026-10-23T01:01:00Z",
            ),
            _seat_verdict(
                seat=REVIEWER_SEAT,
                verdict="approve",
                head_sha=HEAD_6263,
                created="2026-10-23T01:02:00Z",
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any(SECURITY_SEAT in r and "changes_requested" in r for r in verdict.reasons)
