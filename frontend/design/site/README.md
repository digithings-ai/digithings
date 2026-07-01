# `@digithings/design/site` — shared CSS foundation

`site.css` is imported directly by `frontend/digithings-web/app/globals.css`
and `frontend/digiquant-web/app/globals.css` — the live Next.js marketing
sites (digithings.ai, digiquant.io). It supplies the primitives those apps'
React components still reach for by class name: `.wrap`, `.brand*`, buttons,
`.kicker`/`.prompt`, the standalone `.hero-title`, the terminal block
(`.term*`/`.tl-*`, consumed by `frontend/web/src/components/Terminal.tsx`),
sections, **ProductFrame**, **BentoGrid**, **TrustStrip**, **reveal-up**,
**StatCounter**, **ChangelogBand**, `.principles`, and `.footer*`. Terminal-CLI /
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

## `BentoGrid` (CSS-only, EVOLUTION.md Phase B)

Cursor-style linked feature cells. Mobile-first: single column, 2×2 from
768px. Flat `--surface` panels — no glass morphism (anti-pattern #8).

```html
<div class="bento">
  <a class="bento__cell" href="/modules/digigraph">
    <div class="bento__kicker">// orchestration</div>
    <div class="bento__title">Supervisor graph</div>
    <p class="bento__body">One line of what this module does.</p>
    <span class="bento__cta">Learn more <span aria-hidden="true">&rarr;</span></span>
  </a>
  <div class="bento__cell bento__cell--static bento__cell--span-2">
    <!-- non-linked, wide cell -->
  </div>
</div>
```

| Class | Role |
|-------|------|
| `.bento` | Grid container — 1 column below 768px, `repeat(2, 1fr)` at `min-width: 768px`; `max-width: var(--wrap-wide)`. |
| `.bento__cell` | Cell surface — `<a>` for a linked cell (hover lift via `--duration-hover`/`--ease-glide`) or any element with `.bento__cell--static` for a non-interactive cell (no hover, no cursor pointer). |
| `.bento__cell--span-2` | Optional wide cell spanning both columns. |
| `.bento__kicker` / `.bento__title` / `.bento__body` | Mono eyebrow, heading, body copy. |
| `.bento__thumb` | Optional image/thumbnail slot — rounds to `--r-md`, clips overflow. |
| `.bento__cta` | Arrow-suffix link text (`Learn more →`); the `span[aria-hidden]` arrow translates on `.bento__cell:hover`, matching `.btn`'s hover idiom. |

Works unscoped in both themes. Same deferred-React-wrapper note as ProductFrame (#1195).

## `TrustStrip` (CSS-only, EVOLUTION.md Phase B)

Cursor-style hero trust line — a muted row of proof items, text or logos.

```html
<div class="trust-strip">
  <span class="trust-strip__item">open core · self-hosted</span>
  <img class="trust-strip__item" src="/logos/partner.svg" alt="Partner" />
</div>
```

| Class | Role |
|-------|------|
| `.trust-strip` | Centered, wrapping flex row. |
| `.trust-strip__item` | Text item (mono, `--ink-mute`) or `<img>` logo (28px height, grayscale + reduced opacity for visual parity across mixed-brand logos). |

## `reveal-up` (CSS-only utility, EVOLUTION.md Phase B)

Opacity + translate enter animation. **This is not the old `site/reveal.js`**
(removed as dead code in #1240) — `.reveal-up` only owns the two visual
states (`opacity`/`transform`/`transition`); something external toggles the
visible class:

```html
<div class="reveal-up">Revealed on scroll or on mount.</div>
```

```js
// Option A — vanilla pages: frontend/design/scroll-trigger.js
import { initScrollTrigger } from '../scroll-trigger.js';
initScrollTrigger({ activateSelector: '.reveal-up', activationLineRatio: 0.8 });
// toggles .active on .reveal-up elements as they cross the scroll line

// Option B — React: frontend/web/src/motion/primitives.tsx's <Reveal>
// applies its own visibility state via className; pass className="reveal-up"
// and toggle `is-visible` there instead of `.active`, or wire Reveal to add
// `.active` for a single shared contract — either satisfies the CSS below.
```

| Class | Role |
|-------|------|
| `.reveal-up` | Initial state — `opacity: 0`, `translateY(1rem)`. |
| `.reveal-up.is-visible` / `.reveal-up.active` | Visible state — both class names are wired to the same rule so either trigger mechanism (scroll-trigger's `.active` or a `.is-visible` convention) works without duplicating CSS. |

`prefers-reduced-motion: reduce` shows the element immediately (no transition), consolidated in site.css's shared reduced-motion block.

## `StatCounter` (CSS + `stat-counter.js`, EVOLUTION.md Phase B)

xAI-style scroll-triggered metrics strip. **No-fake-data policy** (EVOLUTION.md
§10, anti-pattern #2): placeholder demo values must be clearly labeled as such;
real wiring is just setting `data-target` from real numbers, nothing invented.

```html
<div class="stat-counter-row">
  <div class="stat-counter" data-target="128" data-suffix="ms">
    <span class="stat-counter__value">0</span>
    <span class="stat-counter__label">p50 latency</span>
  </div>
</div>
```

```js
import { initStatCounter } from '../stat-counter.js';
initStatCounter(); // defaults: selector '.stat-counter', 1200ms ease-out-cubic
```

| Class / attribute | Role |
|-------|------|
| `.stat-counter-row` | Centered, wrapping flex row of metrics. |
| `.stat-counter` | One metric — JS-observed root. `data-target` (required), `data-prefix`/`data-suffix`/`data-decimals` (optional formatting). |
| `.stat-counter__value` | The animated number — `tabular-nums`, Geist Mono. |
| `.stat-counter__label` | Mono, uppercase, tracked label. |

`stat-counter.js`'s `initStatCounter()` uses `IntersectionObserver` to count
each `.stat-counter__value` from 0 to `data-target` once, the first time it
scrolls into view (a one-shot count, distinct from `scroll-trigger.js`'s
continuous `--scroll` progress model — different job, separate module).
`prefers-reduced-motion: reduce` (or no `IntersectionObserver` support) shows
the final value immediately, no animation loop.

## `ChangelogBand` (CSS-only + data shape, EVOLUTION.md Phase B)

Cursor-style dated release rows. Mobile: stacked. Desktop (`min-width: 640px`):
fixed date column + title row. CSS-only — rendering the data shape into
markup is left to the consumer (vanilla template string or React `.map()`),
same division of responsibility as TrustStrip.

**Data shape** (`{ date, version?, title, href, tag? }[]`) — see
[`../changelog-example.json`](../changelog-example.json) for a worked
example and `frontend/design/smoke/index.html` for a vanilla-JS renderer.
Source of truth for real content is whatever the consuming app already has
(a `CHANGELOG.md` excerpt, the GitHub Releases API, or a CMS) — this
primitive doesn't fetch or own data, only the markup/CSS contract.

```html
<div class="changelog-band">
  <div class="changelog-row">
    <div class="changelog-row__date">2026-06-29 &middot; v7.2</div>
    <div class="changelog-row__title">
      <a href="/releases/v7.2">Shared design primitives shipped</a>
      <span class="changelog-row__tag">release</span>
    </div>
  </div>
</div>
<p class="changelog-band__footer"><a href="/releases">View all releases &rarr;</a></p>
```

| Class | Role |
|-------|------|
| `.changelog-band` | Column container, `max-width: var(--wrap-wide)`. |
| `.changelog-row` | One entry — 1 column below 640px, `8rem 1fr` grid (date / title) at `min-width: 640px`. Hairline divider between rows. |
| `.changelog-row__date` | Mono date (+ optional version). |
| `.changelog-row__title` | Title, linked; hover tints `--accent`. |
| `.changelog-row__tag` | Optional pill (`release`, `fix`, etc.). |
| `.changelog-band__footer` | "View all releases →" link pattern. |
