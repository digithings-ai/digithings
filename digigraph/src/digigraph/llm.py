"""LLM client: OpenAI-compatible API (Ollama, LiteLLM, OpenAI). Phase 1+."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from openai import OpenAI

# Optional: override for Ollama / LiteLLM. Default OpenAI if unset.
_BASE_URL = os.environ.get("OPENAI_API_BASE")
_API_KEY = os.environ.get("OPENAI_API_KEY", "not-set")

# test = minimal tokens (free tier); medium = balanced; best = largest.
_DIGI_LLM_MODE = os.environ.get("DIGI_LLM_MODE", "test").lower().strip()


def _load_model_modes() -> dict[str, Any]:
    """Load config/model_modes.yaml. Returns {} if missing."""
    config_dir = os.environ.get("DIGI_CONFIG_PATH", "config")
    path = Path(config_dir) / "model_modes.yaml"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_model_for_mode() -> str:
    """
    Return the LiteLLM model name for the current DIGI_LLM_MODE (test|medium|best).
    Reads config/model_modes.yaml defaults; falls back to gpt-4o-mini.
    """
    data = _load_model_modes()
    defaults = data.get("defaults") or {}
    model = defaults.get(_DIGI_LLM_MODE) or defaults.get("test")
    if model:
        return model
    return "gpt-4o-mini"


def get_client() -> OpenAI:
    """Build OpenAI client; uses OPENAI_API_BASE for Ollama/LiteLLM."""
    kwargs: dict[str, Any] = {"api_key": _API_KEY}
    if _BASE_URL:
        kwargs["base_url"] = _BASE_URL.rstrip("/")
    return OpenAI(**kwargs)


def chat_completion(
    model: str,
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.2,
) -> str:
    """
    Single chat completion; returns content of the first choice.
    Model selection (first non-empty): OLLAMA_MODEL env, then get_model_for_mode()
    from DIGI_LLM_MODE, then the model parameter.
    """
    client = get_client()
    effective_model = os.environ.get("OLLAMA_MODEL") or get_model_for_mode() or model
    r = client.chat.completions.create(
        model=effective_model,
        messages=messages,
        temperature=temperature,
    )
    if not r.choices:
        return ""
    return (r.choices[0].message.content or "").strip()
