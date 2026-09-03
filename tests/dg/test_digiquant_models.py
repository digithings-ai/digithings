"""dashboard model tier policy (config/digiquant_models.yaml)."""

from __future__ import annotations

import os
from pathlib import Path

import digigraph.model_config as model_config
import pytest
from digigraph.model_config import (
    apply_digiquant_openrouter_env,
    get_digiquant_tier,
    get_grounding_model,
    get_model_for_mode,
    get_model_for_phase,
    is_flagship_allowed_models_entry,
    is_flagship_openrouter_model,
    is_native_search_only_model,
    is_tool_use_capable_model,
    is_web_search_capable_model,
    sanitize_allowed_models,
    tier_allows_phase_model,
)

_REPO_CONFIG = str(Path(__file__).parents[2] / "config")


def _clear_env(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    """Delete env vars so teardown still undoes mutations by the code under test.

    ``monkeypatch.delenv(..., raising=False)`` records no undo when the key was already
    absent. ``apply_digiquant_openrouter_env`` then does ``os.environ[k] = ...`` and the
    value leaks into later tests (e.g. Live Search ``extra_body`` assertions). Seed a
    placeholder first so the undo stack always restores the pre-test state.
    """
    for name in names:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name, raising=False)


# Phase pools = bare OpenRouter slugs (function tools). The ``:online`` suffix is a
# web-search variant only and must never appear in a phase pool — it 404s on tool use
# for open-weight models. Web-search/grounding slugs keep ``:online``/perplexity below.
_CHEAP_PHASE_MODELS = frozenset(
    {
        "deepseek/deepseek-v4-flash",  # #1622: 1M ctx, tools + strict json_schema
        # deepseek-r1 removed from every phase pool (#1622): CoT output is not reliably
        # strict JSON (#1617 master-digest JSONDecodeError). Re-adding it here must be a
        # deliberate decision, not a drive-by.
        "meta-llama/llama-4-maverick",
    }
)

_BALANCED_PHASE_MODELS = _CHEAP_PHASE_MODELS | frozenset(
    {
        # #2368 (2026-08-14): latest generation per vendor where cost allows — grok-4.3
        # stays on balanced (grok-4.6 is quality-only). gemini-3.7-flash: native PDF/
        # image vision. gpt-5.6-luna: mid-tier OpenAI. deepseek-v4-pro: mid-cost
        # reasoning bump, gate-proven and also pooled on quality.
        "google/gemini-3.7-flash",
        "openai/gpt-5.6-luna",
        "x-ai/grok-4.3",
        "deepseek/deepseek-v4-pro",  # #1622
    }
)

_QUALITY_PHASE_MODELS = _BALANCED_PHASE_MODELS | frozenset(
    {
        # #2368 (2026-08-14): latest-generation flagship slugs per vendor.
        "openai/gpt-5.6-sol",
        "anthropic/claude-sonnet-5",
        "x-ai/grok-4.6",
    }
)

# Web-search/grounding pools keep ``:online`` (built-in plugin) and perplexity (native).
_WEB_SEARCH_MODELS = frozenset(
    {
        "perplexity/sonar",
        "deepseek/deepseek-v4-flash:online",  # #1622
        "meta-llama/llama-4-maverick:online",
        "google/gemini-3.7-flash:online",
        "openai/gpt-5.6-luna:online",
        "openai/gpt-5.6-sol:online",
        "anthropic/claude-sonnet-5:online",
        "x-ai/grok-4.6:online",
    }
)

_TIER_PHASE_MODELS = {
    "cheap": _CHEAP_PHASE_MODELS,
    "balanced": _BALANCED_PHASE_MODELS,
    "quality": _QUALITY_PHASE_MODELS,
}

# Retired OpenRouter IDs — must not appear in digiquant_models.yaml pins or pools.
_BANNED_QWEN_MODEL_MARKERS = (
    "qwen3-235b",
    "qwen/qwen3",
    "qwen3-235b-a22b-instruct-2507",
)


@pytest.fixture(autouse=True)
def _repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_CONFIG_PATH", _REPO_CONFIG)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)


def _cheap_research_pool() -> set[str]:
    cfg = model_config._load_digiquant_models()
    return set(cfg.tiers["cheap"].allowed_models["research"])


@pytest.mark.unit
def test_portfolio_thesis_and_portfolio_slugs_route_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """portfolio H1–H7 slugs must resolve via dashboard_models (CI has OPENROUTER_API_KEY only)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_digiquant_models()
    cheap = cfg.tiers["cheap"]
    assert get_model_for_phase("portfolio/thesis/market-review") in cheap.allowed_models["research"]
    assert get_model_for_phase("portfolio/pm-direction") in cheap.allowed_models["reasoning"]
    assert get_model_for_phase("beliefs-distillation") in cheap.allowed_models["research"]


@pytest.mark.unit
def test_deliberation_pinned_to_json_reliable_deepseek_v4_flash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (dashboard daily, run 28014812240, #1006): H6 deliberation turns must emit
    strict JSON (DeliberationPmTurn / DeliberationAnalystTurn). #991 first mapped the phase to
    the ``reasoning`` pool (prose-only deepseek-r1 → json.loads failed at char 0); #998 then
    routed it to the cheap ``research`` pool — but that pool also contains ``llama-4-maverick``,
    which returns *empty* completions under STRICT json_schema, so the ~half of tickers hashing
    onto it still failed at char 0. Deliberation is now pinned (model_modes.yaml ``phase_models``)
    to deepseek-v4-flash — the json/tool-reliable open-weight model — for *every* ticker,
    bypassing the pool hash. Never maverick, never r1.
    """
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    # The live macro watchlist from the failing run.
    watchlist = (
        "SPY QQQ DIA IWB VTI MDY IJH IWM IJR XLK XLF XLE XLV XLI XLRE XLU XLY XLP XLB XLC "
        "EFA VEA VGK EWJ EWG EWU EWA EEM VWO FXI ASHR EWZ EWT EWY INDA BITO IBIT FBTC ETHA "
        "FETH GBTC GLD IAU SLV DBO USO BNO PDBC DJP CPER BIL SHV SHY IEF TLT AGG HYG LQD TIP "
        "EMB DXY UUP VIX"
    ).split()
    for ticker in watchlist:
        model = get_model_for_phase(f"portfolio/deliberation-{ticker}")
        assert model == "deepseek/deepseek-v4-flash", (
            f"deliberation-{ticker} -> {model!r}, expected the pinned json-reliable "
            "deepseek-v4-flash"
        )
        assert "maverick" not in model, f"deliberation-{ticker} routes to empty-prone maverick"
        assert "deepseek-r1" not in model, f"deliberation-{ticker} routes to prose-only r1"
        assert is_tool_use_capable_model(model)


@pytest.mark.unit
def test_master_digest_pinned_to_v4_flash(monkeypatch: pytest.MonkeyPatch) -> None:
    """#1559/#1622: master-digest is pinned (model_modes.yaml) to deepseek-v4-flash.

    Unpinned, the reasoning-pool hash landed on deepseek-r1, whose chain-of-thought
    output broke strict json_schema (2026-07-18 digest JSONDecodeError → prior digest
    carried forward). v4-flash's 1M context also removes the 64k synthesis ceiling
    (#1559); the input budget remains as a cost bound. Never r1, never maverick.
    """
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_model_for_phase("master-digest")
    assert model == "deepseek/deepseek-v4-flash"
    assert is_tool_use_capable_model(model)


@pytest.mark.unit
def test_asset_analyst_slug_resolves_to_known_good_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H5 asset-analyst must resolve from the extraction pool (CI run 27950332738)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_model_for_phase("portfolio/asset-analyst-AAPL")
    assert model is not None
    assert model in _CHEAP_PHASE_MODELS
    assert is_tool_use_capable_model(model)


@pytest.mark.unit
def test_cheap_tier_resolves_extraction_and_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_digiquant_models()
    cheap = cfg.tiers["cheap"]
    assert get_model_for_phase("alt-sentiment-news") in cheap.allowed_models["extraction"]
    assert get_model_for_phase("monthly-digest") in cheap.allowed_models["reasoning"]
    assert get_model_for_phase("technical-analyst-AAPL") in cheap.allowed_models["extraction"]


@pytest.mark.unit
def test_quality_tier_uses_reasoning_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    cfg = model_config._load_digiquant_models()
    quality = cfg.tiers["quality"]
    assert get_model_for_phase("pm-rebalance") in quality.allowed_models["reasoning"]
    assert get_model_for_phase("macro") in quality.allowed_models["research"]


@pytest.mark.unit
def test_balanced_tier_includes_mid_frontier_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "balanced")
    cfg = model_config._load_digiquant_models()
    balanced = cfg.tiers["balanced"]
    research = balanced.allowed_models["research"]
    assert any("gpt-5.6-luna" in m for m in research)
    assert any("gemini" in m for m in research)
    model = get_model_for_phase("macro")
    assert model is not None
    assert tier_allows_phase_model(model, "balanced")


@pytest.mark.unit
def test_quality_tier_allows_frontier_in_pools() -> None:
    cfg = model_config._load_digiquant_models()
    quality = cfg.tiers["quality"]
    frontier = [m for m in quality.allowed_models["reasoning"] if is_flagship_openrouter_model(m)]
    assert frontier, "quality tier should include frontier reasoning models"
    for model in frontier:
        assert tier_allows_phase_model(model, "quality")


@pytest.mark.unit
def test_phase_slug_selection_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    first = get_model_for_phase("macro")
    second = get_model_for_phase("macro")
    assert first == second
    assert first in _cheap_research_pool()


@pytest.mark.unit
def test_apply_digiquant_openrouter_env_sets_open_weight_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(
        monkeypatch,
        "OPENROUTER_ALLOWED_MODELS",
        "OPENROUTER_COST_QUALITY_TRADEOFF",
        "OPENAI_API_BASE",
        "OPENAI_API_KEY",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DIGIQUANT_MODEL_TIER", "cheap")
    tier = apply_digiquant_openrouter_env()
    assert tier == "cheap"
    pool = os.environ["OPENROUTER_ALLOWED_MODELS"]
    assert "deepseek/*" in pool
    assert "perplexity/*" in pool
    assert "qwen" not in pool.lower()
    assert "openai" not in pool
    assert "anthropic" not in pool
    assert os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] == "10"
    assert os.environ["OPENAI_API_BASE"] == "https://openrouter.ai/api/v1"
    assert os.environ["OPENAI_API_KEY"] == "sk-or-test"


@pytest.mark.unit
def test_apply_does_not_override_existing_openai_api_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-litellm")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    apply_digiquant_openrouter_env()
    assert os.environ["OPENAI_API_BASE"] == "http://127.0.0.1:4000/v1"
    assert os.environ["OPENAI_API_KEY"] == "sk-litellm"


@pytest.mark.unit
def test_apply_openrouter_rewrite_leaves_gemini_on_vendor_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI rewrite is not LiteLLM: leftover ``gemini/`` still needs ``GEMINI_API_KEY``."""
    import digillm

    _clear_env(monkeypatch, "OPENAI_API_BASE", "OPENAI_API_KEY", "GEMINI_API_KEY")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    apply_digiquant_openrouter_env()
    assert os.environ["OPENAI_API_BASE"] == "https://openrouter.ai/api/v1"
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        digillm.get_client_for_model("gemini/gemini-2.5-flash")


@pytest.mark.unit
def test_apply_quality_tier_preserves_frontier_auto_router_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_env(monkeypatch, "OPENROUTER_ALLOWED_MODELS", "OPENAI_API_BASE", "OPENAI_API_KEY")
    monkeypatch.setenv("DIGIQUANT_MODEL_TIER", "quality")
    apply_digiquant_openrouter_env()
    pool = os.environ["OPENROUTER_ALLOWED_MODELS"]
    assert "openai/*" in pool
    assert "anthropic/*" in pool


@pytest.mark.unit
def test_apply_does_not_override_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOWED_MODELS", "custom/*")
    monkeypatch.setenv("OPENROUTER_COST_QUALITY_TRADEOFF", "9")
    apply_digiquant_openrouter_env()
    assert os.environ["OPENROUTER_ALLOWED_MODELS"] == "custom/*"
    assert os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] == "9"


@pytest.mark.unit
def test_grounding_model_from_web_search_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_grounding_model(segment="macro")
    assert model is not None
    assert is_web_search_capable_model(model)
    cfg = model_config._load_digiquant_models()
    assert model in cfg.tiers["cheap"].web_search_models


@pytest.mark.unit
def test_grounding_model_may_be_perplexity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Perplexity is valid for grounding-only paths, not tool phases."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_digiquant_models()
    assert "perplexity/sonar" in cfg.tiers["cheap"].web_search_models
    # Deterministic pick for a segment that hashes to perplexity
    for segment in ("macro", "bonds", "perplexity-grounding", "alt-sentiment-news"):
        model = get_grounding_model(segment=segment)
        assert model is not None
        assert is_web_search_capable_model(model)
        if is_native_search_only_model(model):
            assert not is_tool_use_capable_model(model)


@pytest.mark.unit
def test_phase_models_flagship_override_rejected_on_cheap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/openai/gpt-4o-mini"\n'
    )
    (tmp_path / "digiquant_models.yaml").write_text(
        Path(_REPO_CONFIG, "digiquant_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    assert get_model_for_phase("macro") in _cheap_research_pool()


@pytest.mark.unit
def test_phase_models_mid_tier_override_wins_on_balanced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A bare (tool-capable) mid-tier slug is accepted as an override on balanced.
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/openai/gpt-5.6-luna"\n'
    )
    (tmp_path / "digiquant_models.yaml").write_text(
        Path(_REPO_CONFIG, "digiquant_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "balanced")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/openai/gpt-5.6-luna"


@pytest.mark.unit
def test_phase_models_open_weight_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A bare open-weight slug (not in the macro/research pool) is tool-capable, so the
    # override is honored and wins over the tier pool.
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/deepseek/deepseek-r1"\n'
    )
    (tmp_path / "digiquant_models.yaml").write_text(
        Path(_REPO_CONFIG, "digiquant_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/deepseek/deepseek-r1"


@pytest.mark.unit
def test_phase_models_online_override_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: a ``:online`` override is web-search-only and must NOT route a phase.

    The override is rejected (not tool-capable) and routing falls back to the tier's
    bare phase pool from digiquant_models.yaml.
    """
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/mistralai/mistral-small-3.1-24b-instruct:online"\n'
    )
    (tmp_path / "digiquant_models.yaml").write_text(
        Path(_REPO_CONFIG, "digiquant_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    model = get_model_for_phase("macro")
    assert model in _cheap_research_pool()
    assert ":online" not in model
    assert is_tool_use_capable_model(model)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "flagship"),
    [
        ("openrouter/openai/gpt-5.5", True),
        ("openrouter/anthropic/claude-sonnet-4.6", True),
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
        "openrouter/perplexity/sonar",
    ),
)
def test_web_search_capable_models(model: str) -> None:
    assert is_web_search_capable_model(model)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("model", "capable"),
    [
        # Bare slugs are tool-capable; ``:online`` is web-search-only and rejected.
        ("openrouter/deepseek/deepseek-chat", True),
        ("openrouter/meta-llama/llama-4-maverick", True),
        ("openrouter/deepseek/deepseek-r1", True),
        ("openrouter/mistralai/mistral-small-3.1-24b-instruct", True),
        ("openrouter/openai/gpt-4o-mini", True),
        ("openrouter/deepseek/deepseek-chat:online", False),
        ("openrouter/meta-llama/llama-4-maverick:online", False),
        ("openrouter/deepseek/deepseek-r1:online", False),
        ("openrouter/openai/gpt-4o-mini:online", False),
        ("openrouter/perplexity/sonar", False),
    ],
)
def test_tool_use_capable_models(model: str, capable: bool) -> None:
    assert is_tool_use_capable_model(model) is capable


@pytest.mark.unit
def test_perplexity_is_native_search_only() -> None:
    assert is_native_search_only_model("openrouter/perplexity/sonar")
    assert is_web_search_capable_model("openrouter/perplexity/sonar")
    assert not is_tool_use_capable_model("openrouter/perplexity/sonar")
    assert not tier_allows_phase_model("openrouter/perplexity/sonar", "quality")


@pytest.mark.unit
def test_non_online_deepseek_not_web_search_capable() -> None:
    assert not is_web_search_capable_model("openrouter/deepseek/deepseek-chat")


@pytest.mark.unit
def test_sanitize_allowed_models_strips_frontier_on_cheap() -> None:
    raw = "deepseek/*,openai/*,anthropic/*,meta-llama/*"
    assert sanitize_allowed_models(raw, tier="cheap") == "deepseek/*,meta-llama/*"
    assert is_flagship_allowed_models_entry("openai/*")
    assert not is_flagship_allowed_models_entry("deepseek/*")


@pytest.mark.unit
def test_sanitize_allowed_models_preserves_frontier_on_quality() -> None:
    raw = "deepseek/*,openai/*,anthropic/*"
    assert sanitize_allowed_models(raw, tier="quality") == raw


@pytest.mark.unit
def test_perplexity_only_in_web_search_pools_not_phase_pools() -> None:
    """Regression: perplexity/sonar in allowed_models caused tool-use 404s."""
    cfg = model_config._load_digiquant_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                assert not is_native_search_only_model(model), (
                    f"tier {tier_name} {capability} must not pool native-search-only {model}"
                )
        assert any(is_native_search_only_model(m) for m in tier_cfg.web_search_models), (
            f"tier {tier_name} should offer perplexity in web_search_models"
        )


@pytest.mark.unit
def test_no_stale_qwen_model_ids_in_dashboard_config() -> None:
    """Regression: retired qwen/qwen3-235b slugs 400 on OpenRouter (CI run 27950332738)."""
    yaml_text = Path(_REPO_CONFIG, "digiquant_models.yaml").read_text().lower()
    hits = [marker for marker in _BANNED_QWEN_MODEL_MARKERS if marker in yaml_text]
    assert not hits, f"digiquant_models.yaml still references banned Qwen slugs: {hits}"

    cfg = model_config._load_digiquant_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        assert tier_cfg.allowed_models, f"tier {tier_name} must define allowed_models pools"
        assert not tier_cfg.models, f"tier {tier_name} must not use legacy models: pins"
        allowed_phase = _TIER_PHASE_MODELS[tier_name]
        for capability, pool in tier_cfg.allowed_models.items():
            assert len(pool) >= 1, f"tier {tier_name} {capability} pool is empty"
            for model in pool:
                slug = model.lower()
                assert slug in {m.lower() for m in allowed_phase}, (
                    f"tier {tier_name} {capability} pools unverified model {model!r}"
                )
                assert tier_allows_phase_model(model, tier_name), (
                    f"tier {tier_name} {capability} model {model!r} not allowed for phase calls"
                )
                assert is_tool_use_capable_model(model), (
                    f"tier {tier_name} {capability} model {model!r} lacks tool use"
                )
        for model in tier_cfg.web_search_models:
            assert is_web_search_capable_model(model)
            assert model.lower() in {m.lower() for m in _WEB_SEARCH_MODELS}
    assert "qwen" not in cfg.openrouter_defaults.allowed_models.lower()


@pytest.mark.unit
def test_default_tier_is_cheap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    monkeypatch.delenv("DIGIQUANT_MODEL_TIER", raising=False)
    assert get_digiquant_tier() == "cheap"


@pytest.mark.unit
def test_digiquant_model_tier_wins_over_dashboard_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#3381: DIGIQUANT_MODEL_TIER is canonical; retired DASHBOARD_* is alias only."""
    monkeypatch.setenv("DIGIQUANT_MODEL_TIER", "quality")
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    assert get_digiquant_tier() == "quality"


@pytest.mark.unit
def test_digiquant_model_tier_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLYMPUS_MODEL_TIER", raising=False)
    monkeypatch.setenv("DIGIQUANT_MODEL_TIER", "balanced")
    assert get_digiquant_tier() == "balanced"


@pytest.mark.unit
def test_dashboard_model_tier_alias_when_canonical_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGIQUANT_MODEL_TIER", raising=False)
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    assert get_digiquant_tier() == "quality"


@pytest.mark.unit
def test_empty_digiquant_model_tier_ignores_dashboard_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical key presence (even empty) wins — matches envcompat kill-switch semantics."""
    monkeypatch.setenv("DIGIQUANT_MODEL_TIER", "")
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    assert get_digiquant_tier() == "cheap"


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
    monkeypatch.delenv("DIGIQUANT_MODEL_TIER", raising=False)
    assert get_digiquant_tier() == "cheap"
    model = get_model_for_phase(phase_slug)
    assert model is not None
    assert not is_flagship_openrouter_model(model)
    # Phase models are bare (tool-capable); grounding is a separate web-search pre-pass.
    assert ":online" not in model
    assert is_tool_use_capable_model(model)
    assert not is_web_search_capable_model(model)


@pytest.mark.unit
def test_cheap_tier_has_no_flagship_pins() -> None:
    cfg = model_config._load_digiquant_models()
    cheap = cfg.tiers["cheap"]
    for capability, pool in cheap.allowed_models.items():
        for model in pool:
            assert not is_flagship_openrouter_model(model), (
                f"cheap {capability} pools flagship {model}"
            )
    for model in cheap.web_search_models:
        assert not is_flagship_openrouter_model(model)


@pytest.mark.unit
def test_no_online_slug_in_any_phase_pool() -> None:
    """Core regression guard for the production tool-use 404.

    For every tier and every capability pool in ``allowed_models``, no model may carry
    the ``:online`` suffix AND ``tier_allows_phase_model`` must hold. ``:online`` endpoints
    reject function tools for open-weight models, so routing a tool phase to one 404s
    ("No endpoints found that support tool use"). Grounding is a separate web-search
    pre-pass over ``web_search_models``; phase pools stay bare.
    """
    cfg = model_config._load_digiquant_models()
    for tier_name, tier_cfg in cfg.tiers.items():
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                assert ":online" not in model, (
                    f"tier {tier_name} {capability} pools web-search-only slug {model!r}; "
                    "phase pools must be bare (:online 404s on function tools)"
                )
                assert tier_allows_phase_model(model, tier_name), (
                    f"tier {tier_name} {capability} model {model!r} not allowed for phase calls"
                )
                assert is_tool_use_capable_model(model), (
                    f"tier {tier_name} {capability} model {model!r} lacks tool use"
                )


# ── Phase-slug routing must never fall through to the dev fallback (401 guard) ──
# Regression: the portfolio deliberation worker built slug
# ``portfolio/deliberation-{ticker}`` which matched no phase_capabilities entry
# nor prefix, so get_model_for_phase returned None and the caller fell back to
# get_model_for_mode() -> a dev model (ollama/*) that digillm routed to the default
# OpenAI client -> 401 "Incorrect API key provided: not-set", failing the live baseline.


@pytest.mark.unit
@pytest.mark.parametrize(
    "slug",
    [
        "portfolio/deliberation-AAPL",  # the regression: was unmapped
        "h6_pm_challenge-AAPL",
        "h6_analyst_response-AAPL",
        "portfolio/asset-analyst-AAPL",
        "portfolio/pm-direction",
        "sector-technology",
        "macro",
        "alt-options-derivatives",
        "pm-rebalance",
        "beliefs-distillation",
    ],
)
def test_pipeline_phase_slugs_resolve_to_openrouter(
    monkeypatch: pytest.MonkeyPatch, slug: str
) -> None:
    """Every live-pipeline phase slug must resolve to an OpenRouter model (never None)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    resolved = get_model_for_phase(slug)
    assert resolved is not None, (
        f"phase slug {slug!r} is unmapped — falls back to a dev model (401)"
    )
    assert "/" in resolved and not resolved.startswith(("ollama/", "gemini/", "xai/")), (
        f"phase slug {slug!r} resolved to non-house OpenRouter slug {resolved!r}"
    )


@pytest.mark.unit
def test_deliberation_slug_routes_to_research_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deliberation worker slug resolves to an OpenRouter (the #991 401 guard),
    JSON/tool-capable model — research-pool-equivalent capability. It must NOT resolve to a
    reasoning-pool-only model like deepseek-r1, whose prose output broke json.loads for the
    H6 turns (#993). ``portfolio/deliberation-`` is pinned in ``model_modes.yaml`` (see
    ``test_deliberation_pinned_to_json_reliable_deepseek_v4_flash``), so the pinned model need
    not also sit in the live ``research`` pool — that pool is cost-tuned independently (#2368).
    """
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    resolved = get_model_for_phase("portfolio/deliberation-NVDA")
    assert resolved is not None
    assert resolved in _CHEAP_PHASE_MODELS


@pytest.mark.unit
def test_get_model_for_mode_does_not_auto_override_when_openrouter_key_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Having OPENROUTER_API_KEY alone must not swap digigraph chat onto dashboard paid models."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
    monkeypatch.setenv("DIGI_LLM_MODE", "test")
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    resolved = get_model_for_mode()
    # Dev/local defaults stay local unless agents.llm / DIGI_LLM_* pin OpenRouter.
    assert not resolved.startswith("openrouter/") or ":free" in resolved


@pytest.mark.unit
def test_get_model_for_mode_keeps_dev_default_without_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside an OpenRouter deploy the legacy dev fallback is preserved (no behavior change)."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DIGI_PROJECT_CONFIG", raising=False)
    monkeypatch.delenv("DIGI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DIGI_LLM_MODEL", raising=False)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    resolved = get_model_for_mode()
    # model_modes.yaml defaults are dev models (ollama/*); not forced to OpenRouter here.
    assert not resolved.startswith("openrouter/")


@pytest.mark.unit
def test_unresolved_capability_returns_none_under_a_bound_byok_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolved capability must short-circuit *before* ``_apply_byok_model_override``.

    The guard above the override is only observable with a BYOK key bound. Without a
    key the override is a pass-through, so ``None`` reaches the caller either way and
    every other test in this file agrees whether the guard is there or not — deleting
    it outright leaves the whole ``tests/dg`` suite green. With a key bound and no
    ``X-BYOK-Model``, the override *refuses* ("no header is not consent"), so an empty
    capability that reached it would turn a benign "no phase model configured" into a
    crash on a credential path — ``AttributeError: 'NoneType' has no attribute
    'partition'`` from ``llm_auth._routes_to_another_provider``, which is *not* in
    ``server._LLM_PROBE_ERRORS``, so ``/test_llm`` would 500 instead of degrading. The
    five production callers
    (``research_agent.py``, ``portfolio_common.py``, ``thesis_common.py``,
    ``h6_deliberation.py``, ``_node_factory.py``) all chain ``or get_model_for_mode()``
    and expect a value, not a raise.
    """
    from digigraph.llm_auth import pop_byok, push_byok_header

    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_digiquant_models_cache", None)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    # 'macro' maps to a capability, so the capability branch is entered; the resolver
    # then comes back empty, which is the state the guard exists for.
    monkeypatch.setattr(model_config, "_model_for_digiquant_capability", lambda *a, **k: None)

    class _Headers:
        def __init__(self, d: dict[str, str]) -> None:
            self._d = {k.lower(): v for k, v in d.items()}

        def get(self, name: str) -> str | None:
            return self._d.get(name.lower())

    class _Req:
        def __init__(self) -> None:
            # No x-byok-model: the header being absent is what makes the override refuse.
            self.headers = _Headers(
                {"x-byok-key": "sk-or-v1-test", "x-byok-provider": "openrouter"}
            )

    tok = push_byok_header(_Req())
    try:
        assert get_model_for_phase("macro") is None
    finally:
        pop_byok(tok)
