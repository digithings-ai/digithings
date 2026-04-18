---
name: sector-healthcare
description: Deep-dive analysis of the Healthcare sector (XLV, IBB, XBI). Covers pharma, biotech, managed care, medtech, and regulatory environment. Run as part of the US Equities phase in the daily orchestrator.
---

# Healthcare Sector Sub-Agent

## Inputs
- `config/watchlist.md` (healthcare ETFs)
- `config/preferences.md` (XLV is a current portfolio holding)
- Macro regime output from `macro.md`

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any FDA action page, earnings release, drug approval article, or healthcare news URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Sector ETF Overview
- **XLV** (Health Care SPDR): price, % change, vs 50-DMA and 200-DMA
- **IBB** (iShares Biotech ETF): price, % change — biotech is high-beta within healthcare
- **XBI** (SPDR Biotech Equal-Weight): small/mid-cap biotech indicator
- XLV vs SPY relative strength: is healthcare outperforming or underperforming the market?
- Key context: XLV is a **defensive holding** — assess if that defensiveness is holding

### 2. Subsector Breakdown
- Managed Care / Insurance (UNH, CI, HUM)
- Large-cap Pharma (JNJ, LLY, MRK, ABBV)
- Biotech (IBB, XBI)
- Medical Devices / MedTech (MDT, ABT, SYK)

### 3. Regulatory & Policy Environment
- CMS reimbursement updates, FDA pipeline, drug pricing, antitrust

### 4. Earnings & Catalysts
- Major healthcare names reporting, trial data readouts, conference season, M&A

### 5. Valuation Context
- XLV NTM P/E vs history

### 6. Macro Regime Fit
- Healthcare as defensive allocation; check regime fit explicitly

### 7. Portfolio Assessment
- XLV thesis holding? Maintain/increase/reduce?

---

## Output Format

```
### 🏥 HEALTHCARE SECTOR
**Bias**: [Overweight / Underweight / Neutral] | Confidence: [High / Medium / Low]

**ETF Levels**: XLV: $X (±X%) | IBB: $X (±X%) | XBI: $X (±X%)
**vs 200-DMA**: XLV [above/below by X%]
**Relative Strength vs SPY**: [Outperforming / Underperforming / In-line]

**Subsector Read**:
- Managed Care: [direction + catalyst]
- Large Pharma: [driver]
- Biotech: [risk-on/off + PDUFA dates]

**Regulatory Signal**: [CMS/FDA/pricing]
**Valuation**: XLV NTM P/E ~Xx
**Regime Fit**: [favorable/unfavorable]
**Portfolio Note**: XLV thesis [✅/⚠️/❌] — [rationale]
```

