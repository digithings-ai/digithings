"""Cheaper Inference house routing (CLI/GHA rewrite + catalog misses → OpenRouter)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import digillm
import digillm.client as client_mod
import pytest


@pytest.fixture(autouse=True)
def _clear(monkeypatch: pytest.MonkeyPatch) -> None:
    client_mod.clear_caches()
    yield
    client_mod.clear_caches()


def test_ci_base_rewrites_mapped_house_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    assert (
        client_mod._effective_model_id("deepseek/deepseek-v4-flash") == "deepseek-v4-flash"
    )
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash")
    assert made["base_url"] == "https://api.cheaperinference.com/v1"
    assert made["api_key"] == "ci_live_test"


def test_ci_base_routes_sonar_to_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("perplexity/sonar")
    assert made["base_url"] == "https://openrouter.ai/api/v1"
    assert made["api_key"] == "sk-or-test"
    assert client_mod._effective_model_id("perplexity/sonar") == "perplexity/sonar"


def test_ci_base_keeps_online_on_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.cheaperinference.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "ci_live_test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("deepseek/deepseek-v4-flash:online")
    assert made["base_url"] == "https://openrouter.ai/api/v1"
    assert (
        client_mod.cheaperinference_bare_id_for_house_slug(
            "deepseek/deepseek-v4-flash:online"
        )
        is None
    )


def test_anthropic_not_mapped_to_ci() -> None:
    assert (
        client_mod.cheaperinference_bare_id_for_house_slug("anthropic/claude-sonnet-5")
        is None
    )
