"""Unit tests for scripts/merge_queue.py — the develop merge path (DIG-506).

`digithings-ai` is on GitHub Free, so branch protection and the server-side merge
queue are unavailable on its private repos: the API refuses with "Upgrade to
GitHub Pro or make this repository public". `merge_queue.py` is the merge path
that works without them, and it is therefore the only thing standing between an
untested PR and `develop` until that plan changes. That makes two failure
directions worth pinning.

The dangerous one is a PR merging without ever being tested. Twelve-x's CI runs
a single job named `test`, so a PR shape where that job never reports — a
path-filtered workflow, a skipped step, a waiver — is exactly the hole this
script exists to plug, and the obvious implementations miss it three ways:
requiring the check to merely be *present* rather than to have reported, treating
`NEUTRAL`/`SKIPPED` as a pass because GitHub renders them grey rather than red,
and accepting the author's own review or the merging role's own attestation.
Each of those has a test below.

The other direction is refusing everything, which is how a queue that needs a
human for every merge looks like a queue that fixed nothing. So the tests also
pin the paths that must *succeed*: an approving review from another person, and an
attestation from a role other than the one merging.

`gh` is stubbed on PATH throughout (see the `gh_stub` fixture). An unstubbed `gh`
here would run these cases against the real twelve-x repo.
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
SCRIPT = REPO_ROOT / "scripts" / "merge_queue.py"

EXIT_OK = 0
EXIT_OPERATIONAL = 1
EXIT_NOT_AUTHORISED = 2
EXIT_REFUSED_BASE = 3


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("merge_queue", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["merge_queue"] = module
    spec.loader.exec_module(module)
    return module


mq = _load()


def _pr(
    number: int,
    *,
    created: str = "2026-10-01T00:00:00Z",
    head_sha: str = "a" * 40,
    test_conclusion: str | None = "SUCCESS",
    test_status: str = "COMPLETED",
    reviews: list[dict[str, Any]] | None = None,
    author: str = "chrizefan",
    draft: bool = False,
    mergeable: str = "MERGEABLE",
    merge_state: str = "CLEAN",
    extra_checks: list[dict[str, Any]] | None = None,
    title: str = "",
) -> dict[str, Any]:
    rollup: list[dict[str, Any]] = list(extra_checks or [])
    if test_conclusion is not None:
        rollup.append(
            {
                "__typename": "CheckRun",
                "name": "test",
                "status": test_status,
                "conclusion": test_conclusion,
            }
        )
    return {
        "number": number,
        "title": title or f"work for #{number}",
        "headRefName": f"DIG-{number}-work",
        "headRefOid": head_sha,
        "baseRefName": "develop",
        "isDraft": draft,
        "mergeable": mergeable,
        "mergeStateStatus": merge_state,
        "statusCheckRollup": rollup,
        "reviewDecision": "",
        "author": {"login": author},
        "createdAt": created,
        "reviews": reviews if reviews is not None else [],
    }


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argv],
        capture_output=True,
        text=True,
    )


def _queue_stub(stub: GhStub, prs: list[dict[str, Any]]) -> GhStub:
    """Answer `gh pr list`, and record merges without letting them do anything."""
    stub.wrote("prs.json", json.dumps(prs))
    return stub


# --- the untested-PR hole: a required check that never reported ----------------


def test_required_check_that_never_reported_blocks_the_merge() -> None:
    """A PR with no `test` check at all must not merge.

    This is twelve-x PR #237's real shape, and it is the failure the queue is for:
    the branch looks mergeable, the base's only job never reported, and the change
    lands untested. Treating "check absent" as "check passed" is the bug.
    """
    verdict = mq.evaluate(
        _pr(237, test_conclusion=None),
        mq.load_policy(),
        acting_role="cto",
        attest_role="qa",
    )
    assert not verdict.eligible
    assert "required check 'test' has not reported" in verdict.reasons


@pytest.mark.parametrize("conclusion", ["NEUTRAL", "SKIPPED", "", None])
def test_only_success_passes_a_required_check(conclusion: str | None) -> None:
    """NEUTRAL and SKIPPED are not passes.

    GitHub paints them grey, which is easy to read as "fine". They are GitHub's
    way of saying the check declined to run, and for a required gate that is the
    condition the gate exists to exclude. `NEUTRAL` is exactly what `Cursor Bugbot`
    reports on a usage-limit skip — docs/BRANCH_PROTECTION.md records that as the
    reason it could not be made a required check.
    """
    entry: dict[str, Any] = {"__typename": "CheckRun", "name": "test", "status": "COMPLETED"}
    if conclusion is not None:
        entry["conclusion"] = conclusion
    pr = _pr(1, test_conclusion=None)
    pr["statusCheckRollup"] = [entry]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", attest_role="qa")
    assert not verdict.eligible
    assert any("required check 'test'" in reason for reason in verdict.reasons)


def test_a_pending_required_check_blocks() -> None:
    verdict = mq.evaluate(
        _pr(1, test_conclusion=None, test_status="IN_PROGRESS"),
        mq.load_policy(),
        acting_role="cto",
        attest_role="qa",
    )
    assert not verdict.eligible


def test_a_failing_non_required_check_also_blocks() -> None:
    """A red build is a red build even when the named gate is green."""
    pr = _pr(
        1,
        extra_checks=[
            {
                "__typename": "CheckRun",
                "name": "pip-audit",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            }
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", attest_role="qa")
    assert not verdict.eligible
    assert "check 'pip-audit' is FAILURE" in verdict.reasons


def test_an_ignored_check_cannot_fail_the_queue() -> None:
    pr = _pr(
        1,
        extra_checks=[
            {
                "__typename": "CheckRun",
                "name": "advisory-score",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            }
        ],
    )
    policy = mq.load_policy()
    policy = mq.Policy(
        merge_authorities=policy.merge_authorities,
        review_path=policy.review_path,
        blocked_bases=policy.blocked_bases,
        merge_method=policy.merge_method,
        delete_branch=policy.delete_branch,
        required_checks=policy.required_checks,
        ignored_checks=frozenset({"advisory-score"}),
    )
    assert mq.evaluate(pr, policy, acting_role="cto", attest_role="qa").eligible


# --- review: who is allowed to say the code was read --------------------------


def test_the_author_approving_their_own_pr_does_not_count() -> None:
    pr = _pr(1, reviews=[{"author": {"login": "chrizefan"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", attest_role=None)
    assert not verdict.eligible
    assert any("no approving review from a non-author" in r for r in verdict.reasons)


def test_an_approving_review_from_someone_else_is_enough() -> None:
    """No attestation needed when a real approval exists — the queue must not stall here."""
    pr = _pr(1, reviews=[{"author": {"login": "coderabbit"}, "state": "APPROVED"}])
    assert mq.evaluate(pr, mq.load_policy(), acting_role="cto", attest_role=None).eligible


def test_outstanding_change_requests_block() -> None:
    pr = _pr(
        1,
        reviews=[{"author": {"login": "someone"}, "state": "CHANGES_REQUESTED"}],
    )
    pr["reviewDecision"] = "CHANGES_REQUESTED"
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", attest_role="qa")
    assert not verdict.eligible
    assert "review has outstanding change requests" in verdict.reasons


def test_the_merging_role_cannot_attest_its_own_review() -> None:
    """Self-attestation is refused.

    Every agent in this org pushes under one GitHub login, so GitHub cannot tell
    the author of a PR from the role merging it. The role is the only granularity
    available, which is why an attestation naming the merging role is rejected
    outright rather than trusted.
    """
    verdict = mq.evaluate(_pr(1), mq.load_policy(), acting_role="cto", attest_role="cto")
    assert not verdict.eligible
    assert any("also the merging role" in reason for reason in verdict.reasons)


def test_a_different_role_attesting_passes() -> None:
    assert mq.evaluate(_pr(1), mq.load_policy(), acting_role="cto", attest_role="qa").eligible


def test_an_em_merge_attested_by_the_cto_passes() -> None:
    assert mq.evaluate(_pr(1), mq.load_policy(), acting_role="em", attest_role="cto").eligible


# --- ordering: a queue, not a race --------------------------------------------


def test_queue_order_is_creation_order_not_greenness() -> None:
    """Oldest first. Greenest-first quietly becomes "whoever CI got back first"."""
    verdicts = [
        mq.evaluate(
            _pr(3, created="2026-10-03T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            attest_role="qa",
        ),
        mq.evaluate(
            _pr(1, created="2026-10-01T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            attest_role="qa",
        ),
        mq.evaluate(
            _pr(2, created="2026-10-02T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            attest_role="qa",
        ),
    ]
    assert [v.number for v in sorted(verdicts, key=mq.Verdict.order_key)] == [1, 2, 3]


def test_ties_on_creation_time_break_on_pr_number() -> None:
    same = "2026-10-01T00:00:00Z"
    verdicts = [
        mq.evaluate(_pr(n, created=same), mq.load_policy(), acting_role="cto", attest_role="qa")
        for n in (11, 4, 7)
    ]
    assert [v.number for v in sorted(verdicts, key=mq.Verdict.order_key)] == [4, 7, 11]


# --- the CLI refusals ----------------------------------------------------------


def test_a_role_off_the_roster_is_refused(gh_stub: Any) -> None:
    """The gate the CEO asked for: not Chris, and not the asking agent.

    `merge_queue.py` is the mechanism behind "the EM and the CTO merge, nobody
    else". If it accepted any role that asserted one, it would be a queue that
    anyone can walk into, which is the same standing-authority question the PR 231
    approval declined to answer for merge cards.
    """
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=[])), [])
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "devops")
    assert done.returncode == EXIT_NOT_AUTHORISED
    assert "not on the merge-authority roster" in done.stderr
    assert "cto" in done.stderr and "em" in done.stderr
    assert stub.matching("pr merge") == []


def test_the_roster_is_the_cto_and_the_em_only() -> None:
    roles = {a.role for a in mq.load_policy().merge_authorities}
    assert roles == {"cto", "em"}
    assert "qa" not in roles  # QA reviews; QA does not merge.
    assert "chris" not in roles and "chrisstefan" not in roles


def test_attesting_a_role_outside_the_review_path_is_refused(gh_stub: Any) -> None:
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=[])), [])
    done = _run(
        "list",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "devops",
    )
    assert done.returncode == EXIT_NOT_AUTHORISED
    assert "not in the review path" in done.stderr


@pytest.mark.parametrize("base", ["main", "master", "release/v1.2.3"])
def test_release_bases_are_refused_outright(gh_stub: Any, base: str) -> None:
    """A merge into a release or trunk branch is a human decision, not a queue move."""
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=[])), [])
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto", "--base", base)
    assert done.returncode == EXIT_REFUSED_BASE
    assert base in done.stderr


def test_blocked_bases_match_by_prefix(gh_stub: Any) -> None:
    """`release/v1.2.3` must not slip past a list containing only `release`."""
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=[])), [])
    assert mq.load_policy().is_blocked_base("release/v1.2.3")
    assert mq.load_policy().is_blocked_base("main")
    assert not mq.load_policy().is_blocked_base("develop")
    assert not mq.load_policy().is_blocked_base("feature/develop-helper")


def test_drafts_and_conflicts_do_not_queue(gh_stub: Any) -> None:
    prs = [
        _pr(1, created="2026-10-01T00:00:00Z", draft=True),
        _pr(2, created="2026-10-02T00:00:00Z", mergeable="CONFLICTING"),
        _pr(3, created="2026-10-03T00:00:00Z", merge_state="BLOCKED"),
    ]
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run(
        "list",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "qa",
    )
    assert done.returncode == EXIT_OK
    assert "queued: none" in done.stdout
    assert "draft" in done.stdout
    assert "mergeable=CONFLICTING" in done.stdout
    assert "mergeStateStatus=BLOCKED" in done.stdout


# --- run mode: re-read, pin the head, never escalate ---------------------------


def test_run_merges_the_head_and_pins_the_evaluated_sha(gh_stub: Any) -> None:
    """The merge is pinned to the SHA the gates were evaluated against.

    Without `--match-head-commit`, a push landing between evaluation and merge
    ships code whose checks nobody looked at. With it, the merge aborts instead.
    """
    prs = [_pr(42, head_sha="b" * 40)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "qa",
    )
    assert done.returncode == EXIT_OK, done.stderr
    merges = stub.matching("pr merge 42")
    assert len(merges) == 1
    assert "--match-head-commit" in merges[0]
    assert merges[0][merges[0].index("--match-head-commit") + 1] == "b" * 40
    assert "--squash" in merges[0]
    assert "merged #42" in done.stdout


def test_run_never_escalates_with_admin(gh_stub: Any) -> None:
    """`--admin` would merge a PR the gates just refused. The queue must never pass it.

    An operator can always escalate by hand and say so; a queue that escalates on
    its own is indistinguishable from one that ignores its own gates.
    """
    prs = [_pr(42)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "em", "--attest-review", "qa")
    assert stub.matching("pr merge")
    assert all("--admin" not in call for call in stub.matching("pr merge"))


def test_run_re_reads_the_queue_after_every_merge(gh_stub: Any) -> None:
    """Merging one PR can dirty the next. A queue computed once merges stale verdicts.

    The stub serves a queue that shrinks as PRs merge, which is what the real API
    does: `gh pr list --state open` stops returning a PR the moment it lands.
    """
    stub = gh_stub(
        gh_rule(r"^pr list", stdout_files=["q1.json", "q2.json", "q3.json"]),
        gh_rule(r"^pr merge", stdout=""),
        gh_rule(r"^pr comment", stdout=""),
    )
    stub.wrote("q1.json", json.dumps([_pr(1), _pr(2)]))
    stub.wrote("q2.json", json.dumps([_pr(2)]))
    stub.wrote("q3.json", json.dumps([]))
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "qa",
        "--max-merges",
        "2",
    )
    assert done.returncode == EXIT_OK, done.stderr
    # One read per merge decision. --max-merges stopped the run, so no third read,
    # and the report must not claim to know the current queue.
    assert len(stub.matching("pr list")) == 2
    assert [c[2] for c in stub.matching("pr merge")] == ["1", "2"]
    assert "list` shows the current queue" in done.stdout


def test_run_stops_when_a_merge_makes_the_next_pr_ineligible(gh_stub: Any) -> None:
    """The regression the re-read exists for: #2 goes conflicted after #1 lands.

    Both are green on the first read. Merging #1 invalidates #2's verdict, and a
    batch merge computed from the first read would land #2 unverified.
    """
    stub = gh_stub(
        gh_rule(r"^pr list", stdout_files=["q1.json", "q2.json"]),
        gh_rule(r"^pr merge", stdout=""),
        gh_rule(r"^pr comment", stdout=""),
    )
    stub.wrote("q1.json", json.dumps([_pr(1), _pr(2)]))
    # After #1 lands, #2 has gone conflicted against the new develop tip.
    stub.wrote("q2.json", json.dumps([_pr(2, mergeable="CONFLICTING")]))
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "qa",
        "--max-merges",
        "5",
    )
    assert done.returncode == EXIT_OK, done.stderr
    merged = [c[2] for c in stub.matching("pr merge")]
    assert merged == ["1"], "must not merge #2 from a verdict computed before #1 landed"
    assert "mergeable=CONFLICTING" in done.stdout


def test_dry_run_changes_nothing(gh_stub: Any) -> None:
    prs = [_pr(42)]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--attest-review",
        "qa",
        "--dry-run",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert "would merge" in done.stdout
    assert stub.matching("pr merge") == []
    assert stub.matching("pr comment") == []


def test_the_audit_comment_names_the_role_and_the_verdicts(gh_stub: Any) -> None:
    """The comment is the evidence that no decision card was needed.

    It has to say which role merged and what the merge relied on, or a later
    reader cannot tell a routine queue merge from someone bypassing policy.
    """
    prs = [_pr(42, head_sha="c" * 40)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "em", "--attest-review", "qa")
    comments = stub.matching("pr comment 42")
    assert len(comments) == 1
    body = comments[0][comments[0].index("--body") + 1]
    assert "no decision card required" in body
    assert "`em`" in body
    assert "`qa`" in body
    assert ("c" * 12) in body


def test_max_merges_defaults_to_one(gh_stub: Any) -> None:
    """One merge per invocation, re-read between invocations."""
    prs = [_pr(1, created="2026-10-01T00:00:00Z"), _pr(2, created="2026-10-02T00:00:00Z")]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto", "--attest-review", "qa")
    assert [c[2] for c in stub.matching("pr merge")] == ["1"]


def test_an_operational_gh_failure_is_reported_not_swallowed(gh_stub: Any) -> None:
    _queue_stub(
        gh_stub(gh_rule(r"^pr list", stderr="gh: authentication required", exit_code=1)), []
    )
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OPERATIONAL
    assert "authentication required" in done.stderr


def test_the_policy_file_is_validated_not_assumed(tmp_path: Path) -> None:
    """A roster edited into an unknown schema fails closed rather than merging under defaults."""
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps({"schema": 2}), encoding="utf-8")
    with pytest.raises(mq.QueueError, match="unsupported schema"):
        mq.load_policy(bad)
