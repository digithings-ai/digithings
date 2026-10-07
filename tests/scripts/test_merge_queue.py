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
import re
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
    comments: list[dict[str, Any]] | None = None,
    commits: list[dict[str, Any]] | None = None,
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
    pr = {
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
    # `comments` and `commits` are fetched from GitHub but are absent from every
    # hand-built PR that does not ask for them, so the gates stay exercised on the
    # shape they will really meet when a key is missing.
    if comments is not None:
        pr["comments"] = comments
    if commits is not None:
        pr["commits"] = commits
    return pr


def _review_comment(
    *,
    verdict: str | None = "changes_requested",
    head_sha: str = "a" * 40,
    created: str = "2026-10-07T22:07:11Z",
    login: str = "chrizefan",
    number: int = 347,
    prose: bool = True,
) -> dict[str, Any]:
    """A PR comment in the shape a posted code-review verdict arrives in.

    The marker is an HTML comment whose `key=value` fields are the machine-readable
    part; the prose below it is what a human reads. Only the fields are parsed, so
    the prose here is free to say anything.
    """
    fields = [f"scope=digithings-ai/twelve-x#{number}@{head_sha}"]
    if verdict is not None:
        fields.append(f"verdict={verdict}")
    body = f"<!-- opencode-power-pack:code-review {' '.join(fields)} -->\n"
    if prose:
        body += "## Verdict: changes requested (narrow)\n\n**One finding blocks approval.**\n"
    return {
        "id": f"IC_kwDO{login}_{number}",
        "author": {"login": login},
        "authorAssociation": "MEMBER",
        "body": body,
        "createdAt": created,
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
        base="develop",
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
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role="qa")
    assert not verdict.eligible
    assert any("required check 'test'" in reason for reason in verdict.reasons)


def test_a_pr_targeting_a_different_base_is_refused() -> None:
    """The queue merges one branch. A PR aimed elsewhere must never be picked up.

    `gh pr list --base develop` filters the fetch, and `blocked_bases` refuses the
    branches a human must sign off on. If `--base` were ever dropped from that call,
    the fetch would silently widen to every open PR in the repo and the roster would
    merge them all. This pins the second line of defence: the verdict itself refuses
    a PR whose `baseRefName` is not the queue's base.
    """
    pr = _pr(1)
    pr["baseRefName"] = "main"
    verdict = mq.evaluate(pr, mq.load_policy(), base="develop", acting_role="cto", attest_role="qa")
    assert not verdict.eligible
    assert "baseRefName=main, expected develop" in verdict.reasons


def test_a_pending_required_check_blocks() -> None:
    verdict = mq.evaluate(
        _pr(1, test_conclusion=None, test_status="IN_PROGRESS"),
        mq.load_policy(),
        acting_role="cto",
        base="develop",
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
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role="qa")
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
        required_checks_by_repo=policy.required_checks_by_repo,
        ignored_checks=frozenset({"advisory-score"}),
    )
    assert mq.evaluate(pr, policy, acting_role="cto", base="develop", attest_role="qa").eligible


# --- which checks are required, and telling misconfiguration from a red build --


def test_required_checks_are_resolved_per_repo() -> None:
    """Two repos in this org report different names, so one global list cannot serve both.

    `digithings` runs every test suite through reusable workflows, so GitHub reports
    each as `<caller> / test` — `digibase / test`, `digiclaw / test`, and eleven more —
    and names nothing `test`. `twelve-x` runs one job and does report a bare `test`.
    A single hardcoded list is therefore wrong for one of them, and DIG-690 measured
    which: 28 PRs blocked, every one of them on `required check 'test' has not
    reported`, in a repo where no PR has ever reported it.
    """
    policy = mq.load_policy()
    assert policy.required_for("digithings-ai/twelve-x") == ("test",)
    digithings = policy.required_for("digithings-ai/digithings")
    assert "test" not in digithings, "a bare `test` never reports on digithings"
    assert "Required checks passed" in digithings
    assert "doc-links + agents-init" in digithings
    assert "mypy — digibase + digikey" in digithings
    # An unlisted repo still gets a gate rather than none: the failure that matters
    # here is a silent pass, not a refusal.
    assert policy.required_for("digithings-ai/digithings-ops")


def test_a_required_check_that_no_pr_in_the_queue_ever_reports_is_a_misconfiguration() -> None:
    """A gate name that cannot match must say so, not look like 28 red CI runs.

    The whole cost of DIG-690 was that `required check 'test' has not reported` reads
    identically whether CI is broken or the gate is misnamed, so an operator's first
    move is to go look at CI. Comparing against everything the queue actually reported
    is what separates the two — and it still blocks, because a gate that names nothing
    must not become a gate that names nothing and merges.
    """
    pr = _pr(1, test_conclusion=None)
    pr["statusCheckRollup"] = [
        {
            "__typename": "CheckRun",
            "name": "digibase / test",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
        {
            "__typename": "CheckRun",
            "name": "Required checks passed",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
    ]
    unmatched, reported = mq.unmatched_required_checks([pr], ("test",))
    assert unmatched == ("test",)
    assert "digibase / test" in reported and "Required checks passed" in reported
    # Nothing reported anywhere is a different problem — CI never ran — and must not
    # be reported as a naming problem.
    assert mq.unmatched_required_checks([_pr(2, test_conclusion=None)], ("test",)) == ((), ())


def test_a_required_check_that_any_pr_reports_is_not_called_a_misconfiguration() -> None:
    """The path-filtered case is the one the gate exists for, so it must stay quiet.

    One PR touching only Python legitimately has no `digichat / test`. If that counted
    as misconfiguration, the detector would fire on correct behaviour and train
    operators to ignore it.
    """
    python_only = _pr(1, test_conclusion=None)
    python_only["statusCheckRollup"] = [
        {
            "__typename": "CheckRun",
            "name": "Required checks passed",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        }
    ]
    full_suite = _pr(2, test_conclusion=None)
    full_suite["statusCheckRollup"] = python_only["statusCheckRollup"] + [
        {
            "__typename": "CheckRun",
            "name": "digichat / test",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        }
    ]
    # `digichat / test` is absent from the Python-only PR and present on the other.
    # Required everywhere, reported by *someone* — which is the gate working, not a
    # naming mistake, so there is nothing to announce.
    assert mq.unmatched_required_checks([python_only, full_suite], ("digichat / test",)) == (
        (),
        ("Required checks passed", "digichat / test"),
    )


def test_a_misconfigured_gate_is_announced_once_and_still_blocks(gh_stub: Any) -> None:
    """The condition that cost DIG-690 28 PRs, stated as a test.

    The announcement goes to stderr because it is a diagnostic, not queue state — a
    line of warning mixed into the `list` table would read as a PR's reason for
    blocking. It must name the offending check, name what CI *is* reporting so the
    reader does not go looking for a red build, and point at the file to edit.
    """
    prs = [_pr(1), _pr(2, created="2026-10-02T00:00:00Z")]
    for pr in prs:
        pr["statusCheckRollup"] = [
            {
                "__typename": "CheckRun",
                "name": "digibase / test",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            }
        ]
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("list", "--repo", "digithings-ai/digithings", "--acting-role", "cto")
    assert done.returncode == EXIT_OK
    err = done.stderr
    assert "misconfigured required check" in err
    assert "not a red build" in err
    # Names the gate that cannot match...
    for name in ("Required checks passed", "doc-links + agents-init", "mypy — digibase + digikey"):
        assert f"'{name}'" in err, name
    # ...and what CI is really producing, so the reader stops hunting for a failure.
    assert "digibase / test" in err
    assert "required_checks_by_repo" in err
    # Every PR is still blocked. The announcement is additive: a gate that names
    # nothing must not become a gate that names nothing and merges.
    assert "blocked (2)" in done.stdout
    assert "has not reported" in done.stdout


def test_the_misconfiguration_announcement_names_what_it_meant_instead_of_a_wall_of_names(
    gh_stub: Any,
) -> None:
    """A digithings PR reports 58 distinct checks. Listing all of them is not a fix.

    The reader is told one name is wrong and needs to know what the right one is; a
    58-item dump makes them open a second tool to compare against, which is the work
    the announcement exists to save. So it names the near misses — the reported checks
    sharing a word with the gate — and counts the rest.
    """
    # Deliberately none of digithings' three required contexts — that is the DIG-690
    # shape. The decoys are what the reader has to choose from instead.
    reported = [
        {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
        for name in (
            "path-filter",
            "changes",
            "score",
            "web",
            "gitleaks-scan",
            "doc-links + agents-init",
        )
    ]
    prs = [_pr(1)]
    prs[0]["statusCheckRollup"] = reported
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("list", "--repo", "digithings-ai/digithings", "--acting-role", "cto")
    err = done.stderr
    assert "6 distinct checks did report" in err
    # `mypy` is required, unmatchable, and shares a word with nothing reported —
    # so no near miss is offered for it and the message must not imply one exists.
    assert "'mypy — digibase + digikey'" in err
    assert "nearest:" not in err
    assert "gh pr checks" in err

    near = mq._near_misses(("test",), ("digibase / test", "digiclaw / test", "path-filter"))
    assert near[:2] == ["digibase / test", "digiclaw / test"]
    assert "path-filter" not in near, "no shared word; listing it would be noise"
    # Word-based, so an unrelated check that merely contains the letters is excluded.
    assert mq._near_misses(("mypy",), ("mypy — digibase + digikey", "npm-audit")) == [
        "mypy — digibase + digikey"
    ]
    # Bounded: an org with fifty near-identical suite names does not produce a wall.
    many = tuple(f"suite-{i} / test" for i in range(50))
    assert len(mq._near_misses(("test",), many)) == 4


def test_the_warning_cannot_repeat_because_nothing_can_merge_while_it_fires(
    gh_stub: Any,
) -> None:
    """Why there is no once-per-invocation guard — pinned so nobody adds one blind.

    An earlier version of this code carried an `announced` flag, and a mutation
    deleting it escaped the suite. That was not a coverage gap: the flag was
    unreachable-by-construction. A required name that no PR reports means every PR
    fails the check gate, so nothing is eligible, so `run` breaks out of its re-read
    loop after the first read and the warning can only ever print once. The flag was
    defending against a state the gate itself makes impossible.

    Asserting "the warning printed once" would pass for the wrong reason, so this
    asserts the *reason* instead: the run reads the queue once, merges nothing, and
    says why. If someone ever makes a misconfigured gate stop blocking, this fails
    and the flag becomes necessary again.
    """
    # No PR reports `mypy — digibase + digikey`, so the gate cannot be satisfied.
    # Everything else is green and approved, so these PRs are blocked on the gate
    # alone — remove the misnaming and both would merge.
    reported = [
        {"__typename": "CheckRun", "name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
        for name in ("Required checks passed", "doc-links + agents-init")
    ]
    prs = []
    for number in (1, 2):
        pr = _pr(number)
        pr["statusCheckRollup"] = reported
        pr["reviews"] = [{"author": {"login": "someone-else"}, "state": "APPROVED"}]
        prs.append(pr)
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/digithings", "--acting-role", "cto")
    assert done.returncode == EXIT_OK
    # One read, because the first read found nothing eligible and the loop stopped.
    assert len(stub.matching("pr list")) == 1
    assert not stub.matching("pr merge")
    assert done.stderr.count("misconfigured required check") == 1
    # And the reason is named, not just the count, so the reader knows what to edit.
    assert "'mypy — digibase + digikey'" in done.stderr


def test_a_matching_gate_announces_nothing(gh_stub: Any) -> None:
    """The negative case, pinned so the detector cannot be "fixed" into noise.

    twelve-x is the repo where a bare `test` is correct. If the announcement fired
    there, the fix would have swapped a hard block for a permanent warning, which is
    the same failure wearing a different hat.
    """
    prs = [_pr(1), _pr(2, created="2026-10-02T00:00:00Z")]
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK
    assert "misconfigured" not in done.stderr
    assert done.stderr.strip() == "", done.stderr
    # These PRs block on review (no non-author approval), not on the gate — so the
    # silence is not just "everything was blocked anyway". The check gate passed:
    # with the wrong list every one of them would say `required check 'test'`.
    assert "required check" not in done.stdout


def test_the_audit_comment_records_the_checks_actually_required(gh_stub: Any) -> None:
    """The audit trail has to name the gate that ran, not the policy default.

    Otherwise every merge comment on digithings would claim the merge relied on a
    `test` check that did not exist, which is the one claim the queue's whole
    comment exists to make reliable.
    """
    prs = [_pr(42, head_sha="c" * 40, test_conclusion=None)]
    prs[0]["statusCheckRollup"] = [
        {
            "__typename": "CheckRun",
            "name": "Required checks passed",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
        {
            "__typename": "CheckRun",
            "name": "doc-links + agents-init",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
        {
            "__typename": "CheckRun",
            "name": "mypy — digibase + digikey",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
        },
    ]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run(
        "run", "--repo", "digithings-ai/digithings", "--acting-role", "cto", "--attest-review", "qa"
    )
    comments = stub.matching("pr comment 42")
    assert len(comments) == 1
    body = comments[0][comments[0].index("--body") + 1]
    assert "Required checks passed" in body
    assert "doc-links + agents-init" in body
    assert "mypy — digibase + digikey" in body


# --- review: who is allowed to say the code was read --------------------------


def test_the_author_approving_their_own_pr_does_not_count() -> None:
    pr = _pr(1, reviews=[{"author": {"login": "chrizefan"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role=None)
    assert not verdict.eligible
    assert any("no approving review from a non-author" in r for r in verdict.reasons)


def test_an_approving_review_from_someone_else_is_enough() -> None:
    """No attestation needed when a real approval exists — the queue must not stall here."""
    pr = _pr(1, reviews=[{"author": {"login": "coderabbit"}, "state": "APPROVED"}])
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="cto", base="develop", attest_role=None
    ).eligible


def test_a_bots_approval_is_not_a_review() -> None:
    """A bot's APPROVED is a linter verdict, not a person owning the change.

    GitHub's own review summary ignores bot reviews for exactly this reason. If a
    bot approval satisfied the gate, a repo with an auto-reviewing bot would show
    every PR as reviewed and the queue would merge on nothing but green checks.
    """
    pr = _pr(1, reviews=[{"author": {"login": "coderabbitai[bot]"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role=None)
    assert not verdict.eligible
    assert any("no approving review from a non-author" in r for r in verdict.reasons)


def test_a_commit_status_cannot_stand_in_for_the_build() -> None:
    """A green commit status is not evidence that anything ran.

    GitHub's commit status docs: "any person or integration with write permissions
    can set the state of any status check". So a status named `test` posted by hand
    would green-light any PR. Only a CheckRun — bound to an Actions run — counts as
    the required gate passing.
    """
    pr = _pr(1, test_conclusion=None)
    pr["statusCheckRollup"] = [
        {"__typename": "StatusContext", "context": "test", "state": "SUCCESS"}
    ]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role="qa")
    assert not verdict.eligible
    assert any("only reported as a commit status" in r for r in verdict.reasons)


def test_outstanding_change_requests_block() -> None:
    pr = _pr(
        1,
        reviews=[{"author": {"login": "someone"}, "state": "CHANGES_REQUESTED"}],
    )
    pr["reviewDecision"] = "CHANGES_REQUESTED"
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop", attest_role="qa")
    assert not verdict.eligible
    assert "review has outstanding change requests" in verdict.reasons


def test_the_merging_role_cannot_attest_its_own_review() -> None:
    """Self-attestation is refused.

    Every agent in this org pushes under one GitHub login, so GitHub cannot tell
    the author of a PR from the role merging it. The role is the only granularity
    available, which is why an attestation naming the merging role is rejected
    outright rather than trusted.
    """
    verdict = mq.evaluate(
        _pr(1), mq.load_policy(), acting_role="cto", base="develop", attest_role="cto"
    )
    assert not verdict.eligible
    assert any("also the merging role" in reason for reason in verdict.reasons)


def test_a_different_role_attesting_passes() -> None:
    assert mq.evaluate(
        _pr(1), mq.load_policy(), acting_role="cto", base="develop", attest_role="qa"
    ).eligible


def test_an_em_merge_attested_by_the_cto_passes() -> None:
    assert mq.evaluate(
        _pr(1), mq.load_policy(), acting_role="em", base="develop", attest_role="cto"
    ).eligible


# --- a verdict posted as a PR comment has to reach the gate --------------------
#
# twelve-x PR #347 merged 6m37s after a review saying "changes requested — one
# finding blocks approval" was posted on it. GitHub never saw a blocking
# `CHANGES_REQUESTED` review, so `reviewDecision` was empty, and the queue only
# fetched `reviews` — a comment was invisible to it. `--attest-review qa` then
# satisfied the gate and pointed straight past the verdict.


def test_a_posted_verdict_of_changes_requested_blocks_even_with_an_attestation() -> None:
    """The exact #347 shape: no blocking review, a distinct attestation, one verdict.

    Every other input here is the one that merged. Only the posted verdict is new,
    and it has to be enough on its own.
    """
    pr = _pr(
        347,
        reviews=[],
        comments=[_review_comment(verdict="changes_requested")],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa")
    assert not verdict.eligible
    # The refusal has to name the comment. A queue that refuses without saying
    # where the block came from is a queue nobody can clear.
    assert any("changes_requested" in r and "chrizefan" in r for r in verdict.reasons)


def test_a_posted_verdict_of_approved_does_not_block() -> None:
    """An approving verdict is a signal, not a gate. It must not turn into one."""
    pr = _pr(347, reviews=[], comments=[_review_comment(verdict="approved")])
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_a_comment_without_the_marker_is_ignored() -> None:
    """Prose is not a contract.

    The #347 comment reads `## Verdict: changes requested (narrow)` in its prose.
    Matching on that text would mean matching a heading a reviewer is free to
    reword, so the gate reads the marker's `verdict=` field and nothing else. This
    comment says the same words with no marker and must not block.
    """
    pr = _pr(
        347,
        reviews=[],
        comments=[
            {
                "id": "IC_kwDOprose_347",
                "author": {"login": "chrizefan"},
                "body": "## Verdict: changes requested (narrow)\n\n**One finding blocks approval.**",
                "createdAt": "2026-10-07T22:07:11Z",
            }
        ],
    )
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_a_pr_without_a_comments_key_does_not_crash_the_gate() -> None:
    """A missing key is a missing signal. It must not be an exception.

    `comments` is fetched conditionally and the gates run on whatever the fetch
    returned, so the shape with the key absent is one the gate will really meet.
    """
    pr = _pr(347)
    assert "comments" not in pr
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_a_verdict_against_an_older_commit_on_the_branch_still_blocks() -> None:
    """A reviewer who blocked commit A still blocks A+B.

    Forgetting to re-review after pushing a fix is the common case, and the
    finding is normally still there. Clearing this silently is how the gate
    becomes decoration.
    """
    older = "b" * 40
    head = "c" * 40
    pr = _pr(
        347,
        head_sha=head,
        reviews=[],
        comments=[_review_comment(verdict="changes_requested", head_sha=older)],
        commits=[{"oid": older}, {"oid": head}],
    )
    assert not mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_a_verdict_against_a_head_this_pr_does_not_carry_does_not_block() -> None:
    """A force-push or rebase rewrites history, and the old sha is gone.

    The verdict was about code that no longer exists, so holding the PR on it
    would strand it: the finding cannot be re-applied to the new commits, and the
    only way to clear it would be to close and reopen the PR. A reviewer who
    disagrees posts a fresh verdict against the new head.
    """
    head = "c" * 40
    pr = _pr(
        347,
        head_sha=head,
        reviews=[],
        comments=[_review_comment(verdict="changes_requested", head_sha="f" * 40)],
        commits=[{"oid": head}],
    )
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_the_latest_posted_verdict_wins() -> None:
    """A reviewer who came back and approved clears their own earlier block."""
    pr = _pr(
        347,
        reviews=[],
        comments=[
            _review_comment(verdict="changes_requested", created="2026-10-07T22:07:11Z"),
            _review_comment(verdict="approved", created="2026-10-07T22:20:00Z"),
        ],
    )
    assert mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_an_older_block_still_blocks_when_a_later_marker_has_no_verdict() -> None:
    """A typo is a missing signal, not a clearance.

    The gate refuses to read a verdict it cannot parse, and refusing to read is
    not the same as reading "approved". Letting an unreadable marker clear a
    block would hand anyone who can comment a way to unlock the queue.
    """
    pr = _pr(
        347,
        reviews=[],
        comments=[
            _review_comment(verdict="changes_requested", created="2026-10-07T22:07:11Z"),
            _review_comment(verdict="looks-fine", created="2026-10-07T22:20:00Z"),
        ],
    )
    assert not mq.evaluate(
        pr, mq.load_policy(), acting_role="em", base="develop", attest_role="qa"
    ).eligible


def test_the_fetch_asks_github_for_the_fields_the_posted_verdict_needs() -> None:
    """The structural fix, pinned: a gate cannot read a field the fetch dropped.

    This is the whole root cause of #347 — `comments` was never requested, so no
    amount of parsing could have reached it. Pinning the field list keeps the
    fetch and the gate from drifting apart again.
    """
    source = SCRIPT.read_text()
    # The field list is written as implicitly-concatenated string literals, so take
    # every literal that follows `--json` rather than only the first.
    tail = source.split('"--json",', 1)
    assert len(tail) == 2, "the fetch no longer passes --json"
    literals = re.findall(r'"([^"]*)"', tail[1])
    fields = "".join(literals)
    assert "comments" in fields
    assert "commits" in fields


# --- ordering: a queue, not a race --------------------------------------------


def test_queue_order_is_creation_order_not_greenness() -> None:
    """Oldest first. Greenest-first quietly becomes "whoever CI got back first"."""
    verdicts = [
        mq.evaluate(
            _pr(3, created="2026-10-03T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
            attest_role="qa",
        ),
        mq.evaluate(
            _pr(1, created="2026-10-01T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
            attest_role="qa",
        ),
        mq.evaluate(
            _pr(2, created="2026-10-02T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
            attest_role="qa",
        ),
    ]
    assert [v.number for v in sorted(verdicts, key=mq.Verdict.order_key)] == [1, 2, 3]


def test_ties_on_creation_time_break_on_pr_number() -> None:
    same = "2026-10-01T00:00:00Z"
    verdicts = [
        mq.evaluate(
            _pr(n, created=same),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
            attest_role="qa",
        )
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


def test_a_pr_behind_its_base_does_not_queue(gh_stub: Any) -> None:
    """A PR whose base moved after its checks ran must not merge on that evidence.

    This is the failure the queue exists to prevent, and it is invisible in the
    check rollup: after PR #1 lands, PR #2 still shows `test: SUCCESS` — from the
    run against the *previous* base. GitHub marks it `BEHIND` and the ruleset path
    catches it with `strict`; a local queue has to catch it itself or it merges
    unverified code while looking green.
    """
    prs = [_pr(1, created="2026-10-01T00:00:00Z", merge_state="BEHIND")]
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
    assert "mergeStateStatus=BEHIND" in done.stdout


def test_the_queue_asks_github_for_the_oldest_prs(gh_stub: Any) -> None:
    """`gh pr list` is newest-first, so a plain --limit truncates the head.

    Above the limit, the oldest PRs would never be fetched, never listed and never
    merged — silent head-of-line starvation, which is the opposite of what the FIFO
    ordering is for. `sort:created-asc` moves the truncation to the tail.
    """
    prs = [_pr(1, created="2026-10-01T00:00:00Z")]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
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
    assert stub.matching("sort:created-asc") != []
    # `--base` must be passed to gh, not merely checked afterwards: dropping it makes
    # the queue merge into whatever base the PR happens to target.
    assert stub.matching("--base develop") != []


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
