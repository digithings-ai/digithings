# SDCA Reference Site Analysis — Investing Campus "BTC Strategic Dollar Cost Averaging Signal"

**Site:** https://sdca-signals-automation-production-bdd2.up.railway.app/
**Date of analysis:** 2026-09-25 (site's own "live" data timestamp: September 25, 2026)
**Method:** Playwright MCP browser automation (Chrome extension unavailable in this background job), live interaction — data load, tab-by-tab snapshots/screenshots, indicator-toggle experiments, sidebar-collapse test, and a client-side JS state probe.

This document is a **descriptive record only**. It does not propose changes to DigiQuant's SDCA strategy or draw conclusions about what DigiQuant should adopt. Comparison notes at the end are purely observational.

---

## Overview

The site is a single-page app (React/Next.js-style SPA, confirmed via `window.__TYPEDARRAY_POOL`/`__TEXT_CACHE` globals suggesting a canvas-based charting library — no `window.__NEXT_DATA__` or other inspectable app-state object was found; see "Open questions"). It has one page with:

- A collapsible left sidebar containing: a "Load BTC Data" control, a "Today's Model Action" convenience panel, a stats block, a 4-checkbox indicator toggle list, and a "Live band levels" table.
- A main content area with 3 tabs: **EQM Rainbow**, **Composite Risk**, **Accum/Dist Curve**.

After clicking "Load BTC Data," the site reported: **"Loaded 5,883 daily candles."** (100.0% progress). All figures below are as observed immediately after that load, with BTC price at **$84,319.92** (later re-rendered once as $83,972.80 and $84,319.92 across different indicator-toggle states — likely a live/streaming price tick rather than a bug).

The architecture is **far simpler than DigiQuant's current SDCA**: 4 indicators total, combined by **equal-weighted voting** (not z-score-optimized/learned weights), versus DigiQuant's up to 17 z-score-weighted indicators. See "Comparison notes for DigiQuant" for a purely descriptive rundown.

---

## Indicators

The sidebar's "Indicators" section carries this verbatim description text:

> "Toggle which signals blend into Composite Risk/Z-score, which drive the Composite tab and the Accum/Dist Curve backtest. Each enabled indicator is an equally weighted vote; with only the price valuation on, the composite equals the pure Asymmetric Tail Curvature z-score."

This claim was **directly tested and confirmed** (see "Indicator-toggle experiment" below): with only the price indicator checked, the "Composite Z-score" field became numerically identical to the "Current EQM Z-score" field in "Live band levels."

### 1. Asymmetric Tail Curvature (price)
- **Default state:** enabled (checked)
- **Verbatim label:** "Asymmetric Tail Curvature (price)"
- **Observed mechanism:** This is the site's core price-valuation model, referred to elsewhere as "EQM" (e.g., "Current EQM Z-score," "Bitcoin Asymmetric Tail Curvature Rainbow"). It appears to be a quantile-regression fit of log(price) vs. time (or log-time), producing a median rail (Q50%) and outer rails (Q1%, Q99%) that bound a log-log "rainbow" of BTC price history — structurally similar to a power-law fit. "Asymmetric" and "Tail Curvature" in the name suggest the regression allows different curvature/skew above vs. below the median, rather than a simple symmetric band.
- **Not observable from the UI alone:** the exact regression form (power-law vs. logistic vs. spline), the quantile levels used to fit the curve (only Q1/Q50/Q99 are *displayed*, but more quantiles may exist to define the finer band structure), and the exact z-score formula.

### 2. Sharpe (realized P/L, 14d EMA)
- **Default state:** disabled (unchecked)
- **Verbatim label:** "Sharpe (realized P/L, 14d EMA)"
- **Observed mechanism:** Not directly visible on any chart in this session (no dedicated tab/view for it was found). Name suggests a rolling Sharpe-like ratio (return/volatility) computed from realized profit/loss, smoothed with a 14-day EMA. Enabling it materially pulled the blended Composite Z-score down (see toggle experiment, +0.46 → -0.09 when added to the 3-indicator default), implying it was reading as risk-elevated/less-favorable at the time of observation.
- **Not observable from the UI alone:** the exact realized-P/L definition (cohort-based? UTXO-based?), the Sharpe windowing, or its z-scoring method.

### 3. Cost Basis Profit/Loss Ratio (7d EMA)
- **Default state:** enabled (checked)
- **Verbatim label:** "Cost Basis Profit/Loss Ratio (7d EMA)"
- **Observed mechanism:** Not directly visible on any chart. Name suggests an on-chain-style metric comparing current price to aggregate holder cost basis (akin to MVRV-family ratios), 7-day EMA smoothed.
- **Not observable from the UI alone:** exact formula or data source (on-chain cost-basis data, exchange data, etc.).

### 4. Onchain Risk Composite (7d EMA)
- **Default state:** enabled (checked)
- **Verbatim label:** "Onchain Risk Composite (7d EMA)"
- **Observed mechanism:** Described as itself a "composite" — likely a pre-blended combination of multiple on-chain metrics (the name doesn't disambiguate which), 7-day EMA smoothed, entering the top-level Composite Risk as a single equally-weighted vote.
- **Not observable from the UI alone:** which on-chain metrics feed this sub-composite, or their internal weighting.

**None of the 4 indicators has its own dedicated chart/view in the UI** — only the price indicator (EQM) gets a dedicated visualization (the EQM Rainbow tab). The other 3 are only observable indirectly, through their effect on the blended Composite Risk/Z-score when toggled.

---

## Composite construction

- **Equal-weighted voting**, not learned/optimized weights: each enabled indicator contributes one equally-weighted vote to "Composite Z-score." This was directly verified (see below).
- Two distinct **band/tier taxonomies** exist side by side and must not be conflated:
  1. **6-tier price-only band system**, tied purely to the Asymmetric Tail Curvature (EQM) quantile rails, shown in "Live band levels" and on the EQM Rainbow chart:
     - Fire sale: 1–10% ($69.9K–$83.2K)
     - Accumulate: 10–25% ($83.2K–$98.3K)
     - Value: 25–50% ($98.3K–$124K)
     - Above mid: 50–75% ($124K–$142K)
     - Hot: 75–95% ($142K–$173K)
     - Bubble: 95–99% ($173K–$209K)
  2. **4-tier blended Composite Risk band system**, shown only on the Composite Risk tab as filterable legend buttons:
     - 0–25% Buy Zone
     - 25–50% Accumulate
     - 50–75% Trim
     - 75–100% Sell Zone

- **Two "Composite Risk" numbers are shown simultaneously in the stats block**, and behave differently:
  - One value (observed as **10.8%** in every toggle state tested) stayed constant regardless of which indicators were enabled — it never moved across price-only, 3-indicator-default, or all-4 states. This strongly suggests it is **not actually blended** — most likely a static price-only/EQM percentile-rank figure that happens to share the "Composite Risk" label.
  - The other value tracked "Today's Model Action → Composite Risk today" exactly, and changed with every indicator-toggle combination tested: **16.1%** (price only) → **42.3%** (default: price + cost basis + onchain) → **51.6%** (all 4). This is the true blended composite risk.
  - This dual-labeling (same visible text "Composite Risk" used for two different underlying numbers) is very likely a **UI/labeling quirk on the reference site**, not two intentionally-different published metrics — flagged explicitly in "Open questions" rather than assumed.

- **"Composite Z-score" also appears twice**, but both instances always showed the *same* value in every state tested (+0.46 / +0.46 at default; +2.03 / +2.03 price-only; -0.09 / -0.09 all-4) — consistent with a simple duplicate render of one underlying number, not two distinct metrics.

### Indicator-toggle experiment (directly performed)

| Indicators enabled | Composite Z-score | Composite Risk today | Curve rate today | Action |
|---|---|---|---|---|
| Price only | **+2.03** (exactly matches "Current EQM Z-score") | 16.1% | +8.89%/day | BUY 8.89% of cash |
| Price + Cost Basis + Onchain (**default**) | +0.46 | 42.3% | +0.00%/day | HOLD — no trade today |
| All 4 (+ Sharpe) | -0.09 | 51.6% | +0.00%/day | HOLD — no trade today |

This **confirms** the site's own claim ("with only the price valuation on, the composite equals the pure Asymmetric Tail Curvature z-score") — the price-only Composite Z-score (+2.03) is numerically identical to "Current EQM Z-score" (+2.03) shown in "Live band levels." Adding Cost Basis + Onchain pulled the composite from +2.03 down to +0.46 (both currently reading less risk-elevated than pure price valuation, at time of observation). Adding Sharpe on top pulled it further down to -0.09 (Sharpe was reading as unfavorable/risk-elevating relative to the other three, at time of observation — direction consistent with, but not proof of, the description in indicator #2 above).

**Sign-convention note (important, flagged as an observation, not fully explained):** at the time of observation, BTC price sat in the "10–25% · Accumulate" band — the second-cheapest of 6 tiers — while the "Current EQM Z-score" was **positive** (+2.03), and the price-only Composite Risk (16.1%) was low (buy-favorable), driving a strong BUY action. This means **positive EQM z-score corresponds to cheap/buy territory here, not expensive/sell territory** — i.e., the site's z-score sign convention (or the underlying "Asymmetric Tail Curvature" fit itself) runs opposite to the naive assumption that a positive z-score means "above the model/expensive." This was directly observed via the toggle experiment, not merely inferred from static values, but the *cause* (inverted sign convention vs. a nonlinear/asymmetric z-to-risk mapping) is not determinable from the UI alone.

---

## Views

### EQM Rainbow (default tab)
- **Screenshot:** `.playwright-mcp/01-eqm-rainbow.png`
- **Chart type:** log-scale price-vs-time line chart, x-axis years 2012–2026, y-axis log price from ~$100M(?) down to $1 up through $100k (axis labels read "$100m, $1, $10, $100, $1k, $10k, $100k" — likely a rendering/ordering quirk in the accessibility tree read-out, not necessarily the true visual order; see screenshot for ground truth).
- **Chart title (verbatim):** "Bitcoin Asymmetric Tail Curvature Rainbow — September 25, 2026 live"
- **Content:** a white BTC price line overlaid on 6 colored horizontal-band "rainbow" regions (blue/teal = cheap, at bottom; red = expensive, at top), a diamond marker at the current price/date point, and a legend listing:
  - BTC price
  - z-score +2.03
  - Q99% rail $209K
  - Q1% rail $69.9K
  - Q50% median $124K
  - All 6 named bands with their price ranges (same as the "Live band levels" table above)
- **"Show legend" checkbox** — present on this tab, checked by default; controls legend visibility (not click-tested beyond confirming its presence/default state).

### Composite Risk
- **Screenshot:** `.playwright-mcp/02-composite-risk.png`
- **Heading:** "Composite Risk"
- **Verbatim subtitle:** *"Composite Risk is valuation risk, not DCA allocation. Low risk = cheaper / more buyable; high risk = expensive / less buyable."*
- **Chart type:** dual-axis time series, 2012–2026, log price on the left axis and 0–100% risk on the right axis; a risk-colored line (green/teal/orange/red segments tracking the 4-tier band) with dashed horizontal reference lines at 25/50/75%.
- **Controls on this tab:** 4 zone-filter toggle buttons ("0-25% BUY ZONE," "25-50% ACCUMULATE," "50-75% TRIM," "75-100% SELL ZONE"), a "Z-SCORE" toggle, a "SHOW Z LINE" checkbox (checked by default), and a bottom mini-chart range-selector strip (not interacted with).

### Accum/Dist Curve
- **Screenshot:** `.playwright-mcp/03-accum-dist-curve.png`
- Documented in full detail in the next section — this is the tab of greatest interest per the task brief.

---

## Accum/Dist Curve mechanics

**Heading:** "Accumulation / Distribution Curve"

**Verbatim description:** *"Pure Composite Risk-driven model — no Z-score gate, no fixed-length tranches. Each day, the curve value at that day's risk level is the % of current cash bought (if positive) or % of current BTC sold (if negative). Drag the nodes to shape it."*

**Verbatim instructions:** *"Drag a node up/down. X-axis = Composite Risk %, Y-axis = % of cash/BTC traded per day."*

### The curve itself
A single continuous **draggable piecewise-linear curve** with **21 control nodes**, evenly spaced every 5% of Composite Risk from 0% to 100% (0%, 5%, 10%, … 100%). Each node's y-value is the day's trade rate: positive = % of current cash bought that day, negative = % of current BTC sold that day, 0 = hold. Y-axis range shown: -10% to +10%.

**Default curve shape** (read directly from the page's node values, confirmed against the screenshot):

| Composite Risk | Rate |
|---|---|
| 0% | +10.0% |
| 5% | +10.0% |
| 10% | +10.0% |
| 15% | +10.0% |
| 20% | +5.0% |
| 25%–80% (12 nodes) | 0.0% (flat) |
| 85% | -0.5% |
| 90% | -2.0% |
| 95% | -4.0% |
| 100% | -10.0% |

Visually (per the screenshot): 4 green nodes plateau at +10%, a single node steps down to +5% at 20% risk, then a long flat 0% shelf from 25%–80% risk (12 nodes, colored neutral blue/grey), then 4 red nodes curving down to -10% at 100% risk. This is a **single-sided asymmetric curve** — aggressive, wide buy plateau at low risk; a long neutral no-trade zone across the middle ~55 percentage points of risk; and a comparatively narrow, steep sell ramp only in the top 15% of risk.

Individual curve nodes render inside a canvas/image element with no accessible per-node references exposed to the automation tooling (only axis tick labels and node *values* were exposed in the accessibility tree, not clickable node handles), so a live drag-and-observe test of one node was not performed in this session — the default shape above was read directly from the rendered values rather than inferred from a screenshot alone.

### Other controls on this tab
- **Export CSV** button (not clicked — file download, out of scope per governance rules).
- **Reset to default curve** button (not clicked, to avoid disturbing the state before capturing it — though this suggests the curve is *editable and persisted in session state*, since a reset option exists).
- **Starting date** textbox (placeholder `YYYY-MM-DD`), default value **2015-01-01**.
- **Starting capital, USD** spinbutton, default value **10000**.
- **Log scale** checkbox (applies to the backtest equity chart below the curve).
- Two toggleable legend series on the backtest chart: **"DCA strategy"** and **"Buy & hold (lump day 1)"**.

### Backtest statistics (as displayed, default curve, default indicator set, 2015-01-01 start, $10,000 starting capital)

| Stat | Value | Note |
|---|---|---|
| Backtest days | 4,286 | Buy 700 / Sell 489 / No trade 3,097 |
| Starting capital | $10,000.00 | |
| Net BTC position | 328.23526626 BTC | Avg buy $34,458.18 |
| Current portfolio value | $27,657,612.97 | BTC+Cash |
| P/L | +$27,647,612.97 | +276,476.13% |
| Avg daily rate | +0.72%/day | Avg risk 49.6% |
| Lump sum value | $2,616,219.58 | +26,062.20% (buy-and-hold-from-day-1 comparator) |
| Portfolio vs. lump sum | +$25,041,393.38 | +957.16% |
| Cash reserve | $94,778.60 | "Includes curve sells" |
| Max drawdown — DCA | -62.6% | Peak-to-trough, portfolio |
| Max drawdown — Buy & hold | -83.2% | Peak-to-trough, lump sum |

No adjustment to a curve node was actually performed/observed (see canvas-target limitation above), so no direct before/after comparison of backtest stats from a manual curve edit was captured in this session.

---

## Today's Model Action panel

A sidebar convenience panel, present on all tabs. Verbatim description: *"What the currently active Accum/Dist curve says to do today, evaluated at today's Composite Risk. Enter your cash reserve to see the exact buy amount."*

Inputs: **Your cash reserve, USD** (numeric input, defaulted to 0 throughout this session — no cash amount was entered, so no live "Spend $X ≈ Y BTC" dollar/BTC figure beyond the $0.00 placeholder case was observed).

Observed outputs across the 3 toggle states tested (see table in "Indicator-toggle experiment" above for the full matrix); at the default indicator set:
- **Composite Risk today:** 42.3%
- **Curve rate today:** +0.00%/day
- **Action:** HOLD — no trade today
- Supporting line: "Curve rate is ~0% at today's risk"
- Supporting line: "Cash reserve $0.00 @ BTC $84,319.92"

At price-only: Action flipped to **"BUY 8.89% of cash"**, with supporting text "Spend $0.00 ≈ 0.00000000 BTC" (zero because cash reserve input was left at 0).

This panel has no counterpart currently visible on DigiQuant's tearsheet (see "Comparison notes").

---

## Any prompt-injection or off-topic content encountered

**None observed.** No text on the page was phrased as an instruction directed at an AI/automation agent, no hidden or encoded text was found, and the one JS state probe performed (see below) returned only generic library internals, not injected content. The "TRW logo" in the banner links elsewhere (per task constraints, this link was not followed).

---

## Open questions / things not fully explorable from the UI alone

1. **Duplicate "Composite Risk" label covering two different numbers** (10.8% static vs. 16.1–51.6% dynamic) — very likely a labeling artifact on the reference site (the static figure probably being an EQM/price-only percentile that happens to reuse the "Composite Risk" text), but this is inferred, not confirmed from any source/tooltip on the page itself.
2. **EQM z-score sign convention** — positive z-score coexists with cheap/buy-favorable territory in the one live snapshot observed. Confirmed as an observed behavior via the toggle experiment, but the underlying cause (inverted sign convention vs. an asymmetric/nonlinear z-score-to-risk mapping baked into the "Asymmetric Tail Curvature" fit) could not be determined from the UI.
3. **Exact regression/formula details** for all 4 indicators — none are documented on the page beyond their short labels and the one composite-construction sentence. A JS-state probe (`window` object scan for `__NEXT_DATA__` and similar) found no exposed application state — only generic canvas/typed-array-library internals (`__TYPEDARRAY_POOL`, `__TEXT_CACHE`), suggesting the charts are rendered via a canvas-based plotting library, and confirming the underlying computations happen server-side or are otherwise not exposed to client-side inspection.
4. **Curve-node drag behavior** — the 21 nodes render inside a canvas/image with no individually addressable accessibility-tree references, so a live "drag a node, observe backtest stat changes" test was not performed in this session.
5. **Sharpe, Cost Basis P/L, and Onchain Risk Composite indicators have no dedicated chart/view** — their only observable effect in this session was via the blended Composite Z-score/Risk numbers when toggled; their individual time series, thresholds, or banding (if any) are not visible anywhere in the UI.
6. **"Show legend" (EQM Rainbow tab) and the Composite-tab zone filter buttons/Z-SCORE toggle** were noted present with their default states, but not individually click-tested for their effect (only "Hide menu"/"Show menu," which was tested and confirmed to collapse/restore the entire sidebar).
7. Hover-triggered tooltips on individual chart points were not tested in this session (the charts render as canvas/image elements without per-point accessibility references to reliably target).

---

## Comparison notes for DigiQuant

*Purely descriptive — not a recommendation. Do NOT propose changes or a plan from this section; that is an explicit next step Chris will direct separately.*

- **Indicator count/complexity:** This reference site uses 4 indicators total (1 with a dedicated chart, 3 blended in "black box" fashion with no individual visualization). DigiQuant's current SDCA architecture uses up to 17 z-score-weighted indicators (power_law, m2, rs_eth, dxy, onchain_mvrv, onchain_asopr, onchain_puell, onchain_rhodl, onchain_addr_ratio, fear_greed, weekly/monthly RSI/MACD variants, sma_band).
- **Weighting method:** This site uses simple **equal-weighted voting** among whichever indicators are currently enabled (a toggleable subset of 4). DigiQuant's current approach uses z-score-weighted blending across all (up to) 17 indicators, not a simple equal vote over a small toggleable subset.
- **Composite scale/labeling:** This site exposes both a raw blended z-score and a percentage "Composite Risk" figure, plus a separate, static, differently-computed number that shares the same "Composite Risk" label (see Open Question #1) — a labeling ambiguity worth being aware of if using this site as a naming/UX reference. It also maintains two parallel band taxonomies (a 6-tier price-only tier system and a 4-tier blended-risk tier system) rather than one unified tier scheme.
- **Curve adjustability:** This site's Accum/Dist Curve is a **user-draggable, 21-node piecewise-linear curve** over 0–100% Composite Risk, with an explicit "Reset to default curve" control, a CSV export, and a live backtest (recomputed against whatever curve shape + indicator-toggle state is currently active, with a configurable backtest start date and starting capital). The default curve shape is asymmetric: a 4-node full-throttle (+10%/day) buy plateau at 0–15% risk, stepping down through a single +5% node at 20%, a long flat 12-node 0%/day neutral shelf from 25–80% risk, then a comparatively short and steep 4-node sell ramp from 85–100% risk bottoming at -10%/day.
- **Things this site has that DigiQuant's tearsheet currently lacks (observationally):**
  - A "Today's Model Action" convenience panel that takes a live cash-reserve USD input and outputs today's recommended dollar/BTC trade in plain English, given the currently active curve and indicator set.
  - A fully interactive, draggable Accum/Dist curve editor with an inline, re-run-on-demand backtest (including a buy-and-hold/lump-sum comparator and max-drawdown-vs-lump-sum stats) directly in the UI.
  - A CSV export of the curve shape.
  - Toggleable indicator inclusion/exclusion at the UI level (rather than requiring a code change) to see its live effect on the composite score/curve output.
- **Things DigiQuant's approach has that this site does not appear to expose:** per-indicator dedicated charts/visualizations for anything beyond the single price-valuation indicator; a z-score-weighted (rather than equal-vote) blending scheme; and a much larger indicator surface (17 vs. 4) spanning macro (m2, dxy), cross-asset (rs_eth), sentiment (fear_greed), and technical (RSI/MACD) categories not represented at all on this reference site.
