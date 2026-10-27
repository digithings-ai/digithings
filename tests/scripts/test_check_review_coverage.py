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

import ast
import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest
import yaml

pytestmark = pytest.mark.unit

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
        "agent_tool": [],
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


def test_the_retired_risk_low_label_no_longer_clears_the_gate() -> None:
    """Label simplification 2026-09 retired risk:*. The label is inert now."""
    reviewed, _ = crc.verdict_for(_state(labels={"risk:low", "component:website"}))
    assert not reviewed


def test_a_label_clears_the_gate_even_when_bugbot_is_unavailable() -> None:
    """An outage at Cursor must never be able to freeze a deploy."""
    reviewed, _ = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, bugbot="NEUTRAL"))
    assert reviewed


def test_nothing_at_all_is_not_a_review() -> None:
    reviewed, why = crc.verdict_for(_state())
    assert not reviewed
    assert "no completed agent review" in why


def test_a_marker_comment_without_the_label_names_the_missing_label() -> None:
    """A near miss must not be reported as "no review at all".

    On 2026-10-27 the promotion gate said "no completed agent review (… in-session)"
    about PRs that *did* carry an in-session review comment and were missing only
    the label that accepts it. The operator read that as a broken detector, went
    looking for a bug that was not there, and only found the real gap by reading
    the source. The refusal has to name the one thing left to do.
    """
    reviewed, why = crc.verdict_for(
        _state(
            agent_review={
                "actor": "chrizefan",
                "at": "2026-10-27T00:00:00Z",
                "url": "https://github.com/digithings-ai/digithings/pull/1#c",
            }
        )
    )
    assert not reviewed
    assert "in-session review comment exists" in why
    assert crc.AGENT_REVIEW_LABEL in why
    assert "no completed agent review" not in why


def test_an_unreadable_review_index_is_loud_and_still_fails_closed(monkeypatch, capsys) -> None:
    """Failing closed is right; failing silently is not.

    `_sha_mentioned_in` is discovery for the direct-push hatch. When the search
    index cannot be read it returns nothing, and the caller then reports "no
    review exists" — a different and much more misleading claim than "could not
    look". The warning has to make that distinction visible.
    """

    def _boom(*_args: object, **_kwargs: object) -> dict:
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(crc, "_gh_json", _boom)
    assert crc._sha_mentioned_in("abc1234") == []
    err = capsys.readouterr().err
    assert "search/issues unavailable" in err
    assert "could not look" in err


# ── the reviewed:owner hatch ─────────────────────────────────────────────────
#
# Added because the gate's own first run had no honest hatch: a solo maintainer
# cannot self-approve, and with Bugbot out of quota there was no satisfiable
# claim that left a record. A gate that pressures you into a silent bypass is
# worse than no gate. (A risk:low skip hatch existed until the 2026-09 label
# simplification retired it; trivial diffs now clear via reviewed:owner.)


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


def test_the_owner_hatch_reports_actor_and_date() -> None:
    """The self-applicable hatch is only worth having if it leaves a record."""
    _, owner_why = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}))
    _, bare_why = crc.verdict_for(_state())
    assert owner_why != bare_why


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
    assert "cursor[bot]" not in crc.REVIEW_BOTS
    assert "cursor" not in crc.REVIEW_BOTS


def test_gh_pr_view_bare_coderabbit_login_is_recognized() -> None:
    """``gh pr view --json`` returns ``coderabbitai`` without the ``[bot]`` suffix."""
    assert "coderabbitai" in crc.REVIEW_BOTS
    assert "coderabbitai[bot]" in crc.REVIEW_BOTS
    assert "coderabbitai" in crc.CODERABBIT_LOGINS
    reviewed, why = crc.verdict_for(_state(agent_tool=[{"bot": "coderabbitai", "via": "review"}]))
    assert reviewed
    assert "coderabbitai" in why


# ── agent-tool reviews (CodeRabbit, Claude, other PR-review bots) ────────────
#
# The gate exists to prove a review *loop* ran, not that a specific vendor ran
# it. A completed CodeRabbit / Claude / Copilot review is the same kind of
# artifact as Bugbot. A skip, rate-limit, or "PR is closed" failure is not.


def test_a_coderabbit_submitted_review_is_a_review() -> None:
    reviewed, why = crc.verdict_for(
        _state(agent_tool=[{"bot": "coderabbitai[bot]", "via": "review"}])
    )
    assert reviewed
    assert "coderabbitai[bot]" in why


def test_a_coderabbit_status_check_success_is_a_review() -> None:
    reviewed, why = crc.verdict_for(_state(agent_tool=[{"bot": "CodeRabbit", "via": "check"}]))
    assert reviewed
    assert "CodeRabbit" in why


def test_a_claude_code_review_check_success_is_a_review() -> None:
    reviewed, why = crc.verdict_for(
        _state(agent_tool=[{"bot": "Claude /code-review", "via": "check"}])
    )
    assert reviewed
    assert "Claude /code-review" in why


def test_github_code_quality_review_is_a_review() -> None:
    reviewed, why = crc.verdict_for(
        _state(agent_tool=[{"bot": "github-code-quality[bot]", "via": "review"}])
    )
    assert reviewed
    assert "github-code-quality[bot]" in why


def test_agent_tool_review_outranks_self_applied_labels() -> None:
    _, why = crc.verdict_for(
        _state(
            labels={crc.OWNER_REVIEW_LABEL},
            agent_tool=[{"bot": "coderabbitai[bot]", "via": "review"}],
        )
    )
    assert "coderabbitai[bot]" in why


def test_human_approval_outranks_an_agent_tool_review() -> None:
    _, why = crc.verdict_for(
        _state(
            approvals=["chrizefan"],
            agent_tool=[{"bot": "coderabbitai[bot]", "via": "review"}],
        )
    )
    assert "chrizefan" in why


def test_coderabbit_walkthrough_comment_is_a_completed_review() -> None:
    body = (
        "<!-- This is an auto-generated comment: summarize by coderabbit.ai -->\n"
        "<!-- walkthrough_start -->\nWalkthrough\n"
    )
    assert crc.coderabbit_comment_is_completed_review(body)


def test_coderabbit_no_actionable_comments_is_a_completed_review() -> None:
    body = (
        "<!-- recent_review_start -->\n"
        "No actionable comments were generated in the recent review. 🎉\n"
    )
    assert crc.coderabbit_comment_is_completed_review(body)


def test_coderabbit_rate_limit_is_not_a_review() -> None:
    body = (
        "<!-- This is an auto-generated comment: rate limited by coderabbit.ai -->\n"
        "> [!WARNING]\n> ## Review limit reached\n"
        "<!-- recent_review_start -->\n"
    )
    assert not crc.coderabbit_comment_is_completed_review(body)


def test_coderabbit_review_failed_because_pr_closed_is_not_a_review() -> None:
    body = (
        "<!-- This is an auto-generated comment: failure by coderabbit.ai -->\n"
        "> [!CAUTION]\n> ## Review failed\n> The pull request is closed.\n"
        "<!-- recent_review_start -->\nReviewing files that changed\n"
    )
    assert not crc.coderabbit_comment_is_completed_review(body)


def test_pr_review_state_counts_a_coderabbit_comment_and_submitted_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gh(args: list[str]) -> dict[str, Any]:
        assert "comments" in args[-1]
        return {
            "title": "fix",
            "labels": [],
            "reviews": [
                {
                    "author": {"login": "coderabbitai[bot]"},
                    "state": "COMMENTED",
                    "body": "findings",
                }
            ],
            "comments": [
                {
                    "author": {"login": "coderabbitai[bot]"},
                    "body": ("<!-- walkthrough_start -->\nWalkthrough of the diff\n"),
                }
            ],
            "statusCheckRollup": [],
        }

    monkeypatch.setattr(crc, "_gh_json", fake_gh)
    state = crc._pr_review_state(2510)
    reviewed, why = crc.verdict_for(state)
    assert reviewed
    assert "coderabbitai" in why


def test_pr_review_state_counts_bare_coderabbit_login_from_gh_pr_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: #2561 merged then still failed coverage because logins lacked [bot]."""

    def fake_gh(args: list[str]) -> dict[str, Any]:
        return {
            "title": "chore",
            "labels": [],
            "reviews": [
                {
                    "author": {"login": "coderabbitai"},
                    "state": "COMMENTED",
                    "body": "findings",
                }
            ],
            "comments": [
                {
                    "author": {"login": "coderabbitai"},
                    "body": (
                        "<!-- recent_review_start -->\n"
                        "No actionable comments were generated in the recent review.\n"
                    ),
                }
            ],
            "statusCheckRollup": [],
        }

    monkeypatch.setattr(crc, "_gh_json", fake_gh)
    state = crc._pr_review_state(2557)
    reviewed, why = crc.verdict_for(state)
    assert reviewed
    assert "coderabbitai" in why
    assert state["agent_tool"], "bare login must populate agent_tool"


def test_pr_review_state_ignores_a_coderabbit_rate_limit_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gh(args: list[str]) -> dict[str, Any]:
        return {
            "title": "fix",
            "labels": [],
            "reviews": [],
            "comments": [
                {
                    "author": {"login": "coderabbitai[bot]"},
                    "body": (
                        "<!-- This is an auto-generated comment: "
                        "rate limited by coderabbit.ai -->\n"
                        "## Review limit reached\n"
                    ),
                }
            ],
            "statusCheckRollup": [{"name": "CodeRabbit", "conclusion": ""}],
        }

    monkeypatch.setattr(crc, "_gh_json", fake_gh)
    state = crc._pr_review_state(2544)
    reviewed, _ = crc.verdict_for(state)
    assert not reviewed


def test_pr_review_state_counts_coderabbit_check_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_gh(args: list[str]) -> dict[str, Any]:
        return {
            "title": "fix",
            "labels": [],
            "reviews": [],
            "comments": [],
            "statusCheckRollup": [{"name": "CodeRabbit", "conclusion": "SUCCESS"}],
        }

    monkeypatch.setattr(crc, "_gh_json", fake_gh)
    state = crc._pr_review_state(1)
    reviewed, why = crc.verdict_for(state)
    assert reviewed
    assert "CodeRabbit" in why


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


def test_the_two_self_served_hatches_are_distinct_labels() -> None:
    assert len({crc.AGENT_REVIEW_LABEL, crc.OWNER_REVIEW_LABEL}) == 2


def test_a_missing_agent_review_does_not_block_the_other_hatches() -> None:
    """A PR with reviewed:owner and no agent review must clear via the owner hatch."""
    reviewed, _ = crc.verdict_for(_state(labels={crc.OWNER_REVIEW_LABEL}, agent_review=None))
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


def test_a_trailing_issue_number_that_is_not_a_real_pr_falls_back_to_association(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "docs: foo (#2103)" citing issue #2103 must not crash the gate.

    `parse_pr_number` cannot tell a squash-merge PR reference apart from a
    commit subject that cites an issue in the same "(#N)" shape. `gh pr view`
    on a number that isn't a real PR raises -- this pins that
    `resolve_pr_number` catches it and falls back to the real commit -> PR
    association instead of propagating the crash.
    """
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")

    def fake_pr_view(number: int) -> dict[str, Any]:
        raise subprocess.CalledProcessError(1, "gh pr view", output=b"", stderr=b"not a PR")

    monkeypatch.setattr(crc, "_pr_review_state", fake_pr_view)
    monkeypatch.setattr(crc, "associated_pr_number", lambda _sha: 2106)

    resolved = crc.resolve_pr_number(
        "docs: DigiChat language selector design (#2103)", "abc123", {}
    )
    assert resolved == 2106


def test_a_second_commit_citing_the_same_bogus_number_does_not_re_attempt_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Several commits can cite the same non-PR "(#N)" (e.g. a whole PR's worth of
    commits referencing one tracking issue) -- the second one must not re-run the
    failing `gh pr view` call `resolve_pr_number` already paid for once."""
    attempts: list[int] = []

    def fake_pr_view(number: int) -> dict[str, Any]:
        attempts.append(number)
        raise subprocess.CalledProcessError(1, "gh pr view")

    monkeypatch.setattr(crc, "_pr_review_state", fake_pr_view)
    monkeypatch.setattr(crc, "associated_pr_number", lambda _sha: None)

    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.resolve_pr_number("docs: plan (#2103)", "sha1", cache, invalid)
    crc.resolve_pr_number("docs: design (#2103)", "sha2", cache, invalid)

    assert attempts == [2103], "the second commit's lookup should be memoized, not re-attempted"


def test_a_real_squash_merge_pr_number_is_cached_and_not_re_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common case: a genuine squash-merge "(#N)" resolves without falling back."""
    calls: list[int] = []

    def fake_pr_view(number: int) -> dict[str, Any]:
        calls.append(number)
        return _state()

    monkeypatch.setattr(crc, "_pr_review_state", fake_pr_view)
    monkeypatch.setattr(
        crc,
        "associated_pr_number",
        lambda _sha: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    cache: dict[int, dict[str, Any]] = {}
    resolved = crc.resolve_pr_number(
        "chore(ci): retire the Copilot review request (#1894)", "def456", cache
    )
    assert resolved == 1894
    assert calls == [1894]
    assert 1894 in cache

    # A second, unrelated commit citing the same PR number (e.g. a merge-commit
    # child) must reuse the cached state rather than re-fetching it.
    resolved_again = crc.resolve_pr_number(
        "chore(ci): retire the Copilot review request (#1894)", "ghi789", cache
    )
    assert resolved_again == 1894
    assert calls == [1894], "the second lookup should hit the cache, not gh pr view again"


# ── workflow wiring: a gate that never runs gates nothing ────────────────────
#
# The gate is also dispatchable (#5934): a promotion can be re-gated on its exact
# head without pushing a no-op commit, because a user-posted commit status does
# not satisfy main's branch protection (the context is scoped to the Actions
# app). That entry point is safe only while three things hold, and each is
# asserted here rather than described in a comment:
#
#  - the pull_request path still gates pull requests into main, and nothing else
#    can start the workflow;
#  - a dispatch supplies its own head and base, so the head is required (a
#    default would silently gate a stale commit) and the base defaults to main;
#  - two dispatch-only guards fail closed BEFORE the gate script runs: the
#    dispatched head must be the commit the run checks (the status attaches to
#    github.sha, not to the input), and the base must be main (any other base can
#    yield an empty range, which the script treats as "nothing to promote").


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(spec: dict[str, Any]) -> dict[str, Any]:
    # PyYAML parses the bare key `on:` as the boolean True.
    return spec.get("on") or spec.get(True)


def _steps() -> list[dict[str, Any]]:
    return next(iter(_workflow()["jobs"].values()))["steps"]


def _step(name: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(_steps()):
        if step.get("name") == name:
            assert "run" in step, f"`{name}` is no longer a script: {step}"
            return index, step
    raise AssertionError(f"no step named `{name}` in the gate job — update this test")


DISPATCH_GUARD = "Refuse a dispatch that would gate the wrong range"
COVERAGE_STEP = "Check review coverage of the promotion range"


def test_the_pull_request_trigger_still_only_guards_pull_requests_into_main() -> None:
    triggers = _triggers(_workflow())
    assert triggers["pull_request"] == {"branches": ["main"]}
    assert set(triggers) == {"pull_request", "workflow_dispatch"}, (
        "the gate may also be dispatched on a promotion head (#5934); no other "
        "trigger may start it, and neither of the two may be dropped"
    )


def test_the_dispatch_entry_point_requires_a_head_and_pins_the_base_to_main() -> None:
    inputs = _triggers(_workflow())["workflow_dispatch"]["inputs"]
    assert inputs["head_sha"]["required"] is True
    assert "default" not in inputs["head_sha"], (
        "a defaulted head would gate a stale commit on any dispatch that omits it"
    )
    assert inputs["base_ref"]["required"] is True
    assert inputs["base_ref"]["default"] == "main"


def test_the_dispatch_guard_runs_only_on_a_dispatch_and_checks_what_the_gate_reads() -> None:
    """A guard over different variables than the script uses would check nothing."""
    guard_index, guard = _step(DISPATCH_GUARD)
    coverage_index, coverage = _step(COVERAGE_STEP)

    assert guard["if"] == "github.event_name == 'workflow_dispatch'"
    assert guard["env"] == {
        "HEAD_SHA": "${{ inputs.head_sha }}",
        "CHECKED_SHA": "${{ github.sha }}",
        "BASE_REF": "${{ inputs.base_ref }}",
    }
    # On a dispatch run there is no pull_request payload, so the gate script reads
    # exactly the two inputs the guard just checked. Pin that wiring: a guard
    # reading one value while the script uses another is a guard on nothing.
    assert coverage["env"]["HEAD_SHA"] == (
        "${{ inputs.head_sha || github.event.pull_request.head.sha }}"
    )
    assert coverage["env"]["BASE_REF"] == "${{ inputs.base_ref || github.base_ref }}"
    assert guard_index < coverage_index, (
        "the guard must refuse a wrong range before the gate script grades it"
    )


def _run_guard(*, head: str, checked: str, base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-c", _step(DISPATCH_GUARD)[1]["run"]],
        capture_output=True,
        text=True,
        env={
            "HEAD_SHA": head,
            "CHECKED_SHA": checked,
            "BASE_REF": base,
            "PATH": "/usr/bin:/bin",
        },
        timeout=30,
    )


def test_the_dispatch_guard_admits_the_exact_promotion_head_on_main() -> None:
    result = _run_guard(head="a" * 40, checked="a" * 40, base="main")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("head", ["b" * 40, ""])
def test_the_dispatch_guard_refuses_a_head_the_status_would_not_attach_to(
    head: str,
) -> None:
    """The status attaches to github.sha; gating another SHA lands green elsewhere."""
    checked = "a" * 40
    result = _run_guard(head=head, checked=checked, base="main")
    assert result.returncode != 0
    out = result.stdout + result.stderr
    assert "is not the commit this run checks" in out
    assert checked in out


@pytest.mark.parametrize("base", ["develop", "", "main ", "refs/heads/main"])
def test_the_dispatch_guard_refuses_any_base_but_literal_main(base: str) -> None:
    """Any other base can make the range empty, which the script passes."""
    result = _run_guard(head="a" * 40, checked="a" * 40, base=base)
    assert result.returncode != 0, f"base {base!r} must be refused"
    assert "base_ref must be main" in result.stdout + result.stderr


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


def test_the_baseline_is_actually_an_ancestor_of_both_branch_tips() -> None:
    """A baseline that isn't on develop's own history skips nothing there.

    Caught a real mistake with this: an earlier attempt to advance
    BASELINE_SHA past a squash-merge landed a value that was an ancestor of
    origin/main but NOT of origin/develop, making the move a no-op for the
    develop -> main direction this gate actually checks. Pin the property
    directly instead of trusting a comment to describe it correctly.

    Skips (rather than fails) when a ref can't be resolved at all -- e.g. a
    shallow or partial clone that never fetched one of these branches -- since
    that's an environment limitation, not a claim about BASELINE_SHA itself.
    The same hatch applies when BASELINE_SHA itself is missing from the object
    database of a shallow clone: ``git merge-base --is-ancestor`` then exits 128
    with ``fatal: Not a valid object name``, which is what ``ruff-and-scripts``
    on ``ci.yml`` (default fetch-depth 1) reported against ``origin/main``.
    A full clone with a bad pin still fails: the skip is gated on
    ``git rev-parse --is-shallow-repository``.
    """
    for ref in ("origin/main", "origin/develop"):
        resolvable = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=crc.REPO_ROOT,
            capture_output=True,
        )
        if resolvable.returncode != 0:
            pytest.skip(f"{ref} is not resolvable in this checkout")

        baseline_present = subprocess.run(
            ["git", "cat-file", "-e", f"{crc.BASELINE_SHA}^{{commit}}"],
            cwd=crc.REPO_ROOT,
            capture_output=True,
        )
        if baseline_present.returncode != 0:
            shallow = subprocess.run(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=crc.REPO_ROOT,
                capture_output=True,
                text=True,
            )
            if shallow.returncode == 0 and shallow.stdout.strip() == "true":
                pytest.skip(
                    "BASELINE_SHA is not in this clone's object database "
                    "(shallow checkout — ci.yml ruff-and-scripts uses default fetch-depth 1)"
                )
            pytest.fail(
                f"BASELINE_SHA {crc.BASELINE_SHA} is not a valid commit object in a full clone"
            )

        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", crc.BASELINE_SHA, ref],
            cwd=crc.REPO_ROOT,
            capture_output=True,
        )
        assert result.returncode == 0, f"BASELINE_SHA is not an ancestor of {ref}"


def test_ancestor_pin_treats_a_missing_baseline_object_as_environment() -> None:
    """Shallow clones must skip; a full clone with a bad pin must still fail."""
    src = Path(__file__).read_text(encoding="utf-8")
    assert '["git", "cat-file", "-e"' in src
    assert "--is-shallow-repository" in src
    assert "pytest.fail" in src


# ── one bot rule at the approvals sink (DIG-4298, 2026-10-19) ────────────────
#
# `_evidence_reviews` (the queue) and this sink used to filter bots differently:
# the queue stripped `[bot]`-suffix approvals, the sink only three named logins,
# and both missed a bare-login bot (the shape `gh --json` actually returns). One
# predicate, `is_bot_login`, now classifies for both; these tests pin it at the
# sink through `verdict_for`, the only way a verdict can pick a bot up.


def _sink(reviews: list[dict[str, Any]]) -> tuple[dict[str, Any], bool, str]:
    """Run `_apply_reviews_checks_comments` exactly the way both gates call it."""
    state = _state()
    crc._apply_reviews_checks_comments(state, reviews=reviews, checks=[], comments=[])
    reviewed, why = crc.verdict_for(state)
    return state, reviewed, why


def test_an_unlisted_bots_bare_login_approval_never_reaches_the_approvals_sink() -> None:
    """The DIG-4298 hole: an unlisted bot, bare login, APPROVED — refused.

    `gh` sends the record, not the polite spelling: bare login plus `is_bot`.
    The login alone (`flaky-lint`) is indistinguishable from a person's, so only
    the record can say bot — and the sink must not count the review as an
    approval. Refusal is what `_gate_review_coverage` then sees.
    """
    state, reviewed, why = _sink(
        [{"author": {"login": "flaky-lint", "is_bot": True}, "state": "APPROVED"}]
    )
    assert not reviewed
    assert "no approval" in why

    # The queue routes the SAME reviews list into this sink (`_gate_review_
    # coverage` calls it directly on `_evidence_reviews`' pass-through), so the
    # sink-side verdict is the one both gates grade; the merge-queue suite runs
    # `_evidence_reviews` itself and refuses this shape there too.
    state = _state()
    crc._apply_reviews_checks_comments(
        state,
        reviews=[{"author": {"login": "flaky-lint", "is_bot": True}, "state": "APPROVED"}],
        checks=[],
        comments=[],
    )
    assert state["approvals"] == []
    assert state["agent_tool"] == []
    reviewed, _ = crc.verdict_for(state)
    assert not reviewed


def test_an_unlisted_suffixed_bot_approval_is_not_an_approval_either() -> None:
    """Any `[bot]` suffix is a bot designation whether or not the sink lists the
    login: `netlify[bot]` is in neither REVIEW_BOTS nor BOT_AUTHORS, so the
    2026-10-18 sink would have counted it as a person's approval. Nothing picks
    its review up as agent evidence, so on its own the shape is refused."""
    state, reviewed, why = _sink([{"author": {"login": "netlify[bot]"}, "state": "APPROVED"}])
    assert state["approvals"] == []
    assert state["agent_tool"] == []
    assert not reviewed
    assert "no approval" in why


def test_the_graphql_batch_catches_an_unlisted_bare_bot_the_same_way() -> None:
    """`is_bot_login` must classify GraphQL records too — the batched fetch is
    what the promotion range actually runs, and it carries `__typename`."""
    state = crc.state_from_graphql_pr(
        _graphql_pr(
            reviews=[
                {"author": {"login": "flaky-lint", "__typename": "Bot"}, "state": "APPROVED"},
            ]
        )
    )
    assert state["approvals"] == []
    reviewed, _ = crc.verdict_for(state)
    assert not reviewed
    counts = crc.state_from_graphql_pr(
        _graphql_pr(
            reviews=[
                {"author": {"login": "flaky-lint", "__typename": "User"}, "state": "APPROVED"},
            ]
        )
    )
    assert counts["approvals"] == ["flaky-lint"]
    reviewed, why = crc.verdict_for(counts)
    assert reviewed
    assert "approved by flaky-lint" in why


def test_the_batch_query_asks_for_the_review_authors_typename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No test executes `_pr_batch_query`, and a malformed reviews field would
    only fail at runtime — so pin the shape here instead: the review author has
    to carry `__typename`, or the batched path loses its bot signal and an
    unlisted bare bot's approval sneaks past the sink on promotion runs.
    (The REST fallback keeps classifying via `is_bot`/`type`, so the degradation
    is quiet rather than loud — which is exactly why the query is pinned.)"""
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    query = crc._pr_batch_query([1894, 1893])
    assert "reviews(last: 80) { nodes { state author { login __typename } } }" in query


def test_the_batch_query_asks_for_the_contexts_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin the one query form GitHub accepts.

    `StatusCheckRollup` is an OBJECT with the fields `commit`, `contexts`,
    `id` and `state`; it has no `nodes` field (`undefinedField, fieldName
    nodes, typeName StatusCheckRollup`). Its `contexts` field is a
    `StatusCheckRollupContextConnection` whose `nodes` are the union
    `StatusCheckRollupContext = CheckRun | StatusContext`, so the query must
    ask for `contexts(first: N) { nodes { ... } }` and spread the fragments
    inside `nodes`. Both wrong forms shipped at some point and neither was
    caught, because a rejected query exits 1 and the REST fallback answered
    in its place.
    """
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    query = " ".join(crc._pr_batch_query([1894]).split())
    assert "statusCheckRollup {" in query
    assert "contexts(first: 100) { nodes {" in query
    assert "statusCheckRollup { nodes" not in query
    # A bare `contexts {` has no pagination boundary, and the fragments cannot
    # be spread on the connection itself -- both are `undefinedField` /
    # `cannotSpreadFragment` at GitHub.
    assert "contexts {" not in query


def test_the_parsed_check_list_is_not_empty_for_a_pr_with_a_known_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reader must find the checks GitHub actually sends.

    `statusCheckRollup` is an object whose `contexts` connection carries the
    checks. Reading `nodes` off the object returns an empty list for every
    real PR, so the bot-check arms could never fire -- and the old fixture
    agreed with the broken reader, so no test noticed. This is the check that
    was missing: a PR with a known check must yield a NON-EMPTY list.

    It is asserted through the PUBLIC path (`prefetch_pr_states` -> the state
    it caches), not through a private helper name: a test pinned to a helper
    that the next refactor renames fails for a typo reason, not a behaviour
    reason, and says nothing about the gate.
    """

    def fake_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del query, variables
        return {
            "data": {
                "repository": {
                    "p6047": _graphql_pr(
                        number=6047,
                        checks=[
                            {"name": "CodeRabbit", "conclusion": "SUCCESS"},
                            {"context": "local-ci", "state": "PENDING"},
                        ],
                    )
                }
            }
        }

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", fake_graphql)
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([6047], cache, invalid)
    assert 6047 in cache, "the PR must not be reported as invalid"
    checks = cache[6047]["checks"]
    assert checks, "the parsed check list must not be empty for a PR with a known check"
    assert {c.get("name") or c.get("context") for c in checks} == {"CodeRabbit", "local-ci"}


def test_the_bot_check_arms_fire_off_a_graphql_pr() -> None:
    """Arm 1 (Bugbot) and arm 3 (CodeRabbit / Claude) must clear the gate
    through the GraphQL path — not only through the REST fallback."""
    bugbot = crc.state_from_graphql_pr(
        _graphql_pr(checks=[{"name": "Cursor Bugbot", "conclusion": "SUCCESS"}])
    )
    reviewed, why = crc.verdict_for(bugbot)
    assert reviewed, why
    assert "Cursor Bugbot completed" in why

    coderabbit = crc.state_from_graphql_pr(
        _graphql_pr(checks=[{"name": "CodeRabbit", "conclusion": "SUCCESS"}])
    )
    reviewed, why = crc.verdict_for(coderabbit)
    assert reviewed, why
    assert "agent review by CodeRabbit" in why


def test_a_rejected_graphql_query_is_reported_and_still_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A query GitHub rejects must not vanish.

    `gh api graphql` exits 1 when the response carries errors, so a broken
    query used to raise, fall back to REST, and leave the caller none the
    wiser -- while printing one error line per alias of the rejected chunk
    (25 for a 25-alias chunk) that nobody read. The fallback stays; it now
    says so, once, naming the cause.

    This test drives the diagnostic from a synthetic exception. The capture
    itself, and the real `_gh_graphql`, are covered by
    `test_the_graphql_stderr_is_captured_not_inherited`.
    """

    def boom(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del query, variables
        raise subprocess.CalledProcessError(
            1,
            ["gh", "api", "graphql"],
            "",
            "gh: Field 'nodes' doesn't exist on type 'StatusCheckRollup'",
        )

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", boom)
    monkeypatch.setattr(
        crc,
        "_pr_review_state",
        lambda number: {
            "labels": set(),
            "approvals": [],
            "bugbot": None,
            "title": "",
            "owner_review": None,
            "agent_tool": [],
            "agent_review": None,
        },
    )
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([1894], cache, invalid)
    assert 1894 in cache, "the REST fallback must still answer"
    err = capsys.readouterr().err
    assert "GraphQL" in err
    assert "doesn't exist on type 'StatusCheckRollup'" in err


_REJECTED_QUERY_STDERR = "gh: Field 'nodes' doesn't exist on type 'StatusCheckRollup'"


def _gh_that_rejects_graphql(tmp_path: Path) -> Path:
    """A `gh` stub that rejects a GraphQL query the way GitHub does.

    It writes to stderr and exits non-zero, which is exactly how `gh api
    graphql` reports a query the schema refuses. The stub is a real program
    on the PATH, so the test exercises the real `subprocess.run` -- a
    monkeypatched `subprocess.run` would only prove that the fake it was
    handed behaves as the fake behaves.
    """
    stub = tmp_path / "gh"
    stub.write_text(f"#!/bin/sh\necho \"{_REJECTED_QUERY_STDERR}\" >&2\nexit 1\n")
    stub.chmod(0o755)
    return stub


def test_the_graphql_stderr_is_captured_not_inherited(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The capture is the point of this change, so it needs a test of its own.

    Every other test in this file monkeypatched `_gh_graphql` wholesale, so
    `subprocess.run(..., capture_output=True)` never ran: reverting
    `_gh_graphql` to the form it had before this change left the suite
    byte-identical. This one lets the REAL `_gh_graphql` run against a `gh`
    stub that rejects the query, and pins three things:

    - the stderr is CAPTURED, so it never reaches the terminal;
    - it rides on the exception, where the fallback can name it;
    - the exception names the command that failed, `gh` included.
    """
    _gh_that_rejects_graphql(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    with pytest.raises(subprocess.CalledProcessError) as caught:
        crc._gh_graphql("query { repository { pullRequest { number } } }")

    error = caught.value
    assert _REJECTED_QUERY_STDERR in (error.stderr or "")
    assert error.cmd[0] == "gh", "the failing command must name gh"
    assert error.returncode == 1
    assert _REJECTED_QUERY_STDERR not in capfd.readouterr().err, (
        "the stderr must be captured, not printed to the terminal"
    )


def test_a_rejected_query_names_the_cause_once_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The real `_gh_graphql`, the real fallback, one line naming the cause.

    The point of the capture is that a human reading the log learns WHY the
    gate fell back to REST. So the whole path runs: the real `_gh_graphql`
    against a `gh` stub that rejects the query, the fallback, and the
    diagnostic -- which must name the cause exactly once, not once per alias
    and not once per chunk.
    """
    _gh_that_rejects_graphql(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(
        crc,
        "_pr_review_state",
        lambda number: {
            "labels": set(),
            "approvals": [],
            "bugbot": None,
            "title": "",
            "owner_review": None,
            "agent_tool": [],
            "agent_review": None,
        },
    )
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([1894], cache, invalid)
    assert 1894 in cache, "the REST fallback must still answer"

    err = capfd.readouterr().err
    assert err.count("the batched GraphQL query failed") == 1, (
        f"the fallback must say so once, not once per alias: {err!r}"
    )
    assert _REJECTED_QUERY_STDERR in err


def test_the_commit_lookup_fallback_names_the_cause_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The commit-lookup fallback has to say so too, and only once.

    `prefetch_associated_prs` is the second GraphQL path, and its fallback
    was just as silent as the first one. It now names the cause, once, for
    the whole call -- the chunk loop is inside one try, so one rejected chunk
    is one line.
    """
    _gh_that_rejects_graphql(tmp_path)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "associated_pr_number", lambda sha: None)

    found = crc.prefetch_associated_prs(["a" * 40, "b" * 40])
    assert found == {"a" * 40: None, "b" * 40: None}

    err = capfd.readouterr().err
    assert err.count("the batched GraphQL commit lookup failed") == 1, (
        f"the fallback must say so once for the whole call: {err!r}"
    )
    assert _REJECTED_QUERY_STDERR in err


def test_a_persons_approval_survives_the_bot_rule() -> None:
    """The rule exists to refuse bots, never to doubt a person: `is_bot: false`
    (what `gh` sends for every human account) keeps the approval countable."""
    state, reviewed, why = _sink(
        [{"author": {"login": "reviewer", "is_bot": False}, "state": "APPROVED"}]
    )
    assert state["approvals"] == ["reviewer"]
    assert reviewed
    assert "approved by reviewer" in why


def test_a_listed_reviewer_bots_approval_is_agent_evidence_in_both_spellings() -> None:
    """CodeRabbit's approvals keep counting — through the `REVIEW_BOTS` hatch.

    Excluding bot logins from `approvals` was the DIG-4298 fix; had it been done
    by stripping them out of the evidence list (`_evidence_reviews`' old suffix
    strip), a legitimate CodeRabbit pass would have stopped counting at all, and
    the suffixed spelling already disagreed with the bare one inside one gate:
    `coderabbitai` counted as a person's approval, `coderabbitai[bot]` as no
    evidence. One rule at the sink, identical verdicts both spellings.
    """
    for login in ("coderabbitai", "coderabbitai[bot]"):
        state, reviewed, why = _sink([{"author": {"login": login}, "state": "APPROVED"}])
        assert state["approvals"] == [], login
        assert state["agent_tool"] == [{"bot": login, "via": "review"}], login
        assert reviewed
        assert "agent review by" in why, login
        assert "approved by" not in why, login


def test_rest_typing_is_caught_the_same_way() -> None:
    """Raw REST feeds flag bots with `type: "Bot"` rather than `gh`'s `is_bot`;
    the rule takes the record in whichever shape it arrives."""
    review = {"user": {"login": "sam", "type": "Bot"}, "state": "APPROVED"}
    state, reviewed, why = _sink([review])
    assert state["approvals"] == []
    assert not reviewed
    assert "no approval" in why

    # And the bare-login-first helper shape (`_author_login`'s `author`/`user`
    # nesting) still resolves: an author record passed directly.
    assert crc.is_bot_login({"login": "sam", "type": "Bot"})
    assert not crc.is_bot_login({"login": "sam", "type": "User"})
    assert crc.is_bot_login("coderabbitai[bot]")


def test_is_bot_login_classifies_the_raw_shape_of_every_record() -> None:
    """The one rule, pinned input by input.

    Name signals classify without any record (`[bot]` suffix, `REVIEW_BOTS`
    spellings); record signals classify when the login is bare and unlisted;
    a record with neither is a person, because assuming a bot refuses real
    approvals (see `is_bot_login`'s docstring).
    """
    assert crc.is_bot_login("coderabbitai[bot]"), "suffix"
    assert crc.is_bot_login("netlify[bot]"), "any suffix, listed or not"
    assert crc.is_bot_login("coderabbitai"), "listed name, bare spelling"
    assert not crc.is_bot_login("coderabbitai-bad"), "prefix is not the suffix"
    bare_bot = {"login": "flaky-lint", "is_bot": True}
    assert crc.is_bot_login(bare_bot), "gh --json record"
    assert crc.is_bot_login({"author": bare_bot}), "review node"
    assert crc.is_bot_login({"user": bare_bot}), "REST-ish record"
    assert crc.is_bot_login({"login": "flaky-lint", "__typename": "Bot"}), "GraphQL record"
    assert not crc.is_bot_login({"login": "sam", "__typename": "User"}), "GraphQL person"
    assert not crc.is_bot_login({"login": "sam", "is_bot": False}), "gh --json person"
    assert not crc.is_bot_login({"login": "sam"}), "no signals at all: a person"
    assert not crc.is_bot_login(""), "empty login is empty, not a bot"
    assert not crc.is_bot_login(None)
    assert not crc.is_bot_login({})


# ── batched GitHub fetch (no live network) ───────────────────────────────────
#
# Sequential `gh pr view` + per-SHA `/commits/{sha}/pulls` is the promotion-range
# bottleneck (~1.9s per full view). Hatch rules stay in `verdict_for`; these tests
# pin that the walker batches GraphQL and still refuses `reviewed:agent` without
# the in-session marker.


def _graphql_pr(
    *,
    number: int = 1,
    title: str = "fix",
    labels: list[str] | None = None,
    reviews: list[dict[str, Any]] | None = None,
    comments: list[dict[str, Any]] | None = None,
    checks: list[dict[str, Any]] | None = None,
    labeled: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A pullRequest node in GitHub's REAL shape.

    `statusCheckRollup` is an object whose `contexts` connection carries the
    checks, so the payload nests them under `contexts.nodes`. A flat list
    under `contexts` is a shape GitHub never sends -- and it is exactly the
    shape the old fixture used, which is why the broken query went unnoticed:
    the fixture agreed with the reader even when the query could not run.
    """
    return {
        "number": number,
        "title": title,
        "labels": {"nodes": [{"name": name} for name in (labels or [])]},
        "reviews": {"nodes": reviews or []},
        "comments": {"nodes": comments or []},
        "timelineItems": {"nodes": labeled or []},
        "commits": {
            "nodes": [
                {
                    "commit": {
                        "statusCheckRollup": {
                            "contexts": {"nodes": checks or []},
                        }
                    }
                }
            ]
        },
    }


def test_graphql_pr_counts_coderabbit_review_without_comment_bodies() -> None:
    state = crc.state_from_graphql_pr(
        _graphql_pr(
            reviews=[
                {"author": {"login": "coderabbitai"}, "state": "COMMENTED"},
            ]
        )
    )
    reviewed, why = crc.verdict_for(state)
    assert reviewed
    assert "coderabbitai" in why


def test_graphql_pr_reviewed_agent_requires_the_marker() -> None:
    """Do not weaken the hatch: the label alone is still a refusal."""
    without = crc.state_from_graphql_pr(
        _graphql_pr(
            labels=[crc.AGENT_REVIEW_LABEL],
            comments=[
                {"author": {"login": "a"}, "body": "looks fine", "createdAt": "t", "url": "u"}
            ],
        )
    )
    reviewed, why = crc.verdict_for(without)
    assert not reviewed
    assert crc.AGENT_REVIEW_MARKER in why

    with_marker = crc.state_from_graphql_pr(
        _graphql_pr(
            labels=[crc.AGENT_REVIEW_LABEL],
            comments=[
                {
                    "author": {"login": "chrizefan"},
                    "body": f"{crc.AGENT_REVIEW_MARKER}\nfindings",
                    "createdAt": "2026-09-02T00:00:00Z",
                    "url": "https://github.com/o/r/pull/1#issuecomment-1",
                }
            ],
        )
    )
    reviewed, why = crc.verdict_for(with_marker)
    assert reviewed
    assert "in-session review" in why
    assert "issuecomment-1" in why


def test_prefetch_pr_states_uses_one_graphql_query_for_a_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del variables
        calls.append(query)
        return {
            "data": {
                "repository": {
                    "p1894": _graphql_pr(
                        number=1894,
                        checks=[{"name": "Cursor Bugbot", "conclusion": "SUCCESS"}],
                    ),
                    "p1893": _graphql_pr(number=1893, labels=["reviewed:owner"]),
                }
            }
        }

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", fake_graphql)
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([1894, 1893, 1894], cache, invalid)

    assert len(calls) == 1, "distinct PR numbers in one range must share one GraphQL query"
    assert "p1894" in calls[0] and "p1893" in calls[0]
    reviewed, why = crc.verdict_for(cache[1894])
    assert reviewed
    assert "Bugbot completed" in why
    reviewed, why = crc.verdict_for(cache[1893])
    assert reviewed
    assert "reviewed:owner" in why
    assert not invalid


def test_prefetch_pr_states_treats_a_null_node_as_not_a_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An issue number cited as '(#2103)' must not crash; it is invalid, not reviewed."""

    def fake_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del query, variables
        return {"data": {"repository": {"p2103": None}}}

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", fake_graphql)
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([2103], cache, invalid)
    assert 2103 in invalid
    assert 2103 not in cache


def test_prefetch_pr_states_does_not_re_query_cached_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del query, variables
        nonlocal calls
        calls += 1
        return {"data": {"repository": {"p1": _graphql_pr(number=1, labels=["risk:low"])}}}

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", fake_graphql)
    cache: dict[int, dict[str, Any]] = {}
    invalid: set[int] = set()
    crc.prefetch_pr_states([1], cache, invalid)
    crc.prefetch_pr_states([1], cache, invalid)
    assert calls == 1


def test_prefetch_associated_prs_batches_unnumbered_shas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_graphql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        del variables
        calls.append(query)
        return {
            "data": {
                "repository": {
                    "c0": {
                        "associatedPullRequests": {
                            "nodes": [
                                {"number": 1900, "mergedAt": None},
                                {"number": 1899, "mergedAt": "2026-08-05T19:51:00Z"},
                            ]
                        }
                    },
                    "c1": {"associatedPullRequests": {"nodes": [{"number": 7, "mergedAt": None}]}},
                }
            }
        }

    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(crc, "_gh_graphql", fake_graphql)
    found = crc.prefetch_associated_prs(["aaa1111", "bbb2222"])
    assert len(calls) == 1
    assert found["aaa1111"] == 1899
    assert found["bbb2222"] is None


def test_repo_slug_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[list[str]] = []

    def fake_run(args: list[str]) -> str:
        runs.append(args)
        return "digithings-ai/digithings"

    monkeypatch.setattr(crc, "_run", fake_run)
    crc._repo_slug.cache_clear()
    assert crc._repo_slug() == "digithings-ai/digithings"
    assert crc._repo_slug() == "digithings-ai/digithings"
    assert len(runs) == 1


def test_baseline_ancestor_set_is_one_rev_list(monkeypatch: pytest.MonkeyPatch) -> None:
    runs: list[list[str]] = []

    def fake_run(args: list[str]) -> str:
        runs.append(args)
        return "aaa\nbbb\n"

    monkeypatch.setattr(crc, "_run", fake_run)
    ancestors = crc.baseline_ancestor_shas("e03c7095")
    assert ancestors == {"aaa", "bbb"}
    assert runs == [["git", "rev-list", "e03c7095"]]


# ── the shallow-clone boundary (DIG-4389) ────────────────────────────────────
#
# `git log` emits `%H\x1f%s\x1f%an\x1f%P\x1e`, choosing \x1f and \x1e so a subject
# can contain anything. Python's `str.strip()` treats BOTH as whitespace, so a
# record whose `%P` is empty — the grafted root of a shallow clone — lost its
# trailing separators and crashed the parser. That crash fails closed, which is
# the safe state; merely deleting `.strip()` converts it into a gate that judges
# the ONE commit a shallow clone can see and reports SUCCESS over a ~1000-commit
# promotion. These tests pin both halves: the parser must survive an empty
# `%P`, and the gate must refuse to answer over a degenerate range at all.


_GRAFT_RAW = (
    "6ad9aa1d73796da95cdf414b46409797a7f260a3"
    "\x1fci(merge-queue): board review pass (#5895)\x1fChris\x1f\x1e\n"
)


def test_run_does_not_eat_the_record_and_unit_separators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The root cause: \x1f and \x1e are whitespace to `str.strip()`."""
    assert "\x1f".isspace() and "\x1e".isspace()
    monkeypatch.setattr(crc.subprocess, "check_output", lambda *a, **k: _GRAFT_RAW)
    out = crc._run(["git", "log"])
    assert out == _GRAFT_RAW.rstrip("\n")
    assert out.endswith("\x1e"), "the record terminator must survive the trim"


def test_commits_in_range_parses_a_graft_boundary_record_with_empty_parents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A grafted root has empty `%P`; it must parse as parents="" and not crash."""
    monkeypatch.setattr(crc, "_run", lambda _args: _GRAFT_RAW.rstrip("\n"))
    rows = crc.commits_in_range("origin/main", "6ad9aa1d7379")
    assert rows == [
        {
            "sha": "6ad9aa1d73796da95cdf414b46409797a7f260a3",
            "subject": "ci(merge-queue): board review pass (#5895)",
            "author": "Chris",
            "parents": "",
        }
    ]


def test_commits_in_range_tolerates_a_record_without_a_parents_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive parse: three fields means no parents, not a crash."""
    monkeypatch.setattr(
        crc, "_run", lambda _args: "sha1\x1fsubject\x1fauthor\x1e\n"
    )
    rows = crc.commits_in_range("origin/main", "head")
    assert rows == [
        {"sha": "sha1", "subject": "subject", "author": "author", "parents": ""}
    ]


def test_commits_in_range_refuses_a_record_that_cannot_be_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dropping an unparseable record could hide an unreviewed commit."""
    monkeypatch.setattr(crc, "_run", lambda _args: "sha1\x1fauthor\x1e\n")
    with pytest.raises(ValueError, match="expected at least 3"):
        crc.commits_in_range("origin/main", "head")


def test_commits_in_range_keeps_a_separator_inside_the_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the last two separators are structural; the subject may hold \\x1f."""
    monkeypatch.setattr(
        crc,
        "_run",
        lambda _args: "sha1\x1ffeat: a\x1fb\x1fauthor\x1fp1 p2\x1e\n",
    )
    rows = crc.commits_in_range("origin/main", "head")
    assert rows == [
        {
            "sha": "sha1",
            "subject": "feat: a\x1fb",
            "author": "author",
            "parents": "p1 p2",
        }
    ], "a separator in the subject must not shift author/parents"


def test_a_shallow_clone_refuses_to_judge_the_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One commit is not the promotion; refuse instead of reporting coverage."""
    monkeypatch.setattr(crc, "_shallow_repository", lambda: True)
    reason = crc.history_gap_reason("origin/main", "6ad9aa1d7379")
    assert reason is not None
    assert "shallow" in reason
    assert "--commits-json" in reason, "the refusal must name the way through"


def test_a_disconnected_base_refuses_to_judge_the_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`base..head` over disconnected history is not a promotion range."""
    monkeypatch.setattr(crc, "_shallow_repository", lambda: False)
    monkeypatch.setattr(crc, "_shares_history", lambda _base, _head: False)
    reason = crc.history_gap_reason("origin/main", "6ad9aa1d7379")
    assert reason is not None
    assert "common ancestor" in reason


def test_squashed_or_rebased_history_is_not_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Promotions into main are squashed: main need not be an ancestor of develop."""
    monkeypatch.setattr(crc, "_shallow_repository", lambda: False)
    monkeypatch.setattr(crc, "_shares_history", lambda _base, _head: True)
    assert crc.history_gap_reason("origin/main", "develop") is None


def test_a_range_whose_oldest_commit_is_a_grafted_root_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The boundary signature that survives a misleading shallow check."""
    reason = crc.graft_boundary_reason(
        [{"sha": "s", "subject": "x", "author": "a", "parents": ""}]
    )
    assert reason is not None
    assert "parent" in reason


def test_a_parentless_commit_anywhere_in_the_range_refuses() -> None:
    """A replace/graft boundary need not be the first row `git log` returns."""
    reason = crc.graft_boundary_reason(
        [
            {"sha": "a" * 40, "subject": "x", "author": "a", "parents": "p"},
            {"sha": "b" * 40, "subject": "y", "author": "a", "parents": ""},
        ]
    )
    assert reason is not None
    assert "bbbbbbbb" in reason


def test_a_normal_range_has_no_graft_boundary() -> None:
    assert (
        crc.graft_boundary_reason(
            [{"sha": "s", "subject": "x", "author": "a", "parents": "p1 p2"}]
        )
        is None
    )


def test_main_refuses_a_shallow_clone_before_running_the_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(crc, "_shallow_repository", lambda: True)

    def must_not_run(_base: str, _head: str) -> list[dict[str, Any]]:
        raise AssertionError("the range must not be judged on a shallow clone")

    monkeypatch.setattr(crc, "commits_in_range", must_not_run)
    monkeypatch.setattr(sys, "argv", ["check_review_coverage.py", "--json"])
    assert crc.main() == 2
    assert "shallow" in capsys.readouterr().err


def test_main_fails_closed_when_the_range_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(crc, "_shallow_repository", lambda: False)
    monkeypatch.setattr(crc, "_shares_history", lambda _base, _head: True)

    def unreadable(_base: str, _head: str) -> list[dict[str, Any]]:
        raise subprocess.CalledProcessError(128, "git log")

    monkeypatch.setattr(crc, "commits_in_range", unreadable)
    monkeypatch.setattr(sys, "argv", ["check_review_coverage.py", "--json"])
    assert crc.main() == 2
    assert "cannot read the local range" in capsys.readouterr().err


def _compare_payload(commits: list[dict[str, Any]], total: int | None = None) -> dict[str, Any]:
    return {
        "total_commits": len(commits) if total is None else total,
        "commits": commits,
    }


def _compare_commit(
    sha: str = "a" * 40,
    message: str = "fix(ci): a subject (#1)\n\nbody",
    author: str = "Chris",
    parents: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "sha": sha,
        "commit": {"message": message, "author": {"name": author}},
        "parents": [{"sha": p} for p in (parents if parents is not None else ["b" * 40])],
    }


def test_commits_from_compare_reads_a_complete_payload(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(_compare_payload([_compare_commit()])), encoding="utf-8"
    )
    assert crc.commits_from_compare(str(path)) == [
        {
            "sha": "a" * 40,
            "subject": "fix(ci): a subject (#1)",
            "author": "Chris",
            "parents": "b" * 40,
        }
    ]


def test_commits_from_compare_keeps_the_subject_not_the_body(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(
            _compare_payload(
                [_compare_commit(message="fix: one line (#2)\n\nlong body\nmore")]
            )
        ),
        encoding="utf-8",
    )
    assert crc.commits_from_compare(str(path))[0]["subject"] == "fix: one line (#2)"


def test_commits_from_compare_keeps_both_parents_of_a_merge_commit(tmp_path: Path) -> None:
    """Dropping to the first parent would make `is_merge_commit` miss a merge."""
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(
            _compare_payload([_compare_commit(parents=["c" * 40, "d" * 40])])
        ),
        encoding="utf-8",
    )
    row = crc.commits_from_compare(str(path))[0]
    assert row["parents"] == f"{'c' * 40} {'d' * 40}"
    assert crc.is_merge_commit(row["parents"])


def test_commits_from_compare_refuses_a_payload_that_ends_elsewhere(
    tmp_path: Path,
) -> None:
    """A stale or swapped compare must not be judged as this promotion."""
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(_compare_payload([_compare_commit(sha="a" * 40)])),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"not b{12}"):
        crc.commits_from_compare(str(path), expected_head="b" * 40)


def test_commits_from_compare_refuses_an_empty_payload_for_a_named_head(
    tmp_path: Path,
) -> None:
    path = tmp_path / "compare.json"
    path.write_text(json.dumps(_compare_payload([])), encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        crc.commits_from_compare(str(path), expected_head="b" * 40)


def test_commits_from_compare_accepts_the_named_head_prefix(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(_compare_payload([_compare_commit(sha="a" * 40)])),
        encoding="utf-8",
    )
    assert crc.commits_from_compare(str(path), expected_head="a" * 12)


def test_commits_from_compare_refuses_a_malformed_payload(tmp_path: Path) -> None:
    path = tmp_path / "compare.json"
    path.write_text(json.dumps({"total_commits": 1, "commits": [{"nope": True}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="40-hex"):
        crc.commits_from_compare(str(path))


def test_commits_from_compare_requires_a_file(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        crc.commits_from_compare(str(tmp_path / "missing.json"))


def test_main_refuses_a_missing_compare_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_review_coverage.py", "--commits-json", str(tmp_path / "missing.json")])
    assert crc.main() == 2
    assert "refusing the supplied commit set" in capsys.readouterr().err


def test_commits_from_compare_refuses_a_truncated_payload(tmp_path: Path) -> None:
    """GitHub caps compare at 250 commits; judging a capped set is a false green."""
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(_compare_payload([_compare_commit()], total=1086)),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="truncated"):
        crc.commits_from_compare(str(path))


def test_main_refuses_a_truncated_compare_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        crc,
        "_shallow_repository",
        lambda: (_ for _ in ()).throw(AssertionError("compare input needs no local history")),
    )
    path = tmp_path / "compare.json"
    path.write_text(
        json.dumps(_compare_payload([_compare_commit()], total=1086)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys, "argv", ["check_review_coverage.py", "--commits-json", str(path)]
    )
    assert crc.main() == 2
    assert "truncated" in capsys.readouterr().err


# ── the direct-push hatch (a commit with no source PR) ───────────────────────
#
# Every other hatch hangs off a pull request, so a commit pushed straight to
# develop could carry none of them: it was refused permanently, and the only ways
# out were advancing BASELINE_SHA (retroactively skipping unrelated history) or
# never promoting. This hatch asks for the same artifact `reviewed:agent` asks
# for, addressed to the commit instead of the branch — marker AND short sha, on an
# issue or PR that itself carries the label.
#
# The tests that matter most are the negative ones. Marker without the sha would
# let one review clear every direct push in the range; sha without the marker would
# let a passing mention in unrelated prose stand in for a review; and neither means
# anything if the label is not on the thing carrying the comment.

_SHA = "d28e727cc9a3126fa2345298c2d42649fc9f9ad8"
_SHORT = "d28e727c"


def _fake_github(
    candidates: list[int],
    labels: dict[int, list[str]],
    comments: dict[int, list[dict[str, Any]]],
) -> Any:
    """Stand in for the three endpoints the hatch reads: search, labels, comments."""

    def fake(args: list[str]) -> Any:
        if "search/issues" in args:
            return {"items": [{"number": number} for number in candidates]}
        endpoint = args[-1]
        if endpoint.endswith("/comments"):
            number = int(endpoint.rsplit("/", 2)[-2])
            return comments.get(number, [])
        number = int(endpoint.rsplit("/", 1)[-1])
        return {"labels": [{"name": name} for name in labels.get(number, [])]}

    return fake


def _direct_push_comment(body: str) -> dict[str, Any]:
    return {
        "body": body,
        "user": {"login": "chrizefan"},
        "created_at": "2026-09-02T14:00:00Z",
        "html_url": "https://github.com/o/r/pull/3256#issuecomment-1",
    }


def _hatch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: str,
    labels: list[str],
    candidates: list[int] | None = None,
) -> dict[str, Any] | None:
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(
        crc,
        "_gh_json",
        _fake_github(
            candidates if candidates is not None else [3256],
            {3256: labels},
            {3256: [_direct_push_comment(body)]},
        ),
    )
    return crc.direct_push_review(_SHA)


def test_a_direct_push_is_hatched_by_a_review_quoting_its_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    found = _hatch(
        monkeypatch,
        body=f"{crc.AGENT_REVIEW_MARKER}\n### {_SHORT} docs: rename\nNo blocking findings.",
        labels=[crc.AGENT_REVIEW_LABEL],
    )
    assert found
    assert found["actor"] == "chrizefan"
    assert found["on"] == 3256
    assert found["url"].endswith("issuecomment-1"), "the verdict must link the findings"


def test_the_review_must_quote_the_sha_and_not_merely_carry_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Otherwise one in-session review hatches every direct push in the range."""
    assert (
        _hatch(
            monkeypatch,
            body=f"{crc.AGENT_REVIEW_MARKER}\nReviewed the promotion. Looks fine.",
            labels=[crc.AGENT_REVIEW_LABEL],
        )
        is None
    )


def test_the_review_must_carry_the_marker_and_not_merely_quote_the_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sha mentioned in unrelated prose is not a review of that commit."""
    assert (
        _hatch(
            monkeypatch,
            body=f"Rebased onto {_SHORT}, will look at it later.",
            labels=[crc.AGENT_REVIEW_LABEL],
        )
        is None
    )


def test_the_label_has_to_be_on_the_thing_carrying_the_comment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        _hatch(
            monkeypatch,
            body=f"{crc.AGENT_REVIEW_MARKER}\n{_SHORT}: reviewed",
            labels=["risk:low", "component:root"],
        )
        is None
    )


def test_a_full_sha_in_the_comment_also_satisfies_the_short_sha_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`git log --oneline` prints 8; a reviewer pasting all 40 has still named it."""
    found = _hatch(
        monkeypatch,
        body=f"{crc.AGENT_REVIEW_MARKER}\nReviewed {_SHA} — no findings.",
        labels=[crc.AGENT_REVIEW_LABEL],
    )
    assert found


def test_a_sha_named_only_in_a_review_header_table_still_clears_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A known, accepted limit — pinned so nobody reads the hatch as stronger.

    Requiring marker AND sha narrows the claim; it does not prove this commit was
    read. Every promotion review on #3256 names the range tip in its header table
    ("`origin/develop` (reviewed tip) | `46c9ab76…`"), and that comment does clear
    that commit. Tightening past this means guessing at prose structure, which
    would refuse real reviews to catch a case the review author has no reason to
    game. The honest framing is `reviewed:owner`'s: an accountability record.
    """
    found = _hatch(
        monkeypatch,
        body=(
            f"{crc.AGENT_REVIEW_MARKER}\n"
            "| ref | sha |\n|---|---|\n"
            f"| `origin/develop` (reviewed tip) | `{_SHA}` |\n"
        ),
        labels=[crc.AGENT_REVIEW_LABEL],
    )
    assert found, "documents the limit; see the docstring before tightening this"


def test_no_candidate_mentions_the_sha_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        _hatch(
            monkeypatch,
            body=f"{crc.AGENT_REVIEW_MARKER}\n{_SHORT}",
            labels=[crc.AGENT_REVIEW_LABEL],
            candidates=[],
        )
        is None
    )


def test_the_search_lookup_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A transient API failure must refuse, never hatch — as `associated_pr_number` does."""
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")

    def fail(_args: list[str]) -> Any:
        raise subprocess.CalledProcessError(1, "gh api")

    monkeypatch.setattr(crc, "_gh_json", fail)
    assert crc._sha_mentioned_in(_SHORT) == []
    assert crc._issue_labels(3256) == set()
    assert crc.direct_push_review(_SHA) is None


def test_search_discovery_is_never_trusted_on_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search matches tokenized text and is eventually consistent.

    So a candidate it returns is re-read: the label comes from the issue itself and
    the sha from the comment body. A search hit alone must not hatch anything.
    """
    monkeypatch.setattr(crc, "_repo_slug", lambda: "digithings-ai/digithings")
    monkeypatch.setattr(
        crc,
        "_gh_json",
        _fake_github([3256], {3256: [crc.AGENT_REVIEW_LABEL]}, {3256: []}),
    )
    assert crc.direct_push_review(_SHA) is None


def test_the_hatch_is_unreachable_for_a_commit_that_has_a_pull_request() -> None:
    """The narrowness guarantee: this is not a sixth way to clear a PR.

    A commit with a source PR must keep being judged by that PR's own state, so the
    single call site has to sit behind the `number is None` guard. Pinned
    structurally because a later refactor could hoist it out without any test that
    exercises the PR path noticing.
    """
    tree = ast.parse(inspect.getsource(crc.main))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "direct_push_review"
    ]
    assert len(calls) == 1, "exactly one call site, inside the no-source-PR branch"

    guards = [
        node for node in ast.walk(tree) if isinstance(node, ast.If) and calls[0] in ast.walk(node)
    ]
    innermost = min(guards, key=lambda node: len(list(ast.walk(node))))
    assert ast.unparse(innermost.test) == "number is None"


def test_the_pr_verdict_never_consults_the_direct_push_hatch() -> None:
    assert "direct_push_review" not in inspect.getsource(crc.verdict_for)


def test_the_failure_guidance_tells_you_how_to_hatch_a_direct_push() -> None:
    """A gate whose refusal names no remedy is how BASELINE_SHA gets advanced."""
    src = SCRIPT.read_text(encoding="utf-8")
    assert "it has no PR at all" in src
    assert "no merged source pull request" in src


def test_the_board_seats_bare_review_author_is_a_bot() -> None:
    """gh 2.102 sends a review author as a bare `{"login": "digiforge-board"}`.

    No `is_bot`, no `[bot]` suffix: read as a person, the seat's APPROVED review
    cleared coverage on #6516 over a standing changes-requested review
    (2026-10-27). The login is listed by name so the approval is not counted.
    """
    assert crc.is_bot_login({"login": "digiforge-board"})
    assert crc.is_bot_login("digiforge-board")
    review = {"author": {"login": "digiforge-board"}, "state": "APPROVED"}
    state, reviewed, _why = _sink([review])
    assert state["approvals"] == []
    assert not reviewed


def test_the_board_seat_is_not_exempt_from_commit_review_coverage() -> None:
    """`BOT_AUTHORS` exempts a commit author from review coverage. The seat authors
    the squash commit of nearly every PR, so it must never be added there."""
    assert "digiforge-board" not in crc.BOT_AUTHORS
    assert "digiforge-board[bot]" not in crc.BOT_AUTHORS
