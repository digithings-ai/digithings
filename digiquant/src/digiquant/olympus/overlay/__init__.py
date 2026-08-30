"""Overlay pipeline runs (T4) — per-workspace research + private books.

Entitled Custom/Enterprise workspaces get a scheduled overlay of the **one**
Olympus graph (no ``run_type`` fork): ProfileConfig pin → publish-if-missing
into the shared corpus → user-private H7–H9 book under their workspace.
House run state and job rows are never touched by overlay failures.

Re-exports are lazy (PEP 562, same pattern as ``digiquant.brokers``): the house
pipeline imports ``overlay.persist`` via ``atlas.supabase_io`` on every run, and
an eager ``__init__`` would drag ``budget`` → ``digigraph`` and ``byok`` →
``digillm``/``openai`` into the digiquant-only CI lane, which deliberately does
not install those packages. Overlay jobs (which do need them) run with the full
workspace installed.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — PEP 562 lazy re-export shim

_EXPORTS = {
    "BudgetExhausted": "budget",
    "OverlayBudget": "budget",
    "attributed_spend_usd": "budget",
    "BYOK_AAD_PURPOSE": "byok",
    "LLM_PROVIDERS": "byok",
    "ProviderCredential": "byok",
    "overlay_llm_session": "byok",
    "probe_byok": "byok",
    "ENTITLED_TIERS": "dispatch",
    "JOB_TYPE_OVERLAY_DAILY": "dispatch",
    "DispatchResult": "dispatch",
    "JobRun": "dispatch",
    "JobRunStore": "dispatch",
    "JobStatus": "dispatch",
    "MemoryJobRunStore": "dispatch",
    "OverlaySkipReason": "dispatch",
    "SupabaseJobRunStore": "dispatch",
    "dispatch_overlay_daily": "dispatch",
    "overlay_idempotency_key": "dispatch",
    "OverlayError": "runner",
    "OverlayRunRequest": "runner",
    "OverlayRunResult": "runner",
    "PinSeamConfig": "runner",
    "assert_tenant_agnostic_corpus_key": "runner",
    "pin_seam_config": "runner",
    "publish_overlay_corpus_pin": "runner",
    "run_overlay": "runner",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:  # score:allow untyped any
    submodule = _EXPORTS.get(name)
    if submodule is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(f"{__name__}.{submodule}"), name)
