"""Dispatch entitlement + idempotent claim (T4)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

pytest.importorskip("digillm.client", reason="digiquant-only CI lane omits full-workspace deps")
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JOB_TYPE_OVERLAY_DAILY,
    DispatchResult,
    JobRun,
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    SupabaseJobRunStore,
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
    plan_floor: PlanTier | None = None,
) -> WorkspaceEntitlement:
    return WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=tier,
        subscription_status=status,
        plan_floor=plan_floor,
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


def test_creator_plan_floor_custom_without_stripe_claims() -> None:
    """D1: entitlement_grants.plan_floor=custom unlocks Kairos overlay without Stripe."""
    store = MemoryJobRunStore()
    result = dispatch_overlay_daily(
        store=store,
        workspace=_ws(
            tier=PlanTier.FREE,
            status=SubscriptionStatus.NONE,
            plan_floor=PlanTier.CUSTOM,
        ),
        run_date=_RUN,
        byok=_ok_byok(),
    )
    assert result.claimed is True
    assert result.skip_reason is None
    assert result.job.status is JobStatus.RUNNING


def test_baseline_plan_floor_without_stripe_skips_overlay() -> None:
    store = MemoryJobRunStore()
    result = dispatch_overlay_daily(
        store=store,
        workspace=_ws(
            tier=PlanTier.FREE,
            status=SubscriptionStatus.NONE,
            plan_floor=PlanTier.BASELINE,
        ),
        run_date=_RUN,
        byok=_ok_byok(),
    )
    assert result.claimed is False
    assert result.skip_reason is OverlaySkipReason.NOT_ENTITLED


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


class _JobQuery:
    """Minimal PostgREST seam for ``SupabaseJobRunStore``."""

    def __init__(self, store: dict[str, dict[str, object]]) -> None:
        self._store = store
        self._filters: list[tuple[str, object]] = []
        self._payload: dict[str, object] | None = None
        self._op = "select"
        self.last_upsert: tuple[dict[str, object], str | None, bool] | None = None

    def select(self, _cols: str) -> _JobQuery:
        self._op = "select"
        return self

    def upsert(
        self,
        row: dict[str, object],
        on_conflict: str | None = None,
        ignore_duplicates: bool = False,
    ) -> _JobQuery:
        self.last_upsert = (dict(row), on_conflict, ignore_duplicates)
        key = str(row["idempotency_key"])
        if ignore_duplicates and key in self._store:
            self._payload = dict(self._store[key])
        else:
            self._store[key] = dict(row)
            self._payload = dict(row)
        self._op = "upsert"
        return self

    def update(self, payload: dict[str, object]) -> _JobQuery:
        self._op = "update"
        self._payload = dict(payload)
        return self

    def eq(self, column: str, value: object) -> _JobQuery:
        self._filters.append((column, value))
        return self

    def limit(self, _n: int) -> _JobQuery:
        return self

    def execute(self) -> object:
        if self._op == "upsert":
            return type("R", (), {"data": [self._payload] if self._payload else []})()
        if self._op == "update":
            updated: list[dict[str, object]] = []
            for row in self._store.values():
                if all(row.get(col) == val for col, val in self._filters):
                    row.update(self._payload or {})
                    updated.append(dict(row))
            return type("R", (), {"data": updated})()
        matched = [
            dict(row)
            for row in self._store.values()
            if all(row.get(col) == val for col, val in self._filters)
        ]
        return type("R", (), {"data": matched})()


class _JobClient:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.last_upsert: tuple[dict[str, object], str | None, bool] | None = None

    def table(self, name: str) -> _JobQuery:
        assert name == "job_runs"
        query = _JobQuery(self.rows)
        original = query.upsert

        def _upsert(
            row: dict[str, object],
            on_conflict: str | None = None,
            ignore_duplicates: bool = False,
        ) -> _JobQuery:
            self.last_upsert = (dict(row), on_conflict, ignore_duplicates)
            return original(row, on_conflict=on_conflict, ignore_duplicates=ignore_duplicates)

        query.upsert = _upsert  # type: ignore[method-assign]
        return query


def test_supabase_job_run_store_insert_conflict_do_nothing() -> None:
    client = _JobClient()
    store = SupabaseJobRunStore(client)
    first = JobRun(
        id=uuid4(),
        workspace_id=uuid4(),
        job_type=JOB_TYPE_OVERLAY_DAILY,
        status=JobStatus.PENDING,
        idempotency_key="ws:overlay_daily:2026-08-30",
    )
    stored = store.insert(first)
    assert stored.id == first.id
    assert client.last_upsert is not None
    _row, on_conflict, ignore = client.last_upsert
    assert on_conflict == "idempotency_key"
    assert ignore is True

    second = first.model_copy(update={"id": uuid4()})
    winner = store.insert(second)
    assert winner.id == first.id
    assert winner.id != second.id


def test_supabase_job_run_store_claim_pending_only() -> None:
    client = _JobClient()
    store = SupabaseJobRunStore(client)
    row = JobRun(
        id=uuid4(),
        workspace_id=uuid4(),
        job_type=JOB_TYPE_OVERLAY_DAILY,
        status=JobStatus.PENDING,
        idempotency_key="ws:overlay_daily:2026-08-30",
    )
    store.insert(row)
    now = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    claimed = store.claim(row.idempotency_key, started_at=now)
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING
    again = store.claim(row.idempotency_key, started_at=now)
    assert again is None


def test_supabase_job_run_store_update_status() -> None:
    client = _JobClient()
    store = SupabaseJobRunStore(client)
    row = JobRun(
        id=uuid4(),
        workspace_id=uuid4(),
        job_type=JOB_TYPE_OVERLAY_DAILY,
        status=JobStatus.RUNNING,
        started_at=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        idempotency_key="ws:overlay_daily:2026-08-30",
    )
    store.insert(row)
    finished = row.model_copy(
        update={
            "status": JobStatus.SUCCEEDED,
            "finished_at": datetime(2026, 8, 30, 12, 5, tzinfo=UTC),
        }
    )
    store.update(finished)
    loaded = store.get_by_idempotency_key(row.idempotency_key)
    assert loaded is not None
    assert loaded.status is JobStatus.SUCCEEDED
