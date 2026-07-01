# DigiThings Design System

The shared visual language for every DigiThings public surface:
`digithings.ai`, `digiquant.io`, and `chat.digithings.ai`. A simple,
utilitarian, dark-first aesthetic with per-module accent colors and a
cross-brand starfield signature.

This document is the authoritative reference. The canonical implementation
lives in `frontend/design/tokens.css` + `frontend/design/components.css`,
packaged as the `@digithings/design` npm workspace. Consumers
import the package (or reference the files via relative paths for the
static sites).

**Strategy & external references:** [`EVOLUTION.md`](EVOLUTION.md) synthesizes
our direction with deep scans of [Graphite](references/graphite.com.md),
[Cursor](references/cursor.com.md), and [x.ai](references/x.ai.md) — use it
before major landing or dashboard work. **Deep audits:** [`references/scans/`](references/scans/INDEX.md). Index: [`references/README.md`](references/README.md).

See [ADR-0009 — Frontend umbrella](../../docs/adr/0009-frontend-umbrella.md)
for the layout rationale.

## Consumers

- [`frontend/digithings/`](../digithings/README.md) — digithings.ai
- [`frontend/digiquant/`](../digiquant/README.md) — digiquant.io
- `frontend/digichat/` — chat.digithings.ai (Next.js; workspace dep, token adoption tracked by #240)
- `frontend/olympus/` — workspace dep only; token adoption deferred

---

## Tokens

All tokens are declared as CSS custom properties on `:root` in
`frontend/design/tokens.css`.

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

**Canonical fonts (all surfaces), per [`EVOLUTION.md` §4](EVOLUTION.md#4-typography-direction):**

| Role                    | Font                             | Weight  | Token(s)                       |
| ------------------------ | -------------------------------- | ------- | ------------------------------- |
| Marketing hero display    | Fraunces *or* Instrument Serif   | 400     | `--font-display`                |
| Dashboard display         | Instrument Serif                 | 400     | `--font-display`                |
| Body                      | Geist Sans                       | 400–500 | `--font-sans`                   |
| Labels / eyebrows         | Geist Mono, uppercase, tracked   | 400     | `--font-mono`                   |
| Data / metrics            | Geist Mono, tabular nums         | 400–600 | `--font-mono` + `qn-metric`     |
| Code                      | Geist Mono                       | 400     | `--font-mono`                   |

`--font-sans`, `--font-mono`, `--font-display` are declared in the
`[data-theme]` redesign layer of `tokens.css` and are already loaded in
every Next.js app. **Rule:** serif is display-only on marketing pages;
dashboards and twelve-x use sans + mono exclusively.

**Deprecated:** `--font-family` (`'Inter', …`) and `--font-family-mono`
(`'JetBrains Mono', …`) are the legacy `:root` tokens — still resolved
by pages that haven't adopted `[data-theme]` yet, but no longer the
documented default. New and migrating components should reference
`--font-sans` / `--font-mono` / `--font-display` instead of these two.

| Token (legacy, deprecated) | Value                                 |
| --------------------------- | ------------------------------------- |
| `--font-family`             | `'Inter', system-ui, …`               |
| `--font-family-mono`        | `'JetBrains Mono', 'Fira Code', …`    |

| Token                      | Value                                 |
| -------------------------- | ------------------------------------- |
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

Primitives live in `frontend/design/components.css` and take their visual values
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

`frontend/design/starfield.js`:

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

`frontend/design/scroll-trigger.js`:

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

1. Vendor the tokens. Add a make target that copies `frontend/design/tokens.css`
   into `digichat/src/app/tokens.css`:

   ```make
   sync-tokens:
   	cp frontend/design/tokens.css frontend/digichat/src/app/tokens.css
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

### `frontend/digiquant/`

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
  is limited to the vanilla-JS modules documented above.
- Confidential internal projects are out of scope. This design system
  documents only public-facing surfaces.

---

## Extended primitives

Five additional primitives harvested from the landing-page exploration live
alongside the base tokens + starfield. Each ships a CSS file, an ESM JS
module, and (where useful) a `types.d.ts`. See the smoke-test page at
[`smoke/index.html`](./smoke/index.html) for a minimal reviewer poke-surface
for all five at once.

### `living-architecture/` — interactive SVG diagram engine

```js
import { initDiagram } from '@digithings/design/living-architecture';
import '@digithings/design/living-architecture/styles.css';

const { camera, focus, reset, destroy } = initDiagram({
  hostId: 'arch-host',
  svgId: 'arch-svg',
  nodes: [
    { id: 'a', label: 'Alpha', x: 300, y: 360, accentVar: '--accent-digigraph', group: 'core' },
    { id: 'b', label: 'Beta',  x: 600, y: 360, accentVar: '--accent-digiquant', group: 'core' },
  ],
  edges: [{ source: 'a', target: 'b' }],
  onNodeFocus: (id) => { /* consumer side-effect */ },
});
```

| API                     | Notes                                                                 |
| ----------------------- | --------------------------------------------------------------------- |
| `initDiagram(opts)`     | Builds edges + nodes, returns `{ camera, focus, reset, destroy }`.    |
| `camera.focus(id)`      | 600ms viewBox tween to a node.                                        |
| `camera.reset()`        | Tween back to the SVG's initial `viewBox`.                            |
| `camera.zoomTo(bbox)`   | Tween to an arbitrary `[x, y, w, h]`.                                 |
| `onNodeFocus(id)`       | Fires on node click / Enter / arrow-nav.                              |
| Keyboard (host focused) | ←/→ cycle `group === "core"` nodes; ↑ reset; ↓ focus current/first core; Tab/Shift+Tab walks all nodes (a11y); Enter activates; Esc resets. |
| Zoom-out button         | Auto-injected, top-right of host, calls `camera.reset()`.             |

Static fallback: `fallback-diagram.svg` in the same folder — inline it with
`<object data="…/fallback-diagram.svg">` or render it inside the host
SVG before hydrating; JS will clear it on `initDiagram`.

**Reduced motion**: edge flow animation disabled, viewBox snaps instantly
on `focus` / `reset` / `zoomTo`, bloom transitions removed.

### `terminal/` — scripted terminal widget

```js
import { initTerminal } from '@digithings/design/terminal';
import '@digithings/design/terminal/styles.css';

initTerminal({
  elementId: 'term',
  lines: [
    { kind: 'prompt',    text: 'digithings init' },
    { kind: 'output',    text: 'ready.' },
    { kind: 'comment',   text: 'all services ok' },
    { kind: 'tool-call', text: 'digigraph.route' },
    { kind: 'output',    text: 'const x = 1;', lang: 'js' },
  ],
  speed: 'normal',
  onReady: () => {},
});
```

| Line `kind`   | Rendering                                                   |
| ------------- | ----------------------------------------------------------- |
| `prompt`      | Mono `>` marker, neutral body.                              |
| `output`      | Default body.                                               |
| `comment`     | `//` marker in a muted accent.                              |
| `tool-call`   | Body rendered as a chip.                                    |

Compose multiple terminals side-by-side inside `<div class="terminal-group">`
(no inter-widget coordination needed). `speed` is `"fast" | "normal" | "slow"`
or a custom per-character base in milliseconds. Optional `lang` hint
(`js|ts|tsx|py|sh|json`) swaps in naïve highlighted markup after the keystroke
stream completes — this is decorative, not a real tokenizer.

**Reduced motion**: no typewriter, no cursor blink; text appears instantly.

### `typography-motion/` — variable-weight + tracking shift

Declarative (preferred for hero headlines):

```html
<link rel="stylesheet" href="…/typography-motion/styles.css" />
<h1 class="tws-weight-shift"
    data-weight-from="200" data-weight-to="700">Settle me on scroll.</h1>

<script type="module">
  import { initTypographyMotion } from '@digithings/design/typography-motion';
  initTypographyMotion();
</script>
```

Imperative:

```js
import { attachWeightShift, attachTrackingShift } from '@digithings/design/typography-motion';
const h = attachWeightShift(el, { from: 200, to: 700, scrollStart: 0, scrollEnd: 400 });
// h.detach() when the element leaves the tree
```

`.tws-weight-shift` drives `font-variation-settings: "wght" N` plus a matching
`font-weight`. `.tws-tracking-shift` drives `letter-spacing` in `em` units.
Both bind to scroll-Y progress across `[scrollStart, scrollEnd]`.

**Reduced motion**: element snaps to the `to` value immediately; no scroll
listener attached.

### `quant-native/` — blueprint grid, ticker, metric + chart utilities

```js
import { initTicker } from '@digithings/design/quant-native';
import '@digithings/design/quant-native/styles.css';

initTicker({
  elementId: 'ticker',
  symbols: [
    { sym: 'ATLAS',  price: '184.22', delta: '+0.42%' },
    { sym: 'KAIROS', price: '342.07', delta: '-0.18%' },
  ],
  cadence: 60,  // px/sec
});
```

| Class / API           | Purpose                                                    |
| --------------------- | ---------------------------------------------------------- |
| `.qn-blueprint-bg`    | Horizontal-rule pattern at ~2% opacity; apply to any block. |
| `.qn-ticker`          | Ribbon container (JS-driven `translateX`, pause on hover). |
| `.qn-metric`          | `font-feature-settings: "tnum"`, mono, right-aligned.      |
| `.qn-chart-frame`     | Hairline border + `--bg-primary` fill; wraps an SVG chart. |
| `.qn-up` / `.qn-down` | Muted emerald (digiquant accent) / muted copper (digiclaw accent). |

Directional color is intentionally muted — never Bloomberg-bright red/green.

**Reduced motion**: ticker track is pinned at `translateX(0)` with left
padding; up/down colors unchanged.

### `app-shell-terminal/` — Claude-Code-style app chrome

```js
import { initAppShell, SlashCommandRegistry }
  from '@digithings/design/app-shell-terminal';
import '@digithings/design/app-shell-terminal/styles.css';

const registry = new SlashCommandRegistry();
registry.register('route', {
  description: 'Route a prompt to a specialist',
  handler: (args) => console.log('route:', args.join(' ')),
});

const shell = initAppShell({
  hostId: 'app',
  title: 'digichat',
  sidebarSlot: '<div>history · settings · /commands</div>',
  mainSlot:    '<div id="chat"></div>',
  slashCommands: registry,
  onSubmit: (text) => { /* non-slash input */ },
});
```

| Feature                    | Behavior                                                        |
| -------------------------- | --------------------------------------------------------------- |
| Sidebar                    | `aria-expanded` collapsible; `Cmd+/` toggles.                   |
| Top bar                    | Mono title + metadata strip.                                    |
| Input bar                  | Terminal-style `>` marker; auto-grows to 200px; `Enter` submits, `Shift+Enter` newline. |
| Slash commands             | `registry.register/parse/dispatch`. Built-ins: `/help`, `/clear`. |
| `Cmd+K`                    | Opens a `role="dialog"` palette with focus-trap + filter.       |
| Slash-command reference    | Use `<span class="shell-cmd-ref">/name</span>` inside the sidebar. |

**Reduced motion**: no sidebar / palette transitions; everything resolves
instantly.

### Smoke-test page

Run any static server from `frontend/`:

```bash
cd frontend && python3 -m http.server 8765
open http://localhost:8765/design/smoke/
```

The page renders one minimal instance of each primitive for review.
