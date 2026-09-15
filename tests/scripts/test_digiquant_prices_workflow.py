from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml"


def _spec() -> dict:
    return yaml.safe_load(_WORKFLOW.read_text())


def _steps(spec: dict | None = None) -> list[dict]:
    spec = spec if spec is not None else _spec()
    return [step for job in spec["jobs"].values() for step in job.get("steps", [])]


def test_technicals_writer_is_gone() -> None:
    assert not [s for s in _steps() if "compute-technicals" in str(s.get("run", ""))]


def test_intraday_job_is_a_minimal_noop() -> None:
    """The retired intraday writer is a landing pad, not a runner-time spend.

    The Worker still dispatches ``mode=intraday`` every 15 minutes; the job must
    not check out, install, or read secrets just to do nothing (#4053).
    """
    job = _spec()["jobs"]["intraday"]
    assert "env" not in job, "the no-op intraday job must not carry secrets"
    steps = job.get("steps", []) or []
    assert not [s for s in steps if "uses" in s], (
        "the no-op intraday job must not use checkout/setup actions"
    )
    runs = " ".join(str(s.get("run", "")) for s in steps)
    assert "fetch-quotes" not in runs
    assert "uv sync" not in runs


def test_any_remaining_supabase_market_write_is_run_writers_gated() -> None:
    """No Supabase market write runs on cadence (#4053).

    The intraday fetch-quotes writer retired with the stripped job; the market
    writers that remain (fx-refresh and the eod-macro fetch-macro step) are the
    run_writers-gated paused remainder and must stay gated.

    ``sync-calendar --supabase`` writes ``trading_calendar`` (not a market table)
    and stays on cadence — it is deliberately not matched here.
    """
    spec = _spec()
    market_writers = ("fetch-macro", "fetch-quotes", "compute-technicals")
    for job_name, job in spec["jobs"].items():
        # fx-refresh gates the whole job (its only step is the writer); the
        # eod-macro fetch-macro step is gated at the step level.
        job_gated = "run_writers" in str(job.get("if", ""))
        for step in job.get("steps", []) or []:
            run = str(step.get("run", ""))
            if "--supabase" in run and any(writer in run for writer in market_writers):
                assert job_gated or "run_writers" in str(step.get("if", "")), (
                    f"{job_name}/{step.get('name')}: ungated Supabase market write "
                    "on cadence (#4053)"
                )
