"""OpenTelemetry-only tracing wiring for digigraph.

LangGraph run/node spans nest with digillm LLM/tool spans (which already go
through ``digitrace.trace.traceable`` in ``digillm.client`` — those call sites
are unchanged). The single mechanism is fail-soft:

:func:`trace_run` decorates the workflow entry points in ``workflow.py``;
:func:`trace_node` wraps the plain-function graph nodes in ``graph/graph.py``.
Each emits an OTLP span to the in-house digitrace collector via
``digitrace.trace``. The compiled research subgraph is deliberately NOT
wrapped — it must stay a native runnable so
``graph.stream(..., subgraphs=True)`` custom events keep flowing.

There is no vendor SDK leg: external observability providers are integrations
digitrace can export to over OTLP, not a backend this service configures. The
plug point is the generic endpoint/headers pair
(``DIGI_OTEL_ENDPOINT`` / ``DIGITRACE_OTLP_ENDPOINT`` /
``OTEL_EXPORTER_OTLP_ENDPOINT`` plus ``DIGI_OTEL_HEADERS``).

No-op when no OTLP endpoint is configured (decorators return the original
function). Never carries prompts, documents, or secrets — only run/node names
plus the correlation ids ``digitrace.trace`` already allows.
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
    """Report whether the OTLP export leg is configured.

    Fail-soft and side-effect free: no vendor SDK is enabled and no environment
    variable is written. Returns ``{"otel": ...}`` for logging / tests so the
    call sites in ``workflow.py`` can stay unchanged.
    """
    otel = any(
        (os.environ.get(key) or "").strip()
        for key in (
            "DIGI_OTEL_ENDPOINT",
            "DIGITRACE_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        )
    )
    try:
        from digitrace.config import otel_export_configured

        status = {"otel": otel_export_configured()}
    except ImportError:
        status = {"otel": otel}
    logger.debug("digigraph tracing status: %s", status)
    return status


def trace_node(name: str) -> Callable[[F], F]:
    """Return a decorator adding a ``digigraph_node_<name>`` span to a node function."""
    return _traceable(f"{NODE_SPAN_PREFIX}_{name}")


def trace_run(fn: F) -> F:
    """Decorate a workflow entry point with the shared run span."""
    return _traceable(RUN_SPAN_NAME)(fn)
