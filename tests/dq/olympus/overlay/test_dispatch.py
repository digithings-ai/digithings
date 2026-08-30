"""Dispatch entitlement + idempotent claim (T4)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JOB_TYPE_OVERLAY_DAILY,
    DispatchResult,
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
    overlay_idempotency_key,
)
from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus

pytestmark = pytest.mark.unit

_RUN = date(2026, 8, 30)


def _ws(
    *,
    tier: PlanTier = PlanTier.CUSTOM,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> WorkspaceEntitlement:
    return WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=tier,
        subscription_status=status,
    )


def _ok_byok() -> ByokProbe:
    return ByokProbe(present_and_unsealable=True, provider="openai", fingerprint="abcd1234")


def _missing_byok() -> ByokProbe:
    return ByokProbe(present_and_unsealable=False, reason="missing")


@pytest.mark.parametrize(
    ("tier", "status"),
    (
        (PlanTier.FREE, SubscriptionStatus.ACTIVE),
        (PlanTier.BASELINE, SubscriptionStatus.ACTIVE),
        (PlanTier.CUSTOM, SubscriptionStatus.NONE),
        (PlanTier.CUSTOM, SubscriptionStatus.PAST_DUE),
        (PlanTier.CUSTOM, SubscriptionStatus.CANCELED),
        (PlanTier.ENTERPRISE, SubscriptionStatus.PAST_DUE),
    ),
)
def test_entitlement_miss_skips_not_entitled(tier: PlanTier, status: SubscriptionStatus) -> None:
    store = MemoryJobRunStore()
    result = dispatch_overlay_daily(
        store=store, workspace=_ws(tier=tier, status=status), run_date=_RUN, byok=_ok_byok()
    )
    assert result.claimed is False
    assert result.skip_reason is OverlaySkipReason.NOT_ENTITLED
    assert result.job.status is JobStatus.SKIPPED
    assert result.job.error == OverlaySkipReason.NOT_ENTITLED.value
    assert result.job.job_type == JOB_TYPE_OVERLAY_DAILY


def test_missing_byok_skips_no_credentials() -> None:
    store = MemoryJobRunStore()
    result = dispatch_overlay_daily(
        store=store,
        workspace=_ws(),
        run_date=_RUN,
        byok=_missing_byok(),
    )
    assert result.claimed is False
    assert result.skip_reason is OverlaySkipReason.NO_CREDENTIALS
    assert result.job.status is JobStatus.SKIPPED
    assert result.job.error == OverlaySkipReason.NO_CREDENTIALS.value


def test_entitled_custom_and_enterprise_claim() -> None:
    for tier in (PlanTier.CUSTOM, PlanTier.ENTERPRISE):
        store = MemoryJobRunStore()
        result = dispatch_overlay_daily(
            store=store, workspace=_ws(tier=tier), run_date=_RUN, byok=_ok_byok()
        )
        assert result.claimed is True
        assert result.skip_reason is None
        assert result.job.status is JobStatus.RUNNING


def test_double_dispatch_same_day_one_run() -> None:
    store = MemoryJobRunStore()
    workspace = _ws()
    first = dispatch_overlay_daily(store=store, workspace=workspace, run_date=_RUN, byok=_ok_byok())
    second = dispatch_overlay_daily(
        store=store, workspace=workspace, run_date=_RUN, byok=_ok_byok()
    )
    assert first.claimed is True
    assert second.claimed is False
    assert second.job.id == first.job.id
    assert overlay_idempotency_key(workspace.workspace_id, _RUN) == first.job.idempotency_key
    assert first.job.idempotency_key == (
        f"{workspace.workspace_id}:{JOB_TYPE_OVERLAY_DAILY}:{_RUN.isoformat()}"
    )


def test_skip_is_visible_never_silent() -> None:
    store = MemoryJobRunStore()
    result: DispatchResult = dispatch_overlay_daily(
        store=store,
        workspace=_ws(tier=PlanTier.FREE),
        run_date=_RUN,
        byok=_ok_byok(),
    )
    stored = store.get_by_idempotency_key(result.job.idempotency_key)
    assert stored is not None
    assert stored.status is JobStatus.SKIPPED
    assert stored.error == "not_entitled"
