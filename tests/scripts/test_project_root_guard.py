"""Unit tests for scripts/claude-hooks/project-root-guard.sh.

The guard blocks Write/Edit/NotebookEdit targets outside the project root.
Exceptions under test: ~/.claude/plans/, Claude Code's per-project persistent
memory at ~/.claude/projects/<slug>/memory/, the session's original project
dir (CLAUDE_PROJECT_DIR), and the main repository behind a linked git
worktree — a mid-session `cd` into a worktree re-roots PROJECT_ROOT and must
not start blocking writes to the primary tree.

Also covers the cross-guard interaction: allowing main-tree writes from a
worktree-rooted session must not bypass protected-path-guard.sh's branch
gating of the primary tree's protected paths.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "claude-hooks" / "project-root-guard.sh"
PROTECTED_GUARD = REPO_ROOT / "scripts" / "claude-hooks" / "protected-path-guard.sh"

# Prefixes the guard always allows — fixtures must live elsewhere, or the
# deny-path assertions would silently degrade into allow-path ones.
ALWAYS_ALLOWED = ("/tmp/", "/private/tmp/", "/var/folders/")


def _fixture_root() -> Path:
    for base in (os.environ.get("RUNNER_TEMP"), "/var/tmp"):
        if not base:
            continue
        # Resolve symlinks (macOS /var -> /private/var) so fixture paths match
        # the realpaths git reports for worktree common dirs.
        resolved = Path(base).resolve()
        if not (str(resolved) + "/").startswith(ALWAYS_ALLOWED):
            return Path(tempfile.mkdtemp(prefix="root-guard.", dir=resolved)).resolve()
    raise RuntimeError("no fixture base outside the guard's always-allowed prefixes")


@pytest.fixture()
def make_root():
    created: list[Path] = []

    def make() -> Path:
        d = _fixture_root()
        created.append(d)
        return d

    yield make
    for d in created:
        shutil.rmtree(d, ignore_errors=True)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _make_worktree(main: Path, wt_parent: Path) -> Path:
    """Init a git repo at `main` and link a worktree under `wt_parent`."""
    _git(main, "init")
    _git(main, "config", "user.email", "test@example.com")
    _git(main, "config", "user.name", "test")
    _git(main, "commit", "--allow-empty", "-m", "init")
    worktree = wt_parent / "wt"
    _git(main, "worktree", "add", str(worktree), "-b", "wt-branch")
    return worktree


def run_guard(
    target: str,
    *,
    root: Path,
    home: Path,
    extra_env: dict[str, str] | None = None,
    guard: Path = GUARD,
) -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": target}})
    env = os.environ.copy()
    # The invoking session's own exemptions must not leak into the fixtures.
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("DIGI_ALLOW_PROTECTED", None)
    env["HOME"] = str(home)
    env["DIGI_PROJECT_ROOT"] = str(root)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(guard)],
        input=payload,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_allows_write_inside_project_root(make_root):
    root, home = make_root(), make_root()
    res = run_guard(str(root / "digibase" / "core.py"), root=root, home=home)
    assert res.returncode == 0, res.stderr


def test_resolves_relative_target_against_project_root(make_root):
    root, home = make_root(), make_root()
    res = run_guard("digibase/core.py", root=root, home=home)
    assert res.returncode == 0, res.stderr


def test_denies_write_outside_project_root(make_root):
    root, home, elsewhere = make_root(), make_root(), make_root()
    res = run_guard(str(elsewhere / "notes.md"), root=root, home=home)
    assert res.returncode == 2
    assert "outside the digithings project root" in res.stderr


def test_allows_plans_dir(make_root):
    root, home = make_root(), make_root()
    res = run_guard(str(home / ".claude" / "plans" / "plan.md"), root=root, home=home)
    assert res.returncode == 0, res.stderr


def test_allows_per_project_persistent_memory(make_root):
    root, home = make_root(), make_root()
    memory = home / ".claude" / "projects" / "-Users-x-Code-digithings" / "memory"
    for target in (memory / "MEMORY.md", memory / "polars-only.md"):
        res = run_guard(str(target), root=root, home=home)
        assert res.returncode == 0, res.stderr


def test_denies_claude_projects_paths_outside_memory(make_root):
    root, home = make_root(), make_root()
    target = home / ".claude" / "projects" / "-Users-x-Code-digithings" / "transcript.jsonl"
    res = run_guard(str(target), root=root, home=home)
    assert res.returncode == 2


def test_denies_claude_config_outside_projects(make_root):
    root, home = make_root(), make_root()
    res = run_guard(str(home / ".claude" / "settings.json"), root=root, home=home)
    assert res.returncode == 2


def test_allows_session_project_dir_after_reroot(make_root):
    """CLAUDE_PROJECT_DIR (pinned by Claude Code) stays writable after a `cd`."""
    session_dir, cwd_root, home = make_root(), make_root(), make_root()
    res = run_guard(
        str(session_dir / "README.md"),
        root=cwd_root,
        home=home,
        extra_env={"CLAUDE_PROJECT_DIR": str(session_dir)},
    )
    assert res.returncode == 0, res.stderr


def test_worktree_rooted_guard_allows_main_tree(make_root):
    """Guard re-rooted into a linked worktree still allows the primary tree."""
    main, wt_parent, home = make_root(), make_root(), make_root()
    worktree = _make_worktree(main, wt_parent)

    res = run_guard(str(main / "digibase" / "core.py"), root=worktree, home=home)
    assert res.returncode == 0, res.stderr

    # Unrelated paths stay blocked even with the worktree root in play.
    res = run_guard(str(home / "elsewhere.md"), root=worktree, home=home)
    assert res.returncode == 2


def test_protected_paths_span_primary_tree_from_worktree(make_root):
    """Allowing main-tree writes from a worktree must not bypass branch gating.

    protected-path-guard.sh must deny an edit to the primary tree's
    .github/workflows/ when the worktree's checkout is not on a
    properly-named branch (wt-branch here).
    """
    main, wt_parent, home = make_root(), make_root(), make_root()
    worktree = _make_worktree(main, wt_parent)

    target = str(main / ".github" / "workflows" / "ci.yml")
    res = run_guard(target, root=worktree, home=home, guard=PROTECTED_GUARD)
    assert res.returncode == 2
    assert "protected" in res.stderr

    # On a properly-named branch the same edit is allowed.
    _git(worktree, "checkout", "-b", "task/1-test")
    res = run_guard(target, root=worktree, home=home, guard=PROTECTED_GUARD)
    assert res.returncode == 0, res.stderr
