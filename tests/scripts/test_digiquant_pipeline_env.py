from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

R2_SECRETS = (
    "R2_ACCOUNT_ID",
    "R2_BUCKET",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
)

RESEARCH_SCRIPT_PATH = "digiquant/scripts/research/"


def _assert_r2_secrets(env: dict, where: str) -> None:
    for name in R2_SECRETS:
        assert env.get(name) == "${{ secrets." + name + " }}", (
            f"{where}: {name} must be wired from GitHub secrets or the flipped R2 "
            "read raises RuntimeError before it can serve anything"
        )


def test_shared_pipeline_env_flags_r2() -> None:
    spec = yaml.safe_load((REPO_ROOT / ".github" / "digiquant-pipeline.yml").read_text())
    assert spec["env"]["DIGIQUANT_MARKET_DATA_BACKEND"] == "r2"


def test_research_metrics_steps_set_the_backend() -> None:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-research-metrics.yml").read_text()
    )
    steps = [
        step
        for step in spec["jobs"]["refresh"]["steps"]
        if "run" in step and RESEARCH_SCRIPT_PATH in step["run"]
    ]
    assert steps, "no research-script steps matched — the invocation form drifted"
    for step in steps:
        env = step.get("env") or {}
        assert env.get("DIGIQUANT_MARKET_DATA_BACKEND") == "r2", step.get("name")
        _assert_r2_secrets(env, str(step.get("name")))


def test_at_open_job_sets_the_backend_and_r2_secrets() -> None:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    env = spec["jobs"]["at-open"]["env"]
    assert env.get("DIGIQUANT_MARKET_DATA_BACKEND") == "r2"
    _assert_r2_secrets(env, "at-open")
