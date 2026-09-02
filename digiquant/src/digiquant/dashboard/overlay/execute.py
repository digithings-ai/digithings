"""Corpus + private-phase execute path for one overlay job."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from digiquant.dashboard.overlay.budget import (
    BudgetExhausted,
    OverlayBudget,
    attributed_spend_usd,
    overlay_usage_scope,
)
from digiquant.dashboard.overlay.byok import (
    ByokError,
    ProviderCredential,
    invoke_overlay_chain,
)
from digiquant.dashboard.overlay.dispatch import (
    JobRun,
    JobRunStore,
    JobStatus,
    OverlaySkipReason,
)
from digiquant.dashboard.overlay.models import OverlayRunRequest, OverlayRunResult
from digiquant.dashboard.overlay.persist import (
    OverlayLegacyBookBlocked,
    OverlayPersistDisabled,
    require_overlay_legacy_book_safe,
    require_overlay_persist,
)
from digiquant.dashboard.research_corpus import (
    CorpusKey,
    ResearchCorpusKeyError,
    ResearchCorpusPin,
    ResearchCorpusStore,
    corpus_pin_version_id,
)
from digiquant.vault.envelope import MasterKey

logger = logging.getLogger(__name__)


def assert_tenant_agnostic_corpus_key(
    key: str,
    *,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> CorpusKey:
    """Write-time assertion: reject keys that embed workspace or user ids."""
    parsed = CorpusKey.parse(key)
    blob = parsed.key.lower()
    forbidden = [str(workspace_id).lower()]
    if user_id is not None:
        forbidden.append(str(user_id).lower())
    for marker in forbidden:
        if marker and marker in blob:
            raise ResearchCorpusKeyError(
                f"corpus key must not contain workspace/user id ({marker})"
            )
    return parsed


def publish_overlay_corpus_pin(
    store: ResearchCorpusStore,
    pin: ResearchCorpusPin,
    *,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> tuple[ResearchCorpusPin, bool]:
    """Publish-if-missing after the write-time assertion.

    Returns ``(pin, wrote)`` — ``wrote`` is False when the key already existed.
    """
    assert_tenant_agnostic_corpus_key(pin.corpus_key, workspace_id=workspace_id, user_id=user_id)
    existing = store.get_by_key(pin.corpus_key)
    published = store.publish_if_missing(pin, allow_overlay=True)
    return published, existing is None


def execute_overlay(
    *,
    request: OverlayRunRequest,
    job: JobRun,
    store: JobRunStore,
    corpus: ResearchCorpusStore,
    chain: Callable[..., object] | None,
    credential: ProviderCredential | None,
    vault_key: MasterKey | None,
    spend_reader: Callable[[], Decimal] | None,
) -> OverlayRunResult:
    """Run corpus then chain under a run-scoped usage capture."""
    budget = _budget_for(request, spend_reader)
    published: list[str] = []
    carried: list[str] = []
    with overlay_usage_scope(str(job.id)):
        try:
            _run_corpus_and_chain(
                request=request,
                corpus=corpus,
                budget=budget,
                chain=chain,
                credential=credential,
                vault_key=vault_key,
                published=published,
                carried=carried,
            )
        except Exception as exc:
            mapped = _map_execute_error(exc, store, job, request, budget, published, carried)
            if mapped is not None:
                return mapped
            raise
    return _finish_visible(
        store,
        job,
        request,
        status=JobStatus.SUCCEEDED,
        spent=_spent(budget),
        published=published,
        carried=carried,
    )


def _failed_result(
    store: JobRunStore,
    job: JobRun,
    request: OverlayRunRequest,
    budget: OverlayBudget | None,
    published: list[str],
    carried: list[str],
    error: str,
) -> OverlayRunResult:
    finish_job(store, job, status=JobStatus.FAILED, error=error)
    return OverlayRunResult(
        workspace_id=request.workspace_id,
        status=JobStatus.FAILED,
        spent_usd=_spent(budget),
        published_keys=tuple(published),
        carried_keys=tuple(carried),
    )


def _map_execute_error(
    exc: Exception,
    store: JobRunStore,
    job: JobRun,
    request: OverlayRunRequest,
    budget: OverlayBudget | None,
    published: list[str],
    carried: list[str],
) -> OverlayRunResult | None:
    if isinstance(exc, OverlayPersistDisabled):
        return _finish_visible(
            store,
            job,
            request,
            status=JobStatus.PERSIST_DISABLED,
            spent=_spent(budget),
            published=published,
            carried=carried,
            error=exc.code,
        )
    if isinstance(exc, OverlayLegacyBookBlocked):
        # Stable error code (not the exception type name) so staging hops and
        # operators can tell P6 is still required — not a transient graph failure.
        return _failed_result(store, job, request, budget, published, carried, exc.code)
    if isinstance(exc, ByokError):
        if exc.code == OverlaySkipReason.NO_CREDENTIALS.value:
            return skipped_no_credentials(store, job, request.workspace_id)
        logger.exception("overlay BYOK refuse; house job rows untouched")
        return _failed_result(store, job, request, budget, published, carried, exc.code)
    if isinstance(exc, BudgetExhausted):
        return _finish_visible(
            store,
            job,
            request,
            status=JobStatus.BUDGET_EXHAUSTED,
            spent=exc.spent_usd,
            published=published,
            carried=carried,
            error=JobStatus.BUDGET_EXHAUSTED.value,
        )
    logger.exception("overlay run failed; house job rows untouched")
    return _failed_result(store, job, request, budget, published, carried, type(exc).__name__)


def skipped_no_credentials(store: JobRunStore, job: JobRun, workspace_id: UUID) -> OverlayRunResult:
    finished = finish_job(
        store, job, status=JobStatus.SKIPPED, error=OverlaySkipReason.NO_CREDENTIALS.value
    )
    return OverlayRunResult(
        workspace_id=workspace_id,
        status=finished.status,
        skip_reason=OverlaySkipReason.NO_CREDENTIALS,
    )


def finish_job(
    store: JobRunStore,
    job: JobRun,
    *,
    status: JobStatus,
    error: str | None = None,
) -> JobRun:
    finished = job.model_copy(
        update={
            "status": status,
            "finished_at": datetime.now(tz=UTC),
            "error": error,
        }
    )
    return store.update(finished)


def _spent(budget: OverlayBudget | None) -> Decimal:
    return budget.last_spent_usd() if budget is not None else Decimal("0")


def _budget_for(
    request: OverlayRunRequest,
    spend_reader: Callable[[], Decimal] | None,
) -> OverlayBudget | None:
    if request.research_budget_usd is None:
        return None
    return OverlayBudget(
        limit_usd=request.research_budget_usd,
        reader=spend_reader or attributed_spend_usd,
    )


def _finish_visible(
    store: JobRunStore,
    job: JobRun,
    request: OverlayRunRequest,
    *,
    status: JobStatus,
    spent: Decimal,
    published: list[str],
    carried: list[str],
    error: str | None = None,
) -> OverlayRunResult:
    if status is JobStatus.BUDGET_EXHAUSTED:
        logger.info(
            "overlay budget exhausted workspace_id=%s run_date=%s",
            request.workspace_id,
            request.run_date,
        )
    finish_job(store, job, status=status, error=error)
    return OverlayRunResult(
        workspace_id=request.workspace_id,
        status=status,
        spent_usd=spent,
        published_keys=tuple(published),
        carried_keys=tuple(carried),
    )


def _overlay_pins(request: OverlayRunRequest) -> list[ResearchCorpusPin]:
    pins: list[ResearchCorpusPin] = []
    for theme in request.themes:
        key = f"theme:{theme.strip().lower()}"
        pins.append(
            ResearchCorpusPin(
                version_id=corpus_pin_version_id(key),
                corpus_key=key,
                writer_role="overlay_request",
                label=theme,
            )
        )
    for ticker in request.watchlist:
        key = f"asset:{ticker.strip().lower()}"
        pins.append(
            ResearchCorpusPin(
                version_id=corpus_pin_version_id(key),
                corpus_key=key,
                writer_role="overlay_request",
                label=ticker,
            )
        )
    return pins


def _run_corpus_and_chain(
    *,
    request: OverlayRunRequest,
    corpus: ResearchCorpusStore,
    budget: OverlayBudget | None,
    chain: Callable[..., object] | None,
    credential: ProviderCredential | None,
    vault_key: MasterKey | None,
    published: list[str],
    carried: list[str],
) -> None:
    remaining: Sequence[ResearchCorpusPin] = _overlay_pins(request)
    for pin in remaining:
        if budget is not None:
            budget.check()
        _, wrote = publish_overlay_corpus_pin(
            corpus,
            pin,
            workspace_id=request.workspace_id,
            user_id=request.user_id,
        )
        if wrote:
            published.append(pin.corpus_key)
        else:
            carried.append(pin.corpus_key)
    if budget is not None:
        budget.check()
    if chain is None:
        return
    require_overlay_persist(request.workspace_id)
    invoke_overlay_chain(
        chain=chain,
        credential=credential,
        vault_key=vault_key,
        workspace_id=request.workspace_id,
        run_date=request.run_date,
        requested_version_id=request.profile_version_id,
    )
    if budget is not None:
        budget.check()
    # Documents may already have persisted. Private books stay refused until
    # staged cutover 113 lifts this gate — the job must not finish succeeded
    # (remaining hop overlay_daily_claimed) on a documents-only / fail-soft H9 path.
    require_overlay_legacy_book_safe(request.workspace_id)
