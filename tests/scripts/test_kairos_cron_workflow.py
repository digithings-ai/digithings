"""Kairos cron GHA spec is probe-only and stays off the house pipeline.

Overlay ``usage.start`` is process-global, so overlay / kairos sync / Mailgun
must never share ``pipeline-olympus.yml``'s Hermes chain job. The spec in
``docs/agent-backlog/kairos-tenancy/kairos-cron-check.workflow.yml`` is
fail-closed ``--check`` / ``--dry-run`` only: ``--execute``, ``--all``, and
``hermes.chain`` on that job would be a production apply against Observer.

``cursor/*`` branches cannot write ``.github/workflows/``. Copy the spec onto
a ``chore/`` or ``feat/`` branch as ``kairos-cron-check.yml``. If that file
exists, it must match the spec byte-for-byte.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
SPEC = REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "kairos-cron-check.workflow.yml"
INSTALLED = WORKFLOW_DIR / "kairos-cron-check.yml"
HOUSE = WORKFLOW_DIR / "pipeline-olympus.yml"
MAILGUN_FRAGMENT = (
    REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "pipeline-olympus-mailgun.env.yml"
)
MAILGUN_KEYS = ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "NOTIFY_FROM")

FORBIDDEN_APPLY = ("--execute", "--all", "hermes.chain")


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


class TestKairosCronSpecIsProbeOnly:
    def test_spec_file_exists(self) -> None:
        assert SPEC.is_file()

    def test_schedule_is_offset_from_house(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        crons = [entry["cron"] for entry in _triggers(doc)["schedule"]]
        assert crons == ["15 12 * * *"]
        house = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
        house_crons = [entry["cron"] for entry in _triggers(house)["schedule"]]
        assert "0 12 * * *" in house_crons
        assert "0 12 * * *" not in crons

    def test_permissions_are_contents_read_only(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        assert doc["permissions"] == {"contents": "read"}

    def test_no_environment_gate(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        for name, job in doc["jobs"].items():
            assert "environment" not in job, name

    def test_timeout_and_concurrency_are_set(self) -> None:
        doc = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
        assert doc["concurrency"]["group"] == "kairos-cron-check"
        assert doc["concurrency"]["group"] != "olympus-pipeline"
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
        assert "scripts/kairos_cron_check.py" in blob
        assert "digiquant.olympus.overlay --dry-run" in blob
        assert "digiquant.olympus.kairos.sync_cron --dry-run" in blob
        assert "digiquant.olympus.kairos.route_cron --dry-run" in blob
        for token in FORBIDDEN_APPLY:
            assert token not in blob, token

    def test_install_stays_off_the_graph(self) -> None:
        blob = _blob(SPEC)
        assert "--package digiquant" in blob
        assert "--all-extras" not in blob
        assert "nautilus" not in blob.lower()

    def test_installed_workflow_matches_spec_when_present(self) -> None:
        if not INSTALLED.is_file():
            return
        assert INSTALLED.read_text(encoding="utf-8") == SPEC.read_text(encoding="utf-8")


class TestHousePipelineDoesNotRunOverlay:
    def test_house_run_scripts_omit_kairos_and_overlay(self) -> None:
        blob = _blob(HOUSE)
        assert "digiquant.olympus.hermes.chain" in blob
        assert "olympus.overlay" not in blob
        assert "kairos.sync_cron" not in blob
        assert "kairos.route_cron" not in blob
        assert "kairos_cron_check" not in blob
        assert "notify.dispatch" not in blob


def _house_chain_step_env() -> dict[str, object]:
    doc = yaml.safe_load(HOUSE.read_text(encoding="utf-8"))
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            if "hermes.chain" in str(step.get("run") or ""):
                env = step.get("env") or {}
                assert isinstance(env, dict)
                return env
    raise AssertionError("house hermes.chain step not found")


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
