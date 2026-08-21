"""digillm — the single home for provider-agnostic LLM client code in digithings.

Speaks to any OpenAI-compatible endpoint (LiteLLM proxy, Ollama, OpenRouter,
OpenAI direct, or a registered external provider). No FastAPI, no service
coupling; optional LangSmith tracing via digismith degrades to a no-op when
absent.

Public API:
- :func:`completion` — single completion (optional tools / json_schema output),
  mirroring ``litellm.completion``; returns the OpenAI ``ChatCompletion`` object.
- :func:`run_tools` — agentic tool-calling loop (optional streaming).
- :func:`structured_completion` — validated Pydantic model from a json_schema call.
- :func:`get_client_for_model` / :func:`get_client` / :func:`register_provider`.
- :func:`is_registered_provider` / :func:`get_provider_api_key_env` — read-only
  registry lookups for callers that need to check provider config before routing.
- :func:`resolve_model` — opt-in test/medium/best mode resolution.
- Per-request overrides: :func:`set_proxy_key` / :func:`reset_proxy_key`,
  :func:`set_byok` / :func:`reset_byok`, and the ``proxy_key`` / ``byok``
  context managers.
"""

from digillm.client import (
    ChatCompletionMessage,
    JsonSchemaResponseFormat,
    ProviderCallContextHandle,
    ToolArguments,
    ToolCallDict,
    ToolCallFunction,
    ToolDefinition,
    ToolFunctionSpec,
    byok,
    clear_byok,
    clear_caches,
    completion,
    detach_provider_call_context,
    get_byok,
    get_client,
    get_client_for_model,
    get_provider_api_key_env,
    get_proxy_key,
    is_registered_provider,
    openrouter_web_search,
    provider_call_context,
    proxy_key,
    register_provider,
    reset_byok,
    reset_proxy_key,
    run_tools,
    set_byok,
    set_fan_out_detach_hook,
    set_proxy_key,
    set_telemetry_observer,
    set_usage_observer,
    web_search,
    x_search,
)
from digillm.structured import resolve_model, structured_completion
from digillm.telemetry import (
    ArtifactRef,
    CacheStatus,
    CallPurpose,
    NoArtifactReason,
    NodeRunOutcome,
    NodeRunRecord,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallOutcome,
    ProviderCallRecord,
    RetryReason,
    TelemetryFailureReporter,
    TelemetryObserver,
    TelemetryRecord,
    emit_telemetry,
)

__version__ = "0.1.0"

__all__ = [
    "ArtifactRef",
    "CacheStatus",
    "CallPurpose",
    "ChatCompletionMessage",
    "JsonSchemaResponseFormat",
    "NodeRunOutcome",
    "NodeRunRecord",
    "NoArtifactReason",
    "ProviderAttemptOutcome",
    "ProviderAttemptRecord",
    "ProviderCallOutcome",
    "ProviderCallRecord",
    "ProviderCallContextHandle",
    "RetryReason",
    "TelemetryFailureReporter",
    "TelemetryObserver",
    "TelemetryRecord",
    "ToolArguments",
    "ToolCallDict",
    "ToolCallFunction",
    "ToolDefinition",
    "ToolFunctionSpec",
    "__version__",
    "byok",
    "clear_byok",
    "clear_caches",
    "completion",
    "detach_provider_call_context",
    "emit_telemetry",
    "get_byok",
    "get_client",
    "get_client_for_model",
    "get_provider_api_key_env",
    "get_proxy_key",
    "is_registered_provider",
    "proxy_key",
    "provider_call_context",
    "register_provider",
    "reset_byok",
    "reset_proxy_key",
    "resolve_model",
    "run_tools",
    "set_byok",
    "set_fan_out_detach_hook",
    "set_proxy_key",
    "set_telemetry_observer",
    "set_usage_observer",
    "structured_completion",
    "web_search",
    "openrouter_web_search",
    "x_search",
]
