# R7 twelve-x: inventory of what moves into the existing repo (DIG-3568)

Parent epic DIG-3518. Source: plan PR #5695 (`docs(root): repo split review and
phased migration plan`, open) and `repo-split.md` section R7 plus section 1g/3.

Verified against `digithings-ai/digithings@github/develop` **`d227b6ed5`**
(2026-10-14) and `twelve-x@HEAD` in this run. Counts are `git ls-tree` counts,
not estimates. Refactor-first couplings (§1) are unchanged by this leaf; only
the R7 move list and its merge analysis are in scope.

Chris 22:09 14 Oct (applies to this leaf): GitHub Actions minutes are
exhausted, so missing Actions checks are not failures. This PR carries its
local test pass in the PR body. Docs PR into `develop` via feature branch.
No repo creation, no `main`, no production deploys, no Cloudflare changes.

## 1. What moves: 122 files, two groups

| Group | Paths on develop | Files |
|---|---|---|
| twelve-x desk surface | `apps/dashboard/components/twelve-x/` (72), `apps/dashboard/lib/twelve-x/` (36), `apps/dashboard/app/twelve-x/page.tsx` (1) | 109 |
| twelve-x-only D1 API | `apps/digidata-api/` | 13 |
| **Total** | | **122** |

Of the 109 desk files, **53 are `*.test.ts(x)`** colocated suites; 56 are
implementation. No non-TS assets (no CSS, no fixtures, no markdown) move.

### 1a. Desk surface, full list

`apps/dashboard/app/twelve-x/` (1):

- `page.tsx` — thin server wrapper: `Suspense` + `ClientProductGate`
  (`productKey="fx_hub"`) + `TwelveXClient`. Renders inside the standard
  AppFrame shell. Route is DB-exempt by design (client gates itself on its own
  research feed via `isTwelveXConfigured`).

`apps/dashboard/lib/twelve-x/` (36):

- `consensus-bar.test.ts`, `consensus-bar.ts`
- `consensus-chart.test.ts`, `consensus-chart.ts`
- `consensus-derive.test.ts`, `consensus-derive.ts`
- `consensus-view.test.ts`, `consensus-view.ts`
- `divergence-accuracy.test.ts`, `divergence-accuracy.ts`
- `divergence.test.ts`, `divergence.ts`
- `fetch.test.ts`, `fetch.ts` — typed fetchers over the **dedicated twelve-x
  Supabase client** (`./supabase`), not the dashboard singleton; row types in
  `./types.ts`
- `format.ts`
- `idea-continuity.test.ts`, `idea-continuity.ts`
- `ledger-classes.test.ts`, `ledger-classes.ts`
- `level-vs-fix.test.ts`, `level-vs-fix.ts`
- `matrix-format.test.ts`, `matrix-format.ts`
- `session.test.ts`, `session.ts` — bridges dashboard (core project) login
  into a twelve-x Supabase session via core settings Edge Function
  (`GET /access/twelvex-session`, gated on `client_product_grants`
  `product_key='fx_hub'`) plus twelve-x's own `fx-hub-session` function
- `supabase.ts` — dedicated twelve-x client (separate Supabase project)
- `track-record.test.ts`, `track-record.ts`
- `trade-close-reasons.test.ts`
- `trade-history.test.ts`, `trade-history.ts`
- `trade-levels.pending-levels.test.ts`, `trade-levels.test.ts`, `trade-levels.ts`
- `types.ts` — contract row types for all twelve-x tables
- `wilson.ts`

`apps/dashboard/components/twelve-x/` (72):

- `BankVsQuantPanel.test.tsx`, `BankVsQuantPanel.tsx`
- `BoardDateRangeFilter.tsx`
- `BriefPanel.test.tsx`, `BriefPanel.tsx`
- `BriefsIndex.test.tsx`, `BriefsIndex.tsx`
- `BrokerProfilePanel.test.tsx`, `BrokerProfilePanel.tsx`
- `CalibrationPanel.test.tsx`, `CalibrationPanel.tsx`
- `ConsensusDataTable.test.tsx`, `ConsensusDataTable.tsx`
- `ConsensusScoreBars.test.tsx`, `ConsensusScoreBars.tsx`
- `ConsensusTab.test.tsx`, `ConsensusTab.tsx`
- `CurrencyDrilldownPanel.test.tsx`, `CurrencyDrilldownPanel.tsx`
- `DeltaChip.tsx`
- `DigestBrief.test.tsx`, `DigestBrief.tsx`
- `DivergenceChip.test.tsx`, `DivergenceChip.tsx`
- `DivergencePanel.tsx`
- `EventDetailPanel.test.tsx`, `EventDetailPanel.tsx`
- `EventsTab.open-state.test.tsx`, `EventsTab.test.tsx`, `EventsTab.tsx`
- `EventsTimeline.test.tsx`, `EventsTimeline.tsx`
- `ExcursionRangeCell.dom.test.tsx`, `ExcursionRangeCell.tsx`
- `HowItWorksTab.test.tsx`, `HowItWorksTab.tsx`
- `IdeaCardsIndex.test.tsx`, `IdeaCardsIndex.tsx`
- `IdeaPanel.test.tsx`, `IdeaPanel.tsx`
- `LevelFixChart.test.tsx`, `LevelFixChart.tsx`
- `LevelFixSection.dom.test.tsx`, `LevelFixSection.test.tsx`, `LevelFixSection.tsx`
- `MatrixCellHistoryPanel.test.tsx`, `MatrixCellHistoryPanel.tsx`
- `MatrixTab.open-state.test.tsx`, `MatrixTab.test.tsx`, `MatrixTab.tsx`
- `OppositionLedger.test.tsx`, `OppositionLedger.tsx`
- `TodayConsensusChart.test.tsx`, `TodayConsensusChart.tsx`
- `TodayTab.test.tsx`, `TodayTab.tsx`
- `TrackRecordTab.test.tsx`, `TrackRecordTab.tsx`
- `TradeIdeasPanel.test.tsx`, `TradeIdeasPanel.tsx`
- `TradesTab.dom.test.tsx`, `TradesTab.test.tsx`, `TradesTab.tsx`
- `TwelveXClient.hydration.test.tsx`, `TwelveXClient.test.tsx`, `TwelveXClient.tsx`
- `TwelveXHeading.tsx`, `TwelveXSectionHeading.tsx`
- `WilsonStat.test.tsx`, `WilsonStat.tsx`
- `context.tsx`, `useWatchlist.ts`

### 1b. `apps/digidata-api/` (13), twelve-x-only D1 API

- `README.md`, `package.json` (`digidata-api`, private, `wrangler`/`vitest`/`typescript` devDeps), `tsconfig.json`, `vitest.config.ts`, `wrangler.toml`
- `src/index.ts`, `src/types.ts`, `src/query.ts`, `src/backends.ts`, `src/tables.twelvex.ts`, `src/index.test.ts`
- `d1/twelvex/0001_init.sql` (**26 `CREATE TABLE` statements**, all `IF NOT EXISTS`), `d1/twelvex/0001_init.notes.md`

Data-store facts (Data & Backups seat):

- `wrangler.toml` binds **only `TWELVEX_DB`** (`database_name "twelvex"`,
  placeholder id `00000000-…-d1a1` = local-only). `workers_dev = false`, and the
  file header states it is **NOT deployed**: no deploy workflow, no routes, no
  custom domain. Deploying or creating a remote D1 needs Chris's approval —
  **not done here, not proposed here.**
- `pickBackend` (`src/backends.ts`): `DATA_BACKEND` unset defaults to
  `"supabase"`; `"d1"` requires the `TWELVEX_DB` binding. Supabase stays the
  default until a cutover project (DIG-2902/2903) — no cutover in this move.
- `tables.twelvex.ts` allowlists **25 `fx_*` tables**; the D1 schema creates 26
  tables (delta of one is the API-exposed subset vs the stored schema —
  recorded, not resolved; both files move together so nothing is lost).
- Secrets are local `.dev.vars` only (`DATA_API_TOKEN`,
  `SUPABASE_TWELVEX_URL/SUPABASE_TWELVEX_SERVICE_KEY`, core equivalents).
  Nothing secret-shaped moves; no values are in the tree.

## 2. How they merge with the current twelve-x tree

- The existing private twelve-x repo (373 tracked files at measured HEAD) is a
  **Python pipeline repo** (repo-root package, `supabase/migrations/` ×37,
  session workflows, `docs/`, `archive/`). It has **no `apps/` directory at
  all** (`grep ^(apps|dashboard|digidata)` over its tree = 0 hits).
- The move is therefore **collision-free by construction**: all 122 paths land
  under `apps/`, a prefix the target repo does not use. No renames, no merges
  of same-path files, no history rewrite needed for correctness of the tree.
- Mechanical move (history extraction at migration time, per repo-split §5 —
  **not executed here**): `git filter-repo --path apps/dashboard/components/twelve-x
  --path apps/dashboard/lib/twelve-x --path apps/dashboard/app/twelve-x/page.tsx
  --path apps/digidata-api` on a fresh mirror clone. The desk page keeps its
  `apps/dashboard/…` paths verbatim so relative `@/…` imports keep resolving
  inside the moved tree.
- Supabase vs D1 overlap: none. twelve-x's 37 `supabase/migrations/` files are
  the **production Supabase schema**; `digidata-api/d1/twelvex/0001_init.sql`
  is a **separate D1 schema** for the twelve-x-only Worker API. Different
  databases, different migration directories, no filename overlap to reconcile.
- `digidata-api` stays **undeployed** after the move (its own header + plan
  agree). Cutover/remote-DB creation is a Chris decision, out of scope.

## 3. Couplings to cut first (D-X1, unchanged, owned elsewhere)

Two dashboard-owned seams reference the moving code; both stay in R0/R3 and
become pluggable, or the desk ships as its own Pages app in R7:

- `apps/dashboard/components/client-product-gate.tsx:20`
  (`ensureTwelveXSession` from `@/lib/twelve-x/session`) — the desk's
  client-product gate.
- `apps/dashboard/components/command-palette.tsx:36-37` (`getBriefs`,
  `FxBriefRow` from `@/lib/twelve-x/*`) — palette rows fed by the twelve-x feed.

Desk npm deps that travel with the pages (`@digithings/design`,
`@digithings/ui`, `@luxalgo/vela 0.8.2`, `@supabase/supabase-js`,
`lightweight-charts`, `recharts`, … — from `apps/dashboard/package.json`):
consumed as **published `@digithings/*` packages** after the R0 publish step
(repo-split §4), not as workspace source. Interim: git-pinned source per §4.

Runtime couplings needing no code change but explicit ownership: cron
dispatch token scope must include R7 (`jobs.ts:16,51` dispatches workflows in
both repos today); R2 bucket bindings are unaffected (digidata-api binds only
`TWELVEX_DB`).

## 4. What this leaf does NOT do (hard limits)

- No repo creation on Cursor Origin or GitHub. No migration or push of
  history. No Cloudflare config changes. No `main` merges. No production
  writes, no database writes, no secret handling. Anything needing those goes
  to Chris as a decision — none is needed for this inventory.
- Refactor-first items (§1a–1g of the plan: strategy entry points,
  `DIGIQUANT_CONFIG_DIR`, dashboard-api unfold, package exports, KV tenant
  move, Dockerfile rework) are other leaves' work and are not duplicated here.

## 5. Verification in this run

- File census: `git ls-tree -r github/develop -- <4 paths>` = **122 rows**
  (72 + 36 + 1 + 13), asserted `== 122` in the producing shell call; 53 test
  files by `*.test.*` count; zero non-TS assets outside `digidata-api`
  config/docs.
- Zero-collision proof: `git ls-tree -r <twelve-x HEAD> | grep -cE
  '^(apps|dashboard|digidata)'` = **0** with the same grep returning 373 total
  rows on that tree (matcher live, both arms).
- D1 counts from any host: `grep -cE '^CREATE TABLE' 0001_init.sql` = 26,
  `grep -c '"fx_' tables.twelvex.ts` = 25.
- Local test pass for this docs-only PR: `python3 -c` markdown structural
  check (headings present, all `apps/…` paths referenced resolve via
  `git ls-tree` at `github/develop`) — green, recorded in the PR body.
  GitHub Actions checks are absent fleet-wide per Chris 22:09 and are not
  failures.
