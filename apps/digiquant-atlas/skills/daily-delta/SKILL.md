---
name: daily-delta
description: >
  Mon–Sat daily delta analysis. Triggers on weekday digest runs, "run delta", "daily delta",
  or when the operator ran ./scripts/new-day.sh (wraps run_db_first). In DB-first mode, loads the current
  week's baseline snapshot from Supabase, emits a small delta request JSON (ops), then
  materializes a full snapshot and upserts to Supabase (no data/agent-cache/daily writes).
---

# digiquant-atlas — Daily Delta Skill

This skill runs Mon–Sat (non-Sunday). Instead of rewriting everything from scratch, it:
1. Loads this week's baseline + any prior deltas
2. Triages which segments changed materially
3. Emits a **delta request JSON** (targeted ops) only for changed segments
4. Materializes a complete, readable daily state by applying ops to baseline (compiler)

Estimated token savings vs full run: **~70%** on a typical day.

### Research vs portfolio split (weekdays)

- **Through Phase 7B** (delta request + `materialize_snapshot` / published **`digest`**): **research close-out** — the digest is the **single overview** that rolls up all sub-segments. This is the **final step of the Track A** research task ([`cowork/tasks/research-daily-delta.md`](../../cowork/tasks/research-daily-delta.md)); the PM does **not** compile it.
- **Phase 7C–7D**: **portfolio** layer (monitor + PM). When running **Track A only**, **stop after 7B**. Run 7C–7D from [`cowork/tasks/portfolio-pm-rebalance.md`](../../cowork/tasks/portfolio-pm-rebalance.md) (or a combined session if you intentionally merge tracks).

---

## Token Mode Protocol

Caveman mode is **active by default** throughout this pipeline for all process work.

**Keep caveman ON for:**
- Triage announcements and segment classification decisions
- Delta context load status and checkpoint verifications
- Reasoning about which segments to update or carry forward
- Any conversational message to the user about pipeline state

**Switch to normal mode** (`normal mode`) immediately before authoring content that publishes to Supabase:
- Delta ops narrative fields and segment narrative blocks
- Materialized digest content and digest snapshot fields
- Rebalance decision notes
- Deliberation transcript content (Phase 7C, if triggered)
- Evolution post-mortem observations (Phase 9)

Switch back to caveman (`caveman mode`) immediately after each artifact is published.

**Quick test**: text going into a Supabase field → full tokens. Text staying in the conversation → caveman.

---

## Pre-Flight: Delta Context Load

### Step 0: Confirm delta mode (Supabase, not `_meta.json`)
There is **no** `data/agent-cache/daily/{{DATE}}/_meta.json` in the Supabase-first pipeline.

- **Weekday (Mon–Sat)** → you are in **delta** mode unless the user explicitly asked for a full baseline rerun.
- Load the **latest baseline date** from Supabase: most recent `daily_snapshots.date` where `run_type = 'baseline'` and `date <= {{DATE}}`. Treat that as `{{BASELINE_DATE}}`.
- **Delta number** = count of `daily_snapshots` rows with `run_type = 'delta'` for the same ISO week as `{{DATE}}`, plus one for today’s run (logical sequence only).

**If no baseline exists** before `{{DATE}}`: stop and have the operator run a **Sunday baseline** (or a one-off baseline) via `skills/weekly-baseline/SKILL.md` + `materialize_snapshot.py` before applying deltas.

### Step 0.5: Week anchor vs compiler `--baseline-date` (critical)

Two different dates appear in a weekday run — **do not use the Sunday anchor as `materialize_snapshot --baseline-date`** unless that Sunday row is literally the prior calendar day (e.g. Monday after Sunday).

| Concept | Role | Typical value |
|---------|------|----------------|
| **`{{WEEK_ANCHOR_DATE}}`** | Latest `daily_snapshots` row with `run_type=baseline` and `date <= {{DATE}}`. Put this in **`delta-request.json` → `baseline_date`** and in the materialized snapshot’s **`baseline_date`** field after compile. | Sunday of the ISO week |
| **`{{MATERIALIZE_BASELINE_DATE}}`** | The row **`materialize_snapshot.py` loads** before applying ops: **previous calendar day** if that row exists in `daily_snapshots`; if missing (gap), latest snapshot date **strictly before** `{{DATE}}`. | Mon → prior Sun; Tue → prior Mon; etc. |

Run `python3 scripts/run_db_first.py --date {{DATE}}` (or `--dry-run`) and use the printed lines for both values.

### Step 1: Load Config
- `config/watchlist.md` — full asset universe
- `config/investment-profile.md` — investor profile, risk tolerance, asset preferences, regime playbook

**Optional — issuer filings (ad hoc):** If today’s triage touches a **sector read-through** or **named operating company** (not the ETF wrapper), briefly check whether **major issuers** filed an **8-K** / **10-Q** / **10-K** that could change the narrative. Use EDGAR or **`sec-edgar`** MCP; do **not** assume a Supabase filings table exists.

### Step 2: Load This Week's Baseline
Load the baseline snapshot from Supabase for `{{BASELINE_DATE}}` (this is your analytical anchor for the week).

Baseline anchors to extract (note these explicitly before triage):
- Macro regime classification (4 factors)
- Overall bias per segment
- Key market levels (SPY/QQQ/BTC/10Y/DXY/WTI/Gold)
- Sector scorecard state (OW/UW/N per sector)
- Active thesis statuses

### Step 3: Load Prior Deltas (if any)
If this is Delta #2 or later, load the most recent daily snapshot(s) from Supabase for prior delta dates.
These supersede the baseline for any fields they updated.

Announce: "Delta context loaded (DB-first). Baseline: {{BASELINE_DATE}}. Running triage."

### Checkpoint: Pre-Flight (DB-first)
Confirm Supabase connectivity (service role available for publish step) and that baseline snapshot exists for `{{BASELINE_DATE}}`.

---

## Segment Triage Protocol

Compare today's live data against the current state (baseline + any prior deltas). Classify each segment:

| Priority | Segments | Delta Threshold |
|----------|----------|-----------------|
| **Mandatory** | `macro`, `us_equities`, `crypto` | Always write delta — these move materially every day |
| **High** | `bonds`, `commodities`, `forex` | Write delta if: yield/price moved >0.5% from current state OR new CB signal |
| **Standard** | `international`, `institutional` | Write delta if: major regional event OR notable flow direction change |
| **Low** | `alt_data` sub-segments, all 11 sectors | Write delta if: bias shifted OR tracked name moved >1.5% |

**Output the triage summary** before proceeding (so the user can see what's being updated):
```
TRIAGE — {{DATE}} (Delta #{{DELTA_NUMBER}})
━━━━━━━━━━━━━━━━━━━
✏️  Will update: macro, crypto, bonds (+12bps move), technology (NVDA -4%)
➡️  Carrying forward: commodities, forex, international, healthcare, energy, financials, ...

Estimated delta ops: ~10-30 (vs full snapshot rewrite)
```

---

## Phase 1 — Alternative Data Triage (delta ops)

Quickly scan (5 minutes max):
- Sentiment: Fear & Greed index vs baseline level; Reddit/social sentiment direction
- CTA positioning: Any new systematic trigger crossed since baseline?
- Options: Unusual OI or flow changes vs baseline profile
- Politicians/officials: Any new filings, statements, or trades since baseline?

If material change (sentiment shifted >10 pts, new CTA trigger, unusual options flow, new politician trade):
- Prepare delta ops that update `segment_biases.alt_data` and `narrative.alt_data`.

If minimal change (within noise): do nothing for this segment; it will carry forward from baseline/current state.

---

## Phase 2 — Institutional Intelligence Triage (delta ops)

Quickly scan:
- ETF flow direction today vs baseline direction (same/reversed?)
- Any new 13D/13G filings for tracked stocks?
- Any hedge fund news/positioning changes?

If material change (flow reversal, new filing, notable HF move):
- Prepare delta ops that update `segment_biases.institutional` and `narrative.institutional`.

---

## Phase 3 — Macro Delta (MANDATORY — Always Run)

Every day has macro developments: new data prints, Fed speak, overnight geopolitical events.
Even a "quiet" day should have a macro delta noting what didn't change.

Follow `skills/macro/SKILL.md` with delta framing:
- Compare the 4 macro factors (Growth/Inflation/Policy/Risk Appetite) vs baseline state
- Note today's data releases vs expectations
- Capture any central bank signals or geopolitical developments

Always produce delta ops that update:
- `regime` (if changed) and/or `regime.summary`
- `segment_biases.macro`
- `narrative.macro`
- `market_data` (latest key levels used for today)

---

## Phase 4 — Asset Class Deltas (delta ops)

For each asset class, check live data and compare against current state (baseline + prior deltas):

### 4A: Bonds & Rates
Check: 2Y yield, 10Y yield, 2s10s spread, HY spreads, Fed Funds futures
**Write delta** if: 2Y or 10Y moved ≥5bps vs current state, OR new Fed/BOE/ECB/BOJ signal.
→ Prepare delta ops for `segment_biases.bonds` and `narrative.asset_classes.bonds`

### 4B: Commodities
Check: WTI, Brent, Gold, Copper, natgas
**Write delta** if: WTI/Brent moved ≥1%, Gold ≥0.5%, Copper ≥1%
→ Prepare delta ops for `segment_biases.commodities` and `narrative.asset_classes.commodities`

### 4C: Forex
Check: DXY, EUR/USD, USD/JPY, USD/CNH, GBP/USD
**Write delta** if: DXY moved ≥0.3% OR major pair moved ≥0.5%
→ Prepare delta ops for `segment_biases.forex` and `narrative.asset_classes.forex`

### 4D: Crypto (MANDATORY — Always Run)
Crypto moves materially every single day.
Follow `skills/crypto/SKILL.md` with delta framing.
Always produce delta ops for `segment_biases.crypto` and `narrative.asset_classes.crypto`.

### 4E: International
Check: Nikkei 225, DAX, Shanghai Composite, Hang Seng, Sensex, Brazil Bovespa, major EM indices
**Write delta** if: major index moved ≥1% OR significant EM news event
→ Prepare delta ops for `segment_biases.international` and `narrative.asset_classes.international`

### Checkpoint: Phase 4
Sanity check that mandatory segments (macro + crypto + us_equities) will have updated narrative blocks for today.

---

## Phase 5 — US Equities Delta (MANDATORY — Always Run)

Equity market conditions change every session.

Follow `skills/equity/SKILL.md` with delta framing:
- What changed in index levels, breadth, and factor performance vs baseline?
- Which sectors are outperforming vs underperforming baseline?
- Any notable breadth divergences (rally on low breadth, selloff on high breadth)?

Always produce delta ops that update:
- `segment_biases.us_equities`
- `sector_scorecard` (if any sector bias/driver changed)
- `narrative.us_equities`

### Sector Triage
For each of the 11 GICS sectors, check if any tracked names moved >1.5% OR sector ETF moved >1% OR
sector bias would change vs baseline:

If a sector materially changed, update the relevant row(s) in `sector_scorecard` via targeted ops.

---

## Phase 6 — Research segment delta documents

> **REQUIRED on all delta days.** Each segment document is a **full evolved document** — not a patch summary, not a change log. The delta document IS the complete research analysis for that day, derived from yesterday's document by applying targeted section updates. The library's diff view shows what changed between days automatically.

### Delta Document Architecture (CRITICAL — READ BEFORE AUTHORING)

A delta document must be a **complete, readable research document** for the given day:

```markdown
# Macro Analysis — 2026-04-08
> Delta #3 from baseline 2026-04-05 | Wednesday | [Day headline]

## MACRO REGIME CLASSIFICATION
[Complete updated regime table — replace changed rows, carry forward unchanged]

## Key Macro Data Points
[Updated data tables with today's prices, yields, levels]

## Geopolitical Risk Assessment
[Updated narrative — replace stale sections, append new developments]

## Risk Watch — Next 24-72 Hours
[Fresh risk items for this specific day]
```

**NEVER produce this format (wrong):**
- A "Change Summary" listing what changed (brief diff log with bullets)
- An empty payload with only schema metadata (`date`, `segment`, `baseline_date`)
- A document shorter than the baseline — all sections must be present

### Rules for Authoring Delta Documents

1. **Load yesterday's document first** — `documents` where `date = prior_calendar(DATE)` and same `document_key`. Use the baseline if no prior delta exists this week.
2. **Carry forward unchanged sections** — If a section has no new data, keep its content from yesterday verbatim. Only rewrite what actually changed.
3. **Replace specific sections** — Update the relevant tables/paragraphs for today's data (prices, yields, events, regime classification).
4. **Append new developments** — Add today's events to narrative sections rather than removing yesterday's context.
5. **Never trim to a summary** — The output must be a complete research document, readable standalone.
6. **Always publish, even for carried-forward segments** — Update the header date, risk watch, and any data points that shifted. Never leave an empty payload.

### Step 6.1 — Load yesterday's documents
For each segment, load the prior calendar day's full document from Supabase:
```sql
SELECT payload FROM documents
WHERE document_key = 'deltas/macro.delta.md'
  AND date = prior_calendar_date
ORDER BY date DESC LIMIT 1;
```
If no prior delta exists for this week, use the baseline (`macro.md`, date = WEEK_ANCHOR_DATE).

### Step 6.2 — Author full evolved delta documents

**Canonical document key + title list** — produce ALL of the following every delta day.
The `title` column is the **exact string to pass as `--title`** to `publish_document.py`. It must
never contain a date, "Delta", or "Analysis" suffix — the title is the document's permanent name.

#### Core market analysis (mandatory / high priority — always publish)
| `document_key`                  | `--title`         | Priority  |
|---------------------------------|-------------------|-----------|
| `deltas/macro.delta.md`         | `Macro`           | mandatory |
| `deltas/us-equities.delta.md`   | `US Equities`     | mandatory |
| `deltas/bonds.delta.md`         | `Bonds`           | high      |
| `deltas/commodities.delta.md`   | `Commodities`     | high      |
| `deltas/forex.delta.md`         | `Forex`           | high      |
| `deltas/crypto.delta.md`        | `Crypto`          | mandatory |
| `deltas/international.delta.md` | `International`   | standard  |

#### Sectors (11 GICS — publish if material move or new narrative, otherwise carry-forward in UI)
| `document_key`                                       | `--title`                  | ETF  |
|------------------------------------------------------|----------------------------|------|
| `deltas/sectors/technology.delta.md`                 | `Technology`               | XLK  |
| `deltas/sectors/financials.delta.md`                 | `Financials`               | XLF  |
| `deltas/sectors/healthcare.delta.md`                 | `Health Care`              | XLV  |
| `deltas/sectors/energy.delta.md`                     | `Energy`                   | XLE  |
| `deltas/sectors/industrials.delta.md`                | `Industrials`              | XLI  |
| `deltas/sectors/consumer-discretionary.delta.md`     | `Consumer Discretionary`   | XLY  |
| `deltas/sectors/consumer-staples.delta.md`           | `Consumer Staples`         | XLP  |
| `deltas/sectors/communication-services.delta.md`     | `Communication Services`   | XLC  |
| `deltas/sectors/real-estate.delta.md`                | `Real Estate`              | XLRE |
| `deltas/sectors/utilities.delta.md`                  | `Utilities`                | XLU  |
| `deltas/sectors/materials.delta.md`                  | `Materials`                | XLB  |

#### Alternative data / Intelligence (publish when source data available)
| `document_key`                               | `--title`             | Priority |
|----------------------------------------------|-----------------------|----------|
| `deltas/alt/institutional-flows.delta.md`    | `Institutional Flows` | standard |
| `deltas/alt/cta-positioning.delta.md`        | `CTA Positioning`     | standard |
| `deltas/alt/options-derivatives.delta.md`    | `Options & Derivatives` | standard |
| `deltas/alt/political-signals.delta.md`      | `Political Signals`   | low      |
| `deltas/alt/hedge-fund-intel.delta.md`       | `Hedge Fund Intel`    | low      |
| `deltas/alt/sentiment.delta.md`              | `Sentiment`           | standard |

> **Carry-forward rule:** For sector and intelligence segments where no material change occurred, you do NOT need to publish a new row to Supabase — the UI automatically carries the most recent version forward. However, if the prior document is from a baseline (>6 days ago), republish even an unchanged version so the date header is current.

For each segment you do publish:
- `document_key`: per table above
- `title`: per `--title` column above (permanent name — no date suffix)
- `date`: today's date
- `run_type`: `delta`
- `payload.baseline_date`: The Sunday week anchor date
- `payload.content`: The **full markdown document** for this day

### Step 6.3 — Fold into materialized research docs (optional)
```bash
python3 scripts/fold_document_deltas.py --date DATE
```
Upserts folded full JSON per target_document_key and publishes research-changelog for PM consumption.

### Step 6.4 — Digest delta-request (Phase 7)
Author delta-request.json with narrow ops; seed changed_paths from segments that were updated. Then Phase 7B materialize_snapshot using the prior calendar day as baseline-date, with baseline_date = WEEK_ANCHOR_DATE in the envelope.

**Cowork-only task file:** [`cowork/tasks/research-document-deltas.md`](../../cowork/tasks/research-document-deltas.md) if you schedule research folds separately from PM.

## Phase 7 — Emit Delta Request JSON (authoritative weekday output)

Emit a single **Delta Request JSON** (schema: `templates/delta-request-schema.json`) containing:
- `changed_paths[]`
- `ops[]` (set/append/remove) with short `reason` fields

This JSON is the ONLY required delta-day artifact from the agent.

---

## Phase 7B — Materialize & Publish (DB-first)

Have the operator run the compiler to apply ops to **yesterday’s materialized snapshot** (not the week anchor unless they coincide):

```bash
python3 scripts/materialize_snapshot.py \
  --date {{DATE}} \
  --baseline-date {{MATERIALIZE_BASELINE_DATE}} \
  --ops-json '<PASTE_DELTA_REQUEST_JSON_HERE>'
```

Ensure the pasted delta-request JSON includes **`baseline_date`: `{{WEEK_ANCHOR_DATE}}`** (Sunday / week anchor) so the upserted snapshot records the correct anchor. `materialize_snapshot.py` prefers `baseline_date` from the ops envelope when present.

This will also store a rendered Markdown digest in Supabase (`documents` with `file_path='DIGEST.md'`) unless `--no-markdown` is used.

---

## Phase 7C — Delta Portfolio Monitor (Lightweight)

> On delta days, the portfolio layer is a **monitoring pass**, not a full reconstruction.
> The full anti-anchoring analyst → clean-slate → rebalance cycle runs on baseline days.
> Delta days check: did anything change enough to trigger action before the next baseline?

### Step 7C.1: Load Current State
Read `config/portfolio.json` — both `positions[]` (current) and `proposed_positions[]` (last PM recommendation).

### Step 7C.2: Threshold Scan
For each position in `positions[]`, check today's session data against thresholds:

| Trigger | Condition | Action |
|---------|-----------|--------|
| **Thesis broken** | Any active thesis moved to ❌ Challenged for this asset | → Flag URGENT: run full analyst + PM for this position |
| **Invalidation trigger hit** | Price crossed the exit condition in the asset's most recent analyst report | → Flag URGENT |
| **Weight drift ≥10%** | Today's recommended weight (quick estimate from session bias) differs from current by ≥10% | → Flag for full PM review |
| **New opportunity** | Run scoped screener (`skills/opportunity-screener/SKILL.md`, delta mode: max 2 candidates) — any non-held ticker scores Total ≥ +3 | → Flag for deliberation alongside triggered positions |
| **Regime shift** | Macro regime classification changed from baseline (e.g., Risk-on → Risk-off) | → Flag ALL positions for full PM review |

### Step 7C.3: Decision Fork

**If NO triggers fired:**
  ```
  ## {{DATE}}
  - Portfolio monitor: No threshold triggers. All positions within tolerance.
  - Next full review: [next Sunday's date]
  ```
- Skip Phase 7D entirely. Carry forward `proposed_positions` unchanged.
- Save a minimal `rebalance_decision` JSON artifact (schema: `templates/schemas/rebalance-decision.schema.json`) with Status=No triggers.

**If ANY trigger fired:**
- Announce: "Portfolio threshold triggered: [reason]. Running scoped deliberation."
- Run `skills/deliberation/SKILL.md` for ONLY the triggered positions (not the full roster), using **per-ticker** transcripts (`deliberation-transcript/{{DATE}}/{{TICKER}}.json`) and a **`deliberation_session_index`** for the scoped set (`meta.kind: delta_scoped`).
  - Unbounded rounds until `meta.converged` per ticker; recess + light research allowed per deliberation skill
  - Save analyst reports as `asset_recommendation` JSON (published to `documents`)
- Optionally publish a minimal **`pm_allocation_memo`** when any position weight changes materially.
- Then proceed to Phase 7D below (full PM review).

---

## Phase 7D — Portfolio Manager Review (Delta — Only If Triggered)

> This phase runs only when Phase 7C flagged a trigger. On quiet delta days, it is skipped.

Follow `skills/portfolio-manager/SKILL.md` Phases B and C:

- **Phase B (Clean-Slate)**: build clean-slate portfolio.
- **Phase C (Comparison)**: diff vs `config/portfolio.json` current positions; apply ≥5% threshold.

Output artifacts (JSON-first):
- `rebalance_decision` (schema: `templates/schemas/rebalance-decision.schema.json`)

---

## Phase 8 — Metrics refresh (optional) + Commit

In DB-first mode, Phase 7B already upserted today’s snapshot/positions/theses/documents.
`python3 scripts/update_tearsheet.py` remains optional for NAV/metrics refresh (benchmark series live in `price_history`; legacy `benchmark_history` was removed in migration 010).

Then commit repo changes if any:
`./scripts/git-commit.sh`

---

## Phase 9 — Post-Mortem & Evolution

Follow Phase 9 (`skills/orchestrator/SKILL.md`) exactly. The evolution loop runs every day, even
on delta days. The post-mortem is lightweight on delta days — just update quality-log.md with
today's delta quality assessment.

```markdown
## {{DATE}} — Delta #{{DELTA_NUMBER}} Post-Mortem

**Segments updated**: [list]
**Segments carried forward**: [list]
**Triage accuracy**: Were the right segments updated? Any that should have been skipped or added?
**Materialization quality**: Did the materialized digest read naturally as a complete digest?
**Portfolio actions**: [rebalance decision summary or "No changes"]
```

