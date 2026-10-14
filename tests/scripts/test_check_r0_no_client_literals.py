"""Guard tests for scripts/check_r0_no_client_literals.py (DIG-3689)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_r0_no_client_literals import (  # noqa: E402
    census,
    check,
    is_r0,
    matching_lines,
)


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_patterns_fire_on_each_literal_with_case_variants(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "apps/digichat/src/lib/probe.ts",
        "DataTap\nSITAAS\nZammad\nocc_help\nonline-compliance\nhelp.online\n",
    )
    assert len(matching_lines(path)) == 6


def test_patterns_do_not_fire_on_clean_text(tmp_path: Path) -> None:
    # Positive control that the matcher runs in this file: the line below
    # carries a literal, so a zero elsewhere is a real negative.
    _write(tmp_path, "apps/digichat/src/lib/probe.ts", "DataTap\n")
    clean = _write(tmp_path, "digibase/src/digibase/clean.py", "data tap\ndatabase\n")
    assert matching_lines(clean) == []
    assert len(matching_lines(tmp_path / "apps/digichat/src/lib/probe.ts")) == 1


def test_space_and_hyphen_variants_are_caught(tmp_path: Path) -> None:
    assert len(matching_lines(_write(tmp_path, "a.md", "OCC help\n"))) == 1
    assert len(matching_lines(_write(tmp_path, "b.md", "occ-help\n"))) == 1


def test_r0_classification() -> None:
    assert is_r0("apps/digichat/ARCHITECTURE.md")
    assert is_r0("config/contract/contract.yaml")
    assert is_r0("digisearch/ARCHITECTURE.md")
    assert is_r0("scripts/check_r0_no_client_literals.py")
    assert not is_r0("apps/dashboard-api/src/index.ts")
    assert not is_r0("apps/digithings-stack-cloudflare/src/index.ts")
    assert not is_r0("apps/digichat/config/examples/occ-embed.yaml")
    assert not is_r0("docs/superpowers/plans/2026-09-10-cloudflare-v2-phase0-stranded-work.md")
    # Unmapped paths default to R0 (public by default) until mapped.
    assert is_r0("apps/brand-new-surface/index.ts")


def test_binary_files_are_skipped(tmp_path: Path) -> None:
    path = tmp_path / "asset.png"
    path.write_bytes(b"\x89PNG\x00datatap\x00\x01\x02")
    assert matching_lines(path) == []


def test_baseline_mechanics_new_increased_stale(tmp_path: Path) -> None:
    _write(tmp_path, "apps/digichat/ARCHITECTURE.md", "DataTap\n")
    found = census(tmp_path)
    assert list(found) == ["apps/digichat/ARCHITECTURE.md"]

    baseline = {"apps/digichat/ARCHITECTURE.md": {"count": 1, "ticket": "DIG-x"}}
    assert check(found, baseline) == []

    assert len(check(found, {})) == 1  # new path without an entry fails

    grown = {"apps/digichat/ARCHITECTURE.md": {"count": 2, "ticket": "DIG-x"}}
    assert len(check(found, grown)) == 1  # count moved, fails either way

    assert len(check({}, baseline)) == 1  # entry with no hits is stale


def test_shipped_baseline_is_consistent() -> None:
    root = Path(__file__).resolve().parents[2]
    baseline_path = root / "scripts" / "r0_client_literals_baseline.json"
    assert baseline_path.exists()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["entries"]
    assert len(baseline) > 0
    found = census(root)
    assert check(found, baseline) == []
