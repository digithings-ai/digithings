"""Fail-fast routing and retry budgets for digillm (#3078).

The OpenAI client is mocked throughout — no network.
"""

from __future__ import annotations

import threading
import time
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
    for var in (
        "OPENAI_API_KEY",
        "OPENAI_API_BASE",
        "DIGILLM_PROVIDER_MAX_ATTEMPTS",
        "DIGILLM_MAX_CONCURRENT_CALLS",
    ):
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


def test_concurrent_calls_default_and_invalid_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert client_mod._max_concurrent_calls() == 8
    monkeypatch.setenv("DIGILLM_MAX_CONCURRENT_CALLS", "junk")
    assert client_mod._max_concurrent_calls() == 8
    monkeypatch.setenv("DIGILLM_MAX_CONCURRENT_CALLS", "0")
    assert client_mod._max_concurrent_calls() == 1


def test_concurrent_provider_calls_bounded_by_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # #3738 — a 6-wide burst with limit 2 must never exceed 2 in flight.
    monkeypatch.setenv("DIGILLM_MAX_CONCURRENT_CALLS", "2")
    monkeypatch.setenv("DIGILLM_PROVIDER_MAX_ATTEMPTS", "1")
    in_flight = 0
    observed: list[int] = []
    lock = threading.Lock()
    fake_client = MagicMock()

    def fake_create(**kwargs: object) -> MagicMock:
        nonlocal in_flight
        with lock:
            in_flight += 1
            observed.append(in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return MagicMock()

    fake_client.chat.completions.create.side_effect = fake_create
    threads = [
        threading.Thread(
            target=client_mod._create_with_retry,
            args=(fake_client,),
            kwargs={"model": "m", "messages": []},
        )
        for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    assert fake_client.chat.completions.create.call_count == 6
    assert max(observed) <= 2
