"""Unit tests for digigraph.llm_client (completion/run_tools wrappers over digillm).

The wrappers' job is glue: resolve the model, compute the parallel-safe set, map
``on_tool_step`` → ``stream_deltas``, and delegate to digillm. The LLM mechanics
themselves (routing, retry, caching, the agentic loop, parallel dispatch) live in
digillm and are covered by digillm/tests/test_digillm.py, so these tests mock the
digillm entry points and assert correct wiring.
"""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import pytest

from digigraph import llm_client


@pytest.mark.unit
class TestCompletion:
    """completion() resolves the model and delegates to digillm.completion."""

    def test_resolves_model_and_delegates(self) -> None:
        sentinel = MagicMock(name="ChatCompletion")
        with (
            patch.object(llm_client, "resolve_request_model", return_value="resolved/model") as rrm,
            patch.object(llm_client, "_digillm_completion", return_value=sentinel) as comp,
        ):
            out = llm_client.completion(
                "gpt-4o-mini",
                [{"role": "user", "content": "hi"}],
                temperature=0.5,
                max_tokens=128,
            )
        assert out is sentinel
        rrm.assert_called_once_with("gpt-4o-mini")
        args, kwargs = comp.call_args
        assert args[0] == "resolved/model"
        assert args[1] == [{"role": "user", "content": "hi"}]
        assert kwargs["temperature"] == 0.5
        assert kwargs["max_tokens"] == 128
        assert kwargs["tools"] is None

    def test_forwards_tools_and_response_format(self) -> None:
        tools = [{"type": "function", "function": {"name": "f"}}]
        rf = {"type": "json_schema", "json_schema": {"name": "S", "schema": {}}}
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch.object(llm_client, "_digillm_completion", return_value=MagicMock()) as comp,
        ):
            llm_client.completion("x", [], tools=tools, response_format=rf, tool_choice="auto")
        kwargs = comp.call_args[1]
        assert kwargs["tools"] == tools
        assert kwargs["response_format"] == rf
        assert kwargs["tool_choice"] == "auto"


@pytest.mark.unit
class TestCompletionText:
    """completion_text() returns the first choice's text (legacy chat_completion contract)."""

    def _resp(self, content: str | None, *, empty: bool = False) -> MagicMock:
        resp = MagicMock()
        resp.choices = [] if empty else [MagicMock(message=MagicMock(content=content))]
        return resp

    def test_returns_stripped_first_choice_content(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch.object(llm_client, "_digillm_completion", return_value=self._resp("  hi there  ")),
        ):
            out = llm_client.completion_text("model", [{"role": "user", "content": "x"}])
        assert out == "hi there"

    def test_empty_choices_returns_empty_string(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch.object(llm_client, "_digillm_completion", return_value=self._resp(None, empty=True)),
        ):
            assert llm_client.completion_text("model", []) == ""

    def test_none_content_returns_empty_string(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch.object(llm_client, "_digillm_completion", return_value=self._resp(None)),
        ):
            assert llm_client.completion_text("model", []) == ""


@pytest.mark.unit
class TestRunTools:
    """run_tools() wires parallel_safe + stream_deltas and delegates to digillm.run_tools."""

    def test_no_callback_is_non_streaming_with_parallel_safe(self) -> None:
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch(
                "digigraph.orchestration.registry.list_tool_names", return_value=["a", "b"]
            ),
            patch.object(llm_client, "_digillm_run_tools", return_value="done") as rt,
        ):
            out = llm_client.run_tools(
                "model", [{"role": "user", "content": "go"}], [], execute_tool=lambda n, a: "ok"
            )
        assert out == "done"
        kwargs = rt.call_args[1]
        assert kwargs["parallel_safe_tools"] == {"a", "b"}
        assert kwargs["stream_deltas"] is False
        assert kwargs["on_tool_step"] is None

    def test_callback_enables_streaming(self) -> None:
        cb = MagicMock()
        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch("digigraph.orchestration.registry.list_tool_names", return_value=[]),
            patch.object(llm_client, "_digillm_run_tools", return_value="x") as rt,
        ):
            llm_client.run_tools("model", [], [], execute_tool=lambda n, a: "", on_tool_step=cb)
        kwargs = rt.call_args[1]
        assert kwargs["stream_deltas"] is True
        assert kwargs["on_tool_step"] is cb

    def test_missing_registry_yields_empty_parallel_safe(self) -> None:
        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "digigraph.orchestration.registry":
                raise ImportError("registry unavailable")
            return real_import(name, *args, **kwargs)

        with (
            patch.object(llm_client, "resolve_request_model", return_value="m"),
            patch.object(llm_client, "_digillm_run_tools", return_value="x") as rt,
            patch.object(builtins, "__import__", side_effect=fake_import),
        ):
            llm_client.run_tools("model", [], [], execute_tool=lambda n, a: "")
        assert rt.call_args[1]["parallel_safe_tools"] == set()
