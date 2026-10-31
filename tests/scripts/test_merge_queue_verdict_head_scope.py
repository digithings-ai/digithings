"""A review verdict names one head; a push does not spend a block.

`digithings-ai/digithings#6263` was approved at 01:01 on head `177278b680f4`
and handed back at 01:05 because a `changes_requested` written against
`a87fc55760e9` still stood. #6399 answered that by letting the branch moving
spend every block, which also let any push retire a security block nobody had
answered (T4). The rule now:

* an approve counts only on the head it names;
* a block stands whatever head it names, until the seat that posted it posts a
  verdict on the current head (no `Withdraws:` line needed when the block named
  an older commit — that is the #6263 handback, answered by the seat);
* another seat's approve never clears it, with or without a `Withdraws:` line;
* a native CHANGES_REQUESTED stands until it is dismissed or re-reviewed.

They live beside `test_merge_queue.py` rather than inside it so the #6263
shape reads as one subject.
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


# 2. A `changes_requested` whose head is not the current head still blocks (T4).


def test_a_stale_seat_block_is_not_cleared_by_another_seats_approve() -> None:
    """The security desk blocked a head the PR has left; another seat approved.

    Until T4 this asserted `eligible`: the push spent the security block and
    the code reviewer's approve carried the merge — the #6170 shape again.
    """
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
    assert not verdict.eligible
    assert any(
        SECURITY_SEAT in r and STALE_6263[:12] in r and HEAD_6263[:12] in r
        for r in verdict.reasons
    ), verdict.reasons


def test_a_stale_unseated_block_still_holds_the_current_head() -> None:
    """The same rule where the seat cannot be read: nothing newer answers it.

    Until T4 this asserted `eligible`.
    """
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
    assert not verdict.eligible
    assert any("A push does not spend a block" in r for r in verdict.reasons), verdict.reasons


def test_a_stale_native_block_still_holds_until_it_is_dismissed() -> None:
    """`reviewDecision` keeps saying CHANGES_REQUESTED after the head moves.

    That is GitHub's own rule, and the queue now follows it (T4): a native
    change request is answered by a new review on the head or by a dismissal,
    which GitHub audits. Until T4 this asserted `eligible`, so a push retired
    a native block.
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
    assert not verdict.eligible
    assert any(
        r.startswith("review has outstanding change requests")
        and STALE_6263[:12] in r
        and "dismissal" in r
        for r in verdict.reasons
    ), verdict.reasons


def test_a_dismissed_native_block_does_not_hold() -> None:
    """The audited way out of a native block: GitHub no longer reports it."""
    pr = _pr(6263, comments=[_in_session_review(HEAD_6263)])
    pr["reviewDecision"] = ""
    pr["reviews"].append(
        {
            "author": {"login": "reviewer"},
            "state": "DISMISSED",
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


# 6. T4 (from #6399): a push does not spend a security block.


def test_a_security_block_on_a_then_a_push_to_b_is_not_eligible_on_label_and_coverage() -> None:
    """Security blocks A; the author pushes B; label and coverage are on B.

    This is the T4 bypass end to end: no approve on B from anyone, only the
    `reviewed:agent` label and an in-session marker on B. Not eligible, and the
    refusal names the seat and the commit it blocked.
    """
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=SECURITY_SEAT,
                verdict="changes_requested",
                head_sha=STALE_6263,
                created="2026-10-23T00:50:00Z",
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any(SECURITY_SEAT in r and STALE_6263[:12] in r for r in verdict.reasons), (
        verdict.reasons
    )


def test_the_same_seat_approving_b_clears_its_block_on_a() -> None:
    """The #6263 handback, answered by the seat: it re-reviews B and approves.

    No `Withdraws:` line is needed — the block named A, the approve names B, so
    the seat has posted a verdict on the head the PR stands at.
    """
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
                seat=SECURITY_SEAT,
                verdict="approve",
                head_sha=HEAD_6263,
                created="2026-10-23T01:01:00Z",
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


def test_a_reviewer_seats_own_approve_on_b_clears_its_block_on_a() -> None:
    """The same relief for any seat, not only the security desk."""
    pr = _pr(
        6263,
        comments=[
            _seat_verdict(
                seat=REVIEWER_SEAT,
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


def test_another_seats_withdrawal_does_not_clear_a_security_block() -> None:
    """A `Withdraws:` line speaks only for the seat that writes it."""
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
                withdraws=STALE_6263,
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any(SECURITY_SEAT in r for r in verdict.reasons), verdict.reasons


def test_the_seat_approving_a_again_does_not_clear_its_block_once_the_pr_is_at_b() -> None:
    """An approve on the commit the PR has left says nothing about B."""
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
                seat=SECURITY_SEAT,
                verdict="approve",
                head_sha=STALE_6263,
                created="2026-10-23T00:55:00Z",
                withdraws=STALE_6263,
            ),
            _in_session_review(HEAD_6263),
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible


def test_a_newer_unseated_approve_on_b_answers_an_unseated_block_on_a() -> None:
    """Clause 2 is still newest-verdict: a later verdict naming B replaces it."""
    pr = _pr(
        6263,
        comments=[
            {
                "id": "IC_kwDOprose_6263_block",
                "author": {"login": "chrizefan"},
                "authorAssociation": "MEMBER",
                "body": f"Review verdict: changes requested ({STALE_6263})\n",
                "createdAt": "2026-10-23T00:50:00Z",
            },
            {
                "id": "IC_kwDOprose_6263_approve",
                "author": {"login": "chrizefan"},
                "authorAssociation": "MEMBER",
                "body": f"Review verdict: approve ({HEAD_6263})\n",
                "createdAt": "2026-10-23T01:01:00Z",
            },
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons
