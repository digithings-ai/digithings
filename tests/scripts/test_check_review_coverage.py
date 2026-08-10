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

The subject-parsing tests pin real commit subjects from this repository's history.
Merge-style child commits retain their original subjects, so the gate falls back
to GitHub's commit-to-PR association for those commits.
"""

from __future__ import annotations

import importlib.util
import subprocess
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
    base: dict[str, Any] = {
        "labels": set(),
        "approvals": [],
        "bugbot": None,
        "title": "",
        "owner_review": None,
        "agent_review": None,
    }
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


# ── the reviewed:owner hatch ─────────────────────────────────────────────────
#
# Added because the gate's own first run had no honest hatch: a solo maintainer
# cannot self-approve, Bugbot was out of quota, and the only remaining option was
# to label a blocking CI change `risk:low`. A gate that pressures you into
# mislabelling is worse than no gate.


def test_reviewed_owner_is_a_review() -> None:
    reviewed, _ = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}))
    assert reviewed


def test_reviewed_owner_names_the_actor_and_date_not_just_the_label() -> None:
    """A self-applicable hatch is only worth having if it leaves a record."""
    reviewed, why = crc.verdict_for(
        _state(
            labels={crc.OWNER_REVIEW_LABEL},
            owner_review={"actor": "chrizefan", "at": "2026-08-05T18:00:00Z"},
        )
    )
    assert reviewed
    assert "chrizefan" in why
    assert "2026-08-05T18:00:00Z" in why


def test_reviewed_owner_still_clears_when_the_timeline_lookup_failed() -> None:
    """A GitHub API hiccup must not turn a real claim into a blocked deploy."""
    reviewed, why = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, owner_review=None))
    assert reviewed
    assert crc.OWNER_REVIEW_LABEL in why


def test_reviewed_owner_clears_the_gate_despite_a_neutral_bugbot() -> None:
    reviewed, _ = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, bugbot="NEUTRAL"))
    assert reviewed


def test_the_two_labels_are_distinct_and_report_distinct_reasons() -> None:
    """`risk:low` means it did not need reading; `reviewed:owner` means it was read.

    Conflating them is the failure mode the hatch exists to prevent, so the verdict
    strings must not be interchangeable.
    """
    assert crc.OWNER_REVIEW_LABEL != crc.SKIP_LABEL
    _, owner_why = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}))
    _, skip_why = crc.verdict_for(_state(labels={crc.SKIP_LABEL}))
    assert owner_why != skip_why
    assert "not to warrant" in skip_why


def test_a_completed_bugbot_run_outranks_a_self_applied_label() -> None:
    """Strongest evidence first: Bugbot is the one hatch nobody can self-grant."""
    _, why = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, bugbot="SUCCESS"))
    assert "Bugbot completed" in why


def test_an_approval_outranks_a_self_applied_label() -> None:
    _, why = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, approvals=["someone-else"]))
    assert "someone-else" in why


def test_a_bot_approval_does_not_count_as_human() -> None:
    """cursor[bot] approving its own router pass is not a human reading the diff."""
    assert "cursor[bot]" in crc.BOT_AUTHORS


# ── the reviewed:agent hatch (in-session review) ─────────────────────────────
#
# Every line in this repo is written by a coding agent, so an agent reviewing it is
# not weaker in kind than Bugbot — which is also an agent. What this hatch insists
# on is an ARTIFACT: the label without a posted findings comment is refused, so
# claiming it costs an actual review rather than a click.


def test_reviewed_agent_with_a_posted_review_is_a_review() -> None:
    reviewed, why = crc.verdict_for(
        _state(
            labels={crc.AGENT_REVIEW_LABEL},
            agent_review={
                "actor": "chrizefan",
                "at": "2026-08-05T22:00:00Z",
                "url": "https://github.com/o/r/pull/1#issuecomment-1",
            },
        )
    )
    assert reviewed
    assert "in-session review" in why
    assert "issuecomment-1" in why, "the verdict must link the findings, not just assert them"


def test_reviewed_agent_WITHOUT_the_comment_is_refused() -> None:
    """The whole point of this hatch: the label alone claims a review that never ran."""
    reviewed, why = crc.verdict_for(_state(labels={crc.AGENT_REVIEW_LABEL}, agent_review=None))
    assert not reviewed
    assert crc.AGENT_REVIEW_MARKER in why


def test_reviewed_agent_clears_a_neutral_bugbot() -> None:
    """The case this exists for — Bugbot out of quota, so review happened in session."""
    reviewed, _ = crc.verdict_for(
        _state(
            labels={crc.AGENT_REVIEW_LABEL},
            bugbot="NEUTRAL",
            agent_review={"actor": "a", "at": "t", "url": "u"},
        )
    )
    assert reviewed


def test_a_completed_bugbot_run_outranks_an_in_session_review() -> None:
    _, why = crc.verdict_for(
        _state(
            labels={crc.AGENT_REVIEW_LABEL},
            bugbot="SUCCESS",
            agent_review={"actor": "a", "at": "t", "url": "u"},
        )
    )
    assert "Bugbot completed" in why


def test_the_three_self_served_hatches_are_distinct_labels() -> None:
    assert len({crc.AGENT_REVIEW_LABEL, crc.OWNER_REVIEW_LABEL, crc.SKIP_LABEL}) == 3


def test_a_missing_agent_review_does_not_block_the_other_hatches() -> None:
    """A PR with risk:low and no agent label must not be dragged into the new branch."""
    reviewed, _ = crc.verdict_for(_state(labels={crc.SKIP_LABEL}, agent_review=None))
    assert reviewed


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


def test_unnumbered_commit_uses_its_merged_github_pr_association(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merge-style PR child commits do not carry ``(#1234)`` in their subjects."""
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(
        crc,
        "_gh_json",
        lambda _args: [
            {"number": 1900, "merged_at": None},
            {"number": 1899, "merged_at": "2026-08-05T19:51:00Z"},
        ],
    )

    assert crc.associated_pr_number("a7bf7721") == 1899


def test_open_promotion_pr_does_not_legitimize_a_direct_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only an already-merged source PR can supply review evidence."""
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(
        crc,
        "_gh_json",
        lambda _args: [{"number": 1900, "merged_at": None}],
    )

    assert crc.associated_pr_number("direct123") is None


def test_github_association_failure_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient API failure must not crash or approve an unlinked commit."""
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")

    def fail(_args: list[str]) -> list[dict[str, Any]]:
        raise subprocess.CalledProcessError(1, "gh api")

    monkeypatch.setattr(crc, "_gh_json", fail)

    assert crc.associated_pr_number("unknown123") is None


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
