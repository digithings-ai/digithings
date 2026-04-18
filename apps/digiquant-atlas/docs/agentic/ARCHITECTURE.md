# digiquant-atlas — System Architecture

> **Last updated**: 2026-04  
> **Pipeline version**: v3 — 9-phase orchestrator with three-tier cadence  
> **Canonical doc:** this file is the single long-form architecture narrative; [`docs/ARCHITECTURE-REVIEW.md`](../ARCHITECTURE-REVIEW.md) redirects here.

---

## Where to read what

| Need | Doc |
|------|-----|
| **Cowork schedules (how the repo is run day-to-day)** | [`cowork/tasks/README.md`](../cowork/tasks/README.md), [`cowork/PROJECT.md`](../cowork/PROJECT.md) |
| Operator commands and validation | [`RUNBOOK.md`](../../RUNBOOK.md) |
| Baseline / delta / recovery procedures | [`WORKFLOWS.md`](WORKFLOWS.md) |
| Skill index (filesystem source of truth) | [`SKILLS-CATALOG.md`](SKILLS-CATALOG.md) |
| IDE / Copilot / Cursor setup | [`PLATFORMS.md`](PLATFORMS.md) |
| Dated health / score snapshot | [`../SYSTEM-SCORECARD.md`](../SYSTEM-SCORECARD.md) |

---

## Operational scope (Cowork-first)

**In scope for ongoing operation**

| Track | What | Task entry points |
|-------|------|-------------------|
| **Research (Track A)** | Weekly baseline, weekday delta, month-end synthesis — publish **`digest`** and segment research to Supabase | [`research-weekly-baseline.md`](../cowork/tasks/research-weekly-baseline.md), [`research-daily-delta.md`](../cowork/tasks/research-daily-delta.md), [`research-monthly-synthesis.md`](../cowork/tasks/research-monthly-synthesis.md), or [`recurring-scheduled-run.md`](../cowork/tasks/recurring-scheduled-run.md) |
| **Portfolio (Track B)** | After research exists: thesis → vehicle map → PM / **`rebalance_decision`** | [`portfolio-pm-rebalance.md`](../cowork/tasks/portfolio-pm-rebalance.md), optional [`research-document-deltas.md`](../cowork/tasks/research-document-deltas.md) |
| **Review & improvement** | **`pipeline_review`** → optional GitHub Issues; Phase 9 evolution artifacts per orchestrator | [`post-mortem-research-github.md`](../cowork/tasks/post-mortem-research-github.md), [`post-mortem-portfolio-github.md`](../cowork/tasks/post-mortem-portfolio-github.md) |

**Supporting (not the core cadence)** — still valid: deep dives, backfills, dashboard UX notes, manual runs, operator scripts. They do not replace the Track A → Track B → validate loop above.

The **9-phase tables** below are a **reference map** of how segment skills fit together. **Authoritative step order and publish rules** are [`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md) + the **Cowork task** you attached + [`RUNBOOK.md`](../../RUNBOOK.md).

---

## Overview

digiquant-atlas is an AI-orchestrated daily market intelligence system. Agents load config and prior context from **Supabase**, follow **`skills/<slug>/SKILL.md`** packages, and publish structured JSON to **`daily_snapshots`** and **`documents`** (optional local scratch under `data/` is gitignored).

The system operates on a **three-tier cadence**:

| Tier | Day | Run Mode | Token Cost |
|------|-----|----------|------------|
| **Weekly Baseline** | Sunday | Full 9-phase run — all outputs from scratch | 100% |
| **Daily Delta** | Mon–Sat | Lightweight delta — only segments with material changes | ~25–30% |
| **Monthly Synthesis** | Month-end | Cross-week review + cumulative regime shifts | ~45% |

**Token savings**: ~70–75% on typical weekday runs vs a full daily baseline.

**Canonical skill paths** in the phase tables use **`skills/<slug>/SKILL.md`** only (one folder per slug under `skills/`).

---

## Three-Tier Cadence

### Sunday — Weekly Baseline

The full pipeline. Every segment is re-analyzed from scratch. The baseline becomes the week's analytical anchor. All segment payloads publish to Supabase `documents` / `daily_snapshots` per RUNBOOK.

Entry point: [`skills/weekly-baseline/SKILL.md`](../../skills/weekly-baseline/SKILL.md) → [`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md)

### Mon–Sat — Daily Delta

The delta skill ([`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md)) loads the week's baseline and any prior deltas, then runs a triage protocol:

| Priority | Segments | Threshold to Trigger Delta |
|----------|----------|---------------------------|
| **Mandatory** | `macro`, `us-equities`, `crypto` | Always — these move every day |
| **High** | `bonds`, `commodities`, `forex` | Yield/price moved >0.5% OR new CB signal |
| **Standard** | `international`, `institutional` | Major regional event OR notable flow shift |
| **Low** | `alt-data` sub-segments, all 11 sectors | Bias shifted OR tracked name moved >1.5% |

Output: JSON segment deltas for changed segments + a fully materialized digest snapshot in Supabase (`daily_snapshots` and digest `documents` row).

### Month-End — Monthly Synthesis

Entry point: [`skills/monthly-synthesis/SKILL.md`](../../skills/monthly-synthesis/SKILL.md)  
Script: [`scripts/monthly-rollup.sh`](../../scripts/monthly-rollup.sh)

Collects weekly baselines + daily deltas into month-end synthesis (published to Supabase per RUNBOOK).

---

## Pre-Flight Protocol (All Run Types)

Before any phase executes, the agent performs a structured context load:

1. **Confirm run type** (`baseline` or `delta`) and baseline date — from `skills/weekly-baseline` / `skills/daily-delta`, `python3 scripts/run_db_first.py --dry-run`, or optional `data/agent-cache/daily/{{DATE}}/_meta.json` if your environment writes it
2. **Load config** — `config/watchlist.md`, `config/preferences.md`
3. **Load prior context from Supabase** — query `daily_snapshots` and `documents` for recent dates
4. **Load yesterday's snapshot from Supabase** — establishes continuity baseline for today's changes
5. **Announce**: `"Context loaded. Starting Phase 1 of 9."`

---

## The 9-Phase Pipeline (Weekly Baseline)

### Phase 1 — Alternative Data & Positioning Signals

> **Runs FIRST** — positioning intelligence must color all downstream reads.
> Never read macro before knowing what the market is actually positioned for.

| Sub | Skill package |
|-----|----------------|
| 1A | `skills/alt-sentiment-news/SKILL.md` |
| 1B | `skills/alt-cta-positioning/SKILL.md` |
| 1C | `skills/alt-options-derivatives/SKILL.md` |
| 1D | `skills/alt-politician-signals/SKILL.md` |

Supabase: segment payloads → `documents` per RUNBOOK (stable `document_key` values).

**What each sub-agent covers:**
- **1A Sentiment & News**: AAII/CNN Fear & Greed, retail sentiment, social media signal, top news catalysts
- **1B CTA Positioning**: Systematic trend-follower positioning (via COT, CTI), futures open interest, CTA flow model estimates
- **1C Options & Derivatives**: GEX (gamma exposure), VIX structure, put/call ratios, dealer positioning, block prints
- **1D Politician Signals**: Congressional trades (STOCK Act filings), recent buys/sells by tracked officials

---

### Phase 2 — Institutional Intelligence

> Smart money reads — ETF flows, dark pool prints, and hedge fund signals.

| Sub | Skill package |
|-----|----------------|
| 2A | `skills/inst-institutional-flows/SKILL.md` |
| 2B | `skills/inst-hedge-fund-intel/SKILL.md` |

Supabase: institutional segment payloads → `documents`.

**What each sub-agent covers:**
- **2A Flows**: ETF inflows/outflows by asset class and sector, dark pool unusual activity, 13D/13G/Form 4 filings, options-implied institutional positioning
- **2B Hedge Fund Intel**: Latest signals from 16 tracked funds (CIK list in `config/hedge-funds.md`), reported via 13F, X posts, conference calls

---

### Phase 3 — Macro Regime Classification

> The analytical anchor for all downstream work.
> Every asset class analysis in Phases 4–5 must reference this regime.

Skill: `skills/macro/SKILL.md`  
**Canonical:** published macro segment in Supabase `documents` and snapshot materialization per RUNBOOK.

**4-Factor Regime Model:**

| Factor | What It Measures |
|--------|-----------------|
| **Growth** | GDP trend, PMI, labor market, earnings revisions |
| **Inflation** | CPI/PPI trajectory, commodity pressures, breakevens |
| **Policy** | Fed/ECB/BOJ stance, rate trajectory, QT pace |
| **Risk Appetite** | VIX structure, credit spreads, EM flows, safe-haven demand |

Output: a regime label (e.g., `Growth Slowing / Inflation Sticky / Policy Tightening / Risk-Off`) plus portfolio implications.

---

### Phase 4 — Asset Class Analysis

> Five dedicated asset-class agents. Each reads the Phase 3 regime output and checks for alignment.

| Sub | Skill package |
|-----|----------------|
| 4A | `skills/bonds/SKILL.md` |
| 4B | `skills/commodities/SKILL.md` |
| 4C | `skills/forex/SKILL.md` |
| 4D | `skills/crypto/SKILL.md` |
| 4E | `skills/international/SKILL.md` |

Supabase: asset-class segments → `documents`.

**Coverage:**
- **4A Bonds**: Yield curve (2s10s, 10s30s), real rates, TIPS breakevens, duration positioning, credit spreads (IG/HY), MBS
- **4B Commodities**: WTI/Brent, Nat Gas, Gold, Silver, Copper, agricultural commodities, supply/demand drivers, OPEC+ signals
- **4C Forex**: DXY, EUR/USD, USD/JPY, GBP/USD, EM FX, BOJ/ECB policy divergence, carry trade dynamics
- **4D Crypto**: BTC, ETH, BTC dominance, funding rates, exchange flows, on-chain metrics, macro correlation
- **4E International/EM**: Asia (Hang Seng, Nikkei), Europe (DAX, FTSE), EM country reads, geopolitical risk premiums

---

### Phase 5 — US Equities + 11-Sector Swarm

> Top-down market analysis first, then delegated to 11 specialized sector sub-agents.

| Sub | Skill package |
|-----|----------------|
| 5A | `skills/equity/SKILL.md` |
| 5B | `skills/sector-technology/SKILL.md` |
| 5C | `skills/sector-healthcare/SKILL.md` |
| 5D | `skills/sector-energy/SKILL.md` |
| 5E | `skills/sector-financials/SKILL.md` |
| 5F | `skills/sector-consumer-staples/SKILL.md` |
| 5G | `skills/sector-consumer-disc/SKILL.md` |
| 5H | `skills/sector-industrials/SKILL.md` |
| 5I | `skills/sector-utilities/SKILL.md` |
| 5J | `skills/sector-materials/SKILL.md` |
| 5K | `skills/sector-real-estate/SKILL.md` |
| 5L | `skills/sector-comms/SKILL.md` |
| 5M | *(orchestrator synthesis)* — sector scorecard in materialized digest / snapshot |

Supabase: US equities + 11 sector documents → `documents`.

**Phase 5A covers**: SPY/QQQ/IWM, market breadth (NYSE A/D line, new 52W highs/lows), factor performance (value, growth, momentum, quality, small cap).

**Phase 5M** produces a final sector scorecard after all 11 agents complete:
```
SECTOR SCORECARD — {{DATE}}
| Sector | ETF | Bias | Confidence | Key Driver |
```

---

### Phase 6 — Supabase Consolidation & Bias Tracker

> System-wide Supabase publish. Runs after all research is complete.

| Sub-Phase | Action |
|-----------|--------|
| 6A | Publish new bias row to Supabase `daily_snapshots` (14 columns: date, macro regime, equity/crypto/bond/commodity/forex bias, VIX, inst. flow, options sentiment, CTA direction, HF consensus, Fed odds, notes) |
| 6B | Confirm all segment documents were published to Supabase `documents` this session |

**Complete segment document manifest (25 segments):**
- Core market (7): macro, equity, crypto, bonds, commodities, forex, international
- Sectors (11): technology, healthcare, energy, financials, consumer-staples, consumer-disc, industrials, utilities, materials, real-estate, comms
- Alternative data (4): sentiment, cta-positioning, options, politician
- Institutional (2): flows, hedge-funds
- Portfolio (1): portfolio evolution and rebalance history
- Cross-asset trackers (2): bias rows in `daily_snapshots`, thesis data in `documents`

---

### Phase 7 — Master Synthesis (digest snapshot)

> Synthesis, not regurgitation. Pull the most important signals across all phases
> into a coherent, actionable brief.

**Canonical output:** digest snapshot JSON validated against `templates/digest-snapshot-schema.json`, then `scripts/materialize_snapshot.py` → Supabase `daily_snapshots` plus digest narrative in `documents` (see RUNBOOK). Markdown render is **derived** from JSON.

**Required narrative coverage** (map into snapshot JSON fields / sections the schema defines):
1. **Market Regime Snapshot** — single dominant force today
2. **Alternative Data Dashboard** — sentiment + CTA + options + politician synthesis; lead with any contrarian signal
3. **Institutional Intelligence Summary** — ETF flow direction, notable HF signal, any 13D/13G filing
4. **Macro** — full regime read (from published macro segment)
5. **Asset Classes** — bonds, commodities, forex, crypto, international
6. **US Equities** — overview + full sector scorecard (11 sectors, OW/UW/N + key driver each)
7. **Thesis Tracker** — per active thesis: ✅ Confirmed / ⚠️ Conflicted / ❌ Challenged / ⏳ No signal; flag approaching invalidation triggers
8. **Portfolio Positioning Recommendations** — explicit Trim/Add/Hold/Exit with rationale and conviction scale
9. **Actionable Summary** — top 5 items ranked by priority
10. **Risk Radar** — what could break the current bias in 24–72 hours

---

### Phase 7C — Asset Analyst Pass

> Per-asset conviction scores. Analysts are blinded to current portfolio weights.

- Reads only Phase 1–5 published segment payloads (Supabase `documents`) — no new web searches
- For each ticker in `config/portfolio.json`, produces an independent conviction score
- Also identifies 1–2 new opportunity candidates from the session's research

**Output:** publish per-ticker analyst payloads to Supabase `documents` with stable keys per RUNBOOK.

---

### Phase 7D — Portfolio Manager Review

> Clean-slate portfolio construction, then comparison vs current holdings.
> This is the most actionable output of the full pipeline.

**Phase B — Clean-Slate (blinded to weights):**
- Reads all analyst outputs from published position documents
- Applies theme caps and weight constraints from `config/preferences.md`
- Builds ideal target portfolio
- **Output:** publish `portfolio-recommended` payload to Supabase `documents`

**Phase C — Comparison (weights unlocked):**
- Loads `config/portfolio.json` with current weights
- Diffs recommended vs current; applies ≥5% threshold to filter noise
- Produces rebalance table: Hold / Add / Trim / Exit / New
- **Output:** publish `rebalance-decision` to Supabase `documents`
- Updates `config/portfolio.json` → `proposed_positions[]`
- Publishes portfolio rebalance record to Supabase `documents`

---

### Phase 8 — Web dashboard / tearsheet

```bash
python3 scripts/update_tearsheet.py   # NAV path + frontend/public/dashboard-data.json; Supabase when configured
./scripts/git-commit.sh             # commit config / static JSON as needed
```

**Behavior:** `update_tearsheet.py` uses `config/portfolio.json` and, when Supabase env is set, aligns dashboard history with `daily_snapshots` / documents. See script `--help` for optional disk scan behavior used in some operator workflows.

The Next.js frontend reads from Supabase where wired, with `frontend/public/dashboard-data.json` as static fallback — no separate backend API for the digest loop.

---

### Phase 9 — Post-Mortem & Evolution

> Self-improvement loop. Strict guardrails prevent uncontrolled pipeline drift. Matches [`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md) Phase 9 (JSON-first).

| Sub-Phase | Action | Artifact |
|-----------|--------|----------|
| 9A | Source Scorecard: rate every data source (1–5 stars), log failures, record discoveries | `evolution_sources` JSON — schema `templates/schemas/evolution-sources.schema.json` (publish per RUNBOOK; optional files from `scaffold_evolution_day.sh`) |
| 9B | Quality Post-Mortem: check yesterday's predictions (✅/❌/⏳), rate digest on 5 dimensions (1–5 scale each) | `evolution_quality_log` JSON — schema `templates/schemas/evolution-quality-log.schema.json` |
| 9C | Improvement Proposals: max 2 per session, each specifying exact target file + change + rationale | `evolution_proposals` JSON — schema `templates/schemas/evolution-proposals.schema.json` |
| 9D | Document applied proposals (approved in prior PRs) | `docs/evolution-changelog.md` |
| 9E | Evolution branch + PR | `evolve/YYYY-MM-DD` — requires user approval to merge |

**Guardrails — Phase 9 may NEVER propose changes to:**
- Published digest snapshot schema (`templates/digest-snapshot-schema.json`) / segment contracts without an approved migration
- Risk profile or position sizing in `config/investment-profile.md` §4
- These guardrails themselves

```bash
./scripts/git-commit.sh --evolution   # creates evolve/ branch + PR, does NOT auto-merge to master
```

---

## Artifact layout (canonical vs optional scratch)

**Canonical (system of record):** Supabase `documents` (per-segment JSON payloads, stable keys per RUNBOOK), `daily_snapshots` (materialized digest row for the date), and related tables (`positions`, etc., per schema).

**`data/agent-cache/`** may be **absent** on a fresh clone. Scripts populate it only when running fetch, backfill, evolution PR prep, or similar — see [`data/README.md`](../../data/README.md). **Sunday baseline vs Mon–Sat delta:** same Supabase contract; delta runs additionally emit delta-oriented documents per `skills/daily-delta/SKILL.md`.

---

## Research Continuity Architecture

Supabase is the system's long-term intelligence layer. Research continuity across sessions is achieved by querying prior rows at session start rather than reading flat files.

**Supabase tables used for continuity:**

| Table | Content |
|-------|---------|
| `daily_snapshots` | Per-date bias rows (14 columns: macro regime, equity/crypto/bond/commodity/forex bias, VIX, inst. flow, options sentiment, CTA direction, HF consensus, Fed odds, notes) |
| `documents` | Per-segment research documents keyed by `(date, file_path)` — covers all 25 segments: macro, equity, crypto, bonds, commodities, forex, international, 11 sectors, 4 alt-data sub-segments, 2 institutional, portfolio, thesis data |

**Research continuity protocol:**
- Query Supabase at session start — retrieve last 3 entries per relevant segment for trend identification
- Publish new documents at session end via `publish_document.py` or `materialize_snapshot.py`
- Append-only semantics preserved in Supabase via unique `(date, file_path)` keys on `documents`
- Creates compounding intelligence — each session builds on all prior research in every domain

---

## Data Flow

```
config/watchlist.md ─────────────────────────────────────────┐
config/preferences.md ──────────────────────────────────────┐│
config/hedge-funds.md ─────────────────────┐                ││
                                           │                ││
Supabase daily_snapshots/documents ───┐    │(all skills read)│
(prior context queried at session start)│   │                 │
                                      ▼    ▼                 ▼
         Phase 1 ─► segment JSON ──► Phase 2 ─► Phase 3 ─► Phase 4 ─► Phase 5
                                                    │
                                 (macro regime anchors all phases below)
                                                    │
                                           Phase 6: Supabase PUBLISH
                                         (all segment documents published)
                                                    │
                                           Phase 7: materialized digest
                                         (daily_snapshots + digest document)
                                                    │
                                     Phase 7C/7D: portfolio analysis
                                    (published position + PM payloads)
                                                    │
                                     Phase 8: dashboard-data.json
                                     (update_tearsheet.py → frontend)
                                                    │
                                     Phase 9: evolution JSON (+ optional PR)
                                     (data/agent-cache/evolution/{{DATE}}/)
```

**Dependency rule**: Each phase reads all prior phases' published outputs before executing. This sequential dependency is intentional — sector analysts must know the macro regime before making allocation calls.

---

## Signal Priority Hierarchy

When signals conflict across phases, apply in order:

1. **Fundamental regime change** — macro regime shifts override all other signals
2. **Institutional flows** — large capital movements are directionally predictive short-term
3. **Alternative data / sentiment** — useful for timing and contrarian reads
4. **Technical levels** — useful for medium-term target setting

---

## Web dashboard (frontend)

```
Supabase (documents, daily_snapshots, price_history, …)
     │
     ▼  @supabase/supabase-js in Next.js (App Router)
  frontend/app/ …                    Library, portfolio, architecture pages, …
     │
     ├─ scripts/update_tearsheet.py → frontend/public/dashboard-data.json (static JSON used when present)
     └─ CI: .github/workflows/deploy.yml → static export → GitHub Pages (when configured)
```

**Primary path:** the app reads **live data from Supabase** (`NEXT_PUBLIC_SUPABASE_*`). **`dashboard-data.json`** is an optional static fallback — see [`RUNBOOK.md`](../../RUNBOOK.md).

---

## Repository structure

```
digiquant-atlas/
  AGENTS.md, CLAUDE.md, RUNBOOK.md, CLAUDE_PROJECT_INSTRUCTIONS.md
  config/                    Watchlist, portfolio, preferences, macro_series.yaml, …
  skills/<slug>/SKILL.md     Orchestrator, daily-delta, weekly-baseline, sectors, …
  templates/schemas/         JSON Schema for published artifacts
  scripts/                   Bash + Python — run_db_first.py, materialize_snapshot.py,
                             publish_document.py, preload-history.py, smoke-test.sh, …
  agents/                    Named role files (*.agent.md)
  frontend/                  Next.js (App Router) + TypeScript
  supabase/                  SQL migrations, config.toml
  tests/                     pytest
  cowork/                    Cowork tasks and project prompts
  docs/agentic/              ARCHITECTURE.md (this file), WORKFLOWS, PLATFORMS, …
  data/                      Not in git — local scratch + price CSV cache (see .gitignore)
```

Skills are packaged as **`skills/<slug>/SKILL.md`**; use [`SKILLS-CATALOG.md`](SKILLS-CATALOG.md) for the full list.

---

*Platform setup: [`PLATFORMS.md`](PLATFORMS.md).*
