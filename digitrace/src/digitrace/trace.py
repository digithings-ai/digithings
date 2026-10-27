"""Optional LangSmith + OTLP dual-export trace wrappers with PII redaction.

``traceable(name)`` fans out to two legs — the LangSmith SDK leg (as before,
when ``LANGSMITH_API_KEY`` is set) **and** an OpenTelemetry leg (when an OTLP
endpoint env var is set through :mod:`digibase.otel`). Either leg missing
degrades to the other; both missing returns the original function unmodified
(zero per-call overhead).

Under ADR-0036 the OTel leg is the leg that survives. It carries the
``gen_ai.*`` and OpenInference semantic-convention attributes (model,
provider, token counts, span kind), the ADR-0036 correlation ids
(``tenant.id``, ``pipeline.run_id``, ``session.id``) and the pre-existing
``digi.*`` run/request/session ids. It **never** carries prompt or completion
text: the input and output are redacted, then reduced to a SHA-256 digest and a
character count. A truncated, redacted preview is available only when
``DIGI_TRACE_CONTENT_PREVIEW`` is set (off by default).

Every attribute key is drawn from :data:`SPAN_ATTRIBUTE_ALLOWLIST`; callers
cannot add arbitrary keywords to a span. Unlisted keys are dropped with a
debug log rather than exported. Errors set the span status and ``error.type``
(the exception class name only — never the message or a stack trace).
"""

from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any, Final, TypeVar

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

__all__ = [
    "LANGSMITH_SDK_AVAILABLE",
    "SPAN_ATTRIBUTE_ALLOWLIST",
    "SPAN_KINDS",
    "apply_span_allowlist",
    "content_preview_enabled",
    "otel_leg_enabled",
    "traceable",
]


#: Correlation keys copied onto OTel spans when present as short strings.
_CORRELATION_KEYS = ("workflow_id", "request_id", "session_id")

#: Max length for a correlation value — longer values are dropped, never truncated
#: (truncation could split a token and still leak part of it).
_MAX_CORRELATION_CHARS = 128

#: ADR-0036 correlation ids. The first matching keyword wins.
_CANONICAL_ID_KEYS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("tenant_id", "tenant", "tenant_slug"), "tenant.id"),
    (("pipeline_run_id", "run_id"), "pipeline.run_id"),
    (("session_id",), "session.id"),
)

#: OpenInference span kinds accepted by ``traceable(span_kind=...)``.
SPAN_KINDS: Final[frozenset[str]] = frozenset(
    {"LLM", "CHAIN", "TOOL", "AGENT", "RETRIEVER", "EMBEDDING", "RERANKER", "UNKNOWN"}
)

#: The one place a span attribute key may come from. Anything else is dropped.
SPAN_ATTRIBUTE_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        # digitrace identity (pre-ADR-0036, kept for parity).
        "digi.run_name",
        "digi.workflow_id",
        "digi.request_id",
        "digi.session_id",
        # ADR-0036 correlation ids.
        "tenant.id",
        "pipeline.run_id",
        "session.id",
        # OTel GenAI semantic conventions.
        "gen_ai.operation.name",
        "gen_ai.provider.name",
        "gen_ai.system",
        "gen_ai.request.model",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.total_tokens",
        # OpenInference mirror.
        "openinference.span.kind",
        "llm.provider",
        "llm.model_name",
        "llm.token_count.prompt",
        "llm.token_count.completion",
        "llm.token_count.total",
        # Content is reduced to a digest + length; previews are opt-in only.
        "digi.input.sha256",
        "digi.input.length",
        "digi.output.sha256",
        "digi.output.length",
        "digi.input.preview",
        "digi.output.preview",
        # Failure signal without the exception message or stack trace.
        "error.type",
    }
)

_PREVIEW_ENVS = ("DIGI_TRACE_CONTENT_PREVIEW", "DIGITRACE_CONTENT_PREVIEW")
_PREVIEW_CHARS_ENV = "DIGI_TRACE_PREVIEW_CHARS"
_DEFAULT_PREVIEW_CHARS = 200
_MAX_PREVIEW_CHARS = 1000

_MODEL_MAX_CHARS = 200
_ERROR_TYPE_MAX_CHARS = 64

_OPERATION_BY_KIND: Final[dict[str, str]] = {
    "LLM": "chat",
    "AGENT": "invoke_agent",
    "TOOL": "execute_tool",
    "EMBEDDING": "embeddings",
}


def otel_leg_enabled() -> bool:
    """True when the OTel fan-out leg can emit (endpoint set + API importable)."""
    if not otel_export_configured():
        return False
    try:
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return False
    return True


def content_preview_enabled() -> bool:
    """True only when the operator opted in to redacted, truncated previews."""
    for key in _PREVIEW_ENVS:
        raw = (os.environ.get(key) or "").strip().lower()
        if raw:
            return raw in {"1", "true", "yes", "on"}
    return False


def _preview_chars() -> int:
    raw = (os.environ.get(_PREVIEW_CHARS_ENV) or "").strip()
    if not raw:
        return _DEFAULT_PREVIEW_CHARS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PREVIEW_CHARS
    return max(1, min(value, _MAX_PREVIEW_CHARS))


def apply_span_allowlist(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the allowlisted, scalar-valued span attributes.

    This is the enforcement point for ADR-0036 §7: no arbitrary keyword
    argument reaches a span, and no non-scalar payload survives.
    """
    cleaned: dict[str, Any] = {}
    for key, value in attributes.items():
        if key not in SPAN_ATTRIBUTE_ALLOWLIST:
            logger.debug("dropping non-allowlisted span attribute %r", key)
            continue
        if isinstance(value, bool):
            cleaned[key] = value
        elif isinstance(value, int):
            cleaned[key] = value
        elif isinstance(value, float):
            cleaned[key] = value
        elif isinstance(value, str):
            if value:
                cleaned[key] = value
        elif isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
            cleaned[key] = list(value)
    return cleaned


def _lookup(args: tuple[Any, ...], kwargs: dict[str, Any], key: str) -> Any:
    value = kwargs.get(key)
    if value is None and args and isinstance(args[0], Mapping):
        value = args[0].get(key)
    return value


def _clean_id(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > _MAX_CORRELATION_CHARS:
        return ""
    return value


def _correlation_attrs(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, str]:
    """Extract safe correlation ids from call args (never prompts or secrets)."""
    attrs: dict[str, str] = {}
    for key in _CORRELATION_KEYS:
        cleaned = _clean_id(_lookup(args, kwargs, key))
        if cleaned:
            attrs[f"digi.{key}"] = cleaned
    for keys, attribute in _CANONICAL_ID_KEYS:
        for key in keys:
            cleaned = _clean_id(_lookup(args, kwargs, key))
            if cleaned:
                attrs[attribute] = cleaned
                break
    return attrs


def _infer_span_kind(name: str) -> str:
    lowered = name.lower()
    if "embedding" in lowered:
        return "EMBEDDING"
    if "retriev" in lowered:
        return "RETRIEVER"
    if "rerank" in lowered:
        return "RERANKER"
    if "completion" in lowered or "chat" in lowered or "llm" in lowered:
        return "LLM"
    if "agent" in lowered or "tools" in lowered:
        return "AGENT"
    if "tool" in lowered:
        return "TOOL"
    return "CHAIN"


def _clean_model(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    if not value or len(value) > _MODEL_MAX_CHARS:
        return ""
    if any(char.isspace() for char in value):
        return ""
    return value


def _clean_provider(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    if not value or len(value) > 32:
        return ""
    if not all(char.isalnum() or char in {"_", "-"} for char in value):
        return ""
    return value


def _model_attrs(args: tuple[Any, ...], kwargs: dict[str, Any], span_kind: str) -> dict[str, str]:
    model = _clean_model(kwargs.get("model") or kwargs.get("model_name"))
    if not model and span_kind in {"LLM", "AGENT", "EMBEDDING"} and args:
        # digillm passes the model as the first positional argument.
        if isinstance(args[0], str):
            model = _clean_model(args[0])
    if not model:
        return {}
    attrs = {"gen_ai.request.model": model, "llm.model_name": model}
    provider = _clean_provider(kwargs.get("provider") or kwargs.get("gen_ai_system"))
    if not provider and "/" in model:
        provider = _clean_provider(model.split("/", 1)[0])
    if provider:
        # ``gen_ai.system`` is the stable OTel name; ``gen_ai.provider.name``
        # is its successor in the newer semantic conventions.
        attrs["gen_ai.system"] = provider
        attrs["gen_ai.provider.name"] = provider
        attrs["llm.provider"] = provider
    return attrs


def _get_field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _token_int(usage: Any, *names: str) -> int | None:
    for name in names:
        raw = _get_field(usage, name)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, int) and raw >= 0:
            return raw
        if isinstance(raw, float) and raw >= 0 and raw.is_integer():
            return int(raw)
    return None


def _usage_attrs(result: Any) -> dict[str, int]:
    """Token counts from a completion result, when the result reports them."""
    usage = _get_field(result, "usage")
    if usage is None:
        return {}
    prompt = _token_int(usage, "prompt_tokens", "input_tokens")
    completion = _token_int(usage, "completion_tokens", "output_tokens")
    total = _token_int(usage, "total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    attrs: dict[str, int] = {}
    if prompt is not None:
        attrs["gen_ai.usage.input_tokens"] = prompt
        attrs["llm.token_count.prompt"] = prompt
    if completion is not None:
        attrs["gen_ai.usage.output_tokens"] = completion
        attrs["llm.token_count.completion"] = completion
    if total is not None:
        attrs["gen_ai.usage.total_tokens"] = total
        attrs["llm.token_count.total"] = total
    return attrs


def _stable_payload(value: Any, *, depth: int = 0) -> Any:
    """A JSON-safe, deterministic view of *value* (never a raw repr with an address)."""
    if depth > 6:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _stable_payload(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_payload(v, depth=depth + 1) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_stable_payload(v, depth=depth + 1) for v in value), key=repr)
    if callable(value):
        return f"<{type(value).__name__}>"
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _stable_payload(dump(), depth=depth + 1)
        except Exception:  # pragma: no cover - defensive: tracing never raises
            return f"<{type(value).__name__}>"
    if hasattr(value, "__dict__"):
        try:
            return _stable_payload(
                {k: v for k, v in vars(value).items() if not k.startswith("_")},
                depth=depth + 1,
            )
        except Exception:  # pragma: no cover - defensive: tracing never raises
            return f"<{type(value).__name__}>"
    return f"<{type(value).__name__}>"


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):  # pragma: no cover - _stable_payload is JSON-safe
        return repr(value)


def _content_attrs(
    redactor: PiiRedactor,
    value: Any,
    *,
    prefix: str,
    as_input: bool,
) -> dict[str, Any]:
    """Hash + length of the redacted content; preview only behind the opt-in."""
    redacted = redactor.process_inputs(value) if as_input else redactor.process_outputs(value)
    canonical = _canonical_json(_stable_payload(redacted))
    attrs: dict[str, Any] = {
        f"digi.{prefix}.sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        f"digi.{prefix}.length": len(canonical),
    }
    if content_preview_enabled():
        limit = _preview_chars()
        preview = canonical[:limit]
        if len(canonical) > limit:
            preview += "…"
        attrs[f"digi.{prefix}.preview"] = preview
    return attrs


def _input_attrs(
    redactor: PiiRedactor, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> dict[str, Any]:
    payload = {"args": list(args), "kwargs": kwargs}
    return _content_attrs(redactor, payload, prefix="input", as_input=True)


def _output_attrs(redactor: PiiRedactor, result: Any) -> dict[str, Any]:
    return _content_attrs(redactor, result, prefix="output", as_input=False)


def _set_span_attributes(span: Any, attributes: Mapping[str, Any], *, context: str) -> None:
    """Apply allowlisted attributes one by one; tracing must never break the call."""
    for key, value in apply_span_allowlist(attributes).items():
        try:
            span.set_attribute(key, value)
        except Exception as exc:
            logger.debug("OTel span attribute %r failed for %s: %s", key, context, exc)


def _maybe_wrap_otel(
    fn: F,
    name: str,
    *,
    redactor: PiiRedactor,
    span_kind: str | None = None,
) -> F:
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

    kind = span_kind or _infer_span_kind(name)

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        attrs: dict[str, Any] = {
            "digi.run_name": name,
            "openinference.span.kind": kind,
        }
        operation = _OPERATION_BY_KIND.get(kind)
        if operation:
            attrs["gen_ai.operation.name"] = operation
        attrs.update(_correlation_attrs(args, kwargs))
        attrs.update(_model_attrs(args, kwargs, kind))
        try:
            attrs.update(_input_attrs(redactor, args, kwargs))
        except Exception as exc:  # fail-soft: hashing never breaks the call
            logger.debug("OTel input hashing failed for %r: %s", name, exc)
        try:
            span_cm = tracer.start_as_current_span(
                f"digitrace.{name}", attributes=apply_span_allowlist(attrs)
            )
        except Exception as exc:
            logger.debug("OTel span start failed for %r: %s", name, exc)
            return fn(*args, **kwargs)
        with span_cm as span:
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                try:
                    span.set_status(StatusCode.ERROR)
                except Exception as status_exc:
                    logger.debug("OTel span error-status failed for %r: %s", name, status_exc)
                try:
                    span.set_attribute("error.type", type(exc).__name__[:_ERROR_TYPE_MAX_CHARS])
                except Exception as type_exc:
                    logger.debug("OTel span error-type failed for %r: %s", name, type_exc)
                raise
            try:
                _set_span_attributes(span, _usage_attrs(result), context=name)
                _set_span_attributes(span, _output_attrs(redactor, result), context=name)
            except Exception as exc:  # fail-soft: tracing must never break caller work
                logger.debug("OTel output attributes failed for %r: %s", name, exc)
            return result

    return _wrapper  # type: ignore[return-value]


def traceable(
    name: str,
    *,
    redactor: PiiRedactor | None = None,
    span_kind: str | None = None,
) -> Callable[[F], F]:
    """Wrap *fn* with LangSmith ``traceable`` + OTel fan-out when enabled.

    The LangSmith leg applies PII redaction via the SDK's ``process_inputs`` /
    ``process_outputs`` callbacks. The OTel leg opens one span per call carrying
    the allowlisted ``gen_ai.*`` / OpenInference attributes, the ADR-0036
    correlation ids, and a hash + length of the redacted input and output.
    Returns the original function when neither leg is active.

    ``span_kind`` pins the OpenInference span kind (see :data:`SPAN_KINDS`);
    when omitted it is inferred from *name*, defaulting to ``CHAIN``.
    """
    if span_kind is not None and span_kind not in SPAN_KINDS:
        raise ValueError(f"unknown span kind {span_kind!r}; expected one of {sorted(SPAN_KINDS)}")

    def decorator(fn: F) -> F:
        wrapped = fn
        active_redactor = redactor or default_redactor()
        if LANGSMITH_SDK_AVAILABLE and os.environ.get("LANGSMITH_API_KEY"):
            try:
                wrapped = _langsmith.traceable(  # type: ignore[assignment]
                    name=name,
                    process_inputs=active_redactor.process_inputs,
                    process_outputs=active_redactor.process_outputs,
                )(wrapped)
            # SIMP-023: keep setup fallback for LangSmith SDK version skew; not a silent swallow.
            except (TypeError, ValueError, RuntimeError, OSError) as exc:
                logger.debug("LangSmith traceable setup failed for %r: %s", name, exc)
        return _maybe_wrap_otel(
            wrapped,
            name,
            redactor=active_redactor,
            span_kind=span_kind,
        )

    return decorator
