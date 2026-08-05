"""Unit tests for scripts/check_review_coverage.py and its workflow wiring (#1846).

The gate exists because reviewing a *promotion* is the wrong moment and the wrong
price: a promotion diff is an accumulation of already-merged work (PR #1877 was 52
files and 12k lines), so it is the most expensive review Bugbot will quote and the
least actionable, since a finding there needs a fresh task PR plus another
promotion. This script asserts the cheaper invariant instead — every commit
reaching main was reviewed at its own task PR.

The branch that matters most is ``verdict_for`` refusing a ``NEUTRAL`` Bugbot
conclusion. ``neutral`` is what Cursor reports when the account hits its usage
limit, and on 2026-08-05 that happened on ten consecutive promotions. A gate that
counted neutral as a review would have passed every one of them while nothing had
been reviewed at all — the exact failure it is built to catch. Equally load-bearing
is that a label or a human approval always clears the gate, so an outage at Cursor
can never freeze a deploy.

The subject-parsing tests pin real commit subjects from this repository's history,
because the squash format ("subject (#1234)") is the only link a commit has back
to its pull request.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_review_coverage.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci-review-coverage.yml"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("check_review_coverage", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_review_coverage"] = module
    spec.loader.exec_module(module)
    return module


crc = _load()


# ── the verdict: what counts as reviewed ─────────────────────────────────────


def _state(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"labels": set(), "approvals": [], "bugbot": None, "title": ""}
    base.update(over)
    return base


def test_a_completed_bugbot_run_is_a_review() -> None:
    reviewed, why = crc.verdict_for(_state(bugbot="SUCCESS"))
    assert reviewed
    assert "Bugbot completed" in why


def test_a_neutral_bugbot_is_the_usage_limit_skip_and_is_not_a_review() -> None:
    """The whole reason this gate exists — see the module docstring."""
    reviewed, why = crc.verdict_for(_state(bugbot="NEUTRAL"))
    assert not reviewed
    assert "usage-limit" in why


@pytest.mark.parametrize("conclusion", ["FAILURE", "CANCELLED", "SKIPPED", "TIMED_OUT"])
def test_no_other_bugbot_conclusion_counts_either(conclusion: str) -> None:
    reviewed, _ = crc.verdict_for(_state(bugbot=conclusion))
    assert not reviewed


def test_a_human_approval_is_a_review() -> None:
    reviewed, why = crc.verdict_for(_state(approvals=["chrizefan"]))
    assert reviewed
    assert "chrizefan" in why


def test_the_risk_low_label_is_an_explicit_decision_to_skip() -> None:
    reviewed, why = crc.verdict_for(_state(labels={"risk:low", "component:website"}))
    assert reviewed
    assert "risk:low" in why


def test_a_label_clears_the_gate_even_when_bugbot_is_unavailable() -> None:
    """An outage at Cursor must never be able to freeze a deploy."""
    reviewed, _ = crc.verdict_for(_state(labels={"risk:low"}, bugbot="NEUTRAL"))
    assert reviewed


def test_nothing_at_all_is_not_a_review() -> None:
    reviewed, why = crc.verdict_for(_state())
    assert not reviewed
    assert "no completed Bugbot run" in why


def test_a_bot_approval_does_not_count_as_human() -> None:
    """cursor[bot] approving its own router pass is not a human reading the diff."""
    assert "cursor[bot]" in crc.BOT_AUTHORS


# ── linking a commit back to its pull request ────────────────────────────────


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("fix(website): two claims I wrote in #1891 do not hold (#1893)", 1893),
        ("chore(ci): retire the Copilot review request (#1894)", 1894),
        ("Merge pull request #1892 from digithings-ai/chore/promote-develop-to-main-28", 1892),
        ("chore(module/digichat): release digichat 0.6.0", None),
        ("wip: no pr here", None),
    ],
)
def test_parse_pr_number(subject: str, expected: int | None) -> None:
    assert crc.parse_pr_number(subject) == expected


def test_a_trailing_issue_reference_is_not_mistaken_for_the_pr() -> None:
    """ "in #1891" mid-subject must not win over the trailing "(#1893)"."""
    subject = "fix(website): two claims I wrote in #1891 do not hold (#1893)"
    assert crc.parse_pr_number(subject) == 1893


def test_merge_commits_are_detected_by_parent_count() -> None:
    assert crc.is_merge_commit("aaa bbb")
    assert not crc.is_merge_commit("aaa")


# ── workflow wiring: a gate that never runs gates nothing ────────────────────


def test_the_workflow_exists_and_only_guards_pull_requests_into_main() -> None:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses the bare key `on:` as the boolean True.
    triggers = spec.get("on") or spec.get(True)
    assert list(triggers) == ["pull_request"]
    assert triggers["pull_request"]["branches"] == ["main"]


def test_the_workflow_actually_invokes_the_script() -> None:
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/check_review_coverage.py" in body


def test_the_workflow_fetches_full_history() -> None:
    """The range walk needs history; a shallow clone would silently see nothing."""
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = next(iter(spec["jobs"].values()))["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0


def test_the_workflow_can_read_pull_requests() -> None:
    """`gh pr view` needs the scope, or every commit reads as unreviewed."""
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = next(iter(spec["jobs"].values()))
    assert job["permissions"]["pull-requests"] == "read"


def test_the_baseline_is_a_real_commit_and_pinned() -> None:
    assert crc.BASELINE_SHA
    assert len(crc.BASELINE_SHA) >= 7
