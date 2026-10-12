"""Unit tests for scripts/finalize_agent_prs.py's PR classifier.

Written because of a silent regression that had no test to catch it. Retiring the
Copilot subscription (#1904) removed the only thing that could ever produce a
Copilot review, and this classifier gated ``ready_merge`` behind one:

    if copilot_state == "none" and age >= MIN_AGE_HOURS:
        return "waiting", "request Copilot review"
    if copilot_state in {"approved", "commented"}:
        return "ready_merge", ...

With no Copilot review possible, ``_copilot_review_state`` could only return
``"none"``, so the first branch caught every eligible PR and ``ready_merge`` became
unreachable — the daily finalizer would have printed "waiting — request Copilot
review (no action)" forever and auto-merged nothing. Nothing went red; the
automation just stopped working.

``test_an_eligible_pr_reaches_ready_merge`` is the regression test. The rest pin the
branches around it so the next person removing a gate can see what they broke.

Review is enforced elsewhere now, where it is actually checkable: `bugbot run` or
/review on the task PR, recorded by a reviewed:* label, and asserted for the whole
range by ci-review-coverage.yml before anything reaches main.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "finalize_agent_prs.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("finalize_agent_prs", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["finalize_agent_prs"] = module
    spec.loader.exec_module(module)
    return module


fap = _load()


def _pr(**over: Any) -> dict[str, Any]:
    """An agent PR that should sail through: linked, green, old enough, unlabelled."""
    old = (datetime.now(UTC) - timedelta(hours=fap.MIN_AGE_HOURS + 1)).isoformat()
    base: dict[str, Any] = {
        "number": 1234,
        "headRefName": "cursor/some-work",
        "baseRefName": "develop",
        "labels": [],
        "isDraft": False,
        "body": "Fixes #99",
        "title": "feat: a thing",
        "createdAt": old,
        "statusCheckRollup": [{"name": "CI", "state": "SUCCESS", "conclusion": "SUCCESS"}],
        "reviews": [],
        "reviewRequests": [],
    }
    base.update(over)
    return base


def _evaluate(pr: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> Any:
    # The classifier reads issue labels over the network; the linked issue is not
    # what these tests are about.
    monkeypatch.setattr(fap, "_issue_labels", lambda repo, num: [])
    return fap.evaluate_pr("digithings-ai/digithings", pr, fetch_base=False)


def test_an_eligible_pr_reaches_ready_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE regression test: this returned "waiting" forever after #1904.

    A green, linked, old-enough agent PR with no blocking label must be mergeable.
    If this ever returns "waiting" again, a review gate has been reintroduced that
    depends on something which cannot happen.
    """
    action = _evaluate(_pr(), monkeypatch)
    assert action.state == "ready_merge", f"got {action.state!r} — {action.reason}"


def test_no_state_reason_still_asks_for_a_copilot_review(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dead gate must not come back by accident."""
    action = _evaluate(_pr(), monkeypatch)
    assert "copilot" not in action.reason.lower()


def test_a_young_pr_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    young = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    action = _evaluate(_pr(createdAt=young), monkeypatch)
    assert action.state == "waiting"
    assert "young" in action.reason


def test_a_draft_waits(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _evaluate(_pr(isDraft=True), monkeypatch).state == "waiting"


def test_an_unlinked_pr_needs_a_human(monkeypatch: pytest.MonkeyPatch) -> None:
    action = _evaluate(_pr(body="no linkage here", title="feat: a thing"), monkeypatch)
    assert action.state == "needs_human"


def test_the_retired_needs_human_label_no_longer_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Label simplification 2026-09 retired needs-human-review: it is inert now."""
    action = _evaluate(_pr(labels=[{"name": "needs-human-review"}]), monkeypatch)
    assert action.state == "ready_merge", f"got {action.state!r} — {action.reason}"


def test_a_claude_tier_issue_needs_a_human(monkeypatch: pytest.MonkeyPatch) -> None:
    """digikey-component issues route claude-tier (supervised) — no automerge."""
    monkeypatch.setattr(fap, "_issue_labels", lambda repo, num: ["component:digikey"])
    action = fap.evaluate_pr("digithings-ai/digithings", _pr(), fetch_base=False)
    assert action.state == "needs_human"
    assert "claude-tier" in action.reason


def test_an_already_labelled_pr_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    action = _evaluate(_pr(labels=[{"name": "automerge-agent"}]), monkeypatch)
    assert action.state == "skip"


def test_the_classifier_no_longer_reasons_about_copilot_reviews() -> None:
    """`_copilot_review_state` is gone; only the human-review filter keeps the logins."""
    assert not hasattr(fap, "_copilot_review_state")
    source = SCRIPT.read_text(encoding="utf-8")
    assert "copilot_state" not in source


def test_a_fork_pr_is_never_listed_even_with_an_agent_branch_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CWE-862 regression test: a branch name matching AGENT_BRANCH_PREFIXES is not
    proof the PR came from this repo — anyone can name a fork branch `task/1-x`.
    `_list_agent_prs` must filter on the live `isCrossRepository` field from the API,
    not just the branch string, or the finalizer's ready_merge path (label-add +
    `gh pr merge --auto --squash`) would auto-merge an attacker's fork PR.

    Fail-closed variant (CodeRabbit finding on #2345): the filter requires
    `isCrossRepository is False` exactly, not just falsy — a MISSING field must
    be excluded too, not treated as "confirmed same-repo." An earlier version of
    both this test and the production filter got this backwards: `.get(...,
    False)` on a missing field defaults to False, which reads as "not a fork,"
    the wrong default for a security check that can't confirm the PR's origin.
    """
    same_repo = _pr(number=1, headRefName="task/1-legit", isCrossRepository=False)
    fork = _pr(number=2, headRefName="task/1-legit", isCrossRepository=True)
    missing_field = _pr(number=3, headRefName="task/1-legit")
    assert "isCrossRepository" not in missing_field, (
        "fixture must omit the field, not just falsy it"
    )
    monkeypatch.setattr(fap, "_gh_json", lambda *a: [same_repo, fork, missing_field])
    prs = fap._list_agent_prs("digithings-ai/digithings")
    numbers = {pr["number"] for pr in prs}
    assert numbers == {1}, (
        "only the confirmed same-repo PR should survive; fork and missing-field must not"
    )


def test_list_agent_prs_still_filters_by_branch_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    agent_branch = _pr(number=1, headRefName="claude/some-work", isCrossRepository=False)
    other_branch = _pr(number=2, headRefName="feat/unrelated", isCrossRepository=False)
    monkeypatch.setattr(fap, "_gh_json", lambda *a: [agent_branch, other_branch])
    prs = fap._list_agent_prs("digithings-ai/digithings")
    assert {pr["number"] for pr in prs} == {1}


# --- DIG-3066: the GraphQL deadline and the split query --------------------
#
# The single wide query (--limit 100 with body/reviews/statusCheckRollup) was
# ~1.6 MB and failed on 4/4 measured attempts with HTTP 502/504 at ~11.5 s,
# against a ~11 s upstream deadline. These pin the two halves of the fix: the
# expensive fields move out of the candidate query, and gh calls get a bounded
# retry that still fails loudly.


def _fake_proc(returncode: int, stdout: str = "", stderr: str = "") -> Any:
    return subprocess.CompletedProcess(
        args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_the_candidate_query_does_not_ask_for_the_expensive_fields() -> None:
    """If these creep back into the list query, the 504 comes back with them.

    Asserted against the constants the query actually uses, and cross-checked on
    the source so a rename cannot quietly leave the wide query in place.
    """
    for heavy in ("body", "reviews", "statusCheckRollup", "labels", "mergeable"):
        assert heavy not in fap.CANDIDATE_FIELDS.split(","), (
            f"{heavy} in the candidate query re-inflates the payload"
        )
        assert heavy in fap.HYDRATE_FIELDS.split(","), f"{heavy} must still be fetched per PR"
    # isCrossRepository is the CWE-862 fork guard and is cheap — it must stay in
    # the candidate query or the filter has nothing to fail closed on.
    assert "isCrossRepository" in fap.CANDIDATE_FIELDS.split(",")


def test_the_candidate_limit_sees_more_than_the_old_page_of_100() -> None:
    """The old page silently truncated the scan: 23 of 42 agent PRs were skipped."""
    assert fap.PR_LIST_LIMIT > 100


def test_a_transient_gateway_failure_is_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Any] = []

    def fake_run(args: Any, **kw: Any) -> Any:
        calls.append(args)
        if len(calls) == 1:
            return _fake_proc(
                1, stderr="HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)"
            )
        return _fake_proc(0, stdout='{"ok": true}')

    slept: list[float] = []
    monkeypatch.setattr(fap.subprocess, "run", fake_run)
    monkeypatch.setattr(fap.time, "sleep", lambda s: slept.append(s))

    assert fap._gh_json("pr", "list") == {"ok": True}
    assert len(calls) == 2, "the retry must actually re-invoke gh"
    assert slept == [fap._GH_BACKOFF_SECONDS[0]], "a real backoff must be taken between attempts"


def test_the_retry_gives_up_and_raises_rather_than_swallowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hard failure must still fail the step — the retry must not hide it."""
    calls: list[Any] = []

    def fake_run(args: Any, **kw: Any) -> Any:
        calls.append(args)
        return _fake_proc(1, stderr="HTTP 504: 504 Gateway Timeout")

    monkeypatch.setattr(fap.subprocess, "run", fake_run)
    monkeypatch.setattr(fap.time, "sleep", lambda s: None)

    with pytest.raises(subprocess.CalledProcessError):
        fap._gh_json("pr", "list")
    assert len(calls) == fap.MAX_GH_ATTEMPTS, "all bounded attempts must be spent before raising"


def test_a_deterministic_failure_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retrying a 4xx only burns the job's 45-minute budget."""
    calls: list[Any] = []

    def fake_run(args: Any, **kw: Any) -> Any:
        calls.append(args)
        return _fake_proc(1, stderr="HTTP 401: Bad credentials (https://api.github.com/graphql)")

    monkeypatch.setattr(fap.subprocess, "run", fake_run)
    monkeypatch.setattr(fap.time, "sleep", lambda s: None)

    with pytest.raises(subprocess.CalledProcessError):
        fap._gh_json("pr", "list")
    assert len(calls) == 1, "a 401 is deterministic and must not be retried"


def test_a_pr_whose_state_cannot_be_read_never_reaches_ready_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail CLOSED: an unread statusCheckRollup reads as (False, False) = "green".

    Without this the split query would be a fail-open regression: a transient
    per-PR read failure would push a red-CI PR to ready_merge.
    """
    candidate = {
        "number": 77,
        "headRefName": "cursor/some-work",
        "baseRefName": "develop",
        "isCrossRepository": False,
        "isDraft": False,
        "createdAt": (datetime.now(UTC) - timedelta(hours=fap.MIN_AGE_HOURS + 1)).isoformat(),
    }
    monkeypatch.setattr(fap, "_list_agent_prs", lambda repo: [candidate])
    monkeypatch.setattr(fap, "_hydrate_pr", lambda repo, number: None)
    monkeypatch.setattr(fap, "_issue_labels", lambda repo, num: [])

    actions = fap.evaluate_all("digithings-ai/digithings", fetch_base=False)
    assert len(actions) == 1
    assert actions[0].state != "ready_merge", "unreadable state must never be merge-ready"
    assert actions[0].state == "needs_human"


def test_evaluate_all_merges_the_hydrated_fields_onto_the_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The split must not lose fields — a hydrated PR still classifies as before."""
    candidate = {
        "number": 78,
        "headRefName": "cursor/some-work",
        "baseRefName": "develop",
        "isCrossRepository": False,
        "isDraft": False,
        "createdAt": (datetime.now(UTC) - timedelta(hours=fap.MIN_AGE_HOURS + 1)).isoformat(),
    }
    heavy = {
        "title": "feat: a thing",
        "body": "Fixes #99",
        "labels": [],
        "mergeable": "MERGEABLE",
        "reviewRequests": [],
        "reviews": [],
        "statusCheckRollup": [{"name": "CI", "state": "SUCCESS", "conclusion": "SUCCESS"}],
    }
    monkeypatch.setattr(fap, "_list_agent_prs", lambda repo: [candidate])
    monkeypatch.setattr(fap, "_hydrate_pr", lambda repo, number: heavy)
    monkeypatch.setattr(fap, "_issue_labels", lambda repo, num: [])

    actions = fap.evaluate_all("digithings-ai/digithings", fetch_base=False)
    assert [a.state for a in actions] == ["ready_merge"], (
        "a hydrated green+linked+old PR must still reach ready_merge"
    )
