"""DigiLLM — the single home for provider-agnostic LLM client code in DigiThings.

Speaks to any OpenAI-compatible endpoint (LiteLLM proxy, Ollama, OpenRouter,
OpenAI direct, or a registered external provider). No FastAPI, no service
coupling; optional LangSmith tracing via digismith degrades to a no-op when
absent.

Public API:
- :func:`chat_completion` — single completion (optional tools / structured output).
- :func:`chat_completion_with_tools` — non-streaming tool-calling loop.
- :func:`structured_completion` — validated Pydantic model from a json_schema call.
- :func:`get_client_for_model` / :func:`get_client` / :func:`register_provider`.
- :func:`resolve_model` — opt-in test/medium/best mode resolution.
- Per-request overrides: :func:`set_proxy_key` / :func:`reset_proxy_key`,
  :func:`set_byok` / :func:`reset_byok`, and the ``proxy_key`` / ``byok``
  context managers.
"""

from digillm.client import (
    ChatCompletionMessage,
    JsonSchemaResponseFormat,
    ToolArguments,
    ToolCallDict,
    ToolCallFunction,
    ToolDefinition,
    ToolFunctionSpec,
    byok,
    clear_caches,
    completion,
    get_byok,
    get_client,
    get_client_for_model,
    get_proxy_key,
    proxy_key,
    register_provider,
    reset_byok,
    reset_proxy_key,
    run_tools,
    set_byok,
    set_proxy_key,
)
from digillm.structured import resolve_model, structured_completion

__version__ = "0.1.0"

__all__ = [
    "ChatCompletionMessage",
    "JsonSchemaResponseFormat",
    "ToolArguments",
    "ToolCallDict",
    "ToolCallFunction",
    "ToolDefinition",
    "ToolFunctionSpec",
    "__version__",
    "byok",
    "clear_caches",
    "completion",
    "get_byok",
    "get_client",
    "get_client_for_model",
    "get_proxy_key",
    "proxy_key",
    "register_provider",
    "reset_byok",
    "reset_proxy_key",
    "resolve_model",
    "run_tools",
    "set_byok",
    "set_proxy_key",
    "structured_completion",
]
