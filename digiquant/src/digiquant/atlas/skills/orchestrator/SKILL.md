---
name: market-orchestrator
description: >
  Master orchestrator for the comprehensive daily market analysis pipeline. Triggers when the user says
  "run today's digest", "daily analysis", "morning brief", "market update", or pastes the new-day prompt.
  Supabase-first: phases produce JSON artifacts (publish_document / materialize_snapshot); no
  local markdown trees. Sundays use weekly-baseline; Mon–Sat use daily-delta.
---

# digiquant-atlas — Master Orchestrator

This is the primary entry point for every comprehensive daily digest session.

---

## Supabase-first contract (mandatory)

- **Do not** create local markdown segment trees or filesystem “digest” folders. Canonical work lives in **Supabase** only.
- **Do** load prior state from Supabase (`daily_snapshots`, `documents`, `price_technicals`, `macro_series_observations`).
- **Do** publish structured JSON: `scripts/materialize_snapshot.py` for the digest snapshot;
  `scripts/publish_document.py --payload -` (stdin) for segment docs, portfolio layer, rollups
  (each with a stable `document_key`, e.g. `sectors/energy/2026-04-11.json`).
- **Operator close-out:** `python3 scripts/run_db_first.py` (refreshes metrics, optional `execute_at_open`, validates DB).

Optional local paths used only by fetch scripts or operator helpers are described in [`data/README.md`](../../data/README.md).

Each phase below names a segment skill; deliver **validated JSON** to Supabase per [`RUNBOOK.md`](../../RUNBOOK.md).

**Between phases:** confirm each phase’s JSON is **validated and published** (`validate_artifact.py`, `publish_document.py`) before moving on.

---

## Token Mode Protocol

Caveman mode is **active by default** throughout this pipeline for all process work.

**Keep caveman ON for:**
- Phase start/end announcements and checkpoint verifications
- Triage decisions and sector depth-tier classifications
- Data layer checks and pre-flight status messages
- Inter-phase reasoning about what to update or skip
- Any conversational message to the user about pipeline state

**Switch to normal mode** (`normal mode`) immediately before authoring content that publishes to Supabase:
- Segment narrative blocks (macro, bonds, equity, sector analyses, etc.)
- Digest snapshot JSON narrative/rationale fields
- Rebalance decision rationale
- Deliberation transcript content
- Evolution post-mortem observations and proposals

Switch back to caveman (`caveman mode`) immediately after each artifact is published.

**Quick test**: if the text ends up in a Supabase field → full tokens. If it stays in the conversation → caveman.

---

## Run mode detection (no filesystem meta)

| Condition | Action |
|-----------|--------|
| **Sunday** (or user requests full baseline) | Use `skills/weekly-baseline/SKILL.md` — same 9 phases, but **weekly review + carry-forward + selective rewrites** (append-first, week-ahead bias), then materialize `run_type=baseline` snapshot JSON |
| **Mon–Sat** | Use `skills/daily-delta/SKILL.md` — delta ops JSON → materialize; **do not** run this full orchestrator |

Optional: run `python3 scripts/run_db_first.py --dry-run` to print today’s mode hint and baseline anchor
for deltas (from Supabase).

---

## Full Pipeline (Baseline Mode)

This is the complete 9-phase pipeline. Only run when confirmed in baseline mode.
Follow all 9 phases sequentially. Do not skip phases. Each phase is a dedicated research task with its own **published JSON** in Supabase (not a repo markdown tree).

**Sunday (weekly-baseline):** Phases still run in full, but **authoring** prioritizes **inheriting last week’s published JSON**, **appending** new evidence and forward-looking hooks, and **rewriting only** what is wrong or stale—not a blank-slate regeneration. See `skills/weekly-baseline/SKILL.md`.

---

## Pre-Flight: Session Context Boot

Before starting any phase, **sync the local repository** to ensure you have the latest code (including any merged evolution PRs):

```
git checkout master
git pull origin master
```

Then load the following. Do NOT summarize to the user — just internalize:

1. `config/watchlist.md` — full asset universe
2. `config/investment-profile.md` — investor identity, horizon, risk tolerance, asset preferences, regime playbook
3. `config/hedge-funds.md` — tracked fund reference
4. `docs/ops/data-sources.md` — tracked signal sources, KOL accounts, Polymarket topics
5. **Prior digest** — latest `daily_snapshots` row before today and/or `documents` with `document_key` prefix `digest` (for continuity)

**After loading**, internally note:
- Active theses and their current status
- Macro regime from the last digest (to compare with today)

### Data Layer Check

There are three data sources in priority order:

**Option A — Supabase `price_technicals` (preferred — zero-cost, no scripts needed)**
Check if the GitHub Actions workflow has run recently (fires weekdays at **00:00 UTC**, ~8 PM Eastern during EDT):
```sql
SELECT MAX(date) AS latest_date, COUNT(DISTINCT ticker) AS tickers
FROM price_technicals;
```
The data is **current** if `latest_date` is within the last 3 calendar days — this covers
weekend gaps (Monday morning sees Friday close) and US market holidays like Good Friday.
For morning digest runs, `latest_date` will be the prior trading day's close, never today.
If data is current, query `price_technicals` directly via `mcp_supabase_execute_sql` for all
35 indicators across all 56 tickers at zero cost.  See `skills/data-fetch/SKILL.md` for example
queries and column reference.  Announce: "Supabase data layer confirmed — {date}, {n} tickers."
If `latest_date` is 4+ days old, the workflow may have failed — fall back to Option B.

**Option B — Local scripts (richest output, requires Python + yfinance)**
If Supabase is stale or `quotes.json` / `macro.json` are needed for downstream skills that
read local files, run:
```bash
./scripts/fetch-market-data.sh
# or separately:
python3 scripts/fetch-quotes.py && python3 scripts/fetch-macro.py
```
Running these scripts may produce local `quotes.json` / `macro.json` alongside the fetch output directory for that session; if present, announce it — numerical grounding is available. Prefer Supabase-backed data when current.

**Option C — MCP fallback (sandbox/restricted environments)**
If scripts are unavailable (sandbox, CI, no yfinance), follow `skills/mcp-data-fetch/SKILL.md`
to fetch data via FRED, Alpha Vantage, CoinGecko, and Frankfurter.  This produces the same JSON
schema with slightly reduced coverage (fewer tickers, limited technicals) but is sufficient for
high-quality analysis.  **Check Supabase first** — if `price_technicals` is current, skip
Alpha Vantage entirely and save the 25-call daily budget for prices only.

Skills that consume the data layer:
- `skills/macro/SKILL.md` (Phase 3) — yield curve and VIX from the data layer (Supabase or fetch output)
- `skills/equity/SKILL.md` (Phase 5A) — position technicals from the data layer
- `skills/opportunity-screener/SKILL.md` (Phase 7B) — technical inputs for scoring

Announce to user: "Context loaded. Starting Phase 1 of 9."

### Checkpoint: Pre-Flight
All checks must pass before proceeding. If any check fails, fix the issue (e.g., run `./scripts/new-day.sh`, create missing config) and re-run until clean.

---

## Phase 1 — Alternative Data & Signals

> These signals inform everything downstream. Run them FIRST so that sentiment, positioning, and institutional flows color the macro and segment reads. Alternatives that contradict fundamentals are often the most important signals.

### 1A: Sentiment & News Intelligence
Follow `skills/alt-sentiment-news/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase (`publish_document.py`), document key per RUNBOOK.

### 1B: CTA & Systematic Positioning
Follow `skills/alt-cta-positioning/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 1C: Options & Derivatives Intelligence
Follow `skills/alt-options-derivatives/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 1D: Politician & Official Signals
Follow `skills/alt-politician-signals/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### Checkpoint: Phase 1
Confirms all four alternative-data segment documents are in **`documents`** with substantive payloads. **Do not proceed to Phase 2 until all checks pass.**

---

## Phase 2 — Institutional Intelligence

> Institutional flows and hedge fund positioning reveal where real capital is moving. These signals are often 1-4 weeks ahead of public price moves.

### 2A: Institutional Flows
Follow `skills/inst-institutional-flows/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 2B: Hedge Fund Intelligence
Follow `skills/inst-hedge-fund-intel/SKILL.md` completely.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### Checkpoint: Phase 2
Confirms both institutional segment documents are in **`documents`** with content. **Do not proceed to Phase 3 until all checks pass.**

---

## Phase 3 — Macro Regime Classification

> Macro regime is the anchor for all downstream analysis. The regime output from this phase must be consciously referenced in Phases 4 and 5.

Follow `skills/macro/SKILL.md` completely, **enhanced with**:
- Reference sentiment signals from Phase 1A (do they confirm or contradict macro?)
- Reference CTA positioning from Phase 1B (are systematics aligned with macro?)
- Reference politician/Fed signals from Phase 1D (any policy shift?)

Classify the 4-factor macro regime:
- **Growth**: Expanding / Slowing / Contracting
- **Inflation**: Hot / Cooling / Cold
- **Policy**: Tightening / Neutral / Easing
- **Risk Appetite**: Risk-on / Risk-off / Mixed

This regime classification anchors all subsequent analysis. Record it in the published macro payload.
**Publish:** validated macro segment JSON to Supabase, document key per RUNBOOK.

### Checkpoint: Phase 3
Confirms the macro segment document is in **`documents`** with regime classification. The macro regime anchors all Phase 4–5 analysis — **do not proceed until validated.**

---

## Phase 4 — Asset Class Deep Dives

> Run each asset class analysis through its own dedicated skill. Each reads the macro regime output. Order: bonds → commodities → forex → crypto → international. This order reflects risk hierarchy (safest to most volatile, plus international is DXY-dependent).

### 4A: Bonds & Rates
Follow `skills/bonds/SKILL.md` — reference today's macro regime.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 4B: Commodities
Follow `skills/commodities/SKILL.md` — reference macro regime + bonds/yield output.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 4C: Forex
Follow `skills/forex/SKILL.md` — reference macro regime + bonds.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 4D: Crypto & Digital Assets
Follow `skills/crypto/SKILL.md` — reference macro regime + institutional flow data (IBIT/BTC ETF flows).
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### 4E: International & Emerging Markets
Follow `skills/international/SKILL.md` — reference macro regime + DXY from forex output.
**Publish:** validated segment JSON to Supabase, document key per RUNBOOK.

### Checkpoint: Phase 4
Confirms all five asset-class segment documents are in **`documents`** with content. **Do not proceed to Phase 5 until all checks pass.**

---

## Phase 5 — US Equities: Overview + All 11 Sectors

> US equities is the deepest phase. First establish the market-wide read (breadth, indices, factor exposure), then delegate to each of the 11 GICS sector sub-agents. After all 11 sectors, synthesize into a net equity bias.

### 5A: US Equities Overview
Follow `skills/equity/SKILL.md` with these additions:
- Check market breadth: NYSE Advance/Decline line; new 52W highs vs lows
- Factor performance today: check value (VTV), growth (VUG), momentum (MTUM), quality (QUAL), small cap (IWM) vs large cap (SPY)
- Note the overall market technical trend
- Do NOT do full sector analysis here — that's done in 5B through 5L
**Publish:** validated US equities overview JSON to Supabase, document key per RUNBOOK.

### 5B–5L: Sector Sub-Agents (All 11 GICS Sectors)

**Before running sector sub-agents, classify each sector into a depth tier:**

| Tier | Criteria | Output depth |
|------|----------|--------------|
| **Full** | Current portfolio holding OR screener score ≥ +2 OR sector ETF moved >1% today | Full skill run — comprehensive analysis (~80 lines) |
| **Compressed** | No holding, screener score ≤ +1, sector ETF quiet (<1% move) | 3-paragraph summary: bias + 3 key drivers + 1 portfolio implication (~25 lines) |

On a typical day expect 3–5 Full sectors, 6–8 Compressed. This reduces sector token cost by ~50% vs running all 11 at full depth.

Run each sector skill (Full) or compressed summary (Compressed) sequentially. Each reads the macro regime output and references Phase 5A.

| Phase | Skill | Published segment (document key per RUNBOOK) |
|-------|-------|-----------------------------------------------|
| 5B | `skills/sector-technology/SKILL.md` | e.g. `sectors/technology/{{DATE}}.json` |
| 5C | `skills/sector-healthcare/SKILL.md` | `sectors/healthcare/...` |
| 5D | `skills/sector-energy/SKILL.md` | `sectors/energy/...` |
| 5E | `skills/sector-financials/SKILL.md` | `sectors/financials/...` |
| 5F | `skills/sector-consumer-staples/SKILL.md` | `sectors/consumer-staples/...` |
| 5G | `skills/sector-consumer-disc/SKILL.md` | `sectors/consumer-disc/...` |
| 5H | `skills/sector-industrials/SKILL.md` | `sectors/industrials/...` |
| 5I | `skills/sector-utilities/SKILL.md` | `sectors/utilities/...` |
| 5J | `skills/sector-materials/SKILL.md` | `sectors/materials/...` |
| 5K | `skills/sector-real-estate/SKILL.md` | `sectors/real-estate/...` |
| 5L | `skills/sector-comms/SKILL.md` | `sectors/comms/...` |

**Publish** each sector payload to Supabase (`publish_document.py`) with the stable key for that sector and date.

### 5M: Sector Synthesis
After all 11 sectors, produce a sector scorecard:
```
SECTOR SCORECARD — {{DATE}}
| Sector | ETF | Bias | Confidence | Key Driver |
|--------|-----|------|------------|------------|
| Technology | XLK | OW/UW/N | H/M/L | [1 word] |
| Healthcare | XLV | OW | H | defensives bid |
| Energy | XLE | OW | H | Iran geopolitical |
...all 11
```
Aggregate into: Net Equity Bias (Bullish / Bearish / Neutral / Conflicted) with rationale.

### Checkpoint: Phase 5
Confirms the US equities document and all 11 sector documents are in **`documents`** with content (full or compressed tier as triaged). **Do not proceed to Phase 7 until all checks pass.**

---

## Phase 7 — Master synthesis (digest snapshot JSON)

> Now that all segment payloads for the run are published, synthesize them into the final master digest. This is NOT a regurgitation — it is a synthesis. Pull the most important signals across all phases and generate a coherent, actionable daily brief.

**Track boundary:** Phase 7 (through `materialize_snapshot` / `documents.digest`) is the **last step of research** — the digest is the **research** rollup of all sub-segments, **not** something the portfolio manager authors. Track B ([`cowork/tasks/portfolio-pm-rebalance.md`](../../cowork/tasks/portfolio-pm-rebalance.md)) **consumes** this digest after Track A publishes it.

In DB-first mode, the master synthesis is the **digest snapshot JSON** (schema: `templates/digest-snapshot-schema.json`).
The operator publishes it via `python3 scripts/materialize_snapshot.py` which stores the JSON in Supabase and renders markdown for display.

**The digest snapshot JSON must cover the following (as structured fields / narrative blocks):**

1. **Market Regime Snapshot** — Overall risk-on/risk-off. What is the SINGLE dominant force today?

2. **Alternative Data Dashboard** — 1-paragraph synthesis of sentiment, CTA, options, and politician signals. Lead with any signal that contradicts the fundamental/macro read.

3. **Institutional Intelligence Summary** — Key ETF flow direction, any hedge fund signal worth noting, any 13D/13G filing.

4. **Macro** — Full macro segment (regime, data calendar, central banks, geopolitical)

5. **Asset Classes** — Bonds, commodities, forex, crypto, international segments

6. **US Equities** — Overview + Sector Scorecard (all 11, with OW/UW/N + key driver)

   - Flag: ✅ Confirmed / ⚠️ Conflicted / ❌ Challenged / ⏳ No signal today
   - Briefly note which signals confirm or challenge
   - Note if any thesis is approaching its **invalidation trigger**

8. **Portfolio Positioning Recommendations** — Based on today's full synthesis:
   - Current portfolio: list each position with current thesis status
   - Any rebalancing recommendation? (Trim / Add / Hold / Exit) — with explicit rationale
   - Scale of conviction: High / Medium / Low for any recommended change
   - IMPORTANT: Be direct. If the analysis suggests trimming XLE after a +30% run, say so.

9. **Actionable Summary** — Top 5 items to act on or watch TODAY, ranked by priority

10. **Risk Radar** — What could break the current bias in the next 24-72 hours?

**Quality standards:**
- Be direct. State the bias. Don't hedge everything into meaningless mush.
- Synthesis > repetition. Don't copy-paste segment outputs — extract the key insight from each.
- Contradictions must be flagged explicitly (e.g., "Options show panic, but CTA positioning is still net long — this is a tug-of-war that hasn't resolved.")
- Every section ends with a portfolio implication, not just description.

Do not write freeform markdown as the source of truth. JSON is canonical; markdown is derived.

### Phase 7 — Snapshot payload

Produce the full digest snapshot payload as the authoritative artifact for publishing.
Upsert it to Supabase using `scripts/materialize_snapshot.py` (stdin or file path per RUNBOOK).

**Schema**: See `templates/digest-snapshot-schema.json` (and related snapshot field docs in `templates/`).

The snapshot object includes at minimum:
- `schema_version`: `"1.0"`
- `date`: `"{{DATE}}"`
- `run_type`: `"baseline"` or `"delta"` (from session mode / `run_db_first.py --dry-run`)
- `baseline_date`: null for baselines, the baseline date for deltas
- `regime`: label, bias, conviction, summary, factors (from Market Regime Snapshot section)
- `positions[]`: each position from the Portfolio Positioning table — ticker, name, weight_pct, action, thesis_id, rationale, current_price, entry_price, entry_date
- `theses[]`: each row from the Thesis Tracker table — id, name, vehicle, invalidation, status, notes
- `market_data`: key levels used in the digest (SPY, QQQ, VIX, DXY, US10Y, WTI, Gold, BTC, etc.)
- `segment_biases`: bias per segment (macro, bonds, commodities, forex, crypto, international, us_equities)
- `sector_biases`: bias per sector (OW/UW/N + driver)
- `actionable[]`: top 5 action items from the Actionable Summary section
- `risks[]`: risk radar items from the Risk Radar section
- `portfolio_posture`: Defensive / Neutral / Offensive
- `cash_pct`: cash allocation percentage

**Important**: All numerical values (prices, weights, yields) must be actual numbers, not strings.
Positions weights must sum to approximately 100%. Use the data already gathered during the pipeline —
this step should be a simple marshaling of existing analysis, not new research.

### Checkpoint: Phase 7
Validate the snapshot JSON (`validate_artifact.py`) and ensure required logical sections exist (regime, theses, actionable, risks). **Do not proceed to Phase 7B until validated.**

---

## Phase 7B — Opportunity Screen

> Systematic scan of the full ETF watchlist against today's research. Translates digest
> findings into a ranked list of tickers worth analyst coverage — both current holdings
> (mandatory) and new opportunity candidates (screener-selected).

**Thesis-first Track B (full portfolio task):** run [`skills/market-thesis-exploration/SKILL.md`](../market-thesis-exploration/SKILL.md) → [`skills/thesis-vehicle-map/SKILL.md`](../thesis-vehicle-map/SKILL.md) **before** this screen when executing [`cowork/tasks/portfolio-pm-rebalance.md`](../../cowork/tasks/portfolio-pm-rebalance.md). The screener’s **Step 0** then prefers published **`thesis_vehicle_map`**.

Follow `skills/opportunity-screener/SKILL.md` completely:

1. Load `thesis_vehicle_map` for `{{DATE}}` when present; then `config/watchlist.md` + today's segment outputs + macro regime
2. Score every ticker: regime alignment + signal scan (flows, options, CTA, thesis, sector bias)
3. Rank and filter: current holdings are mandatory; top 3-5 non-held tickers with Total ≥ +2 become opportunity candidates (subject to Step 0 map seeding)
4. Publish **`opportunity_screen`** JSON to Supabase (`documents`)

The screener output defines the **analyst roster** for Phase 7C deliberation.

Announce: "Screen complete. [N] tickers scanned, [M] opportunities identified. Analyst roster: [list]"

### Checkpoint: Phase 7B
Verifies **`opportunity_screen`** is published to **`documents`**. **Do not proceed to Phase 7C until validated.**

---

## Phase 7C — Analyst-PM Deliberation

> Multi-round deliberation: analysts present thesis-driven recommendations, PM challenges
> weak or conflicting positions, analysts defend or revise. Produces higher-conviction
> portfolio inputs through structured debate.

Follow `skills/deliberation/SKILL.md` for the **per-ticker conference** protocol (publish `deliberation-transcript/{{DATE}}/{{TICKER}}.json` + `deliberation-transcript-index/{{DATE}}.json`). **Unbounded rounds** until `meta.converged` per ticker.

1. Analyst roster from published **`opportunity_screen`** + holdings
2. **`asset_recommendation`** JSON per ticker (Supabase), then deliberation rounds
3. **`deliberation_session_index`** listing all per-ticker keys

Announce after completing: "Deliberation complete. [N] tickers, session index published."

### Checkpoint: Phase 7C
Verifies per-ticker `deliberation_transcript` payloads and session index in **`documents`**. **Do not proceed to Phase 7D until validated.**

---

## Phase 7D — Portfolio Manager Review

> Clean-slate portfolio construction followed by comparison vs current positions.
> This phase produces the rebalance decision — the most actionable output of the full pipeline.

When running the **thesis-first** task: publish **`pm_allocation_memo`** (`skills/pm-allocation-memo/SKILL.md`) **before** portfolio-manager Phases B/C.

Follow `skills/portfolio-manager/SKILL.md` **Phases A (ingest), B, and C** completely (DB-first JSON to Supabase):

**Phase A:** merge `final_decisions` from per-ticker deliberation transcripts (+ optional `pm_allocation_memo`).

**Phase B (Clean-Slate — blinded to current weights):** compute ideal target weights as **working notes** (do not publish a `portfolio_recommendation` document).

**Phase C (Comparison — load current weights):** diff vs `config/portfolio.json`; publish `rebalance_decision`; update `proposed_positions[]`.

### Checkpoint: Phase 7D
Verifies `rebalance_decision` in **`documents`** and `portfolio.json` proposed_positions. **Do not proceed to Phase 8 until validated.**

---

## Phase 8 — Supabase Publish + Commit

> Pushes all analysis data to Supabase so the web dashboard updates instantly — no redeployment needed.

### 8A: Generate snapshot.json (if not already written by Phase 7)
Run: `python3 scripts/generate-snapshot.py`
Produce the digest snapshot JSON (schema `templates/digest-snapshot-schema.json`) and publish with `materialize_snapshot.py` — Supabase is canonical.

### 8B: Metrics + DB validation
After `materialize_snapshot.py` / `publish_document.py` have run, execute:
`python3 scripts/run_db_first.py`  
This refreshes performance metrics, runs `execute_at_open.py` when appropriate, and `validate_db_first.py`.

The frontend reads from Supabase at runtime. If validation fails, check `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` and that today’s snapshot row exists in `daily_snapshots`.

### 8C: Commit and push
Run: `./scripts/git-commit.sh` to commit **config / docs** changes only. Digest data is already in Supabase.

### Checkpoint: Phase 8
Verifies Supabase tables have current data for today's date. **Do not proceed to Phase 9 until validated.**

---

## Phase 9 — Post-Mortem & Evolution

> Self-improvement loop. The pipeline gets smarter every day by recording what worked,
> what didn't, and proposing refinements. This phase has **strict guardrails** to prevent
> uncontrolled drift.

### 9A: Source Scorecard Update
- **Sources Used Today**: Rate every data source accessed (1-5 stars for quality/freshness)
- **Sources That Failed**: Log any that were unavailable, paywalled, stale, or returned errors
- **New Sources Discovered**: Record any new X accounts, URLs, or data providers found during research
- **GUARDRAIL**: Do NOT modify `docs/ops/data-sources.md` — only record observations in the JSON artifact
- **Publish:** `evolution_sources` JSON — schema `templates/schemas/evolution-sources.schema.json` (`publish_document.py`). **Optional:** `./scripts/scaffold_evolution_day.sh {{DATE}}` to create starter files where the script writes them (see RUNBOOK).

### 9B: Quality Post-Mortem
- **Signal Accuracy**: Check yesterday's actionable items and predictions — were they correct? Mark ✅/❌/⏳
- **Coverage Gaps**: Note data you wanted but couldn't find (missing indicators, sectors with thin analysis)
- **Data Freshness Issues**: Flag any data that was stale or delayed
- **Quality Score**: Self-assess today's digest on these 5 dimensions (1-5 scale each):
  - Data completeness | Signal clarity | Actionability | Continuity with prior | Positioning quality
- **Publish:** `evolution_quality_log` JSON — schema `templates/schemas/evolution-quality-log.schema.json`

### 9C: Improvement Proposals

**STRICT RULES FOR PROPOSALS:**
1. You may ONLY propose changes — **never execute them directly**
2. Maximum **2 proposals per session** to prevent drift
3. Each proposal must specify: target file, exact change, rationale with data
4. Categories: `Source Addition` | `Skill Refinement` | `Template Update` | `Efficiency`
5. **LOCKED — you may NOT propose changes to:**
   - Output schema/structure (digest snapshot schema `templates/digest-snapshot-schema.json` is immutable)
   - Risk profile or position sizing (`config/investment-profile.md` §4 Risk Constraints)
   - These guardrails themselves
6. Read today’s proposals payload before filing to avoid duplicates
- **Publish:** `evolution_proposals` JSON — schema `templates/schemas/evolution-proposals.schema.json`

### 9D: Document Applied Improvements
If any previously pending proposals have been approved and applied during this session, document them in `docs/evolution-changelog.md` with:
- Date applied, proposal ID, category
- Target file(s) and exact change made
- Rationale (reference quality-log or sources JSON evidence)
- Expected measurable impact
- Commit hash

### 9E: Evolution Branch & PR
After completing the post-mortem, commit evolution artifacts to a **dedicated branch** and open a PR:
`./scripts/git-commit.sh --evolution`

This script will:
1. Create a branch named `evolve/YYYY-MM-DD`
2. Stage evolution JSON artifacts and `docs/evolution-changelog.md` as implemented by the script
3. Push the branch and create a GitHub Pull Request
4. Switch back to `master` so the repo is clean for the next daily run

**The PR requires manual user approval before merging into master.** This ensures no pipeline changes are applied without explicit review. Approved proposals will only take effect once the PR is merged and the next session pulls the latest master.

### Checkpoint: Phase 9
Verifies evolution post-mortem payloads are complete per RUNBOOK (and any files created by `git-commit.sh --evolution` when used).

---

## Final validation

```bash
python3 scripts/validate_db_first.py --validate-mode full
```

Fix any reported gaps in Supabase rows before ending the session.

---

## Session Completion Checklist

Confirm all of the following before ending the session:

- [ ] Phase 1: 4 alternative data segments published
- [ ] Phase 2: 2 institutional intelligence segments published
- [ ] Phase 3: Macro segment published
- [ ] Phase 4: Bonds, commodities, forex, crypto, international segments published
- [ ] Phase 5: US equities + 11 sector segments published
- [ ] Phase 7: Digest snapshot published (`materialize_snapshot.py`)
- [ ] Phase 7B: Opportunity screen JSON published (`documents`); analyst roster determined
- [ ] Phase 7C: Deliberation + analyst outputs published as JSON documents
- [ ] Phase 7D: `rebalance_decision` published; `portfolio.json` updated when approved
- [ ] Phase 8: `run_db_first.py` completed; `validate_db_first.py` clean
- [ ] Phase 9: Post-mortem completed; evolution JSON published (and optional `./scripts/git-commit.sh --evolution` if using that flow)

**All segment and portfolio artifacts publish as JSON into Supabase `documents` (and `daily_snapshots` for the digest).**

Print to user: "✅ Digest complete. Supabase updated. Run `git-commit.sh --evolution` when filing evolution PRs."

---

## Quality Principles (Always Apply)

1. **Search for everything.** Never rely on training data for prices, yields, levels, or news.
2. **Maintain continuity.** Every analysis explicitly references prior context from previous day's outputs. This is NOT a fresh-start diary — it's a living research thread.
3. **Be opinionated.** The user is an experienced investor. They need a clear directional read, not a "on the one hand / on the other hand" recitation.
4. **Thesis-driven.** Every position has an explicit thesis. Flag when reality contradicts it.
5. **Macro-first filtering.** The Phase 3 regime anchors everything. If a sector conflicts with the macro regime, say so explicitly.
6. **Institutions before technicals.** If institutional flows and technicals conflict, weight flows more heavily in the short run; technicals in the medium-term.
7. **Signal hierarchy**: Primary: Fundamental regime change → Secondary: Institutional flows → Tertiary: Sentiment → Quaternary: Technical levels.

