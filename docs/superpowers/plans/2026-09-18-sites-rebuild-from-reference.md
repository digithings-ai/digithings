# Rebuild digithings.ai and digiquant.io (and the digiquant dashboard) from the design reference

Status: draft for approval · 2026-09-18 · branch `feat/rebuild-sites-from-reference`
(worktree `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/wt-rebuild`, cut from
`origin/develop` @ `44ff6d109`).

## 1. Why

Wave 3 and wave 4 migrated the UIs onto the canonical kit, but the result introduced
regressions on the public sites (see §7) and left the pages reading as "kit parts dropped
into an old layout". The **design reference app** (`apps/reference`) is judged
correct and is the visual canon. Rather than patch the old pages, rebuild both public sites
**from scratch** against the reference, and use the rebuild to certify every public-facing
page and its content for release.

Two reference sites are the inspiration for the new presentation:

- **`opencode.ai`** → the model for **digithings.ai**: monospace-first, deliberately small
  type (22px h1), flat 40px nav, 1080px content width, 4–6px radii, CSS-only motion;
  install command as a segmented tab group; dense mono feature checklist with bold lead-ins;
  stats as `Fig N` figures with captions; bracketed mono micro-labels (`[*]`, `[GitHub [208K]]`);
  FAQ accordion; product demo video hero; privacy section; waitlist capture.
- **`gloom.sh`** → the model for **digiquant.io**: shadcn/zinc, Geist + Geist Mono, 36px/600
  mono h1 with −0.9px tracking, 1024px content width, 96px section rhythm, 10px cards;
  product screenshot as the hero artefact; **keycap-style mono shortcut chips** as the
  organising device for a large feature set; install-channel triad (web/desktop/TUI);
  semantic finance colour tokens (positive/negative/pending); bracketed mono footer groups.

Both are flat, high-density, terminal-native and animation-light — the same DNA as the
reference app.

## 2. Scope

In scope:

1. **digithings.ai** — rebuild the public site (`apps/digithings-web`) from scratch on the kit.
2. **digiquant.io** — rebuild the public site (`apps/digiquant-web`) from scratch on the kit.
3. **The digiquant dashboard** (`apps/dashboard`, served at `/dashboard/`) — in scope.
4. **The design reference** (`apps/reference`) — a refinement, consolidation and
   organisation pass (§5), because it is the component source of truth for the rebuild.
5. **A public-page content audit** — every public page and every claim on it, certified for release.

Out of scope (do not modify):

- **digichat** (`apps/digichat`, `packages/digichat-ui`) — explicitly out of scope.
  The two iframe shell pages `/chat` and `/chat/occ` inside digithings-web stay part of that
  site, but nothing about the digichat product changes.
- Backend services, `digikey/`, live-trading paths, `projects/`.
- The kit's public API surface: components come **from** the canonical layer; if a needed part
  is missing, it is added to the kit (with tests) rather than re-implemented app-locally.

## 3. Fresh apps, not in-place edits

Per the decision taken: build **fresh page trees** rather than restyling the existing pages.
Concretely each site keeps its package, build and deploy surface (§8) but its `app/**` is
rebuilt: new layout, new chrome, new page compositions, all rendering kit parts.

Retained deliberately (they are working plumbing, not presentation):

- Routes and redirects (`public/_redirects`), `sitemap.ts`, `robots.ts`, `manifest.ts`.
- Static-export configuration, `trailingSlash`, `basePath` (/dashboard), the `_headers` CSP.
- Post-export build steps: OpenAPI sync, vendored Swagger UI, OpenWiki export, `build-info.json`.
- Data sources: Supabase (tearsheets, live book, prices), the R2 market-data worker, Coinbase WS,
  `lib/repo-activity.json`, `@digithings/design/releases.json`, kit `data/modules.ts` and
  `data/subsystems.ts`.
- The digichat `/embed` iframe shells and their postMessage protocol.
- The "stale vs live" contract in digiquant's `lib/live/types.ts` — live badges and valuation
  silently regress if it is dropped.

## 4. Sources of truth

| Input | Path |
|---|---|
| Design canon (components, tokens, specimens) | `apps/reference` + `packages/design` |
| Kit | `packages/ui/src` (`@digithings/ui`, `@digithings/ui/ui`) |
| Site inventory | `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/rebuild/inventory-*.md` |
| Reference-site study + screenshots | `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/ingest/` |
| Regression must-not-repeat list | `/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/regressions/regressions-wave34.md` |

## 5. Workstream A — reference refinement, consolidation, organisation

Target information architecture (each route becomes a family; specimens are grouped by family,
not by file):

```
/                     foundations — tokens, theme, livery, type suites, motion laws, contents
/typography           type specimen, type suites, word reveals, copy grammar
/controls             ALL inputs and controls (fold the current /ui route in here):
                      button · input/label/textarea/separator · checkbox/switch/radio ·
                      select · slider · tags-input · search-bar · nav-buttons/pager ·
                      date-pager · dropdown-menu · dialog/sheet · tooltip ·
                      collapsible/accordion · skeleton · empty-state
/data                 tables (plain/sortable/precision/pricing-matrix) · dot-matrix · stat ·
                      odometer · marquee · card deck · changelog · repo-activity · conviction · roadmap
/finance              canvas screens (ticker, price, equity, drawdown, synced tearsheet,
                      performance dashboard, blotter/workspace, order book, metrics,
                      returns matrix) + the print tearsheet (folding the current /tearsheet)
/effects              reveal · scroll transitions · ambient · pipeline · routing
/chrome               nav shell · footer · socials · announcement · command palette · toast ·
                      tabs · breadcrumbs · pagination · module card · scroll nav
/chatbot              thread · chrome · cube matrix · terminal transcript · loaders
/layout-patterns      feature cell · bento · numbered stages · docs layout · product frame ·
                      phone · testimonial
/symbols              emblems · marks · tiles · vendor logos · glyphs
/account              account/auth · pricing · docs templates
```
Reference-only, off the primary canon nav: `/brand` (not shipped), `/iterate` (working lab),
the chatbot fixture runtime.

Must-fix defects found in the inventory:

1. **`/ui` is behind the kit it proves.** It does not show Table `density`/`numeric`/
   `TableRowHeader`, Select composition (`SelectPopup`), Badge tones
   (`ghost/link/neutral/accent/warn/up/down`, `dress="chat"`), Checkbox or Switch — all of which
   the kit now ships. `/ui` folds into `/controls` and gains them.
2. **Duplicated specimens across routes** — Dialog, DropdownMenu, Collapsible, Tooltip,
   Input/Label/Textarea and Badge appear in both `/ui` and `/controls`. Each part appears once.
3. **No reference test suite** (lint + typecheck only), so consolidation is unguarded. Add a
   route smoke test (every gallery route renders, no route 404s, the nav lists every family).
4. **Stale docs** — `design/site/README.md` (ProductFrame/Bento "deferred" but exported),
   `design/README.md` ("dashboard token adoption deferred" — it now imports the canon),
   `reference/components.json` (points at a near-empty `components/ui/`), and the unreferenced
   `reference/components/ui/tooltip.tsx`.
5. **Unlayered reference family CSS** outranks kit utilities — audit each family sheet and move
   dress into `@layer components` where the intent is "default, overridable".

Definition of done for workstream A: the target IA above exists; every kit part appears exactly
once; `/controls` covers the whole `ui/index.ts` surface; the route smoke test passes; the stale
docs are corrected; lint + typecheck + `next build --webpack` (18+ routes) green.

## 6. Workstream B — the rebuild, page by page

### digithings.ai (`apps/digithings-web`) — opencode-informed language

| Page | What it must become (mapping to canonical parts) |
|---|---|
| `/` | Small-type mono hero with the one-line claim, install command as a **segmented tab group** (`curl`/`docker`/`git`) with a copy affordance; `OdometerStrip`/`StatCounter` figures as `Fig N` with captions; `TerminalManifest` module list (dense mono checklist with bold lead-ins); `StackRow` vendor groups; `RepoActivity`; `NumberedStages` principles; `WordReveal` claim; `ContactMailto` + `SocialRow`; `Colophon` + footer. Product demo as a looping media block. |
| `/about` | Prose page: property cards, compatibility list (`RuledList` grammar), glass-box traceability, limits, source CTA. |
| `/docs` | `DocsLayout` (unchanged shell): hero, shared guides, per-module articles. Chrome rebuilt on the new nav. |
| `/docs/api`, `/docs/api/[service]` | Index + per-service Swagger explorer, full width, no sidebar-less column bug. |
| `/changelog` | Release rows from `releases.json`, bracketed mono meta. |
| `/quality` | Figures as `Fig N`, dimension stages, lanes and limits as ruled lists. |
| `/security` | Identity/traceability/pipeline/limits ruled lists + disclosure policy. |
| `/services` | What we do, engagement shape, contact. |
| `/team` | Maintainer card, working-together CTA. |
| `/legal/privacy` | Notice, what leaves the browser, browser storage, questions. |
| `/chat`, `/chat/occ` | Retained as-is (iframe shells) with the new nav/footer chrome. |
| `not-found` | New chrome, two CTAs. |

Nav/footer rebuilt once as a shared chrome module (no duplicated nav data between sites).

### digiquant.io (`apps/digiquant-web`) — gloom-informed language

| Page | What it must become |
|---|---|
| `/` | One-line mono value proposition; **product screenshot as the hero artefact** substituted for the canvas mesh; live ticker strip; metrics; the research→portfolio pipeline as a **keycap-chip function gallery** (the 16 phases become chip-labelled cards); live portfolio panel; strategy suite; `WordReveal` claim; three `PricingTierCard`s + FAQ accordion; `Colophon` + footer with bracketed mono groups. |
| `/strategies` | Library grid on the new chrome, filter toggles. |
| `/strategies/[id]` | `TearsheetView` recomposed on the kit finance family with the new chrome; print layout preserved; honesty chips and "illustrative, in-sample" footer retained verbatim. |
| `/subsystems/[id]` | Poster page on new chrome; kit `StackRow`; related chips. |
| `/changelog`, `/contact` | Same treatment as digithings. |
| `/pipeline` | Retained redirect. |
| `/dashboard/**` (24 routes) | Sidebar/`main` layout rebuilt explicitly (**no implicit offset**); DB gate reworked so gated routes render an honest, styled "live data unavailable" panel *and* the static, non-DB surfaces stay readable; `/pipeline` becomes genuinely DB-exempt as its own comment claims; duplicated controls-layer imports re-pointed to `/ui`; nested `<main>` landmarks removed; dead-but-pinned components either wired or deleted. |

Cross-site: one shared chrome/no duplication; counts and claims single-sourced (kit registries,
data files) rather than hardcoded per page.

## 7. Workstream C — public-page content audit and certification

For every public page, produce a signed-off checklist:

1. **Claims** — every factual/numeric claim verified against source at a stated date. The
   inventory's audit lists are the starting set, including: `9 modules shipping`, `16 compose
   services`, `2 vector backends`, `0 keys stored`, `321 python test files`, `180 frontend test
   files`, `63 ci workflows`, `17 test lanes` (counted `5 August 2026`), digikey `18 modules`,
   rate limits `10/min burst 20`, timeouts `connect-5/read-30/write-10/pool-5`, JWKS `300s`,
   disclosure `72 hours`/`7 days`, privacy effective `August 5, 2026`, digichat GHCR `v0.9.3`,
   repo snapshot (`2388 commits`, `1126 pulls merged`, `532 issues closed`, latest
   `digichat-v1.5.0`), plus digiquant's `7 pipeline stages`, `0 live orders`, `3 subsystems`,
   two-tier pricing, strategy honesty chips, and the SDCA knees `25/70`.
2. **Links** — every outbound link resolves (GitHub org/repo/security/scoring/releases, digiquant.io,
   contact addresses); no link to `/openwiki` unless the export actually produces it (see §7) .
3. **Honesty** — no promise of live trading, no unmarked projections; in-sample/backtest wording
   present wherever a performance figure appears.
4. **Placeholders** — no lorem/TODO/placeholder copy; unmounted or dead content removed.
5. **Metadata** — title/description/OG per page, sitemap complete, no route linked but missing.

## 8. Must-not-repeat list (regression baseline)

From the wave-3/4 sweep (report in Sources): **Critical** — dashboard content rendering under the
fixed sidebar. **Important** — the dashboard DB gate replacing every non-exempt route with an
empty state (including static pages); digithings-web's `/openwiki` nav/sitemap link 404ing because
the route is only produced by the deploy script. **Minor** — dashboard route collapse (several nav
destinations silently redirecting to `/pipeline`); inconsistent control typography across migrated
surfaces; a tall empty footer band on digiquant pages. Each rebuild slice's review must explicitly
check these, and the acceptance criteria for the rebuild include "none of the must-not-repeat
regressions are reproducible".

## 9. Build and deploy surface (kept)

- **digithings-web**: `prebuild` (write-csp-headers + sync-openapi) → `next build --webpack`
  (webpack deliberate — Turbopack hydration bug) → `scripts/build-digithings.sh` assembles `dist/`,
  verifies `_headers` frame-src, writes build-info, verifies OpenAPI/Swagger, exports OpenWiki and
  patches its meta CSP, mirrors `functions/`. `wrangler.toml` Pages, `pages_build_output_dir = out`.
- **digiquant-web**: `next build --webpack`; same deploy script family; `_redirects` (olympus,
  atlas, pricing, pipeline, legacy names) and the `/dashboard*`-scoped CSP retained.
- **dashboard**: separate export into `dist/dashboard/` with `basePath /dashboard`; Supabase env
  vars (`NEXT_PUBLIC_SUPABASE_URL`, anon key) and `NEXT_PUBLIC_MARKET_DATA_URL` documented.
- **Reference**: lint, typecheck, `next build --webpack`.

## 10. Execution model

Team tooling is unavailable in this session; work runs through `task` subagents (in-session) and
`delegate` (background, read-only), with the lead verifying every slice and integrating. Per slice:

1. Dispatch with a written brief (scope, files, canonical components, gates, report path).
2. Slice returns a commit; the lead cherry-picks and re-runs the gates at the integrated tip.
3. Review each slice (fresh-context review file per `AGENTS.md`, kept beside the plan).
4. Regressions in §8 are checked explicitly on every slice.

## 11. Task breakdown

| # | Task | Deliverable | Gates |
|---|---|---|---|
| R0 | Reference consolidation | new IA, `/controls` complete, dedupe, docs fixed | lint/typecheck/build + route smoke test |
| R1 | Shared chrome | nav/footer/module-card/CTA built once, single-sourced data | both sites build |
| D1 | digithings-web page tree | all 13 routes rebuilt on the new language | build + content audit checklist |
| Q1 | digiquant-web page tree | all 9 routes rebuilt on the new language | build + content audit checklist |
| Q2 | dashboard chrome + gate | explicit sidebar layout, honest DB gate, `/pipeline` exempt | build + 24-route smoke |
| Q3 | dashboard surfaces | re-point remaining controls-layer imports; remove nested mains; resolve dead components | build + tests |
| C1 | Content audit | signed checklist per public page | all claims verified & dated |
| C2 | Release certification | links, metadata, honesty, placeholders | green on both exports |

## 12. Definition of done

- Both public sites and the dashboard render entirely from canonical parts, with no app-local
  component duplicating a kit part and no raw native UI outside documented exemptions.
- The reference's new IA is live, complete and test-guarded.
- Every public page has a signed content-audit checklist; every claim is verified and dated.
- None of the §8 regressions reproduce; dark and light both verified at desktop and narrow widths.
- Both sites build and export green, with their deploy scripts unchanged in behaviour.
