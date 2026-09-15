from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _steps() -> list[dict]:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    return [step for job in spec["jobs"].values() for step in job.get("steps", [])]


def test_technicals_writer_is_gone() -> None:
    assert not [s for s in _steps() if "compute-technicals" in str(s.get("run", ""))]


def test_intraday_supabase_writer_is_retired() -> None:
    """Same-day opens now live-fetch (#4053) — the intraday writer is gone."""
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    intraday_steps = spec["jobs"]["intraday"].get("steps", [])
    assert not [
        s
        for s in intraday_steps
        if "fetch-quotes" in str(s.get("run", "")) and "--supabase" in str(s.get("run", ""))
    ], "intraday fetch-quotes --supabase writer is retired (#4053)"


def test_any_remaining_quotes_supabase_write_is_run_writers_gated() -> None:
    """The only fetch-quotes --supabase left is the paused eod-macro sector refresh."""
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    for job_name, job in spec["jobs"].items():
        for step in job.get("steps", []) or []:
            run = str(step.get("run", ""))
            if "fetch-quotes" in run and "--supabase" in run:
                assert "run_writers" in str(step.get("if", "")), (
                    f"{job_name}/{step.get('name')}: ungated fetch-quotes --supabase "
                    "write on cadence (#4053)"
                )
