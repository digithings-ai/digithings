"""Optional LangSmith + OTLP dual-export trace wrappers with PII redaction.

Phase 2 (#4931): ``traceable(name)`` fans out to two legs — the LangSmith SDK
leg (as before, when ``LANGSMITH_API_KEY`` is set) **and** an OpenTelemetry
leg (when an OTLP endpoint env var is set, e.g. Langfuse
``/api/public/otel`` with Basic-auth headers via ``DIGI_OTEL_HEADERS`` /
``OTEL_EXPORTER_OTLP_HEADERS``). Either leg missing degrades to the other;
both missing returns the original function unmodified (zero per-call
overhead).

The OTel leg sets only safe attributes (run name + short correlation ids);
it never carries prompts, completions, or secrets. PII redaction for the
LangSmith leg stays on ``process_inputs`` / ``process_outputs`` as before.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from digitrace.config import otel_export_configured
from digitrace.redaction import PiiRedactor, default_redactor

logger = logging.getLogger(__name__)

try:
    import langsmith as _langsmith  # type: ignore[import-untyped]

    LANGSMITH_SDK_AVAILABLE = True
except ImportError:
    _langsmith = None  # type: ignore[assignment]
    LANGSMITH_SDK_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["LANGSMITH_SDK_AVAILABLE", "otel_leg_enabled", "traceable"]

#: Correlation keys copied onto OTel spans when present as short strings.
_CORRELATION_KEYS = ("workflow_id", "request_id", "session_id")

#: Max length for a correlation value — longer values are dropped, never truncated
#: (truncation could split a token and still leak part of it).
_MAX_CORRELATION_CHARS = 128


def otel_leg_enabled() -> bool:
    """True when the OTel fan-out leg can emit (endpoint set + API importable)."""
    if not otel_export_configured():
        return False
    try:
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return False
    return True


def _correlation_attrs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, str]:
    """Extract safe correlation ids from call args (never prompts or secrets)."""
    attrs: dict[str, str] = {}
    for key in _CORRELATION_KEYS:
        value = kwargs.get(key)
        if value is None and args and isinstance(args[0], Mapping):
            value = args[0].get(key)
        if isinstance(value, str):
            value = value.strip()
            if value and len(value) <= _MAX_CORRELATION_CHARS:
                attrs[f"digi.{key}"] = value
    return attrs


def _maybe_wrap_otel(fn: F, name: str) -> F:
    """Wrap *fn* in an OTel span per call; return *fn* unchanged when disabled."""
    if not otel_leg_enabled():
        return fn
    try:
        from opentelemetry import trace as _otel_trace
        from opentelemetry.trace import StatusCode
    except ImportError:
        return fn
    try:
        tracer = _otel_trace.get_tracer("digitrace")
    except Exception as exc:  # fail-soft: tracing must never break caller work
        logger.debug("OTel tracer setup failed for %r: %s", name, exc)
        return fn

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        attrs: dict[str, str] = {"digi.run_name": name}
        attrs.update(_correlation_attrs(args, kwargs))
        try:
            span_cm = tracer.start_as_current_span(f"digitrace.{name}", attributes=attrs)
        except Exception as exc:
            logger.debug("OTel span start failed for %r: %s", name, exc)
            return fn(*args, **kwargs)
        with span_cm as span:
            try:
                return fn(*args, **kwargs)
            except Exception:
                try:
                    span.set_status(StatusCode.ERROR)
                except Exception:
                    pass
                raise

    return _wrapper  # type: ignore[return-value]


def traceable(name: str, *, redactor: PiiRedactor | None = None) -> Callable[[F], F]:
    """Wrap *fn* with LangSmith ``traceable`` + OTel fan-out when enabled.

    Phase 2 dual-export (#4931): the LangSmith leg applies PII redaction via
    the SDK's ``process_inputs`` / ``process_outputs`` callbacks; the OTel leg
    (e.g. Langfuse ``/api/public/otel``) opens one span per call carrying only
    the run name plus short correlation ids. A no-op returning the original
    function when neither leg is active.
    """

    def decorator(fn: F) -> F:
        wrapped = fn
        if LANGSMITH_SDK_AVAILABLE and os.environ.get("LANGSMITH_API_KEY"):
            active_redactor = redactor or default_redactor()
            try:
                wrapped = _langsmith.traceable(  # type: ignore[assignment]
                    name=name,
                    process_inputs=active_redactor.process_inputs,
                    process_outputs=active_redactor.process_outputs,
                )(wrapped)
            # SIMP-023: keep setup fallback for LangSmith SDK version skew; not a silent swallow.
            except (TypeError, ValueError, RuntimeError, OSError) as exc:
                logger.debug("LangSmith traceable setup failed for %r: %s", name, exc)
        return _maybe_wrap_otel(wrapped, name)

    return decorator
