"""Deterministic edit-mode resolution (spec §5.1)."""

from __future__ import annotations

from datetime import date

from digiquant.olympus.edit_mode.config import stale_full_days
from digiquant.olympus.edit_mode.models import ArtifactKey, EditMode, TriageSignal
from digiquant.olympus.edit_mode.prior import PriorLoader


def resolve_edit_mode(
    *,
    artifact_key: ArtifactKey,
    run_date: date,
    prior_loader: PriorLoader,
    triage: TriageSignal | None,
    force_full_rewrite: bool = False,
) -> EditMode:
    """Resolve per-artifact ``full`` | ``edit`` | ``skip`` for *run_date*."""
    if force_full_rewrite:
        return "full"

    prior = prior_loader.load(artifact_key, run_date)
    if prior is None:
        return "full"

    gap_days = (run_date - prior.date).days
    if gap_days > stale_full_days():
        return "full"

    if triage is not None and triage.mode == "quiet":
        return "skip"

    return "edit"
