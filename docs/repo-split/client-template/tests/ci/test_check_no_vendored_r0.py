"""Tests for scripts/check_no_vendored_r0.py using two throwaway git repos. Offline."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_no_vendored_r0.py"
spec = importlib.util.spec_from_file_location("nv", SCRIPT)
nv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nv)  # type: ignore[union-attr]

BIG = "x = 1\n" * 40  # over MIN_BYTES


def repo(tmp: Path, name: str, files: dict[str, str]) -> Path:
    r = tmp / name
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    for rel, body in files.items():
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        (r / rel).write_text(body)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(r), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        check=True,
    )
    return r


def test_exact_copy_is_caught(tmp_path: Path) -> None:
    r0 = repo(tmp_path, "r0", {"digigraph/loader.py": BIG})
    client = repo(tmp_path, "client", {"tools/mcp/loader.py": BIG})
    assert nv.find_copies(client, r0) == [("tools/mcp/loader.py", "digigraph/loader.py")]


def test_edited_copy_passes(tmp_path: Path) -> None:
    r0 = repo(tmp_path, "r0", {"a.py": BIG})
    client = repo(tmp_path, "client", {"a.py": BIG + "y = 2\n"})
    assert nv.find_copies(client, r0) == []


def test_tiny_and_ignored_files_skipped(tmp_path: Path) -> None:
    r0 = repo(tmp_path, "r0", {"x/.gitkeep": "", "small.txt": "hi\n", "LICENSE": BIG})
    client = repo(tmp_path, "client", {"y/.gitkeep": "", "small.txt": "hi\n", "LICENSE": BIG})
    assert nv.find_copies(client, r0) == []


def test_allowlist_needs_reason(tmp_path: Path) -> None:
    r0 = repo(tmp_path, "r0", {"a.py": BIG})
    client = repo(
        tmp_path,
        "client",
        {"a.py": BIG, ".r0-vendor-allow": "a.py # schema fixture pinned on purpose\n"},
    )
    assert nv.find_copies(client, r0) == []
    (client / ".r0-vendor-allow").write_text("a.py\n")
    with pytest.raises(SystemExit):
        nv.find_copies(client, r0)


def test_r0_template_docs_are_not_vendoring(tmp_path: Path) -> None:
    r0 = repo(tmp_path, "r0", {"docs/repo-split/client-template/Makefile": BIG})
    client = repo(tmp_path, "client", {"Makefile": BIG})
    assert nv.find_copies(client, r0) == []
