"""Overlay pipeline runs (T4) — per-workspace research + private books.

Entitled Custom/Enterprise workspaces get a scheduled overlay of the **one**
Olympus graph (no ``run_type`` fork): ProfileConfig pin → publish-if-missing
into the shared corpus → user-private H7–H9 book under their workspace.
House run state and job rows are never touched by overlay failures.
"""

from digiquant.olympus.overlay.byok import (
    BYOK_AAD_PURPOSE,
    LLM_PROVIDERS,
    ProviderCredential,
    overlay_llm_session,
    probe_byok,
)
from digiquant.olympus.overlay.dispatch import (
    ENTITLED_TIERS,
    JOB_TYPE_OVERLAY_DAILY,
    DispatchResult,
    JobRun,
    JobRunStore,
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    dispatch_overlay_daily,
    overlay_idempotency_key,
)

__all__ = [
    "BYOK_AAD_PURPOSE",
    "DispatchResult",
    "ENTITLED_TIERS",
    "JOB_TYPE_OVERLAY_DAILY",
    "JobRun",
    "JobRunStore",
    "JobStatus",
    "LLM_PROVIDERS",
    "MemoryJobRunStore",
    "OverlaySkipReason",
    "ProviderCredential",
    "dispatch_overlay_daily",
    "overlay_idempotency_key",
    "overlay_llm_session",
    "probe_byok",
]
