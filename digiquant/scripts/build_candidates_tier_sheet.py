#!/usr/bin/env python3
"""Build a StrategyIndexEntry[] manifest over every SDCA research-trial
tearsheet, so the dev-only "candidate tier sheet" page can list/sort/filter
them the same way the live /strategies page lists production strategies.

Scans ``.scratch/tearsheets/*.json`` (real ``TearsheetData`` payloads emitted
by ``emit_sdca_trial_tearsheet.py``) and writes ``_candidates_index.json``
into the same directory — reachable in the frontend, without a rebuild, via
the existing ``frontend/digiquant-web/public/preview-tearsheets`` symlink.

Every trial file's top-level ``strategy`` field is the fixed registry alias
"sdca" (see emit_sdca_trial_tearsheet.py), so it can't be used to distinguish
trials from each other in a combined listing. This script instead keys each
manifest entry by its filename stem (the trial id passed to
``--trial-id``) and points ``href`` at that trial's existing single-tearsheet
preview route (``/strategies/preview/?file=<trial-id>``) rather than the live
per-strategy route.

Zero production writes: reads only from the gitignored .scratch directory,
writes only back into it. Never touches settings.json, RESEARCH_STATE.md, or
Supabase.

Usage:
    uv run python scripts/build_candidates_tier_sheet.py
"""

from __future__ import annotations

import json
from pathlib import Path

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
TEARSHEETS_DIR = DIGIQUANT_ROOT / ".scratch" / "tearsheets"
MANIFEST_NAME = "_candidates_index.json"


def build_entry(trial_id: str, ts: dict) -> dict:
    dca = ts.get("dca") or {}
    label = ts.get("label") or trial_id
    return {
        "strategy": trial_id,
        "label": label.replace("_", " ") if label == trial_id else label,
        "kind": ts.get("kind", "dca"),
        "symbol": ts.get("symbol", "BTC-USD"),
        "engine": ts.get("engine", ""),
        "period_start": ts.get("period_start", ""),
        "period_end": ts.get("period_end", ""),
        "signal_delay_days": ts.get("signal_delay_days"),
        "net_profit_pct": ts.get("net_profit_pct"),
        "max_drawdown_pct": ts.get("max_drawdown_pct"),
        "profit_factor": ts.get("profit_factor"),
        "win_rate_pct": ts.get("win_rate_pct"),
        "avg_trade_pct": ts.get("avg_trade_pct"),
        "total_trades": ts.get("total_trades", 0),
        "generated_at": ts.get("generated_at", ""),
        "href": f"/strategies/preview/?file={trial_id}",
        "vs_lump_pct": dca.get("vs_lump_pct", ts.get("vs_lump_pct")),
        "vs_flat_dca_pct": dca.get("vs_flat_dca_pct", ts.get("vs_flat_dca_pct")),
        "capital_deployed_pct": dca.get("capital_deployed_pct", ts.get("capital_deployed_pct")),
        "allocated_pct": dca.get("allocated_pct", ts.get("allocated_pct")),
        "beats_flat_dca_oos": ts.get("beats_flat_dca_oos", False),
    }


def run() -> None:
    if not TEARSHEETS_DIR.exists():
        raise SystemExit(
            f"{TEARSHEETS_DIR} does not exist — run emit_sdca_trial_tearsheet.py first"
        )

    entries = []
    for path in sorted(TEARSHEETS_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue  # skip a previously-written manifest
        trial_id = path.stem
        with path.open() as f:
            ts = json.load(f)
        entries.append(build_entry(trial_id, ts))

    if not entries:
        raise SystemExit(f"no trial tearsheets found in {TEARSHEETS_DIR}")

    entries.sort(key=lambda e: e["generated_at"], reverse=True)

    out_path = TEARSHEETS_DIR / MANIFEST_NAME
    with out_path.open("w") as f:
        json.dump(entries, f)

    print(f"wrote {out_path} ({len(entries)} candidates)")
    print(f"{'trial_id':<45} {'vs_flat_dca%':>13} {'vs_lump%':>10}  beats_oos")
    for e in entries:
        vfd = e["vs_flat_dca_pct"]
        vl = e["vs_lump_pct"]
        vfd_s = f"{vfd:.2f}" if vfd is not None else "n/a"
        vl_s = f"{vl:.2f}" if vl is not None else "n/a"
        print(f"{e['strategy']:<45} {vfd_s:>13} {vl_s:>10}  {e['beats_flat_dca_oos']}")
    print(
        "\nPreview: npm run dev (in frontend/digiquant-web), then open "
        "http://127.0.0.1:3000/strategies/candidates/"
    )


if __name__ == "__main__":
    run()
