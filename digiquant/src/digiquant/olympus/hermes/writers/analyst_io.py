"""Supabase writers for H5 analyst coverage."""

from __future__ import annotations

import logging
from datetime import date

from digiquant.olympus.atlas.supabase_io import SupabaseClient

logger = logging.getLogger(__name__)


def upsert_analyst_coverage(
    client: SupabaseClient,
    *,
    run_date: date,
    ticker: str,
    document_key: str,
    thesis_ids: list[str] | None = None,
) -> None:
    """Write ``analyst_coverage`` row for *ticker* (migration 024)."""
    row = {
        "date": run_date.isoformat(),
        "ticker": ticker,
        "thesis_ids": thesis_ids or [],
        "analyst_role": "asset_analyst",
        "current_recommendation_key": document_key,
    }
    client.table("analyst_coverage").upsert(row, on_conflict="date,ticker").execute()
