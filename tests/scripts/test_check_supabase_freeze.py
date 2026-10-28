"""Tests for scripts/check_supabase_freeze.py (DIG-2887 S0).

Synthetic git repositories only: no network, no Supabase, no real project ids.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_supabase_freeze import (  # noqa: E402
    BASELINE_REL,
    count_markers,
    in_scope,
    main,
)

OLD = "apps/example/src/old.ts"
NEW = "apps/example/src/new.ts"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "develop")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _write(root, OLD, "const url = env.SUPABASE_URL;\nfetch(`${url}/rest/v1/rows`);\n")
    _write(root, "apps/example/src/clean.ts", "export const ok = 1;\n")
    _git(root, "add", "-A")
    assert main(["--root", str(root), "--write-baseline"]) == 0
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def _commit(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "change")


def test_markers_counted():
    assert count_markers("SUPABASE_URL CORE_SUPABASE_SERVICE_KEY") == 2
    assert count_markers('host = "abc.supabase.co"') == 1
    assert count_markers('import { createClient } from "@supabase/supabase-js"') == 1
    assert count_markers("from supabase import create_client\n") == 1
    assert count_markers("from digiquant.supabase_io import write\n") == 1
    assert count_markers("export const ok = 1;\n") == 0


def test_scope_skips_docs_and_tests():
    assert in_scope("apps/x/src/a.ts")
    assert in_scope("digiquant/src/digiquant/io.py")
    for path in (
        "docs/a.ts",
        "README.md",
        "tests/dq/test_a.py",
        "apps/x/src/a.test.ts",
        "apps/x/test/fakes.ts",
        "digiquant/src/test_thing.py",
        BASELINE_REL,
    ):
        assert not in_scope(path), path


def test_baseline_tree_is_clean(repo: Path):
    assert main(["--root", str(repo), "--base-ref", "develop"]) == 0


def test_new_file_with_usage_fails(repo: Path, capsys):
    _write(repo, NEW, "const k = env.CORE_SUPABASE_SERVICE_KEY;\n")
    _commit(repo)
    assert main(["--root", str(repo)]) == 1
    out = capsys.readouterr().out
    assert f"NEW {NEW}" in out
    assert "CORE_SUPABASE_SERVICE_KEY" not in out  # paths and counts only


def test_grown_file_fails(repo: Path, capsys):
    _write(repo, OLD, (repo / OLD).read_text() + "const k = env.SUPABASE_ANON_KEY;\n")
    _commit(repo)
    assert main(["--root", str(repo)]) == 1
    assert f"GREW {OLD}" in capsys.readouterr().out


def test_new_migration_fails_even_without_markers(repo: Path, capsys):
    rel = "digiquant/supabase/migrations/prod/999_new_table.sql"
    _write(repo, rel, "create table t (id int);\n")
    _commit(repo)
    assert main(["--root", str(repo)]) == 1
    assert f"NEW-MIGRATION {rel}" in capsys.readouterr().out


def test_usage_in_tests_and_docs_is_ignored(repo: Path):
    _write(repo, "tests/test_new.py", "SUPABASE_URL = 'x'\n")
    _write(repo, "docs/plan.md", "SUPABASE_URL\n")
    _commit(repo)
    assert main(["--root", str(repo)]) == 0


def test_removal_passes_and_baseline_can_shrink(repo: Path, capsys):
    _write(repo, OLD, "export const gone = true;\n")
    _commit(repo)
    assert main(["--root", str(repo), "--base-ref", "develop"]) == 0
    assert "can shrink" in capsys.readouterr().out
    assert main(["--root", str(repo), "--write-baseline"]) == 0
    entries = json.loads((repo / BASELINE_REL).read_text())["entries"]
    assert OLD not in entries
    _commit(repo)
    assert main(["--root", str(repo), "--base-ref", "develop~1"]) == 0


def test_allowlisting_new_usage_is_refused(repo: Path, capsys):
    _write(repo, NEW, "const k = env.SUPABASE_URL;\n")
    _git(repo, "add", "-A")  # the gate measures tracked files
    assert main(["--root", str(repo), "--write-baseline"]) == 0
    _commit(repo)
    assert main(["--root", str(repo)]) == 0  # the tree matches its own baseline...
    assert main(["--root", str(repo), "--base-ref", "develop~1"]) == 1  # ...but it grew
    assert f"BASELINE-NEW {NEW}" in capsys.readouterr().out


def test_malformed_baseline_fails_closed(repo: Path):
    (repo / BASELINE_REL).write_text("{not json")
    assert main(["--root", str(repo)]) == 2


def test_repo_tree_is_within_its_baseline():
    """The checked-in baseline matches this repository."""
    assert main([]) == 0
