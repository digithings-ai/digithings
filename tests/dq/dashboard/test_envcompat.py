"""Canonical DIGIQUANT_* env names; retired aliases remain readable."""

from __future__ import annotations

from pathlib import Path

import pytest
from digiquant.olympus.envcompat import (
    ATTEMPT,
    EXECUTION_ROUTING,
    OVERLAY_PERSIST,
    RESEARCH_DATA_TOOLS,
    STAGING_USER_JWT,
    env_lookup,
)
from digiquant.olympus.kairos.policy import routing_enabled, routing_enabled_in
from digiquant.olympus.overlay.persist import overlay_persist_enabled

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_env_lookup_canonical_wins_over_alias() -> None:
    env = {EXECUTION_ROUTING: "0", "OLYMPUS_KAIROS_ROUTING": "1"}
    assert env_lookup(EXECUTION_ROUTING, environ=env) == "0"


def test_env_lookup_alias_when_canonical_absent() -> None:
    env = {"OLYMPUS_KAIROS_ROUTING": "1"}
    assert env_lookup(EXECUTION_ROUTING, environ=env) == "1"


def test_env_lookup_canonical_empty_does_not_fall_through() -> None:
    """An explicit empty canonical keeps the kill switch off."""
    env = {EXECUTION_ROUTING: "", "OLYMPUS_KAIROS_ROUTING": "1"}
    assert env_lookup(EXECUTION_ROUTING, environ=env) == ""


def test_env_lookup_default_when_neither_present() -> None:
    assert env_lookup(RESEARCH_DATA_TOOLS, environ={}, default="1") == "1"


def test_routing_enabled_reads_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_KAIROS_ROUTING", raising=False)
    monkeypatch.setenv(EXECUTION_ROUTING, "1")
    assert routing_enabled() is True
    monkeypatch.delenv(EXECUTION_ROUTING, raising=False)
    assert routing_enabled() is False


def test_routing_enabled_in_still_accepts_retired_alias() -> None:
    assert routing_enabled_in({"OLYMPUS_KAIROS_ROUTING": "1"}) is True
    assert routing_enabled_in({EXECUTION_ROUTING: "1"}) is True
    assert routing_enabled_in({}) is False


def test_overlay_persist_reads_canonical_and_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    monkeypatch.delenv(OVERLAY_PERSIST, raising=False)
    assert overlay_persist_enabled() is False
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    assert overlay_persist_enabled() is True
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    monkeypatch.setenv(OVERLAY_PERSIST, "1")
    assert overlay_persist_enabled() is True


def test_staging_jwt_alias() -> None:
    env = {"KAIROS_STAGING_USER_JWT": "jwt-from-alias"}
    assert env_lookup(STAGING_USER_JWT, environ=env) == "jwt-from-alias"
    env = {STAGING_USER_JWT: "jwt-canonical", "KAIROS_STAGING_USER_JWT": "jwt-from-alias"}
    assert env_lookup(STAGING_USER_JWT, environ=env) == "jwt-canonical"


def test_attempt_alias_for_house_workflow_export() -> None:
    """pipeline-olympus.yml still exports OLYMPUS_ATTEMPT; do not rename that file today."""
    env = {"OLYMPUS_ATTEMPT": "3"}
    assert env_lookup(ATTEMPT, environ=env) == "3"


def test_operator_scripts_use_digiquant_prefix() -> None:
    scripts = REPO_ROOT / "scripts"
    expected = (
        "digiquant_cron_check.py",
        "digiquant_route_cron.py",
        "digiquant_staging_e2e.py",
        "digiquant_house_pipeline_proof.py",
        "digiquant_pages_dashboard_gate.py",
        "digiquant_seal_byok.py",
        "digiquant_apply_vendor_secrets.py",
    )
    for name in expected:
        assert (scripts / name).is_file(), name
    # GHA ``kairos-cron-check.yml`` is protected on cursor/*; wrapper stays until
    # a feat/ hop renames the workflow.
    leftover = [p.name for p in scripts.glob("kairos_*.py") if p.name != "kairos_cron_check.py"]
    assert leftover == [], leftover
    assert (scripts / "kairos_cron_check.py").is_file()


def test_cron_probe_workflow_keeps_house_pipeline_separate() -> None:
    installed = REPO_ROOT / ".github" / "workflows" / "kairos-cron-check.yml"
    spec = (
        REPO_ROOT / "docs" / "agent-backlog" / "kairos-tenancy" / "kairos-cron-check.workflow.yml"
    )
    assert installed.is_file()
    assert spec.is_file()
    blob = installed.read_text(encoding="utf-8")
    assert "pipeline-olympus.yml" in blob
    assert "scripts/kairos_cron_check.py" in blob or "scripts/digiquant_cron_check.py" in blob
