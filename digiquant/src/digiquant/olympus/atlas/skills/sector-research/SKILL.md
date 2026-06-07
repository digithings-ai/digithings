---
name: sector-research
description: Templated single-sector deep-dive. Parameterized by sectors.yaml — replaces 11 near-duplicate sector-* skills. Run once per GICS sector during Phase 5 fan-out.
---

# Sector Research Sub-Agent (Templated)

This skill is parameterized. The sub-graph injects the target sector's
config from `config/sectors.yaml` (GICS name, ETFs, key sub-segments,
top tickers, structural drivers) through the research agent's
`phase_inputs.sector_config` block. Every prompt below references fields
from that block.

Web fetch: use `defuddle parse <url> --md` instead of WebFetch for
earnings pages, analyst notes, product announcements, or news article
URLs. Not for API endpoints, `.json`, or `.md` files.

---

## Inputs you will see

- `shared_context.config` — watchlist, investment profile, preferences.
- `shared_context.prior_context` — last several days of snapshots +
  latest-per-segment documents (including last session's sector report
  for this same sector, if any).
- `phase_inputs.sector_config` — this sector's row from `config/sectors.yaml`:
  - `slug` — e.g. `sector-technology`
  - `name` — GICS sector name
  - `etfs` — ordered list of ETF tickers (primary first)
  - `subsegments` — named sub-themes with tickers/drivers
  - `top_tickers` — representative names (max ≈10)
  - `key_drivers` — structural catalysts (earnings season, cycle stage, etc.)
  - `nuance_notes` — free-form analyst guidance specific to this sector
- `phase_inputs.macro_regime` — Phase 3 4-factor regime (growth, inflation,
  policy, risk_appetite, regime_label, portfolio_implications).
- `phase_inputs.phase1_signals` — alt-data positioning snapshots (sentiment,
  CTA, options, politician) that should colour the sector read.
- `phase_inputs.equity_overview` — Phase 5A top-down US equity read.

## Research Steps

### 1. Sector ETF overview
Retrieve current levels and momentum for the ETFs listed in
`sector_config.etfs`:
- price and % change (day, week, month)
- position vs 50-DMA and 200-DMA
- relative strength vs SPY (trending up = outperforming; down = rotating out)

### 2. Sub-segment breakdown
For each entry in `sector_config.subsegments`, pull the relevant data
and note the dominant force today. Do not invent sub-segments not in the
config; if the sector has meaningful activity in an area not listed,
mention it in `notes` and flag it as a candidate for config enrichment.

### 3. Top-ticker read
For each name in `sector_config.top_tickers`, note any material move,
news item, or earnings event. Prefer price action that is out of
pattern with the broader sector — that is where the signal is.

### 4. Driver check
Walk through `sector_config.key_drivers` and `nuance_notes` and score
each as confirming, contradicting, or quiet vs today's read. Drivers
the config flagged but today's data does not support get a short
sentence in `notes` so Phase 9 can evaluate the config over time.

### 5. Macro and positioning alignment
- Does the sector's stance align with `phase_inputs.macro_regime`?
  (e.g., cyclicals in an expanding regime, staples in slowing.)
- Do `phase_inputs.phase1_signals` (sentiment, CTA, options) confirm
  the sector bias, or are they a contrarian tell?
- If misaligned, say so and quantify — it's a setup for Phase 7 risk radar.

### 6. Output
Emit a `SectorReport` JSON per schema. Fields:
- `segment` — `sector_config.slug`
- `date` — today
- `bias` — one of: `strong_bullish`, `bullish`, `neutral`, `bearish`,
  `strong_bearish`, `mixed`
- `headline` — 1-sentence dominant force in this sector today
- `material_findings` — up to 5 structured findings with source IDs
- `sources` — every citation referenced by findings
- `notes` — uncertainty, sector-config drift, contradictions
- Sector-specific structured metrics defined by the output model
  (`SectorReport`): ETF-vs-SPY relative strength category, sub-segment
  leader, key driver confirmation count, conviction score.

## Materiality

Skip noise. Include findings that meaningfully change the read on this
sector relative to yesterday's snapshot. Routine drift under 1% is
noise unless there is a catalyst; flag anything ≥1.5% on a tracked
name, any earnings event, any sub-segment regime change.

## Refusal

If the research context is insufficient to score the sector (e.g.,
data layer fallback = `none` and no prior context for this sector),
return the schema with empty `material_findings`, `bias` = `mixed`,
and a `notes` field explaining what is missing. Do not invent numbers.
