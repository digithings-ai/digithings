---
name: opportunity-screener
description: >
  Systematic investment opportunity screener. Scans the full ETF watchlist universe against
  today's digest research, macro regime, thesis register, and institutional signals to identify
  tickers worth analyst coverage. Runs after the digest snapshot is available, before the analyst-PM
  deliberation. Produces a ranked shortlist that feeds the analyst roster.
  Triggers:   automatically via Phase 7B of orchestrator, or standalone: "screen opportunities",
  "what looks interesting", "scan the watchlist".
---

# Opportunity Screener Skill

Translate the day's research into a ranked list of tickers worth analyst attention.
This is the bridge between "what happened in markets" and "what should we own."

**Thesis-first Track B:** Prefer a published **`thesis_vehicle_map`** for `{{DATE}}` as the **primary** bridge from [`skills/market-thesis-exploration/SKILL.md`](../market-thesis-exploration/SKILL.md) — see Step 0. If the map is absent, fall back to watchlist-only scoring (legacy path).

---

## Why This Step Exists

Without a screener, the analyst roster defaults to whatever is already in `portfolio.json` plus
1-2 ad-hoc picks the PM noticed. That's ~60 tickers in the watchlist being reduced to ~9 by
gut feel. The screener systematically evaluates the full universe so opportunities don't slip
through because nobody thought to look.

---

## Inputs

Load all of the following (already in session context after synthesis):

1. **`thesis_vehicle_map`** (preferred) — Supabase `documents` payload for `document_key` `thesis-vehicle-map/{{DATE}}.json` when published
2. **`config/watchlist.md`** — Full ETF universe with categories (~60 tickers)
3. **Supabase digest** — `documents` row for `document_key='digest'` (payload is canonical; markdown is derived)
4. **Supabase macro regime** — `daily_snapshots.regime` / `daily_snapshots.segment_biases`
5. **Systematic technicals** — Supabase `price_technicals` / `price_history`
6. **`config/portfolio.json`** — Current holdings (ticker list only — NOT weights)
7. **Segment outputs** already produced this session (DB-first: Supabase documents/payloads)

**Do NOT read `weight_pct` from portfolio.json.** Screener is blinded to current sizing.

---

## Step 0: Thesis vehicle map (preferred)

If **`thesis_vehicle_map`** exists for `{{DATE}}`:

- Extract the union of all `body.mappings[].candidate_tickers` as **map-seeded tickers** (dedupe).
- You **still** run regime + signal + technical scoring for these names (and the full watchlist if capacity allows on baseline days).
- In **Step 3c**, **Pool 2 — Opportunity candidates** must **include** map-seeded non-held tickers that score **Total ≥ +1** before filling remaining slots from generic watchlist ranks (up to the same session caps: 5 baseline / 2 delta).
- Note `thesis_id` linkage in the screener JSON notes field or `meta` when you publish `opportunity_screen`.

If the map is **missing**, proceed with legacy Steps 1–3 only.

---

## Step 1: Regime Filter

Read the macro regime classification. Apply the regime-asset alignment matrix:

| Regime | Favored Categories | Disfavored Categories |
|--------|-------------------|----------------------|
| **Risk-on / Growth** | equity_us_large, equity_us_small, equity_em, crypto | cash, commodity_gold, fixed_income (long) |
| **Risk-off / Recession fear** | cash, fixed_income, commodity_gold | equity_us_small, equity_em, crypto |
| **Inflationary / Stagflation** | commodity_oil, commodity_gold, commodity_other, equity_sector (energy, materials) | fixed_income (long), equity_us_large (growth) |
| **Geopolitical shock** | commodity_gold, commodity_oil, cash | equity_em, equity_intl_developed, crypto |
| **Rate transition (cutting)** | fixed_income (long), equity_us_small, XLRE | cash, commodity_gold |
| **Rate transition (hiking)** | cash, fixed_income (short), commodity_gold | fixed_income (long), XLRE, equity_us_small |

For each ticker in `watchlist.md`, assign a **regime score**:
- **+2** — category is strongly favored in current regime
- **+1** — category is mildly aligned
- **0** — neutral / no strong regime signal
- **-1** — category is mildly disfavored
- **-2** — category is strongly opposed

---

## Step 2: Signal Scan

For each ticker in the watchlist, check whether today's outputs contain a relevant signal.
Score each signal found:

| Signal Source | What to Look For | Score |
|--------------|-----------------|-------|
| **Sector scorecard** | Sector ETF rated Overweight or Strong Buy | +2 |
| **Sector scorecard** | Sector ETF rated Underweight or Strong Sell | -2 |
| **Institutional flows** | ETF appears in notable inflows list | +1 |
| **Institutional flows** | ETF appears in notable outflows list | -1 |
| **Alt data — CTA positioning** | Net long/increasing exposure AND ≤70th percentile (not crowded) | +1 |
| **Alt data — CTA positioning** | Positioning at ≥80th percentile (explicit crowding warning) | **-1 override** (replaces the +1; flag as crowding risk) |
| **Alt data — Options** | Unusual call activity or put/call ratio < 0.7 | +1 |
| **Alt data — Options** | Unusual put activity or put/call ratio > 1.3 | -1 |
| **Thesis linkage** | Ticker is referenced by an active thesis in the current digest snapshot | +1 |
| **Thesis challenge** | Ticker's thesis moved to ⚠️ or ❌ today | -2 (flag) |
| **Cross-asset signal** | Digest calls out this asset class explicitly | +1 |
| **Price momentum** | Segment notes strong trend continuation | +1 |
| **Price momentum** | Segment notes breakdown or reversal | -1 |

> **Crowding note**: A CTA crowding flag doesn't necessarily mean exit the position — it means the *risk/reward of adding* is worse, and an unwind would be faster and sharper than a normal drawdown. Flag it prominently in the screener output so the PM can size accordingly.

Sum the signal scores for each ticker. Combined with the regime score and technical score, compute:

```
Total Score = Regime Score + Signal Score + Technical Score
```

## Step 2B: Technical Score (from data layer)

For each ticker, look up its systematic technical signals (Supabase `price_technicals` preferred; legacy archive acceptable for backtesting) and assign a
**Technical Score (±1)**:

| Condition | Score |
|-----------|-------|
| Above 50DMA AND RSI 40–65 AND MACD bullish | **+1** |
| Below 200DMA AND RSI extreme AND MACD bearish | **-1** |
| Mixed or no data file | **0** |

---

## Step 3: Rank and Filter

### 3a: Score the Full Universe
Build a table with all watchlist tickers scored:

| Ticker | Category | Regime Score | Signal Score | Tech Score | Total | Held? | Notes |
|--------|----------|-------------|-------------|-------|-------|-------|------|

### 3b: Apply Filters
Remove tickers that are **not actionable**:
- Total score between -1 and +1 (no strong signal either way) → **Skip**
- Regime score = -2 AND no offsetting signal score ≥ +3 → **Skip** (regime headwind too strong)

### 3c: Select Analyst Roster

The analyst roster is composed of two pools:

**Pool 1 — Current Holdings (mandatory)**:
Every ticker in `portfolio.json` `positions[]` gets an analyst regardless of score.
The screener score is noted but doesn't filter them out — the analyst and PM must decide
whether to keep, trim, or exit based on the full deliberation.

**Pool 2 — Opportunity Candidates (screener-driven)**:
From the remaining non-held tickers, take the **top 3-5 by Total Score** (must have Total ≥ +2).
These are new opportunity candidates for analyst coverage.

**Cap**: Maximum 5 opportunity candidates per session. If more than 5 qualify, take the top 5.
On delta days (scoped screener), maximum 2 candidates.

---

## Step 4: Produce Screener Output (JSON-first)

Write an `opportunity_screen` JSON artifact (recommended) and publish to Supabase `documents`.

This artifact feeds directly into:
- `skills/asset-analyst/SKILL.md` (analyst roster)
- `skills/deliberation/SKILL.md` (Round 1 roster)
- `skills/portfolio-manager/SKILL.md` (Phase A inputs)

---

## Integration Points

### Baseline Days (Sunday)
- Runs as **Phase 7B** in `skills/orchestrator/SKILL.md`, after synthesis, before deliberation (Phase 7C)
- Full watchlist scan (~60 tickers)
- Top 3-5 opportunity candidates selected

### Delta Days (Mon-Sat)
- Runs as part of the **Phase 7C threshold scan** in `skills/daily-delta/SKILL.md`
- Lightweight: only scan categories relevant to segments that had deltas today
- Max 2 opportunity candidates
- Only runs if the delta portfolio monitor is already triggered (don't run for quiet days)

### Standalone
- Invoke: "screen opportunities", "scan the watchlist", "what looks interesting"
- Loads most recent snapshot as research source

---

## Quality Standards

1. **No lazy defaults** — every score must be justified by a specific observation from today's session data
2. **Regime is the primary filter** — a +3 signal score in a -2 regime category still needs explanation
3. **Anti-signals matter** — explicitly flag strong-avoid tickers (Total ≤ -2) so the PM knows what NOT to consider
4. **Don't overload analysts** — 3-5 new candidates is the sweet spot. More dilutes focus.
5. **Score from session data only** — no web searches, no training data prices. Use what Phases 1-5 already gathered.

