"""Unit tests for scripts/secrets_audit.py (#4335)."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "secrets_audit.py"


def _load() -> object:
    spec = importlib.util.spec_from_file_location("secrets_audit", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def audit() -> object:
    return _load()


@pytest.mark.unit
def test_extract_secret_reads_dedupes_and_scans_all_github_yaml(
    audit: object, tmp_path: Path
) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n"
        "  A: ${{ secrets.FRED_API_KEY }}\n"
        "  B: ${{ secrets.CORE_SUPABASE_URL }}\n"
        "  C: ${{ secrets.FRED_API_KEY }}\n"
        "jobs:\n"
        "  x:\n"
        "    secrets: inherit\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    (tmp_path / ".github" / "pipeline.yml").write_text(
        "env:\n  D: ${{ secrets.CORE_SUPABASE_URL }}\n  E: ${{ github.token }}\n",
        encoding="utf-8",
    )
    (tmp_path / "not-github").mkdir()
    (tmp_path / "not-github" / "c.yml").write_text(
        "env:\n  F: ${{ secrets.SHOULD_NOT_BE_SEEN }}\n", encoding="utf-8"
    )

    assert audit.extract_secret_reads(tmp_path) == {
        ".github/pipeline.yml": {"CORE_SUPABASE_URL"},
        ".github/workflows/a.yml": {"FRED_API_KEY", "CORE_SUPABASE_URL"},
    }


@pytest.mark.unit
def test_classify_splits_dead_from_unmanaged_and_drops_implicit(audit: object) -> None:
    report = audit.classify(
        {".github/workflows/a.yml": {"A", "B", "C", "GITHUB_TOKEN"}}, {"A", "B", "D"}
    )

    assert report.dead == {"D"}
    assert report.unmanaged == {"C"}
    assert report.reads == {"A", "B", "C"}


@pytest.mark.unit
def test_cli_strict_exits_nonzero_only_for_dead_secrets(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n  A: ${{ secrets.USED_ONE }}\n  B: ${{ secrets.MISSING_ONE }}\n",
        encoding="utf-8",
    )
    names = tmp_path / "names.txt"
    names.write_text("USED_ONE\nDEAD_ONE\n", encoding="utf-8")

    plain = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--secrets-file", str(names)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert plain.returncode == 0, plain.stderr
    assert "DEAD_ONE" in plain.stdout
    assert "MISSING_ONE" in plain.stdout

    strict = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(names),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert strict.returncode == 1
    assert "DEAD_ONE" in strict.stderr


@pytest.mark.unit
def test_cli_clean_tree_reports_no_drift(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text("env:\n  A: ${{ secrets.ONLY_ONE }}\n", encoding="utf-8")
    names = tmp_path / "names.txt"
    names.write_text("ONLY_ONE\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--secrets-file", str(names)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "dead: none" in result.stdout
    assert "not repo-level: none" in result.stdout


@pytest.mark.unit
def test_reads_ignore_commented_out_names(audit: object, tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n"
        "  # A: ${{ secrets.COMMENTED_OUT }}\n"
        "  B: ${{ secrets.LIVE_ONE }}  # was ${{ secrets.TRAILING_COMMENT }}\n"
        "  C: secrets.BARE_NOT_AN_EXPRESSION\n",
        encoding="utf-8",
    )

    assert audit.reads_in((workflows / "a.yml").read_text(encoding="utf-8")) == {"LIVE_ONE"}


@pytest.mark.unit
def test_cli_strict_ignores_unmanaged_reads(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text(
        "env:\n  A: ${{ secrets.ONLY_ONE }}\n  B: ${{ secrets.MISSING_ONE }}\n",
        encoding="utf-8",
    )
    names = tmp_path / "names.txt"
    names.write_text("ONLY_ONE\n", encoding="utf-8")

    strict = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(names),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert strict.returncode == 0, strict.stderr
    assert "MISSING_ONE" in strict.stdout


@pytest.mark.unit
def test_cli_strict_fails_when_secret_list_unavailable(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "a.yml").write_text("env:\n  A: ${{ secrets.ONLY_ONE }}\n", encoding="utf-8")
    no_path = {**os.environ, "PATH": ""}

    plain = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=no_path,
    )
    assert plain.returncode == 0, plain.stderr
    assert "repo secret list unavailable" in plain.stdout

    strict = subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(tmp_path), "--strict"],
        capture_output=True,
        text=True,
        check=False,
        env=no_path,
    )
    assert strict.returncode == 1
    assert "repo secret list unavailable" in strict.stdout
