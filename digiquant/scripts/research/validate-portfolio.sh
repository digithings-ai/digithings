#!/bin/bash
# validate-portfolio.sh — Check portfolio.json against investment-profile.md constraints
# Run from repo root: ./scripts/validate-portfolio.sh
# Validate proposed positions: ./scripts/validate-portfolio.sh --proposed
set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

PORTFOLIO="config/portfolio.json"
PROFILE="config/investment-profile.md"

if [[ ! -f "$PORTFOLIO" ]]; then echo "❌ $PORTFOLIO not found"; exit 1; fi
if [[ ! -f "$PROFILE" ]]; then echo "❌ $PROFILE not found"; exit 1; fi

# Parse constraints from investment-profile.md (first number in matching row)
extract_pct() {
  grep -i "$1" "$PROFILE" | head -1 | grep -oE '[0-9]+%' | head -1 | tr -d '%'
}

MAX_SINGLE_ETF=$(extract_pct "Max single ETF weight")
MAX_SINGLE_THEME=$(extract_pct "Max single theme/category")
MIN_CASH_FLOOR=$(extract_pct "Min cash/T-bill floor")
WEIGHT_INCREMENT=$(extract_pct "Weight increment")
MIN_POSITION=$(extract_pct "Min position size")

# Defaults if parsing fails
MAX_SINGLE_ETF=${MAX_SINGLE_ETF:-100}
MAX_SINGLE_THEME=${MAX_SINGLE_THEME:-100}
MIN_CASH_FLOOR=${MIN_CASH_FLOOR:-0}
WEIGHT_INCREMENT=${WEIGHT_INCREMENT:-5}
MIN_POSITION=${MIN_POSITION:-3}

# Which positions to validate
POSITIONS_KEY="positions"
LABEL="Current Positions"
if [[ "${1:-}" == "--proposed" ]]; then
  POSITIONS_KEY="proposed_positions"
  LABEL="Proposed Positions"
fi

echo "═══════════════════════════════════════════════════"
echo "  Portfolio Validator — $LABEL"
echo "═══════════════════════════════════════════════════"
echo ""
echo "Constraints (from investment-profile.md):"
echo "  Max single ETF weight:     ${MAX_SINGLE_ETF}%"
echo "  Max single theme/category: ${MAX_SINGLE_THEME}%"
echo "  Min cash/T-bill floor:     ${MIN_CASH_FLOOR}%"
echo "  Weight increment:          ${WEIGHT_INCREMENT}%"
echo "  Min position size:         ${MIN_POSITION}%"
echo ""

python3 - "$POSITIONS_KEY" "$MAX_SINGLE_ETF" "$MAX_SINGLE_THEME" "$MIN_CASH_FLOOR" "$WEIGHT_INCREMENT" "$MIN_POSITION" <<'PYEOF'
import json, sys

positions_key = sys.argv[1]
max_single_etf = int(sys.argv[2])
max_single_theme = int(sys.argv[3])
min_cash_floor = int(sys.argv[4])
weight_increment = int(sys.argv[5])
min_position = int(sys.argv[6])

with open("config/portfolio.json") as f:
    data = json.load(f)

positions = data.get(positions_key, [])
cash_pct = data.get("cash_pct", 0)

if not positions:
    print(f"⚠️  No {positions_key} found in portfolio.json")
    sys.exit(0)

errors = 0
warnings = 0

# 1. Total weight
total = sum(p["weight_pct"] for p in positions) + cash_pct
print(f"📊 Total allocation: {total}% (positions: {total - cash_pct}% + cash: {cash_pct}%)")
if total != 100:
    print(f"  ❌ FAIL: Weights sum to {total}%, must equal 100%")
    errors += 1
else:
    print("  ✅ PASS: Weights sum to 100%")
print()

# 2. Single ETF weight
print("📊 Single ETF weight check:")
for p in positions:
    t, w = p["ticker"], p["weight_pct"]
    if w > max_single_etf:
        print(f"  ❌ FAIL: {t} at {w}% exceeds max {max_single_etf}%")
        errors += 1
    elif w == max_single_etf and max_single_etf < 100:
        print(f"  ⚠️  WARN: {t} at {w}% — at maximum limit")
        warnings += 1
    else:
        print(f"  ✅ {t}: {w}%")
print()

# 3. Theme/category concentration
print("📊 Theme/category concentration:")
cats = {}
for p in positions:
    theme = p.get("category", "unknown").split("_")[0]
    cats.setdefault(theme, []).append(p)
for theme in sorted(cats):
    tt = sum(p["weight_pct"] for p in cats[theme])
    tks = ", ".join(p["ticker"] for p in cats[theme])
    if tt > max_single_theme:
        print(f"  ❌ FAIL: {theme} at {tt}% ({tks}) exceeds max {max_single_theme}%")
        errors += 1
    else:
        print(f"  ✅ {theme}: {tt}% ({tks})")
print()

# 4. Cash floor
print("📊 Cash/T-bill floor check:")
cash_cats = {"fixed_income_cash", "cash"}
cash_total = cash_pct + sum(
    p["weight_pct"] for p in positions if p.get("category", "") in cash_cats
)
if cash_total < min_cash_floor:
    print(f"  ❌ FAIL: Cash {cash_total}% below min {min_cash_floor}%")
    errors += 1
else:
    print(f"  ✅ Cash/T-bill: {cash_total}% (min: {min_cash_floor}%)")
print()

# 5. Weight increment
print(f"📊 Weight increment check (multiples of {weight_increment}%):")
for p in positions:
    t, w = p["ticker"], p["weight_pct"]
    if w % weight_increment != 0:
        print(f"  ❌ FAIL: {t} at {w}% — not a multiple of {weight_increment}%")
        errors += 1
    else:
        print(f"  ✅ {t}: {w}%")
print()

# 6. Min position size
print(f"📊 Min position size check (min {min_position}%):")
for p in positions:
    t, w = p["ticker"], p["weight_pct"]
    if w < min_position:
        print(f"  ❌ FAIL: {t} at {w}% — below min {min_position}%")
        errors += 1
    else:
        print(f"  ✅ {t}: {w}%")
print()

# 7. Duplicates
print("📊 Duplicate ticker check:")
tickers = [p["ticker"] for p in positions]
dupes = [t for t in set(tickers) if tickers.count(t) > 1]
if dupes:
    for d in dupes:
        print(f"  ❌ FAIL: {d} appears {tickers.count(d)} times")
        errors += 1
else:
    print("  ✅ No duplicates")
print()

# 8. Required fields
print("📊 Required fields check:")
req = ["ticker", "name", "category", "weight_pct", "thesis_ids", "entry_date"]
for p in positions:
    missing = [f for f in req if f not in p or p[f] is None]
    if missing:
        print(f"  ❌ FAIL: {p.get('ticker','???')} missing: {', '.join(missing)}")
        errors += 1
    else:
        print(f"  ✅ {p['ticker']}: all fields present")
print()

# Summary
print("═══════════════════════════════════════════════════")
if errors == 0 and warnings == 0:
    print("✅ ALL CHECKS PASSED")
elif errors == 0:
    print(f"⚠️  PASSED with {warnings} warning(s)")
else:
    print(f"❌ FAILED: {errors} error(s), {warnings} warning(s)")
print("═══════════════════════════════════════════════════")
sys.exit(1 if errors > 0 else 0)
PYEOF
