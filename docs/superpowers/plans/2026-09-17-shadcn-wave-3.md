# shadcn migration — Wave 3 (component-level coverage) implementation plan

Spec: `docs/superpowers/specs/2026-09-16-shadcn-migration-design.md` (§5 wave 3+).
Epic: #4206. Predecessors: wave 0 (#4230), wave 1 (#4254), wave 2
(`feat/shadcn-wave-2`, tip `d052a09a7` — local-only at plan time).

- **Date:** 2026-09-17
- **Base:** `d052a09a7` (`feat/shadcn-wave-2` tip). **Dependency:** wave 2
  must land (PR → `develop`) before wave-3 work branches; rebase this branch
  onto `develop` at that point. Until then, plan + census only — no app code.
- **Branch:** `feat/shadcn-wave-3` (worktree `…/opencode/wt-shadcn-w3`
  once execution starts; plan drafted in `wt-shadcn-w2`).

## Goal

100% component coverage: every component rendered by the three product apps
(`digithings-web`, `digiquant-web`, `dashboard`) comes from `@digithings/ui`
and speaks the kit (`web/src/ui`) language. No app-local shadows of shared
families, no legacy dress-axis families with live consumers, no native
buttons/inputs/selects left in app code.

## Owner decisions (2026-09-17, recorded)

1. **Centered Dialog is the standard overlay idiom for modal settings
   surfaces.** `sidebar-settings.tsx` keeps its wave-2 centered
   `<Dialog><DialogContent>` (stock shadcn idiom) — no revert to popover.
   Right-side Sheets stay for BriefPanel-grammar contextual panels
   (Broker/Event panels, mobile drawer rationale). New modal settings
   surfaces default to centered Dialog; new contextual panels default to
   Sheet `side=right`.
2. **Wave 3 drafted** (this plan) following the wave-2 census findings below.

## Census evidence (verified 2026-09-17 on `d052a09a7`)

| App | tsx files | import `@digithings/ui` | use kit `ui` | legacy still rendered |
|---|---|---|---|---|
| digithings-web | ~18+ (components+app) | 26 files | 10 (Button, Sheet, Badge, Alert, Input, Label) | `DtNav.tsx` (every-page nav): `btn btn-primary` + `btn-icon`; `.btn` defined in `@digithings/design` `site.css:76`, not the kit |
| digiquant-web | ~33+ | 39 files | 14 (Button, Badge, Card only) | `dqss-*` (53 uses), `dq-*`, `dqpipe-*`, `ts-tab*` — containers kept intentionally in wave 2, never re-audited |
| dashboard | **281** | 77 files | 35 (Button, Card, Alert, Input, Label, Badge only — no Dialog/Sheet/Select/Table/Tabs from kit) | `acct-*` (login/gate), `oly-slab` (7), `ctl-dialog-card` (5); login, product-gate, observability, pipeline, callback, db-unavailable untouched; ledger residuals: 10 inputs / 10 labels / 3 selects / **117 buttons** outside scope |

Shared package (`packages/ui/src`, 260 files): **200 legacy
dress-axis components** (chat 62, controls 27, finance-tearsheet 18,
repo-activity 12, …) vs **15 kit parts** in `ui/`. Only
`chat/gallery-thread/*` consumes the kit; every other family the sites
render does not. The reference app (27 kit-consuming files) is the sole
fully-swept consumer.

**Sequencing consequence:** app→shared migration alone moves legacy around.
Shared→kit must lead, gated per family by a live-consumer census. Tasks are
ordered accordingly.

## Non-goals (spec §1, restated)

- Chat surfaces stay Assistant UI (`.aui-*`). `digichat` / `digichat-ui`
  remain regression net only (`npm --workspace digichat run test` stays
  green; 125/1229 baseline).
- Finance charts stay `lightweight-charts`; `--up/--down/--rv-*` money and
  diff domains stay fixed literals.
- Terminal family look is canon; reproduce, don't replace.
- Third-party CSS (e.g. `.docs-swagger .swagger-ui .btn`) is out of scope.
- No new app-local CSS class families (canon guard) and no new app-local
  primitives — every replacement imports from `@digithings/ui` or
  `@digithings/ui/ui`.

## Evidence protocol (every task)

- Dev servers from the wave-3 worktree: digithings-web `:3011`,
  digiquant-web `:3012`, dashboard `:3013` (`/dashboard/` basePath),
  reference `:4013`. Webpack mode (`--webpack`) — Turbopack is inoperable on
  the symlinked install; production builds use a real-install copy
  (wave-2 precedent).
- Screenshots into the SDD dir for every surface a task touches (dark +
  light): `…/digichat-build-2.0/.superpowers/sdd/2026-09-17-shadcn-wave-3/`
  (briefs, reports, diffs, screenshots). Ledger `progress.md` there.
- Gates per task: `python3 scripts/check_frontend_canon.py`;
  `npm --workspace @digithings/ui run test`; app `lint` + `typecheck` +
  workspace tests; `next build` (webpack or real-install copy);
  `npm --workspace digichat run test` (web-theme.css is shared);
  zero-consumer grep audit for every deleted class/family.
- Each task gets a brief + report + a fresh-context review like waves 0–2.
- Commits: one per task, single commit, no push (repo precedent). PRs
  one-hop into `develop` after wave 2 lands and this branch rebases.

## Env pre-flight (once, before task 1)

Mirror the wave-2 worktree setup: root `node_modules` symlinked to the
shared `digichat-build-2.0` install, per-app `@digithings/*` overlays
resolving the wave-3 kit (wave-2 task-2 precedent — the root symlink
resolves the shared worktree's stale kit). Lockfile changes via
`npm install --package-lock-only` + libc graft (repo precedent).

---

### Task 1: Canonical layer + missing kit parts

**Why first:** dashboard uses legacy `controls` Dialog/Sheet/Select/Table
because the kit has no Table or Select and its dialog/sheet were passed
over. Nothing else can standardize until the canonical layer is decided.

**Files:**
- Census (read-only first): every consumer of `web/src/controls/*`,
  `web/src/ui/{dialog,sheet,tabs,tooltip,dropdown-menu,textarea,collapsible}.tsx`
  across `reference/`, the three apps, `digichat*`. Output: consumer table
  in the task brief — migration targets are census-gated, no drive-bys.
- Create (CLI inside `web/`): `web/src/ui/{table,select}.tsx` (+ `switch`,
  `checkbox` if the census shows consumers; slider/popover/scroll-area stay
  deferred per wave-1 scope notes unless a live consumer exists).
- Modify: `web/src/ui/index.ts`, `web/src/ui/ui.render.test.tsx`.
- Decide (record in report): kit `dialog`/`sheet` vs `controls` Dialog/Sheet
  as canonical. Candidates: promote kit versions (stock shadcn, centered
  Dialog per owner decision) and re-point `controls` consumers; or bless
  `controls` overlays and delete kit duplicates. Either way exactly one
  survives per part.
- Modify: losing side's consumers re-pointed; loser's files deleted after
  zero-consumer audit.

**Interfaces:**
- Consumes: wave-2 kit + census table.
- Produces: a complete canonical layer — every overlay/form/data part the
  sites need exists in exactly one place.

- [ ] **Step 1:** Consumer census of `controls/*` + overlapping kit parts;
  brief table (file → part → live surface).
- [ ] **Step 2:** Vendor missing kit parts (Table, Select minimum) via CLI;
  barrel + render tests.
- [ ] **Step 3:** Canonical-layer decision (kit vs controls per part);
  migrate the losing side's live consumers; delete losers after
  zero-consumer audit.
- [ ] **Step 4:** Gates: canon, web tests, reference lint/typecheck/build,
  digichat suite A=B, consumer app builds.
- [ ] **Step 5:** Commit.

**Commit:** `feat(digiweb): wave 3 — canonical kit layer, Table+Select, controls retirement`

---

### Task 2: Shared chrome/nav → kit

**Why second:** `DtNav` renders on every digithings.ai page and still uses
legacy `.btn` dress; the shared `NavShell`/`nav-shell.css` backs it.

**Files:**
- Modify: `packages/ui/src/components/NavShell.tsx`,
  `web/src/styles/nav-shell.css` (`.nav-shell-sheet-cta .btn`),
  `packages/design/site/site.css` (`.btn` family → thin alias
  over `buttonVariants`, or deleted after zero-consumer audit).
- Modify: `apps/digithings-web/components/DtNav.tsx`
  (`btn btn-primary` → `buttonVariants`, `btn-icon` → kit `Button`).
- Modify: `dq-nav-h` consumers in digithings-web (21 uses — audit: shared
  header family or app-local; migrate or promote).
- Modify: `web/src/components/docs/*` + `.doc-fields` (kept in wave 2 for
  `Endpoint.tsx:70` — re-audit; kit `Table` if now covered by Task 1).

**Interfaces:**
- Consumes: Task 1 canonical layer.
- Produces: every-page chrome on the kit; `.btn` either an alias or gone.

- [ ] **Step 1:** `dq-nav-h` + `.btn*` consumer audit (both apps).
- [ ] **Step 2:** NavShell/nav-shell.css/site.css → kit; DtNav → kit.
- [ ] **Step 3:** docs family re-audit (`.doc-fields`, Endpoint consumer).
- [ ] **Step 4:** Screenshots (home + docs, dark + light) + gates.
- [ ] **Step 5:** Commit.

**Commit:** `feat(digiweb): wave 3 — shared chrome/nav on the kit`

---

### Task 3: digiquant-web containers

**Files:**
- Census: `dqss-*` (53), `dq-*`, `dqpipe-*`, `ts-tab*` — classify each as
  pure container (keep, document the keep-list in the report) vs control
  (migrate to Task-1 kit parts).
- Modify: any control-classified stragglers; verify wave-2's "no native
  buttons left" claim still holds at task base.
- Modify: `dqss-kpi-skeleton`, `sub-poster` box dress (wave-2 kept for
  container context/bloom — re-confirm or migrate).

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: digiquant-web fully classified; controls on kit, containers on
  an explicit keep-list.

- [ ] **Step 1:** Family census + keep/migrate classification.
- [ ] **Step 2:** Migrate control-classified; document keep-list.
- [ ] **Step 3:** Screenshots (home, tearsheet, subsystem, dark + light).
- [ ] **Step 4:** Gates: canon, digiquant-web tests, web tests, build
  (17 routes), lockfile platform test.
- [ ] **Step 5:** Commit.

**Commit:** `feat(digiquant-web): wave 3 — container census, controls on kit`

---

### Task 4: digithings-web residuals

**Files:**
- Modify: `apps/digithings-web/components/ProviderSettings.contract.test.tsx`
  only if Task 1 changed Sheet/Select/Alert semantics it pins.
- Verify: zero `.dc-settings-*`, `.docs-copy`, `.doc-badge` in render paths
  (wave-2 leftovers are comments + `DtNav` — DtNav covered by Task 2).
- Screenshots: home, `/docs`, provider settings surface, dark + light.

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: digithings-web done — no legacy dress in render paths.

- [ ] **Step 1:** Residual grep audit (render paths vs comments/tests).
- [ ] **Step 2:** Contract-test re-pin only if Task-1 semantics changed.
- [ ] **Step 3:** Screenshots + gates (digithings-web tests, build
  24 routes, prod-export smoke).
- [ ] **Step 4:** Commit.

**Commit:** `feat(digithings-web): wave 3 — residual audit, kit-complete`

---

### Task 5: dashboard sweep (three slices, one commit per slice)

**5a — chrome, gates, login.**
**Files:** `components/app-frame.tsx`, `components/command-palette.tsx`
(shadow — re-point to shared `command-palette/` or promote the better one,
delete the loser), `components/digichat-popup.tsx`,
`components/login-screen.tsx`, `components/client-product-gate.tsx`
(`acct-*` kept per wave-2 — re-audit against Task-1 kit coverage),
`components/db-unavailable.tsx`, `app/auth/callback/page.tsx`.
**Commit:** `feat(dashboard): wave 3 — chrome/gates/login on kit`

**5b — settings residuals.**
**Files:** the ledger's known residuals — 10 inputs / 10 labels / 3 selects /
117 buttons outside wave-2 scope; `components/settings/remaining-hop-status.tsx`;
`components/observability/shared.tsx`. Verify `sidebar-settings.tsx` keeps
the owner-blessed centered Dialog; convert any other centered-vs-sheet
inconsistencies to the Task-1 canonical parts.
**Commit:** `feat(dashboard): wave 3 — settings residuals on kit`

**5c — library + pipeline.**
**Files:** `components/library/*` (14 document views — audit against shared
`docs/` family first; promote-or-repoint, no parallel implementations),
`components/pipeline/PipelineNode.tsx`, `components/house/*` chrome.
**Commit:** `feat(dashboard): wave 3 — library/pipeline on shared families`

Each slice: census → migrate → screenshots (dark + light) → gates
(dashboard tests, canon, lint, build + `check:static-export`, lockfile
platform test) → fresh-context review → commit.

---

### Task 6: Deletions + close-out

- Zero-consumer audits for every retired family/class: `controls/*`
  losers, `.btn` (if aliased in Task 2), `.doc-fields`, `.dqss-*` migrated
  members, `.oly-*`, `.acct-*` migrated members, `.ts-chip`
  (already zero-consumer repo-wide — delete), app-local shadows deleted in
  Tasks 2–5 (verify).
- Update `packages/ui/{ARCHITECTURE,MIGRATION}.md` (promotion
  playbook: reference → `@digithings/ui` → adopted — now with the kit as
  the only primitive source) and the migration spec's wave-3 section.
- CI: `.github/workflows/test-web.yml` + `scripts/ci_paths.yaml` hardening
  if the wave adds packages/paths (wave-2 plan left this as close-out).
- Final gates: full `make test-unit` safe subset, canon clean, all three
  app builds + reference build green, digichat suite green.

**Commit:** `chore(digiweb): wave 3 — retire legacy dress, close out`

---

## Risks / residuals carried in

- **Wave-2 landing first.** This branch sits on local-only `d052a09a7`;
  rebase onto `develop` after wave 2 merges. If wave-2 review demands
  changes, re-census affected tasks.
- Kit `Button` lacks `cursor: pointer` (Tailwind v4 preflight, kit-wide
  policy — wave-2 finding, replicate deliberately, don't "fix" per-app).
  **Superseded by phase 0.3 (`2b2a1c56c`+, #4306):** pointer cursors are now
  kit-level — the kit's interactive parts set `cursor-pointer` and the canon
  guard refuses app-local `cursor-*`. This bullet records wave-3's decision,
  not the current rule (see `packages/ui/MIGRATION.md`).
- Print-media residual (layered `[hidden]` vs unlayered package pins —
  package backlog, not this wave).
- Dev-mode hydration warning (non-reproducible, cold A/B + prod clean).
- Lockfile `libc` graft precedent for `tw-animate-css`-style additions.
