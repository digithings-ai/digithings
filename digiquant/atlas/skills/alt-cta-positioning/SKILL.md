---
name: alt-data-cta-positioning
description: Analyzes CFTC Commitments of Traders (COT) data and systematic/CTA fund positioning across major futures contracts. Tracks speculative net positioning in S&P 500, Treasuries, gold, WTI, EUR/USD, and BTC. Runs early in pipeline to reveal systematic crowding risks.
---

# CTA & Systematic Positioning Sub-Agent

## Purpose
CTAs (Commodity Trading Advisors) and systematic funds move markets mechanically when trends break. Their crowding creates explosive reversals. This skill quantifies their current positioning so we can anticipate forced de-risking or momentum chasing. Run before macro and segment analysis.

## Inputs
- `docs/ops/data-sources.md` (CFTC, futures positioning sources)
- Previous session's CTA output for week-over-week comparison

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any CFTC page, COT report URL, or news article. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. CFTC COT Report — Latest Release
The CFTC releases COT data every Friday for positions as of Tuesday. Search for the latest weekly report data for:
- S&P 500 futures (/ES)
- 10Y T-Note futures (/ZN)
- Gold (/GC)
- WTI (/CL)
- EUR/USD (/6E)
- BTC (/BTC)

### 2. CTA Trend-Following Signal Model
Estimate whether CTAs are adding or reducing positions based on price trends.

### 3. Systematic Crowding Risk Assessment
Flag extreme positioning and estimate potential forced flow if trends break.

### 4. Risk Parity Exposure
Assess correlation regime and potential risk parity stress.

### 5. Vol-Targeting Fund Positioning
Assess VIX level and potential vol-targeting de-risk.

---

## Output Format

```
### 📊 CTA & SYSTEMATIC POSITIONING
**Net Signal**: [Overall systematic fund posture — Risk-On / Risk-Off / Neutral / Mixed]

**CFTC COT Summary (as of [Tuesday date]):**
| Instrument | Levered Funds | vs Prior Week | Extreme? | Crowding Risk |
|------------|--------------|---------------|----------|---------------|
| S&P 500 | [Net long/short] | [±Xk] | [Y/N] | [High/Med/Low] |
| 10Y T-Note | [Net long/short] | [±Xk] | [Y/N] | [rating] |
| Gold | [Net long/short] | [±Xk] | [Y/N] | [rating] |
| WTI Crude | [Net long/short] | [±Xk] | [Y/N] | [rating] |
| EUR/USD | [Net long/short] | [±Xk] | [Y/N] | [rating] |
| BTC | [Net long/short] | [±Xk] | [Y/N] | [rating] |

**CTA Trend Model (estimated current direction):**
- Equities: [Long / Short / Neutral]
- Bonds: [Long / Short / Neutral]
- Gold: [Long / Short / Neutral]
- USD: [Long / Short / Neutral]

**Key Crowding Risks**:
1. [Most extreme position] — if [trigger], estimated $Xbn mechanistic selling

**Risk Parity Signal**: [Stable / Stress]
**Vol-Targeting**: [Within range / Near de-risk threshold]

**Implication for Portfolio**:
[How does CTA positioning affect our positions?]
```

