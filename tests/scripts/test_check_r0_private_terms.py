"""R0 private-terms guard (#6751).

Every case runs on a synthetic repo with a fake term, so the suite never
spells a real private term in public source.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD = REPO_ROOT / "scripts" / "check_r0_private_terms.py"
FAKE_TERM = "zorblax"

# A stand-in for scripts/split/manifest.py. The guard only calls match_rule(),
# and the real manifest is mono-only, so a stub keeps this suite runnable in R0.
STUB_MANIFEST = """
def match_rule(path):
    if path.startswith(("digigraph/", "scripts/")):
        return ("R0", "open")
    if path.startswith("apps/dashboard/"):
        return ("R3", "private app")
    return None
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "split").mkdir(parents=True)
    (root / "scripts" / "check_r0_private_terms.py").write_text(GUARD.read_text("utf-8"), "utf-8")
    (root / "scripts" / "split" / "manifest.py").write_text(STUB_MANIFEST, "utf-8")
    (root / "digigraph").mkdir()
    (root / "digigraph" / "a.py").write_text(f"x = '{FAKE_TERM}'\ny = 1\n", "utf-8")
    (root / "digigraph" / "clean.py").write_text("z = 2\n", "utf-8")
    (root / "terms.txt").write_text(f"# fake\n{FAKE_TERM}\n", "utf-8")
    git(root, "init", "-q")
    git(root, "add", "-A")
    return root


def run(repo: Path, *extra: str, terms: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["python3", str(repo / "scripts" / "check_r0_private_terms.py"), "--root", str(repo)]
    if terms:
        cmd += ["--terms", str(repo / "terms.txt")]
    return subprocess.run(cmd + list(extra), capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})


def baseline(repo: Path) -> dict[str, int]:
    return json.loads((repo / "scripts" / "r0_private_terms_baseline.json").read_text("utf-8"))["entries"]


def test_write_then_check_is_clean(repo: Path) -> None:
    assert run(repo, "--write-baseline").returncode == 0
    assert baseline(repo) == {"digigraph/a.py": 1}
    out = run(repo)
    assert out.returncode == 0, out.stdout
    assert FAKE_TERM not in out.stdout + out.stderr


def test_new_path_fails(repo: Path) -> None:
    run(repo, "--write-baseline")
    (repo / "digigraph" / "b.py").write_text(FAKE_TERM.upper() + "\n", "utf-8")
    git(repo, "add", "-A")
    out = run(repo)
    assert out.returncode == 1
    assert "NEW digigraph/b.py" in out.stdout
    assert FAKE_TERM not in out.stdout.lower().replace("digigraph", "")


def test_path_name_counts_as_a_line(repo: Path) -> None:
    (repo / "digigraph" / f"{FAKE_TERM}_client.py").write_text("pass\n", "utf-8")
    git(repo, "add", "-A")
    run(repo, "--write-baseline")
    assert baseline(repo)[f"digigraph/{FAKE_TERM}_client.py"] == 1


def test_count_change_and_stale_entry_fail(repo: Path) -> None:
    run(repo, "--write-baseline")
    (repo / "digigraph" / "a.py").write_text(f"{FAKE_TERM}\n{FAKE_TERM}\n", "utf-8")
    assert "COUNT digigraph/a.py: baseline 1, measured 2" in run(repo).stdout
    (repo / "digigraph" / "a.py").write_text("clean\n", "utf-8")
    out = run(repo)
    assert out.returncode == 1
    assert "STALE digigraph/a.py" in out.stdout


def test_growth_against_base_ref_fails(repo: Path) -> None:
    run(repo, "--write-baseline")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")
    (repo / "digigraph" / "b.py").write_text(FAKE_TERM + "\n", "utf-8")
    git(repo, "add", "-A")
    run(repo, "--write-baseline")
    out = run(repo, "--base-ref", "HEAD")
    assert out.returncode == 1
    assert "GROWTH digigraph/b.py: new baseline entry" in out.stdout


def test_missing_base_baseline_is_skipped_but_bad_ref_errors(repo: Path) -> None:
    git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-qm", "base")
    run(repo, "--write-baseline")
    assert run(repo, "--base-ref", "HEAD").returncode == 0
    assert run(repo, "--base-ref", "no-such-ref").returncode == 2


def test_missing_terms_is_a_tool_error(repo: Path) -> None:
    run(repo, "--write-baseline")
    out = run(repo, terms=False)
    assert out.returncode == 2
    assert "no terms" in out.stderr


def test_without_manifest_every_tracked_path_is_public(repo: Path, tmp_path: Path) -> None:
    """In R0 the split tooling is gone, so nothing is mapped away."""
    terms = tmp_path / "outside-terms.txt"
    (repo / "terms.txt").rename(terms)
    (repo / "apps" / "dashboard").mkdir(parents=True)
    (repo / "apps" / "dashboard" / "b.ts").write_text(f"// {FAKE_TERM}\n", "utf-8")
    git(repo, "add", "-A")
    cmd = ["python3", str(repo / "scripts" / "check_r0_private_terms.py"), "--root", str(repo), "--terms", str(terms)]
    with_manifest = subprocess.run(cmd + ["--write-baseline"], capture_output=True, text=True)
    assert with_manifest.returncode == 0
    assert "apps/dashboard/b.ts" not in baseline(repo)
    git(repo, "rm", "-q", "--cached", "scripts/split/manifest.py")
    (repo / "scripts" / "split" / "manifest.py").unlink()
    out = subprocess.run(cmd, capture_output=True, text=True)
    assert out.returncode == 1
    assert "apps/dashboard/b.ts" in out.stdout + out.stderr
