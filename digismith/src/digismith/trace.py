"""Optional LangSmith trace wrappers with PII redaction.

When the LangSmith SDK is installed and ``LANGSMITH_API_KEY`` is set,
``traceable(name)`` wraps the target function with ``langsmith.traceable``
and attaches a :class:`~digismith.redaction.PiiRedactor` via the SDK's native
``process_inputs`` / ``process_outputs`` hooks so span payloads are scrubbed
before submission. Otherwise the decorator returns the original function
unmodified (zero per-call overhead).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

from digismith.redaction import PiiRedactor, default_redactor

logger = logging.getLogger(__name__)

try:
    import langsmith as _langsmith  # type: ignore[import-untyped]

    LANGSMITH_SDK_AVAILABLE = True
except ImportError:
    _langsmith = None  # type: ignore[assignment]
    LANGSMITH_SDK_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])

__all__ = ["LANGSMITH_SDK_AVAILABLE", "traceable"]


def traceable(name: str, *, redactor: PiiRedactor | None = None) -> Callable[[F], F]:
    """Wrap *fn* with LangSmith ``traceable`` + PII redaction when enabled.

    The decorator is a no-op when the SDK is missing or ``LANGSMITH_API_KEY``
    is unset, preserving the original function object (identity, ``__name__``,
    etc.). When active, inputs and outputs are passed through ``redactor``
    before LangSmith serializes them, using the SDK's ``process_inputs`` /
    ``process_outputs`` callbacks.
    """

    def decorator(fn: F) -> F:
        if LANGSMITH_SDK_AVAILABLE and os.environ.get("LANGSMITH_API_KEY"):
            active_redactor = redactor or default_redactor()
            try:
                return _langsmith.traceable(  # type: ignore[return-value]
                    name=name,
                    process_inputs=active_redactor.process_inputs,
                    process_outputs=active_redactor.process_outputs,
                )(fn)
            # SIMP-023: keep setup fallback for LangSmith SDK version skew; not a silent swallow.
            except (TypeError, ValueError, RuntimeError, OSError) as exc:
                logger.debug("LangSmith traceable setup failed for %r: %s", name, exc)
        return fn

    return decorator
