"""House LLM pins must resolve on the LiteLLM ``model_list`` (#3414 / #3413)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG = REPO_ROOT / "config"


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


def _olympus_house_slugs() -> set[str]:
    olympus = yaml.safe_load((CONFIG / "olympus_models.yaml").read_text(encoding="utf-8"))
    slugs: set[str] = set()
    for tier in (olympus.get("tiers") or {}).values():
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
    missing = sorted(_olympus_house_slugs() - names)
    assert not missing, f"house pins missing from config/litellm.yaml model_list: {missing}"


def test_litellm_yaml_allows_byok_clientside_credentials() -> None:
    """BYOK keys pass through LiteLLM via extra_body api_key / api_base."""
    data = yaml.safe_load((CONFIG / "litellm.yaml").read_text(encoding="utf-8"))
    model_list = data["model_list"]
    missing: list[str] = []
    for entry in model_list:
        name = entry["model_name"]
        params = entry["litellm_params"]
        allowed = params.get("configurable_clientside_auth_params") or []
        if not {"api_key", "api_base"} <= set(allowed):
            missing.append(name)
    assert not missing, (
        "config/litellm.yaml models missing configurable_clientside_auth_params "
        f"[api_key, api_base]: {missing}"
    )


def test_house_pins_are_unprefixed() -> None:
    """House pins must not use leftover vendor spellings ``openrouter/`` / ``gemini/`` / ``xai/``.

    ``anthropic/`` and ``openai/`` are OpenRouter org slugs and are expected.
    """
    for slug in _olympus_house_slugs():
        assert not slug.startswith("openrouter/"), slug
        assert not slug.startswith("gemini/"), slug
        assert not slug.startswith("xai/"), slug


def test_default_litellm_yaml_does_not_enable_omniroute() -> None:
    names = _model_names(CONFIG / "litellm.yaml")
    leaked = sorted(n for n in names if n.startswith("omniroute/"))
    assert not leaked, f"OmniRoute must stay off by default; found {leaked}"


def test_omniroute_overlay_parses_and_is_optional() -> None:
    overlay = CONFIG / "litellm.omniroute.yaml"
    assert overlay.is_file()
    names = _model_names(overlay)
    assert any(n.startswith("omniroute/") for n in names)
    for name in names:
        assert name.startswith("omniroute/"), name
