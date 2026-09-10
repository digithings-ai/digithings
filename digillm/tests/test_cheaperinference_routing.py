"""Cheaper Inference house routing (CLI/GHA rewrite + fail-fast catalog misses)."""

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


def test_ci_base_raises_on_sonar(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI-catalog miss (sonar) always raises — no OpenRouter fallback."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("perplexity/sonar")


def test_ci_base_raises_on_online(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI-catalog miss (:online) always raises — no OpenRouter fallback."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash:online")
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


def test_ci_key_beats_openrouter_base_for_mapped_house_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """House slugs hit CI when keyed — not OpenRouter just because both keys exist."""
    monkeypatch.delenv("DIGI_HOUSE_UPSTREAM", raising=False)
    monkeypatch.delenv("CHEAPERINFERENCE_HOUSE", raising=False)
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-v1-test")
    monkeypatch.setenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
    assert client_mod._effective_model_id("deepseek/deepseek-v4-flash") == "deepseek-v4-flash"
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash")
    assert made["base_url"] == "https://api.cheaperinference.com/v1"
    assert made["api_key"] == "ci_live_test"


def test_litellm_proxy_keeps_house_slug_when_ci_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    """LiteLLM overlay is the house path — do not rewrite to a bare CI id."""
    monkeypatch.setenv("CHEAPERINFERENCE_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-litellm")
    assert (
        client_mod._effective_model_id("deepseek/deepseek-v4-flash") == "deepseek/deepseek-v4-flash"
    )


# ── Fail-fast behavior (no OpenRouter fallback) ───────────────────────────


def test_ci_catalog_miss_raises_on_get_client_for_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_client_for_model raises for unmapped house slug when CI is upstream."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    # meta-llama/* is not on CI catalog
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        digillm.get_client_for_model("meta-llama/llama-4-maverick")


def test_ci_catalog_miss_raises_on_effective_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_effective_model_id raises for unmapped house slug when CI is upstream."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    # :online variants are not on CI catalog
    with pytest.raises(RuntimeError, match="not on the Cheaper Inference catalog"):
        client_mod._effective_model_id("deepseek/deepseek-v4-flash:online")


def test_mapped_house_slug_succeeds_on_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mapped house slug returns get_client() on CI base without raising."""
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    # Should not raise — gemini-3.1-flash-lite is mapped
    client = digillm.get_client_for_model("google/gemini-3.1-flash-lite")
    assert client is not None


def test_gemini_3_1_flash_lite_mapped_to_ci() -> None:
    """gemini-3.1-flash-lite is on the CI catalog for web_search_models synthesis."""
    assert (
        client_mod.cheaperinference_bare_id_for_house_slug("google/gemini-3.1-flash-lite")
        == "gemini-3.1-flash-lite"
    )
