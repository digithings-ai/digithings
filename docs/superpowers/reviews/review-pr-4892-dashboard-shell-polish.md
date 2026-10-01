# Review — PR #4892 dashboard shell polish

| field | value |
|---|---|
| reviewer | fresh-context subagent (did not author the range) |
| subject | PR #4892, branch `cursor/dashboard-shell-polish-0a7a`, range `14d7db553..6a033058` (HEAD `6a033058279e36a24fd9230da21a929046f73999`, 9 commits, 32 files, +802/−202) |
| scope | `apps/dashboard` only |
| verdict | **approve-with-nits** |
| severity counts | blocker 0 · major 0 · minor 1 · nit 3 |

## Gates run

| check | command | result |
|---|---|---|
| frontend canon | `python3 scripts/check_frontend_canon.py` | `frontend canon guard: clean` |
| touched tests | `cd apps/dashboard && npx vitest run components/shell lib/settings-index.test.ts lib/lw-chart-canon.test.ts app/settings/page.test.tsx components/command-palette.test.tsx components/portfolio/Book{Activity,Attribution,Composition}.test.tsx components/settings components/tearsheet components/twelve-x` | 56 files / 348 tests passed |
| new tests fail without the change | throwaway worktree at HEAD with the 12 changed source files reverted to `14d7db553` (`git checkout 14d7db553 -- <files>`), same vitest run | 14 tests fail, one or more in every file that gained a test: page-header settle (`page header never settled`), single `<main>`, settings search gating (page + lib), connections anchor, palette IA, tearsheet kit table, BookActivity empty state, ConsensusBoard sr-only, ConsensusTab tones, TodayTab `aria-pressed` |
| eslint | `npx eslint <touched dirs/files>` | exit 0 |
| tsc | `npx tsc --noEmit -p .`, then the list of failing files cross-checked against `git diff --name-only 14d7db553..HEAD` | 23 files with errors, all pre-existing test files; **no overlap** with the range |
| forbidden paths | `git diff --name-only 14d7db553..HEAD \| grep -E "^(digikey/\|digiquant/brokers/\|apps/digichat/)\|brokers/callback"` | none |
| naming / secrets / live-trading | `git diff 14d7db553..HEAD \| grep '^+' \| grep -E "Digi[A-Z]\|sk-…\|live[- ]trad\|BEGIN (RSA\|PRIVATE)"` | none |

## Areas checked and found correct

- **PageHeaderProvider `setSpec` fix** (`components/shell/page-header.tsx:39-40`). `setSpec` is now `useCallback(..., [])`. `grep -rn "setSpec\|usePageHeader("` shows the only consumers are `app/settings/page.tsx:41` and `app/house/page.tsx:20`, and both pass only `title`. The settle loop is fixed for every current caller. There is a residual hazard, which is the minor finding below.
- **Tier gating in `filterSettingsIndex`** (`lib/settings-index.ts:43-51,57-74`). An entry is reachable only if its section is visible **and** its anchor's `SECTION_ALIASES[...].tab` is visible. This is the same rule `resolveId` applies (`lib/settings-sections.ts:118-129`).
  - Every index anchor has an alias: an existing test enforces this ("every entry anchor resolves through the alias table").
  - Gated anchors are rendered only when visible: `#profile` (`app/settings/page.tsx:166`) and `#brokers` / `#keys` (`components/settings/connections-section.tsx:250-251`).
  - The only consumer is `app/settings/page.tsx:127`.
  - No tier has `keys` without `brokers`: `overlay_profile` is Studio+, `broker_status` is Desk+ (`lib/entitlements.ts:58-70`).
  - I found no way for a gated setting to surface.
- **Accessibility.**
  - Kit `TableRowHeader` emits `scope="row"` (`packages/ui/src/ui/table.tsx:136-140`), and the test asserts it in markup.
  - Both migrated tables carry an `aria-label`.
  - The ConsensusBoard disputed marker moved from `aria-label` on a role-less `<span>` (ignored by assistive tech) to `aria-hidden` glyph + `sr-only` text. That is an improvement.
  - The TodayTab toggle now exposes `aria-pressed` and fixes the "callss" plural bug.
  - The confluence glyph is `aria-hidden`, so the direction is still read as text.
- **Command palette.**
  - `decisionsHref()` gives `/portfolio?tab=decisions`, and `decisionsHref('theses')` gives `...&pane=theses` (`lib/portfolio-url-state.ts:124-128`). These match `nav-model.ts:49-56` (Book `/portfolio`, Performance `/portfolio/performance`, Decisions `tab=decisions`).
  - The dropped Attribution row is covered: `/portfolio/attribution` is in the Decisions `alsoPaths`, and book attribution now renders inside `DashboardTearsheetView`, so the Performance hint is accurate.
  - `grep go-attribution|go-holdings` finds no stale references.
- **Single `<main>`.** The two removed `<main>`s were in pages rendered inside `ShellFrame`, which owns `<main id="main">` (`components/shell/app-shell.tsx:63`).
- **README.**
  - Book panes match `BOOK_PANES` (`positions`, `activity`), and Decisions panes match `DECISIONS_PANES` (`edge`, `theses`, `audit`).
  - Profile being Studio+ matches `STUDIO_CLASSES`.
  - The DecisionsView primitives (`DivergingBars`, `Sparkline`, `Stat`) and the verdict tones match `components/portfolio/DecisionsView.tsx:4,25`.
- **CHARTS.md inventory.**
  - `grep -rln "from ['\"]recharts" app components lib` lists exactly the 3 sanctioned files.
  - The only lightweight-charts importer is `lib/lw-chart.tsx`.
  - `DecisionEdgeChart.tsx` no longer exists.

## Findings

### MINOR-1 — `usePageHeader` still loops for any page that passes inline `crumbs` or `actions`

- Evidence: `components/shell/page-header.tsx:49-57`. The effect deps are `[setSpec, title, crumbs, asOf, actions, layout]`, and `usePageHeader` itself subscribes to `PageHeaderContext` (line 50).
- Why it loops: an inline array or JSX `crumbs`/`actions` gets a new identity on every render. The cycle is: effect, then `setSpecState`, then provider re-renders, then the consumer re-renders through context, then new identity, then effect again.
- Scope: `PageHeaderSpec` advertises `crumbs` and `actions`, and `PageHeader` renders them (lines 81, 101). The first page to use them will reintroduce the `/settings` / `/house` hang this range fixed. No current caller passes them, so this is latent rather than live.
- Verified: in a throwaway worktree at HEAD (fix applied), I added a probe test rendering `usePageHeader({ title: 'X', crumbs: [{ label: 'Home', href: '/' }] })` and `usePageHeader({ title: 'X', actions: <span>a</span> })` under a `Profiler`. Both hit 51 commits and threw `never settled`. Command: `npx vitest run components/shell/zz-probe.dom.test.tsx`, giving `crumbs renders 51 … actions renders 51`. The worktree has been removed.
- Suggested fix, any one of:
  - split the context into a stable setter context and a spec context, so the registering page does not subscribe to the spec;
  - key the effect on a stable digest of `crumbs`;
  - at minimum, document that `crumbs`/`actions` must be memoised, and add `crumbs` to the dom test so the hazard is pinned.

### NIT-1 — CHARTS.md classification line still says sparklines stay on recharts

- Evidence: `apps/dashboard/lib/CHARTS.md:25` reads "Everything else (bars keyed by ticker/bucket/leg, stacked composition, trivial sparklines) stays on recharts." This range edited `apps/dashboard/README.md:125-127` to say sparklines use kit primitives and "need neither engine".
- No recharts importer is a sparkline: `grep -rln "from ['\"]recharts"` returns only `sleeve-stacked-chart.tsx`, `AttributionTab.tsx` and `DecisionScorecardTab.tsx`.
- The two docs now disagree. Drop "trivial sparklines" from line 25.

### NIT-2 — CHARTS.md says the test checks "a row here", but the test checks its own array

- Evidence: `apps/dashboard/lib/CHARTS.md:67-68` says "`lib/lw-chart-canon.test.ts` fails if a component imports recharts without a row here".
- The new assertion (`lib/lw-chart-canon.test.ts`, "every recharts importer is on the sanctioned list") compares the importers to the hard-coded `RECHARTS_SANCTIONED` array (lines 42-46). It never reads CHARTS.md, so a doc row can drift without failing.
- The scan also covers only `components/` (`componentSources()` walks `join(root, 'components')`), not `app/`.
- Reword to "without being added to `RECHARTS_SANCTIONED` (mirror it here)", or parse the CHARTS.md table in the test.

### NIT-3 — The single-`<main>` contract does not assert the shell still renders one

- Evidence: `apps/dashboard/components/shell/single-main.contract.test.ts:20-31` checks that `app-shell.tsx` is in the scanned file list, and that no *other* file matches `/<main[\s>]/`.
- If `<main>` were dropped from `components/shell/app-shell.tsx:63`, both tests would still pass with zero landmarks.
- Add `expect(readFileSync(join(root, SHELL), 'utf8')).toMatch(/<main[\s>]/)`.

## Discarded (could not substantiate)

- **Tier leak through untagged anchors (`connections`, `plan`, `account`).** These anchors are section ids, and each section is already gated by `visibleSections`. No gated content is reachable through them.
- **New `tsc` errors.** The 23 failing files are pre-existing test files; none is in the range.
- **Kit `Button` in the settings rail and search hits changing semantics.** Both are still `type="button"`, and `aria-current` is unchanged. The canon guard is clean.

## Resolution (author, follow-up commit on the same branch)

| finding | status | change |
|---|---|---|
| minor — inline `crumbs` / `actions` still loop | fixed | `components/shell/page-header.tsx` splits spec and setter into two contexts, so a registering page never re-renders on a spec change. `page-header.dom.test.tsx` gains "settles when crumbs and actions are fresh objects on every page render", which fails against `6a033058` (`page header never settled`) and passes after. |
| nit — CHARTS.md still lists sparklines on recharts | fixed | Classification paragraph now says sparklines / score bars / small multiples are kit primitives. |
| nit — CHARTS.md overstates what the canon test reads | fixed | Text now says the test keeps `RECHARTS_SANCTIONED` in step with the table and scans `components/`. |
| nit — single-main test never asserts the shell keeps `<main>` | fixed | `single-main.contract.test.ts` gains "the app shell still owns the one `<main>`". |
