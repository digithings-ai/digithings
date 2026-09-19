# Shadcn wave 4 — finish the canonical sweep

**Epic:** #4206 · **Residual tracker:** #4306 · **Base:** `develop` (wave 3 merged as `a228df2d8`) · **Branch:** `feat/shadcn-wave-4`

## Goal

Wave 3 put the kit `packages/ui/src/ui/*` in charge and swept the planned file sets, but a whole-frontend re-scan (three read-only censuses, `census-wave4-{dashboard,shared,web}.md`) found the elements wave 3 did not own. Wave 4 finishes the job: every UI element on every frontend either renders a `@digithings/ui` part or is a documented, ruled exemption. The spec §5 accepted-scope reduction and issue #4306 are what this wave closes.

**The wave's done-ness bar:** a fresh scan of `cloudflare/**` finds no raw `<button>`/`<input>`/`<select>`/`<textarea>`/`<label>`/`<table>` used as UI outside a ruled exemption (tab-bar contract elements, the sidebar-settings trigger dress, `PipelineNode`'s geometry-pinned root, third-party swagger chrome, test fixtures), and no app-local component duplicates a kit/shared part.

## Censuses (inputs)

- `census-wave4-dashboard.md` — 118 raw native + 3 `role=` hand-rolls: 109 MIGRATE / 5 BLOCKED / 5 EXEMPT / 2 kit-render. 85 live `<button>`, 17 raw `<table>`, 6 hand-rolled segmented controls, 3 `<select>`, 4 `<input>` (one belongs on the shared `Slider`), 9 `<label>`, 6 `<details>` disclosures. (The reviewer's SEC2–6 prose was lost in delivery; the slice plan below is derived from its per-file inventory.)
- `census-wave4-shared.md` — ~105 MIGRATE. Structural: `web/src/chat/gallery-thread/ui/*` ships six radix/cva primitives duplicating the kit; four dead digichat `ui/` wrappers (`badge/input/label/sheet`, zero importers); `digichat-ui CopyButton` duplicates `web chat/ChatCodeBlock ChatCopyButton`; all 7 dashboard twelve-x panels still import controls `Sheet` although kit `Sheet` is 1:1 (T1b gap 9 was never honoured).
- `census-wave4-web.md` — `digithings-web` + `digiquant-web` genuinely clean (0 native, wave-3 claims hold class by class); 15 migrate sites in the reference (stale Checkbox/Switch specimens + native buttons/tabs); 3 BLOCKED (chatbot bundle isolation, no kit Slider, Table row-header part); `design/**` static HTML is archive, not app code.

## Global constraints

- Kit `packages/ui/src/ui/*` is the only primitive source; shared families (`EmptyState`, `SegmentedControl`, `IconButton`, `Pager`, `DatePager`, `Slider`, `Spinner`) come from the main barrel `@digithings/ui`.
- No new component-class families (the canon guard's family census fails the PR). No hardcoded colours — token-backed utilities only.
- The `cursor-pointer` policy is unchanged (kit `Button` deliberately has none). The `dress="chat"` and `skin` axes are sanctioned; the chat tone lives in `controls-core.css` `@layer components` on purpose.
- Never touch live-trading paths, `digikey/`, or anything under `projects/`.
- Every deletion follows a recorded zero-consumer grep (`rg` output pasted into the task report).
- Deferred work is never silent: it goes to #4306 or a new dated issue, with a ledger line.
- Each task commits on its own branch with the message given below; the lead cherry-picks. Tasks in the same batch must be file-disjoint.

## Tasks

### W4-P1 — kit capability prerequisite (blocks every Table/Select/Badge migration)
**Files:** `packages/ui/src/ui/table.tsx`, `select.tsx`, `badge.tsx`, `index.ts`, `ui.render.test.tsx`, plus token/bridge files only if a new token is genuinely needed (`styles/web-theme.css` + its contract test).
**Do:** close the T1b gap list so the canonical kit can serve the consumers still pinned to `components/controls/*`:
1. Table — numeric/right-aligned and density (compact) cell support, and a row-header cell (`<th scope="row">`) so `portfolio-reference.tsx:80` can migrate.
2. Select — composition parity with controls' `SelectPopup` / `SelectItemIndicator`, so `ProviderSettings.tsx:16`, `select-reference.tsx`, `site-nav.tsx`, `settings-panel.tsx` can move.
3. Badge — bridge the tone variants so `controls-layer-reference.tsx` and any app-local badge tones can retire.
**Consumes:** nothing. **Commit:** `feat(digiweb): wave 4 — kit capability parity for table, select, badge`
**Gates:** canon; `@digithings/ui` tests (+new render tests for each added capability, baseline 50/348); reference typecheck/lint + `next build --webpack` 18/18.

### W4-A1 — dashboard twelve-x A
**Files:** `apps/dashboard/components/twelve-x/{ConsensusDataTable,ConsensusTab,MatrixTab,MatrixCellHistoryPanel,BankVsQuantPanel,EventsTab,EventsTimeline}.tsx` (+ their tests).
**Do:** kit `Button`/`buttonVariants` for the chrome, kit `Table` for the table shells, shared `SegmentedControl` for the view/scale toggles. Keep the BLOCKED geometry (MatrixTab:144 cell, EventsTimeline:379 `tl-card`) and record why.
**Consumes:** W4-P1 (Table variants). **Commit:** `feat(dashboard): wave 4 — twelve-x A controls on kit (#4306)`

### W4-A2 — dashboard twelve-x B
**Files:** `apps/dashboard/components/twelve-x/{TradeIdeasPanel,TodayTab,IdeaCardsIndex,BriefsIndex,IdeaPanel,EventDetailPanel,BrokerProfilePanel,CurrencyDrilldownPanel,HowItWorksTab,TradesTab,DivergenceChip,TwelveXClient,BoardDateRangeFilter}.tsx` (+ tests).
**Do:** as A1, plus `TradesTab:319` range input → shared `Slider` (`TradesTab.test:119` pins `ctl-slider-input` — update deliberately), `TradesTab:457` `role=button` `<tr>` stays BLOCKED, `BoardDateRangeFilter:264` calendar cell stays BLOCKED, `TwelveXClient:91` stays EXEMPT (tab-bar contract).
**Consumes:** W4-P1. **Commit:** `feat(dashboard): wave 4 — twelve-x B controls on kit (#4306)`

### W4-B — dashboard pipeline
**Files:** `apps/dashboard/components/pipeline/{PipelineClient,PipelineCanvas,PipelineTraceLedger,PipelineArtifactLedger,PipelineRunHealth}.tsx` (+ tests).
**Do:** kit `Input`/`Label`/`Button`, `SegmentedControl` for the stage/type filters, kit `Table` where a real table exists, `<details>` → kit `Collapsible`. `PipelineNode:70` stays EXEMPT (camera geometry, test-pinned).
**Consumes:** W4-P1. **Commit:** `feat(dashboard): wave 4 — pipeline controls on kit (#4306)`

### W4-C — dashboard portfolio, tickers, why, observability, today, overview
**Files:** `apps/dashboard/components/{portfolio,tickers,why,observability,today,overview}/**` incl. `DecisionAudit`, `HoldingsActivityTable`, `AllocationsPositionsTable` (+ test edit for the pinned `table-fixed`/`<col>`), `deliberations-tab`, `DecisionScorecardTab`, `AttributionTab`, `DecisionEffectiveness`, `brief-pipeline-health`, `daily-brief-workspace`, `DashboardTearsheetView`, `DetailPanelHeaderActions`; `why/why-client.tsx:71` stays EXEMPT.
**Do:** the census's table/select/input/label/button inventory for this directory group, plus pager → shared `Pager`/`IconButton`, disclosures → kit `Collapsible`, deprecated conviction shims re-pointed to `@digithings/ui` and the `EmptyState` shim removed.
**Consumes:** W4-P1. **Commit:** `feat(dashboard): wave 4 — portfolio/observability surfaces on kit (#4306)`

### W4-D — dashboard app shells, settings, library
**Files:** `apps/dashboard/app/{page,error}.tsx`, `app/portfolio/ledger/page.tsx`, `components/settings/**`, `components/library/{DigestDocumentView,GenericDiffDocumentView}.tsx`; `app/settings/page.tsx:117` + `sidebar-settings.tsx:38` stay EXEMPT (verify only).
**Do:** remaining kit swaps in this group; re-verify the settings surfaces against the kit `Select`/`Switch`/`Checkbox` semantics wave 3 established.
**Consumes:** W4-P1. **Commit:** `feat(dashboard): wave 4 — app shells and settings on kit (#4306)`

### W4-E — package internals (the second component library)
**Files:** `packages/ui/src/chat/gallery-thread/ui/*` (+ the 7 consumers `thread.aui.tsx`, `tool-fallback.aui.tsx`, `reasoning.tsx`, `tool-group.tsx`, `attachment.tsx`, `tooltip-icon-button.tsx`, `message-timing.tsx`, and `gallery-thread.source.test.ts`), `apps/digichat/src/components/ui/{badge,input,label,sheet}.tsx`, `packages/digichat-ui/src/CopyButton.tsx` (or wherever it lives) → dedupe with the shared `ChatCopyButton`.
**Do:** replace the six radix/cva primitives with the kit equivalents (call sites will need small rewrites — radix→base-ui differences are expected; keep the gallery's visual parity and its source test's intent). Delete the four dead digichat `ui/` wrappers (zero importers — prove with grep). Re-point `CopyButton` to the shared implementation or delete it.
**Consumes:** W4-P1 for any Table/Select touch (unlikely). **Commit:** `refactor(digiweb): wave 4 — gallery-thread primitives on kit, dead wrappers removed`

### W4-F — digichat shell + stock chrome
**Files:** `apps/digichat/src/**` chat shell, `byok-cli-flow.tsx`, `stock/{stock-chrome-bar,tool-catalog-bar,embed-composer-menu,message-error.aui,quant-comparison-strip}.tsx` (+ tests).
**Do:** kit `Button`/`Input`/`Label`/`Select`/`Switch`/`Table` per the census clusters, keeping the `dc-*` chrome dress and the `dress="chat"` wrappers. Respect the vendored `app/(baseline)/stock/ui/*` and `assistant-ui/skins/*` do-not-restyle trees (BLOCKED).
**Commit:** `feat(digichat): wave 4 — shell and stock chrome on kit (#4306)`
**Gates:** digichat suite A=B (baseline 126/1244).

### W4-G — digichat-ui
**Files:** `packages/digichat-ui/**` (CopyButton if not done in E, `DocumentPane.tsx`, any raw controls).
**Commit:** `feat(digichat-ui): wave 4 — controls on kit (#4306)`

### W4-H — web app-local surfaces
**Files:** `packages/ui/src/{components/account/AuthCard.tsx,components/ThemeProvider.tsx,components/NavShell.tsx}`, `components/effects-chrome/{ToastStack,AnnouncementBar,Pipeline,RotatingPrompts,TabStrip}.tsx`, `components/docs/CodeTabs.tsx` (+ tests).
**Do:** kit `Button`/`Input`/`Label`/`Tabs` swaps; keep `acct-auth-*` dress and the nav-shell behaviour.
**Commit:** `feat(digiweb): wave 4 — account, chrome, effects on kit (#4306)`

### W4-I — reference specimens + design
**Files:** `apps/reference/components/controls/{form-fields-reference,skeleton-reference}.tsx`, `account/{signup-card,settings-panel}.tsx`, `app/(gallery)/ui/page.tsx`, `code-sample-reference.tsx`, `changelog-rail-reference.tsx`, `terminal-manifest-reference.tsx`, `tearsheet-charts-reference.tsx`, `command-palette-reference.tsx`, `footer-reference.tsx`, `feature-picker-reference.tsx`, `select-reference.tsx`, `site-nav.tsx`, `table-reference.tsx`, `portfolio-reference.tsx`, `portfolio-workspace-reference.tsx`, `dashboard-workspace-reference.tsx`, `iterate/*`, `design/smoke/index.html`.
**Do:** migrate the stale specimens (kit now covers Checkbox/Switch, Table, Select, Tabs, Button, IconButton); keep the specimens that exist to demo a ruled gap only if the gap still exists after W4-P1 — otherwise migrate them too and update the gap list in `ARCHITECTURE.md`/the specs. Keep the SANCTIONED art (`theme-gallery`, `livery-switcher`, `iterate` prototypes) and the BLOCKED ones (chatbot bundle isolation, no kit Slider, `portfolio-reference` row-header until P1 lands).
**Commit:** `feat(digiweb): wave 4 — reference specimens on kit (#4306)`
**Gates:** reference typecheck/lint + build; the reference IS the design canon, so screenshots for every migrated specimen.

### W4-J — cleanup: re-point the pins, then delete the losers
**Files:** the 7 `apps/dashboard/components/twelve-x/*.tsx` imports of controls `Sheet` → kit `Sheet`; `apps/digichat/src/components/ui/collapsible.tsx` → kit `Collapsible`; then `packages/ui/src/components/controls/*` deletions per consumer audit; `index.ts` barrel updates; `ARCHITECTURE.md`/`MIGRATION.md`/spec §5 + `MANIFEST.json` string.
**Do:** only after the consumers move, re-run the per-file zero-consumer audit and delete what is truly unpinned (expected: `Badge`, `Sheet`, `Collapsible`, `Label`, `Avatar`, `Slider`, and `Table`/`Select` if P1 + the consumers landed). Keep `Button`/`Dialog`/`DropdownMenu`/`Tooltip` if their consumers remain, and say so.
**Consumes:** everything. **Commit:** `chore(digiweb): wave 4 — retire the controls layer`
**Gates:** all app suites + builds + canon; `make test-unit` safe subset if the environment allows.

## Risks / residuals carried in

- **Kit gaps are the root of most pins.** If W4-P1 cannot reach parity for a part (e.g. a Table density mode that no token supports), the wave must record the gap and keep the controls pin rather than force a bad migration — with the reason in the ledger.
- **`gallery-thread/ui/*` is a live chat surface** (reached via `./chat/thread` → `DigichatThread.tsx:19`), so W4-E needs visual parity checks, not just green tests.
- **Test-pinned behaviour** (`TradesTab.test` slider class, `AllocationsPositionsTable.test` `table-fixed`/`<col>`, `EventsTimeline.test` geometry) must be updated deliberately and the change explained — never weakened to pass.
- **Environment:** the shared install is stale; every worker uses the per-app `@digithings` overlay recipe (never `cp -al` for tests — duplicate React breaks hook resolution and prerender), and `rm -rf .next` before webpack builds.
- **`make test-unit`** may be unrunnable here (missing Python deps) — no Python file is touched, so it is not a gate for this wave, but say so in the report.
