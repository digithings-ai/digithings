"""digigraph's thin LLM entry point over digillm.

Relocated from the former monolithic ``digigraph.llm`` (#632 P2). digigraph calls
LLMs exclusively through these two wrappers, which add the digigraph-specific glue
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
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import (
    Any,  # score:allow untyped any — heterogeneous LLM tool/step payloads
    Iterator,
)
from uuid import uuid4

from digillm import (  # telemetry + message types for the wrappers below
    CacheStatus,
    CallPurpose,
    ChatCompletionMessage,
    JsonSchemaResponseFormat,
    NoArtifactReason,
    ProviderAttemptOutcome,
    ProviderAttemptRecord,
    ProviderCallContextHandle,
    ProviderCallOutcome,
    ProviderCallRecord,
    RetryReason,
    ToolArguments,
    ToolDefinition,
)
from digillm import completion as _digillm_completion
from digillm import (
    provider_call_context as _digillm_provider_call_context,
)
from digillm import run_tools as _digillm_run_tools
from digillm import set_fan_out_detach_hook as _set_fan_out_detach_hook
from digillm import set_telemetry_observer as _set_telemetry_observer
from digillm import set_usage_observer as _set_usage_observer
from openai.types.chat import ChatCompletion

from digigraph import usage as _usage
from digigraph.model_config import resolve_request_model

logger = logging.getLogger(__name__)

# Public surface. ``digifetch_web_search`` is the single tool-only grounding
# entry — the synthesis engine (plain-completion grounding + citation regexes)
# was deleted (#3859). Consumers import every LLM entry point from this module.
__all__ = [
    "completion",
    "completion_text",
    "run_tools",
    "digifetch_web_search",
]

# Route digillm's usage telemetry into digigraph's per-run accumulator. No-op until
# digigraph.usage.start() activates a run; registered here because llm_client is the
# module every digigraph LLM call imports.
_set_usage_observer(_usage.record)
_set_telemetry_observer(_usage.DETAILED_USAGE_OBSERVER)

# Drop digigraph's own logical-call description inside every digillm parallel tool worker.
# digillm's fan-out copies the caller's context so the request's BYOK credentials reach the
# pool, and ``detach_provider_call_context`` clears digillm's own logical-call var in each
# worker -- but digigraph layers ``usage._LOGICAL_CALL_CONTEXT`` on top, holding the very
# same mutable ProviderCallContextHandle. Without this, parallel workers would share one
# handle and interleave their telemetry. Registered alongside the observers above, and for
# the same reason: llm_client is the module every digigraph LLM call imports.
_set_fan_out_detach_hook(_usage.detach_logical_call_context)


@contextmanager
def _logical_call_scope(
    default_purpose: CallPurpose,
    default_no_artifact_reason: NoArtifactReason,
    *,
    follow_up_purpose: CallPurpose | None = None,
    follow_up_no_artifact_reason: NoArtifactReason | None = None,
) -> Iterator[ProviderCallContextHandle]:
    """Bridge generic DigiGraph metadata only when a real node identity is available."""
    node_run_id, metadata = _usage.provider_call_metadata()
    if node_run_id is None:
        yield metadata.handle if metadata is not None else ProviderCallContextHandle()
        return
    if metadata is None:
        with _digillm_provider_call_context(
            node_run_id=node_run_id,
            purpose=default_purpose,
            no_artifact_reason=default_no_artifact_reason,
            follow_up_purpose=follow_up_purpose,
            follow_up_no_artifact_reason=follow_up_no_artifact_reason,
        ) as handle:
            yield handle
        return
    with _digillm_provider_call_context(
        node_run_id=node_run_id,
        purpose=metadata.purpose,
        parent_call_id=metadata.parent_call_id,
        artifacts=metadata.artifacts,
        no_artifact_reason=metadata.no_artifact_reason,
        follow_up_purpose=metadata.follow_up_purpose,
        follow_up_artifacts=metadata.follow_up_artifacts,
        follow_up_no_artifact_reason=metadata.follow_up_no_artifact_reason,
        defer_finalization=metadata.defer_finalization,
        handle=metadata.handle,
    ) as handle:
        metadata.handle.last_call_id = handle.last_call_id
        try:
            yield handle
        finally:
            metadata.handle.last_call_id = handle.last_call_id


def completion(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    tools: list[ToolDefinition] | None = None,
    tool_choice: str | ToolArguments = "auto",
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
) -> ChatCompletion:
    """Single chat completion through digillm; returns the OpenAI ``ChatCompletion`` object.

    The model is resolved with :func:`resolve_request_model` first (provider-key→
    Ollama fallback, ``ollama-cloud/`` strip, mode / ``OLLAMA_MODEL`` selection).
    Read ``resp.choices[0].message.content`` / ``.tool_calls`` from the result.
    """
    default_purpose = (
        CallPurpose.STRUCTURED_COMPLETION
        if response_format is not None
        else CallPurpose.INITIAL_GENERATION
    )
    with _logical_call_scope(default_purpose, NoArtifactReason.CONSUMED_INLINE):
        return _digillm_completion(
            resolve_request_model(model),
            messages,
            temperature=temperature,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            max_tokens=max_tokens,
        )


def completion_text(
    model: str,
    messages: list[ChatCompletionMessage],
    *,
    temperature: float = 0.2,
    response_format: JsonSchemaResponseFormat | None = None,
    max_tokens: int | None = None,
) -> str:
    """Run :func:`completion` and return the first choice's text (stripped, ``""`` if none).

    Convenience for the many call sites that only want the assistant text — it
    preserves the legacy ``chat_completion`` no-tools return exactly (strip;
    empty string when the response has no choices or no content). For tool calls
    or the full ``ChatCompletion`` object, call :func:`completion` /
    :func:`run_tools` directly.
    """
    resp = completion(
        model,
        messages,
        temperature=temperature,
        response_format=response_format,
        max_tokens=max_tokens,
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
    tool_choice: str = "auto",
    on_tool_step: Callable[[str, Any], None] | None = None,
) -> str:
    """Run digillm's agentic tool-calling loop with digigraph's parallel-safe set + streaming.

    Streams each assistant turn (``stream_deltas``) whenever ``on_tool_step`` is
    supplied, so the callback also receives ``("content", delta)`` / ``("reasoning",
    delta)`` alongside the tool-call/result steps. ``tool_choice`` forwards to
    every turn ("auto" default; "required" forces a tool call every round — see
    :func:`digigraph.tool_policy.require_tool_calls_for_workflow`). Returns the
    model's final answer.
    """
    with _logical_call_scope(
        CallPurpose.TOOL_SELECTION,
        NoArtifactReason.TOOL_DISPATCH,
        follow_up_purpose=CallPurpose.TOOL_FOLLOW_UP,
        follow_up_no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
    ):
        return _digillm_run_tools(
            resolve_request_model(model),
            messages,
            tools,
            execute_tool,
            temperature=temperature,
            max_tool_rounds=max_tool_rounds,
            tool_choice=tool_choice,
            on_tool_step=on_tool_step,
            parallel_safe_tools=_parallel_safe_tools(),
            stream_deltas=on_tool_step is not None,
        )


def digifetch_web_search(
    model: str,
    query: str,
    *,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    max_results: int = 8,
    usage_kind: str = "web_search",
    context: Any | None = None,
) -> tuple[str, list[str]]:
    """Tool-only web grounding. Raises on any failure — never synthesizes, never None.

    ``model`` is accepted for caller compat but unused — the tool path needs no
    synthesis model. ``usage_kind`` is likewise retained for compat (telemetry
    retires in a later task). The bearer threads via ``context`` (Task 2 seam:
    ``ToolContext.state["digi_bearer"]``).
    """
    del model, usage_kind
    from digigraph.orchestration.web_search_tools import call_digisearch_web_search

    raw = call_digisearch_web_search(
        query,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        max_results=max_results,
        context=context,
    )
    rows = (raw or {}).get("results", []) if isinstance(raw, dict) else []
    if not rows:
        raise RuntimeError(f"web_search tool returned no rows for query={query!r}")
    summary = "\n".join(f"- {r.get('content', '')} ({r.get('doc_id', '')})" for r in rows)
    sources = [r.get("doc_id", "") for r in rows]
    _usage.record(kind="web_search", model="digisearch:web_search", sources=len(sources))
    _emit_web_search_telemetry(source_count=len(sources))
    return summary, sources


def _emit_web_search_telemetry(*, source_count: int) -> None:
    """Emit the detailed provider-call records for one tool-only web_search call.

    No-op unless a usage run is active. The tool path has no LLM attempt, so the
    attempt carries zero tokens and no cost — the summary/counts still reconcile
    with :func:`digigraph.usage.snapshot` while ``cost_usd`` stays unavailable
    (never fabricated).
    """
    del source_count
    node_run_id, _metadata = _usage.provider_call_metadata()
    if node_run_id is None:
        node_run_id = uuid4()
    now = datetime.now(tz=timezone.utc)
    call_id = uuid4()
    _usage.observe_telemetry(
        ProviderCallRecord(
            call_id=call_id,
            node_run_id=node_run_id,
            parent_call_id=None,
            purpose=CallPurpose.WEB_SEARCH,
            requested_model="digisearch:web_search",
            cache_status=CacheStatus.BYPASSED,
            outcome=ProviderCallOutcome.SUCCEEDED,
            attempt_count=1,
            artifacts=(),
            no_artifact_reason=NoArtifactReason.CONSUMED_INLINE,
            started_at=now,
            finished_at=now,
        )
    )
    _usage.observe_telemetry(
        ProviderAttemptRecord(
            attempt_id=uuid4(),
            call_id=call_id,
            attempt_number=1,
            provider="digisearch",
            requested_model="digisearch:web_search",
            served_model=None,
            outcome=ProviderAttemptOutcome.SUCCEEDED,
            retry_reason=RetryReason.NOT_APPLICABLE,
            prompt_tokens=0,
            completion_tokens=0,
            # None, not 0.0: detailed projections never fabricate cost
            # evidence (WP1 / #2763) — the aggregate snapshot sums missing
            # cost as 0.0 for diagnostics; both are pinned by
            # test_detailed_tool_search_projection_matches_aggregate_token_semantics.
            cost_usd=None,
            started_at=now,
            finished_at=now,
        )
    )
