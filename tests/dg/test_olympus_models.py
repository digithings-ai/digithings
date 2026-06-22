"""Olympus model tier policy (config/olympus_models.yaml)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

import digigraph.model_config as model_config
from digigraph.model_config import (
    apply_olympus_openrouter_env,
    get_grounding_model,
    get_model_for_phase,
    get_olympus_tier,
    is_flagship_allowed_models_entry,
    is_flagship_openrouter_model,
    is_web_search_capable_model,
    sanitize_allowed_models,
)

_REPO_CONFIG = str(Path(__file__).parents[2] / "config")

# OpenRouter slugs in tier pools (CI has OPENROUTER_API_KEY only).
_WEB_SEARCH_POOL = frozenset(
    {
        "openrouter/deepseek/deepseek-chat:online",
        "openrouter/deepseek/deepseek-r1:online",
        "openrouter/meta-llama/llama-4-maverick:online",
        "openrouter/perplexity/sonar",
    }
)

# Retired OpenRouter IDs — must not appear in olympus_models.yaml pins or pools.
_BANNED_QWEN_MODEL_MARKERS = (
    "qwen3-235b",
    "qwen/qwen3",
    "qwen3-235b-a22b-instruct-2507",
)


@pytest.fixture(autouse=True)
def _repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_CONFIG_PATH", _REPO_CONFIG)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)


def _cheap_research_pool() -> list[str]:
    cfg = model_config._load_olympus_models()
    return list(cfg.tiers["cheap"].allowed_models["research"])


@pytest.mark.unit
def test_hermes_thesis_and_portfolio_slugs_route_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hermes H1–H7 slugs must resolve via olympus_models (CI has OPENROUTER_API_KEY only)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    pool = _cheap_research_pool()
    for slug in (
        "hermes/thesis/market-review",
        "beliefs-distillation",
    ):
        model = get_model_for_phase(slug)
        assert model is not None
        assert model.startswith("openrouter/")
        assert model in pool
    extraction_pool = model_config._load_olympus_models().tiers["cheap"].allowed_models[
        "extraction"
    ]
    assert get_model_for_phase("hermes/portfolio/asset-analyst-AAPL") in extraction_pool
    reasoning_pool = model_config._load_olympus_models().tiers["cheap"].allowed_models[
        "reasoning"
    ]
    assert get_model_for_phase("hermes/portfolio/pm-direction") in reasoning_pool


@pytest.mark.unit
def test_asset_analyst_slug_resolves_to_web_search_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H5 asset-analyst must resolve from the extraction pool (all search-capable)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_model_for_phase("hermes/portfolio/asset-analyst-AAPL")
    assert model is not None
    assert model.startswith("openrouter/")
    assert model in _WEB_SEARCH_POOL
    assert is_web_search_capable_model(model)


@pytest.mark.unit
def test_cheap_tier_resolves_from_capability_pools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_olympus_models()
    cheap = cfg.tiers["cheap"]
    assert get_model_for_phase("alt-sentiment-news") in cheap.allowed_models["extraction"]
    assert get_model_for_phase("monthly-digest") in cheap.allowed_models["reasoning"]
    assert get_model_for_phase("technical-analyst-AAPL") in cheap.allowed_models["extraction"]


@pytest.mark.unit
def test_quality_tier_picks_from_reasoning_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    quality = model_config._load_olympus_models().tiers["quality"]
    assert get_model_for_phase("pm-rebalance") in quality.allowed_models["reasoning"]
    assert get_model_for_phase("macro") in quality.allowed_models["research"]


@pytest.mark.unit
def test_phase_slug_selection_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    first = get_model_for_phase("macro")
    second = get_model_for_phase("macro")
    assert first == second
    assert get_model_for_phase("crypto") != first or len(_cheap_research_pool()) == 1


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
    assert "qwen" not in pool.lower()
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
def test_grounding_model_from_web_search_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_grounding_model(segment="macro")
    assert model is not None
    assert model.startswith("openrouter/")
    assert model in model_config._load_olympus_models().tiers["cheap"].web_search_models
    assert is_web_search_capable_model(model)


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
    assert get_model_for_phase("macro") in _cheap_research_pool()


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
        ("openrouter/deepseek/deepseek-chat:online", False),
        ("openrouter/meta-llama/llama-4-maverick:online", False),
    ],
)
def test_flagship_detection(model: str, flagship: bool) -> None:
    assert is_flagship_openrouter_model(model) is flagship


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "search_capable"),
    [
        ("openrouter/deepseek/deepseek-chat:online", True),
        ("openrouter/perplexity/sonar", True),
        ("openrouter/deepseek/deepseek-chat", False),
        ("openrouter/meta-llama/llama-4-maverick", False),
    ],
)
def test_web_search_capability(model: str, search_capable: bool) -> None:
    assert is_web_search_capable_model(model) is search_capable


@pytest.mark.unit
def test_sanitize_allowed_models_strips_frontier() -> None:
    raw = "deepseek/*,openai/*,anthropic/*,meta-llama/*"
    assert sanitize_allowed_models(raw) == "deepseek/*,meta-llama/*"
    assert is_flagship_allowed_models_entry("openai/*")
    assert not is_flagship_allowed_models_entry("deepseek/*")


@pytest.mark.unit
def test_no_stale_qwen_model_ids_in_olympus_config() -> None:
    """Regression: retired qwen/qwen3-235b slugs 400 on OpenRouter (CI run 27950332738)."""
    yaml_text = Path(_REPO_CONFIG, "olympus_models.yaml").read_text().lower()
    hits = [marker for marker in _BANNED_QWEN_MODEL_MARKERS if marker in yaml_text]
    assert not hits, f"olympus_models.yaml still references banned Qwen slugs: {hits}"

    cfg = model_config._load_olympus_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        assert not tier_cfg.models, f"tier {tier_name} must use allowed_models pools, not models pins"
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                assert model.startswith("openrouter/"), f"{tier_name}.{capability}: {model}"
                assert is_web_search_capable_model(model), (
                    f"{tier_name}.{capability} pools non-search model {model!r}"
                )
        for model in tier_cfg.web_search_models:
            assert is_web_search_capable_model(model), (
                f"{tier_name}.web_search_models contains non-search model {model!r}"
            )
    assert "qwen" not in cfg.openrouter_defaults.allowed_models.lower()


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
    """#926 gate: default cheap tier pools open-weight search-capable models."""
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    assert get_olympus_tier() == "cheap"
    model = get_model_for_phase(phase_slug)
    assert model is not None
    assert model.startswith("openrouter/")
    assert not is_flagship_openrouter_model(model)
    assert is_web_search_capable_model(model)


@pytest.mark.unit
def test_repo_olympus_config_has_no_flagship_pins() -> None:
    cfg = model_config._load_olympus_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                assert not is_flagship_openrouter_model(model), (
                    f"tier {tier_name} {capability} pools flagship {model}"
                )
        for model in tier_cfg.web_search_models:
            assert not is_flagship_openrouter_model(model)
    assert cfg.openrouter_defaults.cost_quality_tradeoff == 10
    assert "openai" not in cfg.openrouter_defaults.allowed_models
    assert "anthropic" not in cfg.openrouter_defaults.allowed_models


@pytest.mark.unit
def test_yaml_uses_allowed_models_pools_not_single_pins() -> None:
    raw = yaml.safe_load(Path(_REPO_CONFIG, "olympus_models.yaml").read_text())
    for tier_name, tier_cfg in raw["tiers"].items():
        assert "models" not in tier_cfg, f"tier {tier_name} must not use legacy models pins"
        assert "grounding_model" not in tier_cfg, (
            f"tier {tier_name} must use web_search_models, not grounding_model pin"
        )
        for capability, pool in tier_cfg["allowed_models"].items():
            assert isinstance(pool, list), f"{tier_name}.{capability} must be a list pool"
            assert len(pool) >= 1, f"{tier_name}.{capability} pool must not be empty"
