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


@pytest.mark.parametrize(
    "banned",
    [
        "OLLAMA/QWEN3:8B",
        "Ollama/Qwen3:8b",
        " ollama/qwen3:8b ",
    ],
)
def test_completion_rejects_banned_model_case_insensitive(banned: str) -> None:
    fake_client = MagicMock()
    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(ValueError, match="banned"),
    ):
        digillm.completion(banned, [{"role": "user", "content": "hi"}])
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


def test_default_client_api_key_fail_fast_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing house key must raise — never the late-401 sentinel ``not-set`` (#3788)."""
    monkeypatch.delenv("LITELLM_PROXY_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    digillm.clear_caches()
    with pytest.raises(RuntimeError, match="No LLM API key configured"):
        client_mod._default_client_api_key()
    with (
        patch.object(client_mod, "OpenAI") as openai_ctor,
        pytest.raises(RuntimeError, match="No LLM API key configured"),
    ):
        digillm.get_client()
    openai_ctor.assert_not_called()


def test_byok_non_proxy_base_mismatch_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """BYOK override base_url must match the registered provider — no house fallthrough."""
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-house")
    digillm.clear_caches()
    with digillm.byok("sk-ant-user", "https://evil.example/v1"):
        with pytest.raises(RuntimeError, match="refusing silent house/vendor fallthrough"):
            digillm.get_client_for_model("anthropic/claude-sonnet-5")


def test_completion_rejects_tools_with_response_format() -> None:
    tools = [
        {
            "type": "function",
            "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}},
        }
    ]
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "Out", "schema": {"type": "object"}, "strict": True},
    }
    with pytest.raises(ValueError, match="mutually exclusive"):
        digillm.completion(
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            tools=tools,  # type: ignore[arg-type]
            response_format=response_format,  # type: ignore[arg-type]
        )


def test_stream_chunk_decode_error_emits_failed_not_cancelled() -> None:
    """Malformed chunk handling must report FAILED, not CANCELLED (#3788)."""
    from digillm.telemetry import ProviderAttemptOutcome, ProviderAttemptRecord, TelemetryRecord

    class _BrokenChoice:
        @property
        def delta(self) -> object:
            raise AttributeError("broken delta")

    class _BrokenChunk:
        choices = [_BrokenChoice()]

    class _Attempts(list[ProviderAttemptRecord]):
        def observe(self, record: TelemetryRecord) -> None:
            if isinstance(record, ProviderAttemptRecord):
                self.append(record)

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = iter([_BrokenChunk()])
    attempts = _Attempts()
    digillm.set_telemetry_observer(attempts)
    with (
        patch.object(client_mod, "get_client_for_model", return_value=fake_client),
        pytest.raises(AttributeError, match="broken delta"),
    ):
        digillm.run_tools(
            "gpt-4o-mini",
            [{"role": "user", "content": "hello"}],
            [],
            execute_tool=lambda *_args: "",
            stream_deltas=True,
        )
    assert len(attempts) == 1
    assert attempts[0].outcome is ProviderAttemptOutcome.FAILED
    assert attempts[0].error_type == "AttributeError"
