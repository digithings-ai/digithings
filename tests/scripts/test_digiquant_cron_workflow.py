"""execution cron GHA spec is probe-only and stays off the house pipeline.

Overlay ``usage.start`` is process-global, so overlay / execution sync / route /
digest / Mailgun must never share ``pipeline-digiquant.yml``'s portfolio chain job. The spec in
``docs/agent-backlog/kairos-tenancy/kairos-cron-check.workflow.yml`` is
fail-closed ``--check`` / ``--dry-run`` only: ``--execute``, ``--all``, and
``portfolio.chain`` on that job would be a production apply against Observer.

Install is ``.github/workflows/execution-cron-check.yml`` copied from the spec
byte-for-byte. Probe-only (``--check`` / ``--dry-run``); never ``--execute``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SPEC = REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "kairos-cron-check.workflow.yml"
INSTALLED = WORKFLOW_DIR / "execution-cron-check.yml"
HOUSE = WORKFLOW_DIR / "pipeline-digiquant.yml"
JOBS_SOURCE = REPO_ROOT / "frontend" / "digithings-cron" / "src" / "jobs.ts"
MAILGUN_FRAGMENT = (
    REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "pipeline-olympus-mailgun.env.yml"
)
MAILGUN_KEYS = ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "NOTIFY_FROM")

FORBIDDEN_APPLY = ("--execute", "--all", "portfolio.chain")


def _worker_jobs() -> dict[str, str]:
    pairs = re.findall(
        r'(?:wd|rd)\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
        JOBS_SOURCE.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    jobs = dict(pairs)
    assert pairs and len(jobs) == len(pairs), "Worker job IDs must be unique literals"
    return jobs


def _triggers(doc: dict[str | bool, object]) -> dict[str, object]:
    """GitHub ``on:`` becomes YAML 1.1 boolean ``True`` under PyYAML."""
    raw: object
    if "on" in doc:
        raw = doc["on"]
    elif True in doc:
        raw = doc[True]
    else:
        raise AssertionError("workflow missing on:")
    assert isinstance(raw, dict)
    return raw


def _run_scripts(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    scripts: list[str] = []
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if isinstance(step, dict) and isinstance(step.get("run"), str):
                scripts.append(step["run"])
    return scripts


def _blob(path: Path) -> str:
    return "\n".join(_run_scripts(path))


class TestExecutionCronSpecIsProbeOnly:
    def test_spec_file_exists(self) -> None:
        assert SPEC.is_file()

    def test_worker_schedule_is_offset_from_house(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        assert _triggers(doc) == {"workflow_dispatch": None}
        jobs = _worker_jobs()
        crons = [jobs["execution-cron-check"]]
        assert crons == ["15 12 * * *"]
        house_crons = [jobs[f"house-run-{hour:02d}"] for hour in (9, 10, 11, 12)]
        assert house_crons == [
            "17 9 * * 1-5",
            "17 10 * * 1-5",
            "17 11 * * 1-5",
            "17 12 * * 1-5",
        ]
        assert "0 12 * * *" not in house_crons
        assert "0 12 * * *" not in crons
        for cron in house_crons:
            assert cron not in crons

    def test_permissions_are_contents_read_only(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        assert doc["permissions"] == {"contents": "read"}

    def test_no_environment_gate(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        for name, job in doc["jobs"].items():
            assert "environment" not in job, name

    def test_timeout_and_concurrency_are_set(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        assert doc["concurrency"]["group"] == "execution-cron-check"
        assert doc["concurrency"]["group"] != "digiquant-pipeline"
        assert doc["concurrency"]["cancel-in-progress"] is False
        for name, job in doc["jobs"].items():
            assert job.get("timeout-minutes"), name

    def test_does_not_pin_checkout_to_main(self) -> None:
        """Probe code lives on develop; pinning main would run a tree without the CLIs."""
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        for job in doc["jobs"].values():
            for step in job.get("steps", []):
                if not isinstance(step, dict):
                    continue
                uses = str(step.get("uses") or "")
                if uses.startswith("actions/checkout@"):
                    assert step.get("with", {}).get("ref") != "main"

    def test_run_steps_are_check_or_dry_run_only(self) -> None:
        blob = _blob(SPEC)
        assert "scripts/execution_cron_check.py" in blob
        assert "digiquant.dashboard.overlay --dry-run" in blob
        assert "digiquant.execution.sync_cron --dry-run" in blob
        assert "digiquant.execution.route_cron --dry-run" in blob
        assert "digiquant.notify.dispatch --dry-run" in blob
        for token in FORBIDDEN_APPLY:
            assert token not in blob, token

    def test_install_stays_off_the_graph(self) -> None:
        blob = _blob(SPEC)
        assert "--package digiquant" in blob
        assert "--all-extras" not in blob
        assert "nautilus" not in blob.lower()

    def test_installed_workflow_is_present_and_matches_spec(self) -> None:
        assert INSTALLED.is_file()
        assert INSTALLED.read_text(encoding="utf-8") == SPEC.read_text(encoding="utf-8")


class TestHouseScheduleRetriesOffPeak:
    """Same anti-congestion pattern as FX Hub (`17 */2` in pipeline-digiquant-prices)."""

    def test_house_crons_avoid_top_of_hour_and_retry_before_ny_open(self) -> None:
        jobs = _worker_jobs()
        crons = [jobs[f"house-run-{hour:02d}"] for hour in (9, 10, 11, 12)]
        assert crons == [
            "17 9 * * 1-5",
            "17 10 * * 1-5",
            "17 11 * * 1-5",
            "17 12 * * 1-5",
        ]
        for cron in crons:
            minute, _hour, *_rest = cron.split()
            assert minute != "0", cron

    def test_house_accepts_repository_dispatch_watchdog(self) -> None:
        house = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
        triggers = _triggers(house)
        dispatch = triggers.get("repository_dispatch")
        assert isinstance(dispatch, dict)
        types = dispatch.get("types")
        assert types == ["olympus-daily"]

    def test_already_committed_gate_skips_the_llm_job(self) -> None:
        house = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
        jobs = house["jobs"]
        assert "already-committed" in jobs
        run = jobs["run"]
        needs = run["needs"]
        assert "already-committed" in needs
        assert "skip != 'true'" in str(run.get("if") or "")
        gate_blob = "\n".join(
            step["run"]
            for step in jobs["already-committed"].get("steps", [])
            if isinstance(step, dict) and isinstance(step.get("run"), str)
        )
        assert "house_schedule_skip.py" in gate_blob


class TestHousePipelineDoesNotRunOverlay:
    def test_house_run_scripts_omit_execution_and_overlay(self) -> None:
        blob = _blob(HOUSE)
        assert "digiquant.portfolio.chain" in blob
        assert "dashboard.overlay" not in blob
        assert "execution.sync_cron" not in blob
        assert "execution.route_cron" not in blob
        assert "execution_cron_check" not in blob
        assert "notify.dispatch" not in blob


def _house_chain_step_env() -> dict[str, object]:
    doc = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            if "portfolio.chain" in str(step.get("run") or ""):
                env = step.get("env") or {}
                assert isinstance(env, dict)
                return env
    raise AssertionError("house portfolio.chain step not found")


class TestHousePipelineMailgunEnvFragment:
    def test_fragment_is_secrets_only(self) -> None:
        frag = yaml.safe_load(MAILGUN_FRAGMENT.read_text(encoding="utf-8"))
        assert tuple(frag) == MAILGUN_KEYS
        for key, value in frag.items():
            assert isinstance(value, str)
            assert f"secrets.{key}" in value
            assert "sk_" not in value
            assert "key-" not in value

    def test_house_chain_env_absent_or_matches_fragment(self) -> None:
        """cursor/* cannot splice the fragment; when installed it must be complete."""
        env = _house_chain_step_env()
        frag = yaml.safe_load(MAILGUN_FRAGMENT.read_text(encoding="utf-8"))
        present = [key for key in MAILGUN_KEYS if key in env]
        if not present:
            return
        for key in MAILGUN_KEYS:
            assert env[key] == frag[key], key

    def test_docs_name_the_splice_hop(self) -> None:
        unblock = (
            REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "HUMAN-UNBLOCK.md"
        ).read_text(encoding="utf-8")
        assert "pipeline-olympus-mailgun.env.yml" in unblock
        for key in MAILGUN_KEYS:
            assert key in unblock
