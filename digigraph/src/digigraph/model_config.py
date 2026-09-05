"""digigraph model configuration & request-model routing.

Relocated from the former monolithic ``digigraph.llm`` (decommissioned in #632
P2). Owns everything about *which model string* a request should use:

- ``model_modes.yaml`` loading + ``test`` / ``medium`` / ``best`` fallbacks
  (:func:`get_model_for_mode`, :func:`get_model_for_phase`). ``llm_mode: free`` is
  policy-only (no product slug pin); require ``agents.llm`` / ``DIGI_LLM_*``.
- :func:`resolve_effective_model` — ``OLLAMA_MODEL`` / mode-YAML selection,
  normalized for the active ``OPENAI_API_BASE`` (strips the LiteLLM ``ollama/``
  prefix when talking directly to Ollama's OpenAI shim).
- :func:`resolve_request_model` — the single helper that turns the *requested*
  model into the concrete string handed to :func:`digillm.completion`,
  reproducing the provider-key→Ollama fallback and ``ollama-cloud/`` strip the
  old ``chat_completion`` did inline. digillm performs no env/YAML model
  substitution and raises on a missing provider key, so this resolution must
  happen here first.

The LLM calls live in :mod:`digigraph.llm_client`; per-request auth (proxy key /
BYOK) lives in :mod:`digigraph.llm_auth`.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

import yaml
from digillm import get_provider_api_key_env, is_registered_provider
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from digigraph.llm_auth import (
    byok_default_model_refusal,
    byok_model_routes_elsewhere,
    byok_operator_model_routes_elsewhere,
    byok_provider_supported,
    byok_routable_model,
    get_byok_model_override,
    get_byok_override,
)

logger = logging.getLogger(__name__)

_MODEL_MODES_LOAD_ERRORS = (OSError, yaml.YAMLError)

# Open-weight-only policy for dashboard / OpenRouter. Blocks frontier providers and IDs.
_FLAGSHIP_PROVIDER_PREFIXES = frozenset({"openai/", "anthropic/"})
_FLAGSHIP_ALLOWED_POOL_PREFIXES = frozenset({"openai/", "anthropic/", "openai/*", "anthropic/*"})
_FLAGSHIP_MODEL_ID_MARKERS = frozenset(
    {
        "gpt-5",
        "gpt-4o",
        "gpt-4.1",
        "gpt-4-turbo",
        "o1-",
        "o1/",
        "o3-",
        "o3/",
        "o4-",
        "claude-opus",
        "claude-sonnet",
        "claude-3-opus",
        "claude-3-5-sonnet",
        "claude-4",
    }
)
_OPEN_WEIGHT_ALLOWED_MODELS = (
    "deepseek/*,meta-llama/*,mistralai/*,nvidia/*,google/gemma*,perplexity/*"
)
_BALANCED_ALLOWED_MODELS = (
    "deepseek/*,meta-llama/*,mistralai/*,google/*,x-ai/*,openai/gpt-5.6-luna*,perplexity/*"
)
_DEFAULT_COST_QUALITY_TRADEOFF = 10
# Mid-tier OpenAI/Anthropic slugs permitted on ``balanced`` (not ``cheap``). Google and
# xAI models never reach this check — they're never classified flagship (see
# _FLAGSHIP_PROVIDER_PREFIXES / _FLAGSHIP_MODEL_ID_MARKERS above), so they're already
# unrestricted on ``balanced``.
_BALANCED_FLAGSHIP_MARKERS = frozenset(
    {
        "gpt-5.6-luna",
    }
)
_NATIVE_SEARCH_ONLY_PREFIXES = frozenset({"perplexity/"})


# test = minimal tokens; free = free-tier *policy* (not a model pin);
# medium = balanced; best = largest.
# When DIGI_PROJECT_CONFIG is set, agents.llm_mode overrides DIGI_LLM_MODE.
def _get_llm_mode() -> str:
    """Resolve current LLM mode per request. Always reads env/config fresh to avoid global state."""
    if os.environ.get("DIGI_PROJECT_CONFIG"):
        try:
            from digigraph.project_config import DigiProjectConfig

            cfg = DigiProjectConfig.load()
            mode = cfg.get_llm_mode()
            if mode:
                return mode.lower().strip()
        except (ImportError, OSError, AttributeError, TypeError, ValueError) as e:
            logger.warning("Failed to load LLM mode from project config: %s", e)
    return os.environ.get("DIGI_LLM_MODE", "test").lower().strip()


def get_llm_mode() -> str:
    """Public alias for the active ``agents.llm_mode`` / ``DIGI_LLM_MODE`` value."""
    return _get_llm_mode()


_FREE_MODE_MODEL_REQUIRED = (
    "llm_mode=free requires an explicit model: set agents.llm in digiproject "
    "or DIGI_LLM_MODEL (and DIGI_LLM_PROVIDER when the model id is not already "
    "provider-prefixed). Use an OpenRouter :free id or ollama/ local model."
)


def _explicit_llm_from_env() -> tuple[str | None, str | None]:
    """Return ``(provider, model)`` from ``DIGI_LLM_PROVIDER`` / ``DIGI_LLM_MODEL`` (either may be None)."""
    provider = (os.environ.get("DIGI_LLM_PROVIDER") or "").strip().lower() or None
    model = (os.environ.get("DIGI_LLM_MODEL") or "").strip() or None
    return provider, model


def _explicit_llm_config() -> tuple[str | None, str | None, str | None]:
    """Resolve explicit LLM pin from digiproject ``agents.llm`` (wins) or env.

    Returns ``(provider, model, api_key_env)``. YAML wins when set; env fills gaps.
    """
    provider: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    if os.environ.get("DIGI_PROJECT_CONFIG"):
        try:
            from digigraph.project_config import DigiProjectConfig

            llm = DigiProjectConfig.load().get_llm()
            if llm is not None:
                provider = llm.provider.strip().lower()
                model = llm.model.strip()
                api_key_env = llm.resolved_api_key_env()
        except (ImportError, OSError, AttributeError, TypeError, ValueError) as e:
            logger.warning("Failed to load agents.llm from project config: %s", e)
    env_provider, env_model = _explicit_llm_from_env()
    if provider is None and env_provider:
        provider = env_provider
    if model is None and env_model:
        model = env_model
    if provider and model and api_key_env is None:
        from digigraph.project_config import _DEFAULT_LLM_KEY_ENV

        api_key_env = _DEFAULT_LLM_KEY_ENV.get(provider, "OPENAI_API_KEY")
    return provider, model, api_key_env


def is_free_tier_model(model: str) -> bool:
    """True when *model* is acceptable under ``llm_mode: free``.

    Allows OpenRouter ``:free`` slugs and local Ollama ids (no operator spend).
    """
    raw = model.strip()
    if not raw:
        return False
    lower = raw.lower()
    if lower.startswith("ollama/") or lower.startswith("ollama-cloud/"):
        return True
    slug = _openrouter_slug(lower)
    return ":free" in slug


def _compose_provider_model(provider: str, model: str) -> str:
    """Return digillm-routable ``provider/model`` unless *model* already has that prefix."""
    p = provider.strip().lower()
    m = model.strip()
    if p in ("ollama", "litellm", "openai"):
        # openai / litellm often use bare ids; ollama uses ollama/…
        if p == "ollama" and not m.startswith("ollama/") and not m.startswith("ollama-cloud/"):
            return f"ollama/{m}"
        return m
    if m.startswith(f"{p}/"):
        return m
    return f"{p}/{m}"


def _resolve_explicit_model(provider: str | None, model: str | None) -> str | None:
    """Compose an explicit pin, or return a standalone model id from env/YAML."""
    if provider and model:
        return _compose_provider_model(provider, model)
    if model:
        return model.strip()
    return None


def _refuse_paid_in_free_mode(resolved: str, mode: str) -> str:
    """In ``free`` mode, reject non-free models (never silently substitute a product slug)."""
    if mode != "free":
        return resolved
    if is_free_tier_model(resolved):
        return resolved
    msg = (
        f"llm_mode=free refused paid/non-free model {resolved!r}; "
        "set agents.llm or DIGI_LLM_MODEL to an OpenRouter :free or ollama/ local model"
    )
    raise ValueError(msg)


class ModelModesConfig(BaseModel):
    """Parsed ``model_modes.yaml``; unknown keys preserved for forward compatibility."""

    model_config = ConfigDict(extra="allow")

    default_model: str | None = None
    defaults: dict[str, str] = Field(default_factory=dict)
    phase_models: dict[str, str] = Field(default_factory=dict)


class DigiquantOpenRouterTierConfig(BaseModel):
    """OpenRouter env knobs for one dashboard model tier (or global defaults)."""

    allowed_models: str = _OPEN_WEIGHT_ALLOWED_MODELS
    cost_quality_tradeoff: int = _DEFAULT_COST_QUALITY_TRADEOFF


class DigiquantTierConfig(BaseModel):
    """One dashboard cost/quality tier (cheap / balanced / quality)."""

    # Legacy single-pin map — migrated into ``allowed_models`` on load when present.
    models: dict[str, str] = Field(default_factory=dict)
    # Per-capability pools; selection is stable-hash by phase slug (no single-model pins).
    allowed_models: dict[str, list[str]] = Field(default_factory=dict)
    # Web-search grounding pool; defaults to the union of ``allowed_models`` when empty.
    web_search_models: list[str] = Field(default_factory=list)
    # Legacy single grounding pin — ignored when ``web_search_models`` is set.
    grounding_model: str = ""
    openrouter: DigiquantOpenRouterTierConfig = Field(default_factory=DigiquantOpenRouterTierConfig)

    @model_validator(mode="after")
    def _migrate_legacy_models(self) -> DigiquantTierConfig:
        if self.models and not self.allowed_models:
            object.__setattr__(
                self,
                "allowed_models",
                {cap: [mdl] for cap, mdl in self.models.items()},
            )
        return self


class DigiquantModelsConfig(BaseModel):
    """Parsed ``digiquant_models.yaml`` — centralized research/portfolio model policy."""

    default_tier: str = "cheap"
    openrouter_defaults: DigiquantOpenRouterTierConfig = Field(
        default_factory=DigiquantOpenRouterTierConfig
    )
    tiers: dict[str, DigiquantTierConfig] = Field(default_factory=dict)
    phase_capabilities: dict[str, str] = Field(default_factory=dict)
    phase_capability_prefixes: dict[str, str] = Field(default_factory=dict)


_EMPTY_MODEL_MODES = ModelModesConfig()
_model_modes_cache: tuple[float, ModelModesConfig] | None = None
_EMPTY_DIGIQUANT_MODELS = DigiquantModelsConfig()
_digiquant_models_cache: tuple[float, DigiquantModelsConfig] | None = None
_VALID_MODEL_TIERS = frozenset({"cheap", "balanced", "quality"})
_VALID_CAPABILITIES = frozenset({"extraction", "research", "reasoning"})


def _load_model_modes() -> ModelModesConfig:
    """Load model modes YAML (mtime-cached). ``DIGI_MODEL_MODES_FILE`` overrides filename."""
    global _model_modes_cache
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    fname = (
        os.environ.get("DIGI_MODEL_MODES_FILE") or "model_modes.yaml"
    ).strip() or "model_modes.yaml"
    path = Path(config_dir) / fname
    if not path.exists():
        return _EMPTY_MODEL_MODES
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("model_modes load failed (stat): %s", e)
        return _EMPTY_MODEL_MODES
    if _model_modes_cache is not None and _model_modes_cache[0] == mtime:
        return _model_modes_cache[1]
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except _MODEL_MODES_LOAD_ERRORS as e:
        logger.warning("model_modes load failed: %s", e)
        return _EMPTY_MODEL_MODES
    try:
        cfg = ModelModesConfig.model_validate(raw)
    except ValidationError as e:
        logger.warning("model_modes validation failed: %s", e)
        return _EMPTY_MODEL_MODES
    _model_modes_cache = (mtime, cfg)
    return cfg


def _digiquant_models_path() -> Path:
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    return Path(config_dir) / "digiquant_models.yaml"


def _load_digiquant_models() -> DigiquantModelsConfig:
    """Load ``digiquant_models.yaml`` (mtime-cached)."""
    global _digiquant_models_cache
    path = _digiquant_models_path()
    if not path.exists():
        return _EMPTY_DIGIQUANT_MODELS
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("dashboard_models load failed (stat): %s", e)
        return _EMPTY_DIGIQUANT_MODELS
    if _digiquant_models_cache is not None and _digiquant_models_cache[0] == mtime:
        return _digiquant_models_cache[1]
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except _MODEL_MODES_LOAD_ERRORS as e:
        logger.warning("dashboard_models load failed: %s", e)
        return _EMPTY_DIGIQUANT_MODELS
    try:
        cfg = DigiquantModelsConfig.model_validate(raw)
    except ValidationError as e:
        logger.warning("dashboard_models validation failed: %s", e)
        return _EMPTY_DIGIQUANT_MODELS
    _digiquant_models_cache = (mtime, cfg)
    _warn_flagship_models_in_digiquant_config(cfg)
    return cfg


def _openrouter_slug(model: str) -> str:
    """Normalize a model string to the OpenRouter model slug (no ``openrouter/`` prefix)."""
    if model.startswith("openrouter/"):
        return model[len("openrouter/") :]
    return model


def is_flagship_openrouter_model(model: str) -> bool:
    """True when *model* names a blocked frontier provider or model family."""
    slug = _openrouter_slug(model).strip().lower()
    if not slug:
        return False
    for prefix in _FLAGSHIP_PROVIDER_PREFIXES:
        if slug.startswith(prefix):
            return True
    for marker in _FLAGSHIP_MODEL_ID_MARKERS:
        if marker in slug:
            return True
    return False


def is_flagship_allowed_models_entry(entry: str) -> bool:
    """True when an ``allowed_models`` pool entry would admit frontier models."""
    normalized = entry.strip().lower()
    if not normalized:
        return False
    if normalized in _FLAGSHIP_ALLOWED_POOL_PREFIXES:
        return True
    for prefix in _FLAGSHIP_PROVIDER_PREFIXES:
        if normalized.startswith(prefix):
            return True
    return is_flagship_openrouter_model(normalized)


def is_native_search_only_model(model: str) -> bool:
    """True for providers that ground via native search but lack function tools."""
    slug = _openrouter_slug(model).strip().lower()
    return any(slug.startswith(prefix) for prefix in _NATIVE_SEARCH_ONLY_PREFIXES)


def _balanced_allows_flagship_model(model: str) -> bool:
    """Mid-tier frontier models allowed on ``balanced`` but not ``cheap``."""
    slug = _openrouter_slug(model).strip().lower()
    return any(marker in slug for marker in _BALANCED_FLAGSHIP_MARKERS)


def tier_allows_phase_model(model: str, tier: str) -> bool:
    """Whether *model* may run tool-calling / structured-output phase LLM calls."""
    if is_native_search_only_model(model):
        return False
    if not is_tool_use_capable_model(model):
        return False
    if not is_flagship_openrouter_model(model):
        return True
    if tier == "quality":
        return True
    if tier == "balanced":
        return _balanced_allows_flagship_model(model)
    return False


def sanitize_allowed_models(allowed_models: str, *, tier: str = "cheap") -> str:
    """Drop disallowed entries from a comma-separated OpenRouter allowed_models string."""
    if tier == "quality":
        stripped = allowed_models.strip()
        return stripped if stripped else _OPEN_WEIGHT_ALLOWED_MODELS
    entries = [part.strip() for part in allowed_models.split(",") if part.strip()]
    if tier == "balanced":
        kept = [
            entry
            for entry in entries
            if not is_flagship_allowed_models_entry(entry)
            or entry.lower().startswith(("openai/gpt-5.6-luna", "google/", "x-ai/"))
        ]
        return ",".join(kept) if kept else _BALANCED_ALLOWED_MODELS
    kept = [entry for entry in entries if not is_flagship_allowed_models_entry(entry)]
    return ",".join(kept) if kept else _OPEN_WEIGHT_ALLOWED_MODELS


def _effective_openrouter_config(
    tier_name: str,
    tier_cfg: DigiquantTierConfig,
    dashboard: DigiquantModelsConfig,
) -> DigiquantOpenRouterTierConfig:
    """Merge tier overrides with ``openrouter_defaults`` (defaults win on empty tier fields)."""
    defaults = dashboard.openrouter_defaults
    tier_or = tier_cfg.openrouter
    allowed = tier_or.allowed_models.strip() or defaults.allowed_models
    tradeoff = (
        tier_or.cost_quality_tradeoff
        if tier_or.cost_quality_tradeoff is not None
        else defaults.cost_quality_tradeoff
    )
    return DigiquantOpenRouterTierConfig(
        allowed_models=sanitize_allowed_models(allowed, tier=tier_name),
        cost_quality_tradeoff=tradeoff,
    )


def _warn_flagship_models_in_digiquant_config(cfg: DigiquantModelsConfig) -> None:
    """Log when digiquant_models.yaml pools a frontier model on a restricted tier."""
    for tier_name, tier_cfg in cfg.tiers.items():
        if tier_name == "quality":
            continue
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                if is_flagship_openrouter_model(model) and not tier_allows_phase_model(
                    model, tier_name
                ):
                    logger.warning(
                        "dashboard_models tier=%s capability=%s pools disallowed model %r",
                        tier_name,
                        capability,
                        model,
                    )
    pool = sanitize_allowed_models(cfg.openrouter_defaults.allowed_models, tier="cheap")
    if pool != cfg.openrouter_defaults.allowed_models.strip():
        logger.debug(
            "dashboard_models openrouter_defaults sanitized for cheap tier to %r",
            pool,
        )


def _phase_models_override(phase_slug: str, phase_models: dict[str, str]) -> str | None:
    """Resolve an explicit ``phase_models`` entry, or None when absent."""
    if phase_slug in phase_models:
        return phase_models[phase_slug]
    for key, mdl in phase_models.items():
        if key.endswith("-") and phase_slug.startswith(key):
            return mdl
    return None


def get_digiquant_tier() -> str:
    """Active dashboard tier from ``OLYMPUS_MODEL_TIER`` or ``digiquant_models.yaml`` default."""
    if "DIGIQUANT_MODEL_TIER" in os.environ:
        raw = os.environ.get("DIGIQUANT_MODEL_TIER", "").strip().lower()
    else:
        raw = os.environ.get("OLYMPUS_MODEL_TIER", "").strip().lower()
    if raw in _VALID_MODEL_TIERS:
        return raw
    return _load_digiquant_models().default_tier or "cheap"


def _capability_for_phase(phase_slug: str, cfg: DigiquantModelsConfig) -> str | None:
    """Map a phase slug to extraction / research / reasoning, or None if unknown."""
    if phase_slug in cfg.phase_capabilities:
        return cfg.phase_capabilities[phase_slug]
    for prefix, cap in cfg.phase_capability_prefixes.items():
        if prefix.endswith("-") and phase_slug.startswith(prefix):
            return cap
    return None


def is_tool_use_capable_model(model: str) -> bool:
    """True when *model* may run OpenRouter function-tool phases (query_data, query_research).

    Tool capability is decoupled from web search. The ``:online`` suffix only activates
    OpenRouter's built-in web plugin — it does **not** imply function-tool support. For
    open-weight models the ``:online`` endpoints reject function tools outright (404
    "No endpoints found that support tool use"), which is why pinning ``:online`` slugs in
    phase pools broke the pipeline. Grounding is supplied by a separate web-search pre-pass
    (:func:`get_grounding_model` over ``web_search_models``) that injects a ``web_grounding``
    block into the prompt, so phase models never need ``:online`` themselves.

    Therefore a model is tool-capable iff it is a plain (bare) OpenRouter slug that is not a
    native-search-only provider (perplexity/*) and does not carry the ``:online`` suffix.
    """
    slug = _openrouter_slug(model).strip().lower()
    if not slug or is_native_search_only_model(model):
        return False
    # ``:online`` is a web-search variant, not a function-tool signal — route it via
    # ``web_search_models`` grounding only, never phase/tool calls.
    if ":online" in slug:
        return False
    return True


def is_web_search_capable_model(model: str) -> bool:
    """True when *model* can ground via ``:online`` or native search (perplexity/*)."""
    slug = _openrouter_slug(model).strip().lower()
    if not slug:
        return False
    if is_native_search_only_model(model):
        return True
    return ":online" in slug


def _pick_from_pool(pool: list[str], key: str) -> str:
    """Stable deterministic pick from *pool* using *key* (phase slug / segment)."""
    if not pool:
        msg = "empty model pool"
        raise ValueError(msg)
    digest = hashlib.sha256(key.encode()).hexdigest()
    return pool[int(digest[:8], 16) % len(pool)]


def _tier_capability_pool(tier_cfg: DigiquantTierConfig, capability: str) -> list[str]:
    pool = list(tier_cfg.allowed_models.get(capability) or [])
    if not pool:
        legacy = tier_cfg.models.get(capability)
        if legacy:
            pool = [legacy]
    return pool


def _tier_web_search_pool(tier_cfg: DigiquantTierConfig) -> list[str]:
    if tier_cfg.web_search_models:
        pool = list(tier_cfg.web_search_models)
    else:
        seen: set[str] = set()
        merged: list[str] = []
        for capability in ("research", "extraction", "reasoning"):
            for model in _tier_capability_pool(tier_cfg, capability):
                if model not in seen:
                    seen.add(model)
                    merged.append(model)
        if merged:
            pool = merged
        elif tier_cfg.grounding_model:
            pool = [tier_cfg.grounding_model]
        else:
            pool = []
    return [m for m in pool if is_web_search_capable_model(m)]


def _model_for_digiquant_capability(capability: str, tier: str, phase_slug: str) -> str | None:
    if capability not in _VALID_CAPABILITIES:
        return None
    tier_cfg = _load_digiquant_models().tiers.get(tier)
    if tier_cfg is None:
        return None
    pool = [
        m for m in _tier_capability_pool(tier_cfg, capability) if tier_allows_phase_model(m, tier)
    ]
    if not pool:
        return None
    return _pick_from_pool(pool, phase_slug)


def get_grounding_model(*, segment: str = "grounding") -> str | None:
    """Return a web-search-capable model for digiquant grounding pre-passes.

    Pool is filtered to ``perplexity/*`` / ``:online`` only (#2567) — house
    grounding must not use the digillm Exa toolkit branch. Slugs are unprefixed
    OpenRouter ids resolved through LiteLLM (#3414).
    """
    tier_cfg = _load_digiquant_models().tiers.get(get_digiquant_tier())
    if tier_cfg is None:
        return None
    pool = _tier_web_search_pool(tier_cfg)
    if not pool:
        return None
    return _pick_from_pool(pool, segment)


def apply_digiquant_openrouter_env(*, force: bool = False) -> str:
    """Apply house LLM routing + OpenRouter cost knobs from the active digiquant tier.

    When ``OPENAI_API_BASE`` is already set (Docker LiteLLM, stack-local), leave it
    alone — house pins are unprefixed slugs on that proxy's ``model_list``.

    CLI / GHA without a local proxy: point the default client at OpenRouter's
    OpenAI-compatible API and copy ``OPENROUTER_API_KEY`` into ``OPENAI_API_KEY``
    when that is unset, so unprefixed pins do not hit api.openai.com.

    Also sets ``OPENROUTER_ALLOWED_MODELS`` and ``OPENROUTER_COST_QUALITY_TRADEOFF``
    when unset (or when *force*). Called at chain startup so CI picks up tier policy
    without duplicating values in ``digiquant-pipeline.yml``.
    """
    if not (os.environ.get("OPENAI_API_BASE") or "").strip():
        os.environ["OPENAI_API_BASE"] = "https://openrouter.ai/api/v1"
        if not (os.environ.get("OPENAI_API_KEY") or "").strip():
            or_key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
            if or_key:
                os.environ["OPENAI_API_KEY"] = or_key
    tier = get_digiquant_tier()
    tier_cfg = _load_digiquant_models().tiers.get(tier)
    if tier_cfg is None:
        logger.warning("dashboard tier %r not found in digiquant_models.yaml", tier)
        return tier
    dashboard = _load_digiquant_models()
    or_cfg = _effective_openrouter_config(tier, tier_cfg, dashboard)
    if or_cfg.allowed_models and (
        force or not os.environ.get("OPENROUTER_ALLOWED_MODELS", "").strip()
    ):
        os.environ["OPENROUTER_ALLOWED_MODELS"] = or_cfg.allowed_models
    if or_cfg.cost_quality_tradeoff is not None and (
        force or not os.environ.get("OPENROUTER_COST_QUALITY_TRADEOFF", "").strip()
    ):
        os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] = str(or_cfg.cost_quality_tradeoff)
    logger.info(
        "dashboard model tier=%s openrouter_pool=%s tradeoff=%s",
        tier,
        os.environ.get("OPENROUTER_ALLOWED_MODELS", ""),
        os.environ.get("OPENROUTER_COST_QUALITY_TRADEOFF", ""),
    )
    return tier


def _apply_byok_model_override(resolved: str) -> str:
    """Point an active BYOK request at the user's own model — never at an operator key.

    ``X-BYOK-Model`` is caller-supplied, so it is untrusted input on a credential
    path. A model naming a *different* registered provider is discarded, which leaves
    the request exactly where it would have been had the header been absent; see
    :func:`digigraph.llm_auth.byok_model_routes_elsewhere` for why that check is one
    rule rather than a per-provider ladder.

    This is an *independent* second door, not a backstop that assumes the first one
    fired: it re-derives the verdict from the bound slug and never consults the
    middleware. The two doors hold different strings — the middleware holds the raw
    header, this holds the once-stripped slug from ``_normalize_byok_model_slug`` —
    and they agree only because :func:`byok_routable_model` strips a provider's own
    prefix to a *fixpoint*, which makes the verdict invariant under that stripping.
    Given that invariant an HTTP mismatch is always refused with a 400 before the
    override is ever bound, so reaching this discard means an in-process caller.

    The model slug is never logged (see ``_byok_model_override`` in llm_auth), so the
    warning names the provider and not the value that was dropped.

    **No header is not consent.** When the key is bound and no ``X-BYOK-Model`` came
    with it, *resolved* is whatever the operator's own configuration produced — the
    tier default on the mode path, a ``phase_models`` override or a capability model
    on the phase path — and if that names a registered provider, digillm serves it
    from the operator's env key while the
    user's key sits bound, displayed as active, and unspent. That is the same
    mis-billing as a foreign ``X-BYOK-Model``, arrived at by omission instead of by
    input, so it gets the same answer: refuse. :class:`ValueError` rather than a
    fallback, because there is nothing to fall back *to* — every model this function
    could substitute is either the operator's (wrong payer) or one the caller never
    chose (wrong model), and silently picking a model is the surprise this whole
    module exists to prevent. ``ValueError`` is already the refusal type here
    (``_FREE_MODE_MODEL_REQUIRED``) and is in ``server._LLM_PROBE_ERRORS``, so
    ``/test_llm`` still degrades instead of crashing.
    """
    byok = get_byok_override()
    if not byok:
        return resolved
    _key, provider = byok
    user_model = get_byok_model_override()
    if user_model and byok_model_routes_elsewhere(provider, user_model):
        logger.warning(
            "BYOK provider %r sent an X-BYOK-Model naming another provider; ignoring it "
            "so the user's key is the one that pays",
            provider,
        )
        # Discarded, not substituted: fall through to the no-header branch so the
        # request lands exactly where it would have landed had the header never been
        # sent. Returning *resolved* here instead would hand back the operator's own
        # default -- which, if that default names a registered provider, is the very
        # mis-billing this function refuses two lines below (#2490).
        user_model = ""
    if not user_model:
        if byok_operator_model_routes_elsewhere(provider, resolved):
            raise ValueError(byok_default_model_refusal(provider))
        return resolved
    return byok_routable_model(provider, user_model)


def _fallback_model_for_mode(mode: str) -> tuple[str, str]:
    """Resolve the deployment default when no explicit operator pin is configured.

    Returns ``(model, source_label)``. Extracted because two callers need the same
    ladder and a credential-adjacent rule must not exist in two copies:
    :func:`effective_llm_settings` (which also reports ``provider`` / ``api_key_env`` /
    ``source``, so it cannot just call :func:`operator_default_model`) and
    :func:`operator_default_model` itself, whose answer the BYOK middleware uses to
    decide whether the deployment default would bill someone other than the caller.

    Raises :class:`ValueError` in ``llm_mode: free``, where an explicit pin is
    mandatory — ``defaults.free`` is access policy, never a product slug.
    """
    if mode == "free":
        raise ValueError(_FREE_MODE_MODEL_REQUIRED)
    data = _load_model_modes()
    if data.default_model:
        return str(data.default_model), "model_modes.default_model"
    # ``free`` is policy-only — never read a product slug from defaults.free.
    resolved = data.defaults.get(mode) or data.defaults.get("test") or "gpt-4o-mini"
    return resolved, ("model_modes" if data.defaults else "default")


def effective_llm_settings() -> dict[str, object]:
    """Return effective LLM settings for CLI / diagnostics (never includes secret values).

    Keys: ``provider``, ``model``, ``llm_mode``, ``api_key_env``, ``api_key_present``,
    ``source`` (``agents.llm`` | ``env`` | ``model_modes.default_model`` |
    ``model_modes`` | ``default``).
    """
    mode = _get_llm_mode()
    provider, model, api_key_env = _explicit_llm_config()
    source = "default"
    resolved = _resolve_explicit_model(provider, model)
    if resolved is not None:
        source = "agents.llm" if os.environ.get("DIGI_PROJECT_CONFIG") else "env"
        # Prefer more precise source when YAML provided the pin.
        if os.environ.get("DIGI_PROJECT_CONFIG"):
            try:
                from digigraph.project_config import DigiProjectConfig

                if DigiProjectConfig.load().get_llm() is not None:
                    source = "agents.llm"
                elif _explicit_llm_from_env() != (None, None):
                    source = "env"
            except (ImportError, OSError, AttributeError, TypeError, ValueError):
                source = "env"
    else:
        resolved, source = _fallback_model_for_mode(mode)
        if "/" in resolved:
            provider = resolved.split("/", 1)[0]
        else:
            provider = "openai"
        model = resolved
        if api_key_env is None:
            from digigraph.project_config import _DEFAULT_LLM_KEY_ENV

            api_key_env = _DEFAULT_LLM_KEY_ENV.get(provider or "", "OPENAI_API_KEY")
    resolved = _refuse_paid_in_free_mode(resolved, mode)
    key_env = api_key_env or "OPENAI_API_KEY"
    return {
        "provider": provider,
        "model": resolved,
        "llm_mode": mode,
        "api_key_env": key_env,
        "api_key_present": bool(os.environ.get(key_env, "").strip()),
        "source": source,
    }


def operator_default_model() -> str:
    """Resolve the deployment's fallback model with **no** BYOK override applied.

    :func:`get_model_for_mode` is this plus :func:`_apply_byok_model_override`; the
    split exists so a caller can ask what the *operator* configured without the
    answer depending on whether a BYOK key happens to be bound. The BYOK middleware
    is that caller: it must know, before binding the key, whether the deployment's
    own default would route the request to some other provider's env key.

    Today the middleware runs its checks before ``push_byok_header``, so calling
    ``get_model_for_mode()`` there would return the same string by coincidence of
    ordering. Coincidence is the wrong thing to build a credential check on — this
    name makes the independence structural instead.

    Raises :class:`ValueError` in ``llm_mode: free`` without an explicit pin, exactly
    as ``get_model_for_mode`` always has.
    """
    mode = _get_llm_mode()
    provider, model, _api_key_env = _explicit_llm_config()
    resolved = _resolve_explicit_model(provider, model)
    if resolved is None:
        resolved, _source = _fallback_model_for_mode(mode)
    return _refuse_paid_in_free_mode(resolved, mode)


def get_model_for_mode() -> str:
    """Return the fallback model for phases without a phase_models entry.

    Resolution order:
    1. Explicit ``agents.llm`` / ``DIGI_LLM_PROVIDER``+``DIGI_LLM_MODEL`` — operator pin.
    2. For ``llm_mode: free`` without an explicit pin → :class:`ValueError` (policy only;
       no shared product slug in ``model_modes.yaml``).
    3. ``default_model`` in model_modes.yaml — optional explicit fallback (non-free).
    4. ``defaults[llm_mode]`` for ``test`` / ``medium`` / ``best`` — mode-keyed fallback.
    5. ``"gpt-4o-mini"`` — hard last resort (non-free modes only).

    OpenRouter paid/dashboard auto-override is **not** applied here. dashboard/research
    phases use :func:`get_model_for_phase`. Having ``OPENROUTER_API_KEY`` set alone
    must not swap a free/local digithings install onto paid dashboard models.
    ``llm_mode: free`` refuses non-``:free`` (non-Ollama) model ids.
    """
    return _apply_byok_model_override(operator_default_model())


def get_model_for_phase(phase_slug: str) -> str | None:
    """Return the configured model for a phase slug (exact or prefix match), or None.

    Resolution order:
    1. ``model_modes.yaml`` ``phase_models`` — explicit per-phase override (frontier escape hatch).
    2. ``digiquant_models.yaml`` — capability tier × ``OLYMPUS_MODEL_TIER``.
    3. ``None`` → caller uses :func:`get_model_for_mode`.

    Prefix match in ``phase_models``: a key ending in '-' (e.g. 'analyst-') matches any
    slug that starts with that prefix (e.g. 'analyst-AAPL').
    """
    data = _load_model_modes()
    phase_models = data.phase_models
    tier = get_digiquant_tier()
    override = _phase_models_override(phase_slug, phase_models)
    if override is not None:
        if tier_allows_phase_model(override, tier):
            return _apply_byok_model_override(override)
        logger.warning(
            "Rejecting phase_models override for %s (%r) on tier %s; "
            "using digiquant_models.yaml instead",
            phase_slug,
            override,
            tier,
        )

    dashboard = _load_digiquant_models()
    capability = _capability_for_phase(phase_slug, dashboard)
    if capability is not None:
        # _model_for_digiquant_capability is str | None; the override takes str and now
        # *refuses* rather than passing through, so an unresolved capability must
        # short-circuit instead of reaching it.
        capability_model = _model_for_digiquant_capability(capability, tier, phase_slug)
        if not capability_model:
            # Signature is ``str | None``; a blank pool entry must read as "unresolved",
            # not as an empty model name. Callers chain ``or get_model_for_mode()``, so
            # this is inert today — it stays None so it cannot become a bug later.
            return None
        return _apply_byok_model_override(capability_model)
    return None


def _parse_provider_prefix(model: str) -> tuple[str | None, str]:
    """Split 'provider/model_id' into (provider, model_id) for known external providers.

    Providers are digillm's own registry (:func:`digillm.is_registered_provider`) —
    digigraph does not keep a second copy. Returns (None, model) for Ollama-native
    model strings (including 'ollama-cloud/…').
    """
    if "/" in model:
        provider, _, model_id = model.partition("/")
        if is_registered_provider(provider):
            return provider, model_id
    return None, model


def _openai_base_looks_like_direct_ollama(base_url: str | None) -> bool:
    """True when requests go to Ollama's built-in OpenAI-compatible server (not LiteLLM)."""
    if not base_url:
        return False
    u = base_url.strip().lower()
    if ":11434" in u:
        return True
    if os.environ.get("DIGI_DIRECT_OLLAMA_OPENAI", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def resolve_effective_model(request_model: str) -> str:
    """``OLLAMA_MODEL`` or mode YAML or *request_model*, normalized for the active ``OPENAI_API_BASE``."""
    m = (os.environ.get("OLLAMA_MODEL") or "").strip() or get_model_for_mode() or request_model
    base = os.environ.get("OPENAI_API_BASE")
    if _openai_base_looks_like_direct_ollama(base) and m.startswith("ollama/"):
        return m[len("ollama/") :]
    return m


def resolve_request_model(request_model: str) -> str:
    """Return the concrete model string to hand to :func:`digillm.completion`.

    Reproduces the routing the legacy ``digigraph.llm.chat_completion`` performed
    inline. digillm does no env/YAML substitution and *raises* on a missing
    provider key, so resolution happens here:

    - ``provider/model_id`` for a known external provider (gemini/xai/openrouter) whose
      API key is set → returned unchanged; digillm routes it to that provider.
    - same prefix but the key is **missing** → fall back to the Ollama mode model
      (``resolve_effective_model(get_model_for_mode())``), mirroring the legacy
      silent Ollama fallback rather than digillm's hard error — **except** when a
      BYOK override is bound for that same provider (user key pays; keep the slug).
    - ``ollama-cloud/<model>`` → strip the prefix (Ollama Cloud expects bare
      names); ``resolve_effective_model`` is intentionally NOT applied so a mode
      default can't override an explicit cloud model.
    - bare / non-prefixed slug with an active BYOK override **for a routable
      provider** → returned unchanged. ``openai`` is not a digillm-registered
      prefix, so OpenAI BYOK models are bare (``gpt-4o-mini``).
      ``resolve_effective_model`` prefers ``OLLAMA_MODEL`` over the request
      string; applying it under BYOK would send a local Ollama slug to the
      user's OpenAI (or other) endpoint while digillm still holds their key.
      Gated on :func:`byok_provider_supported` rather than "BYOK is bound at
      all": ``push_byok_header`` sets digigraph's override whenever a key is
      present, independent of whether the provider has a catalog base URL, so
      checking presence alone would let an unroutable-provider override this
      branch too — harmless only by the coincidence that server.py's 400 on
      unroutable providers (#1873) never lets one reach here today.
    - unprefixed house digiquant slugs (``deepseek/…``, ``meta-llama/…``,
      ``perplexity/…``, …) → returned unchanged. After #3414 these are not
      registered provider prefixes; digillm sends them to ``OPENAI_API_BASE``
      (LiteLLM, or the CLI/GHA OpenRouter rewrite). They must not fall through
      to ``resolve_effective_model``, which prefers ``OLLAMA_MODEL`` /
      ``model_modes`` local defaults (``ollama/qwen3:8b``) and would hand
      OpenRouter an invalid model id.
    - anything else → ``resolve_effective_model(request_model)``.
    """
    provider, _model_id = _parse_provider_prefix(request_model)
    if provider is not None:
        api_key_env = get_provider_api_key_env(provider)
        assert api_key_env is not None, f"provider {provider!r} matched a registered prefix"
        if os.environ.get(api_key_env, "").strip():
            return request_model
        byok = get_byok_override()
        if byok and byok[1] == provider:
            return request_model
        logger.warning(
            "Provider %r key (%s) not configured; falling back to Ollama mode model",
            provider,
            api_key_env,
        )
        return resolve_effective_model(get_model_for_mode())
    if request_model.startswith("ollama-cloud/"):
        return request_model[len("ollama-cloud/") :]
    # BYOK already chose the spendable model via ``_apply_byok_model_override``.
    # Do not let ``OLLAMA_MODEL`` / mode defaults clobber a bare OpenAI (etc.) slug.
    # Gated on the provider actually being BYOK-routable, not just "a BYOK override
    # is bound" -- see the docstring note on ``push_byok_header`` vs ``set_byok``.
    byok = get_byok_override()
    if byok is not None and byok_provider_supported(byok[1]):
        return request_model
    # House digiquant pins (#3414) are unprefixed OpenRouter-style slugs such as
    # ``deepseek/deepseek-v4-flash``. They are not registered providers, so the
    # branch above does not keep them. Without this guard, ``resolve_effective_model``
    # clobbers them with ``model_modes`` local defaults (``ollama/qwen3:8b``), which
    # OpenRouter rejects ("not a valid model ID") on decision_log reflector and every
    # other digiquant phase that goes through digigraph → digillm.
    if "/" in request_model and not request_model.startswith("ollama/"):
        return request_model
    return resolve_effective_model(request_model)
