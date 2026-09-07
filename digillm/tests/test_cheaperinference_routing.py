"""Cheaper Inference house routing (CLI/GHA rewrite + catalog misses → OpenRouter)."""

from __future__ import annotations

from typing import Any  # score:allow untyped any

# Justification: fake OpenAI kwargs + captured call dicts over untyped client boundary.
from unittest.mock import MagicMock, patch

import pytest

import digillm
import digillm.client as client_mod


@pytest.fixture(autouse=True)
def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    client_mod.clear_caches()
    yield
    client_mod.clear_caches()


def test_ci_base_rewrites_mapped_house_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    assert client_mod._effective_model_id("deepseek/deepseek-v4-flash") == "deepseek-v4-flash"
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash")
    assert made["base_url"] == "https://api.cheaperinference.com/v1"
    assert made["api_key"] == "ci_live_test"


def test_ci_base_raises_on_sonar_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI-catalog miss (sonar) raises when fallback is not allowed (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("perplexity/sonar")


def test_ci_base_routes_sonar_to_openrouter_with_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-catalog miss (sonar) falls back to OpenRouter when override is set (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", "1")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("perplexity/sonar")
    assert made["base_url"] == "https://openrouter.ai/api/v1"
    assert made["api_key"] == "sk-or-test"
    assert client_mod._effective_model_id("perplexity/sonar") == "perplexity/sonar"


def test_ci_base_raises_on_online_without_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI-catalog miss (:online) raises when fallback is not allowed (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash:online")


def test_ci_base_keeps_online_on_openrouter_with_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-catalog miss (:online) falls back to OpenRouter when override is set (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", "1")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash:online")
    assert made["base_url"] == "https://openrouter.ai/api/v1"
    assert (
        client_mod.cheaperinference_bare_id_for_house_slug("deepseek/deepseek-v4-flash:online")
        is None
    )


def test_anthropic_not_mapped_to_ci() -> None:
    assert client_mod.cheaperinference_bare_id_for_house_slug("anthropic/claude-sonnet-5") is None


def test_house_preferred_defaults_on_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DIGI_HOUSE_UPSTREAM", raising=False)
    monkeypatch.delenv("CHEAPERINFERENCE_HOUSE", raising=False)
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", "ci_live_test")
    assert client_mod.cheaperinference_house_preferred() is True


def test_house_preferred_force_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", "ci_live_test")
    monkeypatch.setenv("DIGI_HOUSE_UPSTREAM", "openrouter")
    assert client_mod.cheaperinference_house_preferred() is False


def test_house_preferred_false_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHEAPERINFERENCE_API_KEY", raising=False)
    monkeypatch.setenv("DIGI_HOUSE_UPSTREAM", "cheaperinference")
    assert client_mod.cheaperinference_house_preferred() is False


# ── Fail-closed behavior (#3660) ──────────────────────────────────────────


def test_house_openrouter_fallback_disallowed_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI-catalog miss raises by default — no quiet OpenRouter fallback (#3660)."""
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    assert client_mod.house_openrouter_fallback_allowed() is False


def test_house_openrouter_fallback_allowed_when_override_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", "1")
    assert client_mod.house_openrouter_fallback_allowed() is True


def test_house_openrouter_fallback_allowed_true_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    for val in ("true", "yes", "on", "TRUE", "Yes"):
        monkeypatch.setenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", val)
        assert client_mod.house_openrouter_fallback_allowed() is True


def test_require_openrouter_fallback_allowed_raises_when_disallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-catalog miss (sonar) raises RuntimeError when fallback is not allowed."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        client_mod._require_openrouter_fallback_allowed("perplexity/sonar")


def test_require_openrouter_fallback_allowed_warns_when_override_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CI-catalog miss with fallback override logs a warning, does not raise."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.setenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", "1")
    # Should not raise
    client_mod._require_openrouter_fallback_allowed("perplexity/sonar")


def test_ci_catalog_miss_raises_on_get_client_for_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_client_for_model raises for unmapped house slug when CI is upstream (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    # meta-llama/* is not on CI catalog
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("meta-llama/llama-4-maverick")


def test_ci_catalog_miss_raises_on_effective_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_effective_model_id raises for unmapped house slug when CI is upstream (#3660)."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    # :online variants are not on CI catalog
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        client_mod._effective_model_id("deepseek/deepseek-v4-flash:online")


def test_mapped_house_slug_succeeds_on_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mapped house slug returns get_client() on CI base without raising."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.delenv("DIGI_HOUSE_ALLOW_OPENROUTER_FALLBACK", raising=False)
    # Should not raise — gemini-3.1-flash-lite is mapped
    client = digillm.get_client_for_model("google/gemini-3.1-flash-lite")
    assert client is not None


def test_gemini_3_1_flash_lite_mapped_to_ci() -> None:
    """gemini-3.1-flash-lite is on the CI catalog for web_search_models synthesis."""
    assert (
        client_mod.cheaperinference_bare_id_for_house_slug("google/gemini-3.1-flash-lite")
        == "gemini-3.1-flash-lite"
    )
