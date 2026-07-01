---
name: alt-data-onchain-positioning
description: Interprets on-chain Hyperliquid positioning segmented by trader profitability cohort (Hyperdash), reading a pre-computed smart-money-vs-rekt divergence per market (crypto + equity perps). Surfaces distribution / investor-class-divergence as an early conviction/risk overlay. Runs in Phase 1 with zero per-run search cost.
---

# On-Chain Cohort Positioning Sub-Agent

## Grounding Data (use first)

This segment is **deterministically grounded** — do NOT web-search. A `onchain_positioning` object
is injected into PHASE_INPUTS / shared context at `data_layer.market_context.onchain_positioning`,
pre-computed by the pipeline from Hyperdash's public cohort-summary endpoint. Read it as the
factual backbone:

- `overall_divergence` — aggregate `smart_net_bias − crowd_net_bias` in [−1, +1].
- `smart_net_bias` / `crowd_net_bias` — directional bias (long ÷ (long+short), 0..1) of the
  consistently-**profitable** ("smart") and consistently-**unprofitable** ("crowd"/rekt) cohorts.
- `top_divergent_markets` — per-market `{market, divergence, smart_bias, crowd_bias}`, most
  extreme first. Markets span crypto (BTC/ETH/HYPE) **and equity perps** (`xyz:SP500`, etc.).
- `snapshot_ts`, `total_traders` — provenance.

If `onchain_positioning` is **absent or empty** (a Hyperdash outage or no cohort data this run),
do not invent numbers: set `bias: neutral`, `data_quality: absent`, and say so in `notes`.

## Purpose

Hyperdash buckets every tracked Hyperliquid trader by realized profitability. When the
consistently-profitable cohorts lean one way while the consistently-unprofitable ("rekt") cohorts
lean the other, that divergence is an early read on distribution / investor-class divergence —
smart money quietly positioning against the crowd before a move. Now that Hyperliquid lists equity
perps, this read spans crypto **and** equity-index exposure. This is a conviction/risk **overlay**;
it never originates a trade.

## How to read the divergence

- **Large positive `divergence`** (smart long, crowd short) → smart-money-confirm **bullish** for
  that market; supports adding conviction.
- **Large negative `divergence`** (smart short, crowd long) → **distribution / bearish**; the crowd
  is offside. This is the strongest fade signal.
- **Near zero** → cohorts aligned; no edge.
- **Extreme crowd crowding** (very high or very low `crowd_bias` with thin smart presence) → fade
  the crowd, but lower conviction (one-sided data).

---

## Output Format

```
### 🔗 ON-CHAIN COHORT POSITIONING
**Net Signal**: [smart-money-confirm bullish / distribution bearish / aligned / mixed]

**Aggregate (as of [snapshot_ts], [total_traders] traders):**
- Smart-money net bias: [smart_net_bias]   Crowd net bias: [crowd_net_bias]
- Overall divergence: [overall_divergence]

**Most divergent markets:**
| Market | Divergence | Smart bias | Crowd bias | Read |
|--------|-----------|-----------|-----------|------|
| [ticker] | [±] | [0..1] | [0..1] | [smart-confirm / distribution / aligned] |

**Implication for Portfolio**:
[Which holdings or asset-class tilts does this confirm or contradict? Equity perps → equity tilt;
BTC/ETH → crypto tilt. Adjust conviction, not direction-of-record.]
```

Populate the structured fields: `bias` (overall), `smart_money_stance`, `crowd_stance`,
`divergence_signal` (`smart_long_crowd_short` / `smart_short_crowd_long` / `aligned` / `none`),
`top_divergent_markets` (≤5 tickers), and `material_findings` for each notable divergence.
