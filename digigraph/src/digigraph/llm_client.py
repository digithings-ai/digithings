"""DigiGraph's thin LLM entry point over digillm.

Relocated from the former monolithic ``digigraph.llm`` (#632 P2). DigiGraph calls
LLMs exclusively through these two wrappers, which add the DigiGraph-specific glue
on top of the provider-agnostic digillm client:

- :func:`completion` resolves the requested model via
  :func:`digigraph.model_config.resolve_request_model` (digillm performs no
  env/YAML substitution) and returns the OpenAI ``ChatCompletion`` object.
- :func:`run_tools` additionally computes the ``parallel_safe`` tool set from the
  orchestration registry and enables streaming (``stream_deltas``) whenever a
  per-step callback is supplied, then delegates the agentic loop to digillm.

Per-request auth (proxy key / BYOK) is wired separately by
:mod:`digigraph.llm_auth`; both wrappers inherit it through digillm's contextvars.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any  # noqa: ANN401 — heterogeneous LLM tool/step payloads

from digillm import (
    ChatCompletionMessage,
    JsonSchemaResponseFormat,
    ToolArguments,
    ToolDefinition,
)
from digillm import completion as _digillm_completion
from digillm import run_tools as _digillm_run_tools
from digillm import web_search, x_search  # re-exported: xAI grounding pre-passes
from openai.types.chat import ChatCompletion

from digigraph.model_config import resolve_request_model

logger = logging.getLogger(__name__)

# Public surface. ``web_search`` / ``x_search`` are re-exported from digillm so DigiGraph
# and DigiQuant consumers import every LLM entry point from this one module.
__all__ = ["completion", "completion_text", "run_tools", "web_search", "x_search"]


def completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> ChatCompletion:
    """Single chat completion through digillm; returns the OpenAI ``ChatCompletion`` object.

    The model is resolved with :func:`resolve_request_model` first (provider-key→
    Ollama fallback, ``ollama-cloud/`` strip, mode / ``OLLAMA_MODEL`` selection).
    Read ``resp.choices[0].message.content`` / ``.tool_calls`` from the result.
    ``search_parameters`` forwards an xAI Live Search descriptor (no-op off xAI).
    """
    return _digillm_completion(
        resolve_request_model(model),
        messages,
        temperature=temperature,
        tools=tools,
        tool_choice=tool_choice,
        response_format=response_format,
        max_tokens=max_tokens,
        search_parameters=search_parameters,
    )


def completion_text(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> str:
    """Run :func:`completion` and return the first choice's text (stripped, ``""`` if none).

    Convenience for the many call sites that only want the assistant text — it
    preserves the legacy ``chat_completion`` no-tools return exactly (strip;
    empty string when the response has no choices or no content). For tool calls
    or the full ``ChatCompletion`` object, call :func:`completion` /
    :func:`run_tools` directly. ``search_parameters`` is forwarded to xAI Live Search.
    """
    resp = completion(
        model,
        messages,
        temperature=temperature,
        response_format=response_format,
        max_tokens=max_tokens,
        search_parameters=search_parameters,
    )
    if not resp.choices:
        return ""
    return (resp.choices[0].message.content or "").strip()


def _parallel_safe_tools() -> set[str]:
    """Tool names safe to run concurrently, from the orchestration registry (empty if unavailable)."""
    try:
        from digigraph.orchestration.registry import list_tool_names

        return set(list_tool_names("parallel_safe"))
    except ImportError as e:
        logger.debug("Could not load parallel_safe tool list: %s", e)
        return set()


def run_tools(
    model: str,
    messages: list[ChatCompletionMessage],
    tools: list[ToolDefinition],
    execute_tool: Callable[[str, ToolArguments], str | dict[str, Any]],
    *,
    temperature: float = 0.2,
    max_tool_rounds: int = 5,
    on_tool_step: Callable[[str, Any], None] | None = None,
    search_parameters: dict[str, Any] | None = None,
) -> str:
    """Run digillm's agentic tool-calling loop with DigiGraph's parallel-safe set + streaming.

    Streams each assistant turn (``stream_deltas``) whenever ``on_tool_step`` is
    supplied, so the callback also receives ``("content", delta)`` / ``("reasoning",
    delta)`` alongside the tool-call/result steps. ``search_parameters`` forwards an
    xAI Live Search descriptor (first tool round only). Returns the model's final answer.
    """
    return _digillm_run_tools(
        resolve_request_model(model),
        messages,
        tools,
        execute_tool,
        temperature=temperature,
        max_tool_rounds=max_tool_rounds,
        on_tool_step=on_tool_step,
        parallel_safe_tools=_parallel_safe_tools(),
        stream_deltas=on_tool_step is not None,
        search_parameters=search_parameters,
    )
