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
def test_live_search_410_deprecation_fails_soft(monkeypatch: pytest.MonkeyPatch) -> None:
    # xAI deprecated Live Search (HTTP 410). The search path must drop extra_body and
    # retry ungrounded rather than crash the phase (#650).
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    calls: list[dict] = []

    class _Gone(Exception):
        status_code = 410

    def create(**kwargs):
        calls.append(kwargs)
        if "extra_body" in kwargs:
            raise _Gone("Live search is deprecated. Please switch to the Agent Tools API")
        m = MagicMock()
        m.choices = [MagicMock(message=MagicMock(content="ungrounded-ok", tool_calls=None))]
        return m

    client = MagicMock()
    client.chat.completions.create = create
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        out = chat_completion(
            "xai/grok-4.3",
            [{"role": "user", "content": "410-failsoft-probe"}],
            search_parameters=SEARCH_PARAMS,
        )
    assert out == "ungrounded-ok"
    assert len(calls) == 2
    assert "extra_body" in calls[0]
    assert "extra_body" not in calls[1]


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
def test_live_search_bypasses_response_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # A Live Search request is time-sensitive and not captured by the cache key,
    # so two identical calls must each hit the API (no stale cached response).
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = _mock_client()
    msgs = [{"role": "user", "content": "live-search-cache-probe"}]
    with patch("digigraph.llm.get_client_for_model", return_value=client):
        chat_completion("xai/grok-4.3", msgs, search_parameters=SEARCH_PARAMS)
        chat_completion("xai/grok-4.3", msgs, search_parameters=SEARCH_PARAMS)
    assert client.chat.completions.create.call_count == 2


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
