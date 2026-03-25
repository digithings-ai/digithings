"""Optional LangSmith trace wrappers (same behavior as legacy digigraph llm helpers)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

try:
    import langsmith as _langsmith  # type: ignore[import-untyped]

    LANGSMITH_SDK_AVAILABLE = True
except ImportError:
    _langsmith = None  # type: ignore[assignment]
    LANGSMITH_SDK_AVAILABLE = False

F = TypeVar("F", bound=Callable[..., Any])


def traceable(name: str) -> Callable[[F], F]:
    """Wrap *fn* with LangSmith ``traceable`` when the SDK is installed and ``LANGSMITH_API_KEY`` is set."""

    def decorator(fn: F) -> F:
        if LANGSMITH_SDK_AVAILABLE and os.environ.get("LANGSMITH_API_KEY"):
            try:
                return _langsmith.traceable(name=name)(fn)  # type: ignore[return-value]
            except Exception as exc:
                logger.debug("LangSmith traceable setup failed for %r: %s", name, exc)
        return fn

    return decorator
