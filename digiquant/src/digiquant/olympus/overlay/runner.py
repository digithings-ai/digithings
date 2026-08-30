"""Single overlay run: pin → publish-if-missing corpus → private H7–H9 book.

One graph — wires ``requested_version_id`` + ``workspace_id`` at preflight.
Corpus keys stay tenant-agnostic; private writers read ``config.workspace_id``.
Isolation: overlay exceptions never touch house job rows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.overlay.budget import BudgetExhausted, OverlayBudget
from digiquant.olympus.overlay.byok import (
    ByokProbe,
    ProviderCredential,
    overlay_llm_session,
    probe_byok,
)
from digiquant.olympus.overlay.dispatch import (
    JobRun,
    JobRunStore,
    JobStatus,
    OverlaySkipReason,
)
from digiquant.olympus.research_corpus import (
    CorpusKey,
    ResearchCorpusKeyError,
    ResearchCorpusPin,
    ResearchCorpusStore,
    corpus_pin_version_id,
)
from digiquant.olympus.tenancy import house_workspace_id
from digiquant.vault.envelope import MasterKey

logger = logging.getLogger(__name__)


class OverlayRunRequest(BaseModel):
    """Inputs for one overlay daily run (already entitlement-gated)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    run_date: date
    profile_version_id: UUID
    user_id: UUID | None = None
    research_budget_usd: Decimal | None = Field(default=None, ge=0)
    themes: tuple[str, ...] = ()
    watchlist: tuple[str, ...] = ()


class OverlayRunResult(BaseModel):
    """Visible job outcome — never a silent skip."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    status: JobStatus
    skip_reason: OverlaySkipReason | None = None
    spent_usd: Decimal = Decimal("0")
    published_keys: tuple[str, ...] = ()
    carried_keys: tuple[str, ...] = ()
    house_workspace_untouched: bool = True


class PinSeamConfig(BaseModel):
    """Values threaded through preflight — wire, do not redesign the pin loader."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_config_version_id: str | None = None
    workspace_id: str | None = None


class OverlayError(Exception):
    """Structured overlay refusal (``code`` + ``message``)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


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


def _overlay_pins(
    request: OverlayRunRequest,
) -> list[ResearchCorpusPin]:
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


def _finish_job(
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


def run_overlay(
    *,
    request: OverlayRunRequest,
    job: JobRun,
    store: JobRunStore,
    corpus: ResearchCorpusStore,
    byok_client: object | None = None,
    byok: ByokProbe | None = None,
    credential: ProviderCredential | None = None,
    vault_key: MasterKey | None = None,
    chain: Callable[..., object] | None = None,
    spend_reader: Callable[[], Decimal] | None = None,
    house_job_store: JobRunStore | None = None,
) -> OverlayRunResult:
    """Run one overlay job. ``chain`` is the one-graph invoke (injectable).

    ``house_job_store`` is accepted only so tests can prove it is never written.
    """
    del house_job_store  # isolation: overlay must not touch a house store
    if job.workspace_id == house_workspace_id():
        raise OverlayError("house_workspace", "overlay runner refuses the house workspace id")

    probe = (
        byok
        if byok is not None
        else probe_byok(client=byok_client, workspace_id=request.workspace_id)
    )
    if not probe.present_and_unsealable:
        return _skipped_no_credentials(store, job, request.workspace_id)
    return _execute_overlay(
        request=request,
        job=job,
        store=store,
        corpus=corpus,
        chain=chain,
        credential=credential,
        vault_key=vault_key,
        spend_reader=spend_reader,
    )


def _execute_overlay(
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
    budget = _budget_for(request, spend_reader)
    published: list[str] = []
    carried: list[str] = []
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
    except BudgetExhausted as exc:
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
    except Exception as exc:
        logger.exception("overlay run failed; house job rows untouched")
        _finish_job(store, job, status=JobStatus.FAILED, error=type(exc).__name__)
        return OverlayRunResult(
            workspace_id=request.workspace_id,
            status=JobStatus.FAILED,
            spent_usd=budget.last_spent_usd() if budget is not None else Decimal("0"),
            published_keys=tuple(published),
            carried_keys=tuple(carried),
        )
    return _finish_visible(
        store,
        job,
        request,
        status=JobStatus.SUCCEEDED,
        spent=budget.last_spent_usd() if budget is not None else Decimal("0"),
        published=published,
        carried=carried,
    )


def _budget_for(
    request: OverlayRunRequest,
    spend_reader: Callable[[], Decimal] | None,
) -> OverlayBudget | None:
    if request.research_budget_usd is None:
        return None
    return OverlayBudget(
        limit_usd=request.research_budget_usd,
        reader=spend_reader or (lambda: Decimal("0")),
    )


def _skipped_no_credentials(
    store: JobRunStore, job: JobRun, workspace_id: UUID
) -> OverlayRunResult:
    finished = _finish_job(
        store, job, status=JobStatus.SKIPPED, error=OverlaySkipReason.NO_CREDENTIALS.value
    )
    return OverlayRunResult(
        workspace_id=workspace_id,
        status=finished.status,
        skip_reason=OverlaySkipReason.NO_CREDENTIALS,
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
    _finish_job(store, job, status=status, error=error)
    return OverlayRunResult(
        workspace_id=request.workspace_id,
        status=status,
        spent_usd=spent,
        published_keys=tuple(published),
        carried_keys=tuple(carried),
    )


def _invoke_chain(
    *,
    request: OverlayRunRequest,
    chain: Callable[..., object],
    credential: ProviderCredential | None,
    vault_key: MasterKey | None,
) -> None:
    """One-graph invoke. LLM clients bind only inside the BYOK session."""
    kwargs = {
        "workspace_id": request.workspace_id,
        "run_date": request.run_date,
        "requested_version_id": request.profile_version_id,
    }
    if credential is None:
        # Probe-only path (tests / no unsealed row): never construct a house client.
        chain(**kwargs)
        return
    with overlay_llm_session(credential=credential, key=vault_key):
        chain(**kwargs)


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
    if chain is not None:
        _invoke_chain(request=request, chain=chain, credential=credential, vault_key=vault_key)


def pin_seam_config(
    *,
    requested_version_id: UUID | None,
    workspace_id: UUID | None,
) -> PinSeamConfig:
    """Values threaded through preflight — wire, do not redesign the pin loader."""
    return PinSeamConfig(
        profile_config_version_id=(
            None if requested_version_id is None else str(requested_version_id)
        ),
        workspace_id=None if workspace_id is None else str(workspace_id),
    )


__all__ = [
    "OverlayError",
    "OverlayRunRequest",
    "OverlayRunResult",
    "PinSeamConfig",
    "assert_tenant_agnostic_corpus_key",
    "pin_seam_config",
    "publish_overlay_corpus_pin",
    "run_overlay",
]
