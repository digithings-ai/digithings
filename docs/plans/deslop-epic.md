# De-slop epic — execution plan

Epic: [#6327](https://github.com/digithings-ai/digithings/issues/6327)
Epic branch: `feat/deslop-epic` (cut from `github/develop` at `d68a543048`, 2026-10-23)
Final PR: `feat/deslop-epic` → `develop`, left merge-ready for the EM/CTO merge queue.

## Why this shape

The repo contains two generations of UI. The old gallery (`apps/reference`) and the
prose design docs (`packages/ui/DESIGN.md`, `PRODUCT.md`, `packages/design/*.md`)
predate the current work. The active generation is the new website + hero banners,
the new digiquant desk, digichat, and the terminal clients.

This epic spends nothing on the old generation. It fixes the new generation against
the design language the new code actually uses — not against the stale docs.

## Scope amendments

- **2026-10-23 — `apps/dashboard` is out of scope.** It is being replaced by
  `digiquant.io/app` (the `/app` desk in `apps/digiquant-web`). Do not audit,
  polish, screenshot or verify the old dashboard page. Slices U3 and U4 are
  cancelled.
- The old deployed digiquant.io pages are not verification targets. The current
  operator surface is `/app`; the parked new digiquant app is
  `apps/digiquant-app`.

## Design invariants (apply to every UI slice)

1. Preserve the **ASCII terminal feel**, hero-banner designs, wordmarks and
   terminal motifs. These are custom work; they are not slop.
2. Preserve the existing palette, type scale and component vocabulary where they
   already work. No new palette, no gradient system, no glassmorphism, no
   rounded-card SaaS look, no emoji icon set, no fabricated metrics.
3. Every change is justified by a finding from an installed skill (file:line,
   severity). "Looks better" is not a justification.
4. `docs/design/CURRENT_UI_LANGUAGE.md` (slice S0) is the authority for all UI
   slices. `packages/ui/DESIGN.md` and `PRODUCT.md` are historical.
5. Canon guard stays green: `python3 scripts/check_frontend_canon.py`.
6. digi names stay lowercase in prose, copy and docs.
7. Human-gated paths are untouched: `digiquant/brokers/**`, `digikey/**`.

## Tool ownership

Two design skills would otherwise fight over the same files. Split by surface:

| Tool | Owns | Verbs |
|---|---|---|
| **Hallmark** | public pages: `apps/digithings-web` (landing, marketing, variants), `apps/digiquant-web` marketing routes | `audit` first; `redesign <path>` only where the audit proves a structural failure, keeping content and wiring and preserving the ASCII/hero-banner identity |
| **Impeccable** | product UI: `apps/digichat`, `apps/digiquant-web/app/app`, shared kit | audit → fix (polish/distill/critique), within tokens |
| **Taste / frontend-design** | direction checks only on public pages; never a second theme | audit only |
| **baseline-ui / make-interfaces-feel-better** | component-level polish and pass/fail checks on product UI | review then fix |

Both tools may audit anywhere; only the owner may rewrite.

## Hallmark profile for this product

Hallmark's Floor is tuned for editorial marketing pages. Four of its rules encode
generic-web taste and would delete this product's deliberate identity, so they are
**not applied** here:

| Rule | What it bans | Why waived |
|---|---|---|
| 22 | zero-chroma neutrals | the monochrome terminal palette is intentional |
| 63 | middle-dot-joined meta strings | used deliberately in terminal/status chrome |
| 64 | monospace labels | the ASCII terminal voice |
| 67 | uppercase tracked labels | the instrument-panel/terminal motif |

Rules 19 (em dashes) and 54 (eyebrow labels) are judged per surface: fix on
marketing pages where they are generic, keep where the terminal motif needs them.

Everything else in the Floor still applies, notably: 48 raw colour literals,
10 layout-animating properties and `transition: all`, 34 overflow-x,
46 invented metrics, 30 emoji icons, 4 card-in-card, 2a purple gradient,
focus-visible, reduced-motion and scripting-off visibility.

`sloplint` is a signal, not a CI gate. The blocking gate remains
`python3 scripts/check_frontend_canon.py`. A slice reports sloplint counts with the
waived rules already excluded, so the number reflects actionable work.

## Slice manifest

Each slice owns a disjoint path set. A slice may not edit paths owned by another
slice; if a fix requires it, the slice stops and reports the cross-ownership need.

### Foundation

| ID | Branch | Owns | Skills |
|---|---|---|---|
| S0 | `feat/deslop-s0-design-language` | `docs/design/CURRENT_UI_LANGUAGE.md` (new) | create-design-md, impeccable (init/audit), improve-ui |

S0 reconstructs the real current language from the new surfaces: hero banners,
terminal motifs, tokens actually imported, type scale, spacing, motion, copy voice,
and the per-surface differences. It also records what the old docs got wrong.

### UI slices

| ID | Branch | Owns | Primary skills |
|---|---|---|---|
| U1 | `feat/deslop-u1-digichat-core` | `apps/digichat/src/app/**`, `apps/digichat/src/components/{chat-shell,transcript,composer,message}*` | impeccable, baseline-ui, avoid-ai-design, make-interfaces-feel-better |
| U2 | `feat/deslop-u2-digichat-surfaces` | `apps/digichat/src/components/{settings,tools,sidebar,onboarding,empty}*` | impeccable, baseline-ui, ui-skills/accessibility, fixing-metadata |
| U5 | `feat/deslop-u5-digiquant-desk` | `apps/digiquant-web/app/app/**` | impeccable, baseline-ui, avoid-ai-design, fixing-motion-performance |
| U6 | `feat/deslop-u6-digiquant-marketing` | `apps/digiquant-web/app/{page,pipeline,strategies,subsystems,changelog,contact}/**` | hallmark (audit → targeted redesign), impeccable (component audit), web-quality/seo, frontend-design |
| U7 | `feat/deslop-u7-digiquant-atoms` | `apps/digiquant-app/**` | impeccable, baseline-ui, make-interfaces-feel-better |
| U8 | `feat/deslop-u8-web-landing` | `apps/digithings-web/app/{page.tsx,_nav.tsx}`, `apps/digithings-web/components/{landing,chat}/**` | hallmark (audit → targeted redesign), frontend-design, design-taste-frontend (direction), emil-design-eng |
| U9 | `feat/deslop-u9-web-docs` | `apps/digithings-web/app/{docs,book,about,team,security,services,changelog,legal}/**` | hallmark (audit only), impeccable, baseline-ui, fixing-metadata, avoid-ai-writing |
| U10 | `feat/deslop-u10-web-variants` | `apps/digithings-web/app/variants/**` | hallmark (audit only), impeccable, design-taste-frontend (audit only), baseline-ui |
| U11 | `feat/deslop-u11-hero-banner` | `packages/hero-banner/**` | emil-design-eng, animation-performance, fixing-motion-performance, deslop |
| U12 | `feat/deslop-u12-tui-clients` | `clients/{digichat-tui,digiquant-tui,digivoice-tui,digichat-devkit}/**` | emil-design-eng, animation-performance, deslop, karpathy-guidelines |
| U13 | `feat/deslop-u13-tui-shell` | `packages/tui-frame/**`, `packages/design/{app-shell-terminal,quant-native}/**` | deslop, codebase-design, animation-performance |
| U14 | `feat/deslop-u14-ui-kit-core` | `packages/ui/src/{components/data,components/forms,components/feedback,ui}/**` | deslop, codebase-design, impeccable, baseline-ui |
| U15 | `feat/deslop-u15-ui-kit-chat-nav` | `packages/ui/src/{components/chat,components/landing,navigation,motion}/**` | impeccable, emil-design-eng, codebase-design |
| U16 | `feat/deslop-u16-digichat-ui` | `packages/digichat-ui/**` | deslop, baseline-ui, avoid-ai-design |

### Code slices

| ID | Branch | Owns | Primary skills |
|---|---|---|---|
| C1 | `feat/deslop-c1-py-quant-research` | `digiquant/src/digiquant/research/**` | deslop, karpathy-guidelines, codebase-design |
| C2 | `feat/deslop-c2-py-quant-portfolio` | `digiquant/src/digiquant/portfolio/**` | deslop, karpathy-guidelines, codebase-design |
| C3 | `feat/deslop-c3-py-quant-core` | `digiquant/src/digiquant/**` except `brokers/`, `research/`, `portfolio/` | deslop, karpathy-guidelines, improve-codebase-architecture |
| C4 | `feat/deslop-c4-py-digisearch` | `digisearch/**` | deslop, karpathy-guidelines, codebase-design |
| C5 | `feat/deslop-c5-py-digigraph` | `digigraph/**` | deslop, karpathy-guidelines, codebase-design |
| C6 | `feat/deslop-c6-py-core-libs` | `digillm/**`, `digibase/**`, `digivault/**`, `digivoice/**` | deslop, karpathy-guidelines, codebase-design |
| C7 | `feat/deslop-c7-ts-apps-code` | non-UI code in `apps/{digichat,digiquant-web,digithings-web}/**` (`lib`, `hooks`, `api`, `app/**/route.ts`) | deslop, codebase-design, code-review |

C3 and C6 exclude human-gated paths by construction. C1–C6 do not change public
behaviour; they remove dead code, duplicate helpers, needless abstraction, AI
comments, unused imports, and over-defensive branches. Behaviour changes need a
test and are out of scope for this epic.

### Docs and convergence

| ID | Branch | Owns | Skills |
|---|---|---|---|
| D1 | `feat/deslop-d1-docs` | `docs/design/**`, `docs/surfaces/**`, `apps/*/README.md`, `packages/hero-banner/README.md` | avoid-ai-writing, humanizer, no-ai-slop |
| V1 | on epic branch | gates + visual verification | ui-skills, web-quality-audit, playwright |
| V2 | on epic branch | fresh-context review + epic PR | code-review, interface-review, review-and-ship, make-pr-easy-to-review |

D1 updates only docs that describe the current generation. Historical ADRs and
`docs/plans/*` are not edited.

## Execution order

1. **S0** (1 agent). Blocks all UI fixes.
2. **Read-only audits** (parallel with S0, 4 agents): impeccable/avoid-ai-design
   across web apps; web-quality/accessibility/metadata; deslop/karpathy survey of
   Python + `packages/ui`; docs writing audit. Findings to `.agent-tmp/audit/`.
3. **Wave 1 UI** (3 concurrent): U1, U5, U8, U11, U14.
4. **Wave 2 UI** (3 concurrent): U2, U6, U9, U12, U15.
5. **Wave 3 UI** (3 concurrent): U7, U10, U13, U16.
6. **Wave 4 code** (3 concurrent): C1, C4, C5, C6 → then C2, C3, C7.
7. **Wave 5 docs**: D1.
8. **Convergence**: V1 gates and visual verification, V2 review and PR.

Each fix agent works in `.worktrees/deslop/<slice>/` on its own branch cut from
`feat/deslop-epic`, commits, pushes to `github`, and merges back into the epic
branch. Node modules are symlinked from the epic worktree; a slice does not run
`npm ci`.

## Verification

Per UI slice:

```bash
python3 scripts/check_frontend_canon.py
npm run lint -w <workspace>
npm run typecheck -w @digithings/ui        # ui slice only
npm run test -w <workspace>
npm run build -w <workspace>               # where the app has a build
```

Per code slice:

```bash
.venv/bin/ruff check <component>/src
.venv/bin/python -m pytest <component>/tests -q -m unit
npm run lint -w <workspace>
```

Convergence runs the full set on the epic branch, plus screenshots of the changed
pages (static apps) and a TUI frame export diff (terminal clients).

## Reporting

Every slice posts a findings record to the epic issue: skill, finding, file:line,
severity, fix or "no change warranted". No slice merges without one.

## Scope decision — 2026-10-23 (user, after surface review)

Screenshots reviewed: `apps/digithings-web` (landing, `/chat`, `/docs`, `/variants`),
`apps/digiquant-web` (home, `/app`, `/pipeline`, `/strategies`), `apps/digiquant-app`
(`/`, `/blocks`), `apps/digichat` (`/`, `?mode=product`, `?mode=catalog`).

**Keep and review**

| # | Surface | Slice |
|---|---|---|
| 1 | digithings-web landing + hero banner | U8 |
| 2 | digithings-web `/chat` | U2 |
| 3 | digithings-web `/docs` | U9 |
| 4 | digithings-web `/variants` | U10 |
| 5 | digiquant-web home | U6 |
| — | hero-banner package | U11 |
| — | packages/ui + digichat-ui | U14, U15, U16 |

**Consolidate**

`/app` (6), the parked `apps/digiquant-app` (8) and its `/blocks` gallery (10)
are three expressions of one surface. They are merged into one canonical desk
before any polish. New slice **UC** owns the consolidation:
`apps/digiquant-web/app/app/**` + `apps/digiquant-app/**` + the shared block
boundary. Until UC lands, U5/U7 are suspended.

**Drop as review targets**

`apps/digichat` `/`, `?mode=product`, `?mode=catalog` (9, 11, 12) are being
replaced by the **digichat devkit UI** (`clients/digichat-devkit`), the surface
where skins, colors, tools and behavior are configured. New slice **UD** owns
the devkit; U1/U2-digichat are cancelled. `clients/digichat-tui` is in scope only
where the devkit shares code with it.

**Also dropped**

- `apps/dashboard` — replaced by `/app` (already dropped).
- digiquant-web `/pipeline`, `/strategies`, `/changelog`, `/contact`,
  `/subsystems/**` — not selected. `/app` routes remain in UC.
- Do not live-verify the deployed old digiquant.io pages.

### Revised wave order

1. **Wave 1**: U8 landing, U9 docs, U10 variants.
2. **Wave 2**: U2 website `/chat`, U6 digiquant home, U11 hero-banner.
3. **Wave 3**: UC digiquant consolidation, UD digichat devkit, U12 TUI clients
   (digiquant + digivoice only).
4. **Wave 4**: U14/U15/U16 shared kit, U13 TUI shell.
5. **Wave 5**: C1–C6 Python, C7 TS app code.
6. **Wave 6**: D1 docs, then convergence.

## UC — digiquant consolidation (6 + 8 + 10)

Canonical host: **`/app` in `apps/digiquant-web`**. ADR D2 already decided this;
`apps/digiquant-app` is the stale tree copy. `/app` actually carries 19 catalog
pages across 22 route entries (5 FX routes are invite-only), not 12.

### UC1 — lift primitives into the shared kit (S, ~1 day)

Move, with tests and no behaviour change, into `packages/ui/src/components/desk/`:

- `DataTable` feature set from `apps/digiquant-app/components/DataTable.tsx`
  (sort, filter, pagination, sticky, bar, tone) merged with the desk's
  `columnRoles` from `apps/digiquant-web/components/desk/pages/table-columns.ts`.
- `KpiGrid` + `Sparkline` from the parked `components/atoms.tsx` / `ui.tsx`.
- `StateBlock` from `apps/digiquant-app/components/Block.tsx` (per-block error
  boundary + "withheld" + reason). This closes audit T4.

Acceptance: each primitive has a vitest file; `/app` imports the new components;
no second token layer; canon guard green.

### UC2 — replace text panes with rich blocks (M, ~3–5 days, per route)

`apps/digiquant-web/components/desk/desk-view.tsx` currently renders catalog
panes as one 11px line. Replace pane-by-pane with the richer block, keeping
`readOfficial` / `presentResponse` as the data path and `PanelView` as the
table/chart toggle. Order:

1. brief `live` (missing component today)
2. tearsheet `nav` and `benchmarks`
3. ledger cash
4. `/fx` (invite-only, gated; no auth changes)

Acceptance: each route renders loading, empty, error and withheld states through
`StateBlock`; no new chart library; existing tests stay green.

### UC3 — retire the parked app (S, ~½ day) — **blocked, not done**

- Delete `apps/digiquant-app/**`, including the committed `.next` referenced in
  `.gitleaks.toml`.
- Fold `TIERS` / `tierAtLeast` (`apps/digiquant-app/lib/access.ts`) into
  `apps/digiquant-web/components/desk/desk-manifest.ts`; do not port the file.
- Move `BLOCKS.md`, `PLAN.md`, `contracts/*.md` to `docs/surfaces/` or delete.
- Update ADR D2, the parity matrix, `docs/surfaces/digiquant-app-shortcuts.md`,
  and the slice status in this plan.

**Why it is blocked:** ADR D2 says the app retires only once the desk renders
`/fx/*`, `/settings`, `/settings/paper` and the access/tier ladder with live
data. UC2e ports FX; settings and the tier ladder still exist only in the
parked app, so deleting it now would remove the reference implementation
before the desk has a replacement. `TIERS` has no consumers outside the parked
app, and nothing outside it imports the package, so the deletion is safe as a
follow-up the moment UC2f lands.


Acceptance: one host, one env name (`NEXT_PUBLIC_DASHBOARD_API_URL` +
`/official-api`), no hand-copied catalog, `npm run build -w digiquant-web` green.

### Risks

Static export + `trailingSlash` means a new page needs a `PAGES` entry or it
404s. Invite gating is client-side post-hydration; do not turn it into a server
check in this epic. Never touch `digiquant/brokers/**` or the auth/entitlement
path.

## Coordination — concurrent digithings.ai session

Another opencode session, `digiquant-grid-steals-page-focus`, is doing mostly
digithings.ai work **in the main checkout** (`task/auto-default-model` at
`d5b78c51e1` + uncommitted changes). Its current diff touches:

- `apps/digithings-web/app/{_nav.tsx,page.tsx,globals.css}`
- `apps/digithings-web/components/{DtNav.tsx,landing/*}`
- `packages/ui/src/components/{NavShell.tsx,data-layout/ModuleGrid.tsx,diagrams/ArchitectureTour.tsx}`
- `packages/ui/src/navigation/HashScrollManager.tsx`
- `packages/ui/src/styles/{diagrams,nav-shell,web-theme}.css`

Rules for this epic:

1. **Do not edit those paths** in any slice while that session is active. U8
   (landing) is computed but its branch is **HOLD**: at merge time keep only
   metadata/copy/a11y hunks that do not touch nav, grid, `_nav.tsx`,
   `globals.css` or the shared UI files above; drop overlapping hunks.
2. U9 (docs) and U10 (variants) are disjoint and continue.
3. Wave 2 runs **U6 digiquant home, U11 hero-banner, UC1 desk primitives** —
   none of which touch the digithings.ai nav/grid surface.
4. Defer **U2 website `/chat`** until the concurrent session lands, because it
   may touch `ChatEmbedShell` and nav chrome.
5. At convergence, rebase `feat/deslop-epic` onto the new `develop` (or onto the
   other session's merged work) and re-run the full gate set. Do not resolve a
   conflict by reverting the other session's focus/resize fixes.

### UC1 — landed

Commit `d5640d2929`, merged `ac0140cb73`. `packages/ui/src/components/desk/` now
ships `DataTable`, `KpiGrid`, `Sparkline`, `StateBlock`, `BlockBoundary` and
`index.ts`, with 33 tests. Canon guard, `typecheck -w @digithings/ui`,
`test -w @digithings/ui` (1214 passed) and `lint -w @digithings/ui` are green.
No app wiring yet; UC2 does that.

Two notes for consumers:

- `DataTable` emits `data-col` on every cell from `columnRoles(columns, rows)`.
- `Sparkline` derives its accessible summary; pass `label` to override.
- `KpiCell` is the exported item type because `Kpi` already exists in
  `finance-tearsheet`.

### UC2 — split into per-route branches

| Slice | Branch | Route | Work |
|---|---|---|---|
| UC2a | `feat/deslop-uc2a-live-marks` | brief `live` | first `KpiGrid` + `Sparkline` block; the desk has no component for this today |
| UC2b | `feat/deslop-uc2b-tearsheet-nav` | tearsheet `nav`, `benchmarks` | `DataTable` + `Sparkline`, keep `PanelView` toggle |
| UC2c | `feat/deslop-uc2c-ledger-cash` | portfolio ledger | cash ledger missing from the desk |
| UC2d | `feat/deslop-uc2d-fx-panes` | `/app/fx` ×5 (invite) | rich blocks, no auth changes |

Each slice: import from `@digithings/ui`; replace `desk-view.tsx` text panes;
wrap blocks in `BlockBoundary`; render `StateBlock` for loading/empty/error/
withheld; keep `readOfficial`/`presentResponse` as the data path; no new chart
library; tests for the new block and its states.

## UD — digichat devkit UI

The canonical customization surface is the **web `/devkit`** route in
`apps/digichat` (`app/(devkit)/devkit/**`), not the terminal workbench. It
already imports the real `DigichatConfigSchema`, `THREAD_SKINS` and
`expandDigichatDocument`, has an inline preview using the same config resolution
as the product route, and save is fail-closed end-to-end
(`GET /api/devkit/configs`, `POST /api/devkit/save`, `POST /api/devkit/validate`,
files under `config/*.yaml`). It is dev-only (`notFound()` in production) and
loopback-gated; keep that.

### UD1 — skin and colour gallery (core gap)

Today Appearance is one skin `Select` plus one accent pair. The 12-skin grid
still lives in `/?mode=catalog` (`(baseline)/baseline/baseline-client.tsx`).
Fold that gallery into Appearance:

- grid of `THREAD_SKINS` with swatches, name and mode, selected state;
- light/dark pair per skin, not just one accent;
- contrast readout stays, and is shown per candidate pair;
- live preview updates from the gallery selection without saving;
- tests for selection, contrast, and draft/apply.

Acceptance: choosing a skin or colour in `/devkit` previews it, saves it, and
`?mode=catalog` is no longer needed for discovery.

### UD2 — preview unsaved behaviour (second gap)

Gate, backend and model changes apply only after save, so the preview shows the
old behaviour while the user edits. Add a "preview draft" path that overlays the
unsaved draft on the preview request without writing the file. Keep save
fail-closed and unchanged.

### UD3 — retire the terminal workbench screens — **not done (decision)**

The terminal workbench is a working read-only inspector, and the web `/devkit`
is canonical. Removing the TUI screens is a product decision, not a de-slop fix,
and the CLI still has no save path to replace them. Left in place; the web
devkit remains the only place that edits and saves.


### UD constraints

- Preserve the dev-only / loopback gate. Do not expose `/devkit` publicly.
- No schema copy: import `deploy-config/schema.ts` and `THREAD_SKINS`.
- No new palette: skins come from the existing registry.
- Do not touch the concurrent digithings.ai nav/grid files.

## Landed slices

| Slice | Commit | Merge | Result |
|---|---|---|---|
| S0 | `75da5b8c74` | `5ce85f0663` | current UI language doc |
| UC1 | `d5640d2929` | `ac0140cb73` | shared desk primitives, 33 tests |
| U8 | `ffa6e0840b` | `abc82e630f` | landing metadata/JSON-LD, form a11y, canonical URL, focus, 390 tests |
| U10 | `749108d1d8` | `d2d76486c6` | variants focus rings, captions, heading order, em-dash copy |
| UC2b | `0cde7e9534` | `e1765e1b0b` | live marks on `/brief` via a real payload; pane body slot |
| U6 | `f28f5c7295` | `6d75bb3845` | digiquant home metadata, skip target, overflow clip |
| U11 | `bd85c89ed9` | `715b11b784` | hero-banner clock, pause gating, reduced motion, dead exports |
| UC2c | `3e6d280323` | `7d21e778e3` | tearsheet NAV + benchmarks blocks from dashboard-api |
| U14 | `22f06c13a1` | `d61b2543a7` | shared chat kit copy/radius/roles, status + duration tokens |
| U16 | `545bb7c9d7` | `cc7119dda2` | digichat-ui radius/focus/token roles, slash matching |
| C4 | `ac1c77f223` | `843152391e` | digisearch Python: dead code, shared time helper, logging |
| D1 | `374fb1a939` | `064f552672` | stale surface claims corrected, superseded docs marked |
| U17 | `ecf8accbe5` | direct | `/book` mobile contents, metadata, diagrams, PagedJS print |
| U15 | `93ce299ad6` | direct | digichat welcome fallback, route types, baseline assertion |
| U13 | `4197b1b2a4` | merge | TUI frame writer, export validation, terminal token/focus fixes |
| C7 | `a483c3c629` | merge | one `asRecord`, dead `humanizeToolName`, ten dead exports |

`github/develop` was merged into the epic at `48d2a6fb4d` after the table was
first written. That merge brought the upstream companion fix for the chat turn
guard (`ec85a81018`), the digiclaw → digibot rename, and the chat density token
pass; conflicts were resolved toward upstream for `route.ts`, and by combining
the house roles with the density fallback in `gallery-thread/thread.aui.tsx`.

### U8 caveat — `LandingSections.tsx`

U8 fixed 9 em dashes and added `motion-reduce` in this file, which the concurrent
digithings.ai session also has dirty. At rebase, recheck this file by hand and
keep the other session's focus/resize changes. Do not revert them.

### Follow-ups found while fixing

1. **`--shadow-overlay` is missing from `packages/design/tokens.css`.** The
   literal is duplicated at `packages/ui/src/components/page-geometry.tsx:96`
   and `components/landing/AppFirstSection.tsx:413`. Add the token in U14 and
   replace both literals.
2. **digivoice is missing from the repo-activity snapshot.** Not in
   `scripts/fetch_repo_activity.py` output, `lib/repo-activity.json`, or
   `packages/catalog`, which is why `DIGIVOICE_LINES` and `DIGIVOICE_MODULE` are
   hardcoded on the landing. Fix in C7 or D1; do not invent a count.
3. **Variants `MonoNav` has no mobile equivalent** below 880px (`hidden` with no
   replacement). This is a nav redesign and the concurrent session owns nav;
   record it, do not fix it here.
4. **`eslint.base.mjs` registers `react-hooks` with no rules**, so dependency
   arrays are unverified across the repo. Separate CI-policy issue.

### U9 — landed

Commit `e8005a4a1f`, merged `e3fb88ebd8`. `/docs` and `/book` canonical URLs,
`/book/print` noindex, print heading order fixed. Content untouched.

Follow-up: the website body uses `overflow-x: hidden` (`globals.css:38`);
Hallmark rule 34 asks for `clip` on `html` and `body`. That is a website-wide
change in a file owned by U8, and `hidden` can break sticky positioning, so it
needs a visual check before switching. Recorded, not changed here.

### UC2a — landed

Commit `9e04696e4f`, merged `23687592d7`. `blocks/live-marks.tsx` renders the
five live figures through `KpiGrid`, a sparkline only when a series is present,
and `StateBlock` for missing/unknown data. 9 tests; suite 346 passed; canon,
lint and `tsc --noEmit` green.

Caveat found by the slice: `/app` is drawn by `pages/brief.tsx`, not only
`desk-view.tsx`, and `/brief` does not pass a `/kpis/live` payload. **UC2b**
owns that wiring and must not fake data if the route is static.

### UD1 — landed

Commit `2ea5d4f0ef`, merged `7cf54d3cda`. Appearance now renders a 12-skin grid
with name, mode, light/dark swatch strips, per-pair WCAG lines, `aria-pressed`
and arrow/Home/End keyboard selection. Selection rewrites the draft only; no
save call. 122 tests pass in the devkit suite; canon and the devkit eslint pass.

Findings:

1. **Skins are not colour-defined.** Colour is palette-driven (`data-palette`)
   plus the accent pair; `THREAD_SKINS` carries ids only. The gallery therefore
   shows palette-derived swatches, not invented per-skin colours. Do not add a
   fake per-skin palette table.
2. Selection highlight follows `parsed.chrome.skin`, so it moves after the
   debounced validate round-trip. An optimistic local state would make it
   instant; that is polish, not correctness.
3. The pair readout lacks the dismissible below-minimum warning that the accent
   readout has.

### Gate failures found on the baseline (resolved and remaining)

- **Resolved in U15 (`93ce299ad6`).** `npm run lint -w digichat` failed on a
  direct `packages/ui/src` import in
  `src/lib/base-path-usage.source.test.ts:9`; it now imports
  `@digithings/ui/base-path`. `tsc --noEmit` in digichat reported 3 errors in
  `src/app/api/chat/route.ts` (a duplicate unused `guard` block and a
  `sessionId` field the guard type rejects on purpose — the budget key is the
  server-derived IP); both are gone and `tsc` is clean.
- **Remaining, pre-existing on the epic base.** `npm test -w digichat` has 17
  failures across 8 files (`limits/schema`, `product-model-picker`,
  `tool-control`, `deploy-config`, `chat-panel`, `stock/tool-catalog-bar`,
  `api/chat/route`). They reproduce on the current develop checkout and come
  from config/schema drift (`extends` and null-valued keys in
  `config/datatap-trial-foundry.yaml`, missing price-cap pairs in test
  deployments), not from this epic. Re-run after the convergence merge; do not
  paper over them.


### UC2b — landed

Commit `0cde7e9534`, merged `e1765e1b0b`. `/brief` was already client-fetched
(`"use client"` + `readOfficial`), so the live block gets a real `/kpis/live`
payload with no static constraint and no fake data. 7 tests; suite 353 passed;
canon, lint, test and `tsc` green.

Approved shared change: `pages/pane.tsx` gained an optional
`body?: ReactNode` slot. It overrides only the painted face; `blocks` still size
the tile, and every existing caller is unchanged. UC2c/UC2d should use it rather
than adding more slots.

### U6 — landed

Commit `f28f5c7295`, merged `6d75bb3845`. Digiquant **home only**: canonical + full
Twitter card, `<main tabIndex={-1}>` so the skip link lands, hero veil literal
moved to `.dq-hero-veil`, rail tick animated with transform instead of width,
`body { overflow-x: clip }`, card index numbers removed, dead imports removed.
Canon/lint/test/tsc green; 337 tests.

Note: the `overflow-x: clip` change is in `apps/digiquant-web/app/globals.css`,
so it affects `/app` too. It is the layout-safe choice, but verify the desk's
sticky/focus behaviour visually at convergence.

Cross-ownership follow-ups:

1. `packages/design/site/site.css` still sets `body { overflow-x: hidden }` and
   `body { transition: background, color }`. Fix once for every app.
2. `apps/digiquant-web/app/globals.css` has no Hallmark stamp/critique/waiver
   header. Epic-level decision, not a per-page fix.
3. `components/tearsheet/asset-logo.tsx` has a pre-existing `<img>` lint warning.
