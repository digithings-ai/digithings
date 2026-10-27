"""OTLP-only trace wrapper with safe span attributes.

``traceable(name)`` opens one OpenTelemetry span per call when an OTLP endpoint
env var is set (pointing at the in-house digitrace OTLP ingest, headers via
``DIGI_OTEL_HEADERS`` / ``OTEL_EXPORTER_OTLP_HEADERS``). With no endpoint, or no
OpenTelemetry SDK importable, it returns the original function unmodified
(zero per-call overhead).

Specialising the endpoint at a third-party collector is an operator choice;
this library never configures a vendor SDK and needs no vendor secret.

The span sets only safe attributes (run name + short correlation ids); it never
carries prompts, completions, or secrets.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from digitrace.config import otel_export_configured

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["otel_leg_enabled", "traceable"]

#: Correlation keys copied onto OTel spans when present as short strings.
_CORRELATION_KEYS = ("workflow_id", "request_id", "session_id")

#: Max length for a correlation value — longer values are dropped, never truncated
#: (truncation could split a token and still leak part of it).
_MAX_CORRELATION_CHARS = 128


def otel_leg_enabled() -> bool:
    """True when the OTel export leg can emit (endpoint set + API importable)."""
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
        except Exception as exc:  # fail-soft: a broken tracer never breaks the call
            logger.debug("OTel span start failed for %r: %s", name, exc)
            return fn(*args, **kwargs)
        with span_cm as span:
            try:
                return fn(*args, **kwargs)
            except Exception:
                try:
                    span.set_status(StatusCode.ERROR)
                except Exception as status_exc:
                    logger.debug("OTel span error-status failed for %r: %s", name, status_exc)
                raise

    return _wrapper  # type: ignore[return-value]


def traceable(name: str) -> Callable[[F], F]:
    """Wrap a function in one OTel span per call when the OTLP leg is enabled.

    The span exports to the in-house digitrace ingest and carries only the run
    name plus short correlation ids. A no-op returning the original function
    when no endpoint is configured.
    """

    def decorator(fn: F) -> F:
        return _maybe_wrap_otel(fn, name)

    return decorator
