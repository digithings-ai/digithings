# `@digithings/design/site` — shared CSS foundation

`site.css` is imported directly by `frontend/digithings-web/app/globals.css`
and `frontend/digiquant-web/app/globals.css` — the live Next.js marketing
sites (digithings.ai, digiquant.io). It supplies the primitives those apps'
React components still reach for by class name: `.wrap`, `.brand*`, buttons,
`.kicker`/`.prompt`, the standalone `.hero-title`, the terminal block
(`.term*`/`.tl-*`, consumed by `frontend/web/src/components/Terminal.tsx`),
sections, **ProductFrame**, `.principles`, and `.footer*`. Terminal-CLI /
utilitarian aesthetic, light **and** dark, reduced-motion safe. Consumes the
`[data-theme]` semantic tokens in [`../tokens.css`](../tokens.css).

Nav shell, hero layout, cards, pills/stage, the connected graph, and scroll
reveal are React components in `@digithings/web` (`chrome.tsx`, `DigiNav.tsx`
/`DqNav.tsx`, `graph.tsx`, Framer-Motion `Reveal`) — the vanilla-JS/CSS
equivalents that used to live here (`theme.js`, `ui.js`, `reveal.js`,
`terminal.js`, `graph.js`, plus their `.site-nav`/`.hero-grid`/`.card`/
`.pills`/`.stage`/`.gnode`/`.reveal` selectors) were removed in #1240 once an
import-graph audit confirmed neither live app referenced them.

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
on the same origin, so a chosen theme follows the user across surfaces. In the
Next.js apps this is handled by `ThemeProvider.tsx`/`ThemeToggle` in
`@digithings/web`, which reads/writes the same key.

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
