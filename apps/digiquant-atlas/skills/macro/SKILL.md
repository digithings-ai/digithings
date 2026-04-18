---
name: market-macro
description: Run global macro analysis as part of the daily digest. Covers economic data, central bank policy, geopolitics, and the cross-asset macro regime. In the orchestrator pipeline, run as Phase 3 after alternative data and institutional intelligence phases.
---

# Macro Analysis Skill — v2

## Inputs
- `config/watchlist.md` (macro section)
- `config/preferences.md`
- Sentiment output (Phase 1A) — does sentiment confirm or contradict macro?
- CTA positioning output (Phase 1B) — are systematics aligned?
- Politician/Fed signals output (Phase 1D) — any policy pivot signal?

## Data Layer

> **Read before analysis** — these files contain systematic, source-of-truth numbers fetched via
> free public APIs before the pipeline started. Use them for all numerical lookups.

1. DB-first: read the latest macro levels from Supabase (`daily_snapshots.market_data` / `documents.payload`). Prefer embedded `market_data` / snapshot fields for **yield curve** (1M–30Y), **key spreads** (2s10s, 3m10y), **VIX + SKEW**, **commodities**, **FX**, **credit proxies**, and **crypto** — do not web-browse for numbers that already exist there.

2. **Web search for** (not in the data files):
   - News catalysts explaining *why* things moved
   - Economic calendar: scheduled releases, consensus vs actual
   - Fed/ECB/BOJ speeches, statements, minutes
   - PMI, CPI, NFP, GDP prints and market reactions
   - Geopolitical events and escalation risk
   - Inflation breakevens (TIPS) and real yields — use `mcp_fred_fred_series_observations` with series `T10YIE` (10Y breakeven), `T5YIE` (5Y breakeven), `DFII10` (10Y TIPS real yield)
   - Additional FRED series via `mcp_fred_*`: `CPIAUCSL` (CPI), `PCEPI` (PCE), `UNRATE`, `GDP`, `T10Y2Y` (2s10s spread), `T10Y3M` (3m10y spread), `VIXCLS`

> DB-first: do not require `data/agent-cache/daily`. If you need fresh numbers, run `./scripts/fetch-market-data.sh` (writes to legacy archive paths only) or use MCP sources.
> **Web fetch**: use `defuddle parse <url> --md` instead of WebFetch for any news article, Fed speech transcript, central bank statement, or economic release page. Not for API endpoints, `.json`, or `.md` files.

## Research Steps

### 1. Overnight & Pre-Market Summary
- What happened globally while the user's market was closed?
- Any major data, political events, central bank actions, or geopolitical developments overnight?
- How are US equity futures positioned heading into the open?

### 2. Economic Calendar — Today
Search for today's scheduled economic releases:
- US: CPI, PPI, PCE, NFP, ISM, GDP, retail sales, jobless claims, housing data — whichever are due today
- Eurozone / UK / Japan / China: any major prints
- Time of release and consensus estimate vs. prior
- If already released: actual vs. estimate and immediate market reaction

### 3. Economic Calendar — This Week
- Key data releases scheduled for the rest of the week
- Fed / ECB / BOJ / BOE meetings or speeches
- Treasury auction schedule (can move yields)
- Any major geopolitical events or elections

### 4. Central Bank Watch
- Fed: recent rhetoric, any speeches today, meeting proximity
- ECB: rate path, recent guidance
- BOJ: yen policy, any intervention risk
- BOE: UK-specific macro stress
- PBoC: China stimulus signals

### 5. Inflation Breakevens & Real Rates
- 5Y TIPS breakeven (market-implied inflation expectation): direction vs prior week
- 10Y TIPS breakeven: is inflation expectation rising or falling?
- 10Y real yield (nominal 10Y minus breakeven): positive = headwind for gold/growth; negative = tailwind
- Is the market pricing more or less inflation than the Fed expects?

### 6. Macro Regime Assessment
Classify the current macro regime using all available data including upstream alternative data:
- **Growth**: Expanding / Slowing / Contracting
- **Inflation**: Hot / Cooling / Cold
- **Policy**: Tightening / Neutral / Easing
- **Risk appetite**: Risk-on / Risk-off / Mixed

Also assess: **Recession probability (0-100%)** — based on PMI, yield curve inversion duration, credit spreads
Also assess: **Stagflation risk** — inflation + contraction is the worst-case regime

This 4-factor framework + recession probability + stagflation risk shape every downstream segment bias.

### 7. Yield Curve Recession Signal
- 2s10s spread: current inversion depth and duration
- 3M10Y spread: more historically reliable recession predictor
- Historical context: how long has the curve been inverted? (12-18 months post-inversion = typical recession lag)
- Is the curve re-steepening (bull or bear steepener)? Bull steepening = Fed cutting = bad growth signal.

### 8. Global Fiscal Policy Scan
- US federal deficit trajectory: any Congressional Budget Office update
- Any G7 government issuing unusual amounts of debt? (supply pressure on yields)
- Japan's JGB yield curve control: any BOJ policy adjustment affecting global rates?
- UK Gilts: any fiscal credibility concerns?

### 9. Geopolitical & Structural Risks
- Any active geopolitical risks impacting markets (conflict, sanctions, trade policy, elections)?
- Any structural market risks (liquidity concerns, regulatory changes, systemic stress)?
- Escalation probability assessment for active conflicts (Iran, Taiwan, Russia/Ukraine)

## Output Format

```
### 🌍 MACRO
**Regime**: Growth: [X] | Inflation: [X] | Policy: [X] | Risk appetite: [X]

**Overnight**: [Key overnight developments in 2-3 sentences]

**Today's Data**: [Releases, consensus vs actual if available, market reaction]

**This Week**: [Upcoming key events and dates]

**Central Banks**: [Fed stance | ECB | BOJ | Notable divergences]

**Geopolitical**: [Active risks, if any]

**Macro Implication**: [How the current regime should bias positioning across asset classes]
```

