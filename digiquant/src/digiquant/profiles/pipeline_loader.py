"""Load and pin PipelineProfile / ProfileConfig at Atlas preflight (#2607).

Shadow/off by default: overlays never cancel or replace the digithings house
run. Missing / invalid DB rows fall back to the in-code house baseline.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Protocol

from pydantic import ValidationError

from digiquant.profiles.pipeline_profile import (
    HOUSE_PROFILE_ID,
    HOUSE_RUN_ID,
    PinnedPipelineProfile,
    PipelineProfile,
    PipelineProfileMode,
    ProfileConfig,
    default_house_profile,
)

logger = logging.getLogger(__name__)

TABLE = "olympus_pipeline_profiles"
ENV_MODE = "OLYMPUS_PIPELINE_PROFILE_MODE"
ENV_OVERLAY_ID = "OLYMPUS_PIPELINE_PROFILE_OVERLAY_ID"

_READ_ERRORS = (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError)


class _SupabaseClient(Protocol):
    def table(self, name: str) -> Any: ...


def resolve_pipeline_profile_mode(raw: str | None = None) -> PipelineProfileMode:
    """Return ``off`` | ``shadow`` | ``active``. Default ``off`` (no behavior change)."""
    value = (raw if raw is not None else os.environ.get(ENV_MODE, "")).strip().lower()
    if value in ("shadow", "active", "off"):
        return value  # type: ignore[return-value]
    return "off"


def row_to_pipeline_profile(row: dict[str, Any]) -> PipelineProfile:
    """Validate a DB row into ``PipelineProfile`` (no raw dicts downstream)."""
    config_raw = row.get("config")
    if not isinstance(config_raw, dict):
        raise ValueError("pipeline profile row missing config object")
    return PipelineProfile(
        schema_version=int(row.get("schema_version") or 1),
        profile_id=str(row["profile_id"]),
        kind=row["kind"],  # validated by PipelineProfile
        display_name=str(row.get("display_name") or row["profile_id"]),
        config=ProfileConfig.model_validate(config_raw),
        house_run_id=str(row.get("house_run_id") or HOUSE_RUN_ID),
        always_on=bool(row.get("always_on", row.get("kind") == "house")),
        cancel_house_run=False,
    )


def fetch_pipeline_profile_row(
    client: _SupabaseClient,
    profile_id: str,
) -> dict[str, Any] | None:
    """SELECT one enabled profile row; ``None`` if missing."""
    resp = (
        client.table(TABLE)
        .select("*")
        .eq("profile_id", profile_id)
        .eq("enabled", True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    row = rows[0]
    return row if isinstance(row, dict) else None


def load_pipeline_profile(
    client: _SupabaseClient | None,
    profile_id: str,
    *,
    fallback_house: bool = False,
) -> PipelineProfile | None:
    """Load a profile from DB. House miss → in-code baseline when ``fallback_house``."""
    if client is None:
        if fallback_house and profile_id == HOUSE_PROFILE_ID:
            return default_house_profile()
        return None
    try:
        row = fetch_pipeline_profile_row(client, profile_id)
    except _READ_ERRORS as exc:
        logger.warning("pipeline profile load failed for %s (%s)", profile_id, exc)
        row = None
    if row is None:
        if fallback_house and profile_id == HOUSE_PROFILE_ID:
            return default_house_profile()
        return None
    try:
        return row_to_pipeline_profile(row)
    except (ValidationError, ValueError, TypeError, KeyError) as exc:
        logger.warning("invalid pipeline profile %s (%s)", profile_id, exc)
        if fallback_house and profile_id == HOUSE_PROFILE_ID:
            return default_house_profile()
        return None


def pin_pipeline_profile(
    client: _SupabaseClient | None,
    *,
    overlay_profile_id: str | None = None,
    mode: PipelineProfileMode | None = None,
) -> PinnedPipelineProfile:
    """Pin house (+ optional overlay) for preflight graph state.

    * Mode default: ``off`` (env ``OLYMPUS_PIPELINE_PROFILE_MODE``).
    * ``off`` / ``shadow``: ``applies_overlay=False``; ``effective_config`` = house.
    * ``active``: overlay config becomes ``effective_config`` for *preference*
      surfaces only; ``h4_roster_cap_unchanged`` / ``h7_h8_authority_unchanged``
      remain True — this seam never expands H4 or rewrites H7/H8.
    * Overlay cannot cancel/replace house run identity (validated on models).
    """
    resolved_mode = resolve_pipeline_profile_mode(mode if mode is not None else None)
    house = load_pipeline_profile(client, HOUSE_PROFILE_ID, fallback_house=True)
    assert house is not None  # fallback_house always yields a profile

    overlay_id = overlay_profile_id
    if overlay_id is None:
        overlay_id = os.environ.get(ENV_OVERLAY_ID, "").strip() or None

    overlay: PipelineProfile | None = None
    if overlay_id and overlay_id != HOUSE_PROFILE_ID:
        overlay = load_pipeline_profile(client, overlay_id, fallback_house=False)
        if overlay is not None and overlay.kind != "overlay":
            logger.warning(
                "refusing non-overlay profile %s as overlay pin; using house only",
                overlay_id,
            )
            overlay = None
        elif overlay is not None:
            # Belt-and-suspenders: overlays must keep house run identity.
            if overlay.house_run_id != HOUSE_RUN_ID or overlay.cancel_house_run:
                logger.warning(
                    "overlay %s attempted to alter house run identity; dropped",
                    overlay_id,
                )
                overlay = None

    applies = bool(overlay is not None and resolved_mode == "active")
    effective = overlay.config if applies and overlay is not None else house.config

    return PinnedPipelineProfile(
        house=house,
        overlay=overlay,
        mode=resolved_mode,
        effective_config=effective,
        applies_overlay=applies,
        h4_roster_cap_unchanged=True,
        h7_h8_authority_unchanged=True,
        house_run_id=HOUSE_RUN_ID,
    )


def pin_pipeline_profile_at_preflight(
    client: _SupabaseClient | None,
    *,
    overlay_profile_id: str | None = None,
    mode: PipelineProfileMode | None = None,
) -> PinnedPipelineProfile:
    """Fail-soft preflight entry: never raises; always returns a house pin."""
    try:
        return pin_pipeline_profile(
            client,
            overlay_profile_id=overlay_profile_id,
            mode=mode,
        )
    except Exception as exc:  # preflight must not abort the run
        logger.warning("pipeline profile pin failed (%s); using in-code house", exc)
        house = default_house_profile()
        return PinnedPipelineProfile(
            house=house,
            overlay=None,
            mode="off",
            effective_config=house.config,
            applies_overlay=False,
            h4_roster_cap_unchanged=True,
            h7_h8_authority_unchanged=True,
            house_run_id=HOUSE_RUN_ID,
        )
