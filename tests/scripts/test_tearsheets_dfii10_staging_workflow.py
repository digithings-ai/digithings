"""Pin the DFII10 nightly staging step shape (#4804).

DFII10 feeds the gold_sdca sell mask. The mask itself is built at generate
time in generate_tearsheets.py (shipped builder on delayed closes + staged
DFII10.csv) — never staged, so this pin asserts no mask-building logic in
the workflow step. Fail-closed provenance string (Ruling 1, Task 1b) is
"Sell mask UNAVAILABLE (mask_unavailable: DFII10.csv missing or unreadable
in cache)" — noted here, not asserted (this pin is workflow-only).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

STEP_NAME = "Stage gold real-yield sibling (DFII10)"
MACRO_STEP_NAME = "Stage SDCA macro sibling (M2)"
GOLD_STEP_NAME = "Stage gold/DXY siblings (GLD/UUP)"
GENERATE_STEP_NAME = "Generate tearsheets + push to Supabase"

# Ordered named steps before the DFII10 insertion (additive-only guard).
EXPECTED_NAMED_STEPS = [
    "Install from lockfile",
    "Verify calibrations exist in Supabase",
    "Fetch Coinbase daily OHLCV",
    GOLD_STEP_NAME,
    MACRO_STEP_NAME,
    STEP_NAME,
    GENERATE_STEP_NAME,
    "Update persistent failure issue",
]


def _workflow_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "pipeline-digiquant-tearsheets.yml"
    )


def _workflow() -> dict:
    return yaml.safe_load(_workflow_path().read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    wf = _workflow()
    return [step for job in wf["jobs"].values() for step in job["steps"]]


def _step_by_name(name: str) -> dict:
    for step in _steps():
        if step.get("name") == name:
            return step
    raise AssertionError(f"workflow step {name!r} not found")


def test_dfii10_staging_step_exists_after_macro_step() -> None:
    steps = _steps()
    names = [s.get("name") for s in steps]
    assert STEP_NAME in names
    assert names.index(STEP_NAME) > names.index(MACRO_STEP_NAME)
    assert names.index(STEP_NAME) < names.index(GENERATE_STEP_NAME)


def test_dfii10_staging_step_uses_sealed_panel_mechanism() -> None:
    run = _step_by_name(STEP_NAME).get("run", "")
    assert "export_sdca_macro.py" in run
    assert "--series DFII10" in run
    assert "fredgraph" not in run.lower()
    assert "fred.stlouisfed" not in run
    assert "-f digiquant/scripts/export_sdca_macro.py" in run  # main-lag guard


def test_dfii10_staging_step_builds_no_mask() -> None:
    run = _step_by_name(STEP_NAME).get("run", "")
    assert "build_mask" not in run
    assert "sell_dates" not in run


def test_dfii10_staging_step_adds_no_secrets() -> None:
    step = _step_by_name(STEP_NAME)
    run = step.get("run", "")
    assert "secrets" not in run
    assert "GLOOMBERB" not in run
    assert "API_KEY" not in run
    assert "TOKEN" not in run
    assert "env" not in step


def test_existing_steps_unmodified() -> None:
    names = [s.get("name") for s in _steps() if s.get("name")]
    assert names == EXPECTED_NAMED_STEPS
    macro_run = _step_by_name(MACRO_STEP_NAME).get("run", "")
    assert "export_sdca_macro.py" in macro_run
    gold_run = _step_by_name(GOLD_STEP_NAME).get("run", "")
    assert "fetch-quotes" in gold_run


# Ruling 2 (Plan 17): post-develop-merge the workflow (from develop) can
# invoke `--series DFII10` against a main-pinned export script without DFII10
# support → parser.error exit 2, blocking the whole nightly. The step must
# guard on script series-support and skip-with-warning, never hard-fail.
PROBE = "grep -q '\"DFII10\"' digiquant/scripts/export_sdca_macro.py"


def test_dfii10_staging_step_guards_on_series_support() -> None:
    run = _step_by_name(STEP_NAME).get("run", "")
    assert PROBE in run  # capability probe mirrors the -f main-lag idiom
    assert "skip staging" in run  # skip-with-warning path present
    assert "exit 1" not in run  # never hard-fail


def test_series_support_probe_skips_when_unsupported(tmp_path: Path) -> None:
    # Stub the probe negative: a main-era script without the DFII10 key.
    stub = tmp_path / "export_sdca_macro.py"
    stub.write_text('SERIES_FILES = {"M2SL": "M2SL.csv"}\n', encoding="utf-8")
    negative = subprocess.run(["grep", "-q", '"DFII10"', str(stub)], check=False)
    assert negative.returncode != 0  # skip path taken, step exits 0
    # Positive control: this branch's script carries the DFII10 key.
    script = Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "export_sdca_macro.py"
    positive = subprocess.run(["grep", "-q", '"DFII10"', str(script)], check=False)
    assert positive.returncode == 0
