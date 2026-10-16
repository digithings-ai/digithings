# digithings Design System

The shared visual language for every digithings public surface:
`digithings.ai`, `digiquant.io`, and `digithings.ai/chat`. A simple,
utilitarian, dark-first aesthetic with per-module accent colors.

This document is the authoritative reference. The canonical implementation
lives in `packages/design/tokens.css` and `packages/design/site/site.css`,
packaged as the `@digithings/design` npm workspace. Consumers
import the package (or reference the files via relative paths for the
static sites).

**Strategy:** [`EVOLUTION.md`](EVOLUTION.md) is the historical ledger. The competitor
scans, design mine, landing demos, and the static spec/smoke pages were removed
so the next design reference can be built in digiweb (`apps/reference`) instead
of extended here. **Copy & IA:** [`COPY_GUIDE.md`](COPY_GUIDE.md).

See [ADR-0009 — Frontend umbrella](../../docs/adr/0009-frontend-umbrella.md)
for the layout rationale.

## Consumers

- `apps/digithings-web/` — digithings.ai (Next.js; imports `tokens.css` + `site/site.css` directly)
- `apps/digiquant-web/` — digiquant.io (Next.js; imports `tokens.css` + `site/site.css` directly)
- `apps/digichat/` — digithings.ai/chat (Next.js; workspace dep, token adoption tracked by #240)
- `apps/dashboard/` — token adopter: imports `tokens.css`, the `@digithings/ui` `web-theme.css` bridge and ~15 kit sheets

---

## Tokens

All tokens are declared as CSS custom properties on `:root` in
`packages/design/tokens.css`.

### Base palette (dark)

| Token                | Value       | Role                                  |
| -------------------- | ----------- | ------------------------------------- |
| `--bg-primary`       | `#121212`   | Page background |
| `--bg-secondary`     | `#0a0a0a`   | Panels, cards, nav                    |
| `--text-primary`     | `#e6e6e6`   | Default body text                     |
| `--text-secondary`   | `#a3a3a3`   | Muted text, captions                  |
| `--border-color`     | `#2a2a2a`   | Dividers, card borders                |
| `--fg`               | `#ffffff`   | Emphasis / highlight foreground       |

These match the dark-mode values in `digichat/src/app/globals.css`, so
digichat and the marketing site render at identical contrast.

### Typography

**Canonical fonts (all surfaces), utilitarian v0.1 — see [`BLEND.md`](BLEND.md):**

| Role                    | Font                             | Weight  | Token(s)                       |
| ------------------------ | -------------------------------- | ------- | ------------------------------- |
| Display / claims          | Geist Mono                       | 400–500 | `--font-display`                |
| Body                      | Geist Mono                       | 400     | `--font-sans`                   |
| Chrome / labels           | Geist Mono, uppercase, tracked   | 400     | `--font-mono`                   |
| Data / metrics            | Geist Mono, tabular nums         | 400–500 | `--font-mono` + `qn-metric`     |
| Code                      | Geist Mono                       | 400     | `--font-mono`                   |

`--font-sans`, `--font-mono`, `--font-display` are declared in the
`[data-theme]` redesign layer of `tokens.css` and all default to the Geist
Mono stack. **Rule:** one mono voice; hierarchy is size and tracking, not a
second face. Serif (`serif-legacy` / Instrument Serif or Fraunces) is an
escape hatch for rare editorial moments — quotes, legal names — never the
default marketing H1. Product apps that still override with Fraunces are
Phase 2/3 debt ([`ROLLOUT.md`](ROLLOUT.md)).

**Deprecated:** `--font-family` and `--font-family-mono` are the legacy
`:root` tokens. Unthemed pages still resolve `--font-family` to Inter
(a sans escape hatch). Under `[data-theme]` they follow `--font-sans` /
`--font-mono` (Geist Mono). New components should reference
`--font-sans` / `--font-mono` / `--font-display`.

| Token (legacy, deprecated) | Unthemed `:root`                      | Themed `[data-theme]`     |
| --------------------------- | ------------------------------------- | ------------------------- |
| `--font-family`             | `var(--font-stack-sans)`              | `var(--font-sans)`        |
| `--font-family-mono`        | `var(--font-stack-mono)`              | `var(--font-mono)`        |

### Fonts per surface

`tokens.css` builds the **stacks**, each app supplies the **faces**. One file
per app calls `next/font`; nothing else in a surface may load a face or name a
font family.

```
apps/<app>/app/fonts.ts   →   --font-sans-face, --font-mono-face   (next/font)
tokens.css                →   --font-stack-sans / -mono / -display  (face + fallbacks)
                             --font-sans / --font-mono / --font-display  (read by CSS)
```

`--font-stack-mono` is `var(--font-mono-face, "Geist Mono"), ui-monospace,
"SF Mono", Menlo, Consolas, "DejaVu Sans Mono", "Segoe UI Symbol",
monospace`. The fallback chain is required, not decoration: Geist Mono has no
U+25B8 / U+25BE (nav triangles) and no U+2318 (the command key), so those
glyphs come from a later family in the row.

**Swapping a surface's mono is one line.** Change the `mono` loader in that
surface's config:

| Surface | Config | Line to edit |
| --- | --- | --- |
| dashboard (`apps/dashboard`) | `app/fonts.ts:17` | the only `Geist_Mono({…})` call (mono only; this surface has no sans loader) |
| digiquant.io (`apps/digiquant-web`) | `app/fonts.ts:24` | the `Geist_Mono({… variable: "--font-mono-face" …})` call |
| digithings.ai (`apps/digithings-web`) | no `fonts.ts` yet — faces load inline in the layout (pending port, same as DigiChat below) | — |
| DigiChat (`apps/digichat`), both `(digichat)` and `(baseline)` layouts | no `fonts.ts` yet — faces load inline in the layouts (pending port) | — |
| tearsheet (client-facing HTML) | `digiquant/src/digiquant/fonts.py:21` | `MONO_FONT_FAMILY` — Python, not `next/font`: `MONO_FONT_STACK` and `GOOGLE_FONTS_HREF` follow it, and the page CSS, both Plotly layouts and `charts/trades.py` read the stack |

To try another face, change one loader (and its import) in one `fonts.ts`,
screenshot it, then revert:

```diff
-import { Geist_Mono } from "next/font/google";
+import { <Other_Mono_Face> } from "next/font/google";
-export const mono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono-face", display: "swap" });
+export const mono = <Other_Mono_Face>({ subsets: ["latin"], variable: "--font-mono-face", display: "swap" });
```

Nothing else changes: the variable name is generic, so every consumer of
`--font-mono` follows. No surface *config* loads Inter anymore (DIG-2695);
the pending-port surfaces (`apps/digichat`, `apps/digithings-web`) still load
their faces inline in their layouts until their port is redone.

Out of scope for this system: `apps/reference/**` and
`apps/digichat/reference/**` are type-specimen galleries that deliberately
name alternatives.

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

**Redesign layer (`[data-theme]`, EVOLUTION.md §5):** `--wrap: 1180px`
(default container), `--wrap-wide: 1280px` (marketing/bento sections),
`--product-frame-w: 800px` (Graphite/Cursor-style CQ-scaled UI embed),
`--section-y: clamp(4rem, 8vw, 7rem)` / `--section-y-tight:
clamp(2.5rem, 5vw, 4rem)` (section vertical rhythm).

### Radius

`--radius-sm`, `--radius-md`, and `--radius-lg` are `0` (`tokens.css`). True circles
may still use `999px` locally. That is geometry, not chrome.

### Motion

`--transition-speed: 0.8s`, `--transition-ease: cubic-bezier(0.2, 0.8, 0.2, 1)`.

**Redesign layer (`[data-theme]`, EVOLUTION.md §5):** `--ease-glide:
cubic-bezier(0.22, 1, 0.36, 1)` (same curve as `--ease`, named
separately for reveal-on-scroll consumers per the primitives in Phase
B), `--duration-reveal: 0.6s`, `--duration-hover: 0.18s`.

---

## Accent palette

Each module gets one accent color. Surfaces scope `--accent` to a module's
value; component rules always reference `var(--accent)`.

| Module      | Token                   | Swatch                                                                                        | Hex       |
| ----------- | ----------------------- | --------------------------------------------------------------------------------------------- | --------- |
| digigraph   | `--accent-digigraph`    | ![](https://readme-swatches.vercel.app/e5b765?style=round)                                     | `#e5b765` |
| digiquant   | `--accent-digiquant`    | ![](https://readme-swatches.vercel.app/3dd6c4?style=round)                                     | `#3dd6c4` |
| Research    | `--accent-research`        | ![](https://readme-swatches.vercel.app/6fbf94?style=round)                                     | `#6fbf94` |
| Portfolio   | `--accent-portfolio`       | ![](https://readme-swatches.vercel.app/4a8f7b?style=round)                                     | `#4a8f7b` |
| Execution   | `--accent-execution`       | ![](https://readme-swatches.vercel.app/2f7a65?style=round)                                     | `#2f7a65` |
| digisearch  | `--accent-digisearch`   | ![](https://readme-swatches.vercel.app/5aa3c4?style=round)                                     | `#5aa3c4` |
| digichat    | `--accent-digichat`     | ![](https://readme-swatches.vercel.app/e2708a?style=round)                                     | `#e2708a` |
| digikey     | `--accent-digikey`      | ![](https://readme-swatches.vercel.app/d97a5a?style=round)                                     | `#d97a5a` |
| digitrace   | `--accent-digitrace`    | ![](https://readme-swatches.vercel.app/6fa3a3?style=round)                                     | `#6fa3a3` |
| digiclaw    | `--accent-digiclaw`     | ![](https://readme-swatches.vercel.app/b87840?style=round)                                     | `#b87840` |
| digibase    | `--accent-digibase`     | ![](https://readme-swatches.vercel.app/9ea0a5?style=round)                                     | `#9ea0a5` |
| digistore   | `--accent-digistore`    | ![](https://readme-swatches.vercel.app/7b7fc7?style=round)                                     | `#7b7fc7` |
| digilink    | `--accent-digilink`     | ![](https://readme-swatches.vercel.app/4fa39b?style=round)                                     | `#4fa39b` |
| digivault   | `--accent-digivault`    | ![](https://readme-swatches.vercel.app/9d8fc9?style=round)                                     | `#9d8fc9` |

### Scoped override pattern

```html
<section class="accent-digiquant">
  <!-- any `.module-card`, `.flow-node.highlight`, etc. inside resolves
       var(--accent) to #3dd6c4 -->
</section>
```

Or directly in CSS:

```css
.my-section { --accent: var(--accent-digisearch); }
```

---

## Component primitives

The legacy `components.css` sheet (global reset plus `.nav`, `.hero`,
`.module-card`, `.terminal`, and the `--scroll` direction rules) had no
importer. It was removed. Live primitives are `site/site.css`, consumed by
digithings.ai and digiquant.io, and the React kit in `@digithings/ui`.

The vanilla `starfield.js` and `typewriter.js` modules had no importer either
(`apps/dashboard` only declared the starfield module). They were removed.
`scroll-trigger.js` left in #5692. Do not revive them; the next design
reference is `apps/reference`.

---
## Non-goals

- Light and dark both ship under `[data-theme]` in `tokens.css`. The legacy
  `:root` block above that layer stays dark-first for pages that have not migrated.
- No component JS framework here. React components live in `@digithings/ui`;
  this package keeps tokens and the few vanilla-JS modules documented below.
- Confidential internal projects are out of scope. This design system
  documents only public-facing surfaces.

---

## Extended primitives

Two primitives that live surfaces still import sit alongside the tokens.
Each ships a CSS file and an ESM JS module. The static smoke page
and the HTML spec were removed with the old design reference. Live specimens
belong in `apps/reference`.

### `quant-native/` — blueprint grid, ticker, metric + chart utilities

```js
import { initTicker } from '@digithings/design/quant-native';
import '@digithings/design/quant-native/styles.css';

initTicker({
  elementId: 'ticker',
  symbols: [
    { sym: 'RESEARCH',  price: '184.22', delta: '+0.42%' },
    { sym: 'EXECUTION', price: '342.07', delta: '-0.18%' },
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

## Documents

Canon-styled, print-ready document templates (HTML → PDF, self-contained, no
build step).

### `invoice/` — invoice template

A utilitarian **monochrome** single-page invoice — Geist Mono for claim, body,
and chrome, hairline rules, zero radius, no glass. Line items read like an
AI-services invoice (deliverable + compact scope), with an optional second-page
delivery breakdown. Fill the `[bracketed]` placeholders, then
`chromium --headless --print-to-pdf=invoice.pdf index.html`. See
[`invoice/README.md`](./invoice/README.md).

### `quote/` — quote / statement-of-work template

The forward-looking companion to `invoice/`, same utilitarian mono chrome. One page:
priced scope rows (optional items carry an "optional" chip and total
separately), headline figure, timeline, payment terms, and a running-costs /
assumptions block for third-party services the client pays directly. See
[`quote/README.md`](./quote/README.md).
