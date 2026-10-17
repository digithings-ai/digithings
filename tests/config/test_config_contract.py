"""The self-host stack contract must account for every wrangler and compose input.

DIG-2769. The acceptance criterion is "every wrangler binding/var and every
compose env maps to the contract". ``config/contract/check_contract.py`` is the
mechanism; this test is what keeps it honest in CI, because a checker nobody
runs is not a check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_DIR = REPO_ROOT / "config" / "contract"
CHECKER = CONTRACT_DIR / "check_contract.py"
GENERATOR = CONTRACT_DIR / "generate.py"
CONTRACT = CONTRACT_DIR / "contract.yaml"


def run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )


@pytest.mark.skipif(not CHECKER.exists(), reason="config/contract/ not present")
def test_contract_file_exists_and_is_not_empty() -> None:
    assert CONTRACT.exists()
    assert len(CONTRACT.read_text(encoding="utf-8")) > 1000


@pytest.mark.skipif(not CHECKER.exists(), reason="config/contract/ not present")
def test_every_wrangler_and_compose_input_maps_to_the_contract() -> None:
    result = run(CHECKER)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout


@pytest.mark.skipif(not CHECKER.exists(), reason="config/contract/ not present")
def test_the_checker_can_fail() -> None:
    """A checker that only ever passes proves nothing.

    The self-test runs the real check (must pass), then injects an unmapped
    name into each of the four fact sources and requires the check to go red
    naming the sentinel, then requires the tree to come back clean.
    """
    result = run(CHECKER, "--self-test")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SELF-TEST PASS" in result.stdout
    assert result.stdout.count("PROBLEM") == 0


@pytest.mark.skipif(not GENERATOR.exists(), reason="config/contract/ not present")
def test_generated_artefacts_are_current() -> None:
    """Regenerating must be a no-op; a stale artefact is a stale contract."""
    before = {
        path: path.read_bytes()
        for path in sorted((CONTRACT_DIR / "generated").glob("*"))
        if path.is_file()
    }
    assert before, "config/contract/generated/ is empty; run config/contract/generate.py"
    result = run(GENERATOR)
    assert result.returncode == 0, result.stdout + result.stderr
    after = {
        path: path.read_bytes()
        for path in sorted((CONTRACT_DIR / "generated").glob("*"))
        if path.is_file()
    }
    changed = sorted(str(p.relative_to(REPO_ROOT)) for p in after if before.get(p) != after[p])
    assert not changed, f"generated artefacts are stale, re-run generate.py: {changed}"
