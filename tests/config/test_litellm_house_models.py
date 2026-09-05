"""House LLM pins must resolve on the LiteLLM ``model_list`` (#3414 / #3413 / #3605)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config"
LITELLM_YAMLS = (
    CONFIG / "litellm.yaml",
    CONFIG / "litellm.omniroute.yaml",
    CONFIG / "litellm.dev.yaml",
)
EVIL_BASE = "https://evil.example/v1"


def _model_names(path: Path) -> set[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must parse as a mapping"
    model_list = data.get("model_list")
    assert isinstance(model_list, list) and model_list, f"{path} missing model_list"
    names: set[str] = set()
    for entry in model_list:
        assert isinstance(entry, dict), f"model_list entry in {path} is not a mapping"
        name = entry.get("model_name")
        assert isinstance(name, str) and name.strip(), f"missing model_name in {path}"
        names.add(name)
        params = entry.get("litellm_params")
        assert isinstance(params, dict) and params.get("model"), (
            f"{name} in {path} missing litellm_params.model"
        )
    return names


def _digiquant_house_slugs() -> set[str]:
    digiquant = yaml.safe_load((CONFIG / "digiquant_models.yaml").read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for tier in (digiquant.get("tiers") or {}).values():
        for pool in (tier.get("allowed_models") or {}).values():
            slugs.update(str(m) for m in (pool or []))
        slugs.update(str(m) for m in (tier.get("web_search_models") or []))
    modes = yaml.safe_load((CONFIG / "model_modes.yaml").read_text(encoding="utf-8"))
    slugs.update(str(m) for m in (modes.get("phase_models") or {}).values())
    dogfood = yaml.safe_load((CONFIG / "dogfood-digiproject.yaml").read_text(encoding="utf-8"))
    slugs.add(str(dogfood["agents"]["llm"]["model"]))
    from digiskills.synthesize import DEFAULT_SYNTHESIS_MODEL

    slugs.add(DEFAULT_SYNTHESIS_MODEL)
    return {s.strip() for s in slugs if s and str(s).strip()}


def test_litellm_yaml_parses_and_lists_house_slugs() -> None:
    names = _model_names(CONFIG / "litellm.yaml")
    missing = sorted(_digiquant_house_slugs() - names)
    assert not missing, f"house pins missing from config/litellm.yaml model_list: {missing}"


def _load_byok_catalog() -> list[dict[str, Any]]:
    raw = json.loads((CONFIG / "byok-providers.json").read_text(encoding="utf-8"))
    assert isinstance(raw, list) and raw
    return raw


def _model_entries(path: Path) -> dict[str, dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    entries: dict[str, dict[str, Any]] = {}
    for entry in data.get("model_list") or []:
        assert isinstance(entry, dict)
        name = entry["model_name"]
        params = entry["litellm_params"]
        assert isinstance(params, dict)
        entries[name] = params
    return entries


def _api_base_patterns(params: dict[str, Any]) -> list[str]:
    allowed = params.get("configurable_clientside_auth_params") or []
    assert isinstance(allowed, list)
    patterns: list[str] = []
    for item in allowed:
        if item == "api_base":
            raise AssertionError(
                "bare configurable_clientside_auth_params api_base is forbidden; "
                "use LiteLLM's regex form {api_base: ^https://...$}"
            )
        if isinstance(item, dict) and "api_base" in item:
            pattern = item["api_base"]
            assert isinstance(pattern, str) and pattern.startswith("^") and pattern.endswith("$"), (
                f"api_base regex must be a full-match pattern, got {pattern!r}"
            )
            patterns.append(pattern)
    return patterns


def _matches(pattern: str, url: str) -> bool:
    return re.match(pattern, url) is not None or re.match(pattern, url.rstrip("/")) is not None


def test_no_litellm_yaml_allows_arbitrary_api_base() -> None:
    """Defense in depth: unrestricted api_base passthrough is never allowed (#3605)."""
    for path in LITELLM_YAMLS:
        for name, params in _model_entries(path).items():
            patterns = _api_base_patterns(params)
            for pattern in patterns:
                assert not _matches(pattern, EVIL_BASE), f"{path.name} {name} allows {EVIL_BASE}"


def test_litellm_yaml_allows_byok_clientside_credentials() -> None:
    """BYOK catalog models accept api_key plus a host regex, not a bare api_base."""
    entries = _model_entries(CONFIG / "litellm.yaml")
    missing_key: list[str] = []
    missing_regex: list[str] = []
    for provider in _load_byok_catalog():
        for model in provider.get("fallbackModels") or []:
            params = entries.get(model)
            if params is None:
                continue
            allowed = params.get("configurable_clientside_auth_params") or []
            if "api_key" not in allowed:
                missing_key.append(model)
            if not _api_base_patterns(params):
                missing_regex.append(model)
    assert not missing_key, f"BYOK models missing api_key passthrough: {missing_key}"
    assert not missing_regex, f"BYOK models missing api_base regex: {missing_regex}"


def test_every_advertised_byok_preset_is_a_litellm_model_group() -> None:
    """Every catalog fallbackModel must exist as a LiteLLM model_name (#3605)."""
    names = _model_names(CONFIG / "litellm.yaml")
    missing: list[str] = []
    for provider in _load_byok_catalog():
        for model in provider.get("fallbackModels") or []:
            assert isinstance(model, str) and model.strip(), provider
            if model not in names:
                missing.append(f"{provider['id']}:{model}")
    assert not missing, (
        "advertised BYOK presets have no matching LiteLLM model group: " + ", ".join(missing)
    )


def test_advertised_byok_api_base_regex_is_pinned_to_catalog_host() -> None:
    """Each advertised preset may pass api_base only to its catalog provider host."""
    entries = _model_entries(CONFIG / "litellm.yaml")
    catalog = _load_byok_catalog()
    for provider in catalog:
        host = str(provider["baseUrl"])
        other_hosts = [
            str(other["baseUrl"]).rstrip("/") for other in catalog if other["id"] != provider["id"]
        ]
        for model in provider.get("fallbackModels") or []:
            patterns = _api_base_patterns(entries[model])
            assert patterns, model
            assert any(_matches(p, host) for p in patterns), (
                f"{model} regex {patterns} does not match catalog host {host}"
            )
            for other in other_hosts:
                assert not any(_matches(p, other) for p in patterns), (
                    f"{model} regex {patterns} also matches other catalog host {other}"
                )
            parsed = urlparse(host)
            assert parsed.hostname
            # Hostname-only match is not enough — path must stay catalog-exact.
            assert not any(_matches(p, f"https://{parsed.hostname}/steal") for p in patterns)


def test_house_pins_are_unprefixed() -> None:
    """House pins must not use leftover vendor spellings ``openrouter/`` / ``gemini/`` / ``xai/``.

    ``anthropic/`` and ``openai/`` are OpenRouter org slugs and are expected.
    """
    for slug in _digiquant_house_slugs():
        assert not slug.startswith("openrouter/"), slug
        assert not slug.startswith("gemini/"), slug
        assert not slug.startswith("xai/"), slug


def test_default_litellm_yaml_does_not_enable_omniroute() -> None:
    names = _model_names(CONFIG / "litellm.yaml")
    leaked = sorted(n for n in names if n.startswith("omniroute/"))
    assert not leaked, f"OmniRoute must stay off by default; found {leaked}"


def test_digillm_catalog_api_bases_match_byok_providers_json() -> None:
    from digillm.client import _BYOK_CATALOG_API_BASES

    catalog = {str(entry["baseUrl"]).rstrip("/") for entry in _load_byok_catalog()}
    assert catalog == set(_BYOK_CATALOG_API_BASES)


def test_omniroute_overlay_parses_and_is_optional() -> None:
    overlay = CONFIG / "litellm.omniroute.yaml"
    assert overlay.is_file()
    names = _model_names(overlay)
    assert any(n.startswith("omniroute/") for n in names)
    for name in names:
        assert name.startswith("omniroute/"), name


def test_default_litellm_yaml_does_not_enable_cheaperinference() -> None:
    """CI overlay must stay opt-in — default litellm.yaml keeps OpenRouter upstreams."""
    data = yaml.safe_load((CONFIG / "litellm.yaml").read_text(encoding="utf-8"))
    leaked: list[str] = []
    for entry in data["model_list"]:
        params = entry.get("litellm_params") or {}
        base = str(params.get("api_base") or "")
        key = str(params.get("api_key") or "")
        if "CHEAPERINFERENCE" in base or "CHEAPERINFERENCE" in key:
            leaked.append(entry["model_name"])
        if "cheaperinference.com" in base.lower():
            leaked.append(entry["model_name"])
    assert not leaked, f"Cheaper Inference must stay off by default; found {leaked}"


def test_cheaperinference_overlay_parses_and_maps_house_slugs() -> None:
    overlay = CONFIG / "litellm.cheaperinference.yaml"
    assert overlay.is_file()
    names = _model_names(overlay)
    expected = {
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-pro",
        "google/gemini-3.7-flash",
        "openai/gpt-5.6-luna",
        "openai/gpt-5.6-sol",
    }
    missing = sorted(expected - names)
    assert not missing, f"CI overlay missing house slugs: {missing}"
    # Must not claim OpenRouter-only pins
    forbidden = {
        "meta-llama/llama-4-maverick",
        "perplexity/sonar",
        "anthropic/claude-sonnet-5",
        "x-ai/grok-4.3",
        "x-ai/grok-4.6",
    }
    assert not (names & forbidden), names & forbidden
    data = yaml.safe_load(overlay.read_text(encoding="utf-8"))
    for entry in data["model_list"]:
        params = entry["litellm_params"]
        assert params.get("api_key") == "os.environ/CHEAPERINFERENCE_API_KEY", entry["model_name"]
        assert params.get("api_base") == "os.environ/CHEAPERINFERENCE_API_BASE", entry["model_name"]
        assert str(params.get("model", "")).startswith("openai/"), entry["model_name"]


def test_merge_litellm_cheaperinference_replaces_mapped_keeps_openrouter() -> None:
    from scripts.merge_litellm_cheaperinference import merge

    merged = merge(CONFIG / "litellm.yaml", CONFIG / "litellm.cheaperinference.yaml")
    by_name = {e["model_name"]: e for e in merged["model_list"] if isinstance(e, dict)}
    flash = by_name["deepseek/deepseek-v4-flash"]["litellm_params"]
    assert flash["api_key"] == "os.environ/CHEAPERINFERENCE_API_KEY"
    assert flash["model"] == "openai/deepseek-v4-flash"
    sonar = by_name["perplexity/sonar"]["litellm_params"]
    assert sonar["api_key"] == "os.environ/OPENROUTER_API_KEY"
    mav = by_name["meta-llama/llama-4-maverick"]["litellm_params"]
    assert mav["api_key"] == "os.environ/OPENROUTER_API_KEY"
