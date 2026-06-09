"""xAI Agent Tools web_search via the Responses API (grounding pre-pass, #650)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import web_search


def _resp(text: str, urls: list[str]):
    sources = [SimpleNamespace(url=u) for u in urls]
    web_item = SimpleNamespace(type="web_search_call", action=SimpleNamespace(sources=sources))
    reasoning = SimpleNamespace(type="reasoning", action=None)
    return SimpleNamespace(output_text=text, output=[reasoning, web_item])


@pytest.mark.unit
def test_web_search_returns_text_and_sources_for_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = MagicMock()
    client.responses.create.return_value = _resp(
        "CPI rose 0.6% MoM.[[1]](https://bls.gov/cpi/)", ["https://bls.gov/cpi/"]
    )
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        result = web_search(
            "xai/grok-4.3", "latest US CPI", allowed_domains=["bls.gov"], max_results=5
        )
    assert result is not None
    text, sources = result
    assert "CPI rose" in text
    assert sources == ["https://bls.gov/cpi/"]
    # web_search rides the Responses API with the filter applied.
    kwargs = client.responses.create.call_args[1]
    assert kwargs["tools"][0]["type"] == "web_search"
    assert kwargs["tools"][0]["filters"]["allowed_domains"] == ["bls.gov"]
    assert kwargs["model"] == "grok-4.3"


@pytest.mark.unit
def test_web_search_none_for_non_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    result = web_search("gpt-4o-mini", "anything")
    assert result is None


@pytest.mark.unit
def test_web_search_fails_soft_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = MagicMock()
    client.responses.create.side_effect = RuntimeError("boom")
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        assert web_search("xai/grok-4.3", "q") is None
