from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_shared_pipeline_env_flags_r2() -> None:
    spec = yaml.safe_load((REPO_ROOT / ".github" / "digiquant-pipeline.yml").read_text())
    assert spec["env"]["DIGIQUANT_MARKET_DATA_BACKEND"] == "r2"


def test_research_metrics_steps_set_the_backend() -> None:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-research-metrics.yml").read_text()
    )
    for step in spec["jobs"]["refresh"]["steps"]:
        env = step.get("env") or {}
        if "run" in step and "python digiquant/scripts/research/" in step["run"]:
            assert env.get("DIGIQUANT_MARKET_DATA_BACKEND") == "r2", step.get("name")
