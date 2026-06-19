"""DigiGraph model configuration & request-model routing.

Relocated from the former monolithic ``digigraph.llm`` (decommissioned in #632
P2). Owns everything about *which model string* a request should use:

- ``model_modes.yaml`` loading + the ``test`` / ``medium`` / ``best`` mode
  resolution (:func:`get_model_for_mode`, :func:`get_model_for_phase`).
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

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
_OPEN_WEIGHT_ALLOWED_MODELS = "deepseek/*,qwen/*,meta-llama/*,mistralai/*,nvidia/*,google/gemma*"
_DEFAULT_COST_QUALITY_TRADEOFF = 10


# test = minimal tokens (free tier); medium = balanced; best = largest.
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

    models: dict[str, str] = Field(default_factory=dict)
    # xAI model for live_search grounding (legacy). Olympus uses openrouter/* only.
    grounding_model: str = "openrouter/deepseek/deepseek-chat"
    openrouter: OlympusOpenRouterTierConfig = Field(default_factory=OlympusOpenRouterTierConfig)


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


def sanitize_allowed_models(allowed_models: str) -> str:
    """Drop frontier entries from a comma-separated OpenRouter allowed_models string."""
    kept = [
        entry
        for entry in (part.strip() for part in allowed_models.split(","))
        if entry and not is_flagship_allowed_models_entry(entry)
    ]
    return ",".join(kept) if kept else _OPEN_WEIGHT_ALLOWED_MODELS


def _effective_openrouter_config(
    tier_cfg: OlympusTierConfig, olympus: OlympusModelsConfig
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
        allowed_models=sanitize_allowed_models(allowed),
        cost_quality_tradeoff=tradeoff,
    )


def _warn_flagship_models_in_olympus_config(cfg: OlympusModelsConfig) -> None:
    """Log when olympus_models.yaml pins or pools a frontier model."""
    for tier_name, tier_cfg in cfg.tiers.items():
        for capability, model in tier_cfg.models.items():
            if is_flagship_openrouter_model(model):
                logger.warning(
                    "olympus_models tier=%s capability=%s pins flagship model %r",
                    tier_name,
                    capability,
                    model,
                )
        if tier_cfg.grounding_model and is_flagship_openrouter_model(tier_cfg.grounding_model):
            logger.warning(
                "olympus_models tier=%s grounding_model pins flagship %r",
                tier_name,
                tier_cfg.grounding_model,
            )
    pool = sanitize_allowed_models(cfg.openrouter_defaults.allowed_models)
    if pool != cfg.openrouter_defaults.allowed_models.strip():
        logger.warning(
            "olympus_models openrouter_defaults.allowed_models contained frontier entries; "
            "sanitized to %r",
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


def _model_for_olympus_capability(capability: str, tier: str) -> str | None:
    tier_cfg = _load_olympus_models().tiers.get(tier)
    if tier_cfg is None:
        return None
    model = tier_cfg.models.get(capability)
    if model and capability in _VALID_CAPABILITIES:
        return model
    return None


def get_grounding_model() -> str | None:
    """Return the OpenRouter model for ``openrouter:web_search`` grounding pre-passes."""
    tier_cfg = _load_olympus_models().tiers.get(get_olympus_tier())
    if tier_cfg is None:
        return None
    return tier_cfg.grounding_model or None


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
    or_cfg = _effective_openrouter_config(tier_cfg, olympus)
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


def get_model_for_mode() -> str:
    """Return the fallback model for phases without a phase_models entry.

    Atlas/Hermes phases all have explicit phase_models entries, so this is
    reached only by non-Atlas digigraph agent runners that don't supply a
    phase_slug. Resolution order:
    1. ``default_model`` in model_modes.yaml — optional explicit fallback.
    2. ``defaults[DIGI_LLM_MODE]`` — legacy mode-keyed fallback.
    3. ``"gpt-4o-mini"`` — hard last resort.
    """
    data = _load_model_modes()
    if data.default_model:
        return str(data.default_model)
    mode = _get_llm_mode()
    model = data.defaults.get(mode) or data.defaults.get("test")
    if model:
        return model
    return "gpt-4o-mini"


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
    override = _phase_models_override(phase_slug, phase_models)
    if override is not None:
        if is_flagship_openrouter_model(override):
            logger.warning(
                "Rejecting flagship phase_models override for %s (%r); "
                "using olympus_models.yaml instead",
                phase_slug,
                override,
            )
        else:
            return override

    olympus = _load_olympus_models()
    capability = _capability_for_phase(phase_slug, olympus)
    if capability is not None:
        return _model_for_olympus_capability(capability, get_olympus_tier())
    return None


# External providers digigraph routes by a "provider/" prefix. Only the API-key
# env var matters here: digillm owns the actual client/base_url. When the key is
# set, the prefixed model is handed to digillm unchanged (it routes + strips the
# prefix); when missing, we fall back to the Ollama mode model — preserving the
# legacy ``chat_completion`` behavior instead of digillm's hard RuntimeError.
_EXTERNAL_PROVIDERS: dict[str, dict[str, str]] = {
    "gemini": {"api_key_env": "GEMINI_API_KEY"},
    "xai": {"api_key_env": "XAI_API_KEY"},
    "openrouter": {"api_key_env": "OPENROUTER_API_KEY"},
}


def _parse_provider_prefix(model: str) -> tuple[str | None, str]:
    """Split 'provider/model_id' into (provider, model_id) for known external providers.

    Returns (None, model) for Ollama-native model strings (including 'ollama-cloud/…').
    """
    if "/" in model:
        provider, _, model_id = model.partition("/")
        if provider in _EXTERNAL_PROVIDERS:
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
        api_key_env = _EXTERNAL_PROVIDERS[provider]["api_key_env"]
        if os.environ.get(api_key_env, "").strip():
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
