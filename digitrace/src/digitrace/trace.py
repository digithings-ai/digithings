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
import threading
from collections.abc import Callable, Mapping
from typing import Any, TypeVar
from urllib.parse import urlsplit, urlunsplit

from digibase.otel import resolve_otel_headers

from digitrace.config import langfuse_otlp_endpoint, otel_export_configured
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

_EXPORTER_LOCK = threading.Lock()

# After a Langfuse OTLP endpoint, the generic OTEL vars. Status treats all
# four as "export on"; the exporter has to use the same order.
_GENERIC_OTLP_ENVS = ("DIGI_OTEL_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT")

# OTLP/HTTP traces. The exporter posts to the URL it is given and does not
# append this when the configured path is already non-empty, so
# ``.../api/public/otel`` would 404 on cloud.langfuse.com.
_TRACES_PATH = "/v1/traces"


def _traces_endpoint(endpoint: str) -> str:
    """Return *endpoint* with ``/v1/traces`` on the path when it is missing.

    A value that already ends in that path is unchanged, so it is not doubled.
    Query and userinfo are kept; this does not touch auth headers.
    """
    parts = urlsplit(endpoint.strip())
    path = parts.path.rstrip("/")
    if not path.endswith(_TRACES_PATH):
        path = f"{path}{_TRACES_PATH}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _export_endpoint() -> str:
    """Endpoint the OTLP exporter should post to, or ``""`` when unset."""
    endpoint = langfuse_otlp_endpoint()
    if endpoint:
        return endpoint
    for key in _GENERIC_OTLP_ENVS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def _ensure_otlp_exporter() -> None:
    """Install an OTLP HTTP exporter when the global provider is still a proxy.

    ``otel_export_configured`` is true for ``DIGITRACE_LANGFUSE_OTLP_ENDPOINT``
    alone, but nothing else in this process attaches an exporter to that URL.
    Spans opened by :func:`traceable` would otherwise stay in-process. A
    provider that is already a real SDK provider is left alone. Missing SDK
    packages are a no-op so tests (and hosts without ``digibase[otel]``) keep
    the in-memory tracer.
    """
    endpoint = _export_endpoint()
    if not endpoint:
        return
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return
    with _EXPORTER_LOCK:
        provider = otel_trace.get_tracer_provider()
        if type(provider).__name__ != "ProxyTracerProvider":
            return
        try:
            headers = resolve_otel_headers() or None
            exporter = OTLPSpanExporter(endpoint=_traces_endpoint(endpoint), headers=headers)
            sdk_provider = TracerProvider()
            sdk_provider.add_span_processor(BatchSpanProcessor(exporter))
            otel_trace.set_tracer_provider(sdk_provider)
        except Exception as exc:  # tracing must never break the caller
            logger.debug("OTLP exporter setup failed: %s", exc)


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
    _ensure_otlp_exporter()
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
