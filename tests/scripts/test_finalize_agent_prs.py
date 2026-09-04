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
    """Label simplification 2026-09 retired needs-human-review: it is inert now."""
    action = _evaluate(_pr(labels=[{"name": "needs-human-review"}]), monkeypatch)
    assert action.state == "ready_merge", f"got {action.state!r} — {action.reason}"


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
