"""Single overlay run: pin → publish-if-missing corpus → private H7–H9 book.

One graph — wires ``requested_version_id`` + ``workspace_id`` at preflight.
Corpus keys stay tenant-agnostic; private writers read ``config.workspace_id``.
Isolation: overlay exceptions never touch house job rows.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from digiquant.olympus.overlay.byok import (
    ByokProbe,
    ProviderCredential,
    load_active_credential,
    probe_byok,
)
from digiquant.olympus.overlay.dispatch import JobRun, JobRunStore
from digiquant.olympus.overlay.execute import (
    assert_tenant_agnostic_corpus_key,
    execute_overlay,
    publish_overlay_corpus_pin,
    skipped_no_credentials,
)
from digiquant.olympus.overlay.models import (
    OverlayError,
    OverlayRunRequest,
    OverlayRunResult,
    PinSeamConfig,
)
from digiquant.olympus.research_corpus import ResearchCorpusStore
from digiquant.olympus.tenancy import house_workspace_id
from digiquant.vault.envelope import MasterKey


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
        return skipped_no_credentials(store, job, request.workspace_id)
    loaded = credential
    if chain is not None and loaded is None:
        loaded = load_active_credential(client=byok_client, workspace_id=request.workspace_id)
    return execute_overlay(
        request=request,
        job=job,
        store=store,
        corpus=corpus,
        chain=chain,
        credential=loaded,
        vault_key=vault_key,
        spend_reader=spend_reader,
    )


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
