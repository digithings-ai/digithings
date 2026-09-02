"""OpenRouter web search: native for Olympus grounding; Exa toolkit for non-native (#650 / #2567)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from digillm import openrouter_web_search


def _chat_resp(text: str):
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


@pytest.mark.unit
def test_openrouter_web_search_returns_text_and_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("digillm.client.completion") as completion:
        completion.return_value = _chat_resp("CPI rose 0.6% MoM.[[1]](https://bls.gov/cpi/)")
        result = openrouter_web_search(
            "openrouter/deepseek/deepseek-chat",
            "latest US CPI",
            allowed_domains=["bls.gov"],
            max_results=5,
        )
    assert result is not None
    text, sources = result
    assert "CPI rose" in text
    assert "https://bls.gov/cpi/" in sources
    kwargs = completion.call_args[1]
    assert kwargs["tools"][0]["type"] == "openrouter:web_search"
    assert kwargs["tools"][0]["parameters"]["engine"] == "exa"
    assert kwargs["tools"][0]["parameters"]["allowed_domains"] == ["bls.gov"]
    assert kwargs["usage_kind"] == "web_search"


@pytest.mark.unit
def test_openrouter_web_search_none_for_non_openrouter() -> None:
    assert openrouter_web_search("gpt-4o-mini", "anything") is None


@pytest.mark.unit
def test_openrouter_web_search_none_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert openrouter_web_search("openrouter/deepseek/deepseek-chat", "q") is None


@pytest.mark.unit
def test_openrouter_web_search_perplexity_uses_native_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Perplexity uses plain completion (native search), not openrouter:web_search server tool."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("digillm.client.completion") as completion:
        completion.return_value = _chat_resp("headline [[1]](https://example.com)")
        openrouter_web_search("openrouter/perplexity/sonar", "latest CPI")
    kwargs = completion.call_args[1]
    assert "tools" not in kwargs
    assert kwargs["usage_kind"] == "web_search"


@pytest.mark.unit
def test_openrouter_web_search_online_suffix_uses_native_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``:online`` models use built-in search — Exa toolkit branch must stay unused (#2567)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("digillm.client.completion") as completion:
        completion.return_value = _chat_resp("ok [[1]](https://example.com)")
        openrouter_web_search("openrouter/openai/gpt-4o:online", "latest CPI")
    kwargs = completion.call_args[1]
    assert "tools" not in kwargs


@pytest.mark.unit
def test_openrouter_web_search_unprefixed_online_via_house_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """House grounding pins are unprefixed ``:online`` slugs resolved through LiteLLM (#3414)."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    with patch("digillm.client.completion") as completion:
        completion.return_value = _chat_resp("ok [[1]](https://example.com)")
        result = openrouter_web_search("deepseek/deepseek-v4-flash:online", "latest CPI")
    assert result is not None
    kwargs = completion.call_args[1]
    assert "tools" not in kwargs
    assert kwargs["usage_kind"] == "web_search"


@pytest.mark.unit
def test_openrouter_web_search_unprefixed_perplexity_via_house_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:4000/v1")
    with patch("digillm.client.completion") as completion:
        completion.return_value = _chat_resp("headline [[1]](https://example.com)")
        openrouter_web_search("perplexity/sonar", "latest CPI")
    kwargs = completion.call_args[1]
    assert "tools" not in kwargs


@pytest.mark.unit
def test_openrouter_web_search_unprefixed_without_proxy_or_key_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert openrouter_web_search("perplexity/sonar", "q") is None


@pytest.mark.unit
def test_openrouter_web_search_fails_soft_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("digillm.client.completion", side_effect=RuntimeError("boom")):
        assert openrouter_web_search("openrouter/deepseek/deepseek-chat", "q") is None
