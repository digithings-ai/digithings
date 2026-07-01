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
| `site.css` | — | Component layer: nav, buttons, hero, sections, cards, **terminal block**, **connected graph**, pills/stage, principles, footer, `.reveal`. |
| `theme.js` | `initTheme()`, `applyTheme()` | Toggle (`#theme-toggle`), persistence, OS-follow, and theme-aware asset swap for any element with `data-src-dark` / `data-src-light` (QR mark, favicon). |
| `ui.js` | `initNav()`, `initCopy()` | Sticky-nav glass, mobile nav, and `[data-copy]` / `[data-copy-target]` copy buttons. |
| `reveal.js` | `initReveal()` | Scroll reveal for `.reveal` with per-grid stagger. |
| `terminal.js` | `typeTerminal(el, lines, opts)` | Typed terminal playback (the hero signature). Line kinds: `cmd`, `out`, `ok`, `mod`, `install`, `arrow`, `user`, `comment`, `gap`. Escapes content via `../html-escape.js`. |
| `graph.js` | `initGraph(root, {roles, names, defaultMod})` | Wires a connected graph authored in SVG (`.gnode[data-mod]`, `.edge[data-a][data-b]`): hover/focus trace, edge draw-in, live readout. |

All modules are progressive enhancement (a JS-off page is fully visible/static)
and honor `prefers-reduced-motion`.

## JSON-driven detail pages

`modules.html?mod=<id>` (digithings) and `subsystem.html?id=<id>` (digiquant)
render from `modules.json` / `subsystems.json` manifests — one template per
surface, no per-page duplication.
