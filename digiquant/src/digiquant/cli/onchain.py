"""`digiquant onchain ...` — Bitview/BRK valuation-series ingest (#1086)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import click

logger = logging.getLogger(__name__)


@click.group()
def onchain() -> None:
    """On-chain valuation series (Bitview/BRK → parquet / macro store)."""


@onchain.command("fetch-bitview")
@click.option(
    "--series",
    "series_csv",
    type=str,
    default="mvrv,asopr_24h,puell_multiple,rhodl_ratio",
    help="Comma-separated Bitview day1 series ids (NUPL refused).",
)
@click.option(
    "--cache-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Parquet cache (default: data/onchain/bitview).",
)
@click.option("--supabase", is_flag=True, help="Upsert into macro_series_observations.")
@click.option("--dry-run", is_flag=True, help="Fetch + write parquet; never upsert.")
def fetch_bitview_cmd(
    series_csv: str,
    cache_dir: Path | None,
    supabase: bool,
    dry_run: bool,
) -> None:
    """Ingest Bitview/BRK on-chain valuation series (MVRV / aSOPR / Puell / RHODL)."""
    from digiquant.data.onchain.bitview import DEFAULT_CACHE_DIR
    from digiquant.data.onchain.ingest import ingest_bitview
    from digiquant.data.prices.supabase_writer import build_supabase_client

    series_ids = [s.strip() for s in series_csv.split(",") if s.strip()]
    dest = cache_dir or DEFAULT_CACHE_DIR
    client = None
    if supabase and not dry_run:
        client = build_supabase_client(
            os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL")),
            os.environ.get(
                "CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            ),
        )
        if client is None:
            raise click.ClickException(
                "CORE_SUPABASE_URL / CORE_SUPABASE_SERVICE_KEY required for --supabase"
            )

    result = ingest_bitview(
        series_ids,
        cache_dir=dest,
        supabase_client=client,
    )
    payload = result.model_dump(mode="json")
    click.echo(json.dumps(payload, indent=2, default=str))
    if not result.ok:
        raise click.ClickException(result.error or "Bitview ingest returned no data")


__all__ = ["onchain"]
