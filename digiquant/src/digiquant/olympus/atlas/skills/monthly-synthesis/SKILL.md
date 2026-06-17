---
name: monthly-synthesis
description: >
  End-of-month comprehensive synthesis. Reviews all weekly baselines and daily deltas for the
  month to produce a long-term trend analysis and thesis performance review. Triggers when the
  user says "run monthly synthesis", "end of month review", or via monthly-rollup.sh.
---

# digiquant-atlas — Monthly Synthesis Skill

End-of-month review. Synthesizes the full month of weekly baselines + daily deltas into a
comprehensive long-term view. Designed to run on the last trading day of each month.

---

## Pre-Flight: Monthly Context Load

### Step 1: Identify this month's files
- **Weekly baselines**: find baseline snapshots for the month (DB-first: `daily_snapshots` where `run_type='baseline'`)
- **Daily deltas**: find delta snapshots (DB-first: `daily_snapshots` where `run_type='delta'`)
- **Weekly rollups**: monthly range in `documents` (weekly digest artifacts)

### Step 2: Load Core Context
- `config/preferences.md` — active portfolio and theses

Announce: "Monthly synthesis context loaded. Found [N] weekly baselines, [N] delta days. Starting Phase 1."

---

## Phase 1 — Weekly Baseline Review

For each weekly baseline this month (typically 4–5 baselines), read the baseline digest snapshot and note:

1. **Week-opening regime** (4-factor classification)
2. **Week-opening bias** per asset class
3. **Thesis statuses** at week start
4. **Week Ahead Setup section** — what events were flagged as high-impact?

Build an internal table:
```
| Week | Baseline Date | Macro Regime | Equity Bias | Crypto Bias | Bond Bias |
|------|--------------|-------------|------------|------------|-----------|
| W15  | YYYY-MM-DD   | ...          | ...         | ...         | ...       |
```

---

## Phase 2 — Delta Evolution Scan

Read all delta snapshots for this month in chronological order.

For each delta, extract:
- Which segments changed vs which carried forward
- Any bias shifts (especially reversals from the week's baseline)
- Any high-activity days (5+ segments changed = possible regime inflection)

Build a bias timeline:
```
| Date | Delta# | Segments Changed | Macro Regime | Notable Shift |
|------|--------|-----------------|-------------|--------------|
```

Identify:
- **Bias trends**: How many days was each asset class net bullish vs bearish this month?
- **Inflection days**: Dates with the largest number of segment changes
- **Stability windows**: Multi-day stretches with minimal changes (regime was holding)

---

## Phase 3 — Cumulative Regime Assessment

Synthesize the month's regime evolution from the delta scan:

1. **Net direction per macro factor** over the month
2. **Regime stability score**
3. **Critical inflection dates** (with catalysts)

---

## Phase 4 — Asset Class Monthly Performance

For each asset class, synthesize across baselines and deltas:

### Equities
- Month open vs month close for SPY, QQQ, IWM
- Sector leadership rotation during the month
- Any significant factor tilts (value/growth/momentum)

### Crypto
- BTC month open vs close; ETH vs BTC ratio evolution
- Dominant narrative shift during the month

### Bonds & Rates
- 2Y and 10Y yield movement (bps) over the month
- Fed pause/hike/cut probability evolution
- Credit spread direction

### Commodities
- WTI, Gold, Copper month performance
- Any major supply/demand narrative

### Forex
- DXY month performance
- Key pair moves
- Carry trade stress/stability

### International
- Major developed markets performance
- EM standouts (winners and losers)

---

## Phase 5 — Thesis Performance Review

| Field | What to Assess |
|-------|---------------|
| Confirmation count | How many delta days provided confirming signals? |
| Challenge count | How many delta days had conflicting signals? |
| Invalidation check | Did any invalidation trigger get hit? |
| Target proximity | Is the thesis approaching its price/time target? |
| Recommendation | Close / Maintain / Increase conviction / Update thesis |

Flag explicitly: **Any thesis whose invalidation trigger came within 10% during the month.**

---

## Phase 6 — Monthly Synthesis Output

Write the full monthly synthesis as **JSON** using schema `templates/schemas/monthly-digest.schema.json`.

- **`date`** in the payload must be the **month-ending** calendar date (YYYY-MM-DD) per the schema.
- Add a **Cumulative Regime Shifts** block and a **Delta Efficiency Summary** block (see schema narrative guidance).

**Canonical delivery is Supabase** — validate and publish **via stdin** (no `data/agent-cache/` path required for hosted runs):

```bash
python3 scripts/validate_artifact.py - <<'EOF'
{ ... monthly_digest JSON ... }
EOF
python3 scripts/publish_document.py \
  --payload - \
  --document-key monthly/{{YEAR}}-{{MONTH}}.json \
  --title "Monthly synthesis" \
  --category rollup \
  --doc-type-label "Monthly Summary"
```

Use the same `{{YEAR}}-{{MONTH}}` in `document_key` (e.g. `monthly/2026-04.json`). This matches `update_tearsheet.py` logical keys when you run optional disk sync.

---

## Phase 7 — Metrics refresh (optional)

Run: `python3 scripts/update_tearsheet.py`  
Use when you want the full repo ETL to refresh tearsheet-related tables from disk in addition to the `publish_document.py` upsert.

---

## Completion Checklist

- [ ] All this month's weekly baselines reviewed (N baselines)
- [ ] All delta snapshots scanned chronologically
- [ ] Bias timeline constructed (delta evolution scan complete)
- [ ] Cumulative regime shifts identified
- [ ] Asset class monthly performance summarized
- [ ] Thesis performance reviewed (all active theses)
- [ ] Full `monthly_digest` JSON produced with all required sections
- [ ] `validate_artifact.py -` (or file) passed and `publish_document.py --payload -` upserted `documents` with `document_key` `monthly/{{YEAR}}-{{MONTH}}.json`

