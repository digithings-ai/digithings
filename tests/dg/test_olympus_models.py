"""Olympus model tier policy (config/olympus_models.yaml)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import digigraph.model_config as model_config
from digigraph.model_config import (
    apply_olympus_openrouter_env,
    get_grounding_model,
    get_model_for_phase,
    get_olympus_tier,
    is_flagship_allowed_models_entry,
    is_flagship_openrouter_model,
    sanitize_allowed_models,
)

_REPO_CONFIG = str(Path(__file__).parents[2] / "config")


@pytest.fixture(autouse=True)
def _repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_CONFIG_PATH", _REPO_CONFIG)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)


@pytest.mark.unit
def test_cheap_tier_resolves_extraction_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    assert get_model_for_phase("alt-sentiment-news") == (
        "openrouter/qwen/qwen3-235b-a22b-instruct-2507"
    )
    assert get_model_for_phase("monthly-digest") == "openrouter/deepseek/deepseek-chat"
    assert get_model_for_phase("technical-analyst-AAPL") == (
        "openrouter/qwen/qwen3-235b-a22b-instruct-2507"
    )


@pytest.mark.unit
def test_quality_tier_uses_deepseek_r1_for_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    assert get_model_for_phase("pm-rebalance") == "openrouter/deepseek/deepseek-r1"
    assert get_model_for_phase("macro") == "openrouter/deepseek/deepseek-chat"


@pytest.mark.unit
def test_apply_olympus_openrouter_env_sets_open_weight_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_ALLOWED_MODELS", raising=False)
    monkeypatch.delenv("OPENROUTER_COST_QUALITY_TRADEOFF", raising=False)
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    tier = apply_olympus_openrouter_env()
    assert tier == "cheap"
    pool = os.environ["OPENROUTER_ALLOWED_MODELS"]
    assert "deepseek/*" in pool
    assert "qwen/*" in pool
    assert "openai" not in pool
    assert "anthropic" not in pool
    assert os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] == "10"


@pytest.mark.unit
def test_apply_does_not_override_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOWED_MODELS", "custom/*")
    monkeypatch.setenv("OPENROUTER_COST_QUALITY_TRADEOFF", "9")
    apply_olympus_openrouter_env()
    assert os.environ["OPENROUTER_ALLOWED_MODELS"] == "custom/*"
    assert os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] == "9"


@pytest.mark.unit
def test_grounding_model_is_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    assert get_grounding_model() == "openrouter/deepseek/deepseek-chat"


@pytest.mark.unit
def test_phase_models_flagship_override_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/openai/gpt-4o-mini"\n'
    )
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/deepseek/deepseek-chat"


@pytest.mark.unit
def test_phase_models_open_weight_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/mistralai/mistral-small"\n'
    )
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/mistralai/mistral-small"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "flagship"),
    [
        ("openrouter/openai/gpt-5.5", True),
        ("openrouter/anthropic/claude-sonnet-4", True),
        ("openrouter/deepseek/deepseek-chat", False),
        ("openrouter/qwen/qwen3-235b-a22b-instruct-2507", False),
    ],
)
def test_flagship_detection(model: str, flagship: bool) -> None:
    assert is_flagship_openrouter_model(model) is flagship


@pytest.mark.unit
def test_sanitize_allowed_models_strips_frontier() -> None:
    raw = "deepseek/*,openai/*,anthropic/*,qwen/*"
    assert sanitize_allowed_models(raw) == "deepseek/*,qwen/*"
    assert is_flagship_allowed_models_entry("openai/*")
    assert not is_flagship_allowed_models_entry("deepseek/*")


@pytest.mark.unit
def test_default_tier_is_cheap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    assert get_olympus_tier() == "cheap"


@pytest.mark.unit
@pytest.mark.parametrize(
    "phase_slug",
    (
        "macro",
        "crypto",
        "equity",
        "bonds",
        "alt-sentiment-news",
        "sector-technology",
    ),
)
def test_edit_mode_segments_route_to_cheap_open_weight_models(
    monkeypatch: pytest.MonkeyPatch, phase_slug: str
) -> None:
    """#926 gate: default cheap tier pins open-weight models for edit-mode segment schemas."""
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    assert get_olympus_tier() == "cheap"
    model = get_model_for_phase(phase_slug)
    assert model is not None
    assert model.startswith("openrouter/")
    assert not is_flagship_openrouter_model(model)


@pytest.mark.unit
def test_repo_olympus_config_has_no_flagship_pins() -> None:
    cfg = model_config._load_olympus_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        for capability, model in tier_cfg.models.items():
            assert not is_flagship_openrouter_model(model), (
                f"tier {tier_name} {capability} pins flagship {model}"
            )
        assert not is_flagship_openrouter_model(tier_cfg.grounding_model)
    assert cfg.openrouter_defaults.cost_quality_tradeoff == 10
    assert "openai" not in cfg.openrouter_defaults.allowed_models
    assert "anthropic" not in cfg.openrouter_defaults.allowed_models
