"""Budget hard-stop against WP1 telemetry attribution (T4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from digiquant.olympus.overlay.budget import (
    BudgetExhausted,
    OverlayBudget,
    attributed_spend_usd,
)
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.olympus.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.olympus.research_corpus import ResearchCorpusStore
from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus

pytestmark = pytest.mark.unit


def test_attributed_spend_reads_usage_snapshot() -> None:
    spent = attributed_spend_usd(snapshot=lambda: {"cost_usd": 1.25})
    assert spent == Decimal("1.25")


def test_budget_check_raises_when_crossed() -> None:
    budget = OverlayBudget(limit_usd=Decimal("1.00"), reader=lambda: Decimal("1.00"))
    with pytest.raises(BudgetExhausted) as exc:
        budget.check()
    assert exc.value.code == JobStatus.BUDGET_EXHAUSTED.value
    assert exc.value.spent_usd == Decimal("1.00")


def test_budget_hard_stop_mid_run_carries_remaining() -> None:
    """Mock telemetry crossing the limit after the first corpus publish."""
    costs = iter([Decimal("0.40"), Decimal("1.10")])

    def reader() -> Decimal:
        return next(costs)

    store = MemoryJobRunStore()
    workspace = WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=PlanTier.CUSTOM,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    claimed = dispatch_overlay_daily(
        store=store,
        workspace=workspace,
        run_date=date(2026, 8, 30),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
    )
    request = OverlayRunRequest(
        workspace_id=workspace.workspace_id,
        run_date=date(2026, 8, 30),
        profile_version_id=uuid4(),
        research_budget_usd=Decimal("1.00"),
        themes=("ai", "energy"),
    )
    result = run_overlay(
        request=request,
        job=claimed.job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
        spend_reader=reader,
    )
    assert result.status is JobStatus.BUDGET_EXHAUSTED
    assert result.published_keys == ("theme:ai",)
    assert "theme:energy" not in result.published_keys
    finished = store.get_by_idempotency_key(claimed.job.idempotency_key)
    assert finished is not None
    assert finished.status is JobStatus.BUDGET_EXHAUSTED
    assert finished.error == JobStatus.BUDGET_EXHAUSTED.value
