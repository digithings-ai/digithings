"""Unit tests for SitaasLimits — defaults, YAML, and env-var overrides."""

from __future__ import annotations

from pathlib import Path

import pytest

from digigraph.project_config import DigiProjectConfig, SitaasLimits


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sitaas_limits_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """SitaasLimits fields use specified defaults when no YAML or env overrides present."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    limits = SitaasLimits.from_config({})
    assert limits.max_rows_per_fetch == 1000
    assert limits.dataset_size_cap_mb == 50.0
    assert limits.data_engineer_timeout_s == 120


# ---------------------------------------------------------------------------
# YAML overrides
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sitaas_limits_yaml_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """YAML limits: block overrides defaults."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    data = {
        "limits": {
            "max_rows_per_fetch": 500,
            "dataset_size_cap_mb": 25.0,
            "data_engineer_timeout_s": 60,
        }
    }
    limits = SitaasLimits.from_config(data)
    assert limits.max_rows_per_fetch == 500
    assert limits.dataset_size_cap_mb == 25.0
    assert limits.data_engineer_timeout_s == 60


# ---------------------------------------------------------------------------
# Env-var overrides (highest precedence)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_sitaas_limits_env_override_max_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """DIGI_MAX_ROWS_PER_FETCH env var overrides both default and YAML value."""
    monkeypatch.setenv("DIGI_MAX_ROWS_PER_FETCH", "250")
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    limits = SitaasLimits.from_config({"limits": {"max_rows_per_fetch": 800}})
    assert limits.max_rows_per_fetch == 250  # env beats yaml


@pytest.mark.unit
def test_sitaas_limits_env_override_size_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """DIGI_DATASET_SIZE_CAP_MB env var overrides the YAML value."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.setenv("DIGI_DATASET_SIZE_CAP_MB", "10.5")
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    limits = SitaasLimits.from_config({})
    assert limits.dataset_size_cap_mb == pytest.approx(10.5)


@pytest.mark.unit
def test_sitaas_limits_env_override_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """DIGI_DATA_ENGINEER_TIMEOUT env var overrides the YAML value."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.setenv("DIGI_DATA_ENGINEER_TIMEOUT", "45")

    limits = SitaasLimits.from_config({"limits": {"data_engineer_timeout_s": 90}})
    assert limits.data_engineer_timeout_s == 45  # env beats yaml


# ---------------------------------------------------------------------------
# Integration with DigiProjectConfig.get_limits()
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_digi_project_config_get_limits_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """DigiProjectConfig.get_limits() returns a SitaasLimits with defaults when no limits: key."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    cfg = DigiProjectConfig({})
    limits = cfg.get_limits()
    assert isinstance(limits, SitaasLimits)
    assert limits.max_rows_per_fetch == 1000
    assert limits.dataset_size_cap_mb == 50.0
    assert limits.data_engineer_timeout_s == 120


@pytest.mark.unit
def test_digi_project_config_get_limits_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """DigiProjectConfig.get_limits() reads limits: block from digiproject.yaml."""
    monkeypatch.delenv("DIGI_MAX_ROWS_PER_FETCH", raising=False)
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    cfg_file = tmp_path / "digiproject.yaml"
    cfg_file.write_text(
        "project:\n  name: test\nlimits:\n  max_rows_per_fetch: 200\n  dataset_size_cap_mb: 5.0\n  data_engineer_timeout_s: 30\n"
    )
    cfg = DigiProjectConfig.load(str(cfg_file))
    limits = cfg.get_limits()
    assert limits.max_rows_per_fetch == 200
    assert limits.dataset_size_cap_mb == pytest.approx(5.0)
    assert limits.data_engineer_timeout_s == 30


@pytest.mark.unit
def test_digi_project_config_get_limits_env_wins_over_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Env vars take precedence over the limits: YAML block in DigiProjectConfig."""
    monkeypatch.setenv("DIGI_MAX_ROWS_PER_FETCH", "99")
    monkeypatch.delenv("DIGI_DATASET_SIZE_CAP_MB", raising=False)
    monkeypatch.delenv("DIGI_DATA_ENGINEER_TIMEOUT", raising=False)

    cfg_file = tmp_path / "digiproject.yaml"
    cfg_file.write_text("project:\n  name: test\nlimits:\n  max_rows_per_fetch: 500\n")
    cfg = DigiProjectConfig.load(str(cfg_file))
    limits = cfg.get_limits()
    assert limits.max_rows_per_fetch == 99
