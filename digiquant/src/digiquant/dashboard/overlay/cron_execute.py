"""Execute claimed overlay_daily jobs (T4).

Dispatch-only cron leaves rows ``running``. ``--execute`` runs the one Olympus
graph. ``chain=None`` is forbidden: ``execute_overlay`` would mark
``succeeded`` without a book. This module does not import ``byok`` / digillm.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID

from digiquant.dashboard.overlay.dispatch import (
    JobRun,
    JobRunStore,
    JobStatus,
    overlay_idempotency_key,
)
from digiquant.dashboard.overlay.models import OverlayError, OverlayRunRequest
from digiquant.dashboard.overlay.persist import OVERLAY_PERSIST_ENV, overlay_persist_enabled
from digiquant.vault.envelope import MASTER_KEY_ENV

PROFILE_PIN_MISSING = "profile_pin_missing"
OVERLAY_EXECUTE_NOT_CONFIGURED = "OVERLAY_EXECUTE_NOT_CONFIGURED"


class OverlayExecuteRequiresChain(OverlayError):
    """``--execute`` must pass a graph; ``chain=None`` is a fake success path."""

    def __init__(self) -> None:
        super().__init__(
            "chain_required",
            "overlay cron --execute requires a graph; chain=None is forbidden",
        )


class OverlayChainFactory(Protocol):
    """Builds the one-graph invoke for a claimed job (injectable in tests)."""

    def __call__(
        self,
        *,
        job: JobRun,
        profile_version_id: UUID,
        run_date: date,
    ) -> Callable[..., object] | None: ...


class OverlayRunner(Protocol):
    """Runs a claimed overlay job. Tests inject this so cron never imports runner."""

    def __call__(
        self,
        *,
        job: JobRun,
        store: JobRunStore,
        request: OverlayRunRequest,
        chain: Callable[..., object],
    ) -> object: ...


def require_overlay_chain(
    chain: Callable[..., object] | None,
) -> Callable[..., object]:
    """Refuse the ``execute_overlay(chain=None)`` success-without-book path."""
    if chain is None:
        raise OverlayExecuteRequiresChain()
    return chain


def parse_overlay_profile_pin(row: dict[str, object]) -> UUID | None:
    """Parse a tip ``olympus_profile_config.id``. Invalid rows skipped."""
    raw = row.get("id")
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def load_overlay_profile_version_id(client: object, workspace_id: UUID) -> UUID | None:
    """Latest non-house overlay profile pin for the workspace, or None."""
    result = (
        client.table("olympus_profile_config")
        .select("id")
        .eq("workspace_id", str(workspace_id))
        .eq("is_house_default", False)
        .order("recorded_at", desc=True)
        .limit(1)
        .execute()
    )
    data = getattr(result, "data", result)
    if not isinstance(data, list) or not data:
        return None
    row = data[0]
    if not isinstance(row, dict):
        return None
    return parse_overlay_profile_pin(row)


def fail_running_job(store: JobRunStore, job: JobRun, error: str) -> JobRun:
    """Mark a claimed job failed with a visible error (never succeeded)."""
    finished = job.model_copy(
        update={
            "status": JobStatus.FAILED,
            "finished_at": datetime.now(tz=UTC),
            "error": error,
        }
    )
    return store.update(finished)


def missing_overlay_execute_env_names(
    environ: Mapping[str, str] | None = None,
    *,
    store_missing: list[str] | None = None,
) -> list[str]:
    """Store + vault + persist names required to execute. Never returns values."""
    env = os.environ if environ is None else environ
    missing = list(store_missing or [])
    if not (env.get(MASTER_KEY_ENV) or "").strip():
        missing.append(MASTER_KEY_ENV)
    if not overlay_persist_enabled(env):
        missing.append(OVERLAY_PERSIST_ENV)
    return missing


def format_overlay_execute_not_configured(missing: list[str]) -> str:
    return OVERLAY_EXECUTE_NOT_CONFIGURED + ": " + ", ".join(missing)


def production_chain_factory(
    *,
    job: JobRun,
    profile_version_id: UUID,
    run_date: date,
) -> Callable[..., object]:
    """Lazy-import the real Olympus graph. Never returns None."""
    del run_date
    # Dependency-isolation: graph_invoke pulls hermes/atlas; digiquant-only CI omits digillm.
    from digiquant.dashboard.overlay.graph_invoke import build_overlay_chain

    return build_overlay_chain(
        workspace_id=job.workspace_id,
        profile_version_id=profile_version_id,
    )


def production_overlay_runner(
    *,
    job: JobRun,
    store: JobRunStore,
    request: OverlayRunRequest,
    chain: Callable[..., object],
    byok_client: object | None = None,
) -> object:
    """Lazy-import ``run_overlay``. House env keys are not a BYOK fallback."""
    # Dependency-isolation: runner pulls byok/digillm; digiquant-only CI omits them.
    from digiquant.dashboard.overlay.runner import run_overlay
    from digiquant.dashboard.research_corpus import ResearchCorpusStore
    from digiquant.vault.envelope import load_master_key

    return run_overlay(
        request=request,
        job=job,
        store=store,
        corpus=ResearchCorpusStore(),
        chain=chain,
        byok_client=byok_client,
        vault_key=load_master_key(),
    )


def execute_claimed_overlay(
    *,
    job: JobRun,
    store: JobRunStore,
    run_date: date,
    profile_version_id: UUID | None,
    chain_factory: OverlayChainFactory | None = None,
    overlay_runner: OverlayRunner | None = None,
    byok_client: object | None = None,
) -> JobRun:
    """Run one claimed job. Missing pin fails closed; ``chain=None`` raises."""
    if profile_version_id is None:
        return fail_running_job(store, job, PROFILE_PIN_MISSING)
    factory = chain_factory or production_chain_factory
    chain = require_overlay_chain(
        factory(job=job, profile_version_id=profile_version_id, run_date=run_date)
    )
    request = OverlayRunRequest(
        workspace_id=job.workspace_id,
        run_date=run_date,
        profile_version_id=profile_version_id,
    )
    if overlay_runner is None:
        production_overlay_runner(
            job=job,
            store=store,
            request=request,
            chain=chain,
            byok_client=byok_client,
        )
    else:
        overlay_runner(job=job, store=store, request=request, chain=chain)
    latest = store.get_by_idempotency_key(job.idempotency_key)
    return latest if latest is not None else job


def resolve_overlay_profile_pin(
    workspace_id: UUID,
    *,
    profile_pins: Mapping[UUID, UUID] | None,
    load_profile_pin: Callable[[UUID], UUID | None] | None,
    client: object | None,
) -> UUID | None:
    """Prefer injected pins, then a loader, then a live profile-config select."""
    if profile_pins is not None:
        return profile_pins.get(workspace_id)
    if load_profile_pin is not None:
        return load_profile_pin(workspace_id)
    if client is None:
        return None
    return load_overlay_profile_version_id(client, workspace_id)


def execute_claimed_rows(
    *,
    claimed_workspace_ids: Sequence[UUID],
    store: JobRunStore,
    run_date: date,
    profile_pins: Mapping[UUID, UUID] | None,
    load_profile_pin: Callable[[UUID], UUID | None] | None,
    chain_factory: OverlayChainFactory | None,
    overlay_runner: OverlayRunner | None,
    client: object | None,
    log_err: Callable[[str], None],
) -> int:
    """Execute claimed overlay_daily rows. Missing pin / chain=None fail closed.

    One row's exception does not abort the batch; that job is marked failed
    with a visible error (type name only — no exception payload).
    """
    rc = 0
    for workspace_id in claimed_workspace_ids:
        job = store.get_by_idempotency_key(overlay_idempotency_key(workspace_id, run_date))
        if job is None or job.status is not JobStatus.RUNNING:
            continue
        try:
            pin = resolve_overlay_profile_pin(
                workspace_id,
                profile_pins=profile_pins,
                load_profile_pin=load_profile_pin,
                client=client,
            )
            execute_claimed_overlay(
                job=job,
                store=store,
                run_date=run_date,
                profile_version_id=pin,
                chain_factory=chain_factory,
                overlay_runner=overlay_runner,
                byok_client=client,
            )
        except OverlayError as exc:
            fail_running_job(store, job, exc.code)
            log_err(exc.message)
            rc = 3
        except Exception as exc:
            fail_running_job(store, job, type(exc).__name__)
            log_err(f"overlay execute failed workspace_id={workspace_id}: {type(exc).__name__}")
            rc = 3
    return rc


__all__ = [
    "OVERLAY_EXECUTE_NOT_CONFIGURED",
    "PROFILE_PIN_MISSING",
    "OverlayChainFactory",
    "OverlayExecuteRequiresChain",
    "OverlayRunner",
    "execute_claimed_overlay",
    "execute_claimed_rows",
    "fail_running_job",
    "format_overlay_execute_not_configured",
    "load_overlay_profile_version_id",
    "missing_overlay_execute_env_names",
    "parse_overlay_profile_pin",
    "production_chain_factory",
    "production_overlay_runner",
    "require_overlay_chain",
    "resolve_overlay_profile_pin",
]
