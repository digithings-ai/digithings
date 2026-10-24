"""DIGIQUANT_CONFIG_DIR resolution + neutral example configs (repo-split 1b)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from digiquant.config_paths import (
    CONFIG_DIR_ENV,
    LEGACY_CONFIG_DIR_ENV,
    config_dir,
    resolve_config_file,
)

pytestmark = pytest.mark.unit


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv(LEGACY_CONFIG_DIR_ENV, raising=False)
    monkeypatch.delenv("DIGIQUANT_RESEARCH_POLICY_PATH", raising=False)


def test_unset_reads_bundled_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    assert config_dir() is None
    bundled = Path("/bundled/research_policy.yaml")
    assert resolve_config_file("research_policy.yaml", bundled) == bundled


def test_canonical_wins_over_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    canon = tmp_path / "canon"
    legacy = tmp_path / "legacy"
    canon.mkdir()
    legacy.mkdir()
    monkeypatch.setenv(CONFIG_DIR_ENV, str(canon))
    monkeypatch.setenv(LEGACY_CONFIG_DIR_ENV, str(legacy))
    assert config_dir() == canon


def test_legacy_alias_still_works(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv(LEGACY_CONFIG_DIR_ENV, str(tmp_path))
    assert config_dir() == tmp_path


def test_blank_counts_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv(CONFIG_DIR_ENV, "   ")
    monkeypatch.setenv(LEGACY_CONFIG_DIR_ENV, "")
    assert config_dir() is None


def test_research_policy_path_uses_config_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _clean_env(monkeypatch)
    from digiquant.dashboard.research_retrieval import planner

    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    assert planner.resolve_research_policy_path() == tmp_path / "research_policy.yaml"


def test_explicit_policy_path_still_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clean_env(monkeypatch)
    from digiquant.dashboard.research_retrieval import planner

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.setenv("DIGIQUANT_RESEARCH_POLICY_PATH", str(other / "custom.yaml"))
    assert planner.resolve_research_policy_path() == other / "custom.yaml"


def test_sector_paths_use_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clean_env(monkeypatch)
    from digiquant.portfolio import sector_map
    from digiquant.research import sectors_config

    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    assert sectors_config._config_path() == tmp_path / "sectors.yaml"
    assert sector_map._asset_classes_path() == tmp_path / "asset_classes.yaml"


def test_pricing_path_uses_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clean_env(monkeypatch)
    from digiquant.research import pricing

    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    assert pricing._config_path() == tmp_path / "digiquant-model-prices.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_neutral_research_policy_example_validates() -> None:
    from digiquant.dashboard.research_retrieval.planner import (
        load_research_attention_policy,
    )

    example = _repo_root() / "digiquant" / "config" / "research_policy.example.yaml"
    assert example.exists()
    policy = load_research_attention_policy(example)
    assert policy.schema_version >= 1


def test_neutral_sector_example_loads() -> None:
    import digiquant.research.sectors_config as sc

    example = (
        _repo_root()
        / "digiquant"
        / "src"
        / "digiquant"
        / "research"
        / "config"
        / "sectors.example.yaml"
    )
    assert example.exists()
    data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    sectors = data.get("sectors") or []
    assert len(sectors) >= 1
    cfg = sc.SectorConfig.from_dict(sectors[0])
    assert cfg.slug and cfg.name


def test_neutral_asset_classes_example_parses() -> None:
    example = (
        _repo_root()
        / "digiquant"
        / "src"
        / "digiquant"
        / "research"
        / "config"
        / "asset_classes.example.yaml"
    )
    assert example.exists()
    data = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    buckets = data.get("asset_classes") or {}
    assert isinstance(buckets, dict) and len(buckets) >= 1
