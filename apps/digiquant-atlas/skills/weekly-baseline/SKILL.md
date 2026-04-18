---
name: weekly-baseline
description: >
  Sunday weekly anchor run. Same 9-phase structure as the orchestrator, but authoring is a comprehensive
  weekly review: carry forward last week's material with selective rewrites, append-first enhancements,
  and a forward-looking frame for the week ahead—not a blank-slate rewrite. Produces run_type=baseline
  snapshot JSON in Supabase for Mon-Sat delta chaining.
---

# digiquant-atlas — Weekly Baseline Skill

## Digest = research close-out

The materialized **`digest`** (`documents.digest` + `daily_snapshots`) is the **final research deliverable** for the anchor date — the **single overview** synthesizing all sub-segments. It is produced at the end of this pipeline (orchestrator **Phase 7** + publish), **not** by the portfolio ([`cowork/tasks/portfolio-pm-rebalance.md`](../../cowork/tasks/portfolio-pm-rebalance.md)) task.

## What Sunday is (and is not)

- **Is:** A **weekly anchor** in the database (`run_type: baseline`, full materialized digest JSON for this date) plus a **phased, comprehensive review** of the prior week and a **forward-looking** setup for the week ahead.
- **Is not:** A mandate to **discard** last week’s research and regenerate every paragraph from zero. Treat the latest prior `daily_snapshots.snapshot` and published `documents` as **starting material**—**compress** stale parts, **append** new evidence and levels, **rewrite selectively** where the thesis or regime was wrong.

**Token posture:** Prefer **short delta-style updates** inside each phase when a segment is unchanged (e.g. “No material change vs Saturday; carry forward with one line on levels”), then **one deeper pass** only where last week’s narrative is wrong, thin, or contradicted by data. **Bias to `append`** in narrative fields; use **replace** for wrong facts, outdated levels, or regime labels that must be exact.

On top of the orchestrator flow, this skill adds:
1. **Week Setup Preamble** — full review of last week + calendar for next week  
2. **Week Ahead** — explicit forward bias and triggers Mon–Sat deltas will lean on  

---

## Pre-Flight: Week Setup Preamble

Before the standard Pre-Flight, complete the following steps:

### Step 1: Prior Week Review (carry-forward source)
Read these sources (in order) and internalize without dumping them verbatim to the user:
- **Last materialized digest (primary carry-forward source):** Supabase `daily_snapshots` row for the **latest `date` strictly before** this baseline run (e.g. last Saturday or last trading day). Use its `snapshot` JSON as the **base text and structure** for this Sunday’s output: **keep** what still holds, **tighten** verbose stretches, **append** this weekend’s developments and forward-looking hooks, **rewrite** sections that were wrong or are now misleading.
- Supabase `documents` for `document_key` matching `weekly/{{LAST_WEEK_LABEL}}.json` — if present
- `config/portfolio.json` — current positions and last proposed_positions (note tickers only for now; actual weights reviewed in Phase 7D)

After reading, note internally:
- **Bias trajectory**: Was last week mostly bullish/bearish? Any mid-week regime flips?
- **Thesis hits/misses**: Which theses were confirmed, challenged, or neutralized?
- **Persistent signals**: Any alt-data or institutional signals that were consistent all week?
- **Surprises**: What did the market do that wasn't anticipated in the prior baseline?
- **Portfolio health**: Any pending rebalance actions from last week that went unexecuted? Any positions held longer than their thesis time horizon without a confirmation signal?

### Step 2: Week Ahead Calendar
Scan `docs/ops/data-sources.md` and live web sources for this week's high-impact events:
- FOMC meetings or Fed speeches?
- Major data releases (CPI, NFP, PPI, PCE, retail sales, ISM)?
- Earnings of tracked companies (from `config/watchlist.md`)?
- Geopolitical events, central bank decisions, auctions?

Write a brief internal note ranking events by market-impact potential:
```
HIGH IMPACT: [events that could shift the macro regime]
MEDIUM IMPACT: [events that could shift single segments]  
LOW IMPACT: [routine releases unlikely to move the needle]
```

Announce to user: "Week Setup complete. Prior week reviewed. Starting weekly anchor pipeline (Phase 1 of 9) — carry-forward, selective rewrites, week-ahead bias."

---

## Full Pipeline (weekly review + enhancement)

Follow **all 9 phases** from `skills/orchestrator/SKILL.md` in order, but apply this **Sunday authoring rule** in every phase:

| Do | Avoid |
|----|--------|
| Start from **last week’s published outputs** (digest snapshot + segment docs if present) | Blank-slate prose when prior text is still valid |
| **Append** new data, catalysts, and “what we watch next week” | Re-stating unchanged macro/crypto/sector stories in full |
| **Replace** only wrong numbers, dead theses, or contradicted regime calls | Cosmetic rephrasing of entire sections |
| End each major block with a **forward-looking** line (what would change your mind Mon–Sat) | Pure backward-looking recap with no link to next week |

Phases still run so nothing is skipped; **depth** scales with how much that segment moved vs Saturday’s state. Quiet segments can be **compressed** to a short carry-forward note plus level updates.

Return here after Phase 7 (digest synthesis) to add the Week Ahead Setup section, then publish the DB snapshot.

### After Phase 7 — Research baseline manifest (recommended)
Publish **`research_baseline_manifest`** for the week (schema: `templates/schemas/research-baseline-manifest.schema.json`):
- `document_key`: `research-manifest/{{BASELINE_DATE}}.json` (or your team’s stable convention).
- `week_anchor_date` / `baseline_digest_date`: align with this Sunday’s materialized digest date.
- `documents[]`: list every research artifact key you will maintain Mon–Sat (phase outputs, `sectors/{sector}/{{DATE}}.json`, etc.).
- Optional `prior_context_note`: what you are **carrying forward**, **compressing**, **appending**, or **explicitly reversing** vs last week’s digest (helps Mon–Sat delta authors).

Validate + `publish_document.py --payload -` with `--doc-type-label "Research Baseline Manifest"`.

---

## Phase 7 Addition: Week Ahead Setup

After completing Phase 7 synthesis, include the following content in the **snapshot narrative** under a dedicated block (e.g. `narrative.macro` or a separate `narrative.week_ahead_setup` if you add it to the schema). Keep the content identical to the template below.

```markdown
---

## 📅 Week Ahead Setup — {{WEEK_LABEL}}

**This week's base scenario**: [Macro regime + overall bias heading into the week. 2 sentences max.]

**Highest conviction watch**: [Single most important thing to track this week — one sentence]

**Delta sensitivity**: [What specific data prints or events this week could shift the bias? e.g., "Wednesday CPI: >+0.4% MoM flips bond bias to bearish. <+0.1% sends equities risk-on."]

**Key Events Calendar**:
| Day | Date | Event | Expected Impact | Watch Level |
|-----|------|-------|----------------|-------------|
|     |      |       |                |             |

**Weekly invalidation triggers**:
- [Condition that would force full regime reassessment mid-week]
- [Second condition]

**Baseline anchors** (What baseline values Mon–Sat deltas are compared against):
- SPY: $X | QQQ: $X | BTC: $X | 10Y: X% | DXY: X.XX | WTI: $X | Gold: $X
```

---

## Phase 9 Addition: Prior Week Retrospective


```markdown
## {{DATE}} — Weekly Retrospective

**Baseline accuracy**: How well did last week's baseline predict the week's behavior?
- Macro regime held: [Y/N — commentary]
- Equity bias: [held/missed — why]
- Key thesis: [confirmation/challenge count this week]

**Delta quality**: Which daily deltas were most valuable? Which were unnecessary?

**Week's biggest surprise**: [1-2 sentences]
```

---

## Baseline Completion Checklist

All items from the standard Session Completion Checklist (`skills/orchestrator/SKILL.md`), plus:

- [ ] Prior week rollup reviewed in Supabase or `config/portfolio.json` loaded
- [ ] Week Ahead Calendar scanned (high-impact events identified)
- [ ] Sunday output **builds on** prior `daily_snapshots` / docs (not an unnecessary full rewrite); forward-looking bias explicit
- [ ] Week Ahead Setup captured **inside** the digest snapshot JSON (narrative fields)
- [ ] Full digest snapshot JSON produced (schema `templates/digest-snapshot-schema.json`)
- [ ] Snapshot published to Supabase via `scripts/materialize_snapshot.py --snapshot-json ...`
- [ ] Phase 7C: Analyst outputs published as `documents` (e.g. `positions/{{TICKER}}/{{DATE}}.json`) or embedded per team convention
- [ ] Phase 7D: `rebalance_decision` published via `publish_document.py` (schema `rebalance-decision.schema.json`)

### DB-first publish command

Have the operator run:

```bash
python3 scripts/materialize_snapshot.py \
  --date {{DATE}} \
  --snapshot-json '<PASTE_FULL_SNAPSHOT_JSON_HERE>'
```

This upserts:
- `daily_snapshots` (including `snapshot` + `digest_markdown`)
- `positions`
- `theses`
- `documents` (rendered `DIGEST.md`)

