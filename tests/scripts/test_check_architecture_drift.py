"""`check_architecture_drift.py` must flag real drift and only real drift (#3525).

The heuristic proposes, never fails: a module is a candidate only when its
public-interface paths moved at least ``min_lag_days`` after its
``ARCHITECTURE.md`` did, within the lookback window. These tests build a tiny
throwaway git repo with a drifted module, a maintained one, and an unmonitored
one, so the git interaction (``--since`` window, committer dates) is exercised
for real rather than mocked.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_architecture_drift.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_architecture_drift", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve cls.__module__ via sys.modules
    spec.loader.exec_module(module)
    return module


def _stamp(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _commit(repo: Path, when: str) -> None:
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, env=env)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "-m",
            f"change at {when}",
        ],
        cwd=repo,
        check=True,
        env=env,
    )


@pytest.fixture
def drift_repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not on PATH")
    repo = tmp_path / "repo"
    for module in ("diga", "digb", "digc"):
        (repo / module / "src" / module).mkdir(parents=True)

    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init", "-q"],
        cwd=repo,
        check=True,
    )
    # Docs start old, each in its own commit; then the interfaces move.
    for module in ("diga", "digb", "digc"):
        (repo / module / "ARCHITECTURE.md").write_text(f"# {module}\n", encoding="utf-8")
        _commit(repo, _stamp(60))

    (repo / "diga" / "src" / "diga" / "__init__.py").write_text("A = 1\n", encoding="utf-8")
    _commit(repo, _stamp(2))  # diga: interface 2d ago, doc 60d ago → drift

    (repo / "digb" / "src" / "digb" / "__init__.py").write_text("B = 1\n", encoding="utf-8")
    _commit(repo, _stamp(10))
    (repo / "digb" / "ARCHITECTURE.md").write_text("# digb updated\n", encoding="utf-8")
    _commit(repo, _stamp(1))  # digb: doc after interface → maintained

    # digc keeps only a doc and no interface paths → unmonitored.
    (repo / "digc" / "ARCHITECTURE.md").write_text("# digc\n\nnote\n", encoding="utf-8")
    _commit(repo, _stamp(5))
    return repo


def _run(repo: Path) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--window-days",
            "30",
            "--min-lag-days",
            "3",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_flags_only_the_drifted_module(drift_repo: Path) -> None:
    data = _run(drift_repo)
    flagged = {f["module"] for f in data["findings"]}
    assert "diga" in flagged
    assert "digb" not in flagged
    assert "digc" in data["modules_unmonitored"]


def test_never_edits_the_doc(drift_repo: Path) -> None:
    before = (drift_repo / "diga" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    _run(drift_repo)
    after = (drift_repo / "diga" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    assert before == after


def test_is_candidate_lag_and_direction() -> None:
    drift = _load_module()
    now = 1_000_000_000
    assert drift.is_candidate(now, now - 4 * 86_400, 3)
    assert not drift.is_candidate(now, now - 1 * 86_400, 3)  # doc followed within lag
    assert not drift.is_candidate(now, now + 86_400, 3)  # doc after the interface
    assert not drift.is_candidate(None, now, 3)
    assert drift.is_candidate(now, None, 3)  # interface moved, doc has no history
