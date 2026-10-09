"""Pin the GLD/UUP nightly staging step shape (#4804)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

STEP_NAME = "Stage gold/DXY siblings (GLD/UUP)"
BTC_STEP_NAME = "Fetch Coinbase daily OHLCV"


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


def test_gold_staging_step_exists_after_btc_fetch() -> None:
    steps = _steps()
    names = [s.get("name") for s in steps]
    assert STEP_NAME in names
    assert names.index(STEP_NAME) > names.index(BTC_STEP_NAME)


def test_gold_staging_step_uses_plain_stems_with_suffixed_copy() -> None:
    run = _step_by_name(STEP_NAME).get("run", "")
    assert "fetch-quotes" in run
    assert "--tickers GLD,UUP" in run
    fetch_line = next(line for line in run.splitlines() if "fetch-quotes" in line)
    assert "GLD-USD" not in fetch_line
    assert "UUP-USD" not in fetch_line
    assert "cp -f" in run
    assert "GLD-USD.csv" in run
    assert "UUP.csv" in run
    assert "UUP-USD" not in run  # Plan-2: UUP stays plain-stem


def test_gold_staging_step_carries_keying_break_comment() -> None:
    lines = _workflow_path().read_text(encoding="utf-8").splitlines()
    anchor = next(i for i, line in enumerate(lines) if STEP_NAME in line)
    window = "\n".join(lines[anchor : anchor + 12])
    assert "keying" in window


def test_gold_staging_step_adds_no_secrets() -> None:
    step = _step_by_name(STEP_NAME)
    run = step.get("run", "")
    assert "secrets" not in run
    assert "GLOOMBERB" not in run
    assert "API_KEY" not in run
    assert "TOKEN" not in run
    assert "env" not in step


def test_btc_fetch_step_still_present() -> None:
    run = _step_by_name(BTC_STEP_NAME).get("run", "")
    assert "fetch_coinbase.py" in run


def test_m2sl_still_covered_by_macro_script() -> None:
    macro = (
        Path(__file__).resolve().parents[2] / "digiquant" / "scripts" / "export_sdca_macro.py"
    ).read_text(encoding="utf-8")
    assert '"M2SL": "M2SL.csv"' in macro
