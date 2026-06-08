"""xAI Live Search: search_parameters ride through the OpenAI client via extra_body."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from digigraph.llm import chat_completion, chat_completion_with_tools

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


@pytest.mark.unit
def test_search_params_not_attached_on_xai_ollama_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # xai/ model but no key → falls back to the local Ollama client; Live Search
    # must NOT ride that call.
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = _mock_client()
    with patch("digigraph.llm.get_client", return_value=client):
        chat_completion(
            "xai/grok-4.3",
            [{"role": "user", "content": "xai-fallback-unique-prompt"}],
            search_parameters=SEARCH_PARAMS,
        )
    captured = client.chat.completions.create.call_args[1]
    assert "extra_body" not in captured


@pytest.mark.unit
def test_search_params_attached_only_on_first_tool_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Live Search is billed per request — the tool loop must search only once.
    seen: list[dict | None] = []
    tool_call = {"id": "1", "type": "function", "function": {"name": "t", "arguments": "{}"}}

    def fake_cc(
        model,
        messages,
        *,
        temperature=0.2,
        tools=None,
        tool_choice="auto",
        response_format=None,
        max_tokens=None,
        search_parameters=None,
    ):
        seen.append(search_parameters)
        # First round asks for a tool; second round returns the final answer.
        return ("", [tool_call]) if len(seen) == 1 else ("done", None)

    with patch("digigraph.llm.chat_completion", side_effect=fake_cc):
        out = chat_completion_with_tools(
            "xai/grok-4.3",
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "t"}}],
            execute_tool=lambda n, a: "{}",
            search_parameters=SEARCH_PARAMS,
        )
    assert out == "done"
    assert seen == [SEARCH_PARAMS, None]
