"""OpenRouter openrouter:web_search server tool (Olympus grounding, #650)."""

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
def test_openrouter_web_search_skips_require_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    captured: dict = {}

    def _capture_create(_client, **kwargs):
        captured.update(kwargs)
        return _chat_resp("headline [[1]](https://example.com)")

    with patch("digillm.client._create_with_retry", side_effect=_capture_create):
        openrouter_web_search("openrouter/perplexity/sonar", "latest CPI")
    extra = captured.get("extra_body") or {}
    assert "require_parameters" not in (extra.get("provider") or {})


@pytest.mark.unit
def test_openrouter_web_search_fails_soft_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    with patch("digillm.client.completion", side_effect=RuntimeError("boom")):
        assert openrouter_web_search("openrouter/deepseek/deepseek-chat", "q") is None
