"""Run-scoped temporal boundary for dashboard Phase 1 registry reads (#2628 / WP4.1).

Every research/portfolio run pins one timezone-aware UTC ``knowledge_cutoff_at`` before
initial state construction. Later readers filter ``known_at <= knowledge_cutoff_at``
so a long or replayed run cannot observe records that arrived mid-run.

Anti-goals: no new scheduler, graph fork, or hidden ``now()`` fallback for
missing cutoffs — new readers fail closed via :func:`require_knowledge_cutoff_at`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any  # score:allow untyped any — scored-lint: heterogeneous dict / client shapes


class KnowledgeCutoffError(ValueError):
    """Raised when a registry reader needs a pinned cutoff and none is present."""


def require_utc_datetime(
    value: datetime,
    *,
    field_name: str = "timestamp",
) -> datetime:
    """Reject naive and non-UTC timestamps; return *value* unchanged when UTC.

    Offset must be exactly ``+00:00`` (``UTC`` / ``timezone.utc``). Fixed offsets
    that happen to equal zero are accepted; named zones with a non-zero offset
    are rejected.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime, got {type(value).__name__}")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware UTC (naive rejected)")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC (non-UTC offset rejected)")
    return value


def capture_knowledge_cutoff_at(
    *,
    now: Callable[[], datetime] | None = None,
) -> datetime:
    """Capture the run's knowledge cutoff as timezone-aware UTC.

    Call **before** constructing :class:`~digiquant.research.state.ResearchState`.
    Inject ``now`` only in tests — production always uses ``datetime.now(UTC)``.
    """
    stamp = now() if now is not None else datetime.now(UTC)
    return require_utc_datetime(stamp, field_name="knowledge_cutoff_at")


def require_knowledge_cutoff_at(state: Any) -> datetime:
    """Return the pinned cutoff or fail closed — never invent ``now()``.

    Legacy checkpoints may omit the field until they expire; new registry
    readers must call this helper rather than falling back to wall-clock time.
    """
    cutoff = getattr(state, "knowledge_cutoff_at", None)
    if cutoff is None:
        raise KnowledgeCutoffError(
            "knowledge_cutoff_at is required for registry readers; "
            "missing cutoff fails closed (no now() fallback)"
        )
    return require_utc_datetime(cutoff, field_name="knowledge_cutoff_at")


__all__ = [
    "KnowledgeCutoffError",
    "capture_knowledge_cutoff_at",
    "require_knowledge_cutoff_at",
    "require_utc_datetime",
]
