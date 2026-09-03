"""Unit tests for scripts/infer_project_fields_row.py.

The stub-tsv workflow (#2476/#2566) and board hygiene both depend on this
label → TSV row mapping. Wrong phase/area/kind/priority/model silently
mis-files Project #1 cards. No prior unit coverage existed.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow — dynamically loaded script module

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "infer_project_fields_row.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("infer_project_fields_row", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _labels(*names: str) -> list[dict[str, str]]:
    return [{"name": n} for n in names]


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load()


@pytest.mark.unit
def test_default_row_is_phase3_cross_cutting_task_p2_sonnet(mod: Any) -> None:
    row = mod.infer_row(42, _labels("agent-task"))
    assert row == (
        "42",
        "Phase 3 — Domain unification",
        "Cross-cutting",
        "Task",
        "P2",
        "sonnet",
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "phase"),
    [
        ("phase-0", "Phase 2 — Hardening"),
        ("phase-2", "Phase 2 — Hardening"),
        ("phase-3", "Phase 3 — Domain unification"),
        ("phase-4", "Phase 4 — research on digigraph"),
        ("phase-5", "Phase 5 — research tiering"),
        ("client-pilot", "Client Pilot"),
    ],
)
def test_phase_labels_map_to_board_phase_strings(
    mod: Any, label: str, phase: str
) -> None:
    row = mod.infer_row(7, _labels(label))
    assert row[1] == phase


@pytest.mark.unit
@pytest.mark.parametrize(
    ("label", "area"),
    [
        ("component:website", "Website"),
        ("component:digichat", "digichat"),
        ("component:digisearch", "digisearch"),
        ("component:digigraph", "digigraph"),
        ("component:digiquant", "digiquant"),
        ("component:digikey", "digikey"),
        ("component:digismith", "digismith"),
    ],
)
def test_component_labels_set_board_area(mod: Any, label: str, area: str) -> None:
    row = mod.infer_row(9, _labels("agent-task", label))
    assert row[2] == area


@pytest.mark.unit
def test_client_pilot_overrides_component_area(mod: Any) -> None:
    """client-pilot wins area even when a component:* label is also present."""
    row = mod.infer_row(11, _labels("client-pilot", "component:digigraph"))
    assert row[1] == "Client Pilot"
    assert row[2] == "Client Pilot"


@pytest.mark.unit
def test_epic_sets_kind_and_p1(mod: Any) -> None:
    row = mod.infer_row(3, _labels("epic", "component:digikey"))
    assert row[3] == "Epic"
    assert row[4] == "P1"


@pytest.mark.unit
def test_phase0_sets_kind_feature_and_p1(mod: Any) -> None:
    row = mod.infer_row(5, _labels("phase-0", "component:website"))
    assert row[1] == "Phase 2 — Hardening"
    assert row[3] == "Feature"
    assert row[4] == "P1"


@pytest.mark.unit
def test_risk_high_selects_opus(mod: Any) -> None:
    row = mod.infer_row(8, _labels("agent-task", "risk:high"))
    assert row[5] == "opus"


@pytest.mark.unit
def test_first_matching_component_wins(mod: Any) -> None:
    """Iteration order is the map's insertion order — website before digichat."""
    row = mod.infer_row(1, _labels("component:digichat", "component:website"))
    assert row[2] == "Website"


@pytest.mark.unit
def test_cli_prints_tab_separated_row(mod: Any) -> None:
    labels = json.dumps(_labels("agent-task", "component:digigraph", "risk:high"))
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "99", labels],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "\t".join(
        ("99", "Phase 3 — Domain unification", "digigraph", "Task", "P2", "opus")
    )


@pytest.mark.unit
def test_cli_usage_on_wrong_argc() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "usage:" in done.stderr
