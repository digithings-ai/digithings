# The digiweb canon — adoption playbook

Every frontend surface consumes the design system the same way. This is the
playbook that migrated all five apps (#1399, 2026-07) and the contract the
**frontend canon guard** (`scripts/check_frontend_canon.py`) enforces going
forward. The guard runs as a dedicated **unconditional** `frontend-canon` job
in `ci.yml` on every PR/push (#1434) — it scans the whole `apps/` + `packages/` tree via
`git ls-files`, not just the diff, so it must not be path-gated — and also runs
(redundantly) inside the web/dashboard/digichat test jobs.

## The wiring (every app, in this order)

```css
@import "tailwindcss";
@import "@digithings/design/tokens.css";
@import "@digithings/design/site/site.css" layer(components); /* if used — see below */
@import "@digithings/ui/styles/web-theme.css";               /* THE bridge */
@import "@digithings/ui/styles/nav-shell.css";               /* if using NavShell */
@import "@digithings/ui/styles/docs.css";                    /* if using the docs family */

/* Tailwind never scans package sources — point it at the shared components you use: */
@source "../../../packages/ui/src/components/NavShell.tsx";
@source "../../../packages/ui/src/components/docs";
```

Three rules that are load-bearing, learned the hard way:

1. **One bridge, `@theme inline`, never app-local.** `web-theme.css` is the
   only `@theme` block. `inline` makes utilities emit `var(--token)` at the
   use site, so scoped liveries (`.accent-digiquant { --accent: … }`) and
   `data-theme` flips re-resolve inside every utility. A plain `@theme`
   freezes the var at `:root` — the scoped-livery bug that shipped to both
   marketing sites before #1399.
2. **Never import a shared sheet unlayered** — *unless the sheet manages its
   own layering*. Unlayered author CSS outranks ALL `@layer`s: site.css's
   `* { margin: 0 }` reset silently killed every margin utility (including
   NavShell's `mx-auto` centering) until imported as `layer(components)`.
   The exception: sheets whose headers say to import them **plainly** because
   they split rules deliberately between `@layer components` (defaults that
   call-site utilities must override) and unlayered (state/structural rules
   that must keep outranking plain utilities) — `chat-core.css`,
   `chat-widgets.css`, `controls-core.css`, `controls-overlay.css` (#1418,
   #1419), `finance-tearsheet.css` (#1463 — its unlayered portion includes
   the ENTIRE `@media print` grammar, the tearsheet family's differentiator),
   and `repo-activity.css` (#3445 — hairline lists, two-column collapse, clone
   box).
   Wrapping those in `layer(…)` demotes their state rules and breaks
   digichat's rendered-look parity (or, for the tearsheet, the PDF export).
3. **`@source` any package component you render.** Without it the shared
   component's utilities are never generated — the failure is silent (its
   own CSS file masks most of it).

Theming: `data-theme` on `<html>` is authoritative (shared `ThemeProvider` +
`themeInitScript` from `@digithings/ui`). If an app needs `.dark`/`.light`
classes (shadcn-style selectors), mirror them from the attribute (see
digichat's `ThemeClassSync`) — never the other way around.

## Migrate vs leave (styling placement)

**To token utilities in TSX:** clean layout, spacing, color, typography —
`text-ink`, `bg-surface`, `border-hair`, `text-up`/`text-down` (P&L only),
`font-mono`, arbitrary sizes like `text-[0.72rem]` where the scale demands.

**Stays CSS** (family sheet or app globals): `@keyframes`, masks, SVG/canvas
art, `::before`/`::after` art, scroll-driven transforms
(`animation-timeline`), `@container` queries, `:nth-child`/combinator/
descendant selectors, two-color `color-mix()`, custom-prop readers, print
blocks, and unlayered-override classes. Re-point their color values at
tokens; never leave raw hex without a comment naming the token it mirrors.

**Concrete colors are sanctioned only in:** `dashboard/lib/chart-colors.ts`
(categorical/benchmark hues), tenant embed accents, SSR `theme-color` metas
(commented), canvas scenes, print pins, and the reference livery swatch
table — the guard's ALLOWLIST. Anything else needs a
`canon-allow: <reason>` comment on the line, and a reason that survives
review.

## Shared primitives first

Before writing new UI, check `packages/ui/MANIFEST.json` (144 components,
17 families) and `@digithings/ui` exports: NavShell, Footer/Colophon,
DocsLayout/CodeTabs/EndpointDoc, Pricing/PricingMatrix, NumberedStages,
PerfMetrics/StatCounter, TerminalManifest, RepoActivity, the chat family (ChatTranscript/
ChatMessage/ChatMarkdown/ChatToolCall/…), the vendored shadcn kit
(`@digithings/ui/ui`, below — the **only primitive source**; the legacy
controls layer was retired in batch K3), Terminal,
Emblem/StackRow, ModuleCard, Reveal/Stagger/HeroEntrance,
useScrollyFeatures/ScrollyRail. Motion always via `m` under `MotionProvider`
(LazyMotion `domAnimation` `strict` — a raw `motion.*` element creator throws).
The reference app (port 4013) is the live catalog; `/digiweb` is the agent
entry point.

## The vendored UI kit (shadcn, #4206 wave 0)

The migration's first stock shadcn/ui components live in `@digithings/ui`:
`web/src/ui/` — Button, Card, Dialog, Input — barrel `web/src/ui/index.ts`,
package export `@digithings/ui/ui`. Base UI (`@base-ui/react`) underneath,
`base-lyra` preset (radius 0, Lucide), wearing the same single bridge — the
kit has **no CSS file of its own**.

- **Add a component**: run `npx shadcn@latest add <name>` inside
  `packages/ui` — its `components.json` is authoritative
  (`"ui": "@/ui"`). Never vendor into an app; the kit is package-owned, the
  same as any promoted primitive.
- **Consume**: import from `@digithings/ui/ui`, and add
  `@source "../../../packages/ui/src/ui";` to the app entry (rule 3 above). The shipped
  components import `cn` package-relative (`../lib/utils`); `npx shadcn add`
  re-introduces `@/lib/utils` in new files, so re-point those imports before
  committing — consumers need no `@/lib/utils` alias.
- **`--color-primary` is ink/paper — never the accent.** Accent stays a
  livery/scoped signal; primary is the neutral action.

Wave 3 finished the promotion: every app and the reference now consume the kit
where it covers the part, and the controls copies that lost their last consumer
were deleted (Card/Input React copies at T6; the digichat wrappers that needed
the chat tone are one-line adapters pinning `dress="chat"`). The kit reproduces
the controls layer's `dress="reference"|"chat"` axis, so a consumer that needs
the chat tone passes `dress="chat"` rather than importing a second copy.

Wave 4 (#4306) closed the last capability gaps (kit Table `numeric`/`density`
and `TableRowHeader`, kit Select `SelectPopup`/`SelectItemIndicator`, kit Badge
tones), re-pointed the seven dashboard twelve-x `Sheet` imports onto the kit,
and deleted the controls files that then had zero consumers — `Avatar`,
`Badge`, `Sheet`, `Collapsible` — plus digichat's four dead `ui/` wrappers and
the second gallery-thread component library. Batch K1 (#4306) then promoted the
seven highest-impact remaining parts, K2 finished the wayfinding/form parts, and
K3 retired the layer outright. Proof route:
`reference/app/(gallery)/(controls)/controls/page.tsx` (dark, light, and a
scoped livery).

Batch K1 (#4306) promoted the seven highest-impact keep-list parts into the kit
in one pass — **Slider, EmptyState, Skeleton (+ `SkeletonGroup`), RadioGroup/
Radio, Field, IconButton, SegmentedControl** — and repointed every live
consumer (canon specimens, dashboard, digichat-ui, `ThemeProvider`). The
controls copies remained at zero consumers until K3; the reference's local
`.sl-input` slider mechanic was deleted. The recipe is
[§ Promote a part out of the controls layer](#promote-a-part-out-of-the-controls-layer-batch-k1).

Batch K2 (#4306) finished the promotion: **Breadcrumbs, Pagination, DatePager,
TagsInput (+ `TagChip`), SearchBar**, plus two net-new kit parts — **Avatar**
(vendored stock shadcn/Base UI; the kit had none) and **Form** (a presentational
wrapper over `Field` and the kit inputs; the repo carries no form-library
dependency, so it owns no state). Every live consumer was repointed (canon
specimens, the RTL proof, the dashboard day selector and briefs index).
`DatePager`'s `.nb-cal` calendar grid and its `kit-pop` enter/exit travel moved
to `styles/web-theme.css`, so the kit part no longer reads the controls sheet.
The controls copies remained at zero consumers until K3.

Batch K3 (#4306) **retired the legacy controls layer**. The last main-barrel
consumers (dashboard `Button`/`Dialog`/`DropdownMenu`/`Tooltip`,
digiquant-web/digithings-web `Table`/`Select`, digichat's adapter re-exports)
were re-pointed to `@digithings/ui/ui`, `Pager`/`PagerPage` were promoted into
`ui/pager.tsx` for the canon nav-buttons specimen, and `cx` moved to
`lib/cx.ts` for `ContactMailto`. `packages/ui/src/components/controls/*` and
its `src/index.ts` exports were deleted, and the dead `.ctl-*` CSS
(`ctl-avatar*`, `ctl-badge-ref*`, `ctl-search-row`, `ctl-sheet*`) went with it.
The promote playbook below is **closed**: there is no controls layer left to
promote out of — new parts are authored directly in `packages/ui/src/ui/`.

### Promote a part out of the controls layer (batch K1)

The repeatable shape K1 used for each of the seven:

1. **Read the controls source and its CSS.** The controls file's docblock names
   the adoption targets and every `dress`/variant axis that matters; its rules
   live in `styles/controls-core.css` (or a family sheet). Translate them
   value-for-value — this is a *port*, not a redesign.
2. **Write the kit part in `packages/ui/src/ui/<name>.tsx`.** Token utilities
   only (no colour literals, no raw palette shades — the canon guard enforces
   this), logical properties (`ms-/me-/ps-/pe-/start-/end-`, never physical), a
   `cursor-pointer` on every interactive part with the `disabled:cursor-not-allowed`
   pair, and `data-slot="<part>"` mirroring the kit's slot contract. Keep the
   controls `dress`/variant props only where a real consumer passes them.
   Anything that cannot be a utility (a `::after` shimmer, `@keyframes`) goes to
   the kit's styling layer — `styles/web-theme.css` for the bridge-level
   `sk-shimmer` keyframes. Re-export from `ui/index.ts`.
3. **Repoint consumers, one import at a time.** `@digithings/ui` (main barrel →
   controls copy) becomes `@digithings/ui/ui` (kit). Move the symbol into an
   existing `@digithings/ui/ui` import block in the file rather than adding a
   second import from the same module. Leave every other main-barrel import
   (Pager, TabStrip, Tooltip, …) where it is.
4. **Add a specimen entry.** `apps/reference/lib/specimen-inventory.ts` needs a
   `SPECIMENS` key for the new `ui/index.ts` module pointing at the canonical
   specimen file + a marker the file contains, or `specimens.test.ts` fails.
   Repoint the specimen's own import to `@digithings/ui/ui`.
5. **Pin the part in `ui.render.test.tsx`** (render + variant/pointer/RTL
   assertions) and, for pointer contracts that only exist in the DOM, in
   `ui.pointer.client.test.tsx`.
6. **Retired: the controls file.** This step existed because a promotion batch
   left its controls copy in place until a later retirement pass. Batch K3
   (#4306) deleted the layer, so there is no controls copy to keep and no
   promotion source left: author new parts directly in
   `packages/ui/src/ui/`.

## Promotion playbook (v2 — the #1414 epic shape)

New UI is born in the reference, promoted, then adopted — never built app-locally
(the guard's **family census** enforces this: a new app-local class family vs
`scripts/frontend_class_families.json` fails CI).

1. **Promote**: reference specimen → importable, props-driven primitive in
   `@digithings/ui`; the specimen becomes a thin consumer. Shape props against
   the real adoption targets (read the app code first).
2. **Wire**: exports in `web/src/index.ts`, a `package.json` exports entry per
   new css file, `@import` + `@source` lines in consumers, MANIFEST regen.
3. **Adopt**: apps swap markup onto the primitive. **API compatibility beats
   aesthetic purity** — where the reference dress and an app's shipped dress
   differ, give the primitive a variant/`dress` axis that reproduces the app's
   look EXACTLY (see the controls layer's `dress="reference"|"chat"` and the
   kit's `dress="chat"`), and
   record the reference-vs-app delta for a product ruling. Where a primitive
   can't express the app's behavior, do NOT force it — keep the local code and
   write the gap into a ledger (`digichat-ui/ARCHITECTURE.md`,
   `digichat/CONTROLS.md` are the precedents).

   **The kit wins wherever it covers the part.** `@digithings/ui/ui` is the
   canonical home for every part it ships — promote into `web/src/ui/` there,
   and prefer adding a `dress`/`skin` axis to the kit part over keeping a second
   app-local copy. The legacy controls layer was retired in batch K3 (#4306),
   so the kit is now the **only** primitive source. Deferred kit items are in
   #4306 (kit listbox/menu/radiogroup item parts; a kit `hideArrow` prop; the
   kit Table's `overflow-x-auto` vs sticky headers; SegmentedControl wrapping on
   very narrow viewports).

### The cascade-layering contract (bitten twice — read this)

Unlayered author CSS beats every `@layer`, including `utilities`. Therefore:

- **Package control/dress CSS**: single-class defaults (`.ctl-btn-chat { … }`)
  go in `@layer components` so call-site utilities (`p-8`, `text-[9px]`) can
  override them. State/structural rules (`:hover`, `[aria-*]`, `[data-size]`,
  descendant sizing, per-side geometry) stay **unlayered on purpose** — they
  must beat utilities, exactly like the shadcn variants they replace. Probe the
  compiled output when in doubt; specificity intuition lies here.
- **App imports of shared sheets** carrying resets or generic element rules:
  always `layer(components)` (`site.css` shipped `* { margin: 0 }` unlayered
  and silently killed every margin utility — twice).

## RTL — what consumers do (#4306)

The kit now ships logical properties, so an app opts into RTL with one prop,
not a restyle: wrap the tree in `<ThemeProvider dir="rtl">` (or a subtree in
`<DirectionProvider dir="rtl">`) from `@digithings/ui`. Nothing else changes —
LTR rendering is identical. Two rules for app code:

- Author **logical** directional utilities/properties only (`ms-/me-`, `ps-/pe-`,
  `start-/end-`, `text-start/end`, `border-s-/e-`, `rounded-ss/se/es/ee-`); a
  physical `ml-/left-/text-right/…` reintroduces the old bug and will re-break
  under `dir="rtl"`.
- If you truly need a physical edge (a device mock, an explicitly-physical
  `side`/placement prop), keep it physical **and** leave a comment saying why —
  see the exceptions documented in [ARCHITECTURE.md § RTL](ARCHITECTURE.md).

`rtl: true` is set in `components.json` (kit, reference, digichat); the canon
proof is the reference `/rtl` route.

## Pointer cursors — kit-level (#4306, phase 0.3)

Cursor is part of the part, not the page. Tailwind v4 preflight no longer puts
`cursor: pointer` on buttons, so every activatable kit part sets it itself:
`Button`, menu/select items and sub-triggers, `TabsTrigger`, `Switch`,
`Checkbox`, `CollapsibleTrigger`, `TableRow interactive` (opt-in — only some
rows activate), and the controls-layer pager/date-pager/segmented/menu items.
Disabled parts name `cursor: not-allowed` instead of inheriting the base
pointer.

Two rules for app code:

- **Do not add `cursor-*` utilities in an app.** `scripts/check_frontend_canon.py`
  flags `cursor-*` under `apps/**` (the reference gallery is exempt — it proves
  the canon, disabled and native-control specimens included). A missing cursor
  means the kit part is missing it: fix `packages/ui`, not the call site.
- **When a surface is genuinely app-specific** (a canvas pan gesture, a native
  `<details>/<summary>`, a custom timeline or tab-bar) and the kit owns no
  equivalent, keep the utility and add a `canon-allow: <reason>` comment on that
  line, so the exception is reviewed rather than silent.

## Debugging checklist (QA'ing an app against the canon)

- Utility "not applying" but present in compiled CSS → cascade layering
  (rule 2 above).
- Utility missing from compiled CSS entirely → missing `@source`, or a stale
  Turbopack cache: `rm -rf apps/<app>/.next` after switching branches.
- Livery/accent not changing inside a scope → something reintroduced a plain
  `@theme` block (rule 1).
- Money colors: `--up`/`--down` are fixed per theme in tokens.css (dark wears
  the digiquant phosphor) and must never follow a livery.

## App family CSS layering — what consumers do (#4306, workstream A)

The reference's own family sheets used to be unlayered, so they outranked kit
Tailwind utilities on a tie — a hazard whenever an app rebuild moved or
reordered imports. The rule for every app that keeps local family CSS:

- Put the sheet's **dress** in `@layer components` (i.e.
  `@layer components { … }`). Kit utilities live in `utilities`, which is
  ordered after `components`, so a call-site `p-4`/`text-[9px]` now wins over
  the family default without `!important`. This matches the kit's own sheet
  rule above.
- A rule that **must** beat a utility (a documented override, an external
  library's unlayered selector) stays **unlayered on purpose**, and says so
  inline — see `.sb-hint` in the reference `controls.css`, the one exception,
  which has to outrank the unlayered `.kbd` in `globals.css`.
- `@import` statements stay ahead of the layer block (CSS drops a late
  `@import`).
- A second Next root that themes vendor CSS (the reference `(chatbot)` shell
  around assistant-ui) keeps its own unlayered cascade; it is not a canon
  family sheet.

`apps/reference/lib/layering.test.ts` pins the wrapped set and the `.sb-hint`
exception, and the reference documents the convention in its README.
