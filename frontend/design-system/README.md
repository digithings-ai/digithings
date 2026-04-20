# DigiThings Design System

The shared visual language for every DigiThings public surface:
`digithings.ai`, `digiquant.io`, and `chat.digithings.ai`. A simple,
utilitarian, dark-first aesthetic with per-module accent colors and a
cross-brand starfield signature.

This document is the authoritative reference. The canonical implementation
lives in `website/tokens.css` + `website/components.css`. Consumers vendor
or `@import` those files rather than redefining values.

---

## Tokens

All tokens are declared as CSS custom properties on `:root` in
`website/tokens.css`.

### Base palette (dark)

| Token                | Value       | Role                                  |
| -------------------- | ----------- | ------------------------------------- |
| `--bg-primary`       | `#121212`   | Page background (on top of starfield) |
| `--bg-secondary`     | `#0a0a0a`   | Panels, cards, nav                    |
| `--text-primary`     | `#e6e6e6`   | Default body text                     |
| `--text-secondary`   | `#a3a3a3`   | Muted text, captions                  |
| `--border-color`     | `#2a2a2a`   | Dividers, card borders                |
| `--fg`               | `#ffffff`   | Emphasis / highlight foreground       |

These match the dark-mode values in `digichat/src/app/globals.css`, so
DigiChat and the marketing site render at identical contrast.

### Typography

| Token                      | Value                                 |
| -------------------------- | ------------------------------------- |
| `--font-family`            | `'Inter', system-ui, …`               |
| `--font-family-mono`       | `'JetBrains Mono', 'Fira Code', …`    |
| `--font-size-h1`           | `clamp(3rem, 6vw, 4.5rem)`            |
| `--font-size-h2`           | `2.5rem`                              |
| `--font-size-h3`           | `1.5rem`                              |
| `--font-size-section-title`| `3.5rem`                              |
| `--font-size-body`         | `1.25rem`                             |
| `--font-size-small`        | `0.95rem`                             |
| `--font-size-xs`           | `0.85rem`                             |

### Spacing

Tokens `--space-1` … `--space-9` (0.25rem, 0.5rem, 1rem, 1.5rem, 2rem,
3rem, 4rem, 6rem, 8rem). `--spacing-base` (1.5rem) remains as the
container gutter.

### Radius

`--radius-sm: 6px`, `--radius-md: 8px`, `--radius-lg: 12px`.

### Motion

`--transition-speed: 0.8s`, `--transition-ease: cubic-bezier(0.2, 0.8, 0.2, 1)`.

---

## Accent palette

Each module gets one accent color. Surfaces scope `--accent` to a module's
value; component rules always reference `var(--accent)`.

| Module      | Token                   | Swatch                                                                                        | Hex       |
| ----------- | ----------------------- | --------------------------------------------------------------------------------------------- | --------- |
| DigiGraph   | `--accent-digigraph`    | ![](https://readme-swatches.vercel.app/e5b765?style=round)                                     | `#e5b765` |
| DigiQuant   | `--accent-digiquant`    | ![](https://readme-swatches.vercel.app/4fa37a?style=round)                                     | `#4fa37a` |
| Atlas       | `--accent-atlas`        | ![](https://readme-swatches.vercel.app/6fbf94?style=round)                                     | `#6fbf94` |
| Hermes      | `--accent-hermes`       | ![](https://readme-swatches.vercel.app/4a8f7b?style=round)                                     | `#4a8f7b` |
| Kairos      | `--accent-kairos`       | ![](https://readme-swatches.vercel.app/2f7a65?style=round)                                     | `#2f7a65` |
| DigiSearch  | `--accent-digisearch`   | ![](https://readme-swatches.vercel.app/5aa3c4?style=round)                                     | `#5aa3c4` |
| DigiChat    | `--accent-digichat`     | ![](https://readme-swatches.vercel.app/9d8fc9?style=round)                                     | `#9d8fc9` |
| DigiKey     | `--accent-digikey`      | ![](https://readme-swatches.vercel.app/d97a5a?style=round)                                     | `#d97a5a` |
| DigiSmith   | `--accent-digismith`    | ![](https://readme-swatches.vercel.app/6fa3a3?style=round)                                     | `#6fa3a3` |
| DigiClaw    | `--accent-digiclaw`     | ![](https://readme-swatches.vercel.app/b87840?style=round)                                     | `#b87840` |
| DigiBase    | `--accent-digibase`     | ![](https://readme-swatches.vercel.app/9ea0a5?style=round)                                     | `#9ea0a5` |
| DigiStore   | `--accent-digistore`    | ![](https://readme-swatches.vercel.app/7b7fc7?style=round)                                     | `#7b7fc7` |
| DigiLink    | `--accent-digilink`     | ![](https://readme-swatches.vercel.app/4fa39b?style=round)                                     | `#4fa39b` |

### Scoped override pattern

```html
<section class="accent-digiquant">
  <!-- any `.module-card`, `.flow-node.highlight`, etc. inside resolves
       var(--accent) to #4fa37a -->
</section>
```

Or directly in CSS:

```css
.my-section { --accent: var(--accent-digisearch); }
```

---

## Component primitives

Primitives live in `website/components.css` and take their visual values
from tokens.

### `.nav`

```html
<nav class="nav">
  <div class="nav-container">
    <div class="logo">
      <img src="assets/qrw.svg" class="logo-svg" alt="digithings">
      <span class="logo-text">digithings</span>
    </div>
    <div class="nav-links">
      <a class="nav-link" href="#">Docs</a>
    </div>
  </div>
</nav>
```

### `.hero`

```html
<header class="hero">
  <div class="hero-content">
    <div class="hero-text">
      <h1 class="logo-title">digithings</h1>
      <p class="hero-subtitle">Tagline</p>
      <p class="description">Short pitch.</p>
    </div>
    <div class="hero-visual"><!-- terminal or chat-embed --></div>
  </div>
</header>
```

### `.module-card`

Scopes `--accent` via a surrounding `.accent-<module>` class. The left
border + heading pick up the module color automatically.

```html
<div class="accent-digiquant">
  <article class="module-card">
    <h3>DigiQuant</h3>
    <p>NautilusTrader-powered quant engine.</p>
  </article>
</div>
```

### `.feature-grid`

Two-column grid, collapses to one column on mobile.

```html
<section class="feature-grid">
  <div class="info-block"><h3>Open core</h3><p>…</p></div>
  <div class="info-block"><h3>Self-hostable</h3><p>…</p></div>
</section>
```

### `.terminal`

```html
<div class="terminal">
  <div class="terminal-header">
    <span class="dot red"></span>
    <span class="dot yellow"></span>
    <span class="dot green"></span>
    <span class="terminal-title">agent_init.py</span>
  </div>
  <div class="terminal-body">
    <pre><code id="typewriter-code"></code><span class="cursor">_</span></pre>
  </div>
</div>
```

### `.chat-embed-slot`

Drop-in mount point for the DigiChat widget. The accent stripe at the top
picks up the surrounding `--accent`.

```html
<div class="accent-digichat">
  <div class="chat-embed-slot">
    <iframe src="https://chat.digithings.ai/embed?session=demo"
            title="DigiChat"></iframe>
  </div>
</div>
```

### `.footer`

```html
<footer class="footer">
  <div class="container">
    <p>&copy; 2026 digithings AI. Open Core.</p>
  </div>
</footer>
```

---

## Starfield API

`website/starfield.js`:

```js
import { initStarfield } from './starfield.js';

const ctl = initStarfield({
  canvasId: 'network-canvas', // required — id of a <canvas>
  density: 180,               // optional; defaults: 180 desktop / 80 mobile
});
// ctl.stop() cancels the animation and detaches listeners.
```

Behavior:
- Pauses when the tab is hidden (`visibilitychange`).
- Resizes on `window.resize`.
- On screens ≤ 480px the default density drops to 80.

---

## Scroll-trigger API

`website/scroll-trigger.js`:

```js
import { initScrollTrigger } from './scroll-trigger.js';

initScrollTrigger({
  selector: '.scroll-trigger',      // elements that want progress
  revealThreshold: 0.85,            // 0..1; higher = reveals sooner
  activateSelector: '.timeline-event', // optional — adds .active past line
  activationLineRatio: 0.7,         // where the active line sits (0=top,1=bottom)
  onProgress: (el, progress, rect) => { /* optional hook */ },
});
```

Each matching element receives `--scroll: 0..1` on every frame. CSS
consumes it — see the `data-direction="bottom|left|right|zoom"` rules in
`components.css`.

---

## Adoption guide

### `digichat/` (Next.js)

DigiChat already uses the same base palette in `digichat/src/app/globals.css`.
To formally adopt the design system:

1. Vendor the tokens. Add a make target that copies `website/tokens.css`
   into `digichat/src/app/tokens.css`:

   ```make
   sync-tokens:
   	cp website/tokens.css digichat/src/app/tokens.css
   ```

2. Import it from `globals.css`:

   ```css
   @import './tokens.css';
   ```

3. Replace any hardcoded hex values in Next.js components with
   `var(--bg-secondary)`, `var(--accent)`, etc. Scope DigiChat surfaces
   with the `.accent-digichat` class at the root.

Do not import the full `components.css` into DigiChat — its React
components have their own primitives. Tokens alone keep the two surfaces
visually coherent without forcing layout collisions.

### `website/digiquant/` (future PR 3)

DigiQuant.io will be a subdirectory of the main site (or a sibling static
site sharing the same CSS). It will:

1. `@import './tokens.css'` and `@import './components.css'` directly
   (no vendoring — same deployment).
2. Wrap the page root in `<body class="accent-digiquant">` so all
   `var(--accent)` references resolve to the DigiQuant color.
3. Reuse `.hero`, `.module-card`, `.feature-grid`, `.chat-embed-slot`,
   `.terminal` without overrides.
4. Load the same `starfield.js` for cross-brand continuity.

---

## Non-goals

- No light mode yet. The palette is dark-first; a light variant is a
  future PR with tokens overridden inside `@media (prefers-color-scheme: light)`.
- No component JS framework. Primitives are class-based CSS; interactivity
  is limited to the three vanilla-JS modules above.
- Confidential internal projects are out of scope. This design system
  documents only public-facing surfaces.
