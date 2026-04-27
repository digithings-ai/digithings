#!/usr/bin/env python3
"""
legacy_delta_to_ops.py

Convert a legacy DIGEST-DELTA.md (plus optional segment deltas) into a delta request JSON
compatible with templates/delta-request-schema.json.

This is an adapter for migration/simulation only.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _extract_section(md: str, heading: str) -> str:
    # Heading like "## ⚡ Actionable Summary" etc.
    # Use line-based matching (more robust than regex against unicode/emoji edge cases).
    lines = md.splitlines()
    start_idx: Optional[int] = None
    for i, line in enumerate(lines):
        if line.startswith("##") and heading in line:
            start_idx = i + 1
            break
    if start_idx is None:
        return ""
    end_idx = len(lines)
    for j in range(start_idx, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break
    return "\n".join(lines[start_idx:end_idx]).strip()


def _extract_heading_block(md: str, needle: str) -> str:
    """Extract body under the first heading (any depth #..#) whose title contains `needle`."""
    lines = md.splitlines()
    start_line: Optional[int] = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") and needle in stripped:
            start_line = i
            break
    if start_line is None:
        return ""
    header = lines[start_line]
    level = 0
    while level < len(header) and header[level] == "#":
        level += 1
    body: List[str] = []
    for j in range(start_line + 1, len(lines)):
        s = lines[j].lstrip()
        if s.startswith("#"):
            nlev = 0
            while nlev < len(s) and s[nlev] == "#":
                nlev += 1
            if nlev <= level:
                break
        body.append(lines[j])
    return "\n".join(body).strip()


def _extract_list_items(block: str) -> List[str]:
    items: List[str] = []
    for line in block.splitlines():
        s = line.strip()
        if re.match(r"^\d+\.\s+", s):
            items.append(re.sub(r"^\d+\.\s+", "", s).strip())
        elif s.startswith("- "):
            items.append(s[2:].strip())
    return [i for i in items if i][:10]


def _find_vix(md: str) -> Optional[float]:
    m = re.search(r"\bVIX\b[^0-9]*(\d{1,3}(?:\.\d+)?)", md)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def build_ops(delta_md: str) -> Dict[str, Any]:
    ops: List[Dict[str, Any]] = []
    changed_paths: List[str] = []

    # Actionable / risks
    actionable_block = _extract_section(delta_md, "Actionable Summary")
    risks_block = _extract_section(delta_md, "Risk Radar")
    actionable = _extract_list_items(actionable_block) if actionable_block else []
    risks = _extract_list_items(risks_block) if risks_block else []

    if actionable:
        ops.append(
            {
                "op": "set",
                "path": "/actionable",
                "value": actionable,
                "reason": "Replace actionable list from legacy DIGEST-DELTA.md",
            }
        )
        changed_paths.append("/actionable")
    if risks:
        ops.append(
            {
                "op": "set",
                "path": "/risks",
                "value": risks,
                "reason": "Replace risks list from legacy DIGEST-DELTA.md",
            }
        )
        changed_paths.append("/risks")

    # Regime shift summary + bias if present
    m = re.search(r"^\*\*Overall Bias\*\*:\s*(.+)$", delta_md, flags=re.MULTILINE)
    if m:
        overall = m.group(1).strip()
        ops.append(
            {
                "op": "set",
                "path": "/regime/summary",
                "value": overall,
                "reason": "Set regime summary from delta overall bias line",
            }
        )
        changed_paths.append("/regime/summary")

    # Market data: VIX only (we can add more later)
    vix = _find_vix(delta_md)
    if vix is not None:
        ops.append(
            {
                "op": "set",
                "path": "/market_data/VIX",
                "value": vix,
                "reason": "Update VIX level from legacy delta",
            }
        )
        changed_paths.append("/market_data/VIX")

    # Narrative blocks (paths match convert_snapshot_v1 + materialize_snapshot sector normalization)
    for key, needle in [
        ("/narrative/macro", "Macro & Events"),
        ("/narrative/us_equities", "Equities"),
        ("/narrative/asset_classes/crypto", "Crypto"),
        ("/narrative/asset_classes/bonds", "Bonds"),
        ("/narrative/asset_classes/commodities", "Commodities"),
        ("/narrative/asset_classes/forex", "Forex"),
        ("/narrative/asset_classes/international", "International"),
        ("/narrative/alt_data", "Alternative Data"),
    ]:
        block = _extract_heading_block(delta_md, needle)
        if block:
            ops.append(
                {
                    "op": "set",
                    "path": key,
                    "value": block[:12000],
                    "reason": f"Update narrative block from legacy section: {needle}",
                }
            )
            changed_paths.append(key)

    # Sector scorecard: patch a few known rows by sector name (Energy, Technology, Real Estate)
    # We keep it simple: set bias/driver if mentioned.
    sector_rows = []
    score_block = _extract_section(delta_md, "Sector Scorecard")
    if score_block:
        for line in score_block.splitlines():
            if line.strip().startswith("|") and "Sector" not in line and "---" not in line:
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 4:
                    sector_rows.append(cells)
    # Slugs must match materialize_snapshot._normalize_sector_scorecard (from convert_snapshot_v1 rows)
    sector_slug = {
        "Technology": "technology",
        "Healthcare": "healthcare",
        "Energy": "energy",
        "Financials": "financials",
        "Consumer Staples": "consumer_staples",
        "Consumer Disc": "consumer_disc",
        "Con. Disc": "consumer_disc",
        "Industrials": "industrials",
        "Utilities": "utilities",
        "Materials": "materials",
        "Real Estate": "real_estate",
        "Comms": "comms",
    }

    for cells in sector_rows:
        sector = cells[0]
        driver = cells[3] if len(cells) >= 4 else ""
        bias_change = cells[2]
        new_bias = "N"
        if "BULLISH" in bias_change.upper() or "OW" in bias_change.upper():
            new_bias = "OW"
        if "BEARISH" in bias_change.upper() or "UW" in bias_change.upper():
            new_bias = "UW"
        slug = sector_slug.get(sector)
        if not slug:
            continue
        ops.append(
            {
                "op": "set",
                "path": f"/sector_scorecard/{slug}/bias",
                "value": new_bias,
                "reason": f"Sector scorecard update for {sector}",
            }
        )
        ops.append(
            {
                "op": "set",
                "path": f"/sector_scorecard/{slug}/key_driver",
                "value": driver[:200] if driver else "",
                "reason": f"Sector scorecard driver update for {sector}",
            }
        )
        changed_paths.append("/sector_scorecard")

    return {"changed_paths": sorted(set(changed_paths)), "ops": ops}


def parse_baseline_date_from_delta_md(md: str) -> Optional[str]:
    m = re.search(r"Baseline:\s*(\d{4}-\d{2}-\d{2})", md)
    return m.group(1) if m else None


def build_delta_request_payload(date: str, baseline_date: str, delta_md: str) -> Dict[str, Any]:
    """Full delta-request object (schema_version, date, baseline_date, changed_paths, ops, notes)."""
    payload = build_ops(delta_md)
    return {
        "schema_version": "1.0",
        "date": date,
        "baseline_date": baseline_date,
        "changed_paths": payload["changed_paths"],
        "ops": payload["ops"],
        "notes": "Retrofitted from legacy DIGEST-DELTA.md; aligned with templates/delta-request-schema.json.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Convert legacy DIGEST-DELTA.md to delta request ops JSON")
    ap.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    ap.add_argument("--baseline-date", required=True, help="Baseline date (YYYY-MM-DD)")
    ap.add_argument("--delta-md", required=True, help="Path to DIGEST-DELTA.md (e.g. under data/agent-cache/daily/<date>/)")
    ap.add_argument("--out", required=True, help="Output path for delta request JSON")
    args = ap.parse_args()

    md = Path(args.delta_md).read_text(encoding="utf-8")
    out = build_delta_request_payload(args.date, args.baseline_date, md)
    out["notes"] = "Auto-converted from legacy DIGEST-DELTA.md for migration simulation."
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✅ Wrote {args.out} ({len(out['ops'])} ops)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)

