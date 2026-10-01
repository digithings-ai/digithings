"""Phase 2 dual-export tracing wiring for digigraph (#4931).

LangGraph run/node spans nest with digillm LLM/tool spans (which already go
through ``digitrace.trace.traceable`` in ``digillm.client`` — those call sites
are unchanged). Two mechanisms, both fail-soft:

1. Explicit spans: :func:`trace_run` decorates the workflow entry points in
   ``workflow.py``; :func:`trace_node` wraps the plain-function graph nodes in
   ``graph/graph.py``. Each emits a LangSmith run AND an OTel span (Langfuse)
   via ``digitrace.trace``. The compiled research subgraph is deliberately NOT
   wrapped — it must stay a native runnable so ``graph.stream(...,
   subgraphs=True)`` custom events keep flowing.
2. Auto-instrumentation: :func:`configure_langgraph_tracing` defaults
   ``LANGSMITH_TRACING`` / ``LANGCHAIN_TRACING_V2`` on when a LangSmith key is
   present, so LangGraph natively emits run/node traces without code changes.

No-op when neither backend is configured (decorators return the original
function). Never carries prompts, documents, or secrets — only run/node
names plus the correlation ids ``digitrace.trace`` already allows.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

try:
    from digitrace.trace import traceable as _traceable
except ImportError:  # digitrace not installed — tracing degrades to no-op

    def _traceable(name: str, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorator


F = TypeVar("F", bound=Callable[..., Any])

#: Span/run name for a full workflow execution (all three entry points share it
#: so runs are comparable across invoke / via-stream / streaming paths).
RUN_SPAN_NAME = "digigraph_workflow_run"

#: Prefix for per-node spans registered in ``graph/graph.py``.
NODE_SPAN_PREFIX = "digigraph_node"

__all__ = [
    "NODE_SPAN_PREFIX",
    "RUN_SPAN_NAME",
    "configure_langgraph_tracing",
    "trace_node",
    "trace_run",
]


def configure_langgraph_tracing() -> dict[str, bool]:
    """Enable LangGraph auto-instrumentation when a LangSmith key is present.

    Idempotent: only fills in ``LANGSMITH_TRACING`` / ``LANGCHAIN_TRACING_V2``
    when the operator has not set them explicitly. Returns the backend status
    snapshot (``{"langsmith": ..., "otel": ...}``) for logging / tests.
    """
    langsmith = bool((os.environ.get("LANGSMITH_API_KEY") or "").strip())
    if langsmith:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    otel = any(
        (os.environ.get(key) or "").strip()
        for key in (
            "DIGITRACE_LANGFUSE_OTLP_ENDPOINT",
            "LANGFUSE_OTLP_ENDPOINT",
            "DIGI_OTEL_ENDPOINT",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        )
    )
    try:
        from digitrace.config import otel_export_configured, tracing_enabled

        status = {"langsmith": tracing_enabled(), "otel": otel_export_configured()}
    except ImportError:
        status = {"langsmith": langsmith, "otel": otel}
    logger.debug("digigraph tracing status: %s", status)
    return status


def trace_node(name: str) -> Callable[[F], F]:
    """Return a decorator adding a ``digigraph_node_<name>`` span to a node function."""
    return _traceable(f"{NODE_SPAN_PREFIX}_{name}")


def trace_run(fn: F) -> F:
    """Decorate a workflow entry point with the shared run span."""
    return _traceable(RUN_SPAN_NAME)(fn)
