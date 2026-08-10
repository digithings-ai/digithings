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

    # Measure staleness from the last date the content materially CHANGED, not the last date
    # a row was written (#1749). A no-op republish writes a fresh ``documents`` row, and
    # ``prior.date`` is the newest row for the key — so before this the gap was 1 on every
    # run of a frozen chain and §5.3.2's hard cap could never fire. ``content_date`` is None
    # for any row without an ``unchanged_since`` marker, which keeps the pre-existing
    # behaviour for rows published before the marker shipped.
    #
    # This is NOT the verbatim guard §5.3.1 rejects: the trigger is still purely the elapsed
    # day count against ``stale_full_days()``, unchanged. Only what "elapsed since" means is
    # corrected. See :mod:`digiquant.olympus.edit_mode.content_identity`.
    content_date = prior.content_date or prior.date
    gap_days = (run_date - content_date).days
    if gap_days > stale_full_days():
        return "full"

    if triage is not None and triage.mode == "quiet":
        return "skip"

    return "edit"
