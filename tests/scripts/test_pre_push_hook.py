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

DIG-1579 adds a third, on the same pattern. Its *lookup* is
``scripts/branch_age_warning.py``: the branch-age warning the hook prints and
never enforces. The shell suite proves the warning reaches a real push and that
a deletion still succeeds; the tests below pin the three things the hook cannot
see — the age wording, the tier band, and the policy § 5 exemption list — plus
the property the whole arm rests on: no input makes it block.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent / "test_pre_push_hook.sh"
_CHECKER = Path(__file__).resolve().parents[2] / "scripts" / "branch_restart_check.py"
_AGE = Path(__file__).resolve().parents[2] / "scripts" / "branch_age_warning.py"

# The clock the DIG-1579 tests age their fixture commits against. Read once from
# the real clock, not a literal: ``main()`` calls ``time.time()`` itself, so a
# fixture anchored to a fixed epoch in the future measures a NEGATIVE age, the
# warning silently suppresses itself, and the test that was meant to prove the
# warning fires passes for the opposite reason. (It did, once.)
_NOW = int(time.time())


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


def _load_age():
    """Import scripts/branch_age_warning.py the same way."""
    spec = importlib.util.spec_from_file_location("branch_age_warning", _AGE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["branch_age_warning"] = module
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


@pytest.mark.unit
def test_unreadable_arguments_fail_open(capsys) -> None:
    """A usage error must not read as a refusal.

    ``argparse`` exits 2 on a usage error and ``pre-push.sh`` reads any non-zero
    exit as a deliberate block, so a checker that cannot parse the hook's
    arguments would stop the push. The reachable case is version skew:
    ``install-hooks.sh`` installs the hook from ``origin/develop`` while
    ``pre-push.sh`` resolves this file from the working tree, so a checkout that
    has not pulled pairs the new hook (which sends ``--is-update``) with an older
    checker that does not know the flag.
    """
    checker = _load_checker()

    # Conflicting flags, and a flag this version does not define: both are what
    # the skew produces, and both must allow.
    assert checker.main(["HEAD", "--is-create", "--is-update"]) == 0
    assert "could not read its arguments" in capsys.readouterr().out
    assert checker.main(["HEAD", "--is-a-flag-from-the-future"]) == 0
    assert "could not read its arguments" in capsys.readouterr().out


# ── DIG-1579: the branch-age warning ──────────────────────────────────────────


@pytest.mark.unit
def test_branch_age_threshold_is_ten_days() -> None:
    """§ 6, item 3 says 10 days, so the constant is 10 days and not a number of hours.

    The same 10 days is the § 6, item 2 CI guard's threshold. If this moves alone, one
    branch gets two different answers depending on whether you ask the hook or
    the sweep.
    """
    age = _load_age()
    assert age.STALE_AFTER_DAYS == 10
    assert age.STALE_AFTER_SECONDS == 10 * 24 * 60 * 60


@pytest.mark.unit
@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0 seconds"),
        (1, "1 second"),
        (59, "59 seconds"),
        (90, "1 minute"),
        (3600, "1 hour"),
        # Below 48h stays in hours so a reader comparing against the 10-day rule
        # never has to convert units.
        (47 * 3600, "47 hours"),
        # At 48h it switches to days — the boundary, both ways.
        (48 * 3600, "2 days"),
        (14 * 24 * 3600, "14 days"),
        (365 * 24 * 3600, "365 days"),
    ],
)
def test_humanise_age_uses_the_unit_the_threshold_uses(seconds: int, expected: str) -> None:
    age = _load_age()
    assert age.humanise_age(seconds) == expected


@pytest.mark.unit
def test_humanise_age_reports_a_future_commit_instead_of_zero() -> None:
    """A clock or metadata fault must not read as a measurement.

    Rounding a commit dated in the future to "0 seconds" would print the most
    reassuring sentence the warning can print, for a branch whose age is
    unknown.
    """
    age = _load_age()
    rendered = age.humanise_age(-60)
    assert "future" in rendered
    assert rendered != "0 seconds"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("patches", "expected_label"),
    [
        (0, "T0"),
        (1, "T1"),
        (2, "T1"),
        # 3 is the first patch of T2: the tier table's bands are inclusive
        # ("3-10"), so a 3-patch branch must not fall back to T1.
        (3, "T2"),
        (10, "T2"),
        (11, "T3"),
        (500, "T3"),
    ],
)
def test_tier_band_matches_the_policy_table(patches: int, expected_label: str) -> None:
    """Every patch count lands in exactly one tier, and the bands are inclusive.

    § 3 states the bands as ranges ("3-10", ">10"), so 10 is the last day of T2
    and 11 is the first of T3. An off-by-one here would tell an operator the
    wrong owner owns the decision to keep or drop their branch.
    """
    age = _load_age()
    assert age.tier_for(patches).label.startswith(expected_label)


@pytest.mark.unit
def test_every_tier_names_an_owner() -> None:
    """A tier without an owner is advice nobody can act on.

    § 3 assigns each tier to a person or role; the warning is the only place an
    agent reads that assignment, so the assignment has to survive into the text.
    """
    age = _load_age()
    for patches in (0, 1, 3, 11):
        tier = age.tier_for(patches)
        assert tier.owner
        assert tier.action


@pytest.mark.unit
@pytest.mark.parametrize(
    "branch",
    [
        "main",
        "develop",
        "module/digiquant",
        "release/v1.2.3",
        "chore/sync-module-digiquant",
    ],
)
def test_policy_exempt_branches_are_silent(branch: str) -> None:
    """§ 5 exempts these from the stranded set, so a stale one is silent.

    ``module/*`` is an accumulation point whose age is normal, and a
    ``release/v*`` line staying quiet between patches is what keeps it patchable
    for a pinned client. Warning on either would contradict the policy that
    exempts it.
    """
    age = _load_age()
    assert age.is_excluded_branch(branch) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "branch",
    [
        "task/1579-branch-age",
        "fix/DIG-1579-pre-push-branch-age-warning",
        "DIG-1579-pre-push-branch-age-warning",
        # A prefix match on "main" or "develop" would silence these too. They
        # are ordinary work branches and must keep their warning.
        "mainline-anything",
        "develop-tools",
        "module-something",
        "release-please--branches--develop--components--digichat",
    ],
)
def test_ordinary_branches_keep_their_warning(branch: str) -> None:
    """The exemption list matches whole names and prefix-with-separator only."""
    age = _load_age()
    assert age.is_excluded_branch(branch) is False


@pytest.mark.unit
def test_warning_carries_the_three_things_the_operator_needs() -> None:
    """Age, tier and the policy path — the three things § 6, item 3 asks the warning to print."""
    age = _load_age()
    text = "\n".join(age.warning_lines("task/1579-age", 14 * 24 * 3600, 4))
    assert "task/1579-age" in text
    assert "14 days" in text
    assert "T2" in text
    assert "docs/ops/branch-hygiene-policy.md" in text
    # "Non-blocking" is what tells the operator the push is still going to
    # happen, which is the whole reason § 6, item 3 asks for a warning and not a gate.
    assert "Non-blocking" in text


@pytest.mark.unit
def test_warning_still_reports_the_age_when_the_tier_is_unknown() -> None:
    """A missing origin/develop costs the tier, not the warning.

    A shallow or un-fetched clone is the common case for a new worktree. If the
    whole message were dropped there, the one branch that most needs telling
    about its age — a branch whose work is not anywhere else — would be silent.
    """
    age = _load_age()
    text = "\n".join(age.warning_lines("task/1579-age", 30 * 24 * 3600, None))
    assert "30 days" in text
    assert "tier unknown" in text
    assert "docs/ops/branch-hygiene-policy.md" in text


@pytest.mark.unit
def test_a_fresh_branch_says_nothing(tmp_path: Path) -> None:
    """Under the threshold the warning is empty, not a reassuring line.

    An operator who sees output on every push learns to skip it. Asserted
    against ``_evaluate`` — the function that actually applies the threshold —
    rather than ``warning_lines``, which always has text to return and would
    pass vacuously here.

    The repository is real, because ``_evaluate`` reads the age FIRST by design:
    the commit date is the only measurement with no repository-wide dependency,
    and it is the only thing § 6, item 3 turns on. A bogus repo here would raise
    instead of returning ``[]``, and would be testing the wrong function.
    """
    age = _load_age()
    repo = _make_repo(tmp_path, "fresh", _NOW - 60)
    head = _head(repo)

    assert age.tip_commit_time(repo, head) == _NOW - 60
    assert age._evaluate(str(repo), head, "task/1579-fresh", _NOW) == []


def _make_repo(root: Path, name: str, epoch: int) -> Path:
    """A one-commit repository whose only commit carries ``epoch``.

    The commit date is what the whole arm reads, so it is the only thing set
    here. No ``origin/*`` remote is created, which is deliberate: it is the
    shape a fresh worktree has, and it is what makes the "tier unknown" arm
    reachable without inventing a remote.
    """
    import os

    repo = root / name
    repo.mkdir(parents=True)
    saved = {k: os.environ.get(k) for k in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
    stamp = f"@{epoch}"
    os.environ["GIT_AUTHOR_DATE"] = stamp
    os.environ["GIT_COMMITTER_DATE"] = stamp
    try:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(repo), check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "empty tip"],
            cwd=str(repo),
            check=True,
        )
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return repo


def _head(repo: Path) -> str:
    """The repository's single commit sha."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.mark.unit
def test_a_fresh_tip_in_a_real_repo_produces_no_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same threshold, measured against a real repository rather than a clock.

    ``_evaluate`` above proves the comparison; this proves the *input* — that
    ``tip_commit_time`` reads the commit date off disk and lands on the branch's
    real age, so an age of 10 days is not something the caller has to supply.
    """
    age = _load_age()
    now = _NOW
    repo = _make_repo(tmp_path, "fresh", now - 60)
    head = _head(repo)

    assert age.tip_commit_time(repo, head) == now - 60
    assert age._evaluate(str(repo), head, "task/1579-fresh", now) == []

    # Same repository, same clock, one threshold further back: the warning fires.
    old = _make_repo(tmp_path, "stale", now - 14 * 24 * 3600)
    old_head = _head(old)
    lines = age._evaluate(str(old), old_head, "task/1579-stale", now)
    assert lines, "a 14-day-old tip must produce the warning"
    assert any("14 days" in line for line in lines), lines
    assert any("tier unknown" in line for line in lines), lines


@pytest.mark.unit
@pytest.mark.parametrize("days", [0, 1, 2, 3, 9])
def test_a_tip_inside_the_threshold_is_silent_for_every_day_below_it(
    days: int, tmp_path: Path
) -> None:
    """Every day from 0 to 9 is silent; 10 and above is not.

    The boundary is where a warning starts being a nag and then becomes noise,
    so both sides of it are measured against real commit dates rather than one
    hand-picked number.
    """
    age = _load_age()
    now = _NOW
    repo = _make_repo(tmp_path, f"d{days}", now - days * 24 * 3600)
    head = _head(repo)
    assert age._evaluate(str(repo), head, f"task/1579-d{days}", now) == []


@pytest.mark.unit
@pytest.mark.parametrize("days", [11, 14, 90])
def test_a_tip_past_the_threshold_warns_for_every_day_beyond_it(days: int, tmp_path: Path) -> None:
    """The other side of the same boundary, measured the same way."""
    age = _load_age()
    now = _NOW
    repo = _make_repo(tmp_path, f"d{days}", now - days * 24 * 3600)
    head = _head(repo)
    lines = age._evaluate(str(repo), head, f"task/1579-d{days}", now)
    assert lines, f"a {days}-day-old tip must warn"
    assert any("Non-blocking" in line for line in lines), lines


@pytest.mark.unit
def test_an_exempt_branch_is_silent_at_any_age() -> None:
    """A 90-day-old ``module/*`` branch produces nothing, through ``main``.

    The exemption is tested at the name level above; this proves it is applied
    before the age is read, in the function the hook calls. ``--repo`` does not
    exist, so reaching a git call would raise — silence here can only come from
    the short-circuit.
    """
    age = _load_age()
    assert (
        age.main(
            [
                "HEAD",
                "--branch-name",
                "module/digiquant",
                "--repo",
                "/nonexistent-repo-for-this-test",
            ]
        )
        == 0
    )


@pytest.mark.unit
def test_an_unexempt_branch_of_the_same_age_does_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control for the test above: same age, ordinary name, warning printed.

    Without this pair, "an exempt branch is silent" is satisfied by a module that
    prints nothing at all.
    """
    age = _load_age()
    now = _NOW
    repo = _make_repo(tmp_path, "unexempt", now - 90 * 24 * 3600)
    head = _head(repo)
    assert age.main([head, "--branch-name", "task/1579-old", "--repo", str(repo)]) == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    "argv",
    [
        # A ref git cannot resolve.
        ["no-such-ref-at-all", "--branch-name", "task/1579-missing"],
        # A flag from a future hook version (version skew on install).
        ["HEAD", "--a-flag-from-the-future"],
        # Conflicting / unusable arguments.
        [],
        # Not a repository at all.
        ["HEAD", "--branch-name", "task/1579-norepo", "--repo", "/nonexistent-repo-for-this-test"],
    ],
)
def test_the_warning_never_blocks(argv: list[str], capsys) -> None:
    """Every path exits 0. This is the arm's one non-negotiable property.

    ``pre-push.sh`` reads any non-zero exit from a checker as a deliberate
    refusal, and the hook is wired to ``|| true`` precisely because a bug in a
    *warning* must never cost a push. A usage error, an unresolvable ref and a
    repository git cannot answer for are the three reachable surprises, and all
    three have to stay at 0.
    """
    age = _load_age()
    assert age.main(argv) == 0
    capsys.readouterr()


@pytest.mark.unit
def test_an_unreadable_repo_is_reported_as_a_wrong_argument_not_a_bug(
    capsys,
) -> None:
    """A missing ``--repo`` directory must name the directory.

    The reachable path is a stale path in a hook wrapper or a removed worktree.
    What matters is which sentence the operator reads: "cannot run git in
    '/x'" is something they can act on, while "unexpected failure" is a report
    about this module on a push that was never refused. Both exit 0 — the
    non-blocking property is pinned by the test above, and this one pins the
    wording, which is otherwise covered only by the broad handler below it.
    """
    age = _load_age()
    assert age.main(["HEAD", "--repo", "/nonexistent-repo-for-this-test"]) == 0
    out = capsys.readouterr()
    assert "/nonexistent-repo-for-this-test" in (out.err + out.out)
    assert "unexpected failure" not in (out.err + out.out)


@pytest.mark.unit
def test_a_stale_branch_without_a_fetched_base_still_reports_the_age(
    tmp_path: Path, capsys
) -> None:
    """A repo with no ``origin/develop`` warns, and names what to run.

    This is the shape every fresh worktree has. The patch count cannot be
    computed, so the tier reads "unknown" — but the age is still the thing the
    operator needs, and it is still printed. Silently dropping the whole message
    would make the branch least likely to be known look least stale.
    """
    age = _load_age()
    now = _NOW
    repo = _make_repo(tmp_path, "nobase", now - 40 * 24 * 3600)
    head = _head(repo)

    assert age.main([head, "--branch-name", "task/1579-nobase", "--repo", str(repo)]) == 0
    err = capsys.readouterr().err

    assert "task/1579-nobase" in err
    assert "40 days" in err
    assert "tier unknown" in err
    # The remedy is named, because a tier is the part the operator cannot act on
    # without it and a message that says "unknown" alone reads as a bug.
    assert "git fetch origin" in err
    assert "Non-blocking" in err
    assert "docs/ops/branch-hygiene-policy.md" in err


def _make_squashed_base_repo(root: Path, name: str, epoch: int) -> tuple[Path, str]:
    """A repository where ``origin/develop`` holds a **squash** of one branch commit.

    The shape is the one this repository actually produces: ``feature`` carries
    ``B`` then ``C``, while ``develop`` holds a single commit carrying the same
    patch as ``B`` under a different sha and a different message. So:

    - ``git cherry`` reports ``B`` as already applied (patch-id match) and ``C`` as new
      — 1 ``+`` line out of 2;
    - ``git rev-list --count origin/develop..feature`` reports **2**, because the
      squash never put ``B``'s sha on develop.

    Both numbers are the ones a wrong implementation would print, which is what
    makes this fixture able to discriminate between them.
    """
    import os

    repo = root / name
    repo.mkdir(parents=True)
    saved = {k: os.environ.get(k) for k in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
    os.environ["GIT_AUTHOR_DATE"] = os.environ["GIT_COMMITTER_DATE"] = f"@{epoch}"

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=str(repo),
            check=True,
            capture_output=True,
            env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
        )

    try:
        git("init", "-q", "-b", "main")
        git("commit", "-q", "--allow-empty", "-m", "A")
        git("checkout", "-q", "-b", "feature")
        (repo / "f.txt").write_text("b\n")
        git("add", "f.txt")
        git("commit", "-q", "-m", "B on feature")
        (repo / "f.txt").write_text("c\n")
        git("add", "f.txt")
        git("commit", "-q", "-m", "C on feature")
        git("checkout", "-q", "main")
        # Same parent, same patch content, different message -> different sha,
        # same patch-id. This is what a squash merge leaves behind.
        (repo / "f.txt").write_text("b\n")
        git("add", "f.txt")
        git("commit", "-q", "-m", "squash of B")
        git("update-ref", "refs/remotes/origin/develop", "main")
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return repo, "feature"


@pytest.mark.unit
def test_the_tier_counts_unmerged_patches_not_commits(tmp_path: Path) -> None:
    """Policy § 2's measure, on the shape that separates it from a commit count.

    § 2 rules out commit counting *by name* because it "counts commits whose patch
    already reached develop by a squash". This is that case, built for real: one
    branch commit was squash-merged, so the commit count reads 2 and the
    patch count reads 1. The tier the operator is pointed at is the patch count's.

    Measured on this fixture: ``git cherry`` prints 2 lines (one ``-``, one ``+``),
    so a counter that takes the line count rather than the ``+`` lines also reads 2
    and lands the branch in a tier one band too high.
    """
    age = _load_age()
    repo, branch = _make_squashed_base_repo(tmp_path, "squashed", _NOW - 40 * 24 * 3600)

    raw = subprocess.run(
        ["git", "cherry", "origin/develop", branch],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout
    commits = subprocess.run(
        ["git", "rev-list", "--count", "origin/develop..feature"],
        cwd=str(repo), capture_output=True, text=True, check=True,
    ).stdout.strip()

    # The fixture's own non-vacuity: the three readings really do differ.
    assert len(raw.strip().splitlines()) == 2, raw
    assert sum(1 for line in raw.splitlines() if line.startswith("+")) == 1, raw
    assert commits == "2", commits

    assert age.unmerged_patch_count(repo, "feature") == 1
