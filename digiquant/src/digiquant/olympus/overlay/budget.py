"""Per-run overlay research budget (T4 / D9).

Attributed spend is read from the existing WP1 telemetry snapshot
(``digigraph.usage.snapshot()["cost_usd"]``), which is the in-process
projection of ``olympus_provider_attempts``. Crossing
``ProfileConfig.research_budget_usd`` is a graceful stop: remaining
research is skipped/carried, consistent private-phase writes still
commit, and the job row becomes ``budget_exhausted`` (UI-visible).
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from digigraph.usage import snapshot as usage_snapshot
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
]
