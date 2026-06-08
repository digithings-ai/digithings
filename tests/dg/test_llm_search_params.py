"""xAI Live Search: search_parameters ride through the OpenAI client via extra_body."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import chat_completion

SEARCH_PARAMS = {
    "mode": "on",
    "sources": [{"type": "web", "allowed_websites": ["reuters.com"]}],
    "return_citations": True,
}


def _mock_client() -> MagicMock:
    create = MagicMock()
    create.return_value.choices = [MagicMock(message=MagicMock(content="ok", tool_calls=None))]
    client = MagicMock()
    client.chat.completions.create = create
    return client


@pytest.mark.unit
def test_search_params_forwarded_via_extra_body_for_xai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = _mock_client()
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        chat_completion(
            "xai/grok-4.3",
            [{"role": "user", "content": "hi"}],
            search_parameters=SEARCH_PARAMS,
        )
    captured = client.chat.completions.create.call_args[1]
    assert captured["extra_body"] == {"search_parameters": SEARCH_PARAMS}


@pytest.mark.unit
def test_search_params_ignored_for_non_xai(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _mock_client()
    with patch("digigraph.llm.get_client", return_value=client):
        chat_completion(
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            search_parameters=SEARCH_PARAMS,
        )
    captured = client.chat.completions.create.call_args[1]
    assert "extra_body" not in captured
