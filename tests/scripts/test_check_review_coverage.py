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
    assert "no completed agent review" in why


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


def _comment(body: str) -> dict[str, Any]:
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
            {3256: [_comment(body)]},
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
