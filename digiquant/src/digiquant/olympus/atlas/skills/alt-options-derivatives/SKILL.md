---
name: alt-data-options-derivatives
description: Analyzes options market structure, volatility term structure, gamma exposure, put/call ratios, skew, and unusual options activity. Options markets are leading indicators — they often price in moves before they happen in the underlying. Run early in pipeline before macro and segment analysis.
---

# Options & Derivatives Intelligence Sub-Agent

## Grounding Tools (use first)

- **Volatility data tool (`get_macro_series`)** — the volatility complex is ingested
  from FRED (which republishes the CBOE indices) into Supabase. Call
  `get_macro_series(series_ids=["VIXCLS", "VXVCLS", "VXNCLS", "GVZCLS", "OVXCLS"])`:
  - `VIXCLS` = VIX (1-month S&P implied vol), `VXVCLS` = VIX3M (3-month).
  - `VXNCLS` = Nasdaq-100 vol (VXN), `GVZCLS` = gold vol, `OVXCLS` = crude-oil vol.
  These are exact daily closes — cite them as numbers (with `obs_date`) in `sources`,
  not paraphrased commentary. The term-structure ratio **VIXCLS / VXVCLS** is the
  contango/backwardation regime signal (ratio < 1 = contango/calm; > 1 = backwardation/stress).
- **Coverage gap (be explicit):** put/call ratios, dealer gamma/GEX, max pain, and
  unusual-activity scans have **no free data source** and are no longer fetched. Use the
  VIX term structure + cross-asset vol (VXN/GVZ/OVX) as the sentiment/positioning proxy,
  and explicitly state in the output that GEX/put-call are unavailable rather than
  inventing them. Lower conviction where the proxy is thin.

## Purpose
Options markets reveal institutional hedging, speculative bets, and gamma dynamics that can force dealer hedging flows and cause accelerated price moves. This skill reads the options market as a forward-looking intelligence source. Run before segment analysis.

## Inputs
- `docs/ops/data-sources.md` (options/vol sources)

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any options data page, analysis article, or vol commentary URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Put/Call Ratio Analysis
Collect: Total CBOE P/C, SPY P/C, QQQ P/C, equity-only P/C and compare vs recent history.

### 2. VIX Analysis — Volatility Complex
Assess VIX level + term structure (contango vs backwardation) + VVIX if available.

### 3. SKEW Index
Assess tail-hedging premium.

### 4. Gamma Exposure (GEX) Analysis
Determine positive vs negative gamma, gamma flip level, and gamma walls.

### 5. Max Pain Analysis
Determine max pain level for weekly expiration and proximity.

### 6. Implied Volatility Levels by Sector
Check broad and sector IV, IV rank/percentile where available.

### 7. Unusual Options Activity
Scan for notable sweeps/blocks and infer hedging vs speculation.

---

## Output Format

```
### 🎰 OPTIONS & DERIVATIVES INTELLIGENCE
**Overall Options Sentiment**: [Hedged / Neutral / Complacent / Aggressive Bullish / Extreme Fear]

**Volatility Complex:**
- VIX: X.X | [Interpretation]
- Term structure: 1M: X | 3M: X | 6M: X → [Contango/Backwardation]
- SKEW: X — [Tail hedging elevated/moderate/low]

**Put/Call Ratios:**
- Total: X.XX | SPY: X.XX | Equity-only: X.XX

**Gamma Exposure (GEX):**
- SPX GEX: [Positive/Negative]
- Gamma flip: XXXX | Key walls: support XXXX / resistance XXXX

**Max Pain**: SPX/SPY weekly max pain = XXXX

**Implied Volatility**: SPY 30d IV: X% | IV Rank: X

**Unusual Options Activity:**
- [Name/ETF]: [trade] — [what it implies]

**Implication for Positioning**:
[2-3 sentences on near-term risk and what options structure implies.]
```

