#!/usr/bin/env python3
"""Verify strategy_calibrations privacy (#1064 / #1067).

Checks:
  1. Service-role client can read calibration rows for all Slapper strategies.
  2. Anon client (if CORE_SUPABASE_ANON_KEY is set) returns **no** calibration data.
  3. ``strategies`` registry rows exist (public metadata only — no fitted params).

Exit 0 when protected and populated; non-zero on misconfiguration.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "settings.json"


def _strategy_ids() -> list[str]:
    settings = json.loads(SETTINGS_PATH.read_text())
    return list(settings.get("strategies", {}).keys())


def main() -> int:
    from digiquant.data.store.client import build_digiquant_client, digiquant_credentials
    from digiquant.data.store.strategies import read_calibration, read_strategies

    url, service_key = digiquant_credentials()
    if not url or not service_key:
        logger.error(
            "Missing CORE_SUPABASE_URL + CORE_SUPABASE_SERVICE_KEY "
            "(or legacy SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)"
        )
        return 1

    client = build_digiquant_client()
    assert client is not None

    ids = _strategy_ids()
    rows = read_strategies(client)
    if rows.is_empty():
        logger.error("strategies table is empty")
        return 1
    found_ids = {r["id"] for r in rows.to_dicts()}
    missing_registry = [sid for sid in ids if sid not in found_ids]
    if missing_registry:
        logger.error("Missing strategies rows: %s", ", ".join(missing_registry))
        return 1
    logger.info("strategies registry: %d rows OK (public metadata only)", len(found_ids))

    empty_cals: list[str] = []
    for sid in ids:
        cal = read_calibration(client, sid)
        if not cal:
            empty_cals.append(sid)
            continue
        if "rsi_upper_band" not in cal:
            logger.warning("%s calibration missing expected keys", sid)
        logger.info("  service-role read OK: %s (%d params)", sid, len(cal))
    if empty_cals:
        logger.error("No calibration rows for: %s — run sync_strategy_calibrations.py", ", ".join(empty_cals))
        return 1

    anon_key = (os.environ.get("CORE_SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    if anon_key:
        from supabase import create_client  # type: ignore[import-not-found]

        anon = create_client(url, anon_key)
        leaked = 0
        for sid in ids:
            resp = (
                anon.table("strategy_calibrations")
                .select("calibration")
                .eq("strategy_id", sid)
                .limit(1)
                .execute()
            )
            rows_data = resp.data or []
            if rows_data and rows_data[0].get("calibration"):
                leaked += 1
        if leaked:
            logger.error("RLS LEAK: anon key read %d calibration row(s) — remove anon policy!", leaked)
            return 1
        logger.info("anon key: strategy_calibrations returns empty (protected)")
    else:
        logger.info("CORE_SUPABASE_ANON_KEY not set — skip live anon probe (RLS defined in migration 046)")

    logger.info("Calibration store verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
