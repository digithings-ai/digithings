# `@digithings/design/site` — redesign foundation

Shared, framework-free building blocks for the marketing sites (digithings.ai,
digiquant.io). Terminal-CLI / utilitarian aesthetic, light **and** dark, mobile,
reduced-motion safe. Consumes the `[data-theme]` semantic tokens in
[`../tokens.css`](../tokens.css).

## Theme contract

Pages opt in by setting `data-theme="light|dark"` on `<html>` **before paint**
(a pre-paint snippet in `<head>` avoids a flash), then loading `site.css`:

```html
<html data-theme="dark">
<head>
  <link rel="stylesheet" href="../design/tokens.css">
  <link rel="stylesheet" href="../design/site/site.css">
  <script>try{var s=localStorage.getItem('dt-theme');
    document.documentElement.setAttribute('data-theme',
      s||(matchMedia('(prefers-color-scheme: light)').matches?'light':'dark'))}catch(e){}</script>
</head>
```

`localStorage('dt-theme')` is the shared key — the Olympus dashboard mirrors it
on the same origin, so a chosen theme follows the user across surfaces.

## Modules (ES, import what you need)

| File | Export | Purpose |
|------|--------|---------|
| `site.css` | — | Component layer: nav, buttons, hero, sections, cards, **product frame**, **terminal block**, **connected graph**, pills/stage, principles, footer, `.reveal`. |
| `theme.js` | `initTheme()`, `applyTheme()` | Toggle (`#theme-toggle`), persistence, OS-follow, and theme-aware asset swap for any element with `data-src-dark` / `data-src-light` (QR mark, favicon). |
| `ui.js` | `initNav()`, `initCopy()` | Sticky-nav glass, mobile nav, and `[data-copy]` / `[data-copy-target]` copy buttons. |
| `reveal.js` | `initReveal()` | Scroll reveal for `.reveal` with per-grid stagger. |
| `terminal.js` | `typeTerminal(el, lines, opts)` | Typed terminal playback (the hero signature). Line kinds: `cmd`, `out`, `ok`, `mod`, `install`, `arrow`, `user`, `comment`, `gap`. Escapes content via `../html-escape.js`. |
| `graph.js` | `initGraph(root, {roles, names, defaultMod})` | Wires a connected graph authored in SVG (`.gnode[data-mod]`, `.edge[data-a][data-b]`): hover/focus trace, edge draw-in, live readout. |

All modules are progressive enhancement (a JS-off page is fully visible/static)
and honor `prefers-reduced-motion`.

## `ProductFrame` (CSS-only, EVOLUTION.md Phase B)

CQ-scaled ~800px UI embed for marketing pages — Graphite artboard / Cursor
product-screenshot pattern. No JS: markup two nested elements and let the
container query handle scaling.

```html
<div class="product-frame">
  <div class="product-frame__surface">
    <!-- screenshot <img>, terminal snippet, or arbitrary UI markup -->
  </div>
</div>
<p class="product-frame__caption">Fig. 1 — caption text</p>
```

| Class | Role |
|-------|------|
| `.product-frame` | Sizing wrapper — `max-width: var(--product-frame-w)` (800px), establishes a `container-type: inline-size` query container. |
| `.product-frame__surface` | Flat panel — `--surface` background, 1px `--hair` border, `--r-lg` radius. Font size scales in `cqi` (container-query inline units), clamped, so content shrinks with the *frame's* width rather than the viewport. |
| `.product-frame__caption` | Optional mono caption below the frame. |

**Atmosphere rule:** no mesh/glow/grain inside `.product-frame__surface` —
those effects belong to the page background around the frame, never on
the simulated UI itself (EVOLUTION.md §7, "atmospheric outside, surgical
inside").

Works unscoped in both `[data-theme="light"]` and `[data-theme="dark"]`. A
React wrapper is deferred until [#1195](https://github.com/digithings-ai/digithings/issues/1195)
(landing-primitive package location) resolves — the CSS classes are usable
directly from any JSX/TSX today.

## JSON-driven detail pages

`modules.html?mod=<id>` (digithings) and `subsystem.html?id=<id>` (digiquant)
render from `modules.json` / `subsystems.json` manifests — one template per
surface, no per-page duplication.
