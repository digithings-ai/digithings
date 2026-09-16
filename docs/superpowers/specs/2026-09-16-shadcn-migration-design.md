# digiweb × shadcn/ui — component-layer migration design

> **For agentic workers:** this is a design/scoping spec, not an implementation
> plan. It ships no code. Read it end-to-end before acting. Implementation plans
> hang off it wave-by-wave (see §7); the first plan is
> `docs/superpowers/plans/2026-09-16-shadcn-wave-1.md` (to be written).

- **Date:** 2026-09-16
- **Status:** draft — for owner review (all decisions resolved 2026-09-16: JetBrains Mono font, Base UI base, single-chart-stack ambition, migrate-everything; see §9)
- **Owner decision (m0398, verbatim):** "proceed then with this library with
  Shadzian [shadcn]. … I would want to lean on it as much as possible for all
  things from components to elements to animations. I prefer if we just use what
  they offer and change our DigiWeb design to import from there. And then our
  chatbot uses Assistant UI and that's what we lean on for DigiChat. But for the
  rest, we should use this. So we'll have to progressively move everything over."
- **Preset (owner-authored):** <https://ui.shadcn.com/create?preset=buFyyjQ> —
  Style **Lyra**, Base/Theme/Chart **Neutral**, Heading+Font **JetBrains Mono**,
  Icon **Lucide**, Radius **None**, Menu Default/Solid, Menu Accent Subtle.

---

## 1. Goal and scope

Make **shadcn/ui** the component, element, and animation substrate for every
digiweb surface, vendored once in `@digithings/web` and consumed by all sites,
so bespoke component construction ends.

**In scope**

- Vendored shadcn component set living in the `@digithings/web` package,
  exported as `@digithings/web/ui`, with a package-level `components.json`.
- A token bridge that maps shadcn CSS variables onto `@digithings/design`
  tokens so stock shadcn components render in the Instrument-Panel language
  (radius 0, mono, ink/paper primary, hairline borders) with no per-component
  restyle.
- Progressive replacement of hand-built primitives and app-local controls in
  `reference/`, `digithings-web`, `digiquant-web`, `dashboard`, and
  `digichat-*` web chrome with the vendored set.
- shadcn **Blocks** for app shells (sidebar, command palette, data table,
  charts) and selective third-party registry blocks for marketing surfaces.
- Animation standardization on **Motion** + View Transitions, using the motion
  patterns the blocks ship with.

**Out of scope / non-goals**

- **DigiChat chat surface stays on Assistant UI** (`.aui-*` thread, composer,
  transcript). No restyle of assistant-ui elements. digichat/ digichat-ui/
  packages are regression-guarded, not migrated.
- No paid libraries (Tailwind Plus / Untitled UI PRO). No runtime CSS-in-JS
  frameworks (Mantine, Chakra, Emotion).
- Finance charts keep `lightweight-charts` (CHARTS.md); `--up/--down/--rv-*`
  money and diff domains stay fixed literals (DESIGN.md §color).
- The Terminal family look (always-dark palette, prompt glyphs) is canon; the
  migration must reproduce it, not replace it.
- No new app-local CSS class families (canon guard) and no app-local primitives
  (promotion playbook: reference → `@digithings/web` → adopted).

## 2. Current state (verified 2026-09-16)

| Fact | Value |
|------|-------|
| shadcn config today | `cloudflare/digiweb/reference/components.json` exists (style `new-york`, baseColor `neutral`, cssVariables, Lucide, css `app/globals.css`, registries: `@assistant-ui`) |
| Vendored ui/ today | 8 stock files in `reference/components/ui/` (avatar, button, collapsible, dialog, dot-matrix, skeleton, textarea, tooltip) |
| Live shadcn usage today | only `reference/components/chatbot/chatbot-thread-list.tsx` + `cube-matrix-legend.tsx` |
| Token bridge today | **absent** — `web-theme.css` defines no shadcn variable names (`--background`, `--primary`, `--ring`, `--radius`, `--border`, …), so vendored components fall back to shadcn defaults |
| Tailwind setup | v4.1.7, `@import "tailwindcss" source(none)` with explicit `@source` list; `@source not "../components/ui"` |
| Primitive layer | `@digithings/web` (`cloudflare/digiweb/web/`) — controls/chat/finance/docs/… families, 73 exports, ~28 stylesheets; **no `ui/` dir** |
| Consumers | reference (4013), digithings-web, digiquant-web, dashboard, digichat embeds |
| Canon | `MIGRATION.md` (import order, `@theme inline`, `@source`, layering), `DESIGN.md` (Instrument Panel), `scripts/check_frontend_canon.py` |
| Research verdict (2026-09) | stay on shadcn/ui; adopt Lyra preset; Blocks + Motion + View Transitions; HeroUI v3 = npm fallback only if ever needed; avoid Tremor |

## 3. Target architecture

### 3.1 One vendored set, in the package

```
cloudflare/digiweb/web/
  components.json              # NEW — package-level shadcn config (style: lyra)
  src/ui/                      # NEW — vendored shadcn components (copy-paste)
    button.tsx  card.tsx  dialog.tsx  …        # npx shadcn add <name>
  src/styles/
    web-theme.css              # EXTENDED — the one bridge (see §3.2)
```

- Consumers import `@digithings/web/ui` (new subpath export `./ui`, plus
  `./ui/*` if needed). **No app vendors its own copy**; the reference app's
  `components/ui/` is deleted once superseded.
- `npx shadcn@latest add <component|block>` runs **inside `web/`**; the
  package's `components.json` points `ui` alias at `src/ui`, css at the
  bridge sheet, and carries the registries (`@assistant-ui`, plus any
  approved block registries, §9 Q5).
- Consumers add one `@source "../../../digiweb/web/src/ui"` line (path from
  each app's css) so Tailwind emits the classes — MIGRATION.md rule 4. The
  existing `@source not "../components/ui"` exclusion is dropped when the
  reference's vendored dir is deleted.

### 3.2 The token bridge (the center of the migration)

shadcn components are styled through CSS variables defined by the shadcn
theme block (`--background`, `--primary`, `--ring`, `--radius`, …). We add
those names to **`web-theme.css`** — the sanctioned single `@theme inline`
block — mapping each onto design tokens:

| shadcn var | maps to | value/derivation |
|---|---|---|
| `--background` | `--bg-canvas` | `#0A0E0C` dark / livery-appropriate light |
| `--foreground` | `--ink` | `#ECEEF0` |
| `--card` / `--popover` | `--surface` / `--surface-raised` | flat, no shadow except floating (popover) |
| `--card-foreground` / `--popover-foreground` | `--ink` | |
| `--primary` / `--primary-foreground` | ink/paper rect | `--ink` on `--bg-canvas` — **never accent fill** (DESIGN.md loud-CTA rule) |
| `--secondary` / `--muted` / `--accent` (shadcn surface roles) | `--surface-raised` / `--surface` | hover fills stay flat neutrals |
| `--muted-foreground` | `--ink-soft` / `--ink-mute` | |
| `--border` / `--input` | `--hairline` / `--hairline-strong` | `rgba(255,255,255,.09/.15)` |
| `--ring` | accent ring | `color-mix(in srgb, var(--accent) 40%, transparent)` |
| `--destructive` | `--down` | `#E5533E` (money domain — only for true destructive, not P&L semantics) |
| `--radius` (+ `--radius-sm/md/lg/xl`) | `0` | all zero (DESIGN.md) |
| `--font-sans` / `--font-mono` / `--font-display` | **JetBrains Mono** | owner decision 2026-09-16 (§9 Q1): JetBrains Mono ships as the family, weights incl. Light; matches the Lyra preset |

Rules baked in: the block lives inside the existing `@theme inline`; it reads
**theme/livery vars**, never literal colors except the sanctioned money/diff
tokens already owned by the design package; `.dark`/`.light` keep mirroring
`[data-theme]`. Acceptance: a stock `npx shadcn add button` renders
radius-0/mono/ink-primary/hairline with **zero edits** to the vendored file.

### 3.3 Preset adoption (Lyra)

The owner preset `buFyyjQ` = Lyra style + Neutral + radius 0 + Lucide + mono
headings. Adoption is: `style: "lyra"` in `components.json`, the preset's
theme block folded into the **bridge** (not pasted as a second theme — one
`@theme` rule), Lucide already in use, radius already 0. The `new-york`
vendored components are re-added under Lyra as they are swept (§4), so we
never run mixed styles for long.

### 3.4 Animation

- Motion stays the engine (`m` + `MotionProvider`/LazyMotion; raw `motion.*`
  throws by design). Blocks bring Motion patterns with them.
- View Transitions API (React 19.2 / Next 16) for route/page transitions;
  do not stack `AnimatePresence` with a view transition on the same node.
- `AutoAnimate` (~2 KB) considered for table/list diffs (Data Table wave).
- All animation enters through the package, lazy-loaded off the root bundle.

## 4. Workstreams (parallelizable)

| WS | Name | Deliverable | Depends on |
|----|------|-------------|-----------|
| **WS1** | Bridge | shadcn vars in `web-theme.css`; stock button renders canon-clean in reference | — |
| **WS2** | Vendored package | `web/components.json`, `src/ui/`, `./ui` export, `@source` lines, reference `components/ui` deleted | WS1 |
| **WS3** | Primitive sweep | button/input/textarea/label/badge/card/dialog/dropdown/tabs/tooltip/collapsible/sheet/skeleton/avatar/separator/table adopted across apps; old hand-built controls deleted or dressed | WS2 |
| **WS4** | Data + charts | shadcn Data Table (TanStack) for admin/repo/dashboard tables; shadcn Chart (Recharts) for **all** charts pending a finance reproduction audit (candles, sparklines, live ticks — §9 Q4); `lightweight-charts` removed if the audit passes, else finance-only | WS2 |
| **WS5** | Shells & blocks | sidebar block, command palette (supersedes hand-built), login/OTP blocks where applicable | WS2 |
| **WS6** | Animation pass | Motion patterns from blocks; View Transitions for routes; AutoAnimate for tables | WS3–WS5 |
| **WS7** | Marketing blocks | shadcn Blocks first; third-party react-bits / Magic UI / SmoothUI / Aceternity only where shadcn has no equivalent, each owner-signed per block on Lyra tokens (lazy-loaded) | WS2, owner pick |
| **WS8** | Canon & docs | MIGRATION.md, ARCHITECTURE.md, MANIFEST.json, ASSISTANT_UI_ELEMENTS.md, guard allowlist updated; stale css/families removed | runs with every wave |

Rules for every WS: token utilities in TSX for layout/spacing/color/type; css
only for what MIGRATION.md sanctions (keyframes/masks/art/print/unlayered
overrides); no new app-local families; every removal proves no consumer.

## 5. Waves (sequencing)

- **Wave 0 — proof of chain (WS1+WS2):** bridge + package bootstrap + the
  reference app renders a stock `Button`, `Card`, `Dialog`, `Input` from
  `@digithings/web/ui` in the Instrument-Panel skin. Exit: preview screenshots
  + vitest + canon guard green.
- **Wave 1 — reference sweep (WS3):** all primitives swapped in
  `reference/`; bespoke reference css deleted where superseded.
- **Wave 2 — app adoption (WS3+WS4):** digithings-web + digiquant-web +
  dashboard swap primitives; Data Table + Chart for the biggest bespoke
  tables/charts. Each app is its own PR (one-hop into `develop`).
- **Wave 3 — shells + blocks (WS5, WS6):** sidebar/command palette/toasts;
  motion & view-transition pass.
- **Wave 4 — marketing + cleanup (WS7, WS8):** block-by-block, owner-approved;
  dead css, families json, docs final.

Every wave is PR-shaped, reversible, and ends with the full gate: vitest
(`@digithings/web` + touched apps), `check_frontend_canon.py`, lint/typecheck,
reference preview screenshots, and a live digichat regression check (embed
unaffected).

## 6. Constraints inherited (do not violate)

1. Import order per MIGRATION.md (tokens → site layer → `web-theme` → family
   sheets); mixed-layer sheets imported plainly.
2. `web-theme.css` remains the only `@theme` block, `@theme inline` only.
3. `@source` lines for every rendered package path; Tailwind never scans
   package sources.
4. `[data-theme]` on `<html>` is authoritative; `.dark/.light` mirror it.
5. Canon guard: no new app-local class families without a families-json entry.
6. DESIGN.md laws: radius 0, mono, three color domains never blended, no
   accent-fill CTAs, shadows only on floating overlays, no glass/gradients.
7. Promotion playbook: reference → package → adopted; give package primitives
   a `dress`/variant axis instead of forking per app.
8. DigiChat (assistant-ui) is out of scope; its tests (123 files/1214) are the
   regression net for anything the package shares.

## 7. Verification

- Unit: `npm --workspace @digithings/web run test` (46 files/318 tests today),
  per-app Vitest, reference lint/typecheck.
- Tokens/canon: `python scripts/check_frontend_canon.py` clean in every PR.
- Visual: reference app on :4013 + oc-cdp screenshot protocol
  (`/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/oc-cdp/`) for
  before/after per wave; dark + light + livery-switch checks.
- Behavior: Base UI/Radix a11y (focus traps, roving tabindex, ARIA) must not
  regress; keyboard walkthrough of each swapped surface.
- Build: app builds + digithings deploy build-check stay green.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Radix vs Base UI base drift (shadcn default moved to Base UI; both are already deps) | **Base UI pinned** (§9 Q2, owner 2026-09-16); whole vendored set re-added on it; run `shadcn diff` before large adds |
| Bridge fight between shadcn theme block and scoped liveries | exactly one `@theme inline`; test livery switch explicitly in Wave 0 |
| Regressions in shared sheets break digichat embeds | digichat suites in every wave gate; no edits to chat family css unless required |
| Copy-paste set grows unmanaged | MANIFEST.json registry added in WS2; `shadcn diff` job in Wave 3+ |
| Marketing block registry rot (Tremor-style) | per-block vetting: MIT, React 19 + TW4 compatible, copied in (no npm runtime) |

## 9. Decisions (all resolved with the owner, 2026-09-16)

1. **Font — resolved (owner, 2026-09-16):** adopt **JetBrains Mono** as the
   shipping family: "we could move to JetBrains. It's a pretty popular font
   lately and it's more in use for terminal. There is a light JetBrains
   version. It's a big font family, so I'd go to JetBrains for a couple."
   → `--font-sans`/`--font-mono`/`--font-display` move from Geist Mono to
   JetBrains Mono; load the weight ramp the design needs (Light for muted/
   secondary surfaces, Regular body, Medium/Bold chrome and headings); the
   Lyra preset already assumes this family.
2. **Base — resolved (owner, 2026-09-16):** pin to **Base UI**, shadcn's
   default base: "I'd move to base UI if that's what the package uses. I want
   to try to pin things to what we used to have. I'd rather use the full stack
   from the package." → `components.json` pins the Base UI base and the whole
   vendored set is re-added against it (replacing the 8 Radix-era `new-york`
   files); no mixed bases. Assistant UI keeps its own internals regardless.
   Implication: `radix-ui` stays only as long as assistant-ui/deps need it;
   no new Radix primitives from us.
3. **Blocks first cut — resolved (owner, 2026-09-16):** sidebar, command palette,
   data table, charts, login/OTP confirmed for Wave 2–3.
4. **Charts — resolved (owner, 2026-09-16), single-stack ambition:** "if the
   default charts are good enough for our financial charts, I think we should
   just have a single chart package. And that way they all look the same. If it
   could reproduce everything we need." → WS4 gains a finance-chart
   reproduction audit (candles, sparklines, heat/dot-matrix moments, real-time
   tick updates) against shadcn Chart/Recharts; if it passes, all charts
   consolidate on Chart/Recharts and `lightweight-charts` is **removed** — one
   look, one dependency, no dual stack. If it fails, lightweight-charts stays
   finance-only (shadcn Chart elsewhere) and the audit's failing cases are
   recorded here.
5. **Marketing registries — resolved (owner, 2026-09-16), migrate everything:**
   "I want to migrate everything, essentially. We'll make it work. I just want
   to reduce the amount of dependencies and custom build-out we have." →
   shadcn Blocks are the first source for every surface; third-party
   registries (react-bits / Magic UI / SmoothUI / Aceternity) only where
   shadcn has no equivalent, each addition still owner-signed per block during
   Wave 4. Success metric is fewer bespoke components and dependencies, not
   more.
6. **Tracking issue — approved (owner, 2026-09-16):** create the migration epic
   (waves as sub-issues) before Wave 0 PRs so every PR links (#N / `Fixes #N`).

## 10. Definition of done

A site is "migrated" when: it imports only `@digithings/web/ui` (no app-local
`components/ui`), no hand-built equivalent of a shadcn primitive remains, its
css family census has not grown, its dark/light/livery states match DESIGN.md,
and its tests, the canon guard, and the digichat regression suite are green.
