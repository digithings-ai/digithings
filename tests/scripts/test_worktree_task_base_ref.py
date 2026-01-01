"""`worktree_task.sh create` must cut the task branch from origin, not from a local ref (#2547).

A working clone always has `refs/heads/develop`, so the script's original shape —
fetch only *if* the local branch is missing, then branch from the local branch —
never fetched at all for the five components that route straight to develop.
Observed 2026-08-20: `make task ISSUE=2541` produced a worktree 50 commits behind
`origin/develop`, so the branch started on code that had already moved.

These tests assert the resolution, not a literal: the component labels are read
out of `scripts/project_routing.json` rather than
hard-coded, so re-routing a component moves the fixture with it instead of
silently testing a path nobody uses. What is pinned is the *shape* — the new
branch's tip must equal what `origin/<base>` points at on the remote, which is a
claim no amount of routing churn makes uninteresting.

`gh` is stubbed on PATH. The script calls it three times (auth status, issue title,
component label) and its fallback only triggers when `gh` is absent or unauthenticated, so on a
developer machine or in CI an unstubbed run would make live API calls against the
real repository and assert against whatever labels that issue happens to carry.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "worktree_task.sh"
ROUTING_PATH = REPO_ROOT / "scripts" / "project_routing.json"
ROUTING: dict[str, str] = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))["branches"]

ISSUE = "4242"

# Every component routes straight to develop: the `module/*` integration tier
# was retired (#6751). `default` is excluded: it is the fallback, not a
# `component:` label the script would ever read off an issue.
_ONE_HOP = sorted(c for c, b in ROUTING.items() if b == "develop" and c != "default")


def test_every_component_routes_to_develop() -> None:
    """One hop only: a task branch PRs into develop, never into a staging branch."""
    assert _ONE_HOP, f"no component routes straight to develop in {ROUTING_PATH}: {ROUTING}"
    off = {c: b for c, b in ROUTING.items() if b != "develop"}
    assert off == {}, f"components routed off develop in {ROUTING_PATH}: {off}"


ONE_HOP_COMPONENT = _ONE_HOP[0] if _ONE_HOP else "component:root"
# A synthetic routing entry, injected into the fixture's copy of the routing map
# only, so the missing-base fallback stays covered without a real non-develop route.
ROUTED_COMPONENT, ROUTED_BRANCH = "component:routed", "integration/routed"


# A developer's global config is not this test's business. `commit.gpgsign`,
# `core.hooksPath` or a commit template would fail `_commit` and error the module
# instead of exercising the script — and this repo does install a git hook.
_HERMETIC_GIT_ENV = {
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_HERMETIC_GIT_ENV},
    )
    return done.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "commit", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _install_gh_stub(root: Path, component: str) -> Path:
    """A `gh` on PATH that answers the three queries the script makes, and nothing else."""
    bin_dir = root / "bin"
    # exist_ok: a test that runs the script twice reinstalls the stub, and the
    # second call must be able to change the component it answers with.
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *'auth status'*) exit 0 ;;\n"
        "  *'--json title'*) echo '[agent] fix the base ref' ;;\n"
        f"  *'--json labels'*) echo '{component}' ;;\n"
        '  *) echo "gh stub: unexpected invocation: $*" >&2; exit 1 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return bin_dir


def _seed(root: Path, *, routed_at_tip: bool) -> dict[str, object]:
    """A bare `origin`, and a clone whose refs are deliberately one commit behind it.

    `routed_at_tip` decides whether the synthetic routed branch on the remote has
    caught up with `origin/develop`.
    """
    src = root / "src"
    src.mkdir()
    _git(src, "init", "-b", "develop")
    _git(src, "config", "user.email", "test@example.com")
    _git(src, "config", "user.name", "test")
    old = _commit(src, "base")
    _git(src, "branch", ROUTED_BRANCH)

    origin = root / "origin"
    origin.mkdir()
    _git(origin, "init", "--bare", "-b", "develop")
    _git(src, "remote", "add", "origin", str(origin))
    _git(src, "push", "--quiet", "origin", "develop", ROUTED_BRANCH)

    # Clone here, so the clone's local `develop` *and* its `refs/remotes/origin/*`
    # both stop at `old`. Only a fresh fetch can see `new`.
    work = root / "work"
    _git(root, "clone", "--quiet", str(origin), str(work))
    _git(work, "config", "user.email", "test@example.com")
    _git(work, "config", "user.name", "test")

    new = _commit(src, "newer")
    to_push = ["develop", f"develop:{ROUTED_BRANCH}"] if routed_at_tip else ["develop"]
    _git(src, "push", "--quiet", "origin", *to_push)

    (work / "scripts").mkdir(exist_ok=True)
    shutil.copy2(SCRIPT, work / "scripts" / SCRIPT.name)
    routing = json.loads(ROUTING_PATH.read_text(encoding="utf-8"))
    routing["branches"][ROUTED_COMPONENT] = ROUTED_BRANCH
    (work / "scripts" / ROUTING_PATH.name).write_text(json.dumps(routing), encoding="utf-8")

    return {"work": work, "origin": origin, "old": old, "new": new}


@pytest.fixture()
def seed(tmp_path_factory: pytest.TempPathFactory):
    """Hand back a factory, so one test can seed more than one repo.

    pytest owns the directories: it retains the last few runs, which is what you want
    when a failure is "the script chose the wrong ref" and the repos are the evidence.
    """

    def make(*, routed_at_tip: bool = False) -> dict[str, object]:
        root = tmp_path_factory.mktemp("worktree-task").resolve()
        return _seed(root, routed_at_tip=routed_at_tip)

    return make


def _run(
    fixture: dict[str, object],
    component: str,
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    work = fixture["work"]
    assert isinstance(work, Path)
    bin_dir = _install_gh_stub(work.parent, component)
    environ = {**os.environ, **_HERMETIC_GIT_ENV}
    environ["PATH"] = f"{bin_dir}{os.pathsep}{environ['PATH']}"
    # The script would otherwise inherit this run's own repository context.
    for leaked in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        environ.pop(leaked, None)
    environ.update(env or {})
    return subprocess.run(
        ["bash", str(work / "scripts" / SCRIPT.name), "create", ISSUE],
        cwd=work,
        env=environ,
        capture_output=True,
        text=True,
        # `git fetch origin` is against a local bare repo here, but a credential
        # helper or a stray remote would otherwise hang the lane instead of failing.
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


def _created_branch(work: Path) -> str:
    branches = [
        line.strip()
        for line in _git(work, "branch", "--format=%(refname:short)").splitlines()
        if line.strip().startswith(f"task/{ISSUE}-")
    ]
    assert len(branches) == 1, f"expected exactly one task/{ISSUE}-* branch, got {branches}"
    return branches[0]


def _created_branch_tip(work: Path) -> str:
    return _git(work, "rev-parse", _created_branch(work))


def test_branches_from_origin_and_not_from_the_stale_local_ref(seed) -> None:
    """The whole defect in one assertion: local `develop` is behind, the branch is not."""
    fx = seed()
    work = fx["work"]
    done = _run(fx, ONE_HOP_COMPONENT)
    assert done.returncode == 0, done.stderr

    assert _git(work, "rev-parse", "refs/heads/develop") == fx["old"], (
        "fixture is not exercising the defect: the clone's local develop should still "
        "be behind, since nothing but the script under test is allowed to fetch"
    )
    assert _created_branch_tip(work) == fx["new"], (
        "task branch was cut from the local ref rather than from origin/develop — "
        f"stderr: {done.stderr}"
    )


def test_last_stdout_line_is_the_worktree_path(seed) -> None:
    """`run_task.sh` reads this script's last stdout line as a path, so warnings owe stderr."""
    fx = seed()
    done = _run(fx, ONE_HOP_COMPONENT, env={"WORKTREE_TASK_OFFLINE": "1"})
    assert done.returncode == 0, done.stderr
    tail = done.stdout.strip().splitlines()[-1]
    assert Path(tail).is_dir(), f"last stdout line is not an existing directory: {tail!r}"
    # Named explicitly rather than asserting stderr is merely non-empty: `git
    # worktree add` writes its own progress there, so "something on stderr" would
    # pass even with the warning removed.
    assert "WORKTREE_TASK_OFFLINE is set" in done.stderr, done.stderr
    assert "WORKTREE_TASK_OFFLINE is set" not in done.stdout, (
        "the offline warning reached stdout, where run_task.sh may read it as a path"
    )


def test_offline_is_opt_in_and_a_failed_fetch_is_fatal(seed) -> None:
    """Without the opt-out a dead remote must stop the run, not fall back to a local ref."""
    fx = seed()
    work = fx["work"]
    assert isinstance(work, Path)
    _git(work, "remote", "set-url", "origin", str(work.parent / "does-not-exist"))
    # Move the clone's *local* develop past `origin/develop`, so the surviving-run
    # assertion below can tell the two apart. Left equal, `== fx["old"]` holds for
    # refs/heads and refs/remotes alike and the "never from refs/heads" claim is
    # asserted by nothing.
    local_only = _commit(work, "local-only commit")
    assert local_only != fx["old"]

    done = _run(fx, ONE_HOP_COMPONENT)
    assert done.returncode != 0, f"a failed fetch was swallowed; stdout: {done.stdout}"
    assert "WORKTREE_TASK_OFFLINE" in done.stderr, done.stderr
    assert not list(work.glob(f".worktrees/task/{ISSUE}-*"))

    # Opted in, the same dead remote is survivable — from the remote-tracking refs
    # the last successful fetch left behind, never from refs/heads.
    done = _run(fx, ONE_HOP_COMPONENT, env={"WORKTREE_TASK_OFFLINE": "1"})
    assert done.returncode == 0, done.stderr
    assert _git(work, "rev-parse", "refs/heads/develop") == local_only, (
        "fixture is not exercising the distinction: local develop should be ahead"
    )
    assert _created_branch_tip(work) == fx["old"]


def test_missing_origin_base_falls_back_to_origin_develop_loudly(seed) -> None:
    """A routed branch that was never pushed must not resolve to the local one."""
    fx = seed(routed_at_tip=True)
    work = fx["work"]
    assert isinstance(work, Path)
    origin = fx["origin"]
    assert isinstance(origin, Path)
    _git(origin, "branch", "-D", ROUTED_BRANCH)
    # Deliberately *not* deleting refs/remotes/origin/<branch> by hand. Deleting the
    # branch upstream leaves the clone's cached tip behind until something prunes it,
    # so the cached ref is the realistic starting state and the script's own
    # `git fetch --prune` is what has to clear it. Asserted, so that a fetch which
    # stopped pruning would fail here rather than resolve to a dead ref.
    cached = f"refs/remotes/origin/{ROUTED_BRANCH}"
    assert _git(work, "rev-parse", "--verify", cached) == fx["old"]
    # A local branch of the routed name is exactly the trap: it exists, it is
    # stale, and the old code would have branched from it.
    _git(work, "branch", ROUTED_BRANCH, "refs/heads/develop")

    done = _run(fx, ROUTED_COMPONENT)
    assert done.returncode == 0, done.stderr
    assert f"origin/{ROUTED_BRANCH} does not exist" in done.stderr, done.stderr
    assert _created_branch_tip(work) == fx["new"], "fell back to the local branch, not to origin"
    assert not _git(work, "for-each-ref", "--format=%(refname)", cached), (
        f"{cached} survived the fetch, so the fallback above was luck: the ref still "
        "resolved and only the routing lookup happened to miss it"
    )


def test_a_falsy_opt_out_does_not_enable_it(seed) -> None:
    """`=0` must not turn a safety check off, and an unrecognised value must not be guessed.

    Both switches here disable a check, so `[[ -n "$VAR" ]]` — which counts `0` and
    `false` as set — fails in the direction that hurts: `WORKTREE_TASK_OFFLINE=0`
    reads as "yes, skip the fetch". Requiring a literal `1` instead drops `true` on
    the floor, which fails the other way, so the accepted words are a fixed set and
    anything else stops the run.
    """
    fx = seed()
    work = fx["work"]
    assert isinstance(work, Path)

    done = _run(fx, ONE_HOP_COMPONENT, env={"WORKTREE_TASK_OFFLINE": "perhaps"})
    assert done.returncode != 0, f"an unrecognised value was guessed at; stdout: {done.stdout}"
    assert "WORKTREE_TASK_OFFLINE" in done.stderr, done.stderr
    assert not list(work.glob(f".worktrees/task/{ISSUE}-*"))

    # `0` reads as off, so the fetch runs and the branch lands on origin's tip —
    # the same outcome as leaving it unset, which is the whole point.
    done = _run(fx, ONE_HOP_COMPONENT, env={"WORKTREE_TASK_OFFLINE": "0"})
    assert done.returncode == 0, done.stderr
    assert "WORKTREE_TASK_OFFLINE is set" not in done.stderr, (
        "`=0` skipped the fetch, so a falsy value is switching the safety check off"
    )
    assert _created_branch_tip(work) == fx["new"]


def test_the_task_branch_gets_no_upstream(seed) -> None:
    """Branching from a remote-tracking ref must not leave `origin/<base>` as upstream.

    `git worktree add -b <branch> <path> refs/remotes/origin/develop` sets one by
    default (`branch.autoSetupMerge`), which the old local-ref start point never
    did. Under `push.default=simple` a bare `git push` in the worktree then fails,
    and git's own remedy text suggests `git push origin HEAD:develop` — which puts
    task work directly onto the base branch and skips the task PR. `scripts/run_task.sh`
    pushes with an explicit refspec so the scripted path is unaffected; a human or
    an agent working inside the worktree is not.
    """
    fx = seed()
    work = fx["work"]
    assert isinstance(work, Path)
    done = _run(fx, ONE_HOP_COMPONENT)
    assert done.returncode == 0, done.stderr

    branch = _created_branch(work)
    config = subprocess.run(
        ["git", "config", "--get-regexp", f"^branch\\.{branch}\\.(remote|merge)$"],
        cwd=work,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **_HERMETIC_GIT_ENV},
    )
    assert config.stdout.strip() == "", (
        f"task branch {branch} was given an upstream: {config.stdout.strip()!r}"
    )
