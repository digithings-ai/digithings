"""Unit tests for scripts/secrets_audit.py (#4335, #4338)."""

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


def _level_fixture(tmp_path: Path, reads: list[str]) -> dict[str, Path]:
    """A tree whose reads are `reads`, plus one file per level to hand to the CLI."""
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    body = "".join(f"  {name}: ${{{{ secrets.{name} }}}}\n" for name in reads)
    (workflows / "a.yml").write_text(f"env:\n{body}", encoding="utf-8")

    files = {
        "secrets": tmp_path / "secrets.txt",
        "variables": tmp_path / "variables.txt",
        "org": tmp_path / "org.txt",
        "env": tmp_path / "env.txt",
    }
    files["secrets"].write_text("REPO_ONLY\nDUPLICATED\n", encoding="utf-8")
    files["variables"].write_text("VAR_BACKED\n", encoding="utf-8")
    files["org"].write_text("ORG_BACKED\nDUPLICATED\n", encoding="utf-8")
    files["env"].write_text("production:ENV_BACKED\n", encoding="utf-8")
    return files


def _run_levels(files: dict[str, Path], tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(files["secrets"]),
            "--variables-file",
            str(files["variables"]),
            "--org-secrets-file",
            str(files["org"]),
            "--env-secrets-file",
            str(files["env"]),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.unit
def test_classify_levels_splits_explained_unresolved_and_shadowed(audit: object) -> None:
    surface = audit.Surface(
        repo_secrets={"REPO_ONLY", "DUPLICATED"},
        repo_variables={"VAR_BACKED"},
        org_secrets={"ORG_BACKED", "DUPLICATED"},
        environment_secrets={"production": {"ENV_BACKED"}},
    )

    levels = audit.classify_levels(
        {"REPO_ONLY", "VAR_BACKED", "ORG_BACKED", "ENV_BACKED", "DUPLICATED", "PHANTOM"},
        surface,
    )

    assert surface.complete is True
    assert levels.explained == {"VAR_BACKED", "ORG_BACKED", "ENV_BACKED"}
    assert levels.unresolved == {"PHANTOM"}
    assert levels.shadowed == {"DUPLICATED"}


@pytest.mark.unit
def test_surface_incomplete_until_every_level_is_known(audit: object) -> None:
    assert audit.Surface(repo_secrets={"A"}).complete is False
    assert audit.Surface(repo_secrets={"A"}, repo_variables=set()).complete is False
    assert (
        audit.Surface(
            repo_secrets={"A"}, repo_variables=set(), environment_secrets={}, org_secrets=set()
        ).complete
        is True
    )


@pytest.mark.unit
def test_cli_reports_levels_from_files(tmp_path: Path) -> None:
    files = _level_fixture(
        tmp_path, ["REPO_ONLY", "DUPLICATED", "VAR_BACKED", "ORG_BACKED", "ENV_BACKED", "PHANTOM"]
    )

    result = _run_levels(files, tmp_path)

    assert result.returncode == 0, result.stderr
    assert "levels: 1 repo variables, 2 org secrets, 1 environments" in result.stdout
    assert "dead: none" in result.stdout
    assert "unresolved: PHANTOM" in result.stdout
    assert "repo-over-org: DUPLICATED" in result.stdout
    assert "not repo-level: ENV_BACKED, ORG_BACKED, VAR_BACKED" in result.stdout


@pytest.mark.unit
def test_cli_strict_unresolved_needs_every_level_and_fails_on_phantom(tmp_path: Path) -> None:
    files = _level_fixture(tmp_path, ["REPO_ONLY", "PHANTOM"])

    phantom = _run_levels(files, tmp_path, "--strict-unresolved")
    assert phantom.returncode == 1
    assert "PHANTOM" in phantom.stderr

    files["org"].write_text("ORG_BACKED\nDUPLICATED\nPHANTOM\n", encoding="utf-8")
    explained = _run_levels(files, tmp_path, "--strict-unresolved")
    assert explained.returncode == 0, explained.stderr

    offline = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--root",
            str(tmp_path),
            "--secrets-file",
            str(files["secrets"]),
            "--strict-unresolved",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert offline.returncode == 1
    assert "needs every level" in offline.stderr
