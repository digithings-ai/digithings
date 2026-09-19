# shadcn migration — Wave 2 (app adoption) implementation plan

Spec: `docs/superpowers/specs/2026-09-16-shadcn-migration-design.md` (§5 wave 2). Epic: #4206.
Base: `5821764fe` (`origin/develop`, post wave-0 + wave-1). Branch: `feat/shadcn-wave-2`.
Recon evidence: `…/.superpowers/sdd/2026-09-16-shadcn-wave-2/` (census, counts, CI/alias facts).

**Goal:** the three product apps adopt the vendored kit — `digithings-web`, `digiquant-web`,
`dashboard` — each as its **own PR one-hop into `develop`**. `digichat` / `digichat-ui` stay out
of scope (regression net). Biggest tables go to kit `Table`; the dashboard chart stack gets its
§9-Q4 audit. The reference app (wave 1) is the already-swept counterpart and gets no changes
except the kit package itself (Task 1).

**Files touched overall:**
- `packages/ui/src/ui/**` (pre-work), `packages/ui/src/styles/web-theme.css`
- `apps/digithings-web/**`, `apps/digiquant-web/**`, `apps/dashboard/**`
- `packages/ui/{ARCHITECTURE,MIGRATION}.md` (close-out, only if contracts change)
- `.github/workflows/test-web.yml` + `scripts/ci_paths.yaml` (CI hardening decision, close-out)

---

### Task 1: Kit pre-work (package PR)

**Files:**
- Modify: 13 vendored files `packages/ui/src/ui/{alert,badge,button,card,collapsible,dialog,dropdown-menu,input,label,separator,sheet,tabs,textarea,tooltip}.tsx` — `import { cn } from "@/lib/utils"` → `"../lib/utils"` (package-relative; `web/src/lib/utils.ts` is the sibling target — one level up from `src/ui/`).
- Modify: `packages/ui/src/styles/web-theme.css` — inside the existing single `@theme inline`: `--animate-collapsible-down/up` + nested `@keyframes collapsible-down/up`; top-level `@custom-variant data-open` / `data-closed` (same rules the reference carries at `globals.css:396–413`).
- Modify: `packages/ui/src/styles/web-theme.test.ts` — contract rows for the new keyframes/variant declarations.
- Possibly Modify: `apps/reference/app/globals.css` — drop the now-promoted duplicate variant/keyframes block (only if byte-identical semantics; otherwise make the reference consume the package's and remove the local one).

**Interfaces:**
- Consumes: wave-1 kit as shipped.
- Produces: a consumer-portable kit — no `@/lib/utils` requirement (any app can import `@digithings/ui/ui` with only `@source` + `tw-animate-css`), and overlay animations/keyframes available to every consumer; `--hair-strong` defined.

- [ ] **Step 1:** Rewire the 13 `cn` imports to `../lib/utils`; grep-verify zero `from "@/lib` remain in `web/src/ui/`; the reference app must still build (its own `lib/utils.ts` becomes unused by the kit).
- [ ] **Step 2:** Promote the overlay variant + keyframes from the reference into `web-theme.css`; contract-test rows; reference local block removed only if semantically identical.
- [ ] **Step 3:** Decide `--hair-strong`: define `--hair-strong: var(--hair-2)` in the bridge if `--hair-2` resolves in all consumers; else map to `var(--hair)`; contract row. (Controls `Table`/`Breadcrumbs`/`Pagination` currently get an invalid border.)
- [ ] **Step 4:** Gates: `npm --workspace @digithings/ui run test` + `typecheck`; canon guard; **`npm --workspace digichat run test`** (web-theme.css is shared — 125 files); reference lint/typecheck/build.
- [ ] **Step 5:** Commit.

**Commit:** `fix(digiweb): wave 2 pre-work — portable cn imports, shared overlay variants, --hair-strong`

---

### Task 2: digithings-web adoption

**Files:**
- Modify: `apps/digithings-web/components/ProviderSettings.tsx` — hand-built slide-over → kit `Sheet`; native input/select → `Input`/`Select`; labels → `Label`; 6 native buttons → `Button`; `role="alert"` → `Alert`.
- Modify: `apps/digithings-web/components/docs/DigithingsDocs.tsx` — `.docs-copy` → `Button`; `.doc-badge` → `Badge`; the 2 doc tables (`:221`, `:250`) → kit `Table`.
- Modify: `apps/digithings-web/landing/ModuleManifest.tsx` (button), `.btn*` call sites in `app/{page,about,team,services,quality,not-found}`.
- Modify: `apps/digithings-web/app/globals.css` — delete `dc-settings-*` dress; add `@source "../../digiweb/web/src/ui";` + `@import "tw-animate-css"`.
- Modify: `apps/digithings-web/package.json` (+ lockfile) — add `tw-animate-css`.
- Modify: `apps/digithings-web/components/ProviderSettings.contract.test.tsx` — re-pin markup expectations.

**Interfaces:**
- Consumes: Tasks 1; wave-1 variant map (primary→default, ghost→ghost, quiet→outline where stock cannot express inline-text quiet, danger→destructive); loading idiom (`disabled` + inline spinner span).
- Produces: the marketing/docs app on the kit; `.dc-settings-*` deleted.

- [ ] **Step 1:** `ProviderSettings` on `Sheet`/`Input`/`Select`/`Label`/`Button`/`Alert` (preserve focus/escape/backdrop behavior); update the contract test.
- [ ] **Step 2:** docs + marketing `.btn*`/badges/tables per the map; keep utilities-only, no new families.
- [ ] **Step 3:** CSS: delete `dc-settings-*` (verify zero consumers), add `@source` + `tw-animate-css`; `package.json` + lockfile.
- [ ] **Step 4:** Screenshots dark+light (home, `/docs`, provider settings surface) + gates: canon, `test --workspace digithings-web`, `@digithings/ui`, `@digithings/digichat-ui`, digichat suite A/B; build (`next build --webpack`).
- [ ] **Step 5:** Commit.

**Commit:** `feat(digithings-web): adopt the vendored ui kit`

---

### Task 3: digiquant-web adoption

**Files:**
- Modify: `.btn*` sites — `components/landing/CloneRepoButton.tsx`, `components/tearsheet/tearsheet-view.tsx:528`, `SiteNav.tsx`, `app/{page,not-found,contact}/page.tsx`, `subsystems/[id]/page.tsx`.
- Modify: chips → `Badge` — `tearsheet/{strategy-type-chip,signal-delay,honesty}.tsx`, `tearsheet-view.tsx:517–522`, `landing/StrategySuite.tsx` (tone via call-site utilities; keep honesty `title` semantics).
- Modify: card surfaces → kit `Card` where the dress is superseded — `dqss-card` (StrategySuite), `dqpipe-card` (ResearchPipeline), `.sub-poster` (subsystems); keep deck mechanics.
- Modify: tables → kit `Table` — `tearsheet/pivot-stats-table.tsx:170` (18 rows), `landing/DashboardPortfolioPanel.tsx:142` (6 cols, live-flash cells preserved via cell utilities).
- Modify: tabs decision — `ts-tab*` (tearsheet-view 18 refs, pivot-stats 3, StrategySuite 2): kit `Tabs` or keep shared `SegToggle`; record the decision in the report.
- Modify: `app/globals.css` deletions + `@source` + `tw-animate-css`; `package.json` (+lockfile).
- Modify/Add: vitest coverage for swapped components (they run locally; CI wiring is Task 6's decision).

**Interfaces:**
- Consumes: Tasks 1; wave-1 map; #1807 note (digiquant-web tests are dark in CI — record).
- Produces: the quant marketing/tearsheet app on the kit; `dqpipe-card`/`sub-poster` dress deleted where superseded.

- [ ] **Step 1:** buttons + chips + cards.
- [ ] **Step 2:** the two tables on kit `Table` (numeric columns numeric).
- [ ] **Step 3:** tabs decision + implementation; CSS deletions + `@source` + `tw-animate-css`; package.json.
- [ ] **Step 4:** Screenshots dark+light (home, tearsheet, subsystems) + gates: canon, `lint --workspace digiquant-web`, its vitest, `@digithings/ui`, digichat A/B; build.
- [ ] **Step 5:** Commit.

**Commit:** `feat(digiquant-web): adopt the vendored ui kit`

---

### Task 4: dashboard adoption — primitives + chrome

**Files:**
- Modify: `components/settings/{profile,pipeline,notify,keys,brokers,billing}-tab.tsx` + `settings-content.tsx` — 23 inputs → `Input`, 23 labels → `Label`, 8 selects → `Select`, settings buttons → `Button`, `role="alert"`/`Banner` surfaces → `Alert`.
- Modify: `components/login-screen.tsx`, `sidebar.tsx`, `sidebar-settings.tsx` — drawer/dialog → kit `Sheet`/`Dialog`; `acct-*` auth dress deletions in `app/account-surfaces.css` where superseded.
- Modify: `twelve-x/{BoardDateRangeFilter,BrokerProfilePanel,EventDetailPanel}.tsx` — hand-built `role="dialog"` → kit `Dialog`/`Sheet`.
- Modify: `components/ui.tsx` — `StatCard` → kit `Card`; Badge shim kept or re-pinned (record decision + `components/ui.test.tsx`).
- Modify: `.oly-slab` call sites (44 uses / 21 files) → kit `Card` where the dress is superseded; `app/globals.css` `oly` deletions + `@source` + `tw-animate-css`; `package.json` (+lockfile).
- Modify: chips — `DeltaChip`, `DivergenceChip`, `VehicleExpressionRow`, `TradeIdeasPanel`, `ConsensusDataTable` → kit `Badge` (call-site utilities; keep the F5 filled-accent ruling on `DeltaChip`).

**Interfaces:**
- Consumes: Tasks 1; controls-layer `Sheet`/`Tooltip`/`DropdownMenu`/`TabStrip` already in use (do not regress them).
- Produces: dashboard chrome + forms on the kit; `oly` dress pruned.

- [ ] **Step 1:** settings tabs (forms on kit; re-pin touched tests).
- [ ] **Step 2:** auth/sidebar/panels (Dialog/Sheet swaps; preserve the mobile drawer behavior).
- [ ] **Step 3:** surfaces (`oly-slab` → `Card`; `StatCard`; chips → `Badge`).
- [ ] **Step 4:** CSS deletions + `@source` + `tw-animate-css`; screenshots dark+light (overview, settings, portfolio); gates: canon, `test-dashboard.yml` lane equivalent (lint + build + 215 tests).
- [ ] **Step 5:** Commit.

**Commit:** `feat(dashboard): wave 2 — primitives and chrome on the vendored kit`

---

### Task 5: dashboard adoption — data tables + chart audit

**Files:**
- Modify: biggest tables → kit `Table` — `portfolio/AllocationsPositionsTable.tsx`, `portfolio/HoldingsActivityTable.tsx`, `library/RebalanceDocumentView.tsx`, `observability/DecisionScorecardTab.tsx`, `library/GenericDiffDocumentView.tsx`, `twelve-x/TradesTab.tsx`, `twelve-x/ConsensusDataTable.tsx` (the last two are the future Data-Table-block candidates; keep their filter/sort/page behavior).
- Modify: `lib/lw-chart.tsx` + `portfolio/DecisionEdgeChart.tsx` — §9-Q4 audit outcome; `lib/chart-colors.ts` stays the only color home.

**Interfaces:**
- Consumes: Task 4's PR or chains onto it (same PR preferred to avoid lockfile churn); spec §9 Q4.
- Produces: all major tables on kit `Table`; a recorded chart-stack decision (consolidate on Recharts / keep lightweight-charts finance-only).

- [ ] **Step 1:** tables on kit `Table` with numeric treatment; sticky headers preserved via call-site utilities.
- [ ] **Step 2:** chart audit: reproduce the dashboard finance charts on Recharts; if they pass, retire `lightweight-charts`; else record failures and keep it finance-only.
- [ ] **Step 3:** Screenshots + gates as Task 4; commit.

**Commit:** `feat(dashboard): wave 2 — data tables and chart audit`

---

### Task 6: Cross-app close-out

**Files:**
- Modify: `.github/workflows/test-web.yml` + `scripts/ci_paths.yaml` — add the previously-dark `test --workspace digiquant-web` step (decision recorded either way).
- Modify: `packages/ui/{ARCHITECTURE,MIGRATION}.md` — only if adoption changed the written contract (e.g. adoption notes/consumer requirements).
- SDD dir: wave screenshot set + ledger.

**Interfaces:**
- Consumes: Tasks 1–5 all merged or merge-ready.
- Produces: the recorded wave-2 state.

- [ ] **Step 1:** Full-wave grep audit: no deleted family prefix used; no `@/lib/utils` left in the kit; `@source` present in all three apps; no new families (`check_frontend_canon.py` clean); digichat/digichat-ui untouched (paths diffed).
- [ ] **Step 2:** Full gates on each tip: canon; `@digithings/ui`; `@digithings/digichat-ui`; each app's lint/test/build; `npm --workspace digichat run test` A/B.
- [ ] **Step 3:** Screenshot set (dark+light) for each app's key surfaces; ledger complete; docs touch-ups.
- [ ] **Step 4:** Commit (only if files change).

**Commit:** `docs(digiweb): wave 2 — adoption record` (only if any docs/CI files change)

---

### Task 7: Ship — per-app PRs

**Files:** none (git/GitHub only).

**Interfaces:**
- Consumes: the wave-2 branch history; epic #4206.
- Produces: the kit pre-work + three app PRs merged into `develop`.

- [ ] **Step 1:** Push the branch(es). PR order: **T1 kit pre-work first** (§it is the dependency), then `digithings-web`, then `digiquant-web`, then `dashboard` — serialized through `develop` because all carry lockfile/`package.json` changes; each PR references #4206 and summarizes its own adoption.
- [ ] **Step 2:** For each PR: aggregate fresh-context read-only review over its own commit range; post the verdict with the `<!-- in-session-review -->` marker; apply `reviewed:agent`; fix findings on-branch.
- [ ] **Step 3:** Merge each when green (`--merge`, never `--admin`/`--auto`); expect the wave-0/1 up-to-date chase and plan-file add/add conflicts (resolve locally keeping the wave-amended plan).
- [ ] **Step 4:** Ledger record per merge; report wave 2 shipped.

---

## Self-review checklist (end of wave)

- [ ] Every commit maps to a ledger range; no foreign commits; PR boundaries match the task split.
- [ ] Kit files stay stock apart from the pre-work import rewire; no restyles.
- [ ] No new app-local class family; `frontend_class_families.json` untouched; deletions shipped with their swaps.
- [ ] `@source "../../digiweb/web/src/ui"` present in all three apps; `tw-animate-css` imported.
- [ ] digichat + digichat-ui + pinned shims untouched; digichat suite state recorded A/B per PR.
- [ ] Screenshots exist per touched app surface (dark + light).
- [ ] Deviations and CI decisions recorded in the ledger; `--hair-strong` resolved; accent-alias sweep status recorded.
