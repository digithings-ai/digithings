"""The self-host stack contract must account for every wrangler and compose input.

DIG-2769. The acceptance criterion is "every wrangler binding/var and every
compose env maps to the contract". ``config/contract/check_contract.py`` is the
mechanism; this test is what keeps it honest in CI, because a checker nobody
runs is not a check.

The contract also *transcribes* live values (``wrangler_values``). Coverage alone
does not notice a transcription that has gone stale, so the last test compares
each transcribed value against the live worker it copies (DIG-3232).
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
import yaml

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


def _live_wrangler_vars() -> dict[str, dict[str, object]]:
    """``{worker name: [vars]}`` read from every live ``apps/*/wrangler.toml``."""
    live: dict[str, dict[str, object]] = {}
    for path in sorted((REPO_ROOT / "apps").glob("*/wrangler.toml")):
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
        worker = str(doc.get("name") or path.parent.name)
        live.setdefault(worker, {}).update(doc.get("vars") or {})
    return live


@pytest.mark.skipif(not CONTRACT.exists(), reason="config/contract/ not present")
def test_contract_wrangler_values_mirror_the_live_workers() -> None:
    """Every transcribed ``wrangler_values`` row must equal the live var it copies.

    ``contract.yaml`` is the source of truth for the schema, but each row also
    transcribes the live value ("copied verbatim from the stack Worker"). An
    unchecked transcription is a copy that can rot: the OCC grounding prompt sat
    at an older revision in the contract than in ``wrangler.toml`` until this
    test existed (DIG-3232).
    """
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    live = _live_wrangler_vars()
    mismatched: list[str] = []
    compared = 0
    for entry in contract["env"]:
        name = entry["name"]
        for worker in entry["sources"]["wrangler_workers"]:
            declared = live.get(worker)
            if not declared or name not in declared:
                continue
            transcribed = (entry.get("wrangler_values") or {}).get(worker)
            if transcribed is None:
                continue
            compared += 1
            if transcribed != declared[name]:
                mismatched.append(
                    f"{worker}.{name}: contract {str(transcribed)[:60]!r} "
                    f"!= live {str(declared[name])[:60]!r}"
                )
    # A comparison that looked at nothing must not pass (DIG-2769 self-test rule).
    assert compared >= 20, f"only {compared} contract values compared; the scan found no work"
    assert not mismatched, "contract values drifted from the live wrangler.toml: " + "; ".join(
        mismatched
    )
