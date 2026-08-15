# The digiweb canon — adoption playbook

Every frontend surface consumes the design system the same way. This is the
playbook that migrated all five apps (#1399, 2026-07) and the contract the
**frontend canon guard** (`scripts/check_frontend_canon.py`) enforces going
forward. The guard runs as a dedicated **unconditional** `frontend-canon` job
in `ci.yml` on every PR/push (#1434) — it scans the whole `frontend/` tree via
`git ls-files`, not just the diff, so it must not be path-gated — and also runs
(redundantly) inside the web/olympus/digichat test jobs.

## The wiring (every app, in this order)

```css
@import "tailwindcss";
@import "@digithings/design/tokens.css";
@import "@digithings/design/site/site.css" layer(components); /* if used — see below */
@import "@digithings/web/styles/web-theme.css";               /* THE bridge */
@import "@digithings/web/styles/nav-shell.css";               /* if using NavShell */
@import "@digithings/web/styles/docs.css";                    /* if using the docs family */

/* Tailwind never scans package sources — point it at the shared components you use: */
@source "../../digiweb/web/src/components/NavShell.tsx";
@source "../../digiweb/web/src/components/docs";
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
   #1419), and `finance-tearsheet.css` (#1463 — its unlayered portion includes
   the ENTIRE `@media print` grammar, the tearsheet family's differentiator).
   Wrapping those in `layer(…)` demotes their state rules and breaks
   digichat's rendered-look parity (or, for the tearsheet, the PDF export).
3. **`@source` any package component you render.** Without it the shared
   component's utilities are never generated — the failure is silent (its
   own CSS file masks most of it).

Theming: `data-theme` on `<html>` is authoritative (shared `ThemeProvider` +
`themeInitScript` from `@digithings/web`). If an app needs `.dark`/`.light`
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

**Concrete colors are sanctioned only in:** `olympus/lib/chart-colors.ts`
(categorical/benchmark hues), tenant embed accents, SSR `theme-color` metas
(commented), canvas scenes, print pins, and the reference livery swatch
table — the guard's ALLOWLIST. Anything else needs a
`canon-allow: <reason>` comment on the line, and a reason that survives
review.

## Shared primitives first

Before writing new UI, check `frontend/digiweb/MANIFEST.json` (90 components,
14 families) and `@digithings/web` exports: NavShell, Footer/Colophon,
DocsLayout/CodeTabs/EndpointDoc, Pricing/PricingMatrix, NumberedStages,
PerfMetrics/StatCounter, TerminalManifest, the chat family (ChatTranscript/
ChatMessage/ChatMarkdown/ChatToolCall/…), the controls layer (Button/Badge/
Card/Input/Label/Avatar/DropdownMenu/Sheet/Tooltip/Collapsible on the `dress`
axis), Terminal, Emblem/StackRow, ModuleCard, Reveal/Stagger/HeroEntrance,
useScrollyFeatures/ScrollyRail. Motion always via `m` under `MotionProvider`
(LazyMotion `domAnimation` `strict` — a raw `motion.*` element creator throws).
The reference app (port 4013) is the live catalog; `/digiweb` is the agent
entry point.

## Promotion playbook (v2 — the #1414 epic shape)

New UI is born in the reference, promoted, then adopted — never built app-locally
(the guard's **family census** enforces this: a new app-local class family vs
`scripts/frontend_class_families.json` fails CI).

1. **Promote**: reference specimen → importable, props-driven primitive in
   `@digithings/web`; the specimen becomes a thin consumer. Shape props against
   the real adoption targets (read the app code first).
2. **Wire**: exports in `web/src/index.ts`, a `package.json` exports entry per
   new css file, `@import` + `@source` lines in consumers, MANIFEST regen.
3. **Adopt**: apps swap markup onto the primitive. **API compatibility beats
   aesthetic purity** — where the reference dress and an app's shipped dress
   differ, give the primitive a variant/`dress` axis that reproduces the app's
   look EXACTLY (see the controls layer's `dress="reference"|"chat"`), and
   record the reference-vs-app delta for a product ruling. Where a primitive
   can't express the app's behavior, do NOT force it — keep the local code and
   write the gap into a ledger (`digichat-ui/ARCHITECTURE.md`,
   `digichat/CONTROLS.md` are the precedents).

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

## Debugging checklist (QA'ing an app against the canon)

- Utility "not applying" but present in compiled CSS → cascade layering
  (rule 2 above).
- Utility missing from compiled CSS entirely → missing `@source`, or a stale
  Turbopack cache: `rm -rf frontend/<app>/.next` after switching branches.
- Livery/accent not changing inside a scope → something reintroduced a plain
  `@theme` block (rule 1).
- Money colors: `--up`/`--down` are fixed per theme in tokens.css (dark wears
  the digiquant phosphor) and must never follow a livery.
