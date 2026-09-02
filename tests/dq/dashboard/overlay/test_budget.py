"""Budget hard-stop against WP1 telemetry attribution (T4)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

pytest.importorskip("digigraph.usage", reason="digiquant-only CI lane omits full-workspace deps")
from digigraph.usage import record as usage_record
from digigraph.usage import reset as usage_reset
from digigraph.usage import start as usage_start
from digiquant.dashboard.overlay.budget import (
    BudgetExhausted,
    OverlayBudget,
    attributed_spend_usd,
)
from digiquant.dashboard.overlay.byok import ByokProbe
from digiquant.dashboard.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.dashboard.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.dashboard.research_corpus import ResearchCorpusStore
from digiquant.dashboard.tenancy import PlanTier, SubscriptionStatus

from tests.dq.olympus.overlay._sealed import sealed_openai

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
        plan_tier=PlanTier.STUDIO,
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


def test_budget_snapshot_is_run_scoped_not_process_global() -> None:
    """B4: usage.start(run_id=job.id) clears house spend from earlier in-process."""
    usage_start(run_id="house-prior")
    usage_record(kind="chat", model="gpt-4o", cost=9.99)
    try:
        store = MemoryJobRunStore()
        workspace = WorkspaceEntitlement(
            workspace_id=uuid4(),
            plan_tier=PlanTier.STUDIO,
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        claimed = dispatch_overlay_daily(
            store=store,
            workspace=workspace,
            run_date=date(2026, 8, 30),
            byok=ByokProbe(present_and_unsealable=True, provider="openai"),
        )
        result = run_overlay(
            request=OverlayRunRequest(
                workspace_id=workspace.workspace_id,
                run_date=date(2026, 8, 30),
                profile_version_id=uuid4(),
                research_budget_usd=Decimal("1.00"),
                themes=("ai",),
            ),
            job=claimed.job,
            store=store,
            corpus=ResearchCorpusStore(),
            byok=ByokProbe(present_and_unsealable=True, provider="openai"),
        )
        assert result.status is JobStatus.SUCCEEDED
        assert result.spent_usd == Decimal("0")
        assert "theme:ai" in result.published_keys
    finally:
        usage_reset()


def test_budget_checked_after_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    """B5: post-chain overrun → budget_exhausted; corpus already published stays."""
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    spent = Decimal("0")

    def reader() -> Decimal:
        return spent

    def chain(**_kwargs: object) -> None:
        nonlocal spent
        spent = Decimal("5.00")

    store = MemoryJobRunStore()
    workspace = WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=PlanTier.STUDIO,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    claimed = dispatch_overlay_daily(
        store=store,
        workspace=workspace,
        run_date=date(2026, 8, 30),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
    )
    credential, master = sealed_openai(workspace.workspace_id)
    result = run_overlay(
        request=OverlayRunRequest(
            workspace_id=workspace.workspace_id,
            run_date=date(2026, 8, 30),
            profile_version_id=uuid4(),
            research_budget_usd=Decimal("1.00"),
            themes=("ai",),
        ),
        job=claimed.job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
        chain=chain,
        credential=credential,
        vault_key=master,
        spend_reader=reader,
    )
    assert result.status is JobStatus.BUDGET_EXHAUSTED
    assert "theme:ai" in result.published_keys
    finished = store.get_by_idempotency_key(claimed.job.idempotency_key)
    assert finished is not None
    assert finished.status is JobStatus.BUDGET_EXHAUSTED
