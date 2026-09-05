# digiquant-research — System Architecture

> **Last updated**: 2026-06-20  
> **Pipeline version**: v4 — daily dashboard graph (research A0–A4 → portfolio H1–H9) with edit-mode continuity  
> **Canonical spec:** [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../../../../../../../docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md) §13–§14

---

## Where to read what

| Need | Doc |
|------|-----|
| **Cowork schedules (how the repo is run day-to-day)** | [`cowork/tasks/README.md`](../cowork/tasks/README.md), [`cowork/PROJECT.md`](../cowork/PROJECT.md) |
| Operator commands and validation | [`RUNBOOK.md`](../../RUNBOOK.md) |
| Daily cadence + refresh_scope | [`WORKFLOWS.md`](WORKFLOWS.md) |
| Skill index (filesystem source of truth) | [`SKILLS-CATALOG.md`](SKILLS-CATALOG.md) |
| IDE / Copilot / Cursor setup | [`PLATFORMS.md`](PLATFORMS.md) |
| portfolio H1–H9 topology | [`portfolio/docs/ARCHITECTURE.md`](../../../portfolio/docs/ARCHITECTURE.md) |
| Dated health / score snapshot | [`../SYSTEM-SCORECARD.md`](../SYSTEM-SCORECARD.md) |

---

## Operational scope (Cowork-first)

**In scope for ongoing operation**

| Track | What | Task entry points |
|-------|------|-------------------|
| **Research (Track A)** | Daily research with edit-mode — publish **`digest`** and segment research to Supabase | [`recurring-scheduled-run.md`](../cowork/tasks/recurring-scheduled-run.md), `python -m digiquant.portfolio.chain --cadence daily` |
| **Portfolio (Track B)** | Thesis-first portfolio H1–H9 → `commit_run` | Same chain entry point (unified daily graph) |
| **Review & improvement** | `preflight_reflect` on due `decision_log` rows + matured typed forecast outcomes (`forecast_outcomes`, WP5.2); daily beliefs short fold | `--refresh-scope beliefs` (full rewrite) |

**Superseded cadence (historical only):** separate weekly baseline / weekday delta / month-end
synthesis workflows — replaced by one daily graph + `resolve_edit_mode` per artifact ([#930](https://github.com/digithings-ai/digithings/issues/930)).

The **9-phase tables** below are a **reference map** of segment skills. **Authoritative runtime
order** is the LangGraph pipeline: A0 preflight → A1 triage → A2 segments → A3 consolidate →
A4 digest → portfolio H1–H9.

---

## Overview

digiquant-research is an AI-orchestrated daily market intelligence system. Agents load config and
prior context from **Supabase**, follow **`skills/<slug>/SKILL.md`** packages (or `*-edit.md`
when `resolve_edit_mode` returns `edit`), and publish structured JSON to **`daily_snapshots`**
and **`documents`**.

### Daily cadence (current)

| Control | Behavior |
|---------|----------|
| **Cron** | digithings-cron house clocks → `pipeline-digiquant.yml` — `17 9/10/11/12 * * *` UTC daily |
| **Default** | `refresh_scope=none` — continuity via `skip`/`edit`/`full` per artifact |
| **Full refresh** | Manual `workflow_dispatch` / `--refresh-scope all` (no Sunday force) |
| **CLI** | `python -m digiquant.portfolio.chain --cadence daily [--refresh-scope …]` |
| **Cost** | `OLYMPUS_MODEL_TIER` (`cheap` \| `balanced` \| `quality`) — not graph forks |

Quiet-day savings: triage `skip` (0 LLM) + `edit` (`DocumentPatch`) — not a separate delta graph.

---

## research → portfolio handoff

research terminates at `phase7_synthesis` (`DigestPayload`). portfolio reads only `DigestPayload`
from research runtime ([ADR-0015](../../../../../../docs/adr/0015-research-vs-portfolio.md)).

Retrieval tools (portfolio grounding): `query_research`, `query_data`, `query_portfolio` with
phase-scoped blinding (spec §6.1).

---

## Three-Tier Cadence (historical — superseded 2026-06-20)

> **Superseded.** The three-tier baseline/delta/monthly model is replaced by one daily graph
> and per-artifact edit mode. The section below is retained for operator context on legacy
> Cowork task names and token-savings rationale.

### Sunday — Weekly Baseline (historical entry point)

Entry point was: `python -m digiquant.portfolio.chain --run-type baseline`  
**Current:** `--cadence daily` by default; `--refresh-scope all` only via manual dispatch/CLI.

### Mon–Sat — Daily Delta (historical)

Entry point was: `python -m digiquant.portfolio.chain --run-type delta`  
**Current:** `--cadence daily` with triage + `resolve_edit_mode` per segment.

### Month-End — Monthly Synthesis (removed)

**Not in v1.** Month-over-month views are UI aggregation over stored daily artifacts.
Do not schedule `monthly` runs or `phase_monthly` on the daily chain.

---

## Pre-Flight Protocol (All Run Types)

Before any phase executes, the agent performs a structured context load:

1. **Confirm cadence** — `python -m digiquant.portfolio.chain --cadence daily` (optional `--refresh-scope all` for operator full refresh)
2. **Load config** — `config/watchlist.md`, `config/preferences.md`
3. **Load prior context from Supabase** — query `daily_snapshots` and `documents` for recent dates
4. **Load yesterday's snapshot from Supabase** — establishes continuity baseline for today's changes
5. **Inject market context (#694)** — preflight queries `price_technicals`
   (core + sector ETFs, latest row each) and `macro_series_observations`
   (latest + previous value per configured series) into
   `DataLayerSnapshot.market_context`, which `_shared_context` serializes into
   every phase call. Agents get real quantitative values deterministically —
   the Supabase data tools remain available for follow-up queries but are no
   longer the only path to price/macro data (they were never invoked under
   `tool_choice="auto"`). Fail-soft: a data-layer error logs a warning and
   phases run without injected values.
6. **Pin research state (#2863 / WP12.3)** — when a `ResearchStateStore` is
   wired, preflight selects one exact `ResearchStatePin` (optional explicit
   `requested_research_state_version_id`, else cutoff-bound `select_state_as_of`
   + `pin_state_for_run`) onto `ResearchState.research_state_pin`. Resume
   reuses the run/attempt pin; typed `state_unavailable` keeps compatibility
   documents shadow-only. Never re-select / `load_latest` after the pin.
6b. **Ticker evidence bundles (#2844 / WP11.1–WP11.5)** — typed H5
   `TickerEvidenceBundle` + append-only H6 `MissingFactRequest` /
   `EvidenceBundleAmendment` contracts (`research_retrieval` models +
   in-memory `EvidenceBundleStore` with `dump_snapshot`/`from_snapshot` for
   checkpoint reload; private migrations `090`/`091`; SQL IO adapter later).
   One immutable base per run/ticker; amendments must link one base and one
   request. WP11.2 builds the H5 base before the provider call; WP11.3–11.4
   wire deterministic H6 selection + bounded missing-fact supplements; WP11.5
   (`simulated_pipeline` + `TestDurableH5H6LineageRoundTrip`) proves bases and
   amendments survive store serialize/reload across the H5→H6 boundary.
   Optional `PortfolioGraphDeps.evidence_bundle_store`; default graph leaves it
   unwired; `OLYMPUS_EVIDENCE_BUNDLE_WRITER=off` gates append when injected.

7. **Announce**: `"Context loaded. Starting Phase 1 of 9."`

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

**Delta circuit-breaker (#928):** both 2A/2B run live web search + an LLM. Pre-flight
probes `documents` (`query_institutional_absence_streak`) for consecutive recent runs that
published **no** `inst-*` document and records the count on
`DataLayerSnapshot.institutional_absence_streak` (`institutional_data_available` is the
boolean flag). On a **delta** run, once that streak reaches
`phase2_institutional.ABSENCE_BREAKER_THRESHOLD` (3), Phase 2 skips the paid `inst-*`
LLM/search nodes and writes a deterministic empty-`body` stub (zero search spend)
carrying a `circuit_breaker` marker; publish suppresses the empty stub and diagnostics records
the skip + reason under `breakdown.phase2_outputs.circuit_breaker_skips`. **Baseline always
runs Phase 2 fully** — a baseline re-probes the layer rather than inheriting a stale absence.

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

Output: a markdown research memo (`body`) plus optional 4-factor chips
(`growth` / `inflation` / `policy` / `risk_appetite`) and a short `regime_label`
for the pipeline strip.

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

Supabase: US equities + 11 sector **memos** → `documents`. There is no
deterministic `sector-scorecard` step; digest and PM read the sector memos
directly.

**Phase 5A covers**: SPY/QQQ/IWM, market breadth (NYSE A/D line, new 52W highs/lows), factor performance (value, growth, momentum, quality, small cap).

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

### Phase 7 — Master Synthesis (stitched markdown briefing)

> Research-only synthesis. Subsection agents write topical markdown; a stitcher
> assembles one long analyst-entry briefing. **No portfolio positioning** — that is portfolio's
> domain (phases 7C–7E). See [ADR-0015](../../../../../../docs/adr/0015-research-vs-portfolio.md).

**Canonical output:** one `digest` / `digest-delta` document whose `body` is the stitched
markdown. Thin envelope: `date`, `regime_label`, `sources`, `segment_freshness`.
Inside the LangGraph pipeline the terminal `phases/publish_phase.py` writes the digest into
Supabase `daily_snapshots` and `documents`. Markdown render prefers `body`; historical
JSON slots fall back to `compose_legacy_digest_body` (no Overall bias / fake metrics).

**Subsection roster** (capped to current digest topics — not a second per-sector fan-out):
`macro`, `alt-data`, `institutional`, `asset-classes`, `us-equities`. Each subsection
reads only its upstream memos plus the last **two full** digest briefing bodies
(not the #1559 300-char slim).

**Required narrative coverage** (topical `##` headings in the stitched `body`):
1. **Market regime** — single dominant force today; cross-asset research themes (not positioning)
2. **Alt-data** — sentiment + CTA + options + politician synthesis
3. **Institutional** — ETF flow direction, notable HF signal
4. **Asset classes** — bonds, commodities, forex, crypto, international
5. **US equities** — overview plus the 11 sector memos (operators pick leadership from those memos; no rolled-up scorecard)
6. **Watchlist / risk radar** — evidence-based items to monitor; no trade verbs

H1/H2 consume `digest_briefing_for_portfolio` (`date` / `body` / `regime_label` only).

**Context budget ([#1559](https://github.com/digithings-ai/digithings/issues/1559)).** Subsection agents slim their upstream memo bodies under `_DIGEST_SEGMENT_INPUTS_BUDGET_CHARS`. The stitcher sees subsections + two full prior briefing bodies (capped at `_DIGEST_PRIOR_BODY_MAX`, not 300 chars). `latest_segments` is filtered to the digest keys (`digest`, `digest-delta`).

**Failure visibility.** When master-digest synthesis fails and carries the prior forward, the carried payload is stamped with `carried_from` (ISO source date) + a human `continuity` note (JSONB, no migration), and `diagnostics.summarize_run` escalates the run to **degraded** with the failure leading `error_summary` and a first-class `breakdown["master_digest_failed"]` key — so a stale carry is never reported as `ok`.

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

> Self-improvement loop. Strict guardrails prevent uncontrolled pipeline drift. Phase 9 evolution artifacts (JSON-first).

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

**`data/agent-cache/`** may be **absent** on a fresh clone. Scripts populate it only when running fetch, backfill, evolution PR prep, or similar — see [`data/README.md`](../../data/README.md). **Sunday baseline vs Mon–Sat delta:** same Supabase contract; delta runs additionally emit delta-oriented documents.

---

## Snapshot read path (frontend-consumable)

**Goal:** the research frontend (Next.js dashboard at `frontend/dashboard/`) and any other consumer can fetch a daily run's full state with one query and zero pipeline-runtime imports. Issue [#302](https://github.com/digithings-ai/digithings/issues/302).

### Source of truth

After every baseline / delta run, the LangGraph pipeline writes one row to **`daily_snapshots`** via `digiquant.research.supabase_io.publish_daily_snapshot` (PR #441). That row is the canonical artifact — there is **no** separate static JSON published anywhere else. Columns we care about:

| Column | Type | Notes |
|---|---|---|
| `date` | `date` | Trading date (run_date) |
| `run_type` | `text` | `'baseline'` (Sunday) or `'delta'` (Mon–Sat) |
| `baseline_date` | `date` | Most recent baseline this delta builds on; `NULL` for baseline runs |
| `snapshot` | `jsonb` | Full Phase 7 digest payload — matches `templates/digest-snapshot-schema.json` |
| `digest_markdown` | `text` | Optional rendered Markdown view |
| `created_at` / `updated_at` | `timestamptz` | Supabase row timestamps |

### Access (anon, RLS-gated)

Migration **011** (`011_unpartition_snapshots_documents.sql`) installs the policy:

```sql
ALTER TABLE daily_snapshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "anon_read" ON daily_snapshots FOR SELECT TO anon USING (true);
```

So the frontend uses the Supabase **anon** key — no service-role key client-side, no separate publish step. The same policy is in place on `documents`. The Next.js dashboard already consumes Supabase this way; the envelope schema below is the typed contract on top of those rows.

### Envelope schema

The wire-level contract is **[`digiquant.research.SnapshotEnvelope`](../../../../digiquant/src/digiquant/research/snapshot.py)** — a Pydantic v2 model wrapping the Phase 7 digest with run-level metadata. The exported JSON Schema lives at [`digiquant/docs/schemas/research_snapshot.v1.json`](../../../../digiquant/docs/schemas/research_snapshot.v1.json) and is regenerated by `scripts/export_research_snapshot_schema.py`.

```text
SnapshotEnvelope
├─ schema_version: int = 1     # bump on breaking changes
├─ run_date: date              # daily_snapshots.date
├─ run_type: "baseline"|"delta"
├─ baseline_date: date | None  # daily_snapshots.baseline_date
├─ published_at: datetime      # updated_at, falling back to created_at
└─ digest: DigestPayload       # daily_snapshots.snapshot (jsonb)
```

The envelope is `extra="forbid"` end-to-end, so a frontend validator catches drift loudly. `SnapshotEnvelope.from_supabase_row(row)` accepts the natural row dict and assembles the envelope.

### Why this design (Option A) and not a static JSON publish step (Option B)

- The `daily_snapshots` row is **already** the canonical artifact — duplicating it to a static file (committed branch / object-store URL) creates two sources of truth and a cache-invalidation problem.
- RLS gating with the anon key gives the same "no auth dance" UX as a public file URL, but with row-level security primitives if we later want to gate by tenant or date.
- No new infra (no S3 bucket, no GitHub Pages publish step, no CDN cache to invalidate) and no changes to the LangGraph runtime.

### DigestPayload duality (don't import the app from the lib)

`digiquant.research` depends on `digiquant` and `digigraph`. To keep the import direction correct (apps → libs, never libs → apps), `digiquant.research.snapshot.DigestPayload` is a **mirror** of `digiquant.research.phases.phase7_synthesis.DigestSnapshot`. A parity test (`tests/dq/research/test_snapshot.py::TestParityWithPipelineDigest`) imports both classes when the pipeline package is available and asserts field-name equality; drift fails loud.

### Schema versioning policy

Bump `digiquant.research.snapshot.SCHEMA_VERSION` and ship a sibling `research_snapshot.v{N}.json` whenever fields are added/removed/renamed or semantics change. Frontend consumers branch on `envelope.schema_version`. The previous version's schema file stays committed for grace-period rollouts.

### Personalization (read-time, additive)

The pipeline writes one canonical `daily_snapshots` row per day — *not* a per-user view. Per-user filtering and ranking happens at read time via [`digiquant.research.personalize_snapshot`](../../../../digiquant/src/digiquant/research/personalization.py). Issue [#312](https://github.com/digithings-ai/digithings/issues/312).

```
SnapshotEnvelope ──┐
                   ├──> personalize_snapshot ──> PersonalizedSnapshot { envelope, excluded_count, rank_changes }
InvestmentProfile ─┤
AssetPreferences ──┘
```

Behavior:
- **Anonymous** (both args `None`): pass-through — same envelope instance, no diagnostics.
- **`AssetPreferences.excluded_tickers`**: drops items in `actionable_summary`, `risk_radar`, `material_findings` whose label/rationale/trigger/summary mention an excluded ticker (word-boundary uppercase regex; coarse but documented — "USA"/"UK" can collide).
- **`AssetPreferences.custom_universe`**: stable-partitions `actionable_summary` so items mentioning a custom-universe ticker move to the front; positional moves are reported in `rank_changes`.
- **`InvestmentProfile.risk_tolerance`**: `conservative` drops `actionable_summary` items with `priority < 3`; `moderate` / `aggressive` keep all.
- **`InvestmentProfile.esg_preference == "strict"`**: drops items whose label/rationale/trigger/summary contain any `excluded_sectors` substring (lower-cased contains-match). `tilt` / `none` are pass-through here — `tilt` drives weighting downstream in portfolio/execution, not visibility in research.

`schema_version` does **not** bump — personalization is additive and consumed via the sibling `PersonalizedSnapshot` dataclass, keeping the wire envelope contract immutable. Performance budget: < 100 ms per snapshot (issue req); CI assertion at 200 ms for runner variance.

---

## Run Checkpoint / Resume (#665)

A failed or interrupted run (e.g. provider outage, credit exhaustion) can **resume from the last completed node** instead of re-running the whole pipeline. When `DIGI_CHECKPOINTER=postgres` + `DIGI_CHECKPOINTER_POSTGRES_URI` are set, the chain compiles research and portfolio with a LangGraph **PostgresSaver** and runs them under **distinct per-graph threads** — `{run_id}::research` and `{run_id}::portfolio` (never one shared thread; their state schemas differ). Each node (per-segment, per-(axis,ticker) analyst, per-(round,ticker) debater) is a checkpoint boundary, so resume re-runs only incomplete nodes. Publish is **not** checkpointed (cheap + idempotent upserts).

- **Automatic within a run:** the workflow's 3× outer retry reuses the same `GITHUB_RUN_ID`, so attempt 2 finds attempt 1's checkpoint and continues from the failure point.
- **Cross-dispatch:** re-dispatch with `--resume-run-id <prior GITHUB_RUN_ID>` (a `resume_run_id` workflow input) to continue a previously-dead run.
- Resume control flow: if a graph's thread already has a checkpoint, invoke with `None` (continue); otherwise invoke with the upstream state. Degrades to no-checkpointing (plain run) when the env/secret/package is absent.

## Research Continuity Architecture

Supabase is the system's long-term intelligence layer. Research continuity across sessions is achieved by querying prior rows at session start rather than reading flat files.

**Supabase tables used for continuity:**

| Table | Content |
|-------|---------|
| `daily_snapshots` | Per-date bias rows (14 columns: macro regime, equity/crypto/bond/commodity/forex bias, VIX, inst. flow, options sentiment, CTA direction, HF consensus, Fed odds, notes) |
| `documents` | Per-segment research documents keyed by `(workspace_id, date, document_key)` — covers all 25 segments plus inspectable pipeline leaves: `inputs` (preflight), `bias-row` (Phase 6), `attention-plan` (shadow planner), digest |

**Research continuity protocol:**
- Query Supabase at session start — retrieve last 3 entries per relevant segment for trend identification (handled by `phases/preflight.py` → `load_prior_context`)
- Publish new documents at session end via the terminal `phases/publish_phase.py` (replaces legacy `publish_document.py` / `materialize_snapshot.py` scripts when running inside the LangGraph pipeline). Fail-soft extras: `inputs` and `bias-row` via `dashboard.research.inspectable_io` (no LLM).
- Append-only semantics preserved in Supabase via unique `(date, document_key)` keys on `documents`
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
         Phase 1 ─► markdown memo ──► Phase 2 ─► Phase 3 ─► Phase 4 ─► Phase 5
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

### Tool-based grounding (#566)

`preflight.py` still runs a **freshness probe** (latest dates + counts in `state.data_layer`) for triage, but phases no longer rely on pre-loaded values. Instead each research phase runs a **tool loop** so the model fetches real data on demand:

```
preflight (freshness probe; no pre-loaded values)
  ↓ phase node: inputs_builder → scope/segment context
  ├─ web-grounding pre-pass (live_search phases): responses.create(tools=[web_search])
  │    → cited summary injected into phase_inputs as `web_grounding`
  └─ run_research_agent → chat_completion_with_tools(tools=[data tools])
       ├─ get_price_technicals / get_macro_series → real Supabase values
       ├─ web_grounding block (news/sentiment/flows + citations) already in inputs
       └─ model emits final JSON → validate against output_model (retry on invalid)
  ↓ existing publish path (documents + daily_snapshot) — unchanged
```

- **Two data tools, one query layer** (`dashboard/research/data/queries.py`): exposed both in-process (`data/tools.py` → `DATA_TOOLS` + dispatcher, consumed by `build_grounding` in `phases/_node_factory.py`) and over MCP (`digiquant_get_price_technicals` / `digiquant_get_macro_series` in `mcp_server.py`).
- **Per-phase flags** on `SegmentNodeSpec`: `use_data_tools` (macro, asset-classes, equity, sectors) and `live_search` (macro, all alt-/inst-, international). Equity/sector nodes are bespoke and call `build_grounding` directly.
- **Web grounding** (`data/web_grounding.py` → `digigraph.llm_client.openrouter_web_search`):
  a read-only **pre-pass** on a **web-search-capable** model from
  `get_grounding_model()` (Perplexity / `:online` — provider built-in search).
  Domain preferences from `config/search_domains.yaml` are folded into the
  natural-language query (native search has no Exa allowlist tool params).
  The digillm Exa `openrouter:web_search` server tool remains a **toolkit**
  fallback for non-native models and is **not** used by dashboard (#2567).
  Any search error degrades to ungrounded research (no crash).
- **Env gate**: `ATLAS_DATA_TOOLS` (default on; set `0`/`false` to disable all tool grounding). If Supabase is unavailable, `build_grounding` degrades to tool-less rather than crashing the phase.

Function-tools and `response_format=json_schema` are mutually exclusive in one OpenAI-API call, so the structured-output contract is preserved by prompt + Pydantic validate-retry rather than by `response_format` on the tool path.

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
digiquant-research/
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

---

## LLM Routing — digiquant capability tiers

*Current since Jun 2026 (#859, #980, #998); house path via LiteLLM since #3413/#3414: digiquant phase LLM calls are **caller → digillm → LiteLLM**. Capability pools in [`config/digiquant_models.yaml`](../../../../../../config/digiquant_models.yaml) are digiquant **model categories** (`cheap` default / `balanced` / `quality` via `OLYMPUS_MODEL_TIER`) — not an OpenRouter preference. Unprefixed pool/pin slugs are LiteLLM `model_name` keys (upstream swap is a `litellm.yaml` edit). This superseded the 2026-04 three-tier free-provider model (Groq / Ollama / Gemini — [DESIGN-DECISIONS.md ADR-016](../DESIGN-DECISIONS.md#adr-016-three-tier-llm-provider-routing), retained as history). Operator knobs and cost levers: [RUNBOOK.md "OpenRouter model tiers"](../RUNBOOK.md#openrouter-model-tiers-configdashboard_modelsyaml) (section title is historical; knobs still apply when LiteLLM's upstream is OpenRouter). Historical per-phase budgets: [`docs/research/token-budget.md`](../../../../../../docs/research/token-budget.md).*

The default `cheap` tier is **open-weight models only** — frontier models (`openai/*`, `anthropic/*`, GPT-5.x, Claude Opus/Sonnet, o-series) are rejected at runtime (`digigraph.model_config.is_flagship_openrouter_model`), a guard added after a bare-Auto-Router delta run landed on GPT-5.5 and cost $11.95.

### Capability pools (default `cheap` tier)

Each phase slug maps to a **capability** (`phase_capabilities` / `phase_capability_prefixes` in `digiquant_models.yaml`); the model is a **stable-hash pick over that capability's pool** (deterministic per slug — no per-run randomness).

| Capability | Pool (cheap tier) | Example phases |
|------------|-------------------|----------------|
| **extraction** | `deepseek/deepseek-v4-flash`, `meta-llama/llama-4-maverick` | `alt-*`, `inst-*`, 7C per-ticker analysts |
| **research** | `deepseek/deepseek-v4-flash`, `meta-llama/llama-4-maverick` | `macro`, `bonds`, `sector-*`, 7D debate, `phase9-evolution` |
| **reasoning** | `deepseek/deepseek-v4-flash` | `master-digest` (Phase 7), `pm-rebalance`, `monthly-digest` |
| **web search** (grounding pre-pass only) | `perplexity/sonar`, `deepseek-v4-flash:online`, `llama-4-maverick:online` | live-search grounding; never phase/tool calls |

Pools rebalanced in #2368 (2026-08-14, grok-4.6 added 2026-08-15; see #1622 for the prior 2026 open-weight refresh) to prefer the latest generation slug per vendor where cost allows — `deepseek-v4-flash` on cheap; `grok-4.3` (untouched by #2368; `grok-4.6` is the current xAI flagship but reserved for quality), `gpt-5.6-luna`, `gemini-3.7-flash`, and `deepseek-v4-pro` on balanced; `grok-4.6`/`gpt-5.6-sol`/`claude-sonnet-5`/`deepseek-v4-pro` on quality. `deepseek-chat` is retired from every dashboard pool — within dashboard every reference now resolves to `deepseek-v4-flash` (other digithings products pin it independently and are out of scope here). `deepseek-r1` was removed from every phase pool — its chain-of-thought output is not reliably strict JSON (the 2026-07-18 digest `JSONDecodeError`) — and `llama-4-maverick` from the reasoning pools (empty completions under strict `json_schema`, #1006). `z-ai/glm-5` was evaluated and rejected: its endpoint-gate record over four runs was pass/fail/pass/fail (empty bodies under strict `json_schema` even with a retry — the same #1006 class). Every pooled slug is **endpoint-verified** (function tools + strict `json_schema` + context floor) by `scripts/validate_digiquant_pools.py`, which CI runs on any PR touching the routing configs (`validate-digiquant-pools.yml`).

> **Synthesis context (#1559, #1622).** `master-digest` is pinned via `phase_models` to `deepseek/deepseek-v4-flash` (1M-token context), which removes the 64k context ceiling that broke synthesis daily 2026-07-08 → 07-17 (the 2025-era pool models' structured-output endpoints cap at 64,000 tokens against ~70–91k digest inputs). The #1559 input budget (`_slim_segment_body`, ≤64k target) is retained as a **cost bound** — prompt tokens are billed even when they fit. (Diagnostics note: the run-level `model` column in `atlas_run_diagnostics` is the first *served* model of the whole run, not the digest model — a failed digest call records no usage, so its model never appears there.)

### Observed token volume

From `atlas_run_diagnostics` (runs since 2026-06-15): **delta ≈ 1.3M total tokens/run** (~73 LLM calls, ≈ $0.43) and **baseline ≈ 340k** (~33 calls, ≈ $0.13). The old "~113k tokens/run" figure was the 2026-04 free-tier estimate and predates the portfolio fan-outs and web-grounding pre-passes.

### How routing works

Every phase node passes a `phase_slug` (e.g. `alt-sentiment-news`, `master-digest`, `portfolio/deliberation-NVDA`) to `run_research_agent`. The model resolves in this priority order (`digigraph/src/digigraph/model_config.py`):

```
1. Explicit model= kwarg  (test overrides, never set in production)
2. config/model_modes.yaml phase_models  →  explicit per-phase pin (escape hatch;
   frontier models are rejected on cheap/balanced tiers)
3. config/digiquant_models.yaml  →  capability(phase_slug) × OLYMPUS_MODEL_TIER pool,
   stable-hash pick
4. get_model_for_mode()  →  legacy DIGI_LLM_MODE defaults; in an OpenRouter deploy a
   non-OpenRouter fallback is redirected to the active tier's reasoning pool
```

`config/digiquant_models.yaml` owns routing; `config/model_modes.yaml` `phase_models` is empty except for deliberate pins. The live pins (#1006, #1559, #1622):

```yaml
phase_models:
  # H6 deliberation emits strict JSON; llama-4-maverick returned empty completions under
  # STRICT json_schema, so the per-ticker slugs are pinned to the json/tool-reliable model.
  portfolio/deliberation-: deepseek/deepseek-v4-flash   # trailing '-' = prefix match
  # Pinned (not pool-hashed) so digest routing stays deterministic; v4-flash's 1M context
  # removes the #1559 64k synthesis ceiling (#1622).
  master-digest: deepseek/deepseek-v4-flash
```

House traffic is caller → digillm → LiteLLM. Unprefixed OpenRouter slugs (`deepseek/…`, `anthropic/…`) are `config/litellm.yaml` `model_name` keys. Leftover `openrouter/` / `gemini/` / `xai/` prefixes are vendor-client diagnostics when no LiteLLM proxy is configured (`digillm/src/digillm/client.py`).

### Fan-out cap (`ATLAS_MAX_ANALYSTS`)

Phase 7C spawns one LLM node per ticker in the watchlist (up to 98). The `ATLAS_MAX_ANALYSTS` env var caps the fan-out:

| Value | Behaviour |
|-------|-----------|
| `0` (default) | No cap — full watchlist |
| `30` (CI default) | Capped at 30 tickers; logged at INFO level |

On the live thesis-first path the cap is applied once, in H4 (`roster_cap.capped_tickers`),
and since #1767 it is actually enforced — the prior book is the only sanctioned overshoot
and thesis vehicles are prioritised within it. See
`portfolio/docs/ARCHITECTURE.md` § "Roster cap enforcement (#1767)".

This bounds the per-run OpenRouter call volume (and spend) during scheduled CI runs. Production / local runs can set `ATLAS_MAX_ANALYSTS=0` to use the full watchlist.

**Watchlist resolution (#694):** when the CLI is invoked without `--watchlist`
(every scheduled workflow), `resolve_cli_inputs` falls back to
`config/watchlist.md` — both the research graph and the portfolio 7C/7CD fan-out are
compiled from `ResearchInput.watchlist`, and an empty tuple silently skipped every
analyst/debate node. An explicit `--watchlist` still overrides the file, and an
empty file still disables the fan-out. Cost note: with the fallback active, a
delta run adds `min(len(watchlist), ATLAS_MAX_ANALYSTS) × 4` analyst calls plus
the debate/risk rounds — tune `ATLAS_MAX_ANALYSTS` in the workflow envs to
bound spend.

### Fallback behaviour

If a provider-prefixed model's key is not configured (e.g. `OPENROUTER_API_KEY` unset), `resolve_request_model` logs a warning and falls back to the Ollama mode model for that call — the pipeline completes with degraded quality but never hard-fails on a missing key. Empty completions self-heal with a retry (re-asking the same model; `OPENROUTER_FALLBACK_MODELS` covers provider errors on the primary request, not empty `200` bodies); see [RUNBOOK.md "OpenRouter empty completions"](../RUNBOOK.md#openrouter-empty-completions-degraded-book-empty-completion-from--in-logs) for the operator checklist.

### Overriding models (user configuration)

Pin a phase via the `phase_models` block in `config/model_modes.yaml` (exact slug, or trailing-`-` prefix match). Pins are subject to tier policy — frontier models are rejected on `cheap`/`balanced` and fall back to `digiquant_models.yaml`:

```yaml
phase_models:
  master-digest: "deepseek/deepseek-v4-flash"   # pin synthesis to one pool model
  "sector-":     "openrouter/mistralai/mistral-large"  # prefix match: sector-tech, sector-energy, …
```

Tier-wide changes belong in `config/digiquant_models.yaml` (capability pools per tier). To add a new provider, call `digillm.register_provider(prefix, base_url, api_key_env)` or extend `_EXTERNAL_PROVIDERS` in `digillm/src/digillm/client.py`; retry, caching, and fallback logic applies automatically.

### Required secrets / env vars

| Variable | Purpose | Where set |
|----------|---------|-----------|
| `OPENROUTER_API_KEY` | All phase LLM calls + web grounding | GitHub secret + local `.env` |
| `OLYMPUS_MODEL_TIER` | Tier select (`cheap` default / `balanced` / `quality`) | Optional; workflow env or shell |
| `ATLAS_MAX_ANALYSTS` | H4/H5/H6 roster fan-out cap (#1767) | CI workflow env: `"30"` |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | Publishing + diagnostics | GitHub secret + local `.env` |

`OPENROUTER_ALLOWED_MODELS` and `OPENROUTER_COST_QUALITY_TRADEOFF` are **not** set by hand — `apply_digiquant_openrouter_env()` derives them from the active tier at chain startup. Run `python3 scripts/validate-provider-keys.py` after adding keys to `.env` to smoke-test the configured providers.

---

## digigraph Sub-graph Orchestration (issue #176, ADR-0009)

The 9-phase pipeline described above is now orchestrated by a digigraph
sub-graph in `digiquant/src/digiquant/research/`. Skill files in
`skills/<slug>/SKILL.md` remain the authoritative "what to research"
instructions — they are injected into a generic research agent at runtime
rather than ported as prompt code.

Entry point: `digiquant.research.graph.build_research_graph` plus `ResearchInput`.
digiclaw (issue #219) invokes this on a cron schedule.

**What changed operationally:**

- Publishing runs from inside the sub-graph (`supabase_io.py`) rather than
  from `scripts/publish_document.py`. Those scripts are now frozen; see
  their file headers.
- The 11 per-sector `sector-*/SKILL.md` files were deleted in favor of a
  single templated `skills/sector-research/SKILL.md` + `config/sectors.yaml`.
  Every sector now goes through the same prompt with its config injected.
- Phase 9 evolution 9D (apply approved proposals) and 9E (branch + PR)
  are deliberately out of scope for the scheduled sub-graph; 9A/9B/9C
  still emit JSON artifacts into `state.phase9_evolution`.

The Cowork-based manual runs described above remain valid as an escape
hatch for backfills and operator scenarios, but the scheduled cadence
now flows through the sub-graph.

---

## portfolio sub-graph (portfolio deliberation)

portfolio owns **positioning** — thesis lifecycle, vehicle mapping, analyst
deliberation, PM allocation, risk sizing, and book materialization. research's
Phase 7 digest is **research-only** (no `thesis_tracker`, no
`portfolio_recommendations` on new runs). See
[ADR-0015](../../../../../../docs/adr/0015-research-vs-portfolio.md).

### Boundary diagram

```mermaid
flowchart LR
  subgraph research["research"]
    A7["phase7_synthesis<br/>(research digest)"]
  end
  subgraph portfolio["portfolio"]
    H["h1–h4 thesis pipeline<br/>(planned, not wired)"]
    C["phase7c analysts"]
    D["phase7d PM"]
    E["phase7e sizing + materialize"]
    H -.-> C --> D --> E
  end
  A7 -->|"DigestPayload"| H
  A7 --> C
```

### Live vs intended entry

| Stage | Intended (thesis-first) | Live today |
|-------|-------------------------|------------|
| Research handoff | `phase7_digest` + phases 1–6 segment slots | Same |
| Thesis translation | h2 `market-thesis-exploration` → h3 `thesis-vehicle-map` | **Skipped** — Wave 2 skills deleted, not in graph |
| Analyst roster | Tickers from thesis vehicle map + held names | `select_focus_tickers`: `prior_book` holdings + top-N `price_technicals` scores (#696) |
| Thesis rows | Written when theses are proposed/mapped (h1–h3) | Written post-PM in `portfolio_materialize._upsert_theses` (one row per held ticker) |
| Analyst linkage | Per-ticker analysis tied to `source_thesis_ids` | `AnalystPayload.thesis` is per-axis rationale text only — no thesis_id FK |

The **live** portfolio graph is documented in
[`portfolio/docs/README.md`](../../portfolio/docs/README.md). The **planned** seven-phase
expansion (h1 thesis review through h7 PM memo) remains in
[`PORTFOLIO_SUBGRAPH.md`](../../portfolio/PORTFOLIO_SUBGRAPH.md) and
[`WAVE2_UNIT_SPECS.md`](../../portfolio/WAVE2_UNIT_SPECS.md) for reference; wiring h1–h4
is a separate follow-up ([#924](https://github.com/digithings-ai/digithings/issues/924)) from book-continuity work (#859).

Persistence lands in both `documents` (full payload) and the first-class
tables introduced by migration 024: `theses`, `thesis_vehicles`,
`deliberation_sessions`, `deliberation_rounds`, `analyst_coverage`,
`deep_dive_triggers`.
