"""Guard: exactly one uv.lock in the repo, and it is the repo-root one (DIG-944).

Why this exists
---------------
`digiquant` is a member of the root uv workspace (``[tool.uv.workspace]`` in the
root ``pyproject.toml``), so the root ``uv.lock`` is already authoritative for it.

A member-level ``uv.lock`` is therefore not "extra detail", it is a **second,
independent resolution of the same dependency set**. It is only written by a
human running ``uv sync``/``uv lock`` inside that member directory, so it is
never regenerated on a routine bump and it silently drifts away from the root
lock. Nothing warns: the install succeeds.

That is not hypothetical here. ``digiquant/uv.lock`` was committed once in the
foundation baseline (``bdd425414``) and never touched again. It pinned
nautilus-trader 1.223.0 while the root lock pins 1.230.0. Any developer who
followed the ``cd digiquant && uv run pytest -m unit`` invocation documented in
``digiquant/pyproject.toml`` resolved against the stale lock. DIG-944 deletes
it; these tests stop it coming back.

Scope: this is an *always-green* repo invariant, so it lives in ``tests/baseline``
(marked ``baseline``) rather than in a per-package suite. It must run on every
change, including changes to files that touch no package at all, which is
exactly the path-filtered per-package CI lanes would miss.

Two independent checks, because they fail for different reasons:

- ``test_no_tracked_uv_lock_outside_repo_root`` — a second lock got *committed*.
  Reads ``git ls-files``, so it sees what CI and a reviewer see.
- ``test_no_uv_lock_on_disk_in_a_workspace_member`` — someone ran ``uv sync``
  inside a member directory. Untracked, so only a filesystem walk sees it.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_NAME = "uv.lock"
# The one lock that is allowed to exist, as a repo-relative POSIX path.
ROOT_LOCK = LOCK_NAME
# The member this guard was written for. Asserted explicitly below so the guard
# cannot quietly stop covering the regression it exists for.
SUBJECT_MEMBER = "digiquant"


def workspace_members(repo_root: Path = REPO_ROOT) -> list[str]:
    """Repo-relative directories that are uv workspace members.

    A member is a directory carrying its own ``pyproject.toml``. In this repo
    that set is exactly ``[tool.uv.workspace] members``, and deriving it this
    way means the guard follows the workspace as it grows instead of carrying a
    hand-copied list that silently goes stale.

    Parsed from the filesystem rather than with ``tomllib`` so the guard keeps
    working on the oldest interpreter the suite supports, and so it cannot be
    broken by a malformed or unreadable root ``pyproject.toml`` -- a lock file
    is a filesystem fact, not a TOML one.
    """
    members = [
        entry.name
        for entry in sorted(repo_root.iterdir())
        if entry.is_dir() and (entry / "pyproject.toml").is_file()
    ]
    return members


def stray_locks(tracked: Iterable[str], *, allowed: str = ROOT_LOCK) -> list[str]:
    """Of the given repo-relative paths, the ``uv.lock`` files that are not ``allowed``.

    Pure function of its input so the self-test below can prove it actually
    detects a member lock instead of returning nothing for every input.
    """
    return sorted(
        path
        for path in tracked
        if PurePosixPath(path).name == LOCK_NAME and str(PurePosixPath(path)) != allowed
    )


def tracked_paths(repo_root: Path = REPO_ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [path for path in result.stdout.split("\0") if path]


@pytest.mark.baseline
@pytest.mark.unit
def test_no_tracked_uv_lock_outside_repo_root() -> None:
    """A second uv.lock must never be committed into a workspace member."""
    stray = stray_locks(tracked_paths())
    assert stray == [], (
        "Tracked uv.lock outside the repo root: "
        f"{stray}. Every directory with a pyproject.toml is a member of the root "
        "uv workspace, so the root uv.lock already resolves it. A member lock is "
        "only ever written by a hand-run `uv sync` inside that member, is never "
        "regenerated on a bump, and silently serves stale pins. Delete it and "
        "run `uv lock` at the repo root instead."
    )


@pytest.mark.baseline
@pytest.mark.unit
def test_root_uv_lock_is_tracked() -> None:
    """Positive control: the root lock exists, so the guard above is not vacuous.

    Without this, deleting the root uv.lock as well would make
    ``test_no_tracked_uv_lock_outside_repo_root`` pass for the wrong reason.
    """
    assert (REPO_ROOT / ROOT_LOCK).is_file(), (
        f"{ROOT_LOCK} is missing from the repo root. The root lock is the "
        "authoritative resolution for every workspace member; without it there "
        "is no pinned dependency set at all."
    )
    assert ROOT_LOCK in tracked_paths()


@pytest.mark.baseline
@pytest.mark.unit
def test_no_uv_lock_on_disk_in_a_workspace_member() -> None:
    """No untracked uv.lock sitting in a workspace member directory either.

    This is the shape `cd digiquant && uv sync` leaves behind: the file exists
    on disk and is not in git, so the tracked sweep above cannot see it.
    """
    on_disk = sorted(
        f"{member}/{LOCK_NAME}"
        for member in workspace_members()
        if (REPO_ROOT / member / LOCK_NAME).exists()
    )
    assert on_disk == [], (
        f"uv.lock present inside workspace member(s): {on_disk}. Untracked or "
        "not, a member lock shadows the root lock for anything run from that "
        "directory. Delete it; use `uv run` from the repo root."
    )


@pytest.mark.baseline
@pytest.mark.unit
def test_digiquant_fossil_is_gone() -> None:
    """The specific file DIG-944 deleted must not come back."""
    fossil = REPO_ROOT / SUBJECT_MEMBER / LOCK_NAME
    assert not fossil.exists(), (
        f"{SUBJECT_MEMBER}/{LOCK_NAME} was a fossil: committed once in the "
        "foundation baseline, never regenerated, and pinned "
        "nautilus-trader 1.223.0 against the root lock's 1.230.0."
    )


@pytest.mark.baseline
@pytest.mark.unit
def test_detector_flags_a_workspace_member_lock() -> None:
    """Self-test: prove the detector fires, so the guard is not a no-op.

    A guard test that cannot fail is worse than no guard, because it reads in
    CI as coverage. This pins the detector's contract on both a clean input and
    the exact shape it exists to catch.
    """
    clean = ["uv.lock", "pyproject.toml", "digiquant/pyproject.toml", "digiquant/src/server.py"]
    assert stray_locks(clean) == []

    with_member_lock = clean + [f"{SUBJECT_MEMBER}/{LOCK_NAME}"]
    assert stray_locks(with_member_lock) == [f"{SUBJECT_MEMBER}/{LOCK_NAME}"]

    # A lock nested deeper inside a member is also caught, and is not confused
    # by a file that merely has "uv.lock" in its name.
    nested = clean + ["digiquant/vendor/uv.lock", "digiquant/uv.lock.bak", "scripts/uv-lock.py"]
    assert stray_locks(nested) == ["digiquant/vendor/uv.lock"]


@pytest.mark.baseline
@pytest.mark.unit
def test_workspace_member_discovery_finds_the_subject_member() -> None:
    """The guard is only meaningful if it actually covers `digiquant`."""
    members = workspace_members()
    assert members, "No workspace member discovered; the member sweep would pass vacuously."
    assert SUBJECT_MEMBER in members
