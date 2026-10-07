"""Pytest entry for tests/scripts/test_pre_push_hook.sh (#2468 / #2483).

The shell suite is the source of truth (real temp-repo cases against
``scripts/hooks/pre-push.sh``). This wrapper makes it run under the existing
``pytest tests/scripts/`` CI lane without editing the protected ``ci.yml``.

DIG-1589 adds a second layer: the duplicate-work guard's *decision logic* lives
in ``scripts/branch_restart_check.py``, which the hook shells out to. The
end-to-end behaviour (refusals, escapes, regressions) is pinned by the shell
suite above; the pure helpers that decide those answers are pinned here, so a
change in branch-name normalisation or trailer parsing fails with a message
that names the function rather than "exit 1, got 1".
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_pre_push_hook.sh"
_CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "branch_restart_check.py"


def _load_checker():
    """Import scripts/branch_restart_check.py by path.

    ``scripts/`` is not a package and this lane must not grow a root conftest or
    an ``__init__.py`` just to reach one module, so load it the same way the
    hook's own consumer does: straight from the file.
    """
    spec = importlib.util.spec_from_file_location("branch_restart_check", _CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["branch_restart_check"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_pre_push_hook_live_trading_and_deletion_suite() -> None:
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"pre-push suite failed (exit {result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.unit
def test_duplicate_work_threshold_is_three_and_named() -> None:
    """The threshold is 3, not 1.

    The d8c5 sibling branches shared a 40-commit unmerged base, so two honest
    parallel leaves always share at least one patch. Threshold 1 would refuse
    legitimate parallel work; 3 is the point where a shared *unmerged stack*
    means the session is about to rebuild someone else's work.
    """
    checker = _load_checker()
    assert checker.MIN_UNMERGED_PATCH_OVERLAP == 3
    assert isinstance(checker.MIN_UNMERGED_PATCH_OVERLAP, int)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("task/1589-sibling", "task/1589-sibling"),
        ("origin/task/1589-sibling", "task/1589-sibling"),
        ("refs/remotes/origin/task/1589-sibling", "task/1589-sibling"),
        ("refs/heads/task/1589-sibling", "task/1589-sibling"),
        # Whitespace survives an env var typed by a human, and a trailing slash
        # would otherwise compare unequal to the remote ref it names.
        ("  task/1589-sibling  ", "task/1589-sibling"),
        ("origin/task/1589-sibling/", "task/1589-sibling"),
    ],
)
def test_normalize_branch_ref_accepts_every_spelling_an_agent_types(
    value: str, expected: str
) -> None:
    """RESUME_FROM has to match the sibling however the operator spelled it.

    A ``RESUME_FROM`` that silently fails to match re-imposes the refusal the
    escape exists to lift, which reads as "the guard is broken" rather than
    "you typed the wrong ref".
    """
    checker = _load_checker()
    assert checker.normalize_branch_ref(value) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    "branch",
    [
        "main",
        "develop",
        "module/digiquant",
        "release/v1.2.3",
        "release-please--branches--develop--components--digichat",
        "bot/stub-tsv-9999",
    ],
)
def test_protected_branches_are_never_siblings(branch: str) -> None:
    """Protected and machine-pushed refs must not trip the guard.

    ``module/*`` carries the module-branch-protection ruleset and is the
    accumulation point for a component's work; ``bot/*`` and the
    release-please branches are pushed by workflows. Treating any of them as
    "work in flight that someone is about to rebuild" would refuse pushes for
    reasons the operator cannot act on.
    """
    checker = _load_checker()
    assert checker.is_protected_branch(branch) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "branch",
    ["task/1589-sibling", "cursor/dashboard-digiquant-web-d8c5", "fix/retry"],
)
def test_ordinary_branches_are_not_protected(branch: str) -> None:
    checker = _load_checker()
    assert checker.is_protected_branch(branch) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "feat: x\n\nRESTART_REASON: sibling is stranded with no PR.\n",
            "sibling is stranded with no PR.",
        ),
        # A trailer is the documented spelling, but a body line is what an agent
        # writes when it amends mid-thought. Both are "the reason travels with
        # the commit"; neither may be silently ignored.
        (
            "feat: x\n\nI am deliberately not forking.\nRESTART_REASON: hand-rolled baseline.\n",
            "hand-rolled baseline.",
        ),
        # Same reasoning as the Human-Approved-By arm: a bare label is not a reason.
        ("feat: x\n\nRESTART_REASON:\n", None),
        # Mid-sentence mention is documentation, not a declaration of intent.
        ("feat: document the gate\n\nAdd a line reading RESTART_REASON: <one line>.\n", None),
        ("feat: x\n", None),
    ],
)
def test_restart_reason_is_read_from_the_tip_commit_message(
    message: str, expected: str | None
) -> None:
    checker = _load_checker()
    assert checker.parse_restart_reason(message) == expected


@pytest.mark.unit
def test_update_push_is_allowed_without_looking_at_siblings() -> None:
    """An update push is never refused, and the answer costs no git call.

    The guard is about creation. Once the remote holds the ref, the branch keeps
    overlapping the same siblings at every later commit, so a sibling check on an
    update refuses ordinary follow-up work — and this repo's stranded branches
    make that most pushes.

    The repository below does not exist, so reaching any git call would raise.
    An allowance here can therefore only come from the short-circuit, not from a
    lookup that ran and happened to find nothing: the assertions on the empty
    reason and notes keep a fail-open allowance from standing in for it.
    """
    checker = _load_checker()
    decision = checker.check("/nonexistent-repo-for-this-test", "HEAD", is_update=True)
    assert decision.allowed is True
    assert decision.reason == ""
    assert decision.notes == ()


@pytest.mark.unit
def test_unexpected_internal_error_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bug in the guard must not block pushes.

    ``_Unknown`` is the anticipated failure and has its own message. Anything
    else — a decoding error, a git format change, a bad index into the ref
    listing — used to reach the hook as a traceback and a non-zero exit, which
    the hook reads as a deliberate refusal. That is fail-*closed* on exactly the
    surprises this guard exists to tolerate, across every agent's push.
    """
    checker = _load_checker()
    repo = str(_CHECKER.parents[1])

    def boom(_repo: str) -> None:
        raise RuntimeError("synthetic unexpected failure")

    # Everything up to the sibling walk succeeds, so the walk is where the
    # surprise lands.
    monkeypatch.setattr(checker, "_is_reachable_from_base", lambda *_a, **_k: False)
    monkeypatch.setattr(checker, "unmerged_patch_ids", lambda *_a, **_k: {"a", "b", "c", "d"})
    monkeypatch.setattr(checker, "unmerged_remote_branches", boom)

    decision = checker.check(repo, "HEAD", branch_name="task/1589-update", env={})
    assert decision.allowed is True
    assert any("synthetic unexpected failure" in note for note in decision.notes), decision.notes
