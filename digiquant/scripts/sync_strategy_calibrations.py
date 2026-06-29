#!/usr/bin/env python3
"""Upload local Slapper calibrations + registry metadata to Supabase (#1064).

One-time (or whenever you re-optimize in TradingView):

    python digiquant/scripts/sync_strategy_calibrations.py

Requires ``CORE_SUPABASE_URL`` + ``CORE_SUPABASE_SERVICE_KEY`` (service role).
Writes:
  - ``strategies`` — public registry rows (symbol, label, engine, config)
  - ``strategy_calibrations`` — private fitted params (service-role only)

The daily tearsheet pipeline reads calibrations back via ``--from-supabase``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "settings.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Slapper calibrations to Supabase")
    parser.add_argument(
        "--calibrations",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "src"
        / "digiquant"
        / "strategies"
        / "calibrations.json",
        help="Path to calibrations.json (default: gitignored private file)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print payloads only")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After upload, run verify_strategy_calibrations_rls.py",
    )
    args = parser.parse_args()

    if not args.calibrations.exists():
        logger.error("Missing %s — copy your TV-optimized params there first", args.calibrations)
        return 1

    calibrations = json.loads(args.calibrations.read_text())
    settings = json.loads(SETTINGS_PATH.read_text())
    defaults = settings.get("defaults", {})
    strategies = settings.get("strategies", {})

    from digiquant.data.store.client import build_digiquant_client
    from digiquant.data.store.strategies import upsert_calibration, upsert_strategies

    client = build_digiquant_client()
    if client is None and not args.dry_run:
        logger.error("Supabase credentials missing (CORE_SUPABASE_URL + CORE_SUPABASE_SERVICE_KEY)")
        return 1

    strat_rows = []
    for sid, cfg in strategies.items():
        if sid not in calibrations:
            logger.error("calibrations.json missing key %r", sid)
            return 1
        strat_rows.append(
            {
                "id": sid,
                "symbol": cfg["symbol"],
                "label": cfg.get("label", sid),
                "engine": "nautilus",
                "config": {
                    "kind": cfg.get("kind", "long_short"),
                    "trade_start": defaults.get("trade_start"),
                    "initial_capital": defaults.get("initial_capital"),
                    "size_pct_equity": defaults.get("size_pct_equity"),
                },
                "enabled": True,
            }
        )

    if args.dry_run:
        print(json.dumps({"strategies": strat_rows, "calibrations": calibrations}, indent=2))
        return 0

    assert client is not None
    upsert_strategies(client, strat_rows)
    logger.info("Upserted %d strategies rows", len(strat_rows))
    for sid in strategies:
        upsert_calibration(client, sid, calibrations[sid])
        logger.info("  calibration → %s", sid)
    logger.info("Done.")
    if args.verify:
        import subprocess

        verify = Path(__file__).resolve().parent / "verify_strategy_calibrations_rls.py"
        rc = subprocess.call([sys.executable, str(verify)])
        return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
