"""Supabase writers for H5 analyst coverage."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from digiquant.research.supabase_io import SupabaseClient
from digiquant.dashboard.overlay.persist import skip_overlay_shared_register

logger = logging.getLogger(__name__)


def upsert_analyst_coverage(
    client: SupabaseClient,
    *,
    run_date: date,
    ticker: str,
    document_key: str,
    thesis_ids: list[str] | None = None,
    workspace_id: UUID | str | None = None,
) -> None:
    """Write ``analyst_coverage`` row for *ticker* (migration 024)."""
    if skip_overlay_shared_register(workspace_id):
        logger.info(
            "overlay skip shared register analyst_coverage (house-only UNIQUE(date, ticker))"
        )
        return
    row = {
        "date": run_date.isoformat(),
        "ticker": ticker,
        "thesis_ids": thesis_ids or [],
        "analyst_role": "asset_analyst",
        "current_recommendation_key": document_key,
    }
    client.table("analyst_coverage").upsert(row, on_conflict="date,ticker").execute()
