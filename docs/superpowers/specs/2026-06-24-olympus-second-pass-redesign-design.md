# Olympus Dashboard — Second-Pass Redesign (Design Spec)

> **Status:** design locked across all surfaces; ready for implementation planning. This is the
> second design cycle for the Olympus dashboard. The first cycle (shipped, live on `main`)
> reshaped the information architecture to four destinations and progressive disclosure. This
> cycle redesigns the inner surfaces that were carried over from old Olympus and never refined,
> and is grounded in a parallel audit of every surface against the live database.

**Date:** 2026-06-24
**Author:** design session (Chris Stefan + Claude)
**Working context:** frontend `frontend/olympus` (Next.js 16 static export, `basePath /olympus`,
React 19, Tailwind v4, recharts, lucide, `@digithings/design`, Supabase). Backend pipeline in
`digiquant/src/digiquant/olympus` (Atlas + Hermes LangGraph sub-graphs). Tear-sheet template in
`frontend/digiquant-web/components/tearsheet`.

**Audit provenance:** an 8-agent parallel design-audit (workflow `olympus-redesign-audit`) read
each surface's code and queried live Supabase. Every surface scored **2/5** against the bar
("would an investor/PM want to use this?"). The briefs converged on a single diagnosis (below).

---

## The diagnosis (the backbone of this cycle)

The second-pass problem is **not visual polish** — the shell, tokens, and several components
already meet the bar. It is two things, found independently on nearly every surface:

1. **Data-layer amputation.** `lib/queries.ts` and `lib/types.ts` drop the richest DB columns
   *before they reach any component.* Theses discards `confidence` / `horizon` / `thesis_kind` /
   `validation_criteria` / `invalidation_criteria` / `linked_market_thesis_id`; Holdings discards
   per-position `conviction` (not even on the `Position` type); System reads the
   `atlas_run_health` **view**, which strips `est_cost_usd` / tokens / grounding / `breakdown`.
   The data exists in Supabase; the mapping throws it away. **Widening the query/type layer is
   the single highest-leverage move** and unblocks three surfaces at once.

2. **Single-day grounding.** The DB holds **one day** (2026-06-23). The v1 surfaces were tuned
   for an active, multi-day world and break on the baseline single-day world that actually
   dominates: Today's hero renders "No rebalance proposed," holdings weights sum to **150%**, the
   NAV line is a single dot, "Knowledge Base" is empty, time-series panels render 1-row tables.

**Pipeline is the hub.** Every other surface is a spoke that **links into** Pipeline (deep-link a
position to its analyst node, a thesis to its provenance day) and **never re-renders** Pipeline's
artifacts. This dissolves the System↔Pipeline, Theses↔Pipeline, and Documents↔Pipeline
duplication.

### Locked program decisions (this session)

| # | Decision | Choice |
|---|---|---|
| D1 | `positions.weight_pct` sums to ~150% | **Overlapping/double-counted rows** — dedupe/normalize so held + cash = 100%; file an upstream seeding fix. Same basis applied to Today's book strip and Theses exposure rollups. |
| D2 | Time-series surfaces are starved (1 NAV point, 0 resolved decisions) | **Backtest-seed now** — seed `nav_history` (equity/drawdown) + a resolved `decision_log` batch so Performance/charts are demo-worthy. Empty-state stays the honest default for fresh self-hosted installs. |
| D3 | `atlas_run_health` view strips run cost/tokens | **Expose cost + cache-hit + tokens** on System (read `atlas_run_diagnostics` directly / new exposing view). "$0.62/run, 39% cached" is a trust signal for a transparent, self-hostable product. |
| D4 | Tear-sheet shape | **Hybrid** — live-NAV track + Olympus-specific decision track-record track, each degrading independently, on one exportable page. |

---

## Grounding finding (applies to the whole cycle)

The database currently holds **a single day of data** (2026-06-23): 71 pipeline `documents`,
7 positions, 10 theses, 11 pending decisions, 2 `atlas_run_diagnostics` rows (1 ok, 1
failed-then-recovered) — but **1 NAV point, 0 `portfolio_metrics` rows, 0 resolved decisions**.

- **Per-day / current-state surfaces are rich today** — the Pipeline (71 real nodes incl. 20
  analysts + 20 deliberation transcripts), holdings, theses, the read, run economics, freshness.
- **Time-series surfaces are starved today** — equity curve, drawdown, rolling Sharpe, decision
  track record, cost-over-time. D2 (backtest-seed) addresses this; until seeded, they empty-state.

**Empty-state discipline (standard across every surface):** time-series elements are gated on a
data predicate (≥2 NAV points, ≥5 runs, ≥1 resolved decision) and render a calm, *element-specific*
line ("equity curve accrues daily" / "11 decisions in flight, resolve as holding windows close" /
"history builds from 2026-06-23") — **never** an em-dash placeholder, a 1-row "table over time," or
a single-dot chart. Per-day elements are the marquee and must carry each surface on a baseline day.

---

## Surface 1 — Pipeline (LOCKED)

### Decision: Pipeline *replaces* Why

The new top-level destination **Pipeline** takes Why's place. Navigation stays at four primary
destinations: **Today / Portfolio / Pipeline / System** (+ Settings). Why's three tabs are absorbed:

- **The Read** (daily digest) → a compact **summary strip** at the top of Pipeline (headline +
  regime chips + the decision), and the **Daily digest node** in the Synthesis stage.
- **Deliberations** → each PM⇄analyst debate is a **clickable H6 node** (Selection → Deliberation
  → {ticker}); the old flat tab is removed.
- **Documents (per-day reading)** → reading a research document = **opening its node**
  (node-detail panel). A cross-day archive is deferred (Surface 6 — Documents).

### What Pipeline is

A **per-day, zoomable graph of the daily decision pipeline** — research → deliberation →
asset-selection on one surface. A **day selector** scopes it to a date.

### Core interaction model — the layout grammar (locked)

**The axis encodes execution semantics:**

- **Sequential steps lay out horizontally** (left → right, time flows rightward).
- **Parallel steps stack vertically** (workers that run at the same time drip downward).

One **zoomable/pannable canvas** with **selective, in-place expansion**:

- Default view shows the collapsed spine: `Inputs → Research → Synthesis → Selection → Decision`.
- **Click a sequential group** (a stage) → expands *in place* into a bracket whose sub-steps run
  **horizontally** (e.g. Selection → Thesis → Screener → Analysts → Deliberation → PM direction →
  Risk sizing).
- **Click a parallel node** (a fan-out, count-badged) → expands **vertically** with a branch spine
  (Alt-data → 6, Sectors → 12, Analysts → 20, Deliberation → 20).
- **Click a leaf node** → opens that step's persisted output in the node-detail panel.
- Canvas controls: drag-to-pan, scroll/buttons to zoom, **Fit**, **Expand all** / **Collapse**.

### Required behaviors (from review of the mockup)

1. **Camera auto-centers on the opened section** — expanding recenters the viewport dynamically.
2. **No overflow on expansion; production-clean visuals** — clean SVG branch connectors (not CSS
   approximations); consistent spacing/sizing/alignment; explicitly no "AI-slop" rough edges.
3. **Reduced-motion honored; responsive** — mobile: node-detail becomes a bottom sheet; the canvas
   pans within a clipped viewport; the page body never scrolls horizontally.

### Mapping to the real pipeline (topology static; fan-out widths runtime)

| Stage (sequential) | Sub-steps (sequential, horizontal) | Parallel fan-outs (vertical) |
|---|---|---|
| Inputs | Preflight / market data | — |
| Research (Atlas 1–5) | Alt-data · Institutional · Macro · Asset-classes · Sectors | Alt-data ×6, Institutional ×2, Asset-classes ×6, Sectors ×12 |
| Synthesis (6–7) | Consolidate bias · Daily digest | — |
| Selection (Hermes H1–H8) | Thesis framing (H1–3) · Screener (H4) · Analysts (H5) · Deliberation (H6) · PM direction (H7) · Risk sizing (H8) | Analysts ×N(roster), Deliberation ×N(roster) |
| Decision (H9) | Commit | — |

### Data backbone — clicking a node is a query, not a re-run

Grouping key: `date` (ISO) for `documents` / `daily_snapshots` / `positions` / `nav_history` /
`theses`; `run_date` for `decision_log`; `run_id` for `atlas_run_diagnostics`.

| Node | Source | Key |
|---|---|---|
| Research segments | `documents` | `document_key` = segment slug (`alt-*`, `inst-*`, `macro`, `bonds`/`commodities`/`forex`/`crypto`/`equity`/`international`, `sector-*`, `sector-scorecard`) |
| Daily digest ("The Read") | `documents` + `daily_snapshots` | `document_key='digest'`; `daily_snapshots.snapshot` (bias) + `digest_markdown` |
| Analyst (H5) | `documents` | `document_key='analyst/{ticker}'` |
| Deliberation (H6) | `documents` | `document_key='deliberation/{ticker}'` |
| PM direction (H7) | `documents` | `document_key='pm-direction-memo'` |
| Risk sizing / rebalance (H8) | `documents` | `document_key='pm-rebalance'` |
| Decision / commit (H9) | `documents` + `positions` + `nav_history` + `decision_log` | `document_key='commit-run/{run_id}'` |

Pipeline **reuses Documents' rendering stack** for node-detail: `DocumentExpandInline` +
`LibraryDocumentBody` + per-type views (`DigestDocumentView`, `DeliberationDocumentView`,
`AnalystDocumentView`, `RebalanceDocumentView`, `OpportunityScreenerDocumentView`,
`GenericDiffDocumentView`), fed by the `use-library-document` hook keyed on `document_key`.

### Deep-link grammar (LOCKED — six consumers depend on it)

`/pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>` — "open day D, expand stage S, focus
node N." **Keyed off `document_key`, not the legacy `path` field.** `legacy-spa-redirect.tsx`
translates old `/why?...&docKey=` params into this form. Consumers: command palette, Today
doorways, Theses provenance, Holdings linkage, Documents redirects, System links.

### Reference mockup

`/Users/chrisstefan/.claude/jobs/ff9c1ed3/tmp/pipeline-mockup.html` (published artifact
v3-hybrid-seq-par), grounded in the real 2026-06-23 run. Demonstrates the locked grammar; the two
required behaviors above (auto-center, no-overflow/polish) are the known gaps to close in the build.

---

## Cross-surface foundation (Phase 0 — must land first)

These are shared prerequisites, not per-surface work. They are the documented root cause for most
surface failures and would conflict if fixed per-surface.

### F1 — Widen the data layer (`lib/queries.ts` + `lib/types.ts`)

The load-bearing change. Stop dropping columns that already exist in Supabase:

- **Thesis** (`queries.ts:648` mapping, `types.ts:50-57`): add `confidence` (0.0–1.0), `horizon`,
  `thesis_kind` (market | vehicle), `validation_criteria[]`, `invalidation_criteria[]`,
  `linked_market_thesis_id`.
- **Position** (`queries.ts:869`): add `conviction` (unsigned 1–3) and type it on `Position`.
- **Run diagnostics**: add a query reading `atlas_run_diagnostics` directly (`est_cost_usd`,
  `total_tokens`, `cached_tokens`, `llm_calls`, `search_calls`, `grounding_ok/failed`,
  `breakdown` jsonb) — or a curated `atlas_run_economics` view that *exposes* these (D3).

### F2 — IA rename Why → Pipeline (touches shell + every cross-link)

One coordinated change so nav never points at a 404:
- `lib/nav.ts`: replace `{ href:'/why', label:'Why', icon: BookOpen }` with
  `{ href:'/pipeline', label:'Pipeline', icon: GitBranch }` (GitBranch already imported in-repo;
  reads as a DAG, not a digest).
- `sidebar.tsx` `routeActive()`: rewrite the `/why` branch into a `/pipeline` branch that also
  absorbs legacy `/why`, `/research`, `/library` prefixes. **Leave `/portfolio` and `/system`
  branches untouched (verified correct).**
- `command-palette.tsx`: replace the three "Why —" entries with Pipeline-native commands using the
  locked deep-link grammar; re-point `recentDateItems` to `/pipeline?date=…&node=digest` keyed off
  `document_key`. Keep the thesis + recent-run dynamic blocks (palette's best feature).
- `legacy-spa-redirect.tsx`: re-point the three Why-targeting redirects (Research/Library/Strategy)
  to `/pipeline`. Performance/Observability/Architecture/ThesesHub redirects stay correct.
- Update `nav.test.ts` + `sidebar.test.tsx` + drift comments in the same change.
- **Sequencing:** land a `/pipeline` route (placeholder acceptable) in the same change set; if a
  gap is forced, `/pipeline` redirects to `/why` rather than 404.
- Add a visible **"Search… ⌘K" pill** in the sidebar header (+ a Search button in the mobile app
  bar) via the existing `app-shell-context` — the palette is keyboard-only/undiscoverable today.

### F3 — `weight_pct` reconciliation (D1) — shared correctness fix

`weight_pct` rows overlap/double-count across category buckets. **Dedupe/normalize in the query
layer** so held positions + cash = 100%; file an upstream seeding fix. Introduce a **book-
reconciliation primitive** (Invested % / Cash % / — if ever levered — Gross/Net %) sourced from
`nav_history`, used as the single source of truth by **Holdings, Today's book strip, and Theses
exposure rollups**. Never ship a raw 150% headline on any surface.

### F4 — `thesis_id` join normalization — shared correctness fix

`positions.thesis_id` (lowercase tickers `ewt`/`ijr`) ≠ `theses.thesis_id` (`vehicle-ewt`/`MT1`).
Fix upstream for durability, with a **clearly-labelled query-layer normalization** as the interim
so the join is trustworthy now. The same normalized join feeds Theses' "holdings expressing this
thesis," Holdings→thesis links, and Today's book strip.

### F5 — Token hygiene (one rule, applied verbatim everywhere)

Purge off-palette literals: Today's `text-fin-purple` (already aliased to cyan — encodes nothing);
Holdings' `rgba(59,130,246)` weight-bar + `#a78bfa` drilldown line; AdvancedStatsPanel's
`text-fin-purple`; Theses' gradient panel headers + red "Risk radar" gradient; System's three
color-coded card families. **The rule:** cyan `--accent` #3DD6C4 for links/chrome/the single
conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial
values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing
faint regime wash; **no decorative numbering** unless it encodes the system's own priority.

### F6 — Conviction: one canonical encoding

Conviction appears in three shapes — disambiguate, don't triplicate the visual treatment:
- `positions.conviction` (unsigned 1–3) and `theses.confidence` (0.0–1.0) → a **cyan pip/dot
  meter** for unsigned per-row strength.
- `decision_log.conviction` (signed −2..+3) → a **signed +N/−N badge** (fin-green/red) for stance.

Build these as **shared components** reused identically by Holdings, Theses, Performance. (Slop
guard: each instance must encode a *different real quantity* and be the only accent on its row.)

### F7 — Freshness: one shared component

`AsOfBadge` (+ `snapshot-staleness.ts` `isStale`/`formatAge`, `daily_snapshots.created_at`) is the
single freshness component. Settings holds the canonical "last run / which build" Status block;
Today and System hold glanceable inline pills. Do not build three different freshness readouts.

### F8 — Operator-voice → PM-voice copy sweep

Every string an investor/PM reads is product voice. Operator controls (CLI flags, file paths, raw
run lists) live behind a single collapsed "Operator controls" disclosure for self-hosters, never as
hero content. Targets: Theses ("Expand for DB snapshots", "(database)"), Documents ("No files found
for this date"), System (file paths, CLI flags, stale "migration 041 pending" copy), Settings.

### Backend issues to file alongside the frontend work

1. **`weight_pct` seeding fix** — dedupe overlapping category rows so position weights + cash
   reconcile to 100% (D1).
2. **`backtest-seed`** — seed `nav_history` (≥2 points) + a resolved `decision_log` batch so
   time-series surfaces are populated for demos (D2). Program-level data-ops task.
3. **Canonicalize `positions.thesis_id`** to match `theses.thesis_id` (F4 durable fix).
4. **Populate `linked_market_thesis_id`** so the market→vehicle thesis hierarchy has live data.

---

## Surface 2 — Today (landing) — `/`

**Current (2/5):** the hero is wired to `rebalance_actions`, which is empty on baseline/no-trade
days (the common case), so it renders "No rebalance proposed" as the marquee. NAV is a single
undefinable dot. The richest, always-present signals (`actionable_summary`, `risk_radar`,
`confidence`, the regime read) exist and are *already parsed* into `strategy.actionable`/`.risks`
but the page consumes neither. Doorways lean on absent time-series.

**Locked direction — re-ground the hero on what is always present: the read + the book.**

- **Hero** (regime-accented `glass-card`, reuse MoveHero's `REGIME_ACCENT`): eyebrow
  `Today / 2026-06-23 / baseline`; **thesis line** = `strategy.regime` label + `snapshot.headline`
  promoted from caption to `font-display` headline; quiet `0.7 confidence` chip + bias badge.
  **The move is demoted** to a one-line status: "No rebalance today — holding the book" (or
  "N changes today" disclosure when non-empty).
- **Money line, honest for 1 point:** `NAV 99.3 (−0.7% since inception, {date})` from base 100 +
  cash 25% / invested 75%. Gate the daily-delta and benchmark clauses on ≥2 NAV points — don't
  render placeholders.
- **Supporting band 1 — "What to watch"** (replaces the usually-empty Why-today card): render
  `actionable_summary` as 3 ranked rows (priority → rationale) + `risk_radar` as 2 tail-risk rows
  with `horizon_hours`. Already parsed; just consume it. "See the full read" → `/pipeline`.
- **Supporting band 2 — "The book today":** a compact holdings strip (ticker · normalized weight ·
  conviction pips · day move) sorted by conviction or |day move|; surface the day's biggest mover
  (EWT −5.6%) explicitly. Uses the F3 reconciled weight basis. → `/portfolio`.
- **Doorways:** keep Theses (10 active, real) + Portfolio; **retire "How I'm doing"** until
  time-series exists (or replace its body with the real cash/invested split).

**Decision (locked):** hero = regime read with the top-conviction thesis (IJR +3) as the first
supporting row.

**Effort:** medium. **Files:** `app/page.tsx`, `components/today/move-hero.tsx`,
`why-today.tsx`, `today-summaries.tsx`, `components/overview/today-actions-panel.tsx`,
`lib/queries.ts`.

---

## Surface 3 — Portfolio · Holdings — `/portfolio`

**Current (2/5):** the live table renders weights summing to **150%** (raw `weight_pct` printed as
portfolio weight) — a correctness/credibility blocker. The most PM-relevant signals — `conviction`
(dropped in mapping), risk guardrails (`stop_loss_pct`/`target_pct_gain`/`horizon_days`), per-row
P&L — are absent, while near-empty columns (Name 0/7, Category 1/7) take space. Off-palette
blue/purple literals. The 11 pending decisions (proposed changes to *this* book) are invisible.

**Locked direction — a conviction-first, decision-aware positions view that reconciles to 100%.**

1. **Fix the book first:** the F3 reconciliation header strip (Invested / Cash) above the table;
   normalized weights per row; CASH pulled into the strip, not a metric-less table row.
2. **Lead with conviction + risk:** Ticker · Weight (bar) · **conviction pip meter** (F6) · Day %
   and Unrealized % (semantic) · a **risk-envelope micro-cell** (`stop ↔ target` range bar + `Nd`
   horizon chip). Drop empty Name/Category columns; group by `sector_bucket`.
3. **Decision-aware:** per-row decision badge (signed conviction, F6) from `decision_log` for held
   positions; a small **"Proposed by the pipeline" shelf** for `decision_log` tickers not held
   (IWM/QQQ/EWY). Answers "what should I change?" on the page.
4. **Pipeline linkage:** each holding's thesis/decision deep-links into Pipeline for that
   `run_date` (F2 grammar) — Holdings becomes an entry ramp, not a dead end.
5. **Re-tokenize** (F5); target-vs-current column stays hidden until a rebalance payload exists but
   shows a quiet "no target book yet" affordance (not silent absence); `SleeveHistorySection`
   collapses to an empty-state on single-day data.

**Also absorbs from System:** the **Position-risk diagnostics** (advisory stops/targets) relocate
here.

**Effort:** medium. **Files:** `components/portfolio/AllocationsPositionsTable.tsx`,
`PositionDrilldown.tsx`, `SleeveHistorySection.tsx`, `server-metrics-strip.tsx`, `lib/queries.ts`,
`lib/types.ts`.

---

## Surface 4 — Portfolio · Theses — `/portfolio?tab=theses`

**Current (2/5):** three different theses tables (`ThesesTab`, `ThesisDetailPageInner`, legacy
`StrategyThesisPanel` still mounted on Analysis) with disagreeing columns. The `Thesis` type drops
the six richest columns, so no component can show conviction or structured evidence. Operator-voice
copy, gradient slop, status colors that never vary (all 10 are ACTIVE).

**Locked direction — the portfolio's readable RESEARCH LEDGER, split into two linked tiers.**

Prerequisite: **F1** (widen the type/mapping) — nothing below works without it.

- **Landing** (replaces the dense `ThesesTab` table): two calm sections.
  - **Market views** (the 5 `confidence`/`horizon`/`criteria` theses): each a **conviction card** —
    serif claim, a single cyan conviction meter bound to `confidence`, a horizon chip, the book
    weight it drives. Ordered by confidence descending.
  - **Vehicle theses** (the 5 single-name theses): a tighter ticker-keyed list, each showing the
    market view it expresses (once `linked_market_thesis_id` populates; until then grouped under
    **"Unlinked expressions"** with an honest note).
  - One status treatment, reserved for when status leaves ACTIVE.
- **Detail** (replaces the 5-table stack) — the trustworthy artifact: claim/evidence/conviction/
  horizon/status header, then **two side-by-side criteria columns** built from the arrays
  ("What confirms this" = `validation_criteria`, "What breaks this" = `invalidation_criteria`) —
  the single biggest credibility win. Then **"Holdings expressing this thesis"** (F4 join) deep-
  linking to Holdings, and a slim **"Provenance"** strip linking to the Pipeline day (never
  re-rendering the exploration/vehicle-map markdown — that's Pipeline's job).
- **History** collapses to one quiet "tracking from 2026-06-23" line on single-day data.
- **Retire** `StrategyThesisPanel`'s theses block; route Analysis to this canonical surface.

**Decisions (locked):** assume backend populates `linked_market_thesis_id` (ship two-tier +
"Unlinked expressions" fallback; file backend issue); fix `thesis_id` upstream + interim query-
layer normalization (F4).

**Effort:** high. **Files:** `components/portfolio/tabs/ThesesTab.tsx`,
`theses/ThesisDetailPageInner.tsx`, `StrategyThesisPanel.tsx`, `lib/types.ts`, `lib/queries.ts`,
`lib/portfolio-aggregates.ts`.

---

## Surface 5 — Performance tear sheet — new route off Portfolio (D4: hybrid)

**Current (2/5):** no tear sheet exists — `/performance` is a redirect to a legacy SPA tab whose
"Advanced statistics" panel is the canonical AI-slop pattern (a wall of equal-weight `MetricCard`
boxes, `text-fin-purple`). Nothing is exportable. With 1 NAV point + 0 resolved decisions every
chart is empty/single-dot.

**Locked direction — a HYBRID, exportable tear sheet for the single strategy "Olympus," reusing
the digiquant template via a token bridge.** Two stacked, independently-degrading tracks, one
`window.print()` page.

- **Data model:** a TS-mirror `OlympusTearsheet` wrapping the existing `TearsheetData` (live-NAV
  track) **plus** a new `DecisionTrackRecord` type mirroring `backtest.py`'s `BacktestResult`
  (`n_trades`, `hit_rate`, `mean/median_alpha_pct`, `information_ratio`, `sortino_ratio`,
  `max_drawdown_pct`, `conviction_buckets[]`). **Do NOT** bend decisions into the trade-shaped
  `StatBlock`/Long/Short (would force fabricated entry/exit prices).
- **Live-NAV track** (reuse the unified contract honestly): `strategy='Olympus'`,
  `symbol='AI-INTELLIGENCE'`, `engine='live'` (additive to the enum), equity_curve from
  `nav_history`, drawdown derived by the template's `_drawdown_from_equity`, Sharpe/Sortino from
  `portfolio_metrics` when present else via the existing `portfolio-risk-metrics.ts`. Leave
  trade-level fields empty (template already renders their empty-states).
- **Decision track-record track** (the differentiator): a compact KPI rail (Hit rate · Mean alpha ·
  Information ratio · Sortino · Decision max DD · N decisions) + two charts using the template's
  dependency-free `SignedBars`: (1) per-decision signed alpha; (2) **conviction calibration** —
  mean alpha per conviction bucket (THE money chart for an AI stock-picker). A small decision-log
  table reuses `.ts-trades` styling.
- **Hierarchy** (kills the MetricCard wall): one Instrument Serif H1 "Olympus — AI-intelligence
  strategy, live since 2026-06-23," one primary KPI strip, then the two tracks as labeled
  `.ts-panel` sections. Token bridge: `--up→--color-fin-green`, `--down→--color-fin-red`,
  `--ink→--color-text-primary`, `--hair→--color-border-subtle`, etc.
- **Empty-states (default today, first-class):** live-NAV with <2 rows → an "inception" card
  ("NAV 99.32 — live since 2026-06-23 — equity curve accrues daily"); decision track with 0
  resolved → "11 decisions in flight — track record resolves as holding windows close." PDF export
  stays enabled in all states. **D2 backtest-seed** is what makes this populated for demos.

**Decisions (locked):** compute decision metrics **client-side in TS** ported from `backtest.py`
(mirrors `portfolio-risk-metrics.ts`; add a vitest parity test); **backtest-seed** the data (D2).

**Also absorbs from System:** the **Attribution diagnostics** relocate here.

**Effort:** high. **Reuse:** `frontend/digiquant-web/components/tearsheet/*`,
`tearsheet_data.py`, `olympus/atlas/backtest.py`, `lib/portfolio-risk-metrics.ts`,
`lib/performance-series.ts`, the `.ts-*` print CSS.

---

## Surface 6 — Documents archive — defer with a credible stub

**Current (2/5):** `ResearchClient` is 556 lines of MiniCalendar + collapsible filters +
carry-forward manifest plumbing built to navigate many days that don't exist. The "Knowledge Base"
tab is empty in the live taxonomy. It duplicates Pipeline's per-day reading.

**Locked direction — DEFER the standalone archive this cycle; do not ship an empty faceted table.**

1. Per-day reading is fully absorbed by Pipeline node-detail (Pipeline mounts the existing
   `DocumentExpandInline` + per-type views unchanged — reading quality carries over, duplicate
   readers are deleted).
2. The day axis becomes Pipeline's day selector; within-day browse is the graph. **No MiniCalendar,
   no per-date accordion.**
3. **Cross-day discovery = the command palette:** extend it so typing a ticker/segment surfaces
   matching documents across available dates and deep-links to the Pipeline node. Degrades
   perfectly to 1 day.
4. **Remove the Knowledge Base tab** (empty in live data) and the calendar browser. Leave a
   one-line stub for a future faceted archive **gated behind distinct-dates > 1** — until then it
   does not render.

**Decisions (locked):** defer + palette-search seed; remove Knowledge tab; repoint stale
`/why?...&docKey` deep links to the Pipeline node grammar (F2).

**Effort:** low. **Reuse:** the entire doc-rendering stack (handed to Pipeline), `command-palette.tsx`,
`research-doc-categorize.ts` (recomputed against live columns) for any future archive.

---

## Surface 7 — System (How it works) — `/system`

**Current (2/5):** duplicates Pipeline (two phase tables A0–A8 / H1–H9, a 14-card file-path "Phase
map," a 6-chip flow strip). The best data is hidden — run cost/tokens/grounding live in
`atlas_run_diagnostics` but the UI reads the stripping `atlas_run_health` view, and `RunHealthTab`
shows a *stale, false* "migration 041 pending / requires owner sign-off" empty-state (the view is
live). File paths and CLI flags surfaced as product UI.

**Locked direction — reframe around one question: "Is it running, is it healthy, what does it
cost, and how does it work?" Two zones, sharply separated.**

- **Zone 1 — Live status (glanceable hero, real data today):**
  - **Freshness banner** (F7): "Last successful run 2026-06-23 16:58 UTC · baseline · 27/27
    segments"; fin-amber tint if stale; "No runs recorded yet" when empty.
  - **Run-economics row (D3, the differentiator):** Cost/run $0.62 · Tokens 1.64M (39% cached) ·
    LLM calls 163 · Grounding 31/31 — tabular-nums tiles read from `atlas_run_diagnostics`
    directly. The "39% cached → cheaper" chip tells the self-hoster cost story.
  - **Run-health timeline:** narrate the failed→recovered pair as one resilient episode (red dot →
    green dot, "baseline · 2 attempts · recovered"), not two anonymous rows; render as a vertical
    event list (not a sparse 30-row skeleton) when few runs exist.
  - **Per-phase health strip** from `breakdown` jsonb (phase1 6/6 … phase5 13/13) — a segmented bar
    that mirrors Pipeline's stage vocabulary. The ONE place System echoes topology (as a health
    overlay, not a re-listing).
- **Zone 2 — How it works (reference, demoted, de-duplicated against Pipeline):** replace the phase
  tables + file-path map with a tight "Atlas researches → Hermes deliberates → books a portfolio"
  narrative + "See the full graph → Pipeline." Keep ONE honest table: **"What a run persists"**
  (Pipeline doesn't cover this). Model-routing/grounding as prose; CLI flags behind a collapsed
  "Operator controls" disclosure.

**Decisions (locked):** expose cost + cache-hit + tokens (D3, reverses the view policy — your
sign-off given); move **Attribution → Performance** and **Position-risk → Holdings** (System keeps
only engine internals); remove the phase tables + file-path map (keep prose + persistence table +
Pipeline link). Fix the stale RunHealthTab empty-state copy.

**Effort:** medium. **Files:** `components/system/how-olympus-works.tsx`,
`components/observability/RunHealthTab.tsx`, `shared.tsx`, `lib/observability-queries.ts`.

---

## Surface 8 — Settings — `/settings` + sidebar popover

**Current (2/5):** a stub — a Docs link, a theme toggle, a decorative non-functional ⌘K row. The
full page is the popover stretched to `max-w-md`. **Live bug:** `settings-content.tsx` still
hardcodes Docs → `/architecture` (label "Architecture"), contradicting commit `004ac495` which
pointed it to `/system`.

**Locked direction — a compact single-owner CONTROL + STATUS panel (credible, not bloated).** Same
shared component; two presentations (tight popover, fuller multi-card page).

1. **Status / data-freshness card (new, the marquee):** reuse `AsOfBadge` (F7) — "Last run: Jun 23,
   16:13 UTC · 20h ago · baseline"; amber when stale (48h); empty-state "No pipeline runs yet."
   Settings is the canonical "is this current / which build" audit block.
2. **Appearance card:** keep the auto/dark/light tri-toggle exactly as-is.
3. **About / System card:** `NEXT_PUBLIC_OLYMPUS_VERSION`, a friendly data-source host label (never
   the anon key), and the **fixed** Docs → `/system` link.
4. **Replace the decorative ⌘K row** with a real affordance (a "⌘K to search" line in About wired
   to open the palette).

**Do NOT add:** accounts/login, multi-user/roles, notification prefs, API-key management, CSV/JSON
export — no auth exists (anon-key + RLS, single-owner self-hosted) and the data can't back them.

**Decisions (locked):** **hotfix** the `/architecture` → `/system` href + label *now* (live broken
link, independent of the redesign — folded into Phase 0); freshness in both Settings (canonical) and
Today (inline pill); UTC everywhere, explicitly labelled.

**Effort:** low. **Files:** `components/settings-content.tsx`, `sidebar-settings.tsx`,
`app/settings/page.tsx`, `settings-content.test.tsx`.

---

## Surface 9 — App shell (sidebar / palette / mobile)

**Current (2/5 — but craft floor is high, 4/5):** the shell is genuinely good (glass sidebar with
cyan active rail, collapsible, real keyboard palette, clean mobile drawer). It is **materially
stale** against the locked IA: nav still ships "Why"; palette exposes three Why entries; redirects
land on `/why`; `/pipeline` doesn't exist. It would ship a broken nav.

**Locked direction — a precise rename + re-point, NOT a visual redesign.** All of this is **F2**
(see Phase 0): nav.ts Why→Pipeline with GitBranch; `routeActive()` `/why`→`/pipeline` branch;
palette re-authored to Pipeline-native commands + deep-link grammar; redirects re-pointed; visible
⌘K search pill; tests + drift comments updated; nav flip coordinated with the `/pipeline` route.

**Decisions (locked):** keep the mobile **drawer** for this pass (bottom tab bar = fast-follow);
GitBranch icon; query-param deep-link scheme (F2).

**Effort:** medium (mostly Phase 0). **Files:** `lib/nav.ts`, `components/sidebar.tsx`,
`command-palette.tsx`, `app-shell-context.tsx`, `legacy-spa-redirect.tsx`, `nav.test.ts`,
`sidebar.test.tsx`.

---

## Build sequence

| Phase | Surfaces | Why here |
|---|---|---|
| **Phase 0 — Foundation (first)** | F1 data-layer widening · F2 Why→Pipeline rename + shell + palette + redirects + tests · F3 weight_pct reconciliation · F4 thesis_id join · F5 token rule · deep-link grammar lock · Documents reader handed to Pipeline · Settings Docs hotfix | Nothing else is honest until these land. The data-layer widening unblocks Theses/Holdings/System at once; the rename must precede `/pipeline` so no link 404s; the weight_pct/thesis_id fixes are shared correctness bugs that would contradict if fixed per-surface. |
| **Phase 1 — Data-rich marquee (parallel)** | Today · Holdings · System | Highest-impact, data-rich-today, consume Phase 0 outputs directly, independent of each other (different components/tables). Makes the product investor-credible on a single baseline day. |
| **Phase 2 — Research ledger + discovery** | Theses · Documents | Theses (high effort) needs F1 widening + F4 join; Documents needs the Pipeline reader wired + palette re-pointed (Phase 0). Holdings' decision badge (Phase 1) is reused by Theses. |
| **Phase 3 — Time-series-gated** | Performance tear sheet | The only surface whose core value is starved today; gated on the D2 backtest-seed. Build the empty-state-first skeleton + data contract any time after Phase 0; it "goes live" once seeding lands. Absorbs Attribution + Position-risk relocated from System. |

The Pipeline surface itself (Surface 1) is a separate locked build; coordinate its `/pipeline`
route to land with the Phase 0 nav flip.

## Slop guards (the redesign's biggest self-inflicted risk is templating itself)

- **Don't stamp one composition across surfaces** (hero/band/band/doorways · Zone1/Zone2 ·
  Section1/Section2). Each surface's structure is driven by ITS data shape (Today = one promoted
  thesis; Holdings = dense comparison table; System = glanceable-vs-reference).
- **Conviction meters** must each encode a different real quantity and be the only accent on the row.
- **Empty-state copy** must vary by what the element is; some elements are simply absent, not
  narrating their emptiness.
- **The tear sheet's KPI rail** is one keystroke from the MetricCard wall it replaces — single
  headline KPI, strict hierarchy, no equal-weight 2×4 grid.
- **Re-tokenizing to cyan** must not produce a monochrome cyan wash — enforce the F5 rule (cyan =
  interactive/live only).
- **"Link to Pipeline"** must be contextual (a position to ITS node, a thesis to ITS provenance
  day), never a generic "View in Pipeline" button cloned five times.

## Out of scope for this cycle

- Re-designing the locked Pipeline surface (Surface 1).
- A standalone cross-day Documents archive (deferred behind distinct-dates > 1).
- Mobile bottom tab bar (fast-follow after the IA-correctness pass).
- Accounts/auth/multi-user, CSV/JSON export, notification prefs (no data/auth to back them).
