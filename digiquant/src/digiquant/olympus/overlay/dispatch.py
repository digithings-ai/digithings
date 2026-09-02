"""Overlay job dispatch: entitlement gate + idempotent ``job_runs`` claim (T4 / P7).

Binding behavior
----------------
1. Entitlement: (paid Studio/Enterprise with ``subscription_status = active``)
   **or** D1 ``entitlement_grants.plan_floor ∈ {studio, enterprise}`` (creator/ops
   without Stripe), **and** BYOK present-and-unsealable. Otherwise a ``job_runs``
   row is written ``skipped`` with ``error`` = ``not_entitled`` / ``no_credentials``
   — visible, never silent.
2. Idempotent claim: ``idempotency_key = f"{workspace_id}:overlay_daily:{run_date}"``.
   Insert-first on that unique key; claim is ``FOR UPDATE SKIP LOCKED``-style
   (in-memory store serializes the same "first claimer wins" rule). A second
   dispatch for the same day returns the existing row and does not start a
   second run.

Isolation: this module never reads or writes a house-run job row. Overlay
failures stay on the overlay ``JobRunStore`` the caller injected.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus

if TYPE_CHECKING:
    from digiquant.olympus.overlay.byok import ByokProbe

JOB_TYPE_OVERLAY_DAILY = "overlay_daily"
ENTITLED_TIERS: frozenset[str] = frozenset({PlanTier.STUDIO.value, PlanTier.ENTERPRISE.value})


class OverlaySkipReason(StrEnum):
    """Closed vocabulary written to ``job_runs.error`` when status is ``skipped``."""

    NOT_ENTITLED = "not_entitled"
    NO_CREDENTIALS = "no_credentials"


class JobStatus(StrEnum):
    """``job_runs.status`` after migration 104's CHECK extension."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PERSIST_DISABLED = "persist_disabled"


class JobRun(BaseModel):
    """One ``job_runs`` row (T0 schema + T4 status vocabulary)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    workspace_id: UUID
    job_type: str = Field(..., min_length=1, max_length=100)
    status: JobStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    idempotency_key: str = Field(..., min_length=1)


class DispatchResult(BaseModel):
    """Outcome of one ``dispatch_overlay_daily`` call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job: JobRun
    claimed: bool
    skip_reason: OverlaySkipReason | None = None


class JobRunStore(Protocol):
    """Injectable ``job_runs`` seam. Tests use :class:`MemoryJobRunStore`."""

    def get_by_idempotency_key(self, key: str) -> JobRun | None: ...
    def insert(self, row: JobRun) -> JobRun: ...
    def claim(self, key: str, *, started_at: datetime) -> JobRun | None: ...
    def update(self, row: JobRun) -> JobRun: ...


class MemoryJobRunStore:
    """Process-local store implementing insert-first + skip-locked claim.

    ``claim`` returns ``None`` when the row is missing or already past
    ``pending`` (another worker holds it, or it already finished). Concurrent
    claims on the same key serialize on ``_lock`` — the in-memory equivalent of
    ``SELECT … FOR UPDATE SKIP LOCKED``.
    """

    def __init__(self) -> None:
        self._rows: dict[str, JobRun] = {}
        self._lock = threading.Lock()

    def get_by_idempotency_key(self, key: str) -> JobRun | None:
        with self._lock:
            return self._rows.get(key)

    def insert(self, row: JobRun) -> JobRun:
        with self._lock:
            existing = self._rows.get(row.idempotency_key)
            if existing is not None:
                return existing
            self._rows[row.idempotency_key] = row
            return row

    def claim(self, key: str, *, started_at: datetime) -> JobRun | None:
        with self._lock:
            current = self._rows.get(key)
            if current is None or current.status is not JobStatus.PENDING:
                return None
            claimed = current.model_copy(
                update={"status": JobStatus.RUNNING, "started_at": started_at}
            )
            self._rows[key] = claimed
            return claimed

    def update(self, row: JobRun) -> JobRun:
        with self._lock:
            self._rows[row.idempotency_key] = row
            return row


def _parse_dt(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _job_payload(row: JobRun) -> dict[str, object]:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "job_type": row.job_type,
        "status": row.status.value,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error": row.error,
        "idempotency_key": row.idempotency_key,
    }


def _row_to_job(row: dict[str, object]) -> JobRun:
    return JobRun(
        id=UUID(str(row["id"])),
        workspace_id=UUID(str(row["workspace_id"])),
        job_type=str(row["job_type"]),
        status=JobStatus(str(row["status"])),
        started_at=_parse_dt(row.get("started_at")),
        finished_at=_parse_dt(row.get("finished_at")),
        error=str(row["error"]) if row.get("error") is not None else None,
        idempotency_key=str(row["idempotency_key"]),
    )


def _result_rows(result: object) -> list[dict[str, object]]:
    data = getattr(result, "data", result)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


class SupabaseJobRunStore:
    """PostgREST ``job_runs`` store: insert-first claim + status updates.

    ``insert`` is ``INSERT … ON CONFLICT (idempotency_key) DO NOTHING`` via
    ``upsert(..., ignore_duplicates=True)``. The winner is the first row;
    a later caller reads that row and does not start a second run.
    """

    def __init__(self, client: object) -> None:
        self._client = client

    def get_by_idempotency_key(self, key: str) -> JobRun | None:
        result = (
            self._client.table("job_runs")
            .select("id,workspace_id,job_type,status,started_at,finished_at,error,idempotency_key")
            .eq("idempotency_key", key)
            .limit(1)
            .execute()
        )
        rows = _result_rows(result)
        return _row_to_job(rows[0]) if rows else None

    def insert(self, row: JobRun) -> JobRun:
        self._client.table("job_runs").upsert(
            _job_payload(row),
            on_conflict="idempotency_key",
            ignore_duplicates=True,
        ).execute()
        stored = self.get_by_idempotency_key(row.idempotency_key)
        return stored if stored is not None else row

    def claim(self, key: str, *, started_at: datetime) -> JobRun | None:
        result = (
            self._client.table("job_runs")
            .update({"status": JobStatus.RUNNING.value, "started_at": started_at.isoformat()})
            .eq("idempotency_key", key)
            .eq("status", JobStatus.PENDING.value)
            .execute()
        )
        rows = _result_rows(result)
        return _row_to_job(rows[0]) if rows else None

    def update(self, row: JobRun) -> JobRun:
        self._client.table("job_runs").update(
            {
                "status": row.status.value,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "error": row.error,
            }
        ).eq("idempotency_key", row.idempotency_key).execute()
        return row


class WorkspaceEntitlement(BaseModel):
    """Billing columns dispatch reads — no Stripe writes.

    ``plan_floor`` is the owner's ``entitlement_grants`` row (D1 creator/ops), or
    ``None`` when the workspace has no grant. Paying customers keep
    ``workspaces.plan_tier`` + ``subscription_status`` as the Stripe path.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    plan_tier: PlanTier
    subscription_status: SubscriptionStatus
    plan_floor: PlanTier | None = None


def overlay_idempotency_key(workspace_id: UUID, run_date: date) -> str:
    """``f"{workspace_id}:overlay_daily:{run_date}"`` — unique per workspace-day."""
    return f"{workspace_id}:{JOB_TYPE_OVERLAY_DAILY}:{run_date.isoformat()}"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def overlay_billing_entitled(workspace: WorkspaceEntitlement) -> bool:
    """Paid Studio/Enterprise (Stripe active) or D1 studio+ ops grant (no Stripe)."""
    paid = (
        workspace.plan_tier.value in ENTITLED_TIERS
        and workspace.subscription_status is SubscriptionStatus.ACTIVE
    )
    grant = workspace.plan_floor is not None and workspace.plan_floor.value in ENTITLED_TIERS
    return paid or grant


def evaluate_entitlement(
    workspace: WorkspaceEntitlement,
    byok: ByokProbe,
) -> OverlaySkipReason | None:
    """Return a skip reason, or ``None`` when the workspace may run."""
    if not overlay_billing_entitled(workspace):
        return OverlaySkipReason.NOT_ENTITLED
    if not byok.present_and_unsealable:
        return OverlaySkipReason.NO_CREDENTIALS
    return None


def _skip_row(
    *,
    workspace_id: UUID,
    run_date: date,
    reason: OverlaySkipReason,
    now: datetime,
) -> JobRun:
    return JobRun(
        id=uuid4(),
        workspace_id=workspace_id,
        job_type=JOB_TYPE_OVERLAY_DAILY,
        status=JobStatus.SKIPPED,
        started_at=now,
        finished_at=now,
        error=reason.value,
        idempotency_key=overlay_idempotency_key(workspace_id, run_date),
    )


def dispatch_overlay_daily(
    *,
    store: JobRunStore,
    workspace: WorkspaceEntitlement,
    run_date: date,
    byok_client: object | None = None,
    byok: ByokProbe | None = None,
) -> DispatchResult:
    """Entitlement-gate + idempotent claim for one overlay daily job.

    ``byok`` is injectable so tests do not need a vault; production passes a
    Supabase client via ``byok_client`` and lets :func:`probe_byok` unseal.
    """
    key = overlay_idempotency_key(workspace.workspace_id, run_date)
    existing = store.get_by_idempotency_key(key)
    if existing is not None and existing.status is not JobStatus.PENDING:
        return DispatchResult(job=existing, claimed=False)

    if byok is not None:
        probe = byok
    else:
        # Dependency-isolation exception to the no-inline-imports rule: byok pulls
        # digillm/openai, which the digiquant-only CI lane deliberately omits.
        from digiquant.olympus.overlay.byok import probe_byok

        probe = probe_byok(client=byok_client, workspace_id=workspace.workspace_id)
    reason = evaluate_entitlement(workspace, probe)
    now = _now()
    if reason is not None:
        skipped = _skip_row(
            workspace_id=workspace.workspace_id,
            run_date=run_date,
            reason=reason,
            now=now,
        )
        stored = store.insert(skipped)
        if stored.id != skipped.id:
            return DispatchResult(job=stored, claimed=False)
        return DispatchResult(job=stored, claimed=False, skip_reason=reason)

    pending = JobRun(
        id=uuid4(),
        workspace_id=workspace.workspace_id,
        job_type=JOB_TYPE_OVERLAY_DAILY,
        status=JobStatus.PENDING,
        idempotency_key=key,
    )
    stored = store.insert(pending)
    claimed = store.claim(key, started_at=now)
    if claimed is None:
        latest = store.get_by_idempotency_key(key)
        assert latest is not None
        return DispatchResult(job=latest, claimed=False)
    return DispatchResult(job=claimed, claimed=True)


__all__ = [
    "ENTITLED_TIERS",
    "JOB_TYPE_OVERLAY_DAILY",
    "DispatchResult",
    "JobRun",
    "JobRunStore",
    "JobStatus",
    "MemoryJobRunStore",
    "OverlaySkipReason",
    "SupabaseJobRunStore",
    "WorkspaceEntitlement",
    "dispatch_overlay_daily",
    "evaluate_entitlement",
    "overlay_billing_entitled",
    "overlay_idempotency_key",
]
