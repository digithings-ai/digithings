"""Per-run overlay research budget (T4 / D9).

Attributed spend is the run-scoped WP1 snapshot
(``digigraph.usage.start(run_id=job.id)`` then ``snapshot()["cost_usd"]``).
``start`` clears process-global ``_CALLS``, so house spend from earlier
in the process is not attributed to the overlay job. Crossing
``ProfileConfig.research_budget_usd`` is a graceful stop: remaining
research is skipped/carried, consistent private-phase writes still
commit, and the job row becomes ``budget_exhausted`` (UI-visible).

Post-chain overrun: the chain has already returned, so whatever it
persisted stays; the job is ``budget_exhausted`` rather than
``succeeded`` so the UI does not look like a full-budget success.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal

from digigraph.usage import reset as usage_reset
from digigraph.usage import snapshot as usage_snapshot
from digigraph.usage import start as usage_start
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from digiquant.olympus.overlay.dispatch import JobStatus


class BudgetExhausted(Exception):
    """Hard stop: attributed spend reached ``research_budget_usd``."""

    def __init__(self, *, spent_usd: Decimal, limit_usd: Decimal) -> None:
        self.code = JobStatus.BUDGET_EXHAUSTED.value
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd
        self.message = f"overlay research budget exhausted: spent={spent_usd} limit={limit_usd}"
        super().__init__(self.message)


@contextmanager
def overlay_usage_scope(run_id: str) -> Iterator[None]:
    """Bind WP1 capture to this overlay job and clear it on the way out."""
    usage_start(run_id=run_id)
    try:
        yield
    finally:
        usage_reset()


def attributed_spend_usd(
    snapshot: Callable[[], dict[str, object]] | None = None,
) -> Decimal:
    """Sum attributed USD from WP1 in-process telemetry.

    ``digigraph.usage.snapshot`` is the cost-attribution reader the house
    run already uses (reconciled against ``olympus_provider_attempts``).
    Overlay must not invent a second ledger.
    """
    payload = usage_snapshot() if snapshot is None else snapshot()
    raw = payload.get("cost_usd")
    if raw is None:
        return Decimal("0")
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return Decimal("0")


class OverlayBudget(BaseModel):
    """Per-run budget guard. ``reader`` is injectable for tests."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    limit_usd: Decimal = Field(..., ge=0)
    _reader: Callable[[], Decimal] = PrivateAttr(default=attributed_spend_usd)
    _last_spent: Decimal = PrivateAttr(default=Decimal("0"))

    def __init__(
        self,
        limit_usd: Decimal,
        reader: Callable[[], Decimal] | None = None,
    ) -> None:
        super().__init__(limit_usd=limit_usd)
        if reader is not None:
            object.__setattr__(self, "_reader", reader)

    def spent_usd(self) -> Decimal:
        self._last_spent = self._reader()
        return self._last_spent

    def last_spent_usd(self) -> Decimal:
        return self._last_spent

    def remaining_usd(self) -> Decimal:
        leftover = self.limit_usd - self.spent_usd()
        return leftover if leftover > 0 else Decimal("0")

    def is_exhausted(self) -> bool:
        return self.spent_usd() >= self.limit_usd

    def check(self) -> None:
        """Raise :class:`BudgetExhausted` when the hard stop is crossed."""
        spent = self.spent_usd()
        if spent >= self.limit_usd:
            raise BudgetExhausted(spent_usd=spent, limit_usd=self.limit_usd)


__all__ = [
    "BudgetExhausted",
    "OverlayBudget",
    "attributed_spend_usd",
    "overlay_usage_scope",
]
