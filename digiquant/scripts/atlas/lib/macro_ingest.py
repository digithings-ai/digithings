"""Shared helpers for macro_series_observations ingest scripts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = ROOT / "config" / "macro_series.yaml"

CHUNK_SIZE = 500


def dedupe_observation_rows(rows: list[dict]) -> list[dict]:
    """Last row wins per (source, series_id, obs_date); avoids Postgres ON CONFLICT duplicate-key errors."""
    out: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        d = r.get("obs_date")
        ds = str(d)[:10] if d else ""
        key = (str(r.get("source", "")), str(r.get("series_id", "")), ds)
        out[key] = r
    return list(out.values())


def load_config_env() -> None:
    """Load config/supabase.env then config/mcp.secrets.env (gitignored). Does not override existing os.environ."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for path in (ROOT / "config" / "supabase.env", ROOT / "config" / "mcp.secrets.env"):
        if path.exists():
            load_dotenv(path, override=False)
    load_dotenv(override=False)


def load_manifest() -> dict[str, Any]:
    import yaml

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Manifest not found: {MANIFEST_PATH}")
    data = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("macro_series.yaml must be a mapping at top level")
    return data


def connect_supabase():
    try:
        from supabase import create_client
    except ImportError:
        return None
    load_config_env()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        return None
    return create_client(url, key)


def upsert_observations(sb, rows: list[dict], chunk: int = CHUNK_SIZE) -> int:
    """Upsert rows into macro_series_observations. Returns rows written."""
    if not rows:
        return 0
    rows = dedupe_observation_rows(rows)
    for i in range(0, len(rows), chunk):
        sb.table("macro_series_observations").upsert(
            rows[i : i + chunk],
            on_conflict="source,series_id,obs_date",
        ).execute()
    return len(rows)


def latest_obs_date(sb, source: str, series_id: str) -> str | None:
    """Latest obs_date (YYYY-MM-DD) for a series, or None."""
    res = (
        sb.table("macro_series_observations")
        .select("obs_date")
        .eq("source", source)
        .eq("series_id", series_id)
        .order("obs_date", desc=True)
        .limit(1)
        .execute()
    )
    data = getattr(res, "data", None) or []
    if not data:
        return None
    d = data[0].get("obs_date")
    return str(d)[:10] if d else None


def latest_obs_date_for_source(sb, source: str) -> str | None:
    """Latest obs_date for any row with this source (e.g. all FX legs share cadence)."""
    res = (
        sb.table("macro_series_observations")
        .select("obs_date")
        .eq("source", source)
        .order("obs_date", desc=True)
        .limit(1)
        .execute()
    )
    data = getattr(res, "data", None) or []
    if not data:
        return None
    d = data[0].get("obs_date")
    return str(d)[:10] if d else None


def iso_today() -> str:
    from datetime import date

    return date.today().isoformat()
