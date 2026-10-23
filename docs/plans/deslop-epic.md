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

### UC3 — retire the parked app (S, ~½ day)

- Delete `apps/digiquant-app/**`, including the committed `.next` referenced in
  `.gitleaks.toml`.
- Fold `TIERS` / `tierAtLeast` (`apps/digiquant-app/lib/access.ts`) into
  `apps/digiquant-web/components/desk/desk-manifest.ts`; do not port the file.
- Move `BLOCKS.md`, `PLAN.md`, `contracts/*.md` to `docs/surfaces/` or delete.
- Update ADR D2, the parity matrix, `docs/surfaces/digiquant-app-shortcuts.md`,
  and the slice status in this plan.

Acceptance: one host, one env name (`NEXT_PUBLIC_DASHBOARD_API_URL` +
`/official-api`), no hand-copied catalog, `npm run build -w digiquant-web` green.

### Risks

Static export + `trailingSlash` means a new page needs a `PAGES` entry or it
404s. Invite gating is client-side post-hydration; do not turn it into a server
check in this epic. Never touch `digiquant/brokers/**` or the auth/entitlement
path.
