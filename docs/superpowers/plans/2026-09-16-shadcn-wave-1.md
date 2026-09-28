# shadcn Wave 1 — reference sweep (WS3)

> **For agentic workers:** this plan executes wave 1 of
> `docs/superpowers/specs/2026-09-16-shadcn-migration-design.md` (§5 wave 1,
> §4 WS3). Steps use checkbox syntax. Each task gets a brief + report + a
> fresh-context review like wave 0 (see
> `docs/superpowers/plans/2026-09-16-shadcn-wave-0.md` for the shape).

- **Date:** 2026-09-16
- **Base:** `950c72f5f` (`origin/develop` after wave 0 #4230 + #4237)
- **Branch:** `feat/shadcn-wave-1` (worktree
  `…/opencode/wt-shadcn-w1`), PR into `develop`, references epic #4206.

## Goal

Every primitive the **reference app** renders comes from
`@digithings/ui/ui` (stock shadcn, `base-lyra`, Base UI). Hand-built dress
families in the reference are deleted where superseded. The reference stops
carrying its own control dress.

## Scope notes (decisions made from the recon census)

1. **Controls-layer specimens stay.** `controls-layer-reference`,
   `dialog-reference`, `empty-states-reference`, `nav-buttons-reference`,
   `select/tags-input/search-bar/skeleton-reference` document the
   `@digithings/ui` **dress-axis controls layer**, which digichat-facing
   package families still consume. Retiring that layer is wave 3–4 work; wave
   1 does not touch it. New stock-kit specimens go on the `/ui` route instead.
2. **Definition-of-done (§10) is the migration target, not the wave target.**
   After wave 1 the reference still imports the dress-axis kit in specimen
   files, by design.
3. **Deferred with reasons:** slider (`.sl-*`) → wave 2/3 when its consumer
   set grows; searchable dropdown pane → standard `DropdownMenu` with an
   inline filter `Input` (the shadcn command-palette pattern lands in wave 3);
   sonner/toasts, popover/command, scroll-area → wave 3 blocks.
4. **Untouchable:** `(chatbot)/**` (out of scope, `@source not`),
   `components/ui/tooltip.tsx` + `dot-matrix.tsx` (test-pinned shims), all
   shared worktree WIP.
5. **Two vendored generations coexist** during the wave: dress-axis controls
   (existing specimens, digichat) and stock `web/ui` (the sweep target). No
   mixed use inside one surface.
6. **Animation classes** (`data-[state]` slide/zoom) rely on the consumer's
   `tw-animate-css` (already in `reference/package.json`); do not add new
   runtime deps to `web/` unless the CLI itself demands one (report it).

## Evidence protocol (every task)

- Reference dev server on :4013 (webpack mode:
  `npm run dev -- --port 4013` — Turbopack rejects the symlinked install),
  oc-cdp harness at `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/oc-cdp/`.
- Screenshots into the SDD dir for the routes a task touches (dark + light;
  livery switch where a scoped section exists).
- Gates per task: `python3 scripts/check_frontend_canon.py`;
  `npm --workspace @digithings/ui run test`; reference
  `npm run lint && npm run typecheck`; `npx next build --webpack`
  (supplementary; Turbopack is environmental).
- Knip-style audit after each sweep: no class token used in TSX whose only
  definition was deleted (grep the family prefix).
- SDD dir: `…/digichat-build-2.0/.superpowers/sdd/2026-09-16-shadcn-wave-1/`
  (briefs, reports, diffs, screenshots). Ledger `progress.md` there.

## Env pre-flight (once, before task 1)

The new worktree has no `node_modules`:

```bash
WT=…/opencode/wt-shadcn-w1
SHARED=…/opencode/digichat-build-2.0
ln -s "$SHARED/node_modules" "$WT/node_modules"
ln -s "$SHARED/packages/ui/node_modules" \
      "$WT/packages/ui/node_modules"
ln -s "$SHARED/apps/reference/node_modules" \
      "$WT/apps/reference/node_modules"
```

(Proves the wave-0 env quirk: web/reference installs live in the shared
worktree; reference `npm run dev` must use webpack.)

---

### Task 1: Kit — form + layout primitives

**Files:**
- Create (CLI): `packages/ui/src/ui/{textarea,label,separator,badge,alert}.tsx`
- Modify: `packages/ui/src/ui/index.ts`,
  `packages/ui/src/ui/ui.render.test.tsx`

**Interfaces:**
- Consumes: wave 0 kit + `web/components.json` (base-lyra).
- Produces: `Textarea`, `Label`, `Separator`, `Badge`, `Alert`
  (+ parts) from `@digithings/ui/ui`.

- [ ] **Step 1:** Run `npx shadcn@latest add textarea label separator badge alert`
  inside `packages/ui` (record the CLI version in the report).
  Expect zero restyles; only import adaptation allowed (`cn` from
  `@/lib/utils`).
- [ ] **Step 2:** Barrel exports in `src/ui/index.ts`; per-component render
  tests in `ui.render.test.tsx` (`data-slot` assertions).
- [ ] **Step 3:** Badge tones stay stock (`default/secondary/destructive/
  outline`); money/status tone is **call-site** utilities (`text-up`,
  `text-down`, accent) — never a restyle.
- [ ] **Step 4:** Gates + commit.

**Commit:** `feat(digiweb): wave 1 — vendored textarea/label/separator/badge/alert`

---

### Task 2: Kit — overlays (tabs, collapsible, tooltip, sheet, dropdown-menu)

**Files:**
- Create (CLI): `packages/ui/src/ui/{tabs,collapsible,tooltip,sheet,dropdown-menu}.tsx`
- Modify: `packages/ui/src/ui/index.ts`,
  `ui.render.test.tsx`

**Interfaces:**
- Produces: `Tabs` family, `Collapsible` family, `Tooltip` family,
  `Sheet` family, `DropdownMenu` family from `@digithings/ui/ui`.
  `sheet`/`dropdown-menu` are `"use client"`.

- [ ] **Step 1:** CLI add; verify Base UI base in each file; the repo's
  `@base-ui/react` is already a direct dep (`^1.3.0`, installed 1.4.1).
- [ ] **Step 2:** Exports + SSR render tests (dialog-style static markup for
  the primitives that render without portals; note portal-only parts).
- [ ] **Step 3:** Verify animation classes work with the consumer's
  `tw-animate-css` (reference has it); report if any sheet/tab animation
  class is inert.
- [ ] **Step 4:** Gates + commit.

**Commit:** `feat(digiweb): wave 1 — vendored tabs/collapsible/tooltip/sheet/dropdown-menu`

---

### Task 3: Controls specimens + `/ui` route extension

**Files:**
- Modify: `reference/components/controls/{form-fields,dropdown,tooltip,accordion,skeleton}-reference.tsx`
- Modify: `reference/app/(gallery)/ui/page.tsx`
- Modify (delete dress): `reference/app/(gallery)/controls/controls.css`
  (`.ff-*`, `.dd-*`, `.tt-*`, `.acc-*`, `.sk-toggle*` — keep `.sl-*`,
  `.sb-hint`)

**Interfaces:**
- Consumes: Task 1+2 kit.
- Produces: hand-built form/menu/tooltip/disclosure dress gone from the
  reference; `/ui` route is the stock-kit canvas.

- [ ] **Step 1:** form-fields: native inputs/textarea/checkbox/radio +
  `.ff-toggle` → `Input`/`Textarea`/`Checkbox`/`Radio`/kit `Switch`;
  labels → `Label`. Keep the specimen's fieldset semantics
  (`name`, `autocomplete`, `htmlFor`).
- [ ] **Step 2:** dropdown: `.dd-*` pane → `DropdownMenu` with an inline
  filter `Input` in the content (filter state stays app-side; document the
  mapping in the file). Keyboard/focus-return = Base UI defaults.
- [ ] **Step 3:** tooltip: `.tt-*` → stock `Tooltip`; `accordion-reference`
  single-open FAQ → `Collapsible` composition (one open index) or nested;
  `sk-toggle` → kit `Switch`.
- [ ] **Step 4:** `/ui` route: add dark/light/livery sections for the new
  primitives (textarea, label, separator, badge, alert, tabs, collapsible,
  tooltip, dropdown-menu, sheet trigger+content) mirroring wave 0's
  composition grammar (server component, stock only).
- [ ] **Step 5:** Delete the dress blocks; grep audit (`ff-|dd-|tt-|acc-|sk-toggle`
  unused outside defs); screenshots `/controls` + `/ui` dark/light; gates;
  commit.

**Commit:** `feat(digiweb): wave 1 — controls specimens on the stock kit`

---

### Task 4: Account surfaces sweep

**Files:**
- Modify: `reference/components/account/{login-card,signup-card,payment-band,settings-panel,session-card}.tsx`
- Modify: `reference/app/(gallery)/account/account.css` (dress deletions;
  keep layout: activity, plan-items, pay-form, stat-strip)

**Interfaces:**
- Consumes: Tasks 1–2 kit.
- Produces: account surfaces on stock kit; `.acct-input/-field/-select/
  -divider/-toggle/-segment/-strength-seg/-setting-tabs/-error/-forgot`
  deleted where superseded.

- [ ] **Step 1:** inputs/labels/checkbox/radio → kit (login, signup,
  payment-band); error state = `aria-invalid` + call-site tone utility.
- [ ] **Step 2:** settings: native `<select>` + `.acct-setting-tabs` →
  kit `Select` + kit `Tabs` (check Base UI select portalling inside the
  panel); toggle rows → `Switch`.
- [ ] **Step 3:** buttons → kit `Button` (login/signup/session);
  `.acct-divider` → `Separator`.
- [ ] **Step 4:** Delete dress css; grep audit; screenshots
  `/account/*` routes dark + light; gates; commit.

**Commit:** `feat(digiweb): wave 1 — account surfaces on the stock kit`

---

### Task 5: Button + badge sweep (marketing / data / terminal)

**Files:**
- Modify: `reference/components/{buttons-cta-reference,announcement-bar-reference,scroll-nav-reference,toast-stack-reference,pricing-reference,pricing-matrix-reference,changelog-rail-reference,code-review-reference,terminal-budget-reference}.tsx`
- Delete dress: `globals.css` (`.btn-*` minus `btn-row*` layout),
  `data.css` (`.cr-tag*`), `terminal.css` (`.rv-chip`, `.badge`),
  `finance.css` (`.pos-side`)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: one button vocabulary (kit `Button`) across the reference.

- [ ] **Step 1:** Map `.btn-primary→default`, `.btn-ghost→ghost`,
  `.btn-quiet→outline`, `.btn-danger→destructive`; `loading` = disabled +
  inline spinner at the call site (kit Button has no loading prop — record
  the idiom in the file); magnetic CTA = kit `Button` with
  `render={<m.button …/>}` — if Motion+render conflicts, keep the
  hand-built CTA and record why.
- [ ] **Step 2:** Chips → `Badge`: `.cr-tag*` (feature=`secondary`,
  breaking=`destructive`), `.rv-chip`=`outline`, `.badge`,
  `.pos-side`=`outline` + `text-up|text-down`. `.livery-chip`/
  `.tg-swatch-chip` stay (interactive swatches, not badges).
- [ ] **Step 3:** Delete dress css; grep audit; screenshots of touched
  gallery routes dark+light; gates; commit.

**Commit:** `feat(digiweb): wave 1 — button + badge sweep, dress css deleted`

---

### Task 6: Chrome, tables, surface cards

**Files:**
- Modify: `reference/components/{site-nav,dashboard-workspace-reference,portfolio-workspace-reference,portfolio-reference,contents-overview,changelog-rail-reference,deck-cards}.tsx`
- CSS: `globals.css` (`.site-nav-sheet*`, scrim, burger → delete where
  Sheet supersedes), `finance.css` (`.pw-table*`), `home.css` (`.co-card`,
  `.cr-card`), `data.css` (`.deck-alert*`)

**Interfaces:**
- Consumes: Tasks 1–2; kit `Table`, `Select` already exist.
- Produces: mobile nav on kit `Sheet`; all three native tables on kit
  `Table` (fixes the unstyled `.dw-*` defect by replacement).

- [ ] **Step 1:** site-nav: mobile `.site-nav-sheet` → `Sheet`
  (preserve scroll-lock, route-change close, controls inside); the 4 native
  `<select>` pickers → kit `Select` (verify portal placement in nav + sheet).
- [ ] **Step 2:** tables: dashboard-workspace, portfolio-workspace,
  portfolio-reference → kit `Table`/parts; numeric columns use the kit's
  numeric treatment; delete `.pw-table*`; drop unresolved `.dw-*` tokens.
- [ ] **Step 3:** surface cards: `contents-overview` `.co-card` and
  `changelog-rail` `.cr-card` → kit `Card`/parts; `deck-cards` `AlertCard`
  `.deck-alert*` → kit `Alert` (tone mapping status up/down; no accent
  fill). Domain grammars (`.uv-card*`, `.sym-tile-card*`, `dqpipe-*`,
  tearsheet/deck stacks) stay.
- [ ] **Step 4:** CSS deletions + grep audit; screenshots home/`/dashboard`
  /`/portfolio` + mobile-width nav sheet; gates; commit.

**Commit:** `feat(digiweb): wave 1 — chrome sheet, tables, surface cards on the stock kit`

---

### Task 7: Close-out — canon audit + wave evidence

**Files:**
- Modify only if contracts changed: `MIGRATION.md` / `ARCHITECTURE.md`
  (expected: no change — wave 0 wrote them).
- SDD dir: wave screenshot set + ledger.

- [ ] **Step 1:** Full-wave grep audit: every deleted family prefix unused;
  no mixed-generation imports inside one surface; `@source not
  "../components/ui"` still needed (shims stay).
- [ ] **Step 2:** Full gates on the tip: canon guard, web suite, reference
  lint/typecheck, `npx next build --webpack`; digichat regression
  (`npm --workspace digichat run test` — record environmental state A/B).
- [ ] **Step 3:** Screenshot set (dark + light + livery where applicable):
  home, `/controls`, `/account`, `/ui`, `/chrome`; attach to ledger.
- [ ] **Step 4:** Ledger complete; commit any docs touch-ups.

**Commit:** `docs(digiweb): wave 1 — sweep record` (only if files change)

---

### Task 8: Ship

**Files:** none (git/GitHub only).

- [ ] **Step 1:** Push `feat/shadcn-wave-1`; open PR into `develop`
  referencing #4206 (title:
  `feat(digiweb): shadcn wave 1 — reference sweep (#4206)`).
- [ ] **Step 2:** Aggregate PR-scope review in a fresh-context read-only
  subagent (range `950c72f5f..<tip>`), findings comment with the
  `in-session-review` marker + `reviewed:agent` label (wave 0 pattern,
  CODE_REVIEW_POLICY).
- [ ] **Step 3:** Fix findings on-branch, re-verify, merge when CI green
  (`--merge`, never `--admin`/`--auto`); expect the same up-to-date chase
  as wave 0 — resolve plan-file add/add conflicts locally keeping the
  wave-amended plan.

---

## Self-review checklist (before ship)

- [ ] Every task's commits are in the ledger ranges; no foreign commits.
- [ ] No vendored file carries a restyle (byte-stock + `cn` import only).
- [ ] No app-local class family added; families json untouched.
- [ ] `@source` lines unchanged except where a task removes a scanned dir.
- [ ] Chatbot embed + pinned shims untouched; digichat suite state
  recorded A/B.
- [ ] Screenshots exist for every touched route, dark + light.
- [ ] Plan checkboxes match reality; deviations recorded in the ledger.
