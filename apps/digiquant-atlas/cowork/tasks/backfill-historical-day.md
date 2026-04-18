# Task: Backfill historical day (simulated run)

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Purpose

Replay one historical day as if the full pipeline had run on that date.
Produces canonical Supabase artifacts consistent with the **current implementation**
schema, while restricting all external data to what would have been known **on or
before** `RUN_DATE`.

---

## As-of Date Constraints (mandatory — do not skip)

You are operating as if today is `RUN_DATE`. Apply these rules **everywhere**:

| Data type | Rule |
|-----------|------|
| **Prices / technicals** | Use the Supabase context block below (already filtered to `<= RUN_DATE`). Do **not** re-query live tables. |
| **Macro series** (FRED, FX, Treasury, F&G) | Same — use the context block. |
| **News / analyst commentary** | Every web search must include a date constraint: `before:RUN_DATE` or equivalent. Only accept sources with a clear publication timestamp ≤ `RUN_DATE`. |
| **Forward-looking content** | Any article dated *after* `RUN_DATE`, or any projection referencing events after `RUN_DATE`, must be excluded or marked *[forward-looking — excluded]*. |
| **Continuity / prior context** | Load `daily_snapshots` for the **prior trading day** only (the "Prior snapshot context" block below). Do **not** load today's or future rows. |

---

## Steps

### 0. Load context

Run to get the structured data layer for `RUN_DATE`:

```bash
python3 scripts/backfill_context.py --date RUN_DATE --print-prompt
```

This prints prices, macro series, prior snapshot, and the exact run prompt.
Treat all numbers in that output as **ground truth** for this session.

### 1. Determine run type

- If `RUN_DATE` is **Sunday** → run **weekly baseline** (`skills/weekly-baseline/SKILL.md`)
- Otherwise → run **daily delta** (`skills/daily-delta/SKILL.md` through Phase 7B)

### 2. Track A — Research (positioning-blind)

Follow the appropriate skill file with as-of date constraints enforced.

**Sunday baseline:**
- Build on the prior week's research (carry-forward + selective rewrites)
- Produce a full `digest-snapshot-schema.json` payload with `run_type: "baseline"`
- Publish: `python3 scripts/materialize_snapshot.py --date RUN_DATE --snapshot-json '<JSON>'`

**Weekday delta:**
- Produce a `delta-request-schema.json` ops payload
- Materialize: `python3 scripts/materialize_snapshot.py --date RUN_DATE --baseline-date PRIOR_DATE --ops-json '<JSON>'`

After publish, validate:
```bash
python3 scripts/run_db_first.py --date RUN_DATE --skip-execute --validate-mode research
```

### 3. Track B — Portfolio (thesis-first)

Follow [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md) for `RUN_DATE`.

**Precondition check:**
```bash
python3 scripts/validate_pipeline_step.py --date RUN_DATE --step track_b_precheck
```

Run all Track B phases using `RUN_DATE` as the document key date.
Publish each artifact with its canonical `document_key`:

| Artifact | document_key |
|----------|-------------|
| `market_thesis_exploration` | `market-thesis-exploration/RUN_DATE.json` |
| `thesis_vehicle_map` | `thesis-vehicle-map/RUN_DATE.json` |
| `deliberation_transcript` (per ticker) | `deliberation-transcript/RUN_DATE/{TICKER}.json` |
| `deliberation_session_index` | `deliberation-transcript-index/RUN_DATE.json` |
| `pm_allocation_memo` | `pm-allocation-memo/RUN_DATE.json` |
| `rebalance_decision` | `rebalance-decision.json` |

### 4. Close-out

```bash
python3 scripts/run_db_first.py --date RUN_DATE --validate-mode pm --skip-execute
python3 scripts/validate_pipeline_step.py --date RUN_DATE --chain track_b
```

---

## Forward-looking exclusion examples

✅ **Allowed** (dated on or before RUN_DATE):
- "Tariff pause announced April 9, 2026" (if RUN_DATE >= 2026-04-09)
- "CPI print April 10" (if RUN_DATE >= 2026-04-10)
- Price data from price_technicals with date <= RUN_DATE

❌ **Excluded** (post-RUN_DATE):
- "Fed meeting decision expected next week" when that meeting is > RUN_DATE
- Any earnings release or economic data print > RUN_DATE
- News articles dated > RUN_DATE

---

## Schema compliance checklist

Before publishing any snapshot, verify:
- `regime.conviction` ∈ {High, Medium, Low}
- `portfolio.posture` ∈ {Defensive, Neutral, Offensive}
- `sector_scorecard` is an **array** of rows where `bias` ∈ {OW, UW, N}
- Each `segment_biases[key]` is `{bias, confidence, key_driver}` (not a flat string)
- `theses[].status` ∈ {NEW, ACTIVE, MONITORING, CHALLENGED, INVALIDATED, PAUSED, CLOSED}

Run schema validator:
```bash
python3 scripts/validate_artifact.py - <<'EOF'
<paste snapshot JSON>
EOF
```
