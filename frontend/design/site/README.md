# `@digithings/design/site` — shared CSS foundation

`site.css` is imported directly by `frontend/digithings-web/app/globals.css`
and `frontend/digiquant-web/app/globals.css` — the live Next.js marketing
sites (digithings.ai, digiquant.io). It supplies the primitives those apps'
React components still reach for by class name: `.wrap`, `.brand*`, buttons,
`.kicker`/`.prompt`, the standalone `.hero-title`, the terminal block
(`.term*`/`.tl-*`, consumed by `frontend/web/src/components/Terminal.tsx`),
sections, **ProductFrame**, **BentoGrid**, **TrustStrip**, **reveal-up**,
**StatCounter**, **ChangelogBand**, **CodeSampleBand**, **CapabilityCard**,
**HorizontalScrollBand**, **ClosingCtaBand**, **FaqAccordion**, **PricingMatrix**,
**HeroFeaturePicker**, `.principles`, and `.footer*`. Terminal-CLI /
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

## `CodeSampleBand` (CSS + `code-sample-band.js`, EVOLUTION.md Phase B)

xAI/Cursor-style tabbed SDK snippets (`curl` / Python / TypeScript) with
copy-to-clipboard. Always dark, reusing the terminal block's `--term-*`
tokens regardless of page theme. Follows the WAI-ARIA "Tabs with Automatic
Activation" pattern — keyboard-navigable, `aria-selected`, focus ring.

```html
<div class="code-sample-band">
  <div class="code-sample-band__bar">
    <div class="code-sample-band__tabs" role="tablist" aria-label="Install command">
      <button class="code-sample-band__tab" role="tab" aria-selected="true" aria-controls="panel-curl" id="tab-curl">curl</button>
      <button class="code-sample-band__tab" role="tab" aria-selected="false" aria-controls="panel-py" id="tab-py" tabindex="-1">Python</button>
    </div>
    <button class="code-sample-band__copy" type="button" aria-label="Copy code">copy</button>
  </div>
  <div class="code-sample-band__panels">
    <pre class="code-sample-band__panel" role="tabpanel" id="panel-curl" aria-labelledby="tab-curl"><code>curl ...</code></pre>
    <pre class="code-sample-band__panel" role="tabpanel" id="panel-py" aria-labelledby="tab-py" hidden><code>import digithings ...</code></pre>
  </div>
</div>
```

The copy button sits **outside** `role="tablist"` (inside `.code-sample-band__bar`
alongside it) — a tablist owns only `role="tab"` children, so a non-tab button
inside it is an ARIA structure violation.

```js
import { initCodeSampleBand } from '../code-sample-band.js';
initCodeSampleBand(); // wires every .code-sample-band on the page
```

| Class | Role |
|-------|------|
| `.code-sample-band` | Dark panel, `--term-bg`/`--term-hair`. |
| `.code-sample-band__bar` | Flex header row holding the tablist + the copy button as siblings (padding/fill/border). |
| `.code-sample-band__tabs` | `role="tablist"` row — owns only `role="tab"` children. |
| `.code-sample-band__tab` | `role="tab"` button; `[aria-selected="true"]` gets the active surface treatment; `:focus-visible` ring. |
| `.code-sample-band__copy` | Copies the active panel's `textContent` via `navigator.clipboard`; `.is-ok` after a successful copy (2s, matches `.tl-ok`'s `--up` color). |
| `.code-sample-band__panel` | `role="tabpanel"` `<pre><code>` block; Geist Mono, wraps long lines. |

`code-sample-band.js`'s `initCodeSampleBand()` wires click + keyboard
(`ArrowLeft`/`ArrowRight`/`Home`/`End`, roving `tabindex`) on every
`[role="tab"]` inside the matched root, and toggles the matching
`[role="tabpanel"]`'s `hidden` attribute — no network calls, pure DOM.

## `CapabilityCard` (CSS-only, EVOLUTION.md Phase B)

xAI-style mini-UI preview + "Explore →" link. Flat `--surface` panel, hairline
border — no decorative eyebrow pills without an action (anti-pattern #3).
Composes standalone in a `.capability-grid`, or drop a single `.capability-card`
inside a `.bento__cell`.

```html
<div class="capability-grid">
  <div class="capability-card">
    <div class="capability-card__preview">
      <!-- <img>, a .product-frame child, or a .term snippet -->
    </div>
    <div class="capability-card__title">Orchestration</div>
    <p class="capability-card__body">One line of what this capability does.</p>
    <a class="capability-card__cta" href="/modules/digigraph">Explore <span aria-hidden="true">&rarr;</span></a>
  </div>
</div>
```

| Class | Role |
|-------|------|
| `.capability-grid` | Grid container — 1 column below 768px, `repeat(2, 1fr)` at `min-width: 768px`; `max-width: var(--wrap-wide)`. |
| `.capability-card` | Flat card surface with hover lift (`--duration-hover`/`--ease-glide`). |
| `.capability-card__preview` | Optional media slot — takes an `<img>`, a `.product-frame` child, or a `.term` snippet; rounds to `--r-md`, clips overflow. |
| `.capability-card__title` / `.capability-card__body` | Heading + body copy. |
| `.capability-card__cta` | `Explore →` arrow link; the `span[aria-hidden]` arrow translates on card hover, matching `.btn`/`.bento__cta`. |

Works unscoped in both themes. Same deferred-React-wrapper note as ProductFrame (#1195).

## `HorizontalScrollBand` (CSS-only, EVOLUTION.md Phase E)

Cursor-style horizontal snap row for changelog cards, testimonial rows, and
mobile overflow bands. CSS-only — no `horizontal-scroll.js` was needed:
keyboard access comes from making `.h-scroll__track` a focusable
(`tabindex="0"`) native scroll container, so arrow keys scroll it; wrap it in
`role="group"` with an `aria-label` so the row is announced. `prefers-reduced-motion:
reduce` collapses the row to a vertical stack, so every card stays reachable
without a horizontal gesture.

```html
<div class="h-scroll">
  <div class="h-scroll__track" tabindex="0" role="group" aria-label="Recent releases">
    <article class="h-scroll__card"><!-- card content --></article>
    <article class="h-scroll__card"><!-- card content --></article>
    <article class="h-scroll__card"><!-- card content --></article>
  </div>
</div>
```

| Class | Role |
|-------|------|
| `.h-scroll` | Positioning wrapper; applies an edge-fade `mask-image` on both inline edges (removed under reduced motion). |
| `.h-scroll__track` | Focusable (`tabindex="0"`) flex scroll container — `scroll-snap-type: x mandatory`, hidden scrollbar, `:focus-visible` ring. Under `prefers-reduced-motion: reduce` it becomes a vertical column with no snap. |
| `.h-scroll__card` | Snap child — fixed `262px` (Cursor changelog card width), flat `--surface` panel. Full-width when stacked under reduced motion. |

CSS-only, both themes. Same deferred-React-wrapper note as ProductFrame (#1195).
Content wiring (real changelog/testimonial data) is out of scope here — this
primitive owns only the scroll/snap/masking contract, same division as
TrustStrip and ChangelogBand.

## `ClosingCtaBand` (CSS-only, EVOLUTION.md Phase E)

Graphite/Cursor **pre-footer conversion band** — a full-width centered section
placed directly above the footer: one literal headline, one primary `.btn`, and
an optional mono secondary link. Compose with `.reveal-up` (above) for a
scroll-in enter; reduced motion is already honored by the shared block. Copy
tone follows [`../references/scans/copy-patterns.md`](../references/scans/copy-patterns.md)
(literal verbs, no hype). Landing-page wiring is [#1227](https://github.com/digithings-ai/digithings/issues/1227) — this primitive owns only the markup/CSS contract.

```html
<section class="closing-cta reveal-up">
  <div class="closing-cta__inner">
    <h2 class="closing-cta__title">Build your agent stack in the open.</h2>
    <p class="closing-cta__sub">Open-core orchestration, quant, RAG, and chat.</p>
    <div class="closing-cta__actions">
      <a class="btn btn-primary" href="https://github.com/digithings-ai">Start building</a>
      <a class="closing-cta__secondary" href="/architecture">Read the architecture <span aria-hidden="true">&rarr;</span></a>
    </div>
  </div>
</section>
```

**Copy slots** (fill from the consuming app; keep labels literal):

| Slot | Content | Notes |
|------|---------|-------|
| `.closing-cta__title` | Headline | Literal, reads best ≤ ~20ch. |
| `.closing-cta__sub` | Optional one-line support | ≤ ~48ch; omit for a bare title. |
| `.closing-cta__actions` → `.btn.btn-primary` | Primary label + `href` | The single, literal action (e.g. "Start building", "Open Olympus"). |
| `.closing-cta__secondary` | Optional secondary label + `href` | Mono, arrow-suffix; the `span[aria-hidden]` translates on hover, matching `.btn`/`.bento__cta`. |

**Copy variants** (shown in `frontend/design/smoke/index.html`):

| Surface | Title | Primary | Secondary |
|---------|-------|---------|-----------|
| digithings.ai | "Build your agent stack in the open." | Start building | Read the architecture → |
| digiquant.io | "One graph, research to execution." | Open Olympus | Browse strategies → |

| Class | Role |
|-------|------|
| `.closing-cta` | Full-width band — `padding-block: var(--section-y)`, centered text. |
| `.closing-cta__inner` | `max-width: var(--wrap-wide)` centered column (title / sub / actions), gap-stacked. |
| `.closing-cta__title` | Clamped display headline, `max-width: 20ch`. |
| `.closing-cta__sub` | Muted one-line support, `max-width: 48ch`. |
| `.closing-cta__actions` | Wrapping, centered row of the primary `.btn` + optional secondary. |
| `.closing-cta__secondary` | Mono arrow-suffix link; hover tints `--ink` and nudges the arrow. |

CSS-only, both themes. Same deferred-React-wrapper note as ProductFrame (#1195).

## `FaqAccordion` (CSS-only, EVOLUTION.md Phase E)

Graphite/Cursor pricing-page Q&A built on **native `<details>`/`<summary>`** — no
JS. Give every `.faq__item` the **same `name`** to get a native "one open at a
time" exclusive accordion (a modern-browser feature); omit `name` and each item
toggles independently. The disclosure chevron rotates on `[open]`; its transition
is dropped under `prefers-reduced-motion: reduce` (shared block). Keyboard access
is native (`Tab` to the summary, `Enter`/`Space` to toggle).

**Content shape** for a data-driven render (per site): `{ q, a }[]`.

```html
<div class="faq">
  <details class="faq__item" name="pricing-faq" open>
    <summary class="faq__q">Is DigiThings really open source?</summary>
    <p class="faq__a">Yes — the core stack is MIT-licensed and self-hostable.</p>
  </details>
  <details class="faq__item" name="pricing-faq">
    <summary class="faq__q">Do I need to bring my own model keys?</summary>
    <p class="faq__a">For self-hosting, yes — any LiteLLM provider or a local model.</p>
  </details>
</div>
```

| Class | Role |
|-------|------|
| `.faq` | Column container, `max-width: 760px` for readable line length. |
| `.faq__item` | One `<details>`; hairline divider below. Same `name` across items → exclusive accordion. |
| `.faq__q` | The `<summary>` — flex row (label + chevron), default marker removed, `:focus-visible` ring. Rotating CSS chevron via `::after`. |
| `.faq__a` | Answer body, `max-width: 60ch`, muted. |

CSS-only, both themes. Same deferred-React-wrapper note as ProductFrame (#1195).

## `PricingMatrix` (CSS-only, EVOLUTION.md Phase E)

Open-core pricing tiers + optional comparison table. **Honest-copy policy**
(EVOLUTION.md §10, anti-pattern #2): no invented usage caps or fake "limited AI
requests" — the free self-hosted tier is genuinely the full MIT stack. Three
tiers: **Self-hosted (MIT)** · **Managed (future)** · **Enterprise (contact)**.
`.pricing__tier--featured` lifts one card with an `--accent` ring.

**Content shape** (per site): `{ name, price, cadence?, desc, features: string[], cta: { label, href }, featured?: boolean }[]`.

```html
<div class="pricing">
  <div class="pricing__tier">
    <div class="pricing__name">Self-hosted</div>
    <div class="pricing__price">Free <small>· MIT</small></div>
    <p class="pricing__desc">Run the full stack on your own infrastructure.</p>
    <ul class="pricing__features"><li>All core services</li><li>Bring your own key</li></ul>
    <div class="pricing__cta"><a class="btn btn-ghost" href="/docs">Read the docs</a></div>
  </div>
  <div class="pricing__tier pricing__tier--featured"><!-- Managed --></div>
  <div class="pricing__tier"><!-- Enterprise --></div>
</div>

<!-- optional feature × tier comparison -->
<table class="pricing-table">
  <thead><tr><th>Feature</th><th>Self-hosted</th><th>Managed</th><th>Enterprise</th></tr></thead>
  <tbody>
    <tr><th scope="row">Core services</th><td class="is-yes">✓</td><td class="is-yes">✓</td><td class="is-yes">✓</td></tr>
    <tr><th scope="row">Managed upgrades</th><td class="is-no">—</td><td class="is-yes">✓</td><td class="is-yes">✓</td></tr>
  </tbody>
</table>
```

| Class | Role |
|-------|------|
| `.pricing` | Grid — 1 column below 768px, `repeat(3, 1fr)` at `min-width: 768px`; `max-width: var(--wrap-wide)`. |
| `.pricing__tier` | Flat `--surface` card; `.pricing__cta .btn` pins to the bottom, full-width. |
| `.pricing__tier--featured` | Highlighted tier — `--accent` border + ring. |
| `.pricing__name` / `.pricing__price` / `.pricing__desc` | Mono tier label, display price (`<small>` for cadence/licence), muted blurb. |
| `.pricing__features` | Check-bulleted list — `✓` in `--up` via `::before`. |
| `.pricing-table` | Optional comparison grid; `.is-yes` (`--up`) / `.is-no` (`--ink-mute`) cells; first column left-aligned, tier columns centered. |

CSS-only, both themes. Same deferred-React-wrapper note as ProductFrame (#1195).

## `HeroFeaturePicker` (CSS + `hero-picker.js`, EVOLUTION.md Phase E)

Graphite-style **icon-tab row** below the hero that swaps which `ProductFrame`
(#1202) preview shows — e.g. Olympus / Strategies / Pipeline on digiquant.io.
**Static UI crops only** (no video swap — lighter weight per the design spec).
Follows the WAI-ARIA "Tabs" pattern; each panel wraps a `.product-frame`, so it
inherits the container-query sizing and never clips at browser zoom. Tabs are
icon-only (`~53×53px`, Graphite reference) — give each an `aria-label`.

```html
<div class="hero-picker">
  <div class="hero-picker__tabs" role="tablist" aria-label="Preview context">
    <button class="hero-picker__tab" role="tab" id="hp-tab-olympus"
            aria-controls="hp-panel-olympus" aria-selected="true" aria-label="Olympus">
      <svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon --></svg>
    </button>
    <button class="hero-picker__tab" role="tab" id="hp-tab-strategies"
            aria-controls="hp-panel-strategies" aria-selected="false" tabindex="-1" aria-label="Strategies">
      <svg viewBox="0 0 24 24" aria-hidden="true"><!-- icon --></svg>
    </button>
  </div>
  <div class="hero-picker__panels">
    <div class="hero-picker__panel" role="tabpanel" id="hp-panel-olympus" aria-labelledby="hp-tab-olympus">
      <div class="product-frame"><div class="product-frame__surface"><!-- Olympus crop --></div></div>
    </div>
    <div class="hero-picker__panel" role="tabpanel" id="hp-panel-strategies" aria-labelledby="hp-tab-strategies" hidden>
      <div class="product-frame"><div class="product-frame__surface"><!-- Strategies crop --></div></div>
    </div>
  </div>
</div>
```

```js
import { initHeroPicker } from '../hero-picker.js';
initHeroPicker(); // wires every .hero-picker on the page
```

| Class | Role |
|-------|------|
| `.hero-picker` | Centered column — icon tablist above, swapped panels below. |
| `.hero-picker__tabs` | `role="tablist"` row of icon buttons. |
| `.hero-picker__tab` | `role="tab"` icon button, `53×53px`; `[aria-selected="true"]` tints `--accent`; `:focus-visible` ring. Icon-only → needs `aria-label`. |
| `.hero-picker__panels` / `.hero-picker__panel` | `role="tabpanel"` regions; inactive ones carry the `hidden` attribute. Each wraps a `.product-frame`. |

`hero-picker.js`'s `initHeroPicker()` wires click + keyboard (`ArrowLeft`/`ArrowRight`/
`Home`/`End`, roving `tabindex`) on every `[role="tab"]`, toggling the matching
`[role="tabpanel"]`'s `hidden` — the same tab model as `code-sample-band.js`. It
normalizes the initial state from the `aria-selected` tab without stealing focus
on load. No network calls, pure DOM. `prefers-reduced-motion` needs no special
handling — the swap is an instant `hidden` toggle, not an animation.

CSS-only styling, both themes. Same deferred-React-wrapper note as ProductFrame (#1195).
