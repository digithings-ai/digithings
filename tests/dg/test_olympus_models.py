"""Olympus model tier policy (config/olympus_models.yaml)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import digigraph.model_config as model_config
from digigraph.model_config import (
    apply_olympus_openrouter_env,
    get_grounding_model,
    get_model_for_mode,
    get_model_for_phase,
    get_olympus_tier,
    is_flagship_allowed_models_entry,
    is_flagship_openrouter_model,
    is_native_search_only_model,
    is_tool_use_capable_model,
    is_web_search_capable_model,
    sanitize_allowed_models,
    tier_allows_phase_model,
)

_REPO_CONFIG = str(Path(__file__).parents[2] / "config")

# Phase pools = bare OpenRouter slugs (function tools). The ``:online`` suffix is a
# web-search variant only and must never appear in a phase pool — it 404s on tool use
# for open-weight models. Web-search/grounding slugs keep ``:online``/perplexity below.
_CHEAP_PHASE_MODELS = frozenset(
    {
        "openrouter/deepseek/deepseek-chat",
        "openrouter/deepseek/deepseek-v4-flash",  # #1622: 1M ctx, tools + strict json_schema
        # deepseek-r1 removed from every phase pool (#1622): CoT output is not reliably
        # strict JSON (#1617 master-digest JSONDecodeError). Re-adding it here must be a
        # deliberate decision, not a drive-by.
        "openrouter/meta-llama/llama-4-maverick",
    }
)

_BALANCED_PHASE_MODELS = _CHEAP_PHASE_MODELS | frozenset(
    {
        "openrouter/z-ai/glm-5",  # #1622
        "openrouter/google/gemini-2.0-flash-001",
        "openrouter/openai/gpt-4o-mini",
        "openrouter/x-ai/grok-3-mini",
    }
)

_QUALITY_PHASE_MODELS = _BALANCED_PHASE_MODELS | frozenset(
    {
        "openrouter/deepseek/deepseek-v4-pro",  # #1622
        "openrouter/openai/gpt-4o",
        "openrouter/anthropic/claude-sonnet-4",
        "openrouter/google/gemini-2.5-flash",
        "openrouter/google/gemini-2.5-pro",
        "openrouter/x-ai/grok-3",
    }
)

# Web-search/grounding pools keep ``:online`` (built-in plugin) and perplexity (native).
_WEB_SEARCH_MODELS = frozenset(
    {
        "openrouter/perplexity/sonar",
        "openrouter/deepseek/deepseek-chat:online",
        "openrouter/deepseek/deepseek-v4-flash:online",  # #1622
        "openrouter/deepseek/deepseek-r1:online",
        "openrouter/meta-llama/llama-4-maverick:online",
        "openrouter/google/gemini-2.0-flash-001:online",
        "openrouter/openai/gpt-4o-mini:online",
        "openrouter/openai/gpt-4o:online",
        "openrouter/anthropic/claude-sonnet-4:online",
    }
)

_TIER_PHASE_MODELS = {
    "cheap": _CHEAP_PHASE_MODELS,
    "balanced": _BALANCED_PHASE_MODELS,
    "quality": _QUALITY_PHASE_MODELS,
}

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
def test_deliberation_pinned_to_json_reliable_deepseek_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression (Olympus daily, run 28014812240, #1006): H6 deliberation turns must emit
    strict JSON (DeliberationPmTurn / DeliberationAnalystTurn). #991 first mapped the phase to
    the ``reasoning`` pool (prose-only deepseek-r1 → json.loads failed at char 0); #998 then
    routed it to the cheap ``research`` pool — but that pool also contains ``llama-4-maverick``,
    which returns *empty* completions under STRICT json_schema, so the ~half of tickers hashing
    onto it still failed at char 0. Deliberation is now pinned (model_modes.yaml ``phase_models``)
    to deepseek-chat — the json/tool-reliable open-weight model — for *every* ticker, bypassing
    the pool hash. Never maverick, never r1.
    """
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    # The live macro watchlist from the failing run.
    watchlist = (
        "SPY QQQ DIA IWB VTI MDY IJH IWM IJR XLK XLF XLE XLV XLI XLRE XLU XLY XLP XLB XLC "
        "EFA VEA VGK EWJ EWG EWU EWA EEM VWO FXI ASHR EWZ EWT EWY INDA BITO IBIT FBTC ETHA "
        "FETH GBTC GLD IAU SLV DBO USO BNO PDBC DJP CPER BIL SHV SHY IEF TLT AGG HYG LQD TIP "
        "EMB DXY UUP VIX"
    ).split()
    for ticker in watchlist:
        model = get_model_for_phase(f"hermes/portfolio/deliberation-{ticker}")
        assert model == "openrouter/deepseek/deepseek-chat", (
            f"deliberation-{ticker} -> {model!r}, expected the pinned json-reliable deepseek-chat"
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
    assert model == "openrouter/deepseek/deepseek-v4-flash"
    assert is_tool_use_capable_model(model)


@pytest.mark.unit
def test_asset_analyst_slug_resolves_to_known_good_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H5 asset-analyst must resolve from the extraction pool (CI run 27950332738)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    model = get_model_for_phase("hermes/portfolio/asset-analyst-AAPL")
    assert model is not None
    assert model.startswith("openrouter/")
    assert model in _CHEAP_PHASE_MODELS
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
def test_balanced_tier_includes_mid_frontier_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "balanced")
    cfg = model_config._load_olympus_models()
    balanced = cfg.tiers["balanced"]
    research = balanced.allowed_models["research"]
    assert any("gpt-4o-mini" in m for m in research)
    assert any("gemini" in m for m in research)
    model = get_model_for_phase("macro")
    assert model is not None
    assert tier_allows_phase_model(model, "balanced")


@pytest.mark.unit
def test_quality_tier_allows_frontier_in_pools() -> None:
    cfg = model_config._load_olympus_models()
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
    assert "perplexity/*" in pool
    assert "qwen" not in pool.lower()
    assert "openai" not in pool
    assert "anthropic" not in pool
    assert os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] == "10"


@pytest.mark.unit
def test_apply_quality_tier_preserves_frontier_auto_router_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_ALLOWED_MODELS", raising=False)
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "quality")
    apply_olympus_openrouter_env()
    pool = os.environ["OPENROUTER_ALLOWED_MODELS"]
    assert "openai/*" in pool
    assert "anthropic/*" in pool


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
    cfg = model_config._load_olympus_models()
    assert model in cfg.tiers["cheap"].web_search_models


@pytest.mark.unit
def test_grounding_model_may_be_perplexity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Perplexity is valid for grounding-only paths, not tool phases."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    cfg = model_config._load_olympus_models()
    assert "openrouter/perplexity/sonar" in cfg.tiers["cheap"].web_search_models
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
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    assert get_model_for_phase("macro") in _cheap_research_pool()


@pytest.mark.unit
def test_phase_models_mid_tier_override_wins_on_balanced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A bare (tool-capable) mid-tier slug is accepted as an override on balanced.
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/openai/gpt-4o-mini"\n'
    )
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "balanced")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/openai/gpt-4o-mini"


@pytest.mark.unit
def test_phase_models_open_weight_override_wins(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A bare open-weight slug (not in the macro/research pool) is tool-capable, so the
    # override is honored and wins over the tier pool.
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/deepseek/deepseek-r1"\n'
    )
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    assert get_model_for_phase("macro") == "openrouter/deepseek/deepseek-r1"


@pytest.mark.unit
def test_phase_models_online_override_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: a ``:online`` override is web-search-only and must NOT route a phase.

    The override is rejected (not tool-capable) and routing falls back to the tier's
    bare phase pool from olympus_models.yaml.
    """
    (tmp_path / "model_modes.yaml").write_text(
        'phase_models:\n  macro: "openrouter/mistralai/mistral-small-3.1-24b-instruct:online"\n'
    )
    (tmp_path / "olympus_models.yaml").write_text(
        Path(_REPO_CONFIG, "olympus_models.yaml").read_text()
    )
    monkeypatch.setenv("DIGI_CONFIG_PATH", str(tmp_path))
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    model = get_model_for_phase("macro")
    assert model in _cheap_research_pool()
    assert ":online" not in model
    assert is_tool_use_capable_model(model)


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
    cfg = model_config._load_olympus_models()
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
def test_no_stale_qwen_model_ids_in_olympus_config() -> None:
    """Regression: retired qwen/qwen3-235b slugs 400 on OpenRouter (CI run 27950332738)."""
    yaml_text = Path(_REPO_CONFIG, "olympus_models.yaml").read_text().lower()
    hits = [marker for marker in _BANNED_QWEN_MODEL_MARKERS if marker in yaml_text]
    assert not hits, f"olympus_models.yaml still references banned Qwen slugs: {hits}"

    cfg = model_config._load_olympus_models()
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
    # Phase models are bare (tool-capable); grounding is a separate web-search pre-pass.
    assert ":online" not in model
    assert is_tool_use_capable_model(model)
    assert not is_web_search_capable_model(model)


@pytest.mark.unit
def test_cheap_tier_has_no_flagship_pins() -> None:
    cfg = model_config._load_olympus_models()
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
    cfg = model_config._load_olympus_models()
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
# Regression: the Hermes deliberation worker built slug
# ``hermes/portfolio/deliberation-{ticker}`` which matched no phase_capabilities entry
# nor prefix, so get_model_for_phase returned None and the caller fell back to
# get_model_for_mode() -> a dev model (ollama/*) that digillm routed to the default
# OpenAI client -> 401 "Incorrect API key provided: not-set", failing the live baseline.


@pytest.mark.unit
@pytest.mark.parametrize(
    "slug",
    [
        "hermes/portfolio/deliberation-AAPL",  # the regression: was unmapped
        "h6_pm_challenge-AAPL",
        "h6_analyst_response-AAPL",
        "hermes/portfolio/asset-analyst-AAPL",
        "hermes/portfolio/pm-direction",
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
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    resolved = get_model_for_phase(slug)
    assert resolved is not None, f"phase slug {slug!r} is unmapped — falls back to dev model (401)"
    assert resolved.startswith("openrouter/"), (
        f"phase slug {slug!r} resolved to non-OpenRouter model {resolved!r}"
    )


@pytest.mark.unit
def test_deliberation_slug_routes_to_research_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deliberation worker slug routes to the tier research pool — OpenRouter (the #991
    401 guard) and JSON/tool-capable. It must NOT use the reasoning pool, whose deepseek-r1
    returns prose and broke json.loads for the H6 turns (#993)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    cfg = model_config._load_olympus_models()
    assert (
        get_model_for_phase("hermes/portfolio/deliberation-NVDA")
        in cfg.tiers["cheap"].allowed_models["research"]
    )


@pytest.mark.unit
def test_get_model_for_mode_uses_tier_reasoning_in_openrouter_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: with OPENROUTER_API_KEY set, a dev fallback (ollama/*) must be
    replaced by an OpenRouter-routable tier reasoning model, never leak to the default
    OpenAI client (which 401s)."""
    monkeypatch.setenv("OLYMPUS_MODEL_TIER", "cheap")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(model_config, "_olympus_models_cache", None)
    resolved = get_model_for_mode()
    assert resolved.startswith("openrouter/"), (
        f"get_model_for_mode leaked non-OpenRouter fallback {resolved!r} in OpenRouter deploy"
    )


@pytest.mark.unit
def test_get_model_for_mode_keeps_dev_default_without_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside an OpenRouter deploy the legacy dev fallback is preserved (no behavior change)."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(model_config, "_model_modes_cache", None)
    resolved = get_model_for_mode()
    # model_modes.yaml defaults are dev models (ollama/*); not forced to OpenRouter here.
    assert not resolved.startswith("openrouter/")
