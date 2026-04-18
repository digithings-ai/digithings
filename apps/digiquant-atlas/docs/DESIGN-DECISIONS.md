# digiquant-atlas — Solution Design Decisions

> Record of key architectural and design decisions with rationale, alternatives considered,
> and trade-offs accepted. Use ADR (Architecture Decision Record) format.

---

## Table of Contents

1. [ADR-001: Three-Tier Cadence Model](#adr-001-three-tier-cadence-model)
2. [ADR-002: Skill Files as Agent Instructions](#adr-002-skill-files-as-agent-instructions)
3. [ADR-003: Sequential Phase Pipeline with Validation Gates](#adr-003-sequential-phase-pipeline-with-validation-gates)
4. [ADR-004: Macro-First Signal Hierarchy](#adr-004-macro-first-signal-hierarchy)
5. [ADR-005: Static JSON + Supabase Dual Data Layer](#adr-005-static-json--supabase-dual-data-layer)
6. [ADR-006: GitHub Pages as Hosting Platform](#adr-006-github-pages-as-hosting-platform)
7. [ADR-007: Evolution Guardrails and Branch-Based Proposals](#adr-007-evolution-guardrails-and-branch-based-proposals)
8. [ADR-008: snapshot.json Structured Sidecar](#adr-008-snapshotjson-structured-sidecar)
9. [ADR-009: Analyst-PM Deliberation Protocol](#adr-009-analyst-pm-deliberation-protocol)
10. [ADR-010: Portfolio.json as Source of Truth for Positions](#adr-010-portfoliojson-as-source-of-truth-for-positions)
11. [ADR-011: MCP Fallback for Data Fetching](#adr-011-mcp-fallback-for-data-fetching)
12. [ADR-012: Single-Agent Sequential Execution](#adr-012-single-agent-sequential-execution)
13. [ADR-013: Research Continuity Design (Supabase per Segment)](#adr-013-research-continuity-design-supabase-per-segment)
14. [ADR-014: Sector Tiering (Full vs Compressed)](#adr-014-sector-tiering-full-vs-compressed)
15. [ADR-015: ETF-Only Investment Universe](#adr-015-etf-only-investment-universe)

---

## ADR-001: Three-Tier Cadence Model

**Status**: Accepted
**Date**: 2026-03

### Context

Running the full 9-phase pipeline every day consumes ~100% of token budget and takes significant wall-clock time. Most weekdays have minimal market changes that don't warrant full re-analysis of all 20+ segments.

### Decision

Implement a three-tier cadence:

| Tier | When | Token Cost | Files Produced |
|------|------|-----------|----------------|
| **Weekly Baseline** | Sunday | 100% | 29 full files |
| **Daily Delta** | Mon-Sat | ~20-30% | 3-8 delta files + materialized DIGEST |
| **Monthly Synthesis** | Month-end | ~40-50% | Cumulative review |

Deltas reference the baseline and only analyze segments with material changes. Three segments (macro, us-equities, crypto) are always written as mandatory deltas.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Full run every day** | Wasteful — ~70% of tokens cover unchanged segments |
| **Run only on demand** | Misses continuity; each run would be a cold start |
| **Event-driven** (run only when thresholds hit) | Hard to define universal thresholds; misses slow-moving trends |

### Trade-offs

- **Pro**: ~70% token savings on typical weekdays
- **Pro**: Baseline provides a stable analytical anchor for the week
- **Con**: Delta materialization adds complexity (applying deltas to produce complete DIGEST.md)
- **Con**: Requires accurate triage — if a segment changes but isn't flagged, it's missed until the next baseline

### Consequences

- `_meta.json` must always be written to track run type
- `new-day.sh` auto-detects Sunday vs weekday
- Delta days must always produce a materialized DIGEST.md (the frontend reads DIGEST.md, not delta files)
- Baseline must be findable by scanning backwards up to 6 days

---

## ADR-002: Skill Files as Agent Instructions

**Status**: Accepted
**Date**: 2025-12

### Context

AI agents need structured instructions to produce consistent, high-quality output. The instructions must be:
1. Versionable in git
2. Composable (sub-skills for sectors, alt-data, etc.)
3. Editable by humans without programming knowledge
4. Readable by any AI agent (not platform-specific)

### Decision

Use Markdown files with YAML frontmatter as the instruction format:

```markdown
---
name: skill-identifier
description: >
  Trigger phrases that invoke this skill.
---

# Skill Name

## Inputs
- files to read first

## Steps
### 1. Step name
- detailed instructions...

## Output Format
...template snippets...
```

*(Historical)* Skills were originally flat `SKILL-{name}.md` and nested under `skills/sectors/`, etc. **Current repo:** canonical packages are **`skills/<slug>/SKILL.md`** (see `docs/agentic/SKILLS-CATALOG.md`). The Markdown-in-repo pattern below still applies.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **YAML config files** | Too structured — hard to express nuanced analytical instructions |
| **Python scripts** | Not agent-readable; requires code execution |
| **JSON instruction sets** | Unreadable by humans; painful to edit |
| **Platform-specific formats** (Claude Projects, Cursor rules) | Lock-in to one platform |

### Trade-offs

- **Pro**: Universal — works with any AI agent that can read files
- **Pro**: Composable — orchestrator can reference sub-skills
- **Pro**: Git-native — full version history of instruction changes
- **Con**: No compile-time validation — a badly-written skill file fails silently at runtime
- **Con**: YAML frontmatter `name:` field is a routing key — changing it breaks references

---

## ADR-003: Sequential Phase Pipeline with Validation Gates

**Status**: Accepted
**Date**: 2026-01

### Context

The 9-phase pipeline has information dependencies:
- Phase 3 (Macro) needs Phase 1 (Alt Data) signals
- Phase 4 (Asset Classes) needs Phase 3 (Macro Regime)
- Phase 5 (Equities) needs Phase 3 + Phase 4
- Phase 7 (Synthesis) needs all of the above
- Phase 7D (Portfolio) needs Phase 7

Running phases out of order or skipping phases produces incoherent analysis.

### Decision

Enforce strict sequential execution with mandatory validation after publish.

```
Phase N → publish JSON to Supabase → validate_db_first.py (full pipeline) → Phase N+1
              │
         FAIL → Block. Fix data in DB or artifacts. Re-validate.
```

Each gate checks:
- Required Supabase rows and document payloads exist for the run date
- Schema-valid JSON was materialized (`validate_artifact.py` on disk when used locally)

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Parallel phases** (e.g., bonds + forex simultaneously) | Phases have cross-dependencies; parallel execution complicates state management |
| **Soft gates** (warn but don't block) | Risks propagating incomplete data downstream |
| **No gates** (trust the agent) | Agent may skip or produce minimal output without accountability |

### Trade-offs

- **Pro**: Guarantees output quality — no skipping phases
- **Pro**: Creates natural checkpoints for session recovery
- **Con**: Increases total pipeline time (sequential bottleneck)
- **Con**: A single failing gate blocks the entire pipeline

---

## ADR-004: Macro-First Signal Hierarchy

**Status**: Accepted
**Date**: 2026-01

### Context

Financial markets have multiple, often conflicting, signal sources. The system needs a consistent framework for resolving conflicts between:
- Fundamental/macro regime
- Institutional flow data
- Sentiment and positioning
- Technical analysis

### Decision

Adopt a fixed signal hierarchy:

```
1. Regime change (macro fundamentals)  ← Most important
2. Institutional flows
3. Sentiment & positioning
4. Technical levels                    ← Least important (but still valuable)
```

Additionally, Phase 1 (Alt Data) runs BEFORE Phase 3 (Macro) so that alternative signals can inform the macro regime read. A sentiment reading that contradicts fundamentals is flagged as the most important signal.

### Rationale

- Macro regime changes drive multi-month trends. A shift from "Growth Expanding" to "Growth Contracting" changes everything.
- Institutional flows often lead price by 1-4 weeks. Large capital moves before retail.
- Sentiment is a contrarian indicator at extremes. Useful for timing, not direction.
- Technicals confirm or deny the above. A breakout that contradicts the macro regime is less trustworthy.

### Trade-offs

- **Pro**: Prevents the agent from producing "on the one hand / on the other hand" analysis
- **Pro**: Prioritizes signals with the best track record for medium-term calls
- **Con**: May underweight technical signals that are sometimes correct on short timeframes
- **Con**: Assumes macro regime changes are detectable in real-time (they often aren't until confirmed by revised data)

---

## ADR-005: Static JSON + Supabase Dual Data Layer

**Status**: Accepted
**Date**: 2026-02

### Context

The frontend needs data to display. Two options:
1. Supabase (hosted PostgreSQL) — queryable, filterable, scalable
2. Static JSON file — no backend, deployable to GitHub Pages

### Decision

Support **both**, with automatic fallback:

```javascript
isSupabaseConfigured()
  ? query Supabase → return data
  : fetch dashboard-data.json → return data

// If Supabase query fails → fall back to static JSON
```

`update_tearsheet.py` generates BOTH:
- `frontend/public/dashboard-data.json` (generated, gitignored — used as static fallback)
- Supabase 8-table push (when credentials available)

### Rationale

- **Static JSON**: Zero-cost hosting on GitHub Pages. Works offline. No authentication needed. Perfect for personal use.
- **Supabase**: Enables time-series queries, filtering, future features (multi-user, alerts). Better performance for large datasets.
- **Dual path**: New users get a working dashboard immediately without database setup. Power users get Supabase when ready.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Supabase only** | Adds setup friction; breaks if Supabase is down |
| **Static JSON only** | No querying; file grows unbounded; no time-series support |
| **SQLite in-browser** | Complex; requires WASM; limited tooling |

### Trade-offs

- **Pro**: Works with zero infrastructure (just GitHub Pages)
- **Pro**: Graceful degradation — Supabase outage doesn't break the dashboard
- **Con**: Dual data paths must be kept in sync
- **Con**: dashboard-data.json grows over time (includes full markdown content)
- **Con**: Two code paths to maintain in queries.js

---

## ADR-006: GitHub Pages as Hosting Platform

**Status**: Accepted
**Date**: 2026-01

### Context

The dashboard is a read-only React SPA that displays pre-computed data. It needs:
- Free hosting
- Custom domain support (optional)
- Automatic deployment from `master` branch
- No backend server required

### Decision

Deploy the Vite-built React SPA to **GitHub Pages** via GitHub Actions.

```yaml
# .github/workflows/deploy.yml
# Trigger: push to master
# Steps: npm ci → npm run build → upload dist → deploy to Pages
```

Base URL: `https://chrizefan.github.io/digiquant-atlas/`
Vite config: `base: '/digiquant-atlas/'`

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Vercel** | More features than needed; external dependency |
| **Netlify** | Similar to Vercel |
| **Self-hosted** | Maintenance burden for a personal project |
| **S3 + CloudFront** | Overkill; adds AWS dependency |

### Trade-offs

- **Pro**: Free, zero-maintenance, built into GitHub
- **Pro**: Automatic deploy on `git push`
- **Con**: Limited to static files (no SSR, no API routes)
- **Con**: Base path required (`/digiquant-atlas/`) — can cause routing issues
- **Con**: No server-side rendering for SEO (not relevant for personal dashboard)

---

## ADR-007: Evolution Guardrails and Branch-Based Proposals

**Status**: Accepted
**Date**: 2026-02

### Context

Phase 9 allows the pipeline to propose improvements to itself. Without guardrails, this creates a risk of:
- Unbounded drift (small daily changes accumulate into fundamental redesigns)
- Breaking changes to templates, risk constraints, or data formats
- No human review of pipeline modifications

### Decision

Strict guardrails:

1. **Proposals only**: Agent may never directly execute changes — only write proposals
2. **Max 2 per session**: Prevents drift from accumulated micro-changes
3. **Locked sections**: Template structure, risk constraints, and guardrails are immutable
4. **Branch + PR workflow**: `git-commit.sh --evolution` creates `evolve/YYYY-MM-DD` branch and opens a PR
5. **Manual merge required**: No auto-merge; operator reviews and approves

### Rationale

The system should get smarter over time, but not autonomously rewrite itself. A human must be in the loop for any structural change.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **No evolution** (static pipeline) | Misses opportunity for systematic improvement |
| **Auto-apply proposals** with rollback | Risk of cascading failures; hard to debug |
| **Unlimited proposals** | Small changes accumulate into uncontrolled drift |

### Trade-offs

- **Pro**: Safe — no pipeline changes without human approval
- **Pro**: Auditable — every change is a PR with rationale
- **Con**: Slow improvement cycle — proposals sit in PRs until reviewed
- **Con**: Operator must actively review PRs (can accumulate)

---

## ADR-008: snapshot.json Structured Sidecar

**Status**: Accepted
**Date**: 2026-03

### Context

The ETL pipeline (`update-tearsheet.py`) originally extracted positions, regime, and theses from DIGEST.md using regex. This was fragile — any format change in the Markdown broke extraction.

### Decision

The agent writes a `snapshot.json` file alongside DIGEST.md. This JSON file contains the same data in a structured, machine-parseable format:

```
DIGEST.md  ← Human-readable analysis (authoritative for narrative)
snapshot.json ← Machine-readable data (authoritative for numbers)
```

`generate-snapshot.py` can also retroactively create snapshot.json from existing DIGEST.md files.

### Schema

```json
{
  "schema_version": "1.0",
  "date": "YYYY-MM-DD",
  "run_type": "baseline|delta",
  "regime": { "label", "bias", "conviction", "summary", "factors" },
  "positions": [{ "ticker", "weight_pct", "action", "rationale", ... }],
  "theses": [{ "id", "name", "vehicle", "invalidation", "status", "notes" }],
  "market_data": { "SPY": 502.3, "VIX": 28.5, ... },
  "segment_biases": { "macro": "Bearish", ... },
  "actionable": ["item1", ...],
  "risks": ["risk1", ...]
}
```

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Regex-only parsing** | Fragile; breaks on Markdown format changes |
| **Structured-only** (drop Markdown) | Loses the human-readable narrative |
| **Database-first** (write only to Supabase) | Loses portability; can't work offline |

### Trade-offs

- **Pro**: Decouples human-readable output from machine-readable data
- **Pro**: snapshot.json can be validated against a JSON schema
- **Con**: Two files to keep in sync — snapshot.json must match DIGEST.md
- **Con**: Legacy compatibility: `update-tearsheet.py` still has regex fallback for old digests without snapshot.json

---

## ADR-009: Analyst-PM Deliberation Protocol

**Status**: Accepted
**Date**: 2026-03

### Context

A common failure mode in AI-generated financial analysis is "one-voice" bias — the same agent writes both the analysis and the portfolio recommendation, leading to confirmation bias.

### Decision

Phase 7C introduces a structured **multi-role deliberation**:

```
Analyst (per ticker) → presents recommendation
PM (portfolio manager) → challenges weak positions
Analyst → defends or revises
PM → Accept / Override / Escalate
```

This creates adversarial tension within the same agent session. The PM role specifically looks for:
- Conflicted bias (analyst says both bullish and bearish)
- Damaged thesis (invalidation trigger hit but position not closed)
- Regime contradiction (position conflicts with macro regime)
- Insufficient data (analyst relied on stale or missing data)

### Rationale

Real money management uses this pattern. Even in a single-agent system, role-switching produces better outcomes than monolithic recommendation.

### Trade-offs

- **Pro**: Reduces confirmation bias
- **Pro**: Produces auditable deliberation transcript
- **Pro**: Catches thesis violations that monolithic analysis might miss
- **Con**: Significantly increases token usage for portfolio phases
- **Con**: Same agent playing both roles is less effective than two independent agents

---

## ADR-010: Portfolio.json as Source of Truth for Positions

**Status**: Accepted
**Date**: 2026-03

### Context

Position data exists in multiple places:
- DIGEST.md (Portfolio Positioning table)
- snapshot.json (positions array)
- Supabase (positions table)
- config/portfolio.json

### Decision

`config/portfolio.json` is the **authoritative source** for actual positions:
- `positions[]` = confirmed actual holdings (operator has executed trades)
- `proposed_positions[]` = agent-recommended changes (pending operator action)

The agent writes to `proposed_positions[]` during Phase 7D. The operator reviews, executes trades, then promotes to `positions[]`.

### Data Flow

```
Agent analysis → proposed_positions[] (Phase 7D)
                      │
                      ▼ (manual review + trade execution)
                Operator promotes to positions[]
                      │
                      ▼
                update-tearsheet.py reads positions[]
                      │
                      ▼
                Supabase + dashboard-data.json
```

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **DIGEST.md as source of truth** | Requires regex parsing; format varies; not machine-friendly |
| **Supabase as source of truth** | Requires database access for all operations; not offline-friendly |
| **Agent auto-updates positions** | Bypasses human review of trade execution |

### Trade-offs

- **Pro**: Clear separation between actual vs recommended
- **Pro**: Simple JSON format; easy to edit manually
- **Pro**: Agent can never auto-trade (proposed requires manual promotion)
- **Con**: Manual step required between recommendation and position update
- **Con**: portfolio.json can drift from reality if operator forgets to update after trades

---

## ADR-011: MCP Fallback for Data Fetching

**Status**: Accepted
**Date**: 2026-04

### Context

The primary data fetch path uses Python scripts (yfinance + pandas-ta) that require a local venv with installed packages. Some environments (CI, sandboxed agents, cloud workspaces) can't install or run these.

### Decision

Implement a **two-tier data fetching strategy**:

```
Tier 1 (preferred): Local Python scripts
  yfinance + pandas-ta → full OHLCV + 6 technical indicators
  US Treasury XML → yield curve
  
Tier 2 (fallback): MCP tool servers
  FRED → yield curve, rates, economic indicators
  Alpha Vantage → stock prices (limited tickers)
  CoinGecko → crypto prices
  Frankfurter → FX rates
  
Both tiers → same JSON output schema
```

`SKILL-mcp-data-fetch.md` documents the MCP fallback path. The output format matches `quotes.json` and `macro.json` schemas so downstream skills don't need to know which tier was used.

### Trade-offs

- **Pro**: Pipeline works in any environment (local, CI, sandbox)
- **Pro**: MCP provides official, rate-limited API access
- **Con**: MCP tier has fewer tickers and limited technical indicators
- **Con**: Two code paths to maintain for same data format

---

## ADR-012: Single-Agent Sequential Execution

**Status**: Accepted
**Date**: 2026-01

### Context

The pipeline could theoretically use multiple specialized agents running in parallel. For example:
- Macro agent + Bond agent + Crypto agent running simultaneously
- Separate agents for Phases 1, 2, 3, 4, 5

### Decision

Use a **single AI agent session** that sequentially reads different skill files to "change hats." All phases run in one session, one after another.

### Rationale

1. **State sharing**: Later phases need context from earlier phases. The macro regime from Phase 3 must inform Phase 4. A single session holds all context in memory.
2. **No orchestration infrastructure**: Multi-agent systems need message passing, state synchronization, and error handling. A single session avoids all of this.
3. **Simpler debugging**: One transcript, one sequence of events.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Multi-agent parallel** (different AI sessions) | State sharing is hard; requires orchestration infrastructure; loses cross-phase context |
| **Map-reduce** (parallelize sectors, reduce into synthesis) | Adds infrastructure; sectors still need macro context from Phase 3 |

### Trade-offs

- **Pro**: Simple — no orchestration infrastructure needed
- **Pro**: Full context available at every phase
- **Pro**: Single transcript for audit
- **Con**: Sequential bottleneck (can't parallelize independent phases)
- **Con**: Long sessions risk timeout or context overflow
- **Con**: If the agent fails mid-session, the entire pipeline must resume from checkpoint

---

## ADR-013: Research Continuity Design (Supabase per Segment)

**Status**: Accepted
**Date**: 2026-02

### Context

AI agents start each session with no memory of prior sessions. The pipeline needs continuity — today's macro analysis should reference yesterday's regime, not start from scratch.

### Decision

Agent continuity is provided by Supabase. At session start, each phase queries the prior entries from `daily_snapshots` (bias/regime rows) and `documents` (segment narratives). The last 3 entries per segment provide enough trend context without overwhelming the context window. New outputs are published at session end via `publish_document.py` or `materialize_snapshot.py`.

### Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| **Full history in prompt** | Context window overflow for mature systems |
| **Local ROLLING.md files** | Superseded — required git commits after every run; no web access |
| **Vector database (RAG)** | Adds infrastructure; overkill for sequential daily entries |
| **No continuity** (stateless) | Loses analytical continuity; each day starts cold |
| **Summary-only** (one paragraph) | Loses granular details needed for trend analysis |

### Trade-offs

- **Pro**: No git commits required after pipeline runs
- **Pro**: Frontend reads same Supabase data — single source of truth
- **Pro**: Enables "What changed since yesterday?" analysis via SQL
- **Con**: Requires Supabase credentials configured in `config/supabase.env`

---

## ADR-014: Sector Tiering (Full vs Compressed)

**Status**: Accepted
**Date**: 2026-03

### Context

Running all 11 GICS sectors at full depth (~80 lines each) on every baseline day consumes significant tokens. Most sectors on a given day are unremarkable.

### Decision

Classify sectors into tiers before analysis:

| Tier | Criteria | Output Depth |
|------|----------|-------------|
| **Full** | Portfolio holding OR screener ≥ +2 OR sector ETF moved >1% | ~80 lines |
| **Compressed** | All others | ~25 lines (3 paragraphs) |

Typical day: 3-5 Full, 6-8 Compressed. Saves ~50% of sector token budget.

### Trade-offs

- **Pro**: Significant token savings without losing coverage
- **Pro**: Focuses depth where it matters (holdings, movers)
- **Con**: May miss slow-building changes in "quiet" sectors
- **Con**: Requires accurate tiering at the start of Phase 5

---

## ADR-015: ETF-Only Investment Universe

**Status**: Accepted
**Date**: 2025-12

### Context

The system could track individual stocks, bonds, or other securities. The investment universe needs boundaries.

### Decision

Track only **exchange-traded funds (ETFs)**:
- ~60 ETFs across all asset classes
- No individual stocks, bonds, or options
- Organized by category: US Equity, International, Crypto, Commodity, Fixed Income

### Rationale

1. **Diversification by default**: Each ETF represents a basket. No single-stock risk.
2. **Data quality**: ETF prices are clean, liquid, and universally available via yfinance
3. **Thesis-friendly**: "Overweight energy" maps cleanly to XLE, not a specific oil company
4. **Reduced complexity**: 60 tickers vs thousands of individual securities
5. **Regulatory safety**: System provides analysis and bias, not specific stock picks

### Trade-offs

- **Pro**: Clean, manageable universe
- **Pro**: Every position is a sector/theme bet, not an idiosyncratic stock bet
- **Con**: Misses individual stock opportunities (e.g., NVDA earnings)
- **Con**: Sector-level analysis may mask subsector dynamics

---

*New decisions should be appended to this document using the ADR format. Each ADR should include:
Status, Date, Context, Decision, Alternatives Considered, and Trade-offs.*
