import json
import glob
import os

BASE = "/Users/chrisstefan/Code/digithings/.claude/worktrees/sdca-strategy-refine/digiquant/.scratch/candidates_dump/candidates"
OUT = "/Users/chrisstefan/Code/digithings/.claude/worktrees/sdca-strategy-refine/digiquant/.scratch/candidates_dump/summary.json"

rows = []
for path in sorted(glob.glob(os.path.join(BASE, "*.json"))):
    d = json.load(open(path))
    data = d.get("data", d)
    curve = data.get("curve") or {}
    metrics = data.get("metrics") or {}
    row = {
        "id": d.get("id", os.path.splitext(os.path.basename(path))[0]),
        "name": data.get("name"),
        "status": data.get("status"),
        "stage": data.get("stage"),
        "date": data.get("date"),
        "headline": data.get("headline"),
        "has_curve": bool(curve),
        "metrics": metrics,
        "curve_beats_flat_dca_oos": curve.get("beats_flat_dca_oos"),
        "curve_vs_flat_dca_pct": curve.get("vs_flat_dca_pct"),
        "curve_vs_lump_pct": curve.get("vs_lump_pct"),
        "curve_net_profit_pct": curve.get("net_profit_pct"),
        "curve_max_dd_pct": curve.get("max_drawdown_pct"),
        "weights": data.get("weights"),
        "curve_params": data.get("curve_params"),
        "fold_table_len": len(data.get("fold_table") or []),
        "verdict_notes": data.get("verdict_notes"),
        "source": data.get("source"),
    }
    rows.append(row)

json.dump(rows, open(OUT, "w"), indent=2, default=str)
print("wrote", len(rows), "rows to", OUT)
