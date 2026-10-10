"""Both-sides tests for the DCO sign-off carve-out for pre-2026-10-04 commits.

DIG-1369 step 1. ``CONTRIBUTING.md`` promises the sign-off rule "applies from
2026-10-04 forward. Commits before that date are not retro-signed", so the DCO
job must not demand a trailer the project has promised not to ask for.

These tests execute the *real* ``run:`` block extracted from the shipped
workflow against a real git repository built with crafted author dates. The
carve-out is deliberately NOT reimplemented here: a workflow change that alters
the behaviour fails these tests, and a test that only asserted on YAML source
text would pin nothing.

DIG-1369: "Add a test case both sides of the date - this is the part that
regresses if untested." Both sides are covered, plus the boundary.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

WORKFLOW = (
    Path(__file__).resolve().parents[2] / ".github/workflows/ci-dco-sign-off.yml"
)
STEP_NAME = "Check every commit for Signed-off-by"
CUTOFF_UTC = datetime(2026, 10, 4, tzinfo=timezone.utc)
CUTOFF_EPOCH = int(CUTOFF_UTC.timestamp())
DAY = 86_400


def _run_block() -> str:
    """Return the one shell step that does the check."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow["jobs"]["dco-sign-off"]["steps"]
    named = [s for s in steps if s.get("name") == STEP_NAME]
    # Positive control: if this ever matches zero or many, the extraction below
    # would silently start testing the wrong script.
    assert len(named) == 1, f"expected exactly one {STEP_NAME!r} step, got {len(named)}"
    return named[0]["run"]


def _render(base: str, head: str) -> str:
    """Substitute the GitHub-context expressions the runner would have expanded."""
    script = _run_block()
    substitutions = {
        "${{ github.event_name }}": "pull_request",
        "${{ github.event.pull_request.base.sha }}": base,
        "${{ github.event.pull_request.head.sha }}": head,
    }
    for expression, value in substitutions.items():
        assert expression in script, f"{expression} is gone; the test would not exercise it"
        script = script.replace(expression, value)
    # Positive control: an unsubstituted expression would reach bash as a
    # literal and quietly compare the wrong things.
    assert "${{" not in script, "an expression was left unsubstituted"
    return script


def _git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _iso(epoch: int) -> str:
    stamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _commit(repo: Path, name: str, author_epoch: int, *, signoff: bool = False) -> str:
    """Commit with both author and committer date pinned, so only %at matters."""
    (repo / "file.txt").write_text(name)
    _git(repo, "add", "file.txt")
    stamp = _iso(author_epoch)
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = stamp
    env["GIT_COMMITTER_DATE"] = stamp
    args = ["commit", "-q", "-m", f"commit {name}"]
    if signoff:
        args.append("-s")
    _git(repo, *args, env=env)
    return _git(repo, "rev-parse", "HEAD")


def _check(repo: Path, base: str, head: str) -> subprocess.CompletedProcess:
    """Run the shipped script over base..head and return the completed process."""
    script = repo / "dco.sh"
    script.write_text(_render(base, head))
    return subprocess.run(
        ["/bin/bash", str(script)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def _count(output: str, key: str) -> int:
    """Parse checked=N / skipped_pre_cutoff=N as integers, not substrings."""
    match = re.search(rf"\b{key}=(\d+)", output)
    assert match, f"{key}= was not reported in:\n{output}"
    return int(match.group(1))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    work = tmp_path / "repo"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "config", "user.email", "test@example.invalid")
    _git(work, "config", "user.name", "DCO Test")
    return work


@pytest.mark.unit
def test_cutoff_epoch_is_midnight_utc_on_2026_10_04():
    """The constant is the epoch of 2026-10-04T00:00:00Z, not a local midnight."""
    script = _run_block()
    match = re.search(r"^DCO_SIGNOFF_CUTOFF_EPOCH=(\d+)$", script, re.MULTILINE)
    assert match, "the cutoff constant is missing from the script"
    assert int(match.group(1)) == CUTOFF_EPOCH


@pytest.mark.unit
def test_commit_authored_before_the_cutoff_is_not_checked(repo: Path):
    """BEFORE the date: exempt, because the only remedy is the forbidden amendment."""
    base = _commit(repo, "base", CUTOFF_EPOCH - 30 * DAY)
    head = _commit(repo, "old unsigned", CUTOFF_EPOCH - 30 * DAY)

    result = _check(repo, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _count(result.stdout, "checked") == 0
    assert _count(result.stdout, "skipped_pre_cutoff") == 1


@pytest.mark.unit
def test_commit_authored_on_or_after_the_cutoff_still_fails(repo: Path):
    """ON or AFTER the date: the check still applies."""
    base = _commit(repo, "base", CUTOFF_EPOCH)
    head = _commit(repo, "new unsigned", CUTOFF_EPOCH + 5 * DAY)

    result = _check(repo, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert _count(result.stdout, "checked") == 1
    assert _count(result.stdout, "skipped_pre_cutoff") == 0


@pytest.mark.unit
def test_commit_authored_exactly_at_the_cutoff_is_checked(repo: Path):
    """The boundary is inclusive: the cutoff second itself is in scope."""
    base = _commit(repo, "base", CUTOFF_EPOCH - DAY)
    head = _commit(repo, "boundary unsigned", CUTOFF_EPOCH)

    assert _check(repo, base, head).returncode == 1


@pytest.mark.unit
def test_skip_uses_utc_not_the_author_local_timezone(repo: Path):
    """A commit stamped 01:00 +02:00 on the cutoff day is 2026-10-03 in UTC.

    Comparing ISO strings would call it in scope; comparing epochs exempts it.
    """
    one_hour_before_utc_midnight = CUTOFF_EPOCH - 3600
    base = _commit(repo, "base", one_hour_before_utc_midnight - DAY)
    head = _commit(repo, "offset unsigned", one_hour_before_utc_midnight)

    result = _check(repo, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _count(result.stdout, "skipped_pre_cutoff") == 1


@pytest.mark.unit
def test_skipping_one_commit_does_not_hide_a_later_unsigned_commit(repo: Path):
    """A mixed range still fails on the in-scope commit, and reports both counts."""
    base = _commit(repo, "base", CUTOFF_EPOCH - 30 * DAY)
    _commit(repo, "old unsigned", CUTOFF_EPOCH - 10 * DAY)
    head = _commit(repo, "new unsigned", CUTOFF_EPOCH + DAY)

    result = _check(repo, base, head)

    assert result.returncode == 1, result.stdout + result.stderr
    assert _count(result.stdout, "checked") == 1
    assert _count(result.stdout, "skipped_pre_cutoff") == 1


@pytest.mark.unit
def test_a_range_with_nothing_in_scope_says_so_instead_of_claiming_a_pass(repo: Path):
    """Reporting honesty: no commit was checked, so do not claim they were signed."""
    base = _commit(repo, "base", CUTOFF_EPOCH - 30 * DAY)
    head = _commit(repo, "old unsigned", CUTOFF_EPOCH - 2 * DAY)

    result = _check(repo, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "No in-scope commits to check" in result.stdout
    assert "All commits are signed off." not in result.stdout


@pytest.mark.unit
def test_a_signed_in_scope_commit_still_passes(repo: Path):
    """Control: the carve-out did not disable the check."""
    base = _commit(repo, "base", CUTOFF_EPOCH - DAY)
    head = _commit(repo, "new signed", CUTOFF_EPOCH + DAY, signoff=True)

    result = _check(repo, base, head)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _count(result.stdout, "checked") == 1
    assert "All commits are signed off." in result.stdout
