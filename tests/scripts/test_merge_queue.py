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

import http.client
import importlib.util
import json
import re
import subprocess
import sys
import urllib.error
from dataclasses import replace
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


@pytest.fixture(autouse=True)
def reviewer_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the reviewer-independence gate out of every other test in this file.

    The shipped policy turns the gate on in shadow mode, and shadow mode reads
    the Paperclip API. A unit test must not talk to the live control plane, so
    the gate is off by default here and switched on explicitly by the tests
    that are about it.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "off")

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
    local_ci_target_url: str = "",
    local_ci_started_at: str = "2026-10-21T02:06:27Z",
    local_ci_created_at: str = "",
) -> dict[str, Any]:
    rollup: list[dict[str, Any]] = list(extra_checks or [])
    # `local-ci` is the host mirror's commit status, and it is a REQUIRED check on both
    # repos now (digithings always; twelve-x since DIG-4454, while GitHub Actions cannot
    # start). It is a StatusContext, not a CheckRun, which `status_context_checks` allows.
    if local_ci_state is not None:
        status_row: dict[str, Any] = {
            "__typename": "StatusContext",
            "context": "local-ci",
            "state": local_ci_state,
            # A commit status names the build that made it green. Today it names
            # none, which is the hole the provenance gate closes (DIG-4794).
            "targetUrl": local_ci_target_url,
        }
        # GitHub sends `startedAt` for a commit status in one API version and
        # `createdAt` in another, and the gate reads both.
        if local_ci_created_at:
            status_row["createdAt"] = local_ci_created_at
        else:
            status_row["startedAt"] = local_ci_started_at
        rollup.append(status_row)
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
    each as `<caller> / test` — `digibase / test`, `digiclaw / test`, and eleven more —
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


# --- CI provenance (DIG-4794) --------------------------------------------------
#
# A commit status is worth what its writer is worth: "any person or integration
# with write permissions can set the state of any status check". Both repositories
# the queue manages name `local-ci` as their required check, so the queue is the
# only gate - and until this gate, a green word was enough to merge.
#
# The gate asks the status to name the build that made it green, and then reads
# that build back from the Woodpecker API. The tests below are the cases the
# ticket names: a status that names no build, a build on another host, a build
# that ran another commit, a build that did not succeed, and the good case.

DIGITHINGS_REPO = "digithings-ai/digithings"
TWELVE_X_REPO = "digithings-ai/twelve-x"

#: A build URL as Woodpecker's own `CI_PIPELINE_URL` holds it.
GOOD_TARGET_URL = "http://localhost:8000/repos/6/pipeline/259"

#: The real read, kept before the fixture replaces it: one test drives the
#: socket path itself, because the redirect handling cannot be seen from the
#: outside.
_REAL_WOODPECKER_READ = mq._woodpecker_read

#: The real GitHub reader, kept for the same reason: the receipt is read from
#: the REST endpoint, and the rest of the queue keeps reading GitHub.
_REAL_GH_JSON = mq._gh_json

#: The real reader of the deployment's configuration, kept for the same reason:
#: the tests that check how an address is derived need the real one.
_REAL_DEPLOYMENT_CONFIG_FILES = mq._deployment_config_files


@pytest.fixture(autouse=True)
def _provenance_off_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No test may reach the Woodpecker API unless it is about the gate.

    The shipped policy runs the gate in `shadow`, and shadow still reads the
    build to be able to say what it would have refused. The switch is off for
    every other test, so the suite never depends on a Woodpecker instance being
    up and never reads the deployment's token file.

    The log path is pinned under `tmp_path` for every test, not deleted: a test
    that turns the gate on then writes its line to a temporary file instead of
    the deployment's operator log, which is the queue's own record of what it
    refused and would read a fixture's text as a real refusal. The index beside
    the log is pinned the same way, for the same reason.

    The deployment's configuration is read from a fixture file, not from the
    deployment: the addresses are read from the machine the queue runs on, so
    a test that read the real ones would pass on this machine and fail on the
    next one.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_OFF)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(tmp_path / "ci-provenance.log"))
    monkeypatch.setenv(mq.PROVENANCE_INDEX_ENV, str(tmp_path / "ci-provenance.index.json"))
    monkeypatch.delenv("WOODPECKER_TOKEN", raising=False)
    # The token, the build reads, the allowed hosts and the log index are
    # cached on the module, so they are cleared for every test: a token read by
    # one test must not answer for the next one, a read cached by one test
    # must not answer for the next one, and a refusal counted by one test must
    # not silence the log of the next one.
    mq._TOKEN_CACHE.clear()
    mq._READ_CACHE.clear()
    mq._HOST_CACHE.clear()
    mq._HOST_FAILURE.clear()
    mq._INDEX_CACHE.clear()
    mq._LOG_CACHE.clear()

    config = tmp_path / "local-forge.env"
    config.write_text(
        "WOODPECKER_PUBLIC_URL=http://ci-host.test:8000\n"
        "WOODPECKER_URL=http://localhost:8000\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mq, "_deployment_config_files", lambda prov: (str(config),))

    def no_network(url: str, token: str, timeout: float = 10.0) -> tuple[int, Any]:
        raise AssertionError(f"a test reached the Woodpecker API: {url}")

    monkeypatch.setattr(mq, "_woodpecker_read", no_network)


@pytest.fixture
def woodpecker(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A stand-in for the Woodpecker API, and the record of what it was asked.

    `answer` is what the API answers for a build read; `lookup` is what it
    answers for the repository lookup, which is a different question and is
    answered differently. `calls` is the list of URLs the gate read and `tokens`
    the list of tokens it read them with.
    """
    calls: list[str] = []
    tokens: list[str] = []
    answer: dict[str, Any] = {"status": 200, "payload": _pipeline()}
    lookup: dict[str, Any] = {"status": 200, "payload": {"id": 6}}

    def fake_read(url: str, token: str, timeout: float = 10.0) -> tuple[int, Any]:
        calls.append(url)
        tokens.append(token)
        if "/api/repos/lookup/" in url:
            return int(lookup["status"]), lookup["payload"]
        return int(answer["status"]), answer["payload"]

    monkeypatch.setattr(mq, "_woodpecker_read", fake_read)
    monkeypatch.setenv("WOODPECKER_TOKEN", "test-token")
    return {
        "calls": calls,
        "tokens": tokens,
        "answer": answer,
        "lookup": lookup,
    }


def _pipeline(
    *,
    status: str = "success",
    commit: str = "a" * 40,
    steps: dict[str, str] | None = None,
) -> dict[str, Any]:
    """A Woodpecker pipeline, in the shape the API returns it."""
    step_states = steps if steps is not None else {"digithings-check": "success"}
    return {
        "status": status,
        "commit": commit,
        "workflows": [
            {
                "name": "ci",
                "state": status,
                "children": [
                    {"name": name, "state": state} for name, state in step_states.items()
                ],
            }
        ],
    }


def _policy(repo: str = DIGITHINGS_REPO) -> Any:
    """The shipped policy, resolved for one repository."""
    return mq.load_policy().for_repo(repo)


def _approved() -> list[dict[str, Any]]:
    """A review, so the review gate is not the reason a PR was refused."""
    return [{"author": {"login": "someone"}, "state": "APPROVED"}]


def _evaluate(pr: dict[str, Any], repo: str = DIGITHINGS_REPO) -> Any:
    return mq.evaluate(pr, _policy(repo), acting_role="cto", base="develop", repo=repo)


def test_a_local_ci_status_that_names_no_build_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A green word with no build behind it is the hole this gate closes.

    This is the shape every status has today: the worker posts the state and
    names nothing, so nothing can be read back.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url="", reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("no verified Woodpecker provenance" in reason for reason in verdict.reasons)
    assert any("carries no target_url" in reason for reason in verdict.reasons)


def test_a_build_url_on_another_host_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A status may name any URL it likes, so the host is checked."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url="https://ci.example.com/repos/6/pipeline/259", reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("is not a Woodpecker host" in reason for reason in verdict.reasons)
    assert woodpecker["calls"] == [], "the build must not be read from a host that is not ours"


def test_a_url_that_is_not_a_pipeline_link_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A link to something else on the same host names no build."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url="http://localhost:8000/settings", reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("does not name a Woodpecker pipeline" in reason for reason in verdict.reasons)


def test_a_url_that_names_another_woodpecker_repository_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build of another repository says nothing about this one."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url="http://localhost:8000/repos/9/pipeline/259", reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("names the Woodpecker repository '9'" in reason for reason in verdict.reasons)


def test_a_build_that_is_not_there_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build that cannot be read is a missing build, not a passing one."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["status"] = 404
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("does not exist" in reason for reason in verdict.reasons)


def test_a_build_that_could_not_be_read_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A transport failure is its own answer, and it is not a pass."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["status"] = 0
    woodpecker["answer"]["payload"] = "connection refused"
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("could not be read" in reason for reason in verdict.reasons)


def test_a_build_that_is_still_running_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build that has not finished says nothing final yet.

    A step can be green while the rest of the build is still going, so the
    build's own state decides whether the run is over.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(status="running")
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("has not finished" in reason for reason in verdict.reasons)


def test_another_repositorys_failed_check_does_not_speak_for_this_one(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The launcher runs both repositories' checks in one pipeline.

    So the build's own status is not decisive: the twelve-x check can fail
    while the digithings check passes, and refusing a digithings pull request
    for a twelve-x failure would be a wrong refusal. The step that answers
    for the repository is the one that decides.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(
        status="failure", steps={"digithings-check": "success", "twelve-x-check": "failure"}
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons


def test_a_build_that_ran_another_commit_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build of another commit is a build of other code.

    This is the check that makes the gate a provenance check rather than a
    second green light: a writer who can post a status can also point it at a
    real, successful build - of the wrong commit.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("ran another commit" in reason for reason in verdict.reasons)


def test_a_build_that_did_not_run_this_repositorys_check_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The launcher runs both repositories' checks side by side.

    A build that only ran the other repository's check says nothing about this
    one, so the step is what binds a build to a repository.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(steps={"twelve-x-check": "success"})
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("has no 'digithings-check' step" in reason for reason in verdict.reasons)
    assert not any("is failure" in reason for reason in verdict.reasons)


def test_a_check_step_that_did_not_succeed_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build can be green overall and still have failed this repository's check."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(
        status="success", steps={"digithings-check": "failure"}
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("'digithings-check' step of the build named by the status is failure" in reason for reason in verdict.reasons)


def test_a_verified_build_is_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The good case: the status names a build, and the build checks this commit."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    assert woodpecker["calls"] == [
        "http://localhost:8000/api/repos/lookup/digithings-local/ci",
        "http://localhost:8000/api/repos/6/pipelines/259",
    ], "the build must be read from the API form of the URL the status named"


def test_the_newest_local_ci_status_is_the_one_that_is_read(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A status posted twice is answered for by the newest row.

    The older row may be a good one and the newer one a bad one, and reading the
    older row would merge on a build that has since been superseded.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="",
        local_ci_started_at="2026-10-21T02:06:27Z",
        reviews=_approved(),
        extra_checks=[
            {
                "__typename": "StatusContext",
                "context": "local-ci",
                "state": "SUCCESS",
                "startedAt": "2026-10-21T04:11:00Z",
                "targetUrl": GOOD_TARGET_URL,
            }
        ],
    )
    assert _evaluate(pr).eligible, "the newest status names a verified build"


def test_a_newer_status_without_a_build_overrides_an_older_one(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The other way round: the newest row is the answer, good or bad."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url=GOOD_TARGET_URL,
        local_ci_started_at="2026-10-21T02:06:27Z",
        reviews=_approved(),
        extra_checks=[
            {
                "__typename": "StatusContext",
                "context": "local-ci",
                "state": "SUCCESS",
                "startedAt": "2026-10-21T04:11:00Z",
                "targetUrl": "",
            }
        ],
    )
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("carries no target_url" in reason for reason in verdict.reasons)


def test_shadow_mode_records_what_it_would_have_refused_and_merges_anyway(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """Shadow mode is the window: the log is the evidence, the merge goes on.

    The launcher pipeline that runs the check is bound to the launcher's own
    commit, so a strict commit comparison refuses every pull request. Shadow
    says so, every tick, in a file of its own, and merges as before.
    """
    log = tmp_path / "ci-provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    pr = _pr(1, local_ci_target_url="", reviews=_approved())
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    written = log.read_text(encoding="utf-8")
    assert "would refuse" in written
    assert "carries no target_url" in written
    assert "PR #1" in written


def test_the_gate_is_off_when_the_mode_is_off(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """`off` is today's behaviour, and it reads nothing."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_OFF)
    pr = _pr(1, local_ci_target_url="", reviews=_approved())
    assert _evaluate(pr).eligible
    assert woodpecker["calls"] == []


def test_an_unknown_mode_is_treated_as_enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """A misspelled switch must not silence the gate.

    `off` has to be spelled correctly to switch it off; anything else fails
    closed, because the switch decides whether the queue trusts a status.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, "shadoww")
    assert mq.provenance_mode(mq.load_policy()) == mq.PROVENANCE_ENFORCE


def test_a_build_cannot_be_read_without_a_token(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """No token, no build: the queue says so rather than trusting the status."""
    import dataclasses

    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.delenv("WOODPECKER_TOKEN", raising=False)
    policy = mq.load_policy()
    policy = dataclasses.replace(
        policy,
        ci_provenance=dataclasses.replace(policy.ci_provenance, token_file=str(tmp_path / "none")),
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr, policy.for_repo(DIGITHINGS_REPO), acting_role="cto", base="develop", repo=DIGITHINGS_REPO
    )
    assert not verdict.eligible, verdict.reasons
    assert any("no Woodpecker token is available" in reason for reason in verdict.reasons)


def test_the_shipped_policy_runs_the_gate_in_shadow() -> None:
    """The shipping state, pinned.

    Shadow is the honest state: the build that runs the check today is bound to
    the launcher's own commit, so `enforce` would refuse every pull request.
    DIG-4809 owns the 48 hour window and the switch.
    """
    policy = mq.load_policy()
    assert policy.ci_provenance.mode == mq.PROVENANCE_SHADOW
    assert policy.ci_provenance.context == "local-ci"
    assert policy.ci_provenance.woodpecker_repos == {
        DIGITHINGS_REPO: "6",
        TWELVE_X_REPO: "6",
    }
    assert policy.ci_provenance.steps == {
        DIGITHINGS_REPO: "digithings-check",
        TWELVE_X_REPO: "twelve-x-check",
    }
    assert policy.ci_provenance.hosts, "a host allow-list is what makes the URL check mean something"


def test_the_twelve_x_check_is_looked_for_in_its_own_step(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """Each repository is bound to its own step, not to a shared one."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(steps={"digithings-check": "success"})
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr, repo=TWELVE_X_REPO)
    assert not verdict.eligible, verdict.reasons
    assert any("has no 'twelve-x-check' step" in reason for reason in verdict.reasons)


def test_the_newest_status_is_read_whatever_the_order_of_the_rows(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The newest row is the one that answers, not the first one in the list.

    The rollup does not promise an order, so a reader that took the first
    `local-ci` row it found would honour a superseded status - and a superseded
    green is exactly what a writer who wants a merge would leave behind.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url=GOOD_TARGET_URL,
        local_ci_started_at="2026-10-21T04:11:00Z",
        reviews=_approved(),
        extra_checks=[
            {
                "__typename": "StatusContext",
                "context": "local-ci",
                "state": "SUCCESS",
                "startedAt": "2026-10-21T02:06:27Z",
                "targetUrl": "",
            }
        ],
    )
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons


def test_a_status_timestamped_with_created_at_is_read(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """GitHub sends `createdAt` for a commit status in some API versions.

    The gate reads both spellings, so a status row that carries only
    `createdAt` is still ordered against the others.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url=GOOD_TARGET_URL,
        local_ci_created_at="2026-10-21T04:11:00Z",
        reviews=_approved(),
        extra_checks=[
            {
                "__typename": "StatusContext",
                "context": "local-ci",
                "state": "SUCCESS",
                "createdAt": "2026-10-21T02:06:27Z",
                "targetUrl": "",
            }
        ],
    )
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons


def test_a_server_error_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A 5xx from the Woodpecker API is a failure to read, not a build."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["status"] = 500
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("HTTP 500" in reason for reason in verdict.reasons)


def test_a_body_that_is_not_a_build_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A 200 whose body is not a build is not a build."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = ["not", "a", "build"]
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("not a build" in reason for reason in verdict.reasons)


def test_a_build_that_ran_a_commit_with_the_same_prefix_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The commit is compared in full.

    A comparison that stopped at the twelve characters the message prints would
    accept a build of a different commit that happens to share a prefix.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="a" * 12 + "b" * 28)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("ran another commit" in reason for reason in verdict.reasons)


def test_a_build_that_reports_no_commit_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A build that says nothing about which commit it ran cannot be matched.

    The commit comparison is the check that makes this a provenance check, so
    it fails closed: a payload without a commit is a refusal, not a pass.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    payload = _pipeline()
    payload.pop("commit")
    woodpecker["answer"]["payload"] = payload
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("reports no commit" in reason for reason in verdict.reasons)


def test_a_build_with_no_status_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A payload without a status has not finished: it says nothing yet."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    payload = _pipeline()
    payload.pop("status")
    woodpecker["answer"]["payload"] = payload
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("has not finished" in reason for reason in verdict.reasons)


def test_the_token_is_sent_to_the_woodpecker_api(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The read is authenticated, and the token is the one the policy names."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    assert woodpecker["tokens"] and set(woodpecker["tokens"]) == {"test-token"}


def test_the_token_is_read_from_the_file_the_policy_names(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The launchd queue carries no token in its environment, so the file is the source.

    Only the named key is read, so a file that holds other secrets is safe to
    point at.
    """
    import dataclasses

    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.delenv("WOODPECKER_TOKEN", raising=False)
    token_file = tmp_path / "forge.env"
    token_file.write_text(
        "# the deployment\nOTHER_SECRET=not-the-token\nWOODPECKER_TOKEN='file-token'\n",
        encoding="utf-8",
    )
    policy = mq.load_policy()
    policy = dataclasses.replace(
        policy,
        ci_provenance=dataclasses.replace(policy.ci_provenance, token_file=str(token_file)),
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr,
        policy.for_repo(DIGITHINGS_REPO),
        acting_role="cto",
        base="develop",
        repo=DIGITHINGS_REPO,
    )
    assert verdict.eligible, verdict.reasons
    assert woodpecker["tokens"] and set(woodpecker["tokens"]) == {"file-token"}


def test_a_url_that_names_the_repository_by_name_is_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """Woodpecker's web links name the repository as `owner/name`."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="http://localhost:8000/repo/digithings-local/ci/pipelines/259",
        reviews=_approved(),
    )
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons


def test_a_url_that_names_another_repository_by_name_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """Naming the repository is not enough: it has to be our repository."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="http://localhost:8000/repo/somebody-else/their-repo/pipelines/259",
        reviews=_approved(),
    )
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("names the Woodpecker repository" in reason for reason in verdict.reasons)
    assert woodpecker["calls"] == []


def test_the_shipped_policy_does_not_write_the_deployment_address_down() -> None:
    """No address that moves is written in the policy file.

    The deployment's address is a DHCP address. A list that carries it goes
    stale, and under `enforce` a stale list refuses every pull request,
    because every build link then names a host that is not ours.
    """
    prov = mq.load_policy().ci_provenance
    assert prov.hosts == ("localhost:8000", "127.0.0.1:8000")
    assert prov.host_files, "the policy must name the files the addresses come from"
    assert prov.host_url_keys, "the policy must name the keys the addresses come from"
    assert prov.require_config, (
        "the switch to enforce must be gated on the configuration being readable"
    )


def test_the_allowed_hosts_are_read_from_the_deployment_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deployment's address is read, not written down.

    A change of local IP is then a change of the deployment and not a change of
    this repository, which is the whole point: a list that has to be edited
    when the machine moves is a list that is out of date the day after the
    edit is forgotten.
    """
    import dataclasses

    monkeypatch.setattr(mq, "_deployment_config_files", _REAL_DEPLOYMENT_CONFIG_FILES)
    config = tmp_path / "local-forge.env"
    config.write_text(
        "WOODPECKER_PUBLIC_URL=http://192.168.1.35:8000\n", encoding="utf-8"
    )
    policy = mq.load_policy()
    prov = dataclasses.replace(
        policy.ci_provenance,
        host_files=(str(config),),
        host_url_keys=("WOODPECKER_PUBLIC_URL",),
    )
    hosts, problem = mq._allowed_hosts(prov)
    assert problem == ""
    assert "192.168.1.35:8000" in hosts
    assert "localhost:8000" in hosts


def test_a_deployment_configuration_that_cannot_be_read_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The switch to enforce is gated on the deployment being where it was.

    A list of allowed hosts that was written down before the deployment moved
    refuses every pull request once the deployment has moved, and the refusal
    says nothing about the cause. So the gate refuses when it cannot read the
    configuration, and it says that it could not read it.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setattr(
        mq, "_deployment_config_files", lambda prov: (str(tmp_path / "absent.env"),)
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "deployment configuration could not be read" in reason for reason in verdict.reasons
    )


def test_the_woodpecker_repository_id_is_resolved_from_its_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repository that was recreated carries a new id.

    The number written in the policy is the fallback for an API that cannot be
    read; the name is the authority, so a build link that names the repository
    that is really there is evidence even when the number in the policy is
    stale. A number that is written down and never checked is how the gate
    ends up reading a different repository's build.
    """
    calls: list[str] = []

    def fake_read(url: str, token: str, timeout: float = 10.0) -> tuple[int, Any]:
        calls.append(url)
        if "/api/repos/lookup/" in url:
            return 200, {"id": 42}
        return 200, _pipeline(commit="a" * 40)

    monkeypatch.setattr(mq, "_woodpecker_read", fake_read)
    monkeypatch.setenv("WOODPECKER_TOKEN", "test-token")
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="http://localhost:8000/repos/42/pipeline/259",
        reviews=_approved(),
    )
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    assert "http://localhost:8000/api/repos/lookup/digithings-local/ci" in calls
    assert "http://localhost:8000/api/repos/42/pipelines/259" in calls


def test_a_target_url_that_is_not_absolute_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A protocol-relative URL names no host, so it names no build."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="//localhost:8000/repos/6/pipeline/259",
        reviews=_approved(),
    )
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("not an absolute URL" in reason for reason in verdict.reasons)
    assert woodpecker["calls"] == []


def test_a_crafted_target_url_cannot_kill_the_tick(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A status is written by whoever posted it, so its URL is untrusted input.

    A number that is not an ASCII digit, a scheme that is not http, and a path
    that is not a pipeline are all refusals - never an exception, because one
    exception in the gate stops the queue for everybody.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    for target in (
        "http://localhost:8000/repos/6/pipeline/\u0663",
        "http://localhost:8000/repos/6/pipeline/259/3",
        "file://localhost:8000/repos/6/pipeline/259",
        "http://localhost:8000/repos/6/pipeline/abc",
    ):
        pr = _pr(1, local_ci_target_url=target, reviews=_approved())
        verdict = _evaluate(pr)
        assert not verdict.eligible, f"{target} was accepted: {verdict.reasons}"
    assert woodpecker["calls"] == []


def test_the_mode_switch_tolerates_case_and_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The switch is read from a shell, where a stray space is easy."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, " Off ")
    assert mq.provenance_mode(mq.load_policy()) == mq.PROVENANCE_OFF


def test_shadow_mode_reads_the_build_and_still_merges(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """Shadow measures: it reads the build, says what it would refuse, and merges.

    This is the mode the 48 hour window runs in, so it has to reach the API:
    a window that never reads a build measures nothing.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    assert woodpecker["calls"] == [
        "http://localhost:8000/api/repos/lookup/digithings-local/ci",
        "http://localhost:8000/api/repos/6/pipelines/259",
    ]
    written = log.read_text(encoding="utf-8")
    assert "would refuse 'local-ci'" in written
    assert "ran another commit" in written


def test_the_provenance_log_is_written_for_its_owner_only(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The log holds a URL that a status writer chose, so it is not world readable."""
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    assert log.exists()
    assert oct(log.stat().st_mode)[-3:] == "600"


def test_the_provenance_log_is_capped(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The log grows by a line per pull request per tick, so it is capped."""
    log = tmp_path / "provenance.log"
    log.write_text("x" * (mq.PROVENANCE_LOG_MAX_BYTES + 10), encoding="utf-8")
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    assert log.stat().st_size < mq.PROVENANCE_LOG_MAX_BYTES
    assert (tmp_path / "provenance.log.1").exists()


def test_the_suite_never_writes_to_the_deployment_provenance_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deployment's log is written by the queue, not by this suite.

    The file under `~/.config/digithings/merge-queue/` is the operator's record
    of what the queue refused, and the queue reads it during the shadow window.
    Fixture text in that file reads as a real refusal, so the suite writes its
    lines under `tmp_path`: the autouse fixture pins the log path there for
    every test, and the pinned path wins over the module's default.
    """
    deployment_log = tmp_path / "deployment" / "ci-provenance.log"
    monkeypatch.setattr(mq, "PROVENANCE_LOG_PATH", deployment_log)
    mq._log_provenance(
        {"number": 1},
        DIGITHINGS_REPO,
        "local-ci",
        "no target_url",
        "",
        mq.PROVENANCE_SHADOW,
    )
    assert not deployment_log.exists()
    assert (tmp_path / "ci-provenance.log").exists()


def test_the_provenance_log_holds_one_line_per_refusal(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The queue reads every open pull request on every tick.

    A line written again on every tick is how a 48 hour window turns into tens
    of thousands of lines nobody reads, so a refusal that repeats is counted
    instead of written again.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    _evaluate(pr)
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1, lines
    # The counts are written out at the end of a tick, which is when the queue
    # knows that the tick is over.
    mq._flush_provenance_index()
    index = json.loads(
        (tmp_path / "ci-provenance.index.json").read_text(encoding="utf-8")
    )
    assert [entry["count"] for entry in index["entries"].values()] == [2], index


def test_a_refusal_is_written_again_when_the_log_no_longer_holds_it(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The index is a memory of the log, not a log of its own.

    A log that was rotated away or emptied does not hold the refusal the index
    remembers, so the refusal is written again: the window is the file, and the
    file has to say it.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    log.write_text("", encoding="utf-8")
    _evaluate(pr)
    lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    assert len(lines) == 1, lines


def test_the_provenance_index_is_written_for_its_owner_only(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The index says which pull requests the queue refused, so it is private."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    index = tmp_path / "ci-provenance.index.json"
    assert index.exists()
    assert oct(index.stat().st_mode)[-3:] == "600"


def test_the_suite_never_writes_to_the_deployment_provenance_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The deployment's index is written by the queue, not by this suite.

    The index beside the operator's log is the queue's own record of what it
    refused. Fixture text in it reads as a real refusal, and a count in it
    silences the real log, so the suite writes its own index under `tmp_path`.
    """
    deployment_index = tmp_path / "deployment" / "ci-provenance.index.json"
    monkeypatch.setattr(mq, "PROVENANCE_INDEX_PATH", deployment_index)
    mq._log_provenance(
        {"number": 1},
        DIGITHINGS_REPO,
        "local-ci",
        "no target_url",
        "",
        mq.PROVENANCE_SHADOW,
    )
    assert not deployment_index.exists()
    assert (tmp_path / "ci-provenance.index.json").exists()


def test_a_url_that_names_the_repository_by_name_reads_the_build_behind_that_name(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The name shape has to reach the build of the repository it names.

    A link that names the repository as `owner/name` still has to be read from
    the API under a numeric id. Resolving the name to an id is the only way to
    ask for that build, and a name that is never resolved asks for no build at
    all: the gate then reads a URL with no repository in it and refuses a build
    that exists. So the read is asserted here, not just the verdict.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(
        1,
        local_ci_target_url="http://localhost:8000/repo/digithings-local/ci/pipelines/259",
        reviews=_approved(),
    )
    verdict = _evaluate(pr)
    assert verdict.eligible, verdict.reasons
    assert woodpecker["calls"] == [
        "http://localhost:8000/api/repos/lookup/digithings-local/ci",
        "http://localhost:8000/api/repos/6/pipelines/259",
    ]


def test_a_repository_that_cannot_be_resolved_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """A number that cannot be confirmed names a repository we do not know.

    The name is the authority, and it is resolved against the API on every
    check. When the lookup cannot be answered, the number written in the
    policy is not used instead: a repository that was recreated carries a new
    id, and the old id then points at a different repository, whose build says
    nothing about this pull request. The lookup adds no new way for the tick
    to fail - the build itself is read from the same API.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["lookup"]["status"] = 500
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("could not be resolved" in reason for reason in verdict.reasons)
    assert not any("/pipelines/" in call for call in woodpecker["calls"]), (
        "no build may be read through a number that could not be confirmed"
    )


def test_a_configuration_file_that_is_not_utf8_is_a_refusal_not_a_crash(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """One byte that is not UTF-8 must not stop the queue for everybody.

    The gate reads the deployment's own files. A file that holds a byte the
    gate cannot decode is a file it cannot read, and a file it cannot read is
    a refusal that says so - not an exception that ends the tick.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    config = tmp_path / "local-forge.env"
    config.write_bytes(b"WOODPECKER_PUBLIC_URL=http://ci-host.test:8000\nNAME=caf\xe9\n")
    monkeypatch.setattr(mq, "_deployment_config_files", lambda prov: (str(config),))
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "deployment configuration could not be read" in reason for reason in verdict.reasons
    )


def test_a_configuration_line_may_carry_an_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`export KEY=value` is the same line in another dialect.

    A file that writes it that way says the value under a name the key does
    not match, so the address is not found and the gate refuses every pull
    request for a reason that has nothing to do with the pull request.
    """
    import dataclasses

    config = tmp_path / "local-forge.env"
    config.write_text(
        "export WOODPECKER_PUBLIC_URL=http://192.168.1.35:8000\n", encoding="utf-8"
    )
    policy = mq.load_policy()
    prov = dataclasses.replace(
        policy.ci_provenance,
        host_files=(str(config),),
        host_url_keys=("WOODPECKER_PUBLIC_URL",),
    )
    hosts, problem = mq._allowed_hosts(prov)
    assert problem == ""
    assert "192.168.1.35:8000" in hosts


def test_the_credentials_of_a_target_url_are_not_written_to_the_log(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The status writer chose the URL, so it may carry credentials.

    The gate compares the host, and the host is all that anybody reading the
    log needs. The log outlives the tick and the launchd error log is kept,
    so a password written into it stays there.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(
        1,
        head_sha="a" * 40,
        local_ci_target_url="http://user:pass@localhost:8000/repos/6/pipeline/259",
        reviews=_approved(),
    )
    _evaluate(pr)
    written = log.read_text(encoding="utf-8")
    assert "pass" not in written, written
    assert "user" not in written, written


def test_the_mode_is_part_of_what_the_log_remembers(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """A refusal in shadow mode and the same refusal in enforce mode are two lines.

    The switch to enforce is exactly the moment the log has to start carrying
    the new refusals, and the window that reads them is the log.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    _evaluate(pr)
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    _evaluate(pr)
    written = log.read_text(encoding="utf-8")
    assert "would refuse" in written
    assert "refuses" in written


def test_a_count_that_is_not_a_number_does_not_stop_the_tick(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """The index is a convenience, and a corrupted one must not stop the queue.

    The index is written atomically, so a broken count is a hand-edited file
    or a file from another version. The tick has to end anyway: the queue that
    dies on a bad count stops merging for everybody.
    """
    log = tmp_path / "provenance.log"
    index = tmp_path / "ci-provenance.index.json"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    mq._flush_provenance_index()
    entries = json.loads(index.read_text(encoding="utf-8"))["entries"]
    key = next(iter(entries))
    entries[key]["count"] = "many"
    index.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    mq._INDEX_CACHE.clear()
    _evaluate(pr)
    assert log.exists()


def test_the_index_does_not_remember_a_line_the_log_never_took(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """A log that cannot be written is not a log that holds the refusal.

    The index says what the log holds. If the log could not be written, the
    index must not say it holds the line, because the operator reads the log
    and not the index.
    """
    log = tmp_path / "provenance.log"
    log.mkdir()  # a path that cannot be opened for writing
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    index = tmp_path / "ci-provenance.index.json"
    assert not index.exists() or json.loads(index.read_text())["entries"] == {}


def test_a_refusal_is_written_again_when_the_log_holds_other_lines(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any], tmp_path: Path
) -> None:
    """A log that holds other lines no longer holds this refusal.

    The index said the refusal was written, and the log was edited since. The
    claim is checked against the log, not against the index.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_SHADOW)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    _evaluate(pr)
    log.write_text("2026-10-21T00:00:00+00:00 something else\n", encoding="utf-8")
    _evaluate(pr)
    written = log.read_text(encoding="utf-8")
    assert "would refuse" in written


def test_a_redirect_is_refused_and_the_token_stays_home() -> None:
    """A redirect would hand the Woodpecker token to another host.

    `urllib` copies the `Authorization` header to a redirect target, so the
    read refuses redirects rather than following one.
    """
    import http.server
    import threading

    seen: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # the name the base class uses
            seen.append(self.headers.get("Authorization") or "")
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:1/elsewhere")
            self.end_headers()

        def log_message(self, *args: Any) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/api/repos/6/pipelines/259"
        status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    finally:
        server.shutdown()
        server.server_close()
    assert status == 0, payload
    assert seen == ["Bearer the-token"], "the token reached the server that answered"


class _FakeWoodpeckerResponse:
    """The answer of the Woodpecker API, as the read sees it."""

    def __init__(self, status: int, body: str, url: str) -> None:
        self.status = status
        self._body = body.encode("utf-8")
        self._url = url

    def read(self, size: int | None = None) -> bytes:
        """The body, in chunks of `size` when one is asked for.

        The read of the production code asks for a chunk at a time, because
        the timeout of a socket is the timeout of one operation on it and a
        body that trickles in has to be given up on.
        """
        if size is None:
            return self._body
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "_FakeWoodpeckerResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


class _FakeOpenerExhausted(BaseException):
    """The fake had no answer left for a call the read made.

    A `BaseException` on purpose: the read catches `Exception`, so an
    `AssertionError` here would be folded into the reason string and the test
    would carry on with a confusing payload instead of failing.
    """


class _FakeOpener:
    """The opener the read uses, with the answers it was told to give.

    `answers` is the list of answers, one per call: an answer that is an
    exception is raised instead of returned, and the list running out is a
    failure of the test, not of the read.

    The calls are recorded with the timeout they were given and the headers
    they carried, because a read that is clamped by a budget and a read that
    keeps its token are both claims about the call, not about the answer.
    """

    def __init__(self, answers: list[Any]) -> None:
        self.answers = list(answers)
        self.calls: list[str] = []
        self.timeouts: list[float | None] = []
        self.headers: list[dict[str, str]] = []

    def open(self, request: Any, timeout: float | None = None) -> Any:
        self.calls.append(request.full_url)
        self.timeouts.append(timeout)
        self.headers.append(dict(getattr(request, "headers", {}) or {}))
        if not self.answers:
            raise _FakeOpenerExhausted(f"the read asked again: {request.full_url}")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class _FakeClock:
    """`time` with a sleep that counts instead of waiting.

    The clock only moves when something moves it: a sleep, or a body that
    arrives. The read's budget is measured against it.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _TriclingResponse:
    """A body that arrives a byte at a time, slowly.

    The server answers the headers and then trickles the body: the timeout of
    a socket is the timeout of one operation on it, so a read that is not
    given up on can be held open for as long as the server likes.
    """

    def __init__(self, clock: _FakeClock, url: str) -> None:
        self.status = 200
        self._clock = clock
        self._url = url
        self._sent = 0

    def read(self, size: int | None = None) -> bytes:
        self._clock.now += 0.02
        self._sent += 1
        if self._sent > 50:
            return b""
        return b"x"

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> "_TriclingResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _authorization(headers: dict[str, str]) -> str | None:
    """The token a request carried, whatever case the header was stored in."""
    for key, value in headers.items():
        if key.lower() == "authorization":
            return value
    return None


def test_a_dropped_connection_is_read_again_and_the_build_is_still_the_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dropped connection says nothing about the build behind the URL.

    The read is tried again before it is believed, so a connection that drops
    once - a busy host, a laptop that woke up - does not refuse a pull request
    on a fact about the network.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener(
        [
            TimeoutError("timed out"),
            TimeoutError("timed out"),
            _FakeWoodpeckerResponse(200, json.dumps(_pipeline(commit="a" * 40)), url),
        ]
    )
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert status == 200, payload
    assert isinstance(payload, dict) and payload.get("commit") == "a" * 40
    assert len(opener.calls) == mq.PROVENANCE_READ_ATTEMPTS
    assert opener.calls == [url] * mq.PROVENANCE_READ_ATTEMPTS, (
        "the retry asked another URL than the one that was dropped"
    )
    assert all(_authorization(h) == "Bearer the-token" for h in opener.headers), (
        "a retry went out without the token"
    )


def test_a_host_that_did_not_answer_is_asked_once_more_and_not_three_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead host is asked once per pull request, and not three times.

    The queue asks the same host about every pull request of the tick, so a
    host that did not answer is asked once more - briefly - and the answer it
    gave is repeated with it. One dropped connection used to refuse every pull
    request of the tick for a reason that had nothing to do with them, and a
    host that is down used to cost the tick three reads per pull request.
    The memory is of that host and not of the queue, so a host that did answer
    is still asked.
    """
    other_host = "http://ci-host.test:8000/api/repos/6/pipelines/260"
    opener = _FakeOpener([TimeoutError("timed out")] * 12)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    first = _REAL_WOODPECKER_READ(
        "http://localhost:8000/api/repos/lookup/digithings-local/ci",
        "the-token",
        timeout=5,
    )
    assert first[0] == 0, first
    assert "timed out" in str(first[1])
    assert f"tried {mq.PROVENANCE_READ_ATTEMPTS} times" in str(first[1])
    asked = len(opener.calls)
    assert asked == mq.PROVENANCE_READ_ATTEMPTS
    second = _REAL_WOODPECKER_READ(
        "http://localhost:8000/api/repos/6/pipelines/259", "the-token", timeout=5
    )
    assert second[0] == 0, second
    assert "timed out" in str(second[1])
    assert "asked once more" in str(second[1])
    assert len(opener.calls) == asked + 1, "the host that did not answer was asked again"
    # Another host is another host: it is read with the whole budget and not
    # with the one short ask that follows a failure somewhere else.
    third = _REAL_WOODPECKER_READ(other_host, "the-token", timeout=5)
    assert third[0] == 0, third
    assert len(opener.calls) == asked + 1 + mq.PROVENANCE_READ_ATTEMPTS, (
        "the memory of one host's failure was used against another host"
    )


def test_a_failed_read_is_not_the_answer_for_that_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed read is not the answer for that URL.

    The URL is asked again - once more, briefly - instead of being answered
    from the memory of the failure. And the memory has a life of its own: once
    it has run out the URL is read with the whole budget again, and not with
    the one short ask that follows a failure.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener([TimeoutError("timed out")] * 12)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    first = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert first[0] == 0, first
    assert len(opener.calls) == mq.PROVENANCE_READ_ATTEMPTS
    second = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert second[0] == 0, second
    assert len(opener.calls) == mq.PROVENANCE_READ_ATTEMPTS + 1, (
        "the URL was answered from the memory of the failure instead of being asked"
    )
    # The memory has run out: the URL is read with the whole budget again.
    monkeypatch.setattr(mq, "PROVENANCE_HOST_COOLDOWN", 0.0)
    third = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert third[0] == 0, third
    assert len(opener.calls) == 2 * mq.PROVENANCE_READ_ATTEMPTS + 1, (
        "the expired memory did not give the read back to the whole budget"
    )


def test_a_host_that_comes_back_answers_the_one_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that was asleep for a moment answers the ask that follows.

    The memory of a failure is not the answer for the rest of the tick: the
    host is asked once more, and a host that answers is read against its build
    and not against the memory of a failure that is no longer true.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener(
        [
            TimeoutError("timed out"),
            TimeoutError("timed out"),
            TimeoutError("timed out"),
            _FakeWoodpeckerResponse(200, json.dumps(_pipeline(commit="a" * 40)), url),
        ]
    )
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    first = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert first[0] == 0, first
    second = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert second[0] == 200, second
    assert len(opener.calls) == mq.PROVENANCE_READ_ATTEMPTS + 1, (
        "the host that came back was not asked"
    )


def test_the_memory_of_a_failure_is_of_the_service_and_not_of_the_spelling() -> None:
    """Two spellings of one address are one host for the queue.

    The key is the scheme and the host in lower case with its port, so a
    status that spells the same address two ways does not pay two retry
    storms, and two services on one machine stay two hosts.
    """
    assert mq._read_host("http://LocalHost:8000/api/repos/6/pipelines/1") == (
        "http://localhost:8000"
    )
    assert mq._read_host("http://localhost:8000/api") == mq._read_host(
        "http://LOCALHOST:8000/api"
    )
    assert mq._read_host("http://localhost:8000/api") != mq._read_host(
        "http://localhost:9000/api"
    )
    assert mq._read_host("http://localhost:8000/api") != mq._read_host(
        "https://localhost:8000/api"
    )


def test_a_body_that_trickles_in_does_not_hold_the_read_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The budget is a deadline, and not a sum of timeouts.

    The timeout of a socket is the timeout of one operation on it: a server
    that answers the headers and then trickles the body keeps the read open
    for as long as it likes, unless the read gives up when the deadline has
    passed.
    """
    clock = _FakeClock()
    monkeypatch.setattr(mq, "time", clock)
    monkeypatch.setattr(mq, "PROVENANCE_READ_BUDGET", 0.05)
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener([_TriclingResponse(clock, url)])
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert status == 0, payload
    assert "the read exceeded its budget" in str(payload), payload


@pytest.mark.parametrize("code", [404, 503])
def test_a_status_code_is_an_answer_and_is_not_read_again(
    monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    """A server that answered 404 answered, and one that answered 503 answered.

    The answer is cached for the tick and the read is not tried again: only a
    connection that never arrived says nothing about the build. Any status
    code is an answer, not only the ones that read well.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener(
        [urllib.error.HTTPError(url, code, "no such build", {}, None)]
    )
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    first = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert first == (code, None), first
    second = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert second == (code, None), second
    assert len(opener.calls) == 1, "the answer of the API was asked for again"


def test_a_refused_redirect_does_not_make_the_host_look_sick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect is refused by the gate, not lost by the network.

    The refusal is the same every time, so the read is not tried again, and
    the host is not remembered as a host that could not be read: it answered.
    """
    opener = _FakeOpener(
        [
            urllib.error.HTTPError(
                "http://localhost:8000/api/repos/6/pipelines/259", 302, "found", {}, None
            ),
            _FakeWoodpeckerResponse(
                200,
                json.dumps(_pipeline(commit="a" * 40)),
                "http://localhost:8000/api/repos/6/pipelines/260",
            ),
        ]
    )
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    first = _REAL_WOODPECKER_READ(
        "http://localhost:8000/api/repos/6/pipelines/259", "the-token", timeout=5
    )
    assert first == (0, "the request was redirected"), first
    assert len(opener.calls) == 1, "the redirect was followed after it was refused"
    second = _REAL_WOODPECKER_READ(
        "http://localhost:8000/api/repos/6/pipelines/260", "the-token", timeout=5
    )
    assert second[0] == 200, second
    assert len(opener.calls) == 2, "the host that answered was treated as a dead host"


def test_the_read_budget_bounds_the_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One read costs the budget once, not once per attempt.

    The attempt is given the time that is left of the budget, never the
    timeout it was asked with: a read that ignores the budget waits for every
    attempt the whole timeout, and a tick of them waits for hours.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener([TimeoutError("timed out")] * 12)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=100)
    assert status == 0, payload
    assert opener.timeouts, "the read was made with no timeout at all"
    assert max(opener.timeouts) <= mq.PROVENANCE_READ_BUDGET, opener.timeouts


def test_a_read_with_no_budget_left_is_not_attempted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A read with no budget left is not made.

    The budget is what stops the loop. Without it the attempts would go on
    until the attempts ran out, and the tick would keep a pull request waiting
    on a host that is not there.
    """
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener([TimeoutError("timed out")] * 12)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    monkeypatch.setattr(mq, "PROVENANCE_READ_BUDGET", 0.0)
    status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert status == 0, payload
    assert payload == "the read was not attempted", payload
    assert not opener.calls, "the read was made with no budget left"


def test_the_attempts_are_paused_between_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two attempts without a pause are a busy loop against a struggling host.

    The pause is what lets a host that was busy for a moment answer the next
    attempt, and what keeps a host that is down from being asked three times
    in the same breath.
    """
    clock = _FakeClock()
    monkeypatch.setattr(mq, "time", clock)
    url = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener([TimeoutError("timed out")] * 12)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    status, payload = _REAL_WOODPECKER_READ(url, "the-token", timeout=5)
    assert status == 0, payload
    assert len(clock.slept) == mq.PROVENANCE_READ_ATTEMPTS - 1, clock.slept
    assert all(0 < s <= mq.PROVENANCE_RETRY_BACKOFF for s in clock.slept), clock.slept


def test_a_dropped_connection_refuses_the_pull_request_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal names the read that failed, not a fault of the build.

    The gate reads the build through the same read as everything else, so a
    dropped connection is refused with the reason of a read that could not be
    made. A pull request is refused for what is wrong with it, and a network
    that dropped a connection is not a fault of the build.
    """
    lookup = "http://localhost:8000/api/repos/lookup/digithings-local/ci"
    build = "http://localhost:8000/api/repos/6/pipelines/259"
    opener = _FakeOpener(
        [
            _FakeWoodpeckerResponse(200, json.dumps({"id": 6}), lookup),
            *[TimeoutError("timed out")] * 30,
        ]
    )
    monkeypatch.setattr(mq, "_woodpecker_read", _REAL_WOODPECKER_READ)
    monkeypatch.setattr(mq, "_WOODPECKER_OPENER", opener)
    monkeypatch.setenv("WOODPECKER_TOKEN", "test-token")
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any("the Woodpecker API could not be read" in r for r in verdict.reasons), (
        verdict.reasons
    )
    assert not any("could not be resolved" in r for r in verdict.reasons), (
        "the refusal names the lookup of the repository and not the read of the build"
    )
    assert opener.calls == [lookup] + [build] * mq.PROVENANCE_READ_ATTEMPTS, opener.calls


def test_the_gate_verifies_the_check_it_was_asked_about(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The gate reads the status of the check it was invoked for.

    The exemption list is global by name, so a repository that required a
    different status context would otherwise be gated on whatever the policy's
    `context` says - a different status, from a different writer.
    """
    import dataclasses

    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    policy = mq.load_policy()
    policy = dataclasses.replace(
        policy,
        ci_provenance=dataclasses.replace(policy.ci_provenance, context="another-check"),
    )
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr,
        policy.for_repo(DIGITHINGS_REPO),
        acting_role="cto",
        base="develop",
        repo=DIGITHINGS_REPO,
    )
    assert verdict.eligible, verdict.reasons


# ── the trusted receipt: who wrote the status (DIG-4794, the second chain) ───
#
# The `local-ci` row is posted with a user token, so a seat that can run the
# check can post the same green row - and can copy the build link out of any
# recent build. The receipt is the same status posted by the CI's own GitHub
# App installation, so the writer is the CI and nobody else, and it sits on the
# head commit: that is what binds a check to a pull request head, which the
# build's own `commit` field cannot do while the launcher runs one build per
# repository.

#: The status context the CI's app writes its receipt under.
RECEIPT_CONTEXT = "local-ci/app"

#: The login the CI's GitHub App installation writes under.
RECEIPT_WRITER = "digithings-ci[bot]"


@pytest.fixture
def commit_statuses(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The commit statuses on the head, answered from a fixture.

    The GraphQL rollup the queue already reads carries no creator, so the
    receipt is read from the REST endpoint; this is that endpoint. `rows` is
    what it answers with, `problem` makes it fail, and `calls` is the record of
    what it was asked.
    """
    state: dict[str, Any] = {"rows": [], "problem": "", "calls": []}

    def fake_gh_json(*args: str, timeout: float | None = None) -> Any:
        state["calls"].append(" ".join(args))
        if len(args) >= 2 and args[0] == "api" and "/statuses" in args[1]:
            if state["problem"]:
                raise mq.QueueError(state["problem"])
            return list(state["rows"])
        return _REAL_GH_JSON(*args, timeout=timeout)

    monkeypatch.setattr(mq, "_gh_json", fake_gh_json)
    return state


def _receipt_row(
    *,
    state: str = "success",
    login: str = RECEIPT_WRITER,
    target_url: str = GOOD_TARGET_URL,
    created_at: str = "2026-10-21T02:07:00Z",
) -> dict[str, Any]:
    """A commit status row, in the shape the REST endpoint answers with."""
    return {
        "context": RECEIPT_CONTEXT,
        "state": state,
        "target_url": target_url,
        "created_at": created_at,
        "creator": {"login": login},
    }


def _receipt_policy(
    repo: str = DIGITHINGS_REPO,
    *,
    require: bool = True,
    creators: tuple[str, ...] = (RECEIPT_WRITER,),
    commit_match: str = mq.COMMIT_MATCH_ENFORCE,
) -> Any:
    """The shipped policy, with the receipt switched on.

    The shipped policy does not ask for a receipt yet: the CI writes none, so
    a policy that asked for one would refuse every pull request in the org.
    The chain is here, tested, and switched on by the policy change that comes
    with the CI's own installation token.
    """
    policy = mq.load_policy()
    prov = replace(
        policy.ci_provenance,
        trusted_receipt=mq.TrustedReceipt(
            context=RECEIPT_CONTEXT, creators=creators, required=require
        ),
        commit_match=commit_match,
    )
    return replace(policy, ci_provenance=prov).for_repo(repo)


def _receipt_verdict(pr: dict[str, Any], repo: str = DIGITHINGS_REPO) -> Any:
    return mq.evaluate(
        pr, _receipt_policy(repo), acting_role="cto", base="develop", repo=repo
    )


def test_a_receipt_written_by_the_ci_app_is_evidence(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The receipt is the row a seat cannot write, so it is evidence."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert verdict.eligible, verdict.reasons


def test_a_receipt_written_by_somebody_else_is_not_a_receipt(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The writer is the whole point of the receipt."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row(login="chrizefan")]
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "was written by chrizefan, which is not a trusted CI writer" in reason
        for reason in verdict.reasons
    )


def test_a_pull_request_without_a_receipt_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """No receipt is not a receipt."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = []
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        f"no '{RECEIPT_CONTEXT}' receipt is reported on the head commit" in reason
        for reason in verdict.reasons
    )


def test_a_receipt_that_is_not_green_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """A receipt that says the check failed is a failed check."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row(state="failure")]
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        f"the '{RECEIPT_CONTEXT}' receipt is failure" in reason
        for reason in verdict.reasons
    )


def test_a_receipt_that_names_no_build_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The receipt's own build is read back, like the status's."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row(target_url="")]
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        f"the '{RECEIPT_CONTEXT}' receipt carries no target_url" in reason
        for reason in verdict.reasons
    )


def test_a_receipt_whose_build_ran_another_commit_is_not_evidence(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The receipt names a build, and the build has to be the one that ran."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "the build named by the receipt ran another commit" in reason
        for reason in verdict.reasons
    )


def test_a_receipt_without_a_writer_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    commit_statuses: dict[str, Any],
) -> None:
    """A row with no creator has no writer the queue can name."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    row = _receipt_row()
    row.pop("creator")
    commit_statuses["rows"] = [row]
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert result is not None
    assert not result.ok, result.reason
    assert "an unknown writer" in result.reason


def test_a_forged_row_does_not_cancel_the_receipt(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """A failing row next to the CI's own passing one is the forger's business.

    The queue looks for a trusted receipt. If the newest row of the context
    decided, a seat could hold a pull request by writing a failing status next
    to the CI's own passing one - so the trusted row is the one that counts.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [
        _receipt_row(
            login="chrizefan",
            state="failure",
            created_at="2026-10-21T03:00:00Z",
        ),
        _receipt_row(),
    ]
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert result is not None
    assert result.ok, result.reason


def test_the_ci_apps_own_later_failure_cancels_its_earlier_success(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The CI's last word on the head is the word.

    A green receipt from ten o'clock does not survive the app's own red row
    from noon. The app is the CI: when it reports a failure on this head, the
    check failed on this head, and an earlier green row cannot stand in for
    it. This is the other side of the rule above - a forged row is the
    forger's business, the app's own row is the queue's business.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [
        _receipt_row(created_at="2026-10-21T10:00:00Z"),
        _receipt_row(state="failure", created_at="2026-10-21T12:00:00Z"),
    ]
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert result is not None
    assert not result.ok, result.reason
    assert f"the '{RECEIPT_CONTEXT}' receipt is failure" in result.reason


def test_the_ci_apps_own_later_success_cancels_its_earlier_failure(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The newest row of the app decides, in both directions.

    The control for the test above: a failed run followed by a green one is a
    head that passed, because the CI re-ran it and the newer row says so. If
    the queue looked at the oldest row, or at any green row, this would fail.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [
        _receipt_row(state="failure", created_at="2026-10-21T10:00:00Z"),
        _receipt_row(created_at="2026-10-21T12:00:00Z"),
    ]
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert result is not None
    assert result.ok, result.reason


def test_the_commit_statuses_that_cannot_be_read_are_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """A read that fails is not the same as a receipt that is missing."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["problem"] = "gh api failed with exit 1: not logged in"
    pr = _pr(1, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "the commit statuses could not be read" in reason for reason in verdict.reasons
    )


def test_the_receipt_is_read_from_the_rest_endpoint(
    monkeypatch: pytest.MonkeyPatch, commit_statuses: dict[str, Any]
) -> None:
    """The GraphQL rollup carries no creator, so the REST endpoint is read."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert commit_statuses["calls"] == [
        f"api repos/{DIGITHINGS_REPO}/commits/{'a' * 40}/statuses?per_page=100"
    ]


def test_the_queue_reads_no_receipt_when_the_policy_asks_for_none(
    monkeypatch: pytest.MonkeyPatch, commit_statuses: dict[str, Any]
) -> None:
    """A receipt the policy does not ask for is not read at all.

    The queue looks at every open pull request on every tick, and a status list
    it is not going to obey buys nothing while the CI writes none.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(require=False), DIGITHINGS_REPO, mode=mq.PROVENANCE_ENFORCE
    )
    assert result is None
    assert commit_statuses["calls"] == []


def test_the_receipt_is_not_read_when_the_gate_is_off(
    monkeypatch: pytest.MonkeyPatch, commit_statuses: dict[str, Any]
) -> None:
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_OFF)
    result = mq.verify_trusted_receipt(
        _pr(1), _receipt_policy(), DIGITHINGS_REPO, mode=mq.PROVENANCE_OFF
    )
    assert result is None
    assert commit_statuses["calls"] == []


def test_the_shipped_policy_does_not_ask_for_a_receipt_yet() -> None:
    """The CI writes no receipt today, so the shipped policy asks for none.

    A policy that asked for one would refuse every pull request in the org the
    moment the mode was switched to `enforce`, which is the freeze the whole
    switch is staged to avoid. The chain ships switched off, and the policy
    change that comes with the CI's own installation token switches it on.
    """
    prov = mq.load_policy().ci_provenance
    assert prov.trusted_receipt.context == RECEIPT_CONTEXT
    assert prov.trusted_receipt.creators == (RECEIPT_WRITER,)
    assert prov.trusted_receipt.required is False


def test_a_softened_commit_comparison_needs_a_trusted_receipt(tmp_path: Path) -> None:
    """Nothing binds a status to a head without the receipt, so the file is refused.

    The build's own commit cannot be the pull request head while the launcher
    runs one build per repository, so a policy that softens that comparison
    has to ask for the receipt that binds the status to the head instead. A
    policy file that softens it without asking is refused rather than loaded.
    """
    raw = json.loads(mq.POLICY_PATH.read_text(encoding="utf-8"))
    raw["ci_provenance"]["commit_match"] = "shadow"
    raw["ci_provenance"]["trusted_receipt"]["require"] = False
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(mq.QueueError) as excinfo:
        mq.load_policy(path)
    assert "trusted receipt" in str(excinfo.value)


def test_a_softened_commit_comparison_is_measured_and_not_refused(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
    tmp_path: Path,
) -> None:
    """The receipt binds the status to the head, so the comparison can soften.

    The build that runs the check today is the launcher repository's own cron
    run, so its commit is never the pull request head. With the receipt in
    place the binding is the receipt, and the comparison becomes a measurement.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr,
        _receipt_policy(commit_match=mq.COMMIT_MATCH_SHADOW),
        acting_role="cto",
        base="develop",
        repo=DIGITHINGS_REPO,
    )
    assert verdict.eligible, verdict.reasons
    written = log.read_text(encoding="utf-8")
    # Per subject: both chains write the same words, so a loose assertion
    # would pass with the status chain's measurement dropped - and that is
    # the line the 48 hour window reads.
    assert (
        "measured 'local-ci': the build named by the status ran another commit"
        in written
    ), written
    assert (
        "measured 'local-ci/app': the build named by the receipt ran another commit"
        in written
    ), written


def test_the_commit_comparison_can_be_turned_off(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr,
        _receipt_policy(commit_match=mq.COMMIT_MATCH_OFF),
        acting_role="cto",
        base="develop",
        repo=DIGITHINGS_REPO,
    )
    assert verdict.eligible, verdict.reasons


def test_an_unknown_commit_match_mode_fails_safe_to_enforce(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
) -> None:
    """A misspelled switch must not silence the comparison."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.COMMIT_MATCH_ENV, "bogus")
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "the build named by the status ran another commit" in reason
        for reason in verdict.reasons
    )


def test_a_softened_commit_comparison_without_a_receipt_is_refused(
    monkeypatch: pytest.MonkeyPatch, woodpecker: dict[str, Any]
) -> None:
    """The environment can override the file, so the invariant is checked again.

    Nothing binds a status to the head commit without the receipt, so a
    softened comparison without one is a refusal, whatever the file says.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.COMMIT_MATCH_ENV, "shadow")
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _evaluate(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "nothing binds a status to the head commit" in reason
        for reason in verdict.reasons
    )


# ── reviewer independence: the review must come from another seat (DIG-4795) ───
#
# twelve-x #425 merged on 21 Oct 2026 with its review coverage written by its own
# author seat ("same model, separate context"), and #369's "in-session review" came
# from the author seat's own subagents. Every seat in this org pushes and comments
# under ONE GitHub login, so GitHub cannot say which seat wrote a comment. The seat
# identity has to travel inside the review artifact, and the queue has to check it
# against the Paperclip side.
#
# The gate has two halves and they are one question — did a DIFFERENT seat look at
# THIS head? — so they are exercised together:
#
#   * the marker must name the head the PR stands at now (a verdict against an
#     older head says nothing about the code that is about to merge), and
#   * the marker must not come from a seat that wrote the PR.
#
# The author is read from the code, not from the ticket: the seat whose run on the
# PR's own ticket was open when the PR's commits were committed, and the seats the
# commits declare in their trailers. The seat that OWNS the ticket is not the author
# — the QA Lead's finding on #6145 (21 Oct) was that the owner was refused as a
# reviewer while the author's own review passed on every branch without a trailer.

#: The seat that wrote the PR, the seat that reviewed it, and a third seat.
AUTHOR_AGENT = "11111111-1111-4111-8111-111111111111"
REVIEWER_AGENT = "22222222-2222-4222-8222-222222222222"
OTHER_AGENT = "33333333-3333-4333-8333-333333333333"
#: A fourth seat: the one that rebased the branch and so carries the newest
#: committer date on every commit the rebase rewrote.
REBASER_AGENT = "44444444-4444-4444-8444-444444444444"

#: The runs those seats were in when they posted.
AUTHOR_RUN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REVIEWER_RUN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
REBASE_RUN = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"

#: The ticket the PR is about. `_pr` names it in the branch.
TICKET = "DIG-9001"
TICKET_ID = "issue-9001"

#: When the PR's commit was committed. The author's default run covers it, so
#: the seat that ran then is the seat that wrote the code.
COMMIT_AT = "2026-10-20T08:30:00Z"


class _FakePaperclip:
    """The Paperclip side the reviewer gate reads, answered from a fixture.

    The gate asks three things: which seat owns the PR's ticket, which runs
    that seat had on the ticket, and which seat a named run belongs to. These
    answers are a fixture, so no test reads the live control plane.
    """

    def __init__(
        self,
        *,
        tickets: dict[str, dict[str, Any]] | None = None,
        runs: dict[str, dict[str, Any]] | None = None,
        issue_runs: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._tickets = tickets or {}
        self._runs = runs or {}
        self._issue_runs = issue_runs or {}
        #: Every run id the gate asked the API about, in order. The gate must
        #: never ask about a value that cannot be a run id: the API has no
        #: answer for one, and the failed read reads as a broken API.
        self.asked_runs: list[str] = []

    def ticket(self, key: str) -> dict[str, Any] | None:
        return self._tickets.get(key)

    def run(self, run_id: str) -> dict[str, Any] | None:
        self.asked_runs.append(run_id)
        return self._runs.get(run_id)

    def issue_runs(self, issue_id: str) -> list[dict[str, Any]]:
        return list(self._issue_runs.get(issue_id, []))


def _paperclip_run(
    run_id: str,
    agent: str,
    *,
    started: str = "2026-10-20T08:00:00Z",
    finished: str | None = "2026-10-20T09:00:00Z",
    context_issue: str = TICKET_ID,
) -> dict[str, Any]:
    """One run, in the shape the Paperclip API returns for an issue's runs.

    `contextIssueId` is the issue the run was about. A run that was about
    another ticket — the reviewer that works from its own review ticket — is
    not evidence about who wrote this PR.
    """
    return {
        "runId": run_id,
        "agentId": agent,
        "startedAt": started,
        "finishedAt": finished,
        "contextIssueId": context_issue,
    }


def _paperclip(
    *,
    author_runs: list[dict[str, Any]] | None = None,
    runs: list[dict[str, Any]] | None = None,
    assignee: str = AUTHOR_AGENT,
) -> _FakePaperclip:
    """The Paperclip facts of one PR: its ticket, the runs on it, the named runs.

    `author_runs` are the runs that happened on the PR's ticket. The default
    is the author seat's run, which covers the PR's commit — that is what
    makes the seat that wrote the code the author. `runs` are the runs a
    marker may name.
    """
    on_ticket = (
        list(author_runs)
        if author_runs is not None
        else [_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)]
    )
    every = list(runs or []) + on_ticket
    return _FakePaperclip(
        tickets={
            TICKET: {
                "id": TICKET_ID,
                "identifier": TICKET,
                "assigneeAgentId": assignee,
            }
        },
        runs={r["runId"]: r for r in every},
        issue_runs={TICKET_ID: on_ticket},
    )


def _provenance_comment(
    *,
    agent: str = REVIEWER_AGENT,
    run: str = REVIEWER_RUN,
    head: str = "a" * 40,
    created: str = "2026-10-20T10:00:00Z",
    comment_id: str = "IC_kwDOreview_9001",
) -> dict[str, Any]:
    """A review comment carrying the in-session marker AND its provenance.

    The provenance marker is what the gate reads: the Paperclip seat, the run
    that seat was in, and the head the review looked at.
    """
    return {
        "id": comment_id,
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": created,
        "url": "https://github.com/digithings-ai/digithings/pull/9001#issuecomment-1",
        "body": (
            "<!-- in-session-review -->\n"
            f"<!-- digithings-review agent={agent} run={run} head={head} -->\n\n"
            "## Verdict: approve\n\n0 blockers, 2 majors filed.\n"
        ),
    }


def _bare_comment() -> dict[str, Any]:
    """A review comment with the in-session marker and no provenance at all."""
    return {
        "id": "IC_kwDObare_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": "<!-- in-session-review -->\n\n## Verdict: approve\n\n0 blockers.\n",
    }


def _reviewed_pr(
    comments: list[dict[str, Any]],
    *,
    number: int = 9001,
    head_sha: str = "a" * 40,
    label: bool = True,
    commit_at: str = COMMIT_AT,
    commits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A PR that claims an in-session review, with the label that claims it.

    The PR carries the commit the review is about, and the time it was
    committed: the author is read from the code, so a fixture with no commit
    has no author and the gate cannot judge independence at all.
    """
    pr = _pr(
        number,
        head_sha=head_sha,
        comments=comments,
        commits=(
            list(commits)
            if commits is not None
            else [
                {
                    "oid": head_sha,
                    "messageHeadline": "fix: the work this PR carries",
                    "authoredDate": commit_at,
                    "committedDate": commit_at,
                }
            ]
        ),
    )
    if label:
        pr["labels"] = [{"name": "reviewed:agent"}]
    return pr


def _judge(pr: dict[str, Any], prov: _FakePaperclip) -> Any:
    """Run the whole gate on one PR, with the Paperclip side under the test's control."""
    return mq.evaluate(
        pr,
        mq.load_policy(),
        acting_role="cto",
        base="develop",
        prov=prov,
    )


def test_a_marker_from_the_author_seat_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seat cannot review its own PR: the marker is dropped and the PR waits.

    This is the loophole twelve-x #425 merged through — the review coverage came
    from the author seat itself ("same model, separate context"), and the guard
    found the content harmless but the door open to any seat.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason
    assert "author's own seat" in reason
    assert "a review from a different seat" in reason


def test_the_reviewed_agent_label_does_not_carry_the_author_seats_own_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The label claims a review; the marker behind it has to be one.

    `reviewed:agent` is a claim, and the claim's evidence is the findings comment.
    When that comment is the author's own review, the label is a claim with nothing
    behind it — the same hole #5526 was, with the author as the only reviewer.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)])
    assert pr["labels"] == [{"name": "reviewed:agent"}]
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    assert not any("in-session review" in reason for reason in verdict.reasons)


def test_the_seat_that_wrote_the_code_is_the_author_without_a_trailer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author's own review does not count, with or without a trailer.

    The QA Lead's first blocker (21 Oct): 28 of the 30 open develop PRs carry
    no `Paperclip-Agent-Id:` trailer, and on those the author's own review
    was accepted. The author is read from the code — the seat whose run on
    the PR's own ticket was open when the commit was committed — so a
    trailer is one source among several, not the only one.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "author's own seat" in reason
    assert AUTHOR_AGENT[:8] in reason


def test_the_seat_that_owns_the_ticket_is_not_the_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owning the ticket is not writing the code.

    The QA Lead's second blocker (21 Oct): the seat that owns DIG-4795 — the
    Code Reviewer — was treated as the author, so its review was refused. A
    ticket owner is asked to move the ticket along; the author is the seat
    whose commit is on the branch. Measured on #6145: the owner was the Code
    Reviewer and the author was the Repo CI & Release Engineer.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
        runs=[_paperclip_run(REVIEWER_RUN, OTHER_AGENT)],
        assignee=OTHER_AGENT,
    )
    pr = _reviewed_pr([_provenance_comment(agent=OTHER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert OTHER_AGENT[:8] in verdict.review_evidence


def test_a_reviewer_woken_on_the_ticket_while_the_author_pushes_is_not_the_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author is the seat the code came from, not the seat that was awake.

    A reviewer woken on the ticket while the author pushes a fix shares a
    window with the author. The seat the most commits fall into is the
    author, so the reviewer stays a reviewer — and its review counts.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(
                AUTHOR_RUN,
                AUTHOR_AGENT,
                started="2026-10-20T08:00:00Z",
                finished="2026-10-20T11:00:00Z",
            ),
            _paperclip_run(
                REVIEWER_RUN,
                REVIEWER_AGENT,
                started="2026-10-20T09:30:00Z",
                finished="2026-10-20T10:30:00Z",
            ),
        ],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the first change",
                "authoredDate": "2026-10-20T08:30:00Z",
                "committedDate": "2026-10-20T08:30:00Z",
            },
            {
                "oid": "b" * 40,
                "messageHeadline": "fix: the change the reviewer watched land",
                "authoredDate": "2026-10-20T10:00:00Z",
                "committedDate": "2026-10-20T10:00:00Z",
            },
        ],
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert REVIEWER_AGENT[:8] in verdict.review_evidence


def test_a_seat_that_pushed_one_of_the_commits_is_an_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authorship is per commit, not a ranking of the whole PR.

    A PR can carry commits from two seats: the seat that wrote most of them
    and the seat that wrote the rest. A rule that ranks the seats by how many
    commits fall into their windows drops the second seat from the author set
    — and then that seat's own review counts as coverage of a PR it partly
    wrote. The commit that falls inside exactly one seat's window was written
    by that seat.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(
                AUTHOR_RUN,
                AUTHOR_AGENT,
                started="2026-10-20T08:00:00Z",
                finished="2026-10-20T09:00:00Z",
            ),
            _paperclip_run(
                REVIEWER_RUN,
                REVIEWER_AGENT,
                started="2026-10-20T09:30:00Z",
                finished="2026-10-20T11:00:00Z",
            ),
        ],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the first change",
                "authoredDate": "2026-10-20T08:30:00Z",
                "committedDate": "2026-10-20T08:30:00Z",
            },
            {
                "oid": "b" * 40,
                "messageHeadline": "fix: the change the other seat pushed",
                "authoredDate": "2026-10-20T10:00:00Z",
                "committedDate": "2026-10-20T10:00:00Z",
            },
        ],
    )
    # The second seat wrote the second commit, so it is an author: its own
    # review does not count.
    own = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=pr["commits"],
    )
    verdict = _judge(own, prov)
    assert not verdict.eligible
    assert "author's own seat" in " ".join(verdict.reasons)

    # A seat that wrote nothing on the branch still reviews.
    third = _paperclip(
        author_runs=[
            _paperclip_run(
                AUTHOR_RUN,
                AUTHOR_AGENT,
                started="2026-10-20T08:00:00Z",
                finished="2026-10-20T09:00:00Z",
            ),
            _paperclip_run(
                REVIEWER_RUN,
                REVIEWER_AGENT,
                started="2026-10-20T09:30:00Z",
                finished="2026-10-20T11:00:00Z",
            ),
        ],
        runs=[_paperclip_run("cccccccc-cccc-4ccc-8ccc-cccccccccccc", OTHER_AGENT)],
    )
    outside = _reviewed_pr(
        [_provenance_comment(agent=OTHER_AGENT, run="cccccccc-cccc-4ccc-8ccc-cccccccccccc")],
        commits=pr["commits"],
    )
    verdict = _judge(outside, third)
    assert verdict.eligible, verdict.reasons
    assert OTHER_AGENT[:8] in verdict.review_evidence


def test_a_merge_commit_does_not_make_the_merging_seat_the_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merging `develop` into a branch is maintenance, not authorship.

    Measured on #6145: the merge of `develop` landed inside the QA Lead's
    run window, so a gate that counted merge commits made the seat that
    rebased the branch an author of the PR it was reviewing.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(AUTHOR_RUN, AUTHOR_AGENT),
            _paperclip_run(
                REVIEWER_RUN,
                REVIEWER_AGENT,
                started="2026-10-20T09:00:00Z",
                finished="2026-10-20T10:00:00Z",
            ),
        ],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": COMMIT_AT,
            },
            {
                "oid": "b" * 40,
                "messageHeadline": "Merge branch 'develop' into DIG-9001-work",
                "authoredDate": "2026-10-20T09:30:00Z",
                "committedDate": "2026-10-20T09:30:00Z",
            },
        ],
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert REVIEWER_AGENT[:8] in verdict.review_evidence


def test_a_rebased_commit_is_attributed_to_its_author_not_to_the_rebasing_seat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rebase does not hand the branch to the seat that rebased it.

    A rebase rewrites every commit it replays: the author date and the
    message stay, the committer date becomes the rebasing seat's. Measured
    on #6145 (the QA Lead's finding, 21 Oct): read from the committer date,
    the seat that rebased the branch became the PR's author, and the real
    author's own review then counted as coverage of the PR it wrote.

    So the commit below carries the signature of a rewrite — a committer date
    inside the rebasing seat's run window, an author date inside the
    author's — and the author is still the seat that wrote the code.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(AUTHOR_RUN, AUTHOR_AGENT),
            _paperclip_run(
                REBASE_RUN,
                REBASER_AGENT,
                started="2026-10-20T11:00:00Z",
                finished="2026-10-20T13:00:00Z",
            ),
        ],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": "2026-10-20T12:00:00Z",
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "author's own seat" in reason
    assert AUTHOR_AGENT[:8] in reason


def test_a_rebase_outside_every_run_window_leaves_the_pr_reviewable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rebase's own timestamp must not decide whether the PR has an author.

    A seat that rebases a branch usually works it from another ticket, so
    the rebase lands outside every run window on this PR's own ticket. Read
    from the committer date, that leaves the PR with no author at all: the
    gate cannot show the review came from a different seat, so it refuses
    every marker and the PR can never merge (the QA Lead's finding on #6145,
    21 Oct). The author date is still inside the author's window, so the
    author is found and another seat's review counts.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
        runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": "2026-10-20T23:30:00Z",
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert REVIEWER_AGENT[:8] in verdict.review_evidence


def test_a_commit_with_no_author_date_is_not_attributed_to_anyone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A commit with no author date is no evidence about who wrote it.

    The gate does not fall back to the committer date, because that is the
    date a rewrite moves: a fallback would reopen the hole the author date
    closes. So a commit without an author date is left out, and a PR whose
    commits all lack one has no author — which the gate refuses, rather than
    guesses at.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
        runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "committedDate": COMMIT_AT,
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "authoring seat could not be identified" in reason


def test_a_run_trailer_names_the_author_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run trailer names the author even when no window covers the commit.

    `Paperclip-Run-Id:` is the run that wrote the commit, and the API says
    which seat owned that run. It is exact, so it counts on its own.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[],
        runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
    )
    pr = _reviewed_pr(
        [_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": COMMIT_AT,
                "messageBody": (
                    f"Paperclip-Agent-Id: {AUTHOR_AGENT}\n"
                    f"Paperclip-Run-Id: {AUTHOR_RUN}\n"
                ),
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "author's own seat" in reason
    assert AUTHOR_AGENT[:8] in reason


def test_a_pr_with_no_author_evidence_is_unverifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No author, no verdict: the PR waits and says why.

    A branch with no trailer, a ticket with no run that covers the commit,
    and a reviewer who is not the author: the gate cannot show the review
    came from a different seat, so it refuses rather than assumes.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(author_runs=[])
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "authoring seat could not be identified" in reason


def test_a_marker_from_another_seat_on_the_current_head_is_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate must not add friction to a real independent review."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
        runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT, started="2026-10-20T09:30:00Z")],
    )
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert "in-session review" in verdict.review_evidence
    # The evidence names the seat and the head it checked, so the audit trail
    # says which review carried the PR.
    assert REVIEWER_AGENT[:8] in verdict.review_evidence
    assert "a" * 12 in verdict.review_evidence


def test_a_marker_from_the_author_seat_during_its_own_run_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author's own review, posted while the author's run was open.

    The window is the author's: the seat's subagents and same-session
    reviewers share its run id, so a marker of that seat inside that window
    is the author's review. The log says which run spoke.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(
                AUTHOR_RUN,
                AUTHOR_AGENT,
                started="2026-10-20T08:00:00Z",
                finished="2026-10-20T11:00:00Z",
            )
        ],
    )
    pr = _reviewed_pr(
        [
            _provenance_comment(
                agent=AUTHOR_AGENT,
                run=AUTHOR_RUN,
                created="2026-10-20T10:00:00Z",
            )
        ]
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "author's own seat" in reason
    assert "still active" in reason
    assert AUTHOR_RUN[:8] in reason


def test_a_review_from_another_seat_inside_the_author_run_window_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Another seat's review is that seat's review, even mid-author-run.

    The QA Lead's third blocker (21 Oct): the author's run window was a veto
    on every marker, so an independent review posted while the author was
    still working was dropped. Refusing that refuses every honest review, and
    the author's own review is already refused by the seat it names.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[
            _paperclip_run(
                AUTHOR_RUN,
                AUTHOR_AGENT,
                started="2026-10-20T08:00:00Z",
                finished="2026-10-20T11:00:00Z",
            ),
            _paperclip_run(
                REVIEWER_RUN,
                REVIEWER_AGENT,
                started="2026-10-20T09:30:00Z",
                finished="2026-10-20T10:30:00Z",
            ),
        ],
    )
    pr = _reviewed_pr(
        [
            _provenance_comment(
                agent=REVIEWER_AGENT,
                run=REVIEWER_RUN,
                created="2026-10-20T10:00:00Z",
            )
        ]
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert REVIEWER_AGENT[:8] in verdict.review_evidence


def test_a_marker_that_names_an_older_head_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verdict on an older head says nothing about the head about to merge.

    Measured on #5994 on 21 Oct: the only marker on the PR was a `changes
    requested` verdict naming head `22d4b3126`, while the PR stood at
    `15414f011d`. A stale approve on an older head would satisfy the gate.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN, head="b" * 40)],
        head_sha="a" * 40,
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "names head" in reason
    assert "while this PR stands at" in reason


def test_a_marker_that_names_a_short_prefix_of_the_head_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reviewer who writes 7 characters of the head has still named the head.

    The QA Lead's census of the open develop PRs on 21 Oct found markers
    naming the head as 7, 8, 12 and 40 characters. A check that wanted one
    fixed width would read a valid 7-character marker as naming nothing.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN, head="a" * 7)],
        head_sha="a" * 40,
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible
    assert REVIEWER_AGENT[:8] in verdict.review_evidence


def test_a_marker_that_names_too_few_characters_binds_no_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three characters are not a head binding, whatever they match."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN, head="aaa")],
        head_sha="a" * 40,
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason


def test_a_stale_last_marker_is_a_refusal_and_not_a_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The last marker governs. An older review does not stand in for it.

    The QA Lead's second implementation detail (21 Oct): the gate reads the
    last review marker, so if that marker names a stale head the remedy has to
    be a new review. Falling back to an earlier marker would let a stale last
    marker be papered over by an older one — and the head only moves forward,
    so an earlier marker can only ever bind an older head.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    earlier = _provenance_comment(
        agent=REVIEWER_AGENT,
        run=REVIEWER_RUN,
        created="2026-10-20T09:00:00Z",
        comment_id="IC_kwDOearlier_9001",
    )
    later = _provenance_comment(
        agent=REVIEWER_AGENT,
        run=REVIEWER_RUN,
        head="b" * 40,
        created="2026-10-20T11:00:00Z",
        comment_id="IC_kwDOlater_9001",
    )
    pr = _reviewed_pr([earlier, later], head_sha="a" * 40)
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason
    assert "names head" in reason


def test_a_self_review_marker_last_does_not_fall_back_to_an_earlier_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The author seat cannot post last and let an earlier review cover for it.

    The author seat's own marker is the one the gate reads, so it is refused
    even though an independent reviewer said something earlier. The remedy is
    another seat's review, posted after.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(
        author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)],
        runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)],
    )
    earlier = _provenance_comment(
        agent=REVIEWER_AGENT,
        run=REVIEWER_RUN,
        created="2026-10-20T09:00:00Z",
        comment_id="IC_kwDOearlier_9001",
    )
    later = _provenance_comment(
        agent=AUTHOR_AGENT,
        run=AUTHOR_RUN,
        created="2026-10-20T11:00:00Z",
        comment_id="IC_kwDOlater_9001",
    )
    pr = _reviewed_pr([earlier, later])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason
    assert "author's own seat" in reason


def test_a_marker_without_provenance_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A comment that says "approve" but names no seat and no head proves nothing.

    This is the state every review comment is in today: the marker is the only
    thing a comment carries, and the marker names nobody.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr([_bare_comment()])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "carries neither a seat nor a run" in reason
    assert "names no head SHA" in reason


def test_a_marker_naming_a_run_the_api_does_not_know_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolvable run is a missing signal, not a clearance."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip()
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "does not know" in reason
    assert REVIEWER_RUN[:8] in reason


def test_a_marker_whose_seat_does_not_match_its_run_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker names one seat; the run says another. The run wins."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, OTHER_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "belongs to seat" in reason
    assert OTHER_AGENT[:8] in reason


def test_a_marker_quoted_in_prose_is_not_a_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sentence that quotes the marker is prose about it, not the claim.

    This is the comment that put the transport failures in the shadow log on
    21 Oct 2026: a review comment that explained which marker the gate wants
    and quoted it with placeholder values. Read as a claim, the gate asked the
    Paperclip API about `…`, the read failed on a healthy API, and the gate
    reported a broken API instead of the fact about the comment it held.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOprose_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n\n"
            "The reviewer-independence gate wants a "
            "`<!-- digithings-review agent=… run=… head=… -->` marker from a seat "
            "that is not the author's. This comment cannot carry it.\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    # The comment carries no provenance at all, so the PR waits for a real
    # review — and it waits with the truth: the gate judged the comment it
    # held, and nothing was asked of the API.
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "carries neither a seat nor a run" in reason
    assert prov.asked_runs == []


def test_a_marker_with_placeholder_values_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A placeholder is not a record, so it is never sent to the API.

    The review template ships the marker with `<your Paperclip agent id>` and
    friends. A seat that posts a marker with values it could not fill in posts
    a claim the queue can never resolve — and the queue used to ask the API
    about it, which turned a fact about the comment into a failed read and the
    failed read into a broken API (DIG-4809, 21 Oct 2026).
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOplaceholder_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            "<!-- digithings-review agent=… run=… head=… -->\n\n"
            "## Verdict: approve\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "not a run id" in reason
    assert "not a commit SHA" in reason
    assert prov.asked_runs == []


def test_a_marker_naming_a_seat_that_is_not_one_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seat id is a uuid. A value that is not one is not checked against a run."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOseat_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            f"<!-- digithings-review agent=… run={REVIEWER_RUN} "
            "head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "not a seat id" in reason
    # The run is a real run id, so the run is read — the seat that claimed it
    # is the one thing the gate could not check.
    assert prov.asked_runs == [REVIEWER_RUN]


def test_a_marker_naming_a_seat_and_no_run_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A seat that is not a seat id names no seat the queue could check."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOseatonly_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            "<!-- digithings-review agent=… -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "not a seat id" in reason
    assert prov.asked_runs == []


def test_a_uuid_shaped_placeholder_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A uuid shape the Paperclip API would refuse is never sent to it.

    The API answers 400 for an id that is not a uuid it accepts, and a 400
    read as a failed read is a transport failure — the queue then stops every
    merge on a healthy API. So the shape is checked here, against the rule the
    API itself applies (measured on 21 Oct 2026: version 1 to 5 and variant 8,
    9, a or b are accepted, everything else answers 400).
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOsha_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            "<!-- digithings-review agent=11111111-1111-4111-8111-111111111111 "
            "run=00000000-0000-0000-0000-000000000000 "
            "head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "not a run id" in reason
    assert prov.asked_runs == []


def test_a_marker_beside_the_in_session_marker_still_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The two markers may share a line: the line carries nothing but markers."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOsameline_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            f"<!-- in-session-review --> <!-- digithings-review agent={REVIEWER_AGENT} "
            f"run={REVIEWER_RUN} head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert prov.asked_runs == [REVIEWER_RUN]


def test_a_marker_in_a_bullet_still_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A list bullet in front of the marker is formatting, not prose."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDObullet_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            f"- <!-- digithings-review agent={REVIEWER_AGENT} run={REVIEWER_RUN} "
            "head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert prov.asked_runs == [REVIEWER_RUN]


def test_a_marker_in_a_quoted_reply_is_not_a_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quoted reply carries someone else's words, so it is not the seat's claim."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOquote_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            f"> <!-- digithings-review agent={REVIEWER_AGENT} run={REVIEWER_RUN} "
            "head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa -->\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "could not be read" not in reason
    assert "carries neither a seat nor a run" in reason
    assert prov.asked_runs == []


def test_a_run_that_carries_no_seat_is_not_review_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A run the API knows but that names no seat proves nobody reviewed.

    The marker claims a seat and a run, and neither can be checked, so the
    gate cannot say who reviewed: that is a missing signal, not a clearance.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[{"runId": REVIEWER_RUN}])
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "carries no seat" in reason


def test_a_marker_with_text_after_it_on_its_line_is_not_a_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The marker stands alone: a line that carries more than the marker is prose."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    comment = {
        "id": "IC_kwDOtrailing_9001",
        "author": {"login": "chrizefan"},
        "authorAssociation": "MEMBER",
        "createdAt": "2026-10-20T10:00:00Z",
        "body": (
            "<!-- in-session-review -->\n"
            f"<!-- digithings-review agent={REVIEWER_AGENT} run={REVIEWER_RUN} "
            "head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa --> Reviewed.\n"
        ),
    }
    pr = _reviewed_pr([comment])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "carries neither a seat nor a run" in reason
    assert prov.asked_runs == []


def test_a_marker_on_a_line_of_its_own_still_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule tightens the reader, not the claim: a real marker still counts."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert prov.asked_runs == [REVIEWER_RUN]


def test_a_ticket_the_api_does_not_know_is_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 is an answer, not a failure. The queue must not die on it.

    The live API answers 404 for a ticket key nobody ever filed. That has to
    read as "no such ticket" — the gate then says it could not identify the
    authoring seat — and not as an exception that takes the tick down.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _FakePaperclip(tickets={})
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason
    assert "authoring seat could not be identified" in reason


def test_an_api_that_cannot_be_read_leaves_the_pr_unverifiable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The API going away is not a verdict. The PR waits, and nothing crashes.

    A partial judgement is not a judgement: if the queue cannot read the
    run record, it cannot say the reviewer was another seat, so it refuses
    the PR — and it says why.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")

    class _BrokenPaperclip(_FakePaperclip):
        def run(self, run_id: str) -> dict[str, Any] | None:
            raise mq._PaperclipUnavailable("Paperclip could not be read")

        def issue_runs(self, issue_id: str) -> list[dict[str, Any]]:
            raise mq._PaperclipUnavailable("Paperclip could not be read")

    prov = _BrokenPaperclip(
        tickets={TICKET: {"id": TICKET_ID, "assigneeAgentId": AUTHOR_AGENT}},
    )
    pr = _reviewed_pr([_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)])
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "reviewer independence" in reason
    assert "could not be checked" in reason


def test_a_404_from_the_api_is_an_answer_and_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The live API answers 404 for a record nobody has. That must not crash.

    This is the difference between "there is no such ticket" and "the API is
    down", and the gate has to tell them apart: a 404 is a fact it can judge
    on, a refused connection is a fact it cannot.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")

    def _urlopen(request: Any, timeout: int | None = None) -> Any:
        raise urllib.error.HTTPError(
            str(request.full_url), 404, "Not Found", {}, None
        )

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-0000") is None
    assert reader.run("00000000-0000-4000-8000-000000000000") is None
    assert reader.issue_runs("issue-0000") == []


def test_a_400_from_the_api_is_an_answer_and_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 400 is the server refusing the address, so there is no record under it.

    The live API answers 400 for a heartbeat run id that is not a uuid it
    accepts. Read as a failed read, that answer became a transport failure,
    and a transport failure stops every merge in the queue — over a bad id in
    a comment, on a healthy API (DIG-4809, 21 Oct 2026).
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")

    def _urlopen(request: Any, timeout: int | None = None) -> Any:
        raise urllib.error.HTTPError(
            str(request.full_url), 400, "Bad Request", {}, None
        )

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-0000") is None
    assert reader.run("00000000-0000-0000-0000-000000000000") is None
    assert reader.issue_runs("issue-0000") == []


def test_a_commit_whose_run_trailer_is_not_a_run_id_refuses_the_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trailer the API would refuse leaves the author unknown, so the gate refuses.

    The commit names a run that is not a run id. The seat that wrote the
    commit cannot be resolved, and an unknown seat may be the seat that
    posted the review the gate is about to count. Dropping the trailer
    silently would let that seat review itself; the gate refuses instead.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": COMMIT_AT,
                "messageBody": (
                    f"Paperclip-Agent-Id: {AUTHOR_AGENT}\n"
                    "Paperclip-Run-Id: 00000000-0000-0000-0000-000000000000\n"
                ),
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "authoring seat could not be identified" in reason
    assert "names a run id that is not one" in reason
    assert prov.asked_runs == []


def test_a_commit_whose_seat_trailer_is_not_a_seat_id_refuses_the_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The seat trailer is the author's name: a broken one leaves the author unknown."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT, run=REVIEWER_RUN)],
        commits=[
            {
                "oid": "a" * 40,
                "messageHeadline": "fix: the work",
                "authoredDate": COMMIT_AT,
                "committedDate": COMMIT_AT,
                "messageBody": (
                    "Paperclip-Agent-Id: 00000000-0000-0000-0000-000000000000\n"
                ),
            }
        ],
    )
    verdict = _judge(pr, prov)
    assert not verdict.eligible
    reason = " ".join(verdict.reasons)
    assert "authoring seat could not be identified" in reason
    assert "names a seat id that is not one" in reason


def test_a_marker_naming_a_seat_in_another_case_is_the_same_seat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A uuid is a uuid in any case: the gate compares one spelling of it.

    The API accepts an uppercase uuid, so an uppercase marker names a real
    seat. Refusing it would refuse an honest review for a spelling.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "enforce")
    prov = _paperclip(runs=[_paperclip_run(REVIEWER_RUN, REVIEWER_AGENT)])
    pr = _reviewed_pr(
        [_provenance_comment(agent=REVIEWER_AGENT.upper(), run=REVIEWER_RUN.upper())]
    )
    verdict = _judge(pr, prov)
    assert verdict.eligible, verdict.reasons
    assert prov.asked_runs == [REVIEWER_RUN.lower()]


def test_a_refused_connection_is_not_read_as_a_missing_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A connection error raises, so the gate says "could not be checked"."""
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)

    def _urlopen(request: Any, timeout: int | None = None) -> Any:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable):
        reader.ticket("DIG-4795")


class _FakeResponse:
    """The shape `urlopen` returns: a context manager whose `read` is bytes."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_a_slow_read_that_times_out_once_is_asked_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow API is not a refusal: the read waits, and it tries again.

    On 2026-10-21 the Code Reviewer measured the Paperclip API answering
    `GET /api/issues/{id}` in 31.5 s, 36.5 s and 30.7 s, and
    `GET /api/issues/{id}/runs` not at all in 60 s. The old ten-second read
    turned every one of those into a refusal, and in `enforce` mode a refusal
    for a transport reason is indistinguishable from a refusal for a real one.
    So the read waits longer than the slowest answer measured, and a read that
    times out is asked again — the request is a GET, and a question that was
    not answered is not an answer.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    timeouts: list[float | None] = []
    answers: list[Any] = [TimeoutError("timed out"), {"id": "issue-0000"}]

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        timeouts.append(timeout)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _FakeResponse(answer)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-4795") == {"id": "issue-0000"}
    assert timeouts == [mq.PAPERCLIP_READ_TIMEOUT, mq.PAPERCLIP_READ_TIMEOUT]


def test_a_read_that_never_answers_says_it_is_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the API never answers, the refusal says so and names the attempts.

    The message is what separates "the API was too slow" from "the reviewer
    was the author": in `enforce` mode the first must never be read as the
    second, and the shadow log has to be able to count the transport failures
    apart from the refusals about review independence.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    timeouts: list[float | None] = []

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        timeouts.append(timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable) as excinfo:
        reader.ticket("DIG-4795")
    message = str(excinfo.value)
    assert "could not be read" in message
    assert f"{mq.PAPERCLIP_READ_ATTEMPTS} attempts" in message
    assert "/api/issues/DIG-4795" in message
    assert not isinstance(excinfo.value, mq._PaperclipMissing)
    assert len(timeouts) == mq.PAPERCLIP_READ_ATTEMPTS


def test_a_missing_record_is_not_asked_for_twice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 is an answer, and an answer does not get better by asking again.

    The gate judges a missing ticket or a run nobody has heard of, so the
    first answer ends the read. Trying again would only spend the budget on a
    fact that is already known.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    timeouts: list[float | None] = []

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        timeouts.append(timeout)
        raise urllib.error.HTTPError(str(request.full_url), 404, "Not Found", {}, None)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-4795") is None
    assert len(timeouts) == 1


def test_a_truncated_answer_is_a_transport_failure_and_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A body that stops half way is not a fact, and it must not crash the gate.

    A truncated response raises `http.client.IncompleteRead`, which is neither
    an `OSError` nor a `ValueError`. Before this change it escaped the read
    entirely and the gate crashed instead of failing closed.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    answers: list[Any] = [
        http.client.IncompleteRead(b'{"id": "issue-0'),
        {"id": "issue-0000"},
    ]

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _FakeResponse(answer)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-4795") == {"id": "issue-0000"}
    assert len(answers) == 0


def test_a_server_error_is_asked_for_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 5xx is the API failing, not the API answering, so it earns one more try."""
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    timeouts: list[float | None] = []
    answers: list[Any] = [
        urllib.error.HTTPError(
            "http://127.0.0.1:3100/api/issues/DIG-4795", 503, "Unavailable", {}, None
        ),
        {"id": "issue-0000"},
    ]

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        timeouts.append(timeout)
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _FakeResponse(answer)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    assert reader.ticket("DIG-4795") == {"id": "issue-0000"}
    assert len(timeouts) == 2


def test_the_read_numbers_are_the_measured_ones() -> None:
    """The four numbers are the fix, so the suite has to pin them.

    The slowest answer measured on 2026-10-21 was 36.5 s, so a timeout below
    45 s turns a slow API back into a refusal — the exact failure this change
    exists to remove. A budget below the timeout leaves no room for the second
    attempt, and a backoff of zero hammers a control plane that is already
    struggling.
    """
    assert mq.PAPERCLIP_READ_TIMEOUT >= 45
    assert mq.PAPERCLIP_READ_BUDGET >= mq.PAPERCLIP_READ_TIMEOUT
    assert mq.PAPERCLIP_READ_ATTEMPTS == 2
    assert mq.PAPERCLIP_RETRY_BACKOFF == 3.0


def test_a_read_stays_inside_its_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One read costs at most its budget, however slow the API is.

    The budget is the promise that a control plane which does not answer
    cannot hold the read open for ever. The clock belongs to the test here, so
    the wall clock of the read is a number and not a hope — and the pause
    between the attempts is inside the budget, not on top of it.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    clock = {"now": 1_000.0}
    timeouts: list[float | None] = []

    def _sleep(seconds: float) -> None:
        clock["now"] += seconds

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        timeouts.append(timeout)
        clock["now"] += timeout or 0.0
        raise TimeoutError("timed out")

    monkeypatch.setattr(mq.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(mq.time, "sleep", _sleep)
    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable) as excinfo:
        reader.ticket("DIG-4795")
    assert clock["now"] - 1_000.0 <= mq.PAPERCLIP_READ_BUDGET
    assert all(timeout is not None and timeout > 0 for timeout in timeouts)
    assert len(timeouts) == 2
    assert "(after 2 attempts)" in str(excinfo.value)


def test_a_spent_budget_names_the_attempts_it_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal names the attempts that were made, not the attempts allowed.

    With the budget spent before the second attempt, one request was made. A
    message that said "2 attempts" would be a claim about the API that the API
    never saw.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq, "PAPERCLIP_READ_BUDGET", 1.0)
    clock = {"now": 1_000.0}
    calls: list[float | None] = []

    def _sleep(seconds: float) -> None:
        clock["now"] += seconds

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        calls.append(timeout)
        clock["now"] += timeout or 0.0
        raise TimeoutError("timed out")

    monkeypatch.setattr(mq.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(mq.time, "sleep", _sleep)
    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable) as excinfo:
        reader.ticket("DIG-4795")
    assert len(calls) == 1
    assert "(after 1 attempt)" in str(excinfo.value)


def test_a_refusal_from_the_api_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 403 is the API answering, and its answer does not change when asked again.

    It is also not a transport failure, so the refusal must not wear the
    transport failure's message. The shadow log counts transport failures, and
    a refusal about permissions counted as one would hide the real refusals.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    calls: list[float | None] = []

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        calls.append(timeout)
        raise urllib.error.HTTPError(str(request.full_url), 403, "Forbidden", {}, None)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable) as excinfo:
        reader.ticket("DIG-4795")
    message = str(excinfo.value)
    assert "403" in message
    assert "attempts" not in message
    assert len(calls) == 1


def test_two_server_errors_name_the_code_and_the_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server that keeps failing is named in the refusal, with the attempts.

    Without the code in the message the refusal reads as "the budget was
    spent", which is a different fault with a different fix.
    """
    monkeypatch.setenv("PAPERCLIP_API_KEY", "not-a-real-key")
    monkeypatch.setattr(mq.time, "sleep", lambda _seconds: None)
    calls: list[float | None] = []

    def _urlopen(request: Any, timeout: float | None = None) -> Any:
        calls.append(timeout)
        raise urllib.error.HTTPError(str(request.full_url), 503, "Unavailable", {}, None)

    monkeypatch.setattr(mq.urllib.request, "urlopen", _urlopen)
    reader = mq.ReviewerProvenance(
        mq.ReviewIndependence(mode="enforce", api_url="http://127.0.0.1:3100")
    )
    with pytest.raises(mq._PaperclipUnavailable) as excinfo:
        reader.ticket("DIG-4795")
    message = str(excinfo.value)
    assert "503" in message
    assert "(after 2 attempts)" in message
    assert len(calls) == 2


def test_shadow_mode_merges_and_records_what_it_would_refuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The rollout DIG-4809 named: measure first, refuse later.

    Shadow mode is the 48-hour window. The PR merges as it would have merged
    before, and the log says what the gate would have said — so the flip to
    `enforce` is a switch, not a leap.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "shadow")
    log = tmp_path / "reviewer-independence.log"
    policy = replace(
        mq.load_policy(),
        review_independence=mq.ReviewIndependence(mode="shadow", log_path=str(log)),
    )
    prov = _paperclip(author_runs=[_paperclip_run(AUTHOR_RUN, AUTHOR_AGENT)])
    pr = _reviewed_pr([_provenance_comment(agent=AUTHOR_AGENT, run=AUTHOR_RUN)])
    verdict = mq.evaluate(pr, policy, acting_role="cto", base="develop", prov=prov)
    assert verdict.eligible, verdict.reasons
    text = log.read_text(encoding="utf-8")
    assert "would refuse" in text
    assert "author's own seat" in text


def test_the_gate_off_reads_no_provenance_at_all(monkeypatch: pytest.MonkeyPatch) -> None:
    """`off` is a switch, and it has to actually switch the gate off.

    Without this, a broken mode string that silently fell back to the strict
    reading would refuse every PR in the org, and the failure would look like
    the gate working.
    """
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "off")
    pr = _reviewed_pr([_bare_comment()])
    verdict = _judge(pr, _paperclip())
    assert verdict.eligible, verdict.reasons


def test_the_shipped_policy_turns_the_reviewer_gate_on() -> None:
    """The gate must not ship off.

    DIG-4809 named a 48-hour shadow window and a later flip to `enforce`. That
    is a rollout, not a gate that never runs: the shipped policy has to have the
    gate on in one of its two working modes.
    """
    mode = mq.load_policy().review_independence.mode
    assert mode in ("shadow", "enforce"), mode


def test_a_policy_with_an_unreadable_reviewer_mode_is_refused(tmp_path: Path) -> None:
    """A broken switch stops the queue rather than turning the gate off."""
    raw = json.loads(
        (REPO_ROOT / "scripts" / "merge_queue_policy.json").read_text(encoding="utf-8")
    )
    raw["review_independence"]["mode"] = "maybe"
    bad = tmp_path / "policy.json"
    bad.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(mq.QueueError, match="review_independence.mode"):
        mq.load_policy(bad)


def test_an_unreadable_env_value_fails_safe_to_enforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A misspelled switch must never turn a security gate off."""
    monkeypatch.setenv("MQ_REVIEW_INDEPENDENCE", "yes please")
    assert mq._effective_mode(mq.ReviewIndependence(mode="off")) == "enforce"


def test_the_review_command_posts_the_provenance_the_gate_reads() -> None:
    """The gate reads a marker the review command has to write.

    Two files carry the command: the one the seats run and the source it is
    generated from. Both have to carry the marker, or the gate refuses the
    reviews the command produced.
    """
    for path in (
        REPO_ROOT / ".claude" / "commands" / "review.md",
        REPO_ROOT / "agents" / "sources" / "commands" / "review.md",
    ):
        body = path.read_text(encoding="utf-8")
        assert "digithings-review" in body, path
        assert "agent=" in body and "run=" in body and "head=" in body, path


def test_the_merge_queue_doc_names_the_reviewer_independence_gate() -> None:
    """The gate a reader cannot find is a gate nobody can rely on."""
    doc = MERGE_QUEUE_DOC.read_text(encoding="utf-8")
    assert "reviewer independence" in doc.lower()
    assert "digithings-review" in doc


def test_a_seats_failing_row_beside_the_ci_receipt_does_not_hold_the_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The receipt chain judges the row by its writer, not by its colour.

    The generic scan reads every status that is neither a required check nor
    an ignored one, so without the receipt being carved out of it, a seat's
    own failing `local-ci/app` row would hold the pull request next to the
    CI's own passing one - the one thing the receipt chain exists to prevent.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row()]
    forged = {
        "__typename": "StatusContext",
        "context": RECEIPT_CONTEXT,
        "state": "FAILURE",
        "targetUrl": GOOD_TARGET_URL,
        "startedAt": "2026-10-21T03:00:00Z",
    }
    pr = _pr(
        1,
        local_ci_target_url=GOOD_TARGET_URL,
        reviews=_approved(),
        extra_checks=[forged],
    )
    verdict = _receipt_verdict(pr)
    assert verdict.eligible, verdict.reasons


def test_a_forged_row_still_cannot_cancel_the_receipt(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """The same scan, the other way round: a green seat row is not a receipt."""
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    commit_statuses["rows"] = [_receipt_row(login="chrizefan")]
    forged = {
        "__typename": "StatusContext",
        "context": RECEIPT_CONTEXT,
        "state": "SUCCESS",
        "targetUrl": GOOD_TARGET_URL,
        "startedAt": "2026-10-21T03:00:00Z",
    }
    pr = _pr(
        1,
        local_ci_target_url=GOOD_TARGET_URL,
        reviews=_approved(),
        extra_checks=[forged],
    )
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "was written by chrizefan, which is not a trusted CI writer" in reason
        for reason in verdict.reasons
    ), verdict.reasons


def test_a_refused_receipt_does_not_claim_the_receipt_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
) -> None:
    """A receipt that is there and is refused says what is wrong with it.

    The prefix used to say "has no trusted CI receipt" for every failure, so a
    receipt the app wrote and whose build ran another commit was reported as
    a missing receipt - the wrong thing to hand back.
    """
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    woodpecker["answer"]["payload"] = _pipeline(commit="b" * 40)
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = _receipt_verdict(pr)
    assert not verdict.eligible, verdict.reasons
    assert any(
        "is not accepted as a trusted CI receipt" in reason for reason in verdict.reasons
    ), verdict.reasons
    assert not any(
        "has no trusted CI receipt" in reason for reason in verdict.reasons
    ), verdict.reasons


def test_the_policy_note_says_the_switch_moves_commit_match_with_it() -> None:
    """The note is the file an operator reads when the switch is flipped."""
    import json

    raw = json.loads(mq.POLICY_PATH.read_text(encoding="utf-8"))
    note = str(raw.get("ci_provenance_note") or "")
    assert "the switch to `enforce` has to move `commit_match` in the same edit" in note


def test_a_receipt_block_without_a_require_key_is_required(tmp_path: Path) -> None:
    """The rule is written down, and it fails closed."""
    import json

    raw = json.loads(mq.POLICY_PATH.read_text(encoding="utf-8"))
    raw["ci_provenance"]["trusted_receipt"] = {
        "context": RECEIPT_CONTEXT,
        "creators": [RECEIPT_WRITER],
    }
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    policy = mq.load_policy(path)
    assert policy.ci_provenance.trusted_receipt.required is True


def test_a_build_that_reports_no_commit_is_measured_not_refused(
    monkeypatch: pytest.MonkeyPatch,
    woodpecker: dict[str, Any],
    commit_statuses: dict[str, Any],
    tmp_path: Path,
) -> None:
    """A build with no commit is a measurement under a softened comparison.

    It used to be a hard refusal. Under `commit_match: shadow` it is measured,
    and the rule is pinned so it cannot move without a test saying so.
    """
    log = tmp_path / "provenance.log"
    monkeypatch.setenv(mq.PROVENANCE_MODE_ENV, mq.PROVENANCE_ENFORCE)
    monkeypatch.setenv(mq.PROVENANCE_LOG_ENV, str(log))
    woodpecker["answer"]["payload"] = _pipeline(commit="")
    commit_statuses["rows"] = [_receipt_row()]
    pr = _pr(1, head_sha="a" * 40, local_ci_target_url=GOOD_TARGET_URL, reviews=_approved())
    verdict = mq.evaluate(
        pr,
        _receipt_policy(commit_match=mq.COMMIT_MATCH_SHADOW),
        acting_role="cto",
        base="develop",
        repo=DIGITHINGS_REPO,
    )
    assert verdict.eligible, verdict.reasons
    written = log.read_text(encoding="utf-8")
    assert "reports no commit" in written, written
