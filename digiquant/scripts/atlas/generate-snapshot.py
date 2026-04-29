#!/usr/bin/env python3
"""Generate snapshot.json sidecar from existing DIGEST.md + portfolio.json.

Usage:
  python scripts/generate-snapshot.py                  # latest day
  python scripts/generate-snapshot.py 2026-04-06       # specific day
  python scripts/generate-snapshot.py --all            # all day folders
  python scripts/generate-snapshot.py --validate       # validate existing snapshot.json files
  python scripts/generate-snapshot.py --force 2026-04-06  # re-parse even if snapshot.json exists

NOTE: If snapshot.json already exists and has a populated 'regime' key (written
directly by the AI in Phase 7), this script returns it unchanged unless --force
is given. Regex parsing is a fallback for legacy/missing files only.
"""
import argparse
import json, re, sys, os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
DAILY_DIR = ROOT / "data" / "agent-cache" / "daily"
PORTFOLIO_JSON = ROOT / "config" / "portfolio.json"

SCHEMA_PATH = ROOT / "templates" / "snapshot-schema.json"


def load_portfolio_json():
    if not PORTFOLIO_JSON.exists():
        return [], {}
    data = json.loads(PORTFOLIO_JSON.read_text(encoding="utf-8"))
    return data.get("positions", []), data.get("constraints", {})


def parse_regime(content):
    """Extract regime object from DIGEST.md content.

    Tolerates:
    - em dash (—), en dash (–), or hyphen (-) as separator
    - bold/italic markup around the value
    - emoji prefix on the heading line
    """
    regime = {"label": "Unknown", "bias": "Unknown", "conviction": "Medium", "summary": ""}

    # Pattern: **Overall Bias**: <value> (any dash style, optional emphasis)
    m = re.search(r"\*\*Overall Bias\*\*:\s*\*{0,2}([^\n*]+?)\*{0,2}\s*$", content, re.MULTILINE)
    if not m:
        print("   ⚠️  No '**Overall Bias**' found — regime will be 'Unknown'", file=sys.stderr)
        return regime

    full = m.group(1).strip()
    # Split on any dash variant: em dash, en dash, or " - "
    sep_m = re.search(r"\s*[—–\-]\s*", full)
    if sep_m:
        regime["bias"] = full[:sep_m.start()].strip()
        regime["label"] = full[sep_m.end():].strip()
    else:
        regime["bias"] = full
        regime["label"] = full

    # Derive conviction from language
    lower = full.lower()
    if any(w in lower for w in ["strong", "high conviction", "maximum"]):
        regime["conviction"] = "High"
    elif any(w in lower for w in ["caution", "mixed", "conflicted", "uncertain"]):
        regime["conviction"] = "Low"
    else:
        regime["conviction"] = "Medium"

    # Grab summary paragraph
    para = content[m.end():].lstrip().split("\n\n")[0]
    regime["summary"] = para.strip()[:500]

    return regime


def parse_positions_table(content):
    """Extract positions from DIGEST.md table format.

    Tolerates:
    - Optional emoji prefix on the '## Portfolio Positioning' heading
    - Tickers 2-6 characters (covers IEMG, etc.)
    - Weight with or without trailing %
    """
    positions = []
    # Tolerate emoji or bold prefix on the section heading
    pm = re.search(r"##\s*(?:[^\w]\s*)?Portfolio Positioning", content)
    if not pm:
        print("   ⚠️  No '## Portfolio Positioning' section found", file=sys.stderr)
        return positions
    section = content[pm.end():]
    next_h2 = re.search(r"\n## ", section)
    if next_h2:
        section = section[:next_h2.start()]

    table_pat = r"^\|\s*([A-Z]{2,6})\s*\|\s*(\d+(?:\.\d+)?)%?\s*\|(.+)\|"
    for m in re.finditer(table_pat, section, re.MULTILINE):
        ticker = m.group(1)
        weight = float(m.group(2))
        cells = [c.strip() for c in m.group(3).split("|")]
        action_raw = cells[-2] if len(cells) >= 2 else ""
        rationale = cells[-1] if cells else ""

        # Normalize action to enum
        action_upper = action_raw.upper().replace("*", "")
        if "EXIT" in action_upper:
            action = "EXIT"
        elif "ADD" in action_upper:
            action = "ADD"
        elif "TRIM" in action_upper:
            action = "TRIM"
        elif "HOLD" in action_upper:
            action = "HOLD"
        else:
            action = "HOLD"

        positions.append({
            "ticker": ticker,
            "weight_pct": weight,
            "action": action,
            "rationale": rationale[:300],
        })
    return positions


def _normalize_thesis_status(raw):
    """Normalize free-form thesis status (with emoji) to DB enum value."""
    if not raw:
        return None
    s = raw.lower().replace("\u2705", "").replace("\u26a0\ufe0f", "").replace("\u274c", "").strip()
    if "challenged" in s:
        return "CHALLENGED"
    if "confirmed" in s or "active" in s:
        return "ACTIVE"
    if "monitoring" in s:
        return "MONITORING"
    if "invalidated" in s:
        return "INVALIDATED"
    if "closed" in s:
        return "CLOSED"
    if "paused" in s or "hold" in s:
        return "PAUSED"
    if "new" in s:
        return "NEW"
    return "ACTIVE"


def parse_theses(content):
    """Extract thesis tracker table from DIGEST.md.

    Tolerates optional emoji prefix on the section heading.
    """
    theses = []
    tm = re.search(r"## (?:[^\w]\s*)?Thesis Tracker", content)
    if not tm:
        print("   ⚠️  No '## Thesis Tracker' section found", file=sys.stderr)
        return theses
    section = content[tm.end():]
    next_h2 = re.search(r"\n## ", section)
    if next_h2:
        section = section[:next_h2.start()]

    rows = [l.strip() for l in section.splitlines()
            if l.strip().startswith("|") and not re.match(r"^\|[-\s|]+\|$", l.strip())]
    if len(rows) >= 2:
        rows = rows[1:]  # skip header
    for row in rows:
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) >= 5:
            theses.append({
                "id": cells[0],
                "name": cells[1],
                "vehicle": cells[2],
                "invalidation": cells[3],
                "status": _normalize_thesis_status(cells[4]),
                "notes": cells[5] if len(cells) > 5 else "",
            })
    return theses


def parse_market_data(content):
    """Extract key market levels from content (best-effort regex)."""
    data = {}
    patterns = {
        "SPY": r"SPY[^0-9]*?(\d{3,4}(?:\.\d+)?)",
        "VIX": r"VIX[^0-9]*?(\d{1,3}(?:\.\d+)?)",
        "DXY": r"DXY[^0-9]*?(\d{2,3}(?:\.\d+)?)",
        "WTI": r"WTI[^0-9]*?\$?(\d{2,3}(?:\.\d+)?)",
        "Gold": r"[Gg]old[^0-9]*?\$?(\d{3,5}(?:\.\d+)?)",
        "BTC": r"BTC[^0-9]*?\$?([\d,]+(?:\.\d+)?)",
        "US10Y": r"10[- ]?[Yy](?:ear)?[^0-9]*?(\d{1,2}(?:\.\d+)?)%?",
    }
    for key, pat in patterns.items():
        m = re.search(pat, content)
        if m:
            val = m.group(1).replace(",", "")
            try:
                data[key] = float(val)
            except ValueError:
                pass
    return data


def parse_segment_biases(content):
    """Extract per-segment biases from DIGEST.md."""
    biases = {}
    segments = {
        "macro": r"(?:Macro|Macro Regime)\s*(?:Bias)?[:\s]*\*?\*?([A-Za-z\- /]+)",
        "bonds": r"(?:Bonds?|Fixed Income)\s*(?:Bias)?[:\s]*\*?\*?([A-Za-z\- /]+)",
        "commodities": r"Commodit(?:y|ies)\s*(?:Bias)?[:\s]*\*?\*?([A-Za-z\- /]+)",
        "crypto": r"Crypto\s*(?:Bias)?[:\s]*\*?\*?([A-Za-z\- /]+)",
    }
    for seg, pat in segments.items():
        m = re.search(pat, content)
        if m:
            biases[seg] = m.group(1).strip().rstrip("*")
    return biases


def parse_actionable(content):
    """Extract actionable summary items. Tolerates emoji prefix on heading."""
    items = []
    m = re.search(r"## (?:[^\w]\s*)?Actionable Summary", content)
    if not m:
        return items
    sub = content[m.end():].lstrip()
    for line in sub.splitlines():
        if line.startswith("## "):
            break
        line = line.strip()
        if line.startswith("- ") or re.match(r"\d+\.\s+", line):
            clean = re.sub(r"^(-\s*|\d+\.\s*)", "", line)
            items.append(clean[:300])
    return items[:10]


def parse_risks(content):
    """Extract risk radar items. Tolerates emoji prefix on heading."""
    items = []
    m = re.search(r"## (?:[^\w]\s*)?Risk Radar", content)
    if not m:
        return items
    sub = content[m.end():].lstrip()
    for line in sub.splitlines():
        if line.startswith("## "):
            break
        line = line.strip()
        if line.startswith("- ") or re.match(r"\d+\.\s+", line):
            clean = re.sub(r"^(-\s*|\d+\.\s*)", "", line)
            items.append(clean[:300])
    return items[:10]


def detect_run_type(day_dir):
    meta_path = day_dir / "_meta.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return data.get("type", "baseline"), data.get("baseline")
        except Exception:
            pass
    return "baseline", None


def _snapshot_is_populated(data):
    """Return True if snapshot.json contains AI-written data (not just the scaffold)."""
    if not isinstance(data, dict):
        return False
    regime = data.get("regime", {})
    return bool(regime and regime != {} and regime.get("bias", "Unknown") != "Unknown")


def validate_snapshot(snap, path_label=""):
    """Validate snapshot dict against the canonical schema. Print warnings for missing fields."""
    required = ["schema_version", "date", "run_type", "regime", "positions", "theses",
                "market_data", "segment_biases", "actionable", "risks"]
    missing = [k for k in required if k not in snap]
    if missing:
        print(f"   ⚠️  {path_label} snapshot.json missing required fields: {missing}", file=sys.stderr)
    regime = snap.get("regime", {})
    for rf in ["label", "bias", "conviction", "summary"]:
        if not regime.get(rf) or regime[rf] == "Unknown":
            print(f"   ⚠️  {path_label} regime.{rf} is empty/Unknown", file=sys.stderr)
    return len(missing) == 0


def generate_snapshot(day_dir, pj_positions, force=False):
    """Generate snapshot.json for a single day folder.

    If snapshot.json already exists and is AI-populated (regime.bias != 'Unknown'),
    return the existing file without re-parsing DIGEST.md (unless force=True).
    This makes the regression path the fallback, not the primary path.
    """
    digest_path = day_dir / "DIGEST.md"
    snap_path = day_dir / "snapshot.json"

    # Prefer existing AI-written snapshot.json (skip fragile regex parsing)
    if not force and snap_path.exists():
        try:
            existing = json.loads(snap_path.read_text(encoding="utf-8"))
            if _snapshot_is_populated(existing):
                return existing
        except Exception:
            pass  # Fall through to re-parse

    if not digest_path.exists():
        return None

    print(f"   ⚠️  {day_dir.name}: snapshot.json missing/unpopulated — falling back to DIGEST.md regex parse", file=sys.stderr)
    content = digest_path.read_text(encoding="utf-8")
    date_str = day_dir.name
    run_type, baseline_date = detect_run_type(day_dir)

    # Parse all components
    regime = parse_regime(content)
    positions = parse_positions_table(content)
    theses = parse_theses(content)
    market_data = parse_market_data(content)
    segment_biases = parse_segment_biases(content)
    actionable = parse_actionable(content)
    risks = parse_risks(content)

    # Enrich positions with portfolio.json metadata
    pj_lookup = {p["ticker"]: p for p in pj_positions}
    for pos in positions:
        pj = pj_lookup.get(pos["ticker"], {})
        pos["name"] = pj.get("name", pos["ticker"])
        pos["category"] = pj.get("category")
        pos["thesis_id"] = (pj.get("thesis_ids") or [None])[0]
        pos["entry_price"] = pj.get("entry_price_usd")
        pos["entry_date"] = pj.get("entry_date")

    # Detect portfolio posture
    posture_match = re.search(r"Portfolio Posture\*?\*?:\s*(\w+)", content)
    posture = posture_match.group(1) if posture_match else "Defensive"

    # Detect cash %
    cash_match = re.search(r"Cash.*?(\d+)%", content)
    cash_pct = float(cash_match.group(1)) if cash_match else None

    snapshot = {
        "schema_version": "1.0",
        "date": date_str,
        "run_type": run_type,
        "baseline_date": baseline_date,
        "regime": regime,
        "positions": positions,
        "theses": theses,
        "market_data": market_data,
        "segment_biases": segment_biases,
        "actionable": actionable,
        "risks": risks,
        "portfolio_posture": posture,
        "cash_pct": cash_pct,
    }

    out_path = day_dir / "snapshot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    return snapshot


def main():
    pj_positions, _ = load_portfolio_json()

    parser = argparse.ArgumentParser(
        description="generate-snapshot.py — Generate snapshot.json sidecar from DIGEST.md + portfolio.json",
        epilog="Without arguments, processes the latest day folder."
    )
    parser.add_argument(
        "date", nargs="?", metavar="YYYY-MM-DD",
        help="Target date folder (default: latest)"
    )
    parser.add_argument("--all", action="store_true", help="Process all day folders")
    parser.add_argument(
        "--validate", action="store_true",
        help="Validate existing snapshot.json files against schema expectations"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-parse even if snapshot.json already exists (overrides regime guard)"
    )
    args = parser.parse_args()
    force = args.force

    if args.validate:
        # Validate all existing snapshot.json files against schema expectations
        target = args.date
        day_dirs = []
        if target and re.match(r"\d{4}-\d{2}-\d{2}", target):
            day_dirs = [DAILY_DIR / target]
        else:
            day_dirs = sorted([d for d in DAILY_DIR.iterdir()
                               if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)])
        ok = err = skipped = 0
        for d in day_dirs:
            sp = d / "snapshot.json"
            if not sp.exists():
                skipped += 1
                continue
            try:
                snap = json.loads(sp.read_text(encoding="utf-8"))
                if validate_snapshot(snap, d.name):
                    ok += 1
                else:
                    err += 1
            except Exception as e:
                print(f"   ❌ {d.name}: invalid JSON — {e}", file=sys.stderr)
                err += 1
        print(f"\nValidation: {ok} OK, {err} errors, {skipped} skipped (no snapshot.json)")
        sys.exit(1 if err else 0)

    elif args.all:
        # Process all day folders
        count = 0
        for day_dir in sorted(DAILY_DIR.iterdir()):
            if day_dir.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", day_dir.name):
                snap = generate_snapshot(day_dir, pj_positions, force=force)
                if snap:
                    print(f"  ✅ {day_dir.name}: {len(snap['positions'])} positions, {len(snap['theses'])} theses")
                    count += 1
        print(f"\nGenerated {count} snapshot.json files")

    elif args.date and re.match(r"\d{4}-\d{2}-\d{2}", args.date):
        # Specific date
        day_dir = DAILY_DIR / args.date
        if not day_dir.exists():
            print(f"❌ Folder not found: {day_dir}")
            sys.exit(1)
        snap = generate_snapshot(day_dir, pj_positions, force=force)
        if snap:
            print(f"✅ {args.date}: {len(snap['positions'])} positions, {len(snap['theses'])} theses")
            print(json.dumps(snap, indent=2)[:2000])
        else:
            print(f"❌ No DIGEST.md in {day_dir}")

    else:
        # Latest day folder
        day_dirs = sorted([d for d in DAILY_DIR.iterdir()
                          if d.is_dir() and re.match(r"\d{4}-\d{2}-\d{2}", d.name)])
        if not day_dirs:
            print("❌ No daily output folders found")
            sys.exit(1)
        day_dir = day_dirs[-1]
        snap = generate_snapshot(day_dir, pj_positions, force=force)
        if snap:
            print(f"✅ {day_dir.name}: {len(snap['positions'])} positions, {len(snap['theses'])} theses")
        else:
            print(f"❌ No DIGEST.md in {day_dir}")


if __name__ == "__main__":
    main()
