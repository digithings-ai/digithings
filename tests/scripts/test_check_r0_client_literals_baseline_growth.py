"""Guard tests for scripts/check_r0_client_literals_baseline_growth.py (DIG-4577).

Every fixture is synthetic: the paths are placeholders and the "literal" token
below is not a real client name, so nothing here can leak a client literal.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_r0_client_literals_baseline_growth import (  # noqa: E402
    BASELINE_REL,
    main,
)

#: A synthetic token standing in for a client literal. It must never appear in
#: the gate's output, because the gate prints paths and counts only.
SYNTHETIC_LITERAL = "SYNTHETIC-LITERAL-VALUE"

ONE = "apps/example-service/pkg/one.ts"
TWO = "apps/example-service/pkg/two.ts"


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _write_baseline(root: Path, entries: dict[str, int]) -> None:
    path = root / BASELINE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "_comment": f"synthetic fixture carrying {SYNTHETIC_LITERAL}",
        "entries": {
            rel: {"count": count, "ticket": f"DIG-0000 {SYNTHETIC_LITERAL}"}
            for rel, count in entries.items()
        },
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _init_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "guard@example.invalid")
    _git(root, "config", "user.name", "Guard Test")


def _commit_baseline(root: Path, entries: dict[str, int]) -> str:
    """Write and commit a baseline; returns the commit sha (the base ref)."""
    _write_baseline(root, entries)
    _git(root, "add", BASELINE_REL)
    _git(root, "commit", "-q", "-m", "synthetic baseline")
    return _git(root, "rev-parse", "HEAD").strip()


def _run(root: Path, base_ref: str = "HEAD") -> int:
    return main(["--root", str(root), "--base-ref", base_ref])


def test_new_entry_fails(tmp_path, capsys):
    """A path the base baseline does not list is growth."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 1, TWO: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 1
    assert f"NEW {TWO}" in out
    assert "allowance entry with count 1" in out


def test_grown_file_count_fails(tmp_path, capsys):
    """The file-count summary shows the allowance grew."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 1, TWO: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 1
    assert "the base baseline lists 1 file(s); this branch lists 2 file(s)" in out


def test_raised_per_file_count_fails(tmp_path, capsys):
    """A higher count for a path the base baseline already lists is growth."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 3})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 1
    assert f"GROW {ONE}: baseline count 1 -> 3" in out


def test_shrink_passes(tmp_path, capsys):
    """Removing an allowance entry is the point: it must pass."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1, TWO: 1})
    _write_baseline(tmp_path, {ONE: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 0
    assert "clean" in out


def test_unchanged_passes(tmp_path, capsys):
    """An unchanged allowance passes."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 0
    assert "clean" in out


def test_missing_base_baseline_is_handled_explicitly(tmp_path, capsys):
    """A base branch with no baseline file is a finding, not a tool error."""
    _init_repo(tmp_path)
    (tmp_path / "README.md").write_text("synthetic\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "no baseline")
    _write_baseline(tmp_path, {ONE: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 1
    assert "BASE-MISSING" in out
    assert BASELINE_REL in out
    assert "tool error" not in out


def test_failure_message_says_remove_the_literal_not_allowlist_it(tmp_path, capsys):
    """The failure tells the reader to remove the literal, not allowlist it."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 1, TWO: 1})

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 1
    assert "Remove the offending literal from the source instead of allowlisting it" in out


def test_output_never_prints_a_literal_value(tmp_path, capsys):
    """Only paths and counts leave the gate: no literal value is printed."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    _write_baseline(tmp_path, {ONE: 1, TWO: 1})

    rc = _run(tmp_path)
    captured = capsys.readouterr()

    assert rc == 1
    assert SYNTHETIC_LITERAL not in captured.out
    assert SYNTHETIC_LITERAL not in captured.err


def test_unresolvable_base_ref_fails_closed(tmp_path, capsys):
    """A base ref that does not resolve is a tool error, never a clean tree."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})

    rc = _run(tmp_path, base_ref="origin/no-such-branch")
    out = capsys.readouterr().out

    assert rc == 2
    assert "tool error" in out
    assert "fails closed" in out


def test_malformed_baseline_fails_closed(tmp_path, capsys):
    """A baseline that is not JSON is a tool error, never a clean tree."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    (tmp_path / BASELINE_REL).write_text("not json at all", encoding="utf-8")

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 2
    assert "tool error" in out


def test_missing_head_baseline_fails_closed(tmp_path, capsys):
    """No baseline in the tree under test is a tool error, never a clean tree."""
    _init_repo(tmp_path)
    _commit_baseline(tmp_path, {ONE: 1})
    (tmp_path / BASELINE_REL).unlink()

    rc = _run(tmp_path)
    out = capsys.readouterr().out

    assert rc == 2
    assert "tool error" in out
