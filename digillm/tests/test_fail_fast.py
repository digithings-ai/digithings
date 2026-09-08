"""Fail-fast routing and retry budgets for digillm (#3078).

The OpenAI client is mocked throughout — no network.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import digillm
from digillm import client as client_mod

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    previous_usage_observer = client_mod._usage_observer
    digillm.clear_caches()
    digillm.set_usage_observer(None)
    for var in ("OPENAI_API_KEY", "OPENAI_API_BASE", "DIGILLM_PROVIDER_MAX_ATTEMPTS"):
        monkeypatch.delenv(var, raising=False)
    yield
    digillm.set_usage_observer(previous_usage_observer)
    digillm.clear_caches()


def _tool_call_response(name: str = "query_data") -> MagicMock:
    tc = MagicMock()
    tc.id = "call_1"
    tc.function.name = name
    tc.function.arguments = "{}"
    msg = MagicMock()
    msg.content = ""
    msg.tool_calls = [tc]
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_completion_rejects_banned_model_without_calling_provider() -> None:
    fake_client = MagicMock()
    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(ValueError, match="ollama/qwen3:8b"),
    ):
        digillm.completion("ollama/qwen3:8b", [{"role": "user", "content": "hi"}])
    assert fake_client.chat.completions.create.call_count == 0


def test_run_tools_rejects_banned_model() -> None:
    with pytest.raises(ValueError, match="ollama/qwen3:8b"):
        digillm.run_tools(
            "ollama/qwen3:8b",
            [{"role": "user", "content": "hi"}],
            [],
            execute_tool=lambda *_: "",
        )


def test_run_tools_stops_after_two_consecutive_same_tool_errors() -> None:
    execute_tool = MagicMock(side_effect=ValueError("column close does not exist"))
    with (
        patch.object(client_mod, "completion", return_value=_tool_call_response("query_data")),
        pytest.raises(RuntimeError, match="query_data"),
    ):
        digillm.run_tools(
            "deepseek/deepseek-v4-flash",
            [{"role": "user", "content": "hi"}],
            [{"type": "function", "function": {"name": "query_data"}}],
            execute_tool=execute_tool,
            max_tool_rounds=10,
        )
    assert execute_tool.call_count == 2


def test_provider_retry_budget_honors_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openai import APITimeoutError

    monkeypatch.setenv("DIGILLM_PROVIDER_MAX_ATTEMPTS", "2")
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = APITimeoutError(request=MagicMock())
    with (
        patch.object(client_mod, "_sleep_transient_retry", return_value=0.0),
        pytest.raises(APITimeoutError),
    ):
        client_mod._create_with_retry(fake_client, model="m", messages=[])
    assert fake_client.chat.completions.create.call_count == 2
