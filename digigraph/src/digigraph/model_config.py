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

from digigraph.llm_auth import get_byok_model_override, get_byok_override

logger = logging.getLogger(__name__)

_MODEL_MODES_LOAD_ERRORS = (OSError, yaml.YAMLError)

# Open-weight-only policy for Olympus / OpenRouter. Blocks frontier providers and IDs.
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
    "deepseek/*,meta-llama/*,mistralai/*,google/*,x-ai/*,openai/gpt-4o-mini*,perplexity/*"
)
_DEFAULT_COST_QUALITY_TRADEOFF = 10
# Mid-tier frontier slugs permitted on ``balanced`` (not ``cheap``).
_BALANCED_FLAGSHIP_MARKERS = frozenset(
    {
        "gpt-4o-mini",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "grok-3-mini",
        "grok-3",
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


class OlympusOpenRouterTierConfig(BaseModel):
    """OpenRouter env knobs for one Olympus model tier (or global defaults)."""

    allowed_models: str = _OPEN_WEIGHT_ALLOWED_MODELS
    cost_quality_tradeoff: int = _DEFAULT_COST_QUALITY_TRADEOFF


class OlympusTierConfig(BaseModel):
    """One Olympus cost/quality tier (cheap / balanced / quality)."""

    # Legacy single-pin map — migrated into ``allowed_models`` on load when present.
    models: dict[str, str] = Field(default_factory=dict)
    # Per-capability pools; selection is stable-hash by phase slug (no single-model pins).
    allowed_models: dict[str, list[str]] = Field(default_factory=dict)
    # Web-search grounding pool; defaults to the union of ``allowed_models`` when empty.
    web_search_models: list[str] = Field(default_factory=list)
    # Legacy single grounding pin — ignored when ``web_search_models`` is set.
    grounding_model: str = ""
    openrouter: OlympusOpenRouterTierConfig = Field(default_factory=OlympusOpenRouterTierConfig)

    @model_validator(mode="after")
    def _migrate_legacy_models(self) -> OlympusTierConfig:
        if self.models and not self.allowed_models:
            object.__setattr__(
                self,
                "allowed_models",
                {cap: [mdl] for cap, mdl in self.models.items()},
            )
        return self


class OlympusModelsConfig(BaseModel):
    """Parsed ``olympus_models.yaml`` — centralized Atlas/Hermes model policy."""

    default_tier: str = "cheap"
    openrouter_defaults: OlympusOpenRouterTierConfig = Field(
        default_factory=OlympusOpenRouterTierConfig
    )
    tiers: dict[str, OlympusTierConfig] = Field(default_factory=dict)
    phase_capabilities: dict[str, str] = Field(default_factory=dict)
    phase_capability_prefixes: dict[str, str] = Field(default_factory=dict)


_EMPTY_MODEL_MODES = ModelModesConfig()
_model_modes_cache: tuple[float, ModelModesConfig] | None = None
_EMPTY_OLYMPUS_MODELS = OlympusModelsConfig()
_olympus_models_cache: tuple[float, OlympusModelsConfig] | None = None
_VALID_OLYMPUS_TIERS = frozenset({"cheap", "balanced", "quality"})
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


def _olympus_models_path() -> Path:
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    return Path(config_dir) / "olympus_models.yaml"


def _load_olympus_models() -> OlympusModelsConfig:
    """Load ``olympus_models.yaml`` (mtime-cached)."""
    global _olympus_models_cache
    path = _olympus_models_path()
    if not path.exists():
        return _EMPTY_OLYMPUS_MODELS
    try:
        mtime = path.stat().st_mtime
    except OSError as e:
        logger.warning("olympus_models load failed (stat): %s", e)
        return _EMPTY_OLYMPUS_MODELS
    if _olympus_models_cache is not None and _olympus_models_cache[0] == mtime:
        return _olympus_models_cache[1]
    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except _MODEL_MODES_LOAD_ERRORS as e:
        logger.warning("olympus_models load failed: %s", e)
        return _EMPTY_OLYMPUS_MODELS
    try:
        cfg = OlympusModelsConfig.model_validate(raw)
    except ValidationError as e:
        logger.warning("olympus_models validation failed: %s", e)
        return _EMPTY_OLYMPUS_MODELS
    _olympus_models_cache = (mtime, cfg)
    _warn_flagship_models_in_olympus_config(cfg)
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
            or entry.lower().startswith(("openai/gpt-4o-mini", "google/", "x-ai/"))
        ]
        return ",".join(kept) if kept else _BALANCED_ALLOWED_MODELS
    kept = [entry for entry in entries if not is_flagship_allowed_models_entry(entry)]
    return ",".join(kept) if kept else _OPEN_WEIGHT_ALLOWED_MODELS


def _effective_openrouter_config(
    tier_name: str,
    tier_cfg: OlympusTierConfig,
    olympus: OlympusModelsConfig,
) -> OlympusOpenRouterTierConfig:
    """Merge tier overrides with ``openrouter_defaults`` (defaults win on empty tier fields)."""
    defaults = olympus.openrouter_defaults
    tier_or = tier_cfg.openrouter
    allowed = tier_or.allowed_models.strip() or defaults.allowed_models
    tradeoff = (
        tier_or.cost_quality_tradeoff
        if tier_or.cost_quality_tradeoff is not None
        else defaults.cost_quality_tradeoff
    )
    return OlympusOpenRouterTierConfig(
        allowed_models=sanitize_allowed_models(allowed, tier=tier_name),
        cost_quality_tradeoff=tradeoff,
    )


def _warn_flagship_models_in_olympus_config(cfg: OlympusModelsConfig) -> None:
    """Log when olympus_models.yaml pools a frontier model on a restricted tier."""
    for tier_name, tier_cfg in cfg.tiers.items():
        if tier_name == "quality":
            continue
        for capability, pool in tier_cfg.allowed_models.items():
            for model in pool:
                if is_flagship_openrouter_model(model) and not tier_allows_phase_model(
                    model, tier_name
                ):
                    logger.warning(
                        "olympus_models tier=%s capability=%s pools disallowed model %r",
                        tier_name,
                        capability,
                        model,
                    )
    pool = sanitize_allowed_models(cfg.openrouter_defaults.allowed_models, tier="cheap")
    if pool != cfg.openrouter_defaults.allowed_models.strip():
        logger.debug(
            "olympus_models openrouter_defaults sanitized for cheap tier to %r",
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


def get_olympus_tier() -> str:
    """Active Olympus tier from ``OLYMPUS_MODEL_TIER`` or ``olympus_models.yaml`` default."""
    raw = os.environ.get("OLYMPUS_MODEL_TIER", "").strip().lower()
    if raw in _VALID_OLYMPUS_TIERS:
        return raw
    return _load_olympus_models().default_tier or "cheap"


def _capability_for_phase(phase_slug: str, cfg: OlympusModelsConfig) -> str | None:
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


def _tier_capability_pool(tier_cfg: OlympusTierConfig, capability: str) -> list[str]:
    pool = list(tier_cfg.allowed_models.get(capability) or [])
    if not pool:
        legacy = tier_cfg.models.get(capability)
        if legacy:
            pool = [legacy]
    return pool


def _tier_web_search_pool(tier_cfg: OlympusTierConfig) -> list[str]:
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


def _model_for_olympus_capability(capability: str, tier: str, phase_slug: str) -> str | None:
    if capability not in _VALID_CAPABILITIES:
        return None
    tier_cfg = _load_olympus_models().tiers.get(tier)
    if tier_cfg is None:
        return None
    pool = [
        m for m in _tier_capability_pool(tier_cfg, capability) if tier_allows_phase_model(m, tier)
    ]
    if not pool:
        return None
    return _pick_from_pool(pool, phase_slug)


def get_grounding_model(*, segment: str = "grounding") -> str | None:
    """Return an OpenRouter model for web-search grounding pre-passes."""
    tier_cfg = _load_olympus_models().tiers.get(get_olympus_tier())
    if tier_cfg is None:
        return None
    pool = _tier_web_search_pool(tier_cfg)
    if not pool:
        return None
    return _pick_from_pool(pool, segment)


def apply_olympus_openrouter_env(*, force: bool = False) -> str:
    """Apply OpenRouter cost knobs from the active Olympus tier. Returns tier name.

    Sets ``OPENROUTER_ALLOWED_MODELS`` and ``OPENROUTER_COST_QUALITY_TRADEOFF`` when
    unset (or when *force*). Called at chain startup so CI picks up tier policy
    without duplicating values in ``olympus-pipeline.yml``.
    """
    tier = get_olympus_tier()
    tier_cfg = _load_olympus_models().tiers.get(tier)
    if tier_cfg is None:
        logger.warning("olympus tier %r not found in olympus_models.yaml", tier)
        return tier
    olympus = _load_olympus_models()
    or_cfg = _effective_openrouter_config(tier, tier_cfg, olympus)
    if or_cfg.allowed_models and (
        force or not os.environ.get("OPENROUTER_ALLOWED_MODELS", "").strip()
    ):
        os.environ["OPENROUTER_ALLOWED_MODELS"] = or_cfg.allowed_models
    if or_cfg.cost_quality_tradeoff is not None and (
        force or not os.environ.get("OPENROUTER_COST_QUALITY_TRADEOFF", "").strip()
    ):
        os.environ["OPENROUTER_COST_QUALITY_TRADEOFF"] = str(or_cfg.cost_quality_tradeoff)
    logger.info(
        "Olympus model tier=%s openrouter_pool=%s tradeoff=%s",
        tier,
        os.environ.get("OPENROUTER_ALLOWED_MODELS", ""),
        os.environ.get("OPENROUTER_COST_QUALITY_TRADEOFF", ""),
    )
    return tier


def _apply_byok_model_override(resolved: str) -> str:
    """When BYOK + X-BYOK-Model is active for a non-OpenAI provider, use the user's model."""
    byok = get_byok_override()
    if not byok:
        return resolved
    _key, provider = byok
    user_model = get_byok_model_override()
    if not user_model:
        return resolved
    if provider == "openai":
        return user_model or resolved
    if provider == "openrouter":
        slug = (
            user_model[len("openrouter/") :] if user_model.startswith("openrouter/") else user_model
        )
        return f"openrouter/{slug}"
    if provider == "gemini":
        slug = user_model[len("gemini/") :] if user_model.startswith("gemini/") else user_model
        return f"gemini/{slug}"
    if provider == "anthropic":
        slug = (
            user_model[len("anthropic/") :] if user_model.startswith("anthropic/") else user_model
        )
        return f"anthropic/{slug}"
    if provider == "xai":
        slug = user_model[len("xai/") :] if user_model.startswith("xai/") else user_model
        return f"xai/{slug}"
    return resolved


def effective_llm_settings() -> dict[str, object]:
    """Return effective LLM settings for CLI / diagnostics (never includes secret values).

    Keys: ``provider``, ``model``, ``llm_mode``, ``api_key_env``, ``api_key_present``,
    ``source`` (``agents.llm`` | ``env`` | ``model_modes`` | ``default``).
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
    elif mode == "free":
        raise ValueError(_FREE_MODE_MODEL_REQUIRED)
    else:
        data = _load_model_modes()
        if data.default_model:
            resolved = str(data.default_model)
            source = "model_modes.default_model"
        else:
            # ``free`` is policy-only — never read a product slug from defaults.free.
            resolved = data.defaults.get(mode) or data.defaults.get("test") or "gpt-4o-mini"
            source = "model_modes" if data.defaults else "default"
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


def get_model_for_mode() -> str:
    """Return the fallback model for phases without a phase_models entry.

    Resolution order:
    1. Explicit ``agents.llm`` / ``DIGI_LLM_PROVIDER``+``DIGI_LLM_MODEL`` — operator pin.
    2. For ``llm_mode: free`` without an explicit pin → :class:`ValueError` (policy only;
       no shared product slug in ``model_modes.yaml``).
    3. ``default_model`` in model_modes.yaml — optional explicit fallback (non-free).
    4. ``defaults[llm_mode]`` for ``test`` / ``medium`` / ``best`` — mode-keyed fallback.
    5. ``"gpt-4o-mini"`` — hard last resort (non-free modes only).

    OpenRouter paid/Olympus auto-override is **not** applied here. Olympus/Atlas
    phases use :func:`get_model_for_phase`. Having ``OPENROUTER_API_KEY`` set alone
    must not swap a free/local digithings install onto paid Olympus models.
    ``llm_mode: free`` refuses non-``:free`` (non-Ollama) model ids.
    """
    mode = _get_llm_mode()
    provider, model, _api_key_env = _explicit_llm_config()
    resolved = _resolve_explicit_model(provider, model)
    if resolved is None:
        if mode == "free":
            raise ValueError(_FREE_MODE_MODEL_REQUIRED)
        data = _load_model_modes()
        if data.default_model:
            resolved = str(data.default_model)
        else:
            # Never consult defaults.free — free is access policy, not a model pin.
            resolved = data.defaults.get(mode) or data.defaults.get("test") or "gpt-4o-mini"
    resolved = _refuse_paid_in_free_mode(resolved, mode)
    return _apply_byok_model_override(resolved)


def get_model_for_phase(phase_slug: str) -> str | None:
    """Return the configured model for a phase slug (exact or prefix match), or None.

    Resolution order:
    1. ``model_modes.yaml`` ``phase_models`` — explicit per-phase override (frontier escape hatch).
    2. ``olympus_models.yaml`` — capability tier × ``OLYMPUS_MODEL_TIER``.
    3. ``None`` → caller uses :func:`get_model_for_mode`.

    Prefix match in ``phase_models``: a key ending in '-' (e.g. 'analyst-') matches any
    slug that starts with that prefix (e.g. 'analyst-AAPL').
    """
    data = _load_model_modes()
    phase_models = data.phase_models
    tier = get_olympus_tier()
    override = _phase_models_override(phase_slug, phase_models)
    if override is not None:
        if tier_allows_phase_model(override, tier):
            return _apply_byok_model_override(override)
        logger.warning(
            "Rejecting phase_models override for %s (%r) on tier %s; "
            "using olympus_models.yaml instead",
            phase_slug,
            override,
            tier,
        )

    olympus = _load_olympus_models()
    capability = _capability_for_phase(phase_slug, olympus)
    if capability is not None:
        return _apply_byok_model_override(
            _model_for_olympus_capability(capability, tier, phase_slug)
        )
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
      silent Ollama fallback rather than digillm's hard error.
    - ``ollama-cloud/<model>`` → strip the prefix (Ollama Cloud expects bare
      names); ``resolve_effective_model`` is intentionally NOT applied so a mode
      default can't override an explicit cloud model.
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
    return resolve_effective_model(request_model)
