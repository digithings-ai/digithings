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
    is_tool_use_capable_model,
    is_web_search_capable_model,
    sanitize_allowed_models,
)

_REPO_CONFIG = str(Path(__file__).parents[2] / "config")

# OpenRouter slugs verified in CI (OPENROUTER_API_KEY only — no direct OpenAI).
_KNOWN_GOOD_OPENROUTER_MODELS = frozenset(
    {
        "openrouter/deepseek/deepseek-chat:online",
        "openrouter/deepseek/deepseek-r1:online",
        "openrouter/meta-llama/llama-4-maverick:online",
    }
)

# Retired OpenRouter IDs — must not appear in olympus_models.yaml pins or pools.
_BANNED_QWEN_MODEL_MARKERS = (
    "qwen3-235b",
    "qwen/qwen3",
    "qwen3-235b-a22b-instruct-2507",
)

_BANNED_PERPLEXITY_MARKERS = (
    "perplexity/sonar",
    "openrouter/perplexity",
)


@pytest.fixture(autouse=True)
def _repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_CONFIG_PATH", _REPO_CONFIG)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)


def _cheap_research_pool() -> set[str]:
    cfg = model_config._load_olympus_models()
    return set(cfg.tiers["cheap"].allowed_models["research"])


@pytest.mark.unit
def test_hermes_thesis_and_portfolio_slugs_route_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hermes H1–H7 slugs must resolve via olympus_models (CI has OPENROUTER_API_KEY only)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_olympus_models()
    cheap = cfg.tiers["cheap"]
    assert get_model_for_phase("hermes/thesis/market-review") in cheap.allowed_models["research"]
    assert get_model_for_phase("hermes/portfolio/pm-direction") in cheap.allowed_models["reasoning"]
    assert get_model_for_phase("beliefs-distillation") in cheap.allowed_models["research"]


@pytest.mark.unit
def test_asset_analyst_slug_resolves_to_known_good_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H5 asset-analyst must resolve from the extraction pool (CI run 27950332738)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_model_for_phase("hermes/portfolio/asset-analyst-AAPL")
    assert model is not None
    assert model.startswith("openrouter/")
    assert model in _KNOWN_GOOD_OPENROUTER_MODELS
    assert is_tool_use_capable_model(model)


@pytest.mark.unit
def test_cheap_tier_resolves_extraction_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_olympus_models()
    cheap = cfg.tiers["cheap"]
    assert get_model_for_phase("alt-sentiment-news") in cheap.allowed_models["extraction"]
    assert get_model_for_phase("monthly-digest") in cheap.allowed_models["reasoning"]
    assert get_model_for_phase("technical-analyst-AAPL") in cheap.allowed_models["extraction"]


@pytest.mark.unit
def test_quality_tier_uses_reasoning_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    cfg = model_config._load_olympus_models()
    quality = cfg.tiers["quality"]
    assert get_model_for_phase("pm-rebalance") in quality.allowed_models["reasoning"]
    assert get_model_for_phase("macro") in quality.allowed_models["research"]


@pytest.mark.unit
def test_phase_slug_selection_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    first = get_model_for_phase("macro")
    second = get_model_for_phase("macro")
    assert first == second
    assert first in _cheap_research_pool()


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
    assert "perplexity" not in pool.lower()
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
    assert is_web_search_capable_model(model)
    assert is_tool_use_capable_model(model)
    cfg = model_config._load_olympus_models()
    assert model in cfg.tiers["cheap"].web_search_models


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
    "model",
    (
        "openrouter/deepseek/deepseek-chat:online",
        "openrouter/meta-llama/llama-4-maverick:online",
    ),
)
def test_web_search_capable_models(model: str) -> None:
    assert is_web_search_capable_model(model)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "capable"),
    [
        ("openrouter/deepseek/deepseek-chat:online", True),
        ("openrouter/meta-llama/llama-4-maverick:online", True),
        ("openrouter/deepseek/deepseek-r1:online", True),
        ("openrouter/perplexity/sonar", False),
        ("openrouter/deepseek/deepseek-chat", False),
    ],
)
def test_tool_use_capable_models(model: str, capable: bool) -> None:
    assert is_tool_use_capable_model(model) is capable


@pytest.mark.unit
def test_perplexity_not_web_search_capable() -> None:
    assert not is_web_search_capable_model("openrouter/perplexity/sonar")


@pytest.mark.unit
def test_non_online_deepseek_not_web_search_capable() -> None:
    assert not is_web_search_capable_model("openrouter/deepseek/deepseek-chat")


@pytest.mark.unit
def test_sanitize_allowed_models_strips_frontier() -> None:
    raw = "deepseek/*,openai/*,anthropic/*,meta-llama/*"
    assert sanitize_allowed_models(raw) == "deepseek/*,meta-llama/*"
    assert is_flagship_allowed_models_entry("openai/*")
    assert not is_flagship_allowed_models_entry("deepseek/*")


@pytest.mark.unit
def test_no_perplexity_in_olympus_config_pools() -> None:
    """Regression: perplexity/sonar lacks tool use → OpenRouter 404 on tool phases."""
    cfg = model_config._load_olympus_models()
    pool_models: list[str] = []
    for tier_cfg in cfg.tiers.values():
        for pool in tier_cfg.allowed_models.values():
            pool_models.extend(pool)
        pool_models.extend(tier_cfg.web_search_models)
    pool_models.append(cfg.openrouter_defaults.allowed_models)
    joined = " ".join(pool_models).lower()
    hits = [marker for marker in _BANNED_PERPLEXITY_MARKERS if marker in joined]
    assert not hits, f"olympus_models.yaml pools still reference perplexity: {hits}"


@pytest.mark.unit
def test_no_stale_qwen_model_ids_in_olympus_config() -> None:
    """Regression: retired qwen/qwen3-235b slugs 400 on OpenRouter (CI run 27950332738)."""
    yaml_text = Path(_REPO_CONFIG, "olympus_models.yaml").read_text().lower()
    hits = [marker for marker in _BANNED_QWEN_MODEL_MARKERS if marker in yaml_text]
    assert not hits, f"olympus_models.yaml still references banned Qwen slugs: {hits}"

    cfg = model_config._load_olympus_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        assert tier_cfg.allowed_models, f"tier {tier_name} must define allowed_models pools"
        assert not tier_cfg.models, f"tier {tier_name} must not use legacy models: pins"
        for capability, pool in tier_cfg.allowed_models.items():
            assert len(pool) >= 1, f"tier {tier_name} {capability} pool is empty"
            for model in pool:
                slug = model.lower()
                assert slug in {m.lower() for m in _KNOWN_GOOD_OPENROUTER_MODELS}, (
                    f"tier {tier_name} {capability} pools unverified model {model!r}"
                )
                assert is_web_search_capable_model(model), (
                    f"tier {tier_name} {capability} model {model!r} lacks web search"
                )
                assert is_tool_use_capable_model(model), (
                    f"tier {tier_name} {capability} model {model!r} lacks tool use"
                )
        for model in tier_cfg.web_search_models:
            assert is_web_search_capable_model(model)
            assert is_tool_use_capable_model(model)
    assert "qwen" not in cfg.openrouter_defaults.allowed_models.lower()
    assert "perplexity" not in cfg.openrouter_defaults.allowed_models.lower()


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
    """#926 gate: default cheap tier pools open-weight models for edit-mode segment schemas."""
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    assert get_olympus_tier() == "cheap"
    model = get_model_for_phase(phase_slug)
    assert model is not None
    assert model.startswith("openrouter/")
    assert not is_flagship_openrouter_model(model)
    assert is_web_search_capable_model(model)
    assert is_tool_use_capable_model(model)


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
