"""Tests for digillm: routing, chat_completion, tools, structured output, overrides.

The OpenAI client is mocked throughout — no network. Caches are cleared between
tests (module-global response/client caches would otherwise mask the mock).
"""

from __future__ import annotations

import json
from typing import Any  # noqa: ANN401 — fake OpenAI client dict shapes
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

import digillm
from digillm import client as client_mod


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear module-global caches and provider env vars before each test."""
    digillm.clear_caches()
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "LITELLM_PROXY_API_KEY",
        "XAI_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "DIGI_LLM_CACHE_TTL_SECONDS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    digillm.clear_caches()


def _mock_response(content: str = "", tool_calls: Any = None) -> MagicMock:
    """Build a mock OpenAI ChatCompletion response with one choice."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── Provider routing / client construction ──────────────────────────────────


def test_parse_provider_prefix_known_and_unknown() -> None:
    assert client_mod._parse_provider_prefix("groq/llama-3.3-70b") == ("groq", "llama-3.3-70b")
    assert client_mod._parse_provider_prefix("gpt-4o-mini") == (None, "gpt-4o-mini")
    # Unregistered prefix is treated as a plain model (default client handles it).
    assert client_mod._parse_provider_prefix("ollama/qwen2.5") == (None, "ollama/qwen2.5")


def test_get_client_for_model_external_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gk-test")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        c1 = digillm.get_client_for_model("groq/llama-3.3-70b")
        c2 = digillm.get_client_for_model("groq/other-model")  # cached by provider
    assert made["api_key"] == "gk-test"
    assert made["base_url"] == "https://api.groq.com/openai/v1"
    assert c1 is c2  # provider client is cached and reused


def test_get_client_for_model_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        digillm.get_client_for_model("gemini/gemini-2.5-flash")


def test_default_client_uses_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
    monkeypatch.setenv("OPENAI_API_BASE", "http://localhost:4000/")
    made: dict[str, Any] = {}

    def fake_openai(**kwargs: Any) -> MagicMock:
        made.update(kwargs)
        return MagicMock()

    with patch.object(client_mod, "OpenAI", side_effect=fake_openai):
        digillm.get_client_for_model("gpt-4o-mini")
    assert made["api_key"] == "sk-default"
    assert made["base_url"] == "http://localhost:4000"  # trailing slash stripped


def test_default_client_cached_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-1")
    with patch.object(client_mod, "OpenAI", side_effect=lambda **_: MagicMock()):
        a = digillm.get_client()
        b = digillm.get_client()
        assert a is b
        monkeypatch.setenv("OPENAI_API_KEY", "sk-2")  # different cache key
        c = digillm.get_client()
        assert c is not a


def test_register_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client_mod.register_provider("acme", "https://acme.test/v1", "ACME_API_KEY")
    try:
        monkeypatch.setenv("ACME_API_KEY", "ak-1")
        made: dict[str, Any] = {}
        with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: made.update(kw) or MagicMock()):
            digillm.get_client_for_model("acme/model-x")
        assert made["base_url"] == "https://acme.test/v1"
        assert made["api_key"] == "ak-1"
    finally:
        client_mod._EXTERNAL_PROVIDERS.pop("acme", None)


# ── chat_completion ─────────────────────────────────────────────────────────


def test_chat_completion_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("  hello world  ")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.chat_completion("groq/llama-3.3-70b", [{"role": "user", "content": "hi"}])
    assert out == "hello world"
    # Bare model_id (prefix stripped) is what hits the wire.
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "llama-3.3-70b"


def test_chat_completion_passes_model_as_given_no_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("ok")
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        digillm.chat_completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    _, kwargs = fake_client.chat.completions.create.call_args
    assert kwargs["model"] == "gpt-4o-mini"  # used verbatim, no env substitution


def test_chat_completion_response_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("cached-value")
    msgs = [{"role": "user", "content": "same"}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        first = digillm.chat_completion("gpt-4o-mini", msgs)
        second = digillm.chat_completion("gpt-4o-mini", msgs)
    assert first == second == "cached-value"
    # Second call served from cache → underlying API hit exactly once.
    assert fake_client.chat.completions.create.call_count == 1


def test_chat_completion_empty_choices() -> None:
    fake_client = MagicMock()
    empty = MagicMock()
    empty.choices = []
    fake_client.chat.completions.create.return_value = empty
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        assert digillm.chat_completion("gpt-4o-mini", [{"role": "user", "content": "x"}]) == ""


def test_chat_completion_with_tools_returns_tuple() -> None:
    fn = MagicMock()
    fn.name = "get_weather"
    fn.arguments = '{"city": "Paris"}'
    tc = MagicMock()
    tc.id = "call_1"
    tc.function = fn
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("", tool_calls=[tc])
    tools = [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.chat_completion(
            "gpt-4o-mini", [{"role": "user", "content": "weather?"}], tools=tools
        )
    assert isinstance(out, tuple)
    content, tool_calls = out
    assert content == ""
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert tool_calls[0]["id"] == "call_1"


# ── Tool-calling loop ────────────────────────────────────────────────────────


def test_chat_completion_with_tools_loop() -> None:
    """One tool round, then a final text answer."""
    fn = MagicMock()
    fn.name = "lookup"
    fn.arguments = '{"q": "x"}'
    tc = MagicMock()
    tc.id = "c1"
    tc.function = fn

    responses = [
        _mock_response("", tool_calls=[tc]),  # round 1: request tool
        _mock_response("final answer"),  # round 2: no tools → final
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    executed: list[tuple[str, dict]] = []

    def execute_tool(name: str, args: dict) -> str:
        executed.append((name, args))
        return "tool-result"

    steps: list[tuple[str, Any]] = []
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.chat_completion_with_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
        )
    assert out == "final answer"
    assert executed == [("lookup", {"q": "x"})]
    assert ("tool_call", {"name": "lookup", "arguments": {"q": "x"}}) in steps
    assert any(k == "tool_result" for k, _ in steps)


def test_chat_completion_with_tools_parallel_branch() -> None:
    """Two parallel-safe tools in one round run via the concurrent branch."""
    fn_a = MagicMock()
    fn_a.name = "alpha"
    fn_a.arguments = '{"n": 1}'
    tc_a = MagicMock()
    tc_a.id = "a"
    tc_a.function = fn_a
    fn_b = MagicMock()
    fn_b.name = "beta"
    fn_b.arguments = '{"n": 2}'
    tc_b = MagicMock()
    tc_b.id = "b"
    tc_b.function = fn_b

    responses = [
        _mock_response("", tool_calls=[tc_a, tc_b]),  # round 1: two tool calls
        _mock_response("done"),  # round 2: final answer
    ]
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = responses

    executed: set[str] = set()

    def execute_tool(name: str, args: dict) -> dict:
        executed.add(name)
        return {"content": f"{name}-result"}

    steps: list[tuple[str, Any]] = []
    tools = [
        {"type": "function", "function": {"name": "alpha", "parameters": {}}},
        {"type": "function", "function": {"name": "beta", "parameters": {}}},
    ]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        out = digillm.chat_completion_with_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "go"}],
            tools,
            execute_tool,
            on_tool_step=lambda kind, payload: steps.append((kind, payload)),
            parallel_safe_tools={"alpha", "beta"},
        )
    assert out == "done"
    assert executed == {"alpha", "beta"}
    # Both tools fire a tool_call and a tool_result event (parallel branch defers
    # the tool_call event until after dispatch, but still emits it for each).
    call_names = {p["name"] for k, p in steps if k == "tool_call"}
    result_names = {p["name"] for k, p in steps if k == "tool_result"}
    assert call_names == {"alpha", "beta"}
    assert result_names == {"alpha", "beta"}


def test_normalize_tool_arguments_repairs_bad_json() -> None:
    assert json.loads(client_mod._normalize_tool_arguments('{"a": 1')) == {"a": 1}
    assert client_mod._normalize_tool_arguments("") == "{}"
    assert json.loads(client_mod._normalize_tool_arguments('{"a": 1,}')) == {"a": 1}
    assert client_mod._normalize_tool_arguments("not json at all") == "{}"


# ── Retry ────────────────────────────────────────────────────────────────────


def test_create_with_retry_retries_then_succeeds() -> None:
    from openai import APITimeoutError

    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = [
        APITimeoutError(request=MagicMock()),
        _mock_response("recovered"),
    ]
    with patch.object(client_mod, "_sleep_transient_retry", return_value=5.0) as sleep:
        r = client_mod._create_with_retry(fake_client, model="m", messages=[])
    assert r.choices[0].message.content == "recovered"
    assert sleep.call_count == 1


def test_create_with_retry_propagates_non_transient() -> None:
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = ValueError("bad request")
    with pytest.raises(ValueError, match="bad request"):
        client_mod._create_with_retry(fake_client, model="m", messages=[])


# ── Per-request overrides (contextvars) ──────────────────────────────────────


def test_set_proxy_key_changes_default_client_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    made: list[dict[str, Any]] = []
    with patch.object(
        client_mod, "OpenAI", side_effect=lambda **kw: made.append(kw) or MagicMock()
    ):
        digillm.get_client()  # uses env key
        with digillm.proxy_key("proxy-tok"):
            digillm.get_client()  # uses proxy override
    assert made[0]["api_key"] == "sk-env"
    assert made[1]["api_key"] == "proxy-tok"


def test_set_proxy_key_reset_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    tok = digillm.set_proxy_key("temp")
    assert digillm.get_proxy_key() == "temp"
    digillm.reset_proxy_key(tok)
    assert digillm.get_proxy_key() is None


def test_set_byok_uncached_and_uses_supplied_key() -> None:
    made: list[dict[str, Any]] = []
    with patch.object(
        client_mod, "OpenAI", side_effect=lambda **kw: made.append(kw) or MagicMock()
    ):
        with digillm.byok("user-key", "https://api.openai.com/v1"):
            a = digillm.get_client()
            b = digillm.get_client()
    # BYOK clients are never cached: two constructions for two calls.
    assert len(made) == 2
    assert a is not b
    assert made[0]["api_key"] == "user-key"
    assert made[0]["base_url"] == "https://api.openai.com/v1"


def test_byok_bypasses_response_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_response("byok-out")
    msgs = [{"role": "user", "content": "same"}]
    with patch.object(client_mod, "get_client_for_model", return_value=fake_client):
        with digillm.byok("user-key"):
            digillm.chat_completion("gpt-4o-mini", msgs)
            digillm.chat_completion("gpt-4o-mini", msgs)
    # No cache while BYOK active → API hit twice.
    assert fake_client.chat.completions.create.call_count == 2


# ── structured_completion ────────────────────────────────────────────────────


class _Person(BaseModel):
    name: str
    age: int


def test_structured_completion_happy_path() -> None:
    payload = '{"name": "Ada", "age": 36}'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(payload)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            person = digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
            )
    assert isinstance(person, _Person)
    assert person.name == "Ada" and person.age == 36


def test_structured_completion_strips_markdown_fences() -> None:
    fenced = '```json\n{"name": "Bob", "age": 5}\n```'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(fenced)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            person = digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
            )
    assert person.name == "Bob" and person.age == 5


def test_structured_completion_sends_json_schema_response_format() -> None:
    captured: dict[str, Any] = {}

    def fake_create(_client: Any, **kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return _mock_response('{"name": "X", "age": 1}')

    with patch.object(client_mod, "_create_with_retry", side_effect=fake_create):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            digillm.structured_completion(
                "gpt-4o-mini", [{"role": "user", "content": "x"}], _Person
            )
    rf = captured["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "_Person"
    assert "properties" in rf["json_schema"]["schema"]


def test_structured_completion_validation_error() -> None:
    bad = '{"name": "NoAge"}'  # missing required 'age'
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response(bad)):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            with pytest.raises(ValidationError):
                digillm.structured_completion(
                    "gpt-4o-mini", [{"role": "user", "content": "who?"}], _Person
                )


def test_structured_completion_empty_raises() -> None:
    with patch.object(client_mod, "_create_with_retry", return_value=_mock_response("")):
        with patch.object(client_mod, "get_client_for_model", return_value=MagicMock()):
            with pytest.raises(ValueError, match="Empty response"):
                digillm.structured_completion(
                    "gpt-4o-mini", [{"role": "user", "content": "x"}], _Person
                )


# ── Mode resolution ──────────────────────────────────────────────────────────


def test_resolve_model_from_mapping() -> None:
    modes = {"test": "gpt-4o-mini", "medium": "gpt-4o", "best": "o1"}
    assert digillm.resolve_model("test", modes) == "gpt-4o-mini"
    assert digillm.resolve_model("BEST", modes) == "o1"


def test_resolve_model_default_fallback() -> None:
    assert digillm.resolve_model("medium", {}, default="fallback-model") == "fallback-model"


def test_resolve_model_missing_raises() -> None:
    with pytest.raises(KeyError):
        digillm.resolve_model("best", {"test": "m"})


def test_resolve_model_from_yaml_path(tmp_path: Any) -> None:
    yaml_file = tmp_path / "model_modes.yaml"
    yaml_file.write_text("defaults:\n  test: tiny-model\n  best: big-model\n")
    assert digillm.resolve_model("test", path=yaml_file) == "tiny-model"
    assert digillm.resolve_model("best", path=yaml_file) == "big-model"


def test_resolve_model_yaml_flat_mapping(tmp_path: Any) -> None:
    yaml_file = tmp_path / "modes.yaml"
    yaml_file.write_text("test: a\nmedium: b\nbest: c\n")
    assert digillm.resolve_model("medium", path=yaml_file) == "b"
