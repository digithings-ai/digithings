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
and accepting a review claim that left no artifact on the PR. Each of those has a
test below.

The other direction is refusing everything, which is how a queue that needs a
human for every merge looks like a queue that fixed nothing. So the tests also
pin the paths that must *succeed*: a review pass that left its findings on the PR
(a reviewer bot, an in-session review, or a human approval) with no review thread left
open on the current code. No non-author approval is required (Chris, 2026-10-15), and
QA's `qa/gate` status is ignored (Chris, 2026-10-17).

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

#: `gh api graphql` answer for a PR with no review threads.
NO_THREADS: dict[str, Any] = {
    "data": {"repository": {"pullRequest": {"reviewThreads": {"totalCount": 0, "nodes": []}}}}
}


def _pr(
    number: int,
    *,
    created: str = "2026-10-01T00:00:00Z",
    head_sha: str = "a" * 40,
    test_conclusion: str | None = "SUCCESS",
    local_ci_state: str | None = "SUCCESS",
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
    omit: tuple[str, ...] = (),
    approved: bool = False,
) -> dict[str, Any]:
    rollup: list[dict[str, Any]] = list(extra_checks or [])
    # `local-ci` is the host mirror's commit status, and it is a REQUIRED check on both
    # repos now (digithings always; twelve-x since DIG-4454, while GitHub Actions cannot
    # start). It is a StatusContext, not a CheckRun, which `status_context_checks` allows.
    if local_ci_state is not None:
        rollup.append(
            {"__typename": "StatusContext", "context": "local-ci", "state": local_ci_state}
        )
    if test_conclusion is not None:
        rollup.append(
            {
                "__typename": "CheckRun",
                "name": "test",
                "status": test_status,
                "conclusion": test_conclusion,
            }
        )
    # Review evidence for tests whose subject is NOT the review gate: the queue
    # enforces the promotion gate's evidence (DIG-3154), so a fixture that must
    # merge carries a non-author approval. Refusal tests keep the default.
    resolved_reviews = list(reviews) if reviews is not None else []
    if approved:
        resolved_reviews.append({"author": {"login": "reviewer"}, "state": "APPROVED"})
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
        "reviews": resolved_reviews,
    }
    # A correct fetch carries both keys, so the fixture carries them too: `comments`
    # empty unless the test is about the review record, and `commits` naming this head
    # unless the test is about a rewritten branch. `omit` models the row that is
    # MISSING a key — the shape `#5903` merged on, and the one the queue now refuses
    # rather than reads as "nothing was posted (#5903 post-mortem).
    #
    # This used to be the other way round, on the theory that the gates should stay
    # exercised on the shape they meet when a key is missing. What that theory missed
    # is that a gate reading an absent key is not exercised, it is blind, and the
    # blindness was the outage: `test_a_pr_without_a_comments_key_does_not_crash_the_gate`
    # asserted a missing comment list was *eligible*.
    pr["comments"] = list(comments) if comments is not None else []
    pr["commits"] = list(commits) if commits is not None else [{"oid": head_sha}]
    for key in omit:
        pr.pop(key, None)
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


def test_a_twelve_x_pr_with_no_local_ci_status_cannot_merge(gh_stub: Any) -> None:
    """The replacement gate is fail-closed: no mirror verdict means no merge.

    twelve-x's gate moved from the Actions job `test` to the host-posted `local-ci`
    status (DIG-4454). Absence must behave exactly as absence of `test` did - the
    status is the evidence, and an unposted status is not a pass.
    """
    prs = [_pr(1, local_ci_state=None)]
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == 0, done.stderr
    assert "required check 'local-ci' has not reported" in done.stdout


def test_required_check_that_never_reported_blocks_the_merge() -> None:
    """A PR with no `test` check at all must not merge.

    This was twelve-x PR #237's real shape before 2026-10-19, when its gate was the
    Actions job `test`; the mechanism is the same whichever name is required:
    the branch looks mergeable, the base's only job never reported, and the change
    lands untested. Treating "check absent" as "check passed" is the bug.
    """
    verdict = mq.evaluate(
        _pr(237, test_conclusion=None),
        mq.load_policy(),
        acting_role="cto",
        base="develop",
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
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
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
    verdict = mq.evaluate(pr, mq.load_policy(), base="develop", acting_role="cto")
    assert not verdict.eligible
    assert "baseRefName=main, expected develop" in verdict.reasons


def test_a_pending_required_check_blocks() -> None:
    verdict = mq.evaluate(
        _pr(1, test_conclusion=None, test_status="IN_PROGRESS"),
        mq.load_policy(),
        acting_role="cto",
        base="develop",
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
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert "check 'pip-audit' is FAILURE" in verdict.reasons


def test_an_ignored_check_cannot_fail_the_queue() -> None:
    pr = _pr(
        1,
        approved=True,
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
        blocked_bases=policy.blocked_bases,
        merge_method=policy.merge_method,
        delete_branch=policy.delete_branch,
        required_checks=policy.required_checks,
        required_checks_by_repo=policy.required_checks_by_repo,
        ignored_checks=frozenset({"advisory-score"}),
    )
    assert mq.evaluate(pr, policy, acting_role="cto", base="develop").eligible


# --- which checks are required, and telling misconfiguration from a red build --


def test_required_checks_are_resolved_per_repo() -> None:
    """Two repos in this org report different names, so one global list cannot serve both.

    `digithings` runs every test suite through reusable workflows, so GitHub reports
    each as `<caller> / test` — `digibase / test`, `digibot / test`, and eleven more —
    and names nothing `test`. `twelve-x` runs one job and does report a bare `test`.
    A single hardcoded list is therefore wrong for one of them, and DIG-690 measured
    which: 28 PRs blocked, every one of them on `required check 'test' has not
    reported`, in a repo where no PR has ever reported it.

    `twelve-x` is named explicitly as of DIG-4454 for a different reason: its Actions
    billing is blocked, so the `test` job cannot start and every PR reads as a red
    build. The host mirror `twelvex_ci.py` posts the same work as a `local-ci` status,
    so the queue requires that name until the minutes reset. Both repos therefore
    resolve to `local-ci` today, for two unrelated reasons — which is precisely why
    the list is per-repo rather than one global name.
    """
    policy = mq.load_policy()
    assert policy.required_for("digithings-ai/twelve-x") == ("local-ci",)
    digithings = policy.required_for("digithings-ai/digithings")
    assert digithings == ("local-ci",), digithings
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
    assert mq.unmatched_required_checks(
        [_pr(2, test_conclusion=None, local_ci_state=None)], ("test",)
    ) == ((), ())


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
    # Names the gate that cannot match (digithings requires exactly `local-ci`,
    # DIG-3707)...
    assert "'local-ci'" in err
    # ...and how many checks CI is really producing, so the reader stops hunting
    # for a failure (`local-ci` shares a word with nothing reported, so no near
    # miss is offered here — the next test pins that path).
    assert "1 distinct checks did report" in err
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
    # Deliberately not digithings' required `local-ci` context — that is the
    # DIG-690 shape. The decoys are what the reader has to choose from instead.
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
    # `local-ci` is required, unmatchable, and shares a word with nothing reported —
    # so no near miss is offered for it and the message must not imply one exists.
    assert "'local-ci'" in err
    assert "nearest:" not in err
    assert "gh pr checks" in err

    near = mq._near_misses(("test",), ("digibase / test", "digibot / test", "path-filter"))
    assert near[:2] == ["digibase / test", "digibot / test"]
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
    # No PR reports `local-ci`, so the gate cannot be satisfied.
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
            gh_rule(r"^api graphql", stdout=NO_THREADS),
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
    assert "'local-ci'" in done.stderr


def test_a_matching_gate_announces_nothing(gh_stub: Any) -> None:
    """The negative case, pinned so the detector cannot be "fixed" into noise.

    twelve-x used to be the repo where a bare `test` was correct; since DIG-4454 its
    gate is `local-ci`, and the announcement must stay silent for that name too. If it fired
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
    prs = [_pr(42, head_sha="c" * 40, test_conclusion=None, approved=True)]
    # `local-ci` arrives as a commit StatusContext, never as a CheckRun run —
    # that is the whole point of `status_context_checks` (DIG-3707).
    prs[0]["statusCheckRollup"] = [
        {
            "__typename": "StatusContext",
            "context": "local-ci",
            "state": "SUCCESS",
        },
    ]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/digithings", "--acting-role", "cto")
    comments = stub.matching("pr comment 42")
    assert len(comments) == 1
    body = comments[0][comments[0].index("--body") + 1]
    assert "local-ci" in body


# --- review: who is allowed to say the code was read --------------------------


def _coverage_state() -> dict[str, Any]:
    """A state dict shaped the way `_gate_review_coverage` builds one."""
    return {
        "labels": set(),
        "approvals": [],
        "bugbot": None,
        "title": "",
        "owner_review": None,
        "agent_tool": [],
        "agent_review": None,
    }


def test_no_review_evidence_is_refused() -> None:
    """With no review pass on the PR at all, the review gate refuses."""
    verdict = mq.evaluate(_pr(1), mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("review coverage" in r for r in verdict.reasons)
    # The old hand-back told agents to reach for an attestation. It must not.
    assert not any("attest" in r for r in verdict.reasons)


def test_the_author_approving_their_own_pr_does_not_count() -> None:
    """A self-approval is not evidence that anyone else read the change."""
    pr = _pr(1, reviews=[{"author": {"login": "chrizefan"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("review coverage" in r for r in verdict.reasons), verdict.reasons


def test_an_unlisted_bots_bare_login_approval_is_refused() -> None:
    """DIG-4298: an unlisted bot's APPROVED must not clear coverage.

    `gh` returns the bare login (no `[bot]` suffix — in production it is
    `flaky-lint` with `is_bot: true` on the author record). The queue reads
    reviews through `_evidence_reviews` and hands them to the coverage sink,
    which applies the one bot rule, so this review must not clear the gate as
    though a person had approved.
    """
    pr = _pr(
        1,
        reviews=[{"author": {"login": "flaky-lint", "is_bot": True}, "state": "APPROVED"}],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("review coverage" in r for r in verdict.reasons), verdict.reasons


def test_an_unlisted_suffixed_bot_approval_is_refused_too() -> None:
    """Any `[bot]` suffix is a linter verdict that must not be evidence either way.

    The refusal comes from the one sink rule both gates share, not from a second
    filter in the queue, so the queue and the promotion gate cannot disagree.
    """
    pr = _pr(1, reviews=[{"author": {"login": "netlify[bot]"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("review coverage" in r for r in verdict.reasons), verdict.reasons


def test_a_listed_reviewer_bots_approval_counts_as_an_agent_review_not_an_approval() -> None:
    """A listed reviewer bot's APPROVED is still evidence — as an agent review.

    Excluding bot logins from `approvals` (DIG-4298) must not exclude their
    reviews from the gate: CodeRabbit and friends clear coverage through the
    `REVIEW_BOTS` hatch, bare or suffixed, and the verdict they produce never
    claims `approved by` — the audit trail must not say a person approved.
    """
    crc = mq._coverage_module()
    for login in ("coderabbitai", "coderabbitai[bot]"):
        pr = _pr(1, reviews=[{"author": {"login": login}, "state": "APPROVED"}])
        verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
        assert verdict.eligible, (login, verdict.reasons)
        state = _coverage_state()
        crc._apply_reviews_checks_comments(
            state,
            reviews=mq._evidence_reviews(pr),
            checks=pr["statusCheckRollup"],
            comments=[],
        )
        assert state["approvals"] == [], "a bot login must not sit in approvals as a person"
        reviewed, why = crc.verdict_for(state)
        assert reviewed
        assert "agent review" in why
        assert "approved by" not in why


def test_review_evidence_alone_is_enough_at_the_production_setting() -> None:
    """The configuration production actually runs: no seat can approve its own PR,
    so review EVIDENCE alone must make a PR eligible.

    Every other no-approval case in this file asserts a REFUSAL, so without this
    test the queue's happy path would only be exercised with an approval that
    production cannot supply.
    """
    pr = _pr(
        1,
        comments=[
            {
                "id": "IC_kwDOreview_1",
                "author": {"login": "chrizefan"},
                "authorAssociation": "MEMBER",
                "createdAt": "2026-10-19T00:00:00Z",
                "body": (
                    "<!-- in-session-review -->\n\n"
                    "## Verdict: approve-with-nits\n\n0 blockers, 2 majors filed.\n"
                ),
            }
        ],
    )
    pr["labels"] = [{"name": "reviewed:agent"}]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible, verdict.reasons


def test_a_non_author_approval_is_not_required() -> None:
    """Chris's 2026-10-15 definition: a review pass that left comments is the review.

    Every agent pushes under one login, so no agent can give a non-author approval.
    An in-session review with its findings comment, and no approval, must merge.
    """
    pr = _labeled_pr(1, [_finding_comment()])
    assert pr["reviews"] == []
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible, verdict.reasons
    assert "in-session review" in verdict.review_evidence


def test_a_human_approval_still_counts() -> None:
    """A real approval stays an alternative way to meet the review gate."""
    pr = _pr(1, reviews=[{"author": {"login": "someone"}, "state": "APPROVED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible, verdict.reasons


@pytest.mark.parametrize("login", ["coderabbitai[bot]", "copilot-pull-request-reviewer[bot]"])
def test_a_reviewer_bot_pass_counts_as_the_review(login: str) -> None:
    """A reviewer bot that reviewed the diff is a review pass that left comments."""
    pr = _pr(1, reviews=[{"author": {"login": login}, "state": "COMMENTED"}])
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible, verdict.reasons


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
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("only reported as a commit status" in r for r in verdict.reasons)


def test_outstanding_change_requests_block() -> None:
    pr = _pr(
        1,
        reviews=[{"author": {"login": "someone"}, "state": "CHANGES_REQUESTED"}],
    )
    pr["reviewDecision"] = "CHANGES_REQUESTED"
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert "review has outstanding change requests" in verdict.reasons


def test_the_attest_review_option_is_gone(gh_stub: Any) -> None:
    """`--attest-review` was removed (2026-10-17); passing it is a usage error."""
    _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=[])), [])
    done = _run(
        "list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto", "--attest-review", "qa"
    )
    assert done.returncode == 2
    assert "unrecognized arguments: --attest-review" in done.stderr


def test_an_em_merge_with_review_evidence_passes() -> None:
    assert mq.evaluate(
        _pr(1, approved=True), mq.load_policy(), acting_role="em", base="develop"
    ).eligible


# --- QA is not in the review path ---------------------------------------------


@pytest.mark.parametrize("state", ["SUCCESS", "FAILURE", "PENDING", "ERROR"])
def test_a_qa_gate_status_is_ignored(state: str) -> None:
    """`qa/gate` neither clears nor blocks a merge (Chris, 2026-10-17)."""
    qa = {"__typename": "StatusContext", "context": "qa/gate", "state": state}
    with_evidence = mq.evaluate(
        _pr(1, approved=True, extra_checks=[qa]), mq.load_policy(), acting_role="em", base="develop"
    )
    assert with_evidence.eligible, with_evidence.reasons
    assert not any("qa/gate" in c for c in with_evidence.checks)
    without_evidence = mq.evaluate(
        _pr(2, extra_checks=[qa]), mq.load_policy(), acting_role="em", base="develop"
    )
    assert not without_evidence.eligible
    assert any("review coverage" in r for r in without_evidence.reasons)


def test_no_role_is_on_a_review_path() -> None:
    raw = json.loads((REPO_ROOT / "scripts" / "merge_queue_policy.json").read_text())
    assert "review_path" not in raw


# --- review comments must be resolved or addressed ----------------------------


def test_an_open_review_thread_on_current_code_blocks() -> None:
    pr = _pr(1, approved=True)
    pr["reviewThreads"] = [
        {"isResolved": False, "isOutdated": False, "path": "scripts/merge_queue.py"}
    ]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any(
        "review comments not addressed" in r and "scripts/merge_queue.py" in r
        for r in verdict.reasons
    )


@pytest.mark.parametrize(
    "thread",
    [
        {"isResolved": True, "isOutdated": False, "path": "a.py"},
        {"isResolved": False, "isOutdated": True, "path": "a.py"},
    ],
)
def test_a_resolved_or_outdated_thread_does_not_block(thread: dict[str, Any]) -> None:
    pr = _pr(1, approved=True)
    pr["reviewThreads"] = [thread]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert verdict.eligible, verdict.reasons


def test_review_threads_are_read_from_github(gh_stub: Any) -> None:
    open_thread = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": 1,
                        "nodes": [{"isResolved": False, "isOutdated": False, "path": "x.py"}],
                    }
                }
            }
        }
    }
    stub = gh_stub(gh_rule(r"^api graphql", stdout=open_thread))
    verdict = mq.evaluate(
        _pr(7, approved=True),
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    call = stub.matching("api graphql")[0]
    assert "number=7" in call and "owner=digithings-ai" in call


def test_an_unreadable_thread_list_holds_the_pr(gh_stub: Any) -> None:
    gh_stub(gh_rule(r"^api graphql", stderr="HTTP 502", exit_code=1))
    verdict = mq.evaluate(
        _pr(7, approved=True),
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    assert any("review threads could not be read" in r for r in verdict.reasons)


def test_threads_past_the_first_page_hold_the_pr(gh_stub: Any) -> None:
    many = {
        "data": {
            "repository": {
                "pullRequest": {
                    "reviewThreads": {
                        "totalCount": 101,
                        "nodes": [{"isResolved": True, "isOutdated": False, "path": "a"}] * 100,
                    }
                }
            }
        }
    }
    gh_stub(gh_rule(r"^api graphql", stdout=many))
    verdict = mq.evaluate(
        _pr(7, approved=True),
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible


def test_threads_are_not_read_for_a_pr_already_refused(gh_stub: Any) -> None:
    stub = gh_stub(gh_rule(r"^api graphql", stdout=NO_THREADS))
    verdict = mq.evaluate(
        _pr(7, draft=True, approved=True),
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    assert stub.matching("api graphql") == []


# --- a verdict posted as a PR comment has to reach the gate --------------------
#
# twelve-x PR #347 merged 6m37s after a review saying "changes requested — one
# finding blocks approval" was posted on it. GitHub never saw a blocking
# `CHANGES_REQUESTED` review, so `reviewDecision` was empty, and the queue only
# fetched `reviews` — a comment was invisible to it. `--attest-review qa` then
# satisfied the gate and pointed straight past the verdict.


def test_a_posted_verdict_of_changes_requested_blocks_even_with_an_approval() -> None:
    """The exact #347 shape: no blocking review, an approval, one verdict.

    Every other input here is the one that merged. Only the posted verdict is new,
    and it has to be enough on its own.
    """
    pr = _pr(
        347,
        reviews=[],
        approved=True,
        comments=[_review_comment(verdict="changes_requested")],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    # The refusal has to name the comment. A queue that refuses without saying
    # where the block came from is a queue nobody can clear.
    assert any("changes_requested" in r and "chrizefan" in r for r in verdict.reasons)


def test_a_posted_verdict_of_approved_does_not_block() -> None:
    """An approving verdict is a signal, not a gate. It must not turn into one."""
    pr = _pr(347, reviews=[], approved=True, comments=[_review_comment(verdict="approved")])
    assert mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


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
        approved=True,
        comments=[
            {
                "id": "IC_kwDOprose_347",
                "author": {"login": "chrizefan"},
                "body": "## Verdict: changes requested (narrow)\n\n**One finding blocks approval.**",
                "createdAt": "2026-10-07T22:07:11Z",
            }
        ],
    )
    assert mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


def test_a_pr_without_a_comments_key_is_not_a_clearance() -> None:
    """A missing key is a missing signal: not an exception, and not a clearance.

    This is the `#5903` post-mortem, and the version of this test that stood here
    asserted the opposite. The host tick fetched its rows with a field list that left
    `comments` out, so `_posted_verdict_reason` read nothing and `_gate_review` stayed
    silent — while four review passes sat on that PR, the newest a
    `changes_requested`. It merged on the coverage gate; the queue's own audit comment
    names it (`review: review evidence via the coverage gate`).

    With no repo there is nothing to read from, so the refusal has to be the verdict.
    """
    pr = _pr(347, approved=True, omit=("comments",))
    assert "comments" not in pr
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("review record could not be read" in r for r in verdict.reasons)


def test_the_review_record_is_fetched_before_the_verdict_gate(gh_stub: Any) -> None:
    """The `#5903` repair: one read, before both review gates.

    `_review_coverage` does fetch comments lazily, but it runs *after* `_gate_review`,
    so on its own it cannot repair a row `_gate_review` has already read as
    verdict-free. Here the row carries no comments and a `changes_requested` verdict
    is waiting behind the fetch.
    """
    gh_stub(
        gh_rule(
            r"^pr view",
            stdout={"comments": [_review_comment(verdict="changes_requested")]},
        ),
        gh_rule(r"^api graphql", stdout=NO_THREADS),
    )
    pr = _pr(347, approved=True, omit=("comments",))
    verdict = mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    assert any("changes_requested" in r for r in verdict.reasons)
    # The fetch completes the row rather than standing in for it, so the coverage gate
    # downstream reads the same comments instead of fetching them a second time.
    assert pr["comments"]


def test_a_fetched_empty_comment_list_is_still_a_clearance() -> None:
    """Positive control: the repair must not touch an ordinary green PR.

    `comments=[]` is what the runner's own fetch produces for a PR nobody has
    commented on. It is a read that came back empty, which is not the same thing as a
    read that could not happen.
    """
    pr = _pr(347, approved=True)
    assert pr["comments"] == []
    assert mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


@pytest.mark.parametrize("payload", ["null", "[]"])
def test_a_comment_read_with_no_comment_list_is_not_an_empty_read(
    gh_stub: Any, payload: str
) -> None:
    """A read that returns no comment list is unreadable, not clean.

    `_gh_json` maps empty stdout to `None`, and `gh` is not promised to answer with an
    object, so `null` and a bare list are the shapes that reach the guard. Reading either
    as "no verdict was posted" is the same hole one layer down, so the refusal stands.
    """
    gh_stub(
        gh_rule(r"^pr view", stdout=payload),
        gh_rule(r"^api graphql", stdout=NO_THREADS),
    )
    pr = _pr(347, approved=True, omit=("comments",))
    verdict = mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    assert any("returned no comment list" in r for r in verdict.reasons)


def test_a_comment_read_that_could_not_be_parsed_is_a_refusal_not_a_traceback(
    gh_stub: Any,
) -> None:
    """An unparseable read is refused in the gate's own words, not as a traceback.

    `gh` answered with something that is not JSON, so `_gh_json` raises `ValueError`.
    Escaping `evaluate` would surface as a traceback instead of the queue's named
    refusal, for a shape the gate could simply read as unreadable.
    """
    gh_stub(
        gh_rule(r"^pr view", stdout="{not json"),
        gh_rule(r"^api graphql", stdout=NO_THREADS),
    )
    pr = _pr(347, approved=True, omit=("comments",))
    verdict = mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="em",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    assert any("could not be read" in r for r in verdict.reasons)


def test_a_comments_field_that_is_not_a_list_is_refused() -> None:
    """A malformed row is unreadable, not empty.

    `comments is not None` would have accepted any truthy value here, and both gates
    would then have scored it as no comments at all. The guard asks for a list.
    """
    pr = _pr(347, approved=True)
    pr["comments"] = "not a list"
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("not a list" in r for r in verdict.reasons)


def test_a_missing_commits_key_does_not_clear_a_posted_block() -> None:
    """The second leg of `#5903`: unverifiable ancestry must not spend a block.

    `_on_pr_history` answers "is the verdict's commit still on this branch?" from
    `pr["commits"]`. With no commit list the question is unanswerable, and the shape
    that answered "no" retired a verdict whose commit was still on the branch.
    """
    pr = _pr(
        347,
        head_sha="c" * 40,
        approved=True,
        comments=[_review_comment(verdict="changes_requested", head_sha="b" * 40)],
        omit=("commits",),
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("changes_requested" in r and "no commit list" in r for r in verdict.reasons)


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
        approved=True,
        comments=[_review_comment(verdict="changes_requested", head_sha=older)],
        commits=[{"oid": older}, {"oid": head}],
    )
    assert not mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


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
        approved=True,
        comments=[_review_comment(verdict="changes_requested", head_sha="f" * 40)],
        commits=[{"oid": head}],
    )
    assert mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


def test_the_latest_posted_verdict_wins() -> None:
    """A reviewer who came back and approved clears their own earlier block."""
    pr = _pr(
        347,
        reviews=[],
        approved=True,
        comments=[
            _review_comment(verdict="changes_requested", created="2026-10-07T22:07:11Z"),
            _review_comment(verdict="approved", created="2026-10-07T22:20:00Z"),
        ],
    )
    assert mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


def test_an_older_block_still_blocks_when_a_later_marker_has_no_verdict() -> None:
    """A typo is a missing signal, not a clearance.

    The gate refuses to read a verdict it cannot parse, and refusing to read is
    not the same as reading "approved". Letting an unreadable marker clear a
    block would hand anyone who can comment a way to unlock the queue.
    """
    pr = _pr(
        347,
        reviews=[],
        approved=True,
        comments=[
            _review_comment(verdict="changes_requested", created="2026-10-07T22:07:11Z"),
            _review_comment(verdict="looks-fine", created="2026-10-07T22:20:00Z"),
        ],
    )
    assert not mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop").eligible


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


def test_the_default_limit_stays_under_github_node_cap() -> None:
    """DIG-3240: the default fetch must stay under GitHub's 500,000-node cap.

    The --json field list costs ~10,502 possible nodes per PR, so limit 50
    (~525k) is rejected and `run` at the default exits 1 with an unreadable
    queue. The default must stay at or below 47, with headroom preferred.
    """
    # Read the real default out of the script, not a copy of it.
    source = SCRIPT.read_text()
    match = re.search(r'add_argument\("--limit", type=int, default=(\d+)', source)
    assert match is not None, "the --limit default is gone from merge_queue.py"
    default = int(match.group(1))
    assert default * 10502 < 500000, (
        f"default --limit {default} costs ~{default * 10502} nodes, over GitHub's 500,000 cap"
    )


def test_a_pr_with_no_evidence_at_all_is_refused() -> None:
    """The #5489/#5277 shape: no labels, no reviews, no Bot runs — refused."""
    pr = _pr(1)
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="em", base="develop")
    assert not verdict.eligible
    assert any("no completed agent review" in reason for reason in verdict.reasons)


def test_a_bugbot_success_clears_review_coverage() -> None:
    """The strongest hatch: a completed Bugbot run is the review."""
    pr = _pr(
        1,
        extra_checks=[
            {
                "__typename": "CheckRun",
                "name": "Cursor Bugbot",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
            }
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible
    assert not any("review coverage" in reason for reason in verdict.reasons)


def test_a_reviewed_owner_label_clears_review_coverage() -> None:
    """The accountability hatch: label read, actor recorded by the main gate.

    Attestation still carries the `_gate_review` half here — the point is that
    the *coverage* half is satisfied by the label alone.
    """
    pr = _pr(1)
    pr["labels"] = [{"name": "reviewed:owner"}]
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert verdict.eligible
    assert not any("review coverage" in reason for reason in verdict.reasons)


# --- ordering: a queue, not a race --------------------------------------------


def test_queue_order_is_creation_order_not_greenness() -> None:
    """Oldest first. Greenest-first quietly becomes "whoever CI got back first"."""
    verdicts = [
        mq.evaluate(
            _pr(3, created="2026-10-03T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
        ),
        mq.evaluate(
            _pr(1, created="2026-10-01T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
        ),
        mq.evaluate(
            _pr(2, created="2026-10-02T00:00:00Z"),
            mq.load_policy(),
            acting_role="cto",
            base="develop",
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
    prs = [_pr(42, head_sha="b" * 40, approved=True)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
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
    prs = [_pr(42, approved=True)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "em")
    assert stub.matching("pr merge")
    assert all("--admin" not in call for call in stub.matching("pr merge"))


def test_run_re_reads_the_queue_after_every_merge(gh_stub: Any) -> None:
    """Merging one PR can dirty the next. A queue computed once merges stale verdicts.

    The stub serves a queue that shrinks as PRs merge, which is what the real API
    does: `gh pr list --state open` stops returning a PR the moment it lands.
    """
    stub = gh_stub(
        gh_rule(r"^pr list", stdout_files=["q1.json", "q2.json", "q3.json"]),
        gh_rule(r"^api graphql", stdout=NO_THREADS),
        gh_rule(r"^pr merge", stdout=""),
        gh_rule(r"^pr comment", stdout=""),
    )
    stub.wrote("q1.json", json.dumps([_pr(1, approved=True), _pr(2, approved=True)]))
    stub.wrote("q2.json", json.dumps([_pr(2, approved=True)]))
    stub.wrote("q3.json", json.dumps([]))
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
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
        gh_rule(r"^api graphql", stdout=NO_THREADS),
        gh_rule(r"^pr merge", stdout=""),
        gh_rule(r"^pr comment", stdout=""),
    )
    stub.wrote("q1.json", json.dumps([_pr(1, approved=True), _pr(2, approved=True)]))
    # After #1 lands, #2 has gone conflicted against the new develop tip.
    stub.wrote("q2.json", json.dumps([_pr(2, mergeable="CONFLICTING")]))
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--max-merges",
        "5",
    )
    assert done.returncode == EXIT_OK, done.stderr
    merged = [c[2] for c in stub.matching("pr merge")]
    assert merged == ["1"], "must not merge #2 from a verdict computed before #1 landed"
    assert "mergeable=CONFLICTING" in done.stdout


# --- a stale branch is brought up to date, not dead-ended ---------------------
#
# `strict` protection plus `STALE_MERGE_STATES` means every merge this queue lands makes
# every *other* PR `BEHIND` — a state the queue then refuses. Nothing else in the script
# could clear it, so the queue drained one PR per operator and then dead-ended: measured
# on digithings on 2026-10-19, a single merge left 23 PRs blocked and the next one needed
# a hand-run `gh pr update-branch` before it could queue at all.
#
# The step is deliberately narrow. It touches only a PR whose *sole* reason is `BEHIND`,
# and only one per run, because an update spends a full CI run and the next merge
# invalidates it. Each of those bounds has a test.


def test_a_merge_that_leaves_the_next_pr_behind_does_not_dead_end_the_queue(
    gh_stub: Any,
) -> None:
    """The queue's own merge must not be the reason the queue stops.

    #1 is clean; #2 is `BEHIND` with everything else green. After #1 lands, #2's branch
    has to be brought up to date or nothing can queue until a human intervenes.
    """
    prs = [
        _pr(1, approved=True),
        _pr(
            2,
            created="2026-10-02T00:00:00Z",
            head_sha="b" * 40,
            approved=True,
            merge_state="BEHIND",
        ),
    ]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
            gh_rule(r"update-branch", stdout=""),
        ),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert [c[2] for c in stub.matching("pr merge")] == ["1"]
    updates = stub.matching("update-branch")
    assert len(updates) == 1, "the stale PR's branch must be brought up to date"
    call = " ".join(updates[0])
    assert "/pulls/2/update-branch" in call
    # Pinned to the head the verdict was read from, exactly as a merge is: a push
    # landing in between must be reported, never merged under.
    assert f"expected_head_sha={'b' * 40}" in call
    assert "#2" in done.stdout


def test_a_stale_pr_is_never_merged_on_the_read_that_updated_it(gh_stub: Any) -> None:
    """The update re-runs the checks, so until they report there is no verdict to merge."""
    prs = [_pr(7, approved=True, merge_state="BEHIND")]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"update-branch", stdout=""),
        ),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert stub.matching("pr merge") == []
    assert len(stub.matching("update-branch")) == 1


def test_list_names_the_stale_branches_and_updates_nothing(gh_stub: Any) -> None:
    """`list` is the read-only view: it shows the stale set and touches nothing."""
    prs = [
        _pr(7, approved=True, merge_state="BEHIND"),
        _pr(8, created="2026-10-02T00:00:00Z", approved=True, merge_state="BEHIND"),
    ]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK
    assert "stale (2)" in done.stdout
    assert "#7" in done.stdout and "#8" in done.stdout
    assert stub.matching("update-branch") == [], "list must not write"


def test_a_pr_blocked_for_a_real_reason_is_not_updated(gh_stub: Any) -> None:
    """An update is only worth a CI run when it makes the PR queueable.

    `BEHIND` *plus* a red check is a PR someone has to fix; updating its branch would
    re-run every check and land on the same verdict.
    """
    prs = [
        _pr(
            9,
            approved=True,
            merge_state="BEHIND",
            extra_checks=[
                {
                    "__typename": "CheckRun",
                    "name": "lint",
                    "status": "COMPLETED",
                    "conclusion": "FAILURE",
                }
            ],
        )
    ]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert stub.matching("update-branch") == []


def test_only_one_stale_branch_is_updated_per_run_by_default(gh_stub: Any) -> None:
    """More than one is wasted: the next merge invalidates every other update's CI."""
    prs = [
        _pr(11, approved=True, merge_state="BEHIND"),
        _pr(12, created="2026-10-02T00:00:00Z", approved=True, merge_state="BEHIND"),
        _pr(13, created="2026-10-03T00:00:00Z", approved=True, merge_state="BEHIND"),
    ]
    stub = _queue_stub(
        gh_stub(gh_rule(r"^pr list", stdout=prs), gh_rule(r"update-branch", stdout="")),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert len(stub.matching("update-branch")) == 1


def test_the_oldest_stale_branch_is_the_one_updated(gh_stub: Any) -> None:
    """The same FIFO rule as the merge order: oldest first, not whatever is cheapest."""
    prs = [
        _pr(20, created="2026-10-05T00:00:00Z", approved=True, merge_state="BEHIND"),
        _pr(19, created="2026-10-01T00:00:00Z", approved=True, merge_state="BEHIND"),
    ]
    stub = _queue_stub(
        gh_stub(gh_rule(r"^pr list", stdout=prs), gh_rule(r"update-branch", stdout="")),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    updates = stub.matching("update-branch")
    assert len(updates) == 1
    assert "/pulls/19/update-branch" in " ".join(updates[0])


def test_max_updates_zero_turns_the_stale_step_off(gh_stub: Any) -> None:
    """An operator who wants the head-of-queue merge only must still be able to ask."""
    prs = [_pr(5, approved=True, merge_state="BEHIND")]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--max-updates",
        "0",
    )
    assert done.returncode == EXIT_OK, done.stderr
    assert stub.matching("update-branch") == []
    assert "mergeStateStatus=BEHIND" in done.stdout


def test_a_failed_update_fails_the_run_instead_of_looking_like_success(
    gh_stub: Any,
) -> None:
    """A refused update — a conflict, a moved head — is an answer, not a no-op.

    The alternative is the mode this queue exists to avoid: reporting a clean tick
    when the thing that was supposed to happen did not.
    """
    prs = [_pr(5, approved=True, merge_state="BEHIND")]
    _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"update-branch", stderr="gh: update branch failed", exit_code=1),
        ),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OPERATIONAL
    assert "update-branch of #5 failed" in done.stderr


@pytest.mark.parametrize("state", ["BLOCKED", "UNKNOWN", "DIRTY"])
def test_only_behind_is_updated_not_another_stale_state(gh_stub: Any, state: str) -> None:
    """`BLOCKED`, `UNKNOWN` and `DIRTY` are stale too, and an update clears none of them.

    They are all in `STALE_MERGE_STATES`, so a predicate that widened to the whole set
    would spend a CI run on a branch GitHub has not finished evaluating, or on one a
    blocking check names — and updating does not make either queueable.
    """
    prs = [_pr(30, approved=True, merge_state=state)]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert stub.matching("update-branch") == [], f"{state} must not be updated"


def test_a_benign_422_is_reported_without_failing_the_tick(gh_stub: Any) -> None:
    """The API refuses an update two ways and the response does not separate them.

    A head that moved between the read and the call, and the benign "no new commits on
    the base branch" a concurrent tick produces, both arrive as 422. The branch is
    unchanged either way, so failing the run would report the tick as broken after its
    merges had already landed.
    """
    prs = [_pr(5, approved=True, merge_state="BEHIND")]
    _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"update-branch", stderr="gh: Validation Failed (HTTP 422)", exit_code=1),
        ),
        prs,
    )
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OK, done.stderr
    assert "refused (422)" in done.stderr
    # A refusal leaves the branch as it was, so it must not be announced as an update.
    assert "updated #5" not in done.stdout


def test_max_updates_above_one_updates_that_many_oldest_first(gh_stub: Any) -> None:
    """The cap is a cap, not a switch: `--max-updates N` is what the docs promise."""
    prs = [
        _pr(11, approved=True, merge_state="BEHIND"),
        _pr(12, created="2026-10-02T00:00:00Z", approved=True, merge_state="BEHIND"),
        _pr(13, created="2026-10-03T00:00:00Z", approved=True, merge_state="BEHIND"),
    ]
    stub = _queue_stub(
        gh_stub(gh_rule(r"^pr list", stdout=prs), gh_rule(r"update-branch", stdout="")),
        prs,
    )
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
        "--max-updates",
        "2",
    )
    assert done.returncode == EXIT_OK, done.stderr
    calls = [" ".join(c) for c in stub.matching("update-branch")]
    assert len(calls) == 2
    assert "/pulls/11/" in calls[0] and "/pulls/12/" in calls[1]


def test_dry_run_does_not_update_a_stale_branch(gh_stub: Any) -> None:
    """`--dry-run` has to stay read-only now that run mode has a second write path."""
    prs = [_pr(5, approved=True, merge_state="BEHIND")]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto", "--dry-run")
    assert done.returncode == EXIT_OK, done.stderr
    assert stub.matching("update-branch") == []
    assert stub.matching("pr merge") == []


def test_dry_run_changes_nothing(gh_stub: Any) -> None:
    prs = [_pr(42, approved=True)]
    stub = _queue_stub(gh_stub(gh_rule(r"^pr list", stdout=prs)), prs)
    done = _run(
        "run",
        "--repo",
        "digithings-ai/twelve-x",
        "--acting-role",
        "cto",
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
    prs = [_pr(42, head_sha="c" * 40, approved=True)]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "em")
    comments = stub.matching("pr comment 42")
    assert len(comments) == 1
    body = comments[0][comments[0].index("--body") + 1]
    assert "no decision card required" in body
    assert "`em`" in body
    assert "`qa`" not in body
    assert "approved by reviewer" in body
    assert "no unresolved review threads" in body
    assert ("c" * 12) in body


def test_max_merges_defaults_to_one(gh_stub: Any) -> None:
    """One merge per invocation, re-read between invocations."""
    prs = [
        _pr(1, created="2026-10-01T00:00:00Z", approved=True),
        _pr(2, created="2026-10-02T00:00:00Z", approved=True),
    ]
    stub = _queue_stub(
        gh_stub(
            gh_rule(r"^pr list", stdout=prs),
            gh_rule(r"^api graphql", stdout=NO_THREADS),
            gh_rule(r"^pr merge", stdout=""),
            gh_rule(r"^pr comment", stdout=""),
        ),
        prs,
    )
    _run("run", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert [c[2] for c in stub.matching("pr merge")] == ["1"]


def test_an_operational_gh_failure_is_reported_not_swallowed(gh_stub: Any) -> None:
    _queue_stub(
        gh_stub(gh_rule(r"^pr list", stderr="gh: authentication required", exit_code=1)), []
    )
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OPERATIONAL
    assert "authentication required" in done.stderr


def test_a_gh_transport_failure_names_the_exit_status_and_retry(gh_stub: Any) -> None:
    """A gh non-zero exit with empty stdout is a retryable transport error.

    DIG-3822: a 504-class `gh` failure surfaced as a JSON parse error, which
    reads as a bug in the response handling rather than a transient transport
    fault on a read. The message must name the exit status and say retry.
    """
    _queue_stub(
        gh_stub(
            gh_rule(
                r"^pr list",
                stdout="",
                stderr="HTTP 504: upstream request timeout (https://api.github.com/graphql)",
                exit_code=1,
            )
        ),
        [],
    )
    done = _run("list", "--repo", "digithings-ai/twelve-x", "--acting-role", "cto")
    assert done.returncode == EXIT_OPERATIONAL
    assert "exit 1" in done.stderr
    assert "retry" in done.stderr.lower()
    assert "non-JSON" not in done.stderr


def test_the_policy_file_is_validated_not_assumed(tmp_path: Path) -> None:
    """A roster edited into an unknown schema fails closed rather than merging under defaults."""
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps({"schema": 2}), encoding="utf-8")
    with pytest.raises(mq.QueueError, match="unsupported schema"):
        mq.load_policy(bad)


# ── AGENTS.md vs this roster (DIG-690) ────────────────────────────────────────
#
# AGENTS.md is the file every adapter loads as canonical rules, and its
# Merge-when-ready section said "when a task PR is merge-ready, merge it" while
# this queue refuses every role that is not cto or em. That is a contradiction an
# agent resolves by picking the sentence it read most recently, and both wrong
# answers fail silently: one merges behind a control, the other stalls on a green
# PR. The prose now names the roster. These tests pin it to *this* policy file, so
# a later roster edit that forgets to update AGENTS.md fails CI instead of shipping
# the same contradiction under a new name.

AGENTS_MD = REPO_ROOT / "AGENTS.md"
MERGE_QUEUE_DOC = REPO_ROOT / "docs" / "MERGE_QUEUE.md"
AGENTS_YML = REPO_ROOT / "agents.yml"


def _agents_merge_when_ready() -> str:
    """The Merge-when-ready section of AGENTS.md, up to the next H2."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    start = text.index("## Merge-when-ready")
    rest = text[start + 1 :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def test_agents_md_names_every_role_that_can_merge() -> None:
    section = _agents_merge_when_ready()
    for authority in mq.load_policy().merge_authorities:
        assert f"`{authority.role}`" in section, (
            f"AGENTS.md § Merge-when-ready does not name merge authority "
            f"{authority.role!r}; an agent reading only AGENTS.md would not know "
            f"the roster"
        )


def test_agents_md_sends_develop_merges_through_the_queue() -> None:
    section = _agents_merge_when_ready()
    assert "scripts/merge_queue.py" in section
    assert "scripts/merge_queue_policy.json" in section
    # The carve-out has to be scoped to develop and say the stacked path is
    # unaffected, or it reads as "agents no longer merge anything".
    assert "develop" in section and "module/" in section


def test_the_roster_is_stated_once_and_the_two_docs_link_each_other() -> None:
    agents = _agents_merge_when_ready()
    queue = MERGE_QUEUE_DOC.read_text(encoding="utf-8")
    anchor = "develop-merges-go-through-the-merge-queue"
    assert f"../AGENTS.md#{anchor}" in queue
    assert "MERGE_QUEUE.md" in agents


def test_the_generated_rule_adapters_carry_the_roster() -> None:
    """agents.yml feeds .cursor/rules and .github/copilot-instructions.md.

    Those two are what Cursor and Copilot actually read, so a rule that lives only
    in AGENTS.md does not reach half the fleet.
    """
    import yaml  # local: agents_init.py requires it too, so CI has it

    rules = yaml.safe_load(AGENTS_YML.read_text(encoding="utf-8"))["rules"]
    merge_rules = [r for r in rules if "Merge-when-ready" in r]
    assert len(merge_rules) == 1, "expected exactly one merge rule in agents.yml"
    rule = merge_rules[0]
    assert "scripts/merge_queue.py" in rule
    for authority in mq.load_policy().merge_authorities:
        assert f"`{authority.role}`" in rule


# --- review claims: a claimed review must have its artifact (DIG-3154) --------
# PR #5526 merged with the `reviewed:agent` label, zero reviews and no findings
# comment; the promotion gate (`scripts/check_review_coverage.py`) refused it and
# the promotion turned red. The queue refuses that shape here, where the fix is
# a comment instead of another promotion. Deliberately narrower than the full
# promotion gate: a PR with no claim at all still merges.

_MARKER = "<!-- in-session-review -->"


def _labeled_pr(number: int, comments: list[dict[str, Any]] | None) -> dict[str, Any]:
    """A `reviewed:agent` PR.

    `comments=None` means the row was fetched WITHOUT the comment list — the shape the
    coverage gate fetches lazily, and, since `#5903`, the shape `_ensure_comments`
    refuses when it has no repo to read from. A read that came back empty is
    `comments=[]`, which is a different row.
    """
    pr = _pr(number, omit=("comments",))
    pr["labels"] = [{"name": "reviewed:agent"}]
    if comments is not None:
        pr["comments"] = comments
    return pr


def _finding_comment() -> dict[str, Any]:
    return {
        "author": {"login": "chrizefan"},
        "body": f"findings for this PR\n\n{_MARKER}\nsha 71bae0e9",
        "createdAt": "2026-10-12T23:08:43Z",
        "url": "https://github.com/digithings-ai/digithings/pull/5526#issuecomment-1",
    }


def test_a_claimed_review_with_its_findings_comment_merges() -> None:
    """Label plus marker comment is the satisfied hatch — the queue must not add friction."""
    verdict = mq.evaluate(
        _labeled_pr(5526, [_finding_comment()]),
        mq.load_policy(),
        acting_role="cto",
        base="develop",
    )
    assert verdict.eligible
    assert not any("reviewed:agent" in reason for reason in verdict.reasons)


def test_a_claimed_review_without_its_findings_comment_is_refused() -> None:
    """The #5526 shape: label, zero reviews, prose but no marker. Must not merge."""
    pr = _labeled_pr(
        5526,
        [
            {
                "author": {"login": "chrizefan"},
                "body": "looks good",
                "createdAt": "2026-10-12T22:00:00Z",
            }
        ],
    )
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any(
        "reviewed:agent" in reason and "in-session-review" in reason for reason in verdict.reasons
    )


def test_a_claimed_review_whose_comments_cannot_be_read_is_refused() -> None:
    """Fail closed: without a repo to read comments from, the claim is unverifiable."""
    pr = _labeled_pr(5526, None)
    assert "comments" not in pr
    verdict = mq.evaluate(pr, mq.load_policy(), acting_role="cto", base="develop")
    assert not verdict.eligible
    assert any("cannot be verified" in reason for reason in verdict.reasons)


def test_a_claimed_review_fetches_comments_lazily(gh_stub: Any) -> None:
    """`gh pr list` carries labels but no comments; the queue fetches them only for a claim."""
    gh_stub(
        gh_rule(r"^pr view", stdout={"comments": [_finding_comment()]}),
        gh_rule(r"^api graphql", stdout=NO_THREADS),
    )
    pr = _labeled_pr(5526, None)
    verdict = mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="cto",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert verdict.eligible


def test_an_unreadable_comments_fetch_is_refused(gh_stub: Any) -> None:
    """A failing comments read is a refused merge, not a skipped gate."""
    gh_stub(gh_rule(r"^pr view", stdout="", stderr="boom", exit_code=1))
    pr = _labeled_pr(5526, None)
    verdict = mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="cto",
        base="develop",
        repo="digithings-ai/digithings",
    )
    assert not verdict.eligible
    # Name the gate: `_review_coverage` also says it could not read something,
    # and this PR is about which one speaks first on a row with no comments.
    assert any(
        reason.startswith("the review record could not be read") for reason in verdict.reasons
    ), verdict.reasons


def _verdict(
    number: int,
    *,
    stale: bool,
    eligible: bool = False,
    created_at: str = "2026-10-01T00:00:00Z",
) -> Any:
    """A verdict with only the fields the stale selection reads."""
    return mq.Verdict(
        number=number,
        title=f"PR {number}",
        head_ref=f"task/{number}-slug",
        created_at=created_at,
        head_sha="a" * 40,
        eligible=eligible,
        stale_base_only=stale,
    )


def test_only_a_branch_stale_because_the_base_moved_is_offered_for_an_update() -> None:
    """A branch that is broken is not fixed by updating it.

    Updating a branch costs a full CI run, so a PR that is blocked for a real
    reason must not be refreshed: it would spend the run and stay blocked.
    """
    verdicts = [
        _verdict(1, stale=False),
        _verdict(2, stale=True),
        _verdict(3, stale=False),
        _verdict(4, stale=True),
        # A PR that is eligible is not stale: refreshing it would spend a CI run
        # on a branch the queue can merge as it stands.
        _verdict(5, stale=False, eligible=True),
    ]
    offered = mq.stale_candidates(verdicts, 10)
    assert [v.number for v in offered] == [2, 4]


def test_the_number_of_branches_offered_for_an_update_is_bounded() -> None:
    """The limit is the number of CI runs one tick may spend."""
    verdicts = [_verdict(n, stale=True) for n in (1, 2, 3, 4, 5)]
    assert [v.number for v in mq.stale_candidates(verdicts, 3)] == [1, 2, 3]
    assert mq.stale_candidates(verdicts, 0) == []
    assert mq.stale_candidates(verdicts, -1) == []


def test_the_branches_offered_for_an_update_are_the_oldest_first() -> None:
    """The oldest PR has been waiting longest for the CI run an update spends.

    The order comes from when the PR was created, not from the order the caller
    happened to hand the list over in: a caller that sorted the list any other
    way would otherwise refresh a different set than the queue merges first.
    """
    verdicts = [
        _verdict(7, stale=True, created_at="2026-10-05T00:00:00Z"),
        _verdict(3, stale=True, created_at="2026-10-01T00:00:00Z"),
        _verdict(5, stale=True, created_at="2026-10-03T00:00:00Z"),
    ]
    assert [v.number for v in mq.stale_candidates(verdicts, 2)] == [3, 5]
