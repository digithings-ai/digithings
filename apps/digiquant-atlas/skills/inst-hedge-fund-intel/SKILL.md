---
name: institutional-hedge-fund-intel
description: Gathers 7-day positioning signals, public commentary, and disclosed trades from 16 tracked funds across Value, Quant/Systematic, Long/Short Equity, and Macro strategy types. Sources include CNBC/Bloomberg interviews, SEC filings, X/LinkedIn posts, and public letters.
---

# Hedge Fund Intelligence Sub-Agent

## Purpose
The world's best investors — both fundamental and systematic — leave signal trails. Their public commentary, SEC filings, and media appearances reveal conviction changes and regime views. This skill systematically gathers available signals from tracked funds across 4 strategy archetypes. Run in the Institutional Intelligence phase.

## Inputs
- `config/hedge-funds.md` — master fund reference with sources and investment style

## Workflow (from registry — keep in sync)

1. Scan EDGAR for any 13D/G/F filings in the last 7 days for tracked CIKs
2. Check X accounts for any direct fund communications (where listed)
3. Search for recent media coverage of each fund
4. Synthesize into a **HF Consensus** signal per asset class

**HF Consensus Signal**: Bullish / Bearish / Mixed / No Signal
- **Bullish**: 3+ funds with recent buys or positive commentary
- **Bearish**: 3+ funds with recent sells, shorts, or negative commentary
- **Mixed**: funds disagree
- **No Signal**: no material intelligence available

> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any media interview page, EDGAR filing, investor letter, or fund commentary URL. Not for API endpoints, `.json`, or `.md` files.

---

## Research Steps

### 1. Media (7-Day Search)
Search for interviews/appearances for major managers in last 7 days and extract actionable views.

### 2. Social Posts
Scan high-signal accounts (Ackman, Dalio, Asness) for last-7d commentary.

### 3. SEC EDGAR Recent Filings
Check for new 13F/13D/13G/Form 4 filings where relevant.

### 4. Letters / Research
Check for any public investor letters or research pieces in last 30 days.

### 5. Synthesize Themes
Identify consensus, divergence, and regime read across funds.

---

## Output Format

```
### 🏦 HEDGE FUND INTELLIGENCE (7-Day Scan)

**Active Signals This Period:**

**Category A: Value & Generalist**
- Berkshire: [signal] / [No new]
- Pershing (Ackman): [signal]

**Category B: Quant & Systematic**
- Bridgewater (Dalio): [signal]
- AQR (Asness): [signal]

**Category C: Long/Short Equity**
- Tiger Global: [13F highlights]
- Coatue: [AI/tech conviction]

**Category D: Macro Legends**
- Druckenmiller: [comment]
- Paul Tudor Jones: [comment]

**Cross-Fund Synthesis:**
- **Consensus theme**: [...]
- **Divergent view**: [...]
- **Macro regime read**: [...]

**Implication for Portfolio:**
[2-3 sentences]
```

