---
name: digiweb
description: The shared design system behind digithings.ai, digiquant.io, olympus, and digichat.
colors:
  bg-canvas: "#0A0E0C"
  surface: "#121417"
  surface-raised: "#171A1E"
  hairline: "rgba(255, 255, 255, 0.09)"
  hairline-strong: "rgba(255, 255, 255, 0.15)"
  ink: "#ECEEF0"
  ink-soft: "#9AA0A6"
  ink-mute: "#6B7177"
  phosphor-teal: "#3DD6C4"
  phosphor-teal-weak: "rgba(61, 214, 196, 0.14)"
  on-accent: "#04201C"
  gain: "#3DD6C4"
  loss: "#E5533E"
  caution: "#E0B341"
  terminal-bg: "#08090B"
  terminal-ink: "#E7EAEC"
  terminal-mute: "#7E858B"
  livery-digigraph: "#E5B765"
  livery-digisearch: "#5AA3C4"
  livery-digichat: "#E2708A"
  livery-digikey: "#D97A5A"
  livery-digivault: "#9D8FC9"
  livery-digistore: "#7B7FC7"
  diff-add: "#86C98F"
  diff-del: "#E2929E"
typography:
  display:
    fontFamily: '"Geist Mono", "JetBrains Mono", ui-monospace, monospace'
    fontSize: "clamp(2rem, 5vw, 3.4rem)"
    fontWeight: 500
    lineHeight: 1.1
    letterSpacing: "-0.04em"
  body:
    fontFamily: '"Geist Mono", "JetBrains Mono", ui-monospace, monospace'
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "-0.015em"
  mono:
    fontFamily: '"Geist Mono", "JetBrains Mono", ui-monospace, monospace'
    fontSize: "0.8rem"
    fontWeight: 400
    lineHeight: normal
    letterSpacing: "0.02em"
rounded:
  sm: "0"
  md: "0"
  lg: "0"
  pill: "0"
spacing:
  control: "0.6rem"
  card: "1.2rem"
  generous: "1.6rem"
  section: "clamp(4.5rem, 9vw, 8rem)"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.bg-canvas}"
    rounded: "0"
    padding: "0.62rem 1.3rem"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.ink}"
    rounded: "0"
    padding: "0.62rem 1.3rem"
  button-danger:
    backgroundColor: transparent
    textColor: "{colors.loss}"
    rounded: "0"
    padding: "0.62rem 1.3rem"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "0"
    padding: "{spacing.card}"
  input:
    backgroundColor: "{colors.bg-canvas}"
    textColor: "{colors.ink}"
    rounded: "0"
    padding: "0.55rem 0.7rem"
  chip-selected:
    backgroundColor: "{colors.phosphor-teal-weak}"
    textColor: "{colors.ink}"
    rounded: "0"
    padding: "0.4rem 0.75rem"
  badge:
    backgroundColor: transparent
    textColor: "{colors.ink-mute}"
    rounded: "0"
    padding: "0.16rem 0.5rem"
---

# Design System: digiweb

## Overview

**Creative North Star: "The Instrument Panel"**

digiweb reads as a cockpit, not a brochure. Monochrome is the resting state — black, white, and a three-step ink hierarchy — with color held in reserve as a signal, never spent as decoration. Every affordance from a button to a candlestick chart is built out of the same restrained kit: hairline borders, zero-radius controls, one mono type voice for claim/body/chrome, and serif only as a rare editorial escape hatch. The system does not perform enthusiasm; it reports state precisely and gets out of the way.

### Active blend — utilitarian terminal (v0.1 promoted)

As of 2026-08-30 the Instrument Panel tightens to utilitarian terminal simplicity — inspired by [herdr.dev](design/references/herdr.dev.md), [agentmail.to](design/references/agentmail.to.md), and [omarchy.org](design/references/omarchy.org.md), alongside Cursor / Graphite / xAI. Ledger: [`design/BLEND.md`](design/BLEND.md). Product rollout plan: [`design/ROLLOUT.md`](design/ROLLOUT.md).

**Shipping in `tokens.css` + design-reference (Phase 0):**

- **Radius 0** on `--r-*` / legacy `--radius-*` — no pills. Actionable vs container = **fill vs outline**.
- **Mono everything** — `--font-display` and body default to the mono stack. Serif is an escape hatch only.
- **Loud CTA = ink/paper rect** (reference `.btn-primary`). `--accent` = focus, live/status, chart identity — not primary marketing fill.
- **Sparse section rhythm** via `--section-y`; dashboards may tighten locally.
- Still reject glass, violet washes, synthwave, Inter-as-brand, and multi-accent chrome.

Phases 2–3 product-local debt is stripped on this branch (marketing Fraunces heroes, digichat shadcn radius, olympus `.glass-card` and `rounded-*` chrome). Gallery `uv-` CSS stays reference-only.

That restraint is structural, not stylistic. A dashboard, a landing page, and a terminal-style chatbot all draw from the *same* instrument-panel vocabulary — the module color that dresses digigraph's marketing hero is the identical `--accent` variable a digiquant chart reads to tint its equity line, just scoped differently. Color is a wiring diagram, not a moodboard: every hue in the system routes to an explicit meaning (a module's identity, a gain, a loss, a diff) and never means two things in the same place.

digiweb explicitly rejects the AI-slop default aesthetic: no purple-to-blue gradient heroes, no glassmorphism, no floating gradient blobs, no Inter-as-brand-font, no decorative box-shadow lifted off nothing in particular. Depth comes from hairline borders and tonal layering; when a shadow does appear, it means something specific (see Elevation & Depth).

**Key Characteristics:**
- Monochrome-by-default livery; color is opt-in per surface and always routes through `--accent`, never a hardcoded hex.
- Three color domains that never blend: **identity** (`--accent` / module liveries), **money** (`--up` / `--down`, fixed literals, livery-proof), and **diff** (`--rv-add` / `--rv-del`, a third pastel-only palette reserved for code review).
- **One mono voice** for claim, body, and chrome; serif is an escape hatch only (`serif-legacy` type suite in the reference).
- **Radius 0** everywhere in chrome; actionable vs container is read by **fill vs hairline**, not pill vs rectangle. True circles (spinners, live dots, avatars) stay geometric.
- "One loud thing per viewport": exactly one solid-fill control — **ink/paper rect**; `--accent` reserved for focus/live/identity — never primary marketing fill.
- Flat by default; a black shadow means "this is a floating overlay," an accent glow means "this is alive right now" — the two never substitute for each other.

## Colors

The palette is intentionally narrow: three neutrals for text, three surfaces for depth, one accent, and two small semantic sets (money, diff) that are deliberately fenced off from the accent system so a scoped livery can never repaint a gain, a loss, or a code change.

### Primary
- **Phosphor Teal** (`#3DD6C4` dark / `#0C7C71` light): the system's default accent — code-commented in the tokens file as "the terminal phosphor," it is digiquant's identity color and the monochrome livery's fallback. Used for focus rings, selected-state fills, chart identity lines, live/status, and anything reading "this is the live/default module" — **not** the primary marketing CTA fill (that is ink/paper). Spent sparingly by rule, never as a background wash. The light value was darkened from `#0E8C7F` on 2026-08-12 (WCAG 1.4.3): the lighter hex cleared only 4.14:1 for text/`--on-accent` use, under the 4.5:1 minimum. The per-module token `--accent-digiquant` deliberately stayed at the original `#0E8C7F`, since it is consumed as a *background* under a fixed dark `--on-accent`, a pairing that needs the opposite direction.

### Secondary — Module Liveries (opt-in, one at a time)
- **Amber Gold** — digigraph (`#E5B765`)
- **Slate Blue** — digisearch (`#5AA3C4`)
- **Rose** — digichat (`#E2708A`, ruled 6.4:1 AA+ on dark canvas)
- **Terracotta** — digikey (`#D97A5A`)
- **Lavender** — digivault (`#9D8FC9`, the "Obsidian-kinship hue")
- **Periwinkle** — digistore (`#7B7FC7`)

**The One-Livery Rule.** Exactly one module accent is active at a time, set via a global livery switcher or a local `.accent-<module>` scope class — never two module hues visible in the same view. `atlas`, `hermes`, and `kairos` are backend LangGraph sub-graph names, not colored products: their accents collapse to plain `--ink` on any redesigned surface by explicit ruling, so they never appear in the livery switcher.

### Tertiary — Money (fenced off from livery, never scoped)
- **Gain** (`#3DD6C4` dark / `#0C7C71` light): positive P&L and returns only. Light value darkened alongside Phosphor Teal above (2026-08-12, WCAG 1.4.3) — `--up` is a literal, kept in sync with `--accent`'s light hex by convention, not a live reference.
- **Loss** (`#E5533E` dark / `#C9533B` light): negative P&L and returns only.
- **Caution** (`#E0B341` dark / `#B5832A` light): warnings and non-P&L "bearish sentiment" reads that must not borrow money color.

**The Ledger Rule.** Gain/Loss are fixed to their own token (or, on the light theme, a bare literal) — never to `var(--accent)` — specifically so a livery switch, a scoped `.accent-*` class, or a theme flip can never repaint a P&L number. A module's identity color may be positive in tone and still not use Gain; only an actual signed financial read may.

### Neutral
- **Canvas** (`#0A0E0C` dark / `#FBFBF9` light): page background.
- **Surface** (`#121417` dark / `#FFFFFF` light): the standard card/panel fill.
- **Surface Raised** (`#171A1E` dark / `#F4F4F1` light): a nested/secondary tier, used sparingly.
- **Ink** (`#ECEEF0` dark / `#14181B` light): primary text and values.
- **Ink Soft** (`#9AA0A6` dark / `#5C636A` light): body copy, secondary reads.
- **Ink Mute** (`#6B7177` dark / `#8A9097` light): micro-caps labels, placeholders, meta text.
- **Hairline** (`rgba(255,255,255,.09)` dark / `rgba(10,15,20,.10)` light): the universal 1px border — this is the system's *only* depth cue on flat surfaces.
- **Hairline Strong** (`rgba(255,255,255,.15)` dark / `rgba(10,15,20,.18)` light): the hover/emphasis weight of the same border.

### Fourth domain — Diff (code review only, never reused)
- **Diff Add** (`#86C98F`) / **Diff Del** (`#E2929E`): a deliberately theme-invariant pastel pair used only for unified-diff washes, so a code change is never confused with a P&L read or a livery choice.

### Named Rules
**The Three Domains Rule.** Identity (`--accent`/liveries), Money (`--up`/`--down`/`--warn`), and Diff (`--rv-add`/`--rv-del`) are three separate color systems that must never blend into one palette or substitute for each other, even where a hue coincidentally matches (on the printed tearsheet, `--up` and `--accent` happen to share a literal value in the current teal brand — that is a coincidence of the current palette, not a rule; keep the tokens distinct in code regardless).

**The Terminal-Ink Rule.** The Terminal component family (`--term-bg`/`--term-ink`/`--term-mute`) carries its *own* always-dark-feeling palette, resolved independently of the page's own theme tokens — a terminal reads as a terminal even inside a light-themed page.

## Typography

**Display Font:** Geist Mono (with JetBrains Mono, ui-monospace, monospace fallback)
**Body Font:** Geist Mono (same stack — utilitarian v0.1 mono everything)
**Label/Mono Font:** Geist Mono (with JetBrains Mono, ui-monospace, monospace fallback)

**Character:** One mono voice carries claim, body, and chrome. Hierarchy is size and tracking, not a second face. Serif (`serif-legacy` / Instrument Serif or Fraunces) is an escape hatch for rare editorial moments — quotes, legal names — never the default marketing H1.

### Hierarchy
- **Display** (500, `clamp(2rem, 5vw, 3.4rem)`, 1.1 line-height, -0.04em tracking): hero claims, section titles, markdown `h1`–`h6` (flattened so a stray heading in chat never out-ranks the transcript). Weight stays light; never bold for emphasis.
- **Body** (400, ~1rem, 1.55 line-height): reading copy, capped at 65–75ch measure.
- **Mono / Label** (400, 0.56–0.86rem depending on context, 0.08–0.14em tracking, uppercase for labels): kickers (`// section`), eyebrows, button labels, form labels, table headers, terminal transcript, tabular numerals (`font-variant-numeric: tabular-nums` wherever a digit might change).

### Named Rules
**The Normative Display Rule.** `tokens.css` sets `--font-display` (and body) to the **Geist Mono** stack — digiweb v0.1 shipping default. Product apps that still override with Fraunces/Instrument Serif are Phase 2/3 debt (see `design/ROLLOUT.md`). Design-reference type suites keep `serif-legacy`, `plex`, `editorial`, `omarchy`, etc. for comparison only.

**The Mono-First Rule.** Serif is an escape hatch only. Dashboards, data, chrome, and marketing claims default to mono.

**The One Glyph, One Meaning Rule.** Five distinct prompt/marker glyphs exist across the system and are never reused across registers: `$` (process-list panes), `❯` (a diegetic OS-level CLI session), `>` (chat user turn), `▸` (chat assistant turn), `·` (chat system aside). Each glyph alone tells you which surface you're in — role in a chat transcript is read by glyph *shape*, not by color; both user and assistant markers render in the same accent.

## Layout

The grid is content-container-based rather than a rigid 12-column system: a `1180px` standard wrap and a `1280px` wide wrap bound most marketing content, a responsive `clamp(1.25rem, 4vw, 3.25rem)` gutter handles horizontal insets, and section rhythm runs on two clamped steps — `clamp(4.5rem, 9vw, 8rem)` standard (sparse-leaning), `clamp(2.5rem, 5vw, 4rem)` tight — rather than a fixed pixel gap.

Two structural patterns recur across every family and are load-bearing rather than decorative:

**The Command-Band-Then-Ledger Rule.** Every dashboard surface (olympus's portfolio workspace, its decision-monitoring views) composes the same way: one restrained command band naming the primary state (a large mono statistic, a compact metrics `dl`, an as-of timestamp), followed by a single full-width hairline ledger table. Never a stack of nested decorative cards competing for attention.

**Hierarchy by geometry, not color.** The bento/module grid communicates importance through cell *span* (hero = 2×2, wide = 2×1, tall = 1×2, unit = 1×1) while background and border stay neutral — only the hero cell gets a faint accent wash. A grayscale screenshot of the grid should still read its hierarchy correctly.

Responsive behavior collapses through one shared breakpoint (`760px`) for most multi-column grids (feature cells, bento grid) and a device-appropriate breakpoint elsewhere (`900px` card-deck pinning, `640px`–`720px` for dense metric/ratio grids). Device mockups (the olympus phone frame) deliberately opt out of breakpoints entirely and resize fluidly via `clamp()`, because hardware should look like hardware at any width, not requeue its layout.

**The Crop-Never-Break Rule.** Product screenshots inside a `ProductFrame` scale down to fit their container (`Math.min(1, containerWidth / artboardWidth)`) but never scale up past their authored size — an undersized container crops via `overflow: hidden` rather than letting the artwork reflow or blow out its box.

## Elevation & Depth

**Flat by default; shadow means overlay; glow means alive.** The system does not use ambient elevation shadows on ordinary content. A card, a panel, a form field, a finance dashboard composite — all of them read depth from a single 1px hairline border and a flat surface fill, escalating only to the stronger `hairline-strong` border on hover. Olympus states this as an explicit house rule: "FLAT — no glass morphism on content."

A soft, theme-invariant black shadow (`rgba(0,0,0,.45–.65)`, always a plain black rgba, never `color-mix`-tinted) is reserved *exclusively* for genuinely floating overlay chrome that sits above the page: the dropdown menu pane, the tooltip bubble, the typed hero terminal, the toast stack, and the command palette. These are the only surfaces in the entire system that cast a real elevation shadow.

Separately, an accent- or money-colored glow (a `box-shadow` built from `color-mix(var(--accent) or var(--up)/var(--down), N%, transparent)`) signals liveness — a running pipeline node's pulsing ring, a "live" status dot, a chart's identity-line drop-glow. This is never a substitute for the black overlay shadow and never appears on inert content; it means "this is actively happening right now," not "this is lifted off the page."

### Shadow Vocabulary
- **Overlay lift** (`0 18px 40px -18px rgba(0,0,0,.5)` dropdown pane; scaled variants for tooltip/terminal/toast/command-palette): the single family of shadows meaning "floating above the page."
- **Focus ring** (`0 0 0 2–4px color-mix(in srgb, var(--accent) or var(--down), ~20–50%, transparent)`): the universal focus-visible treatment on every interactive control — a spread shadow standing in for an outline.
- **Liveness glow** (`color-mix(var(--accent)/var(--up)/var(--down), 12–55%, transparent)`, animated on a 1.6–2.4s cycle): pulsing status pips, live dots, chart identity-line glow. Reserved for genuinely live/streaming state.
- **Print flattening.** On any print/PDF surface (the tearsheet family), every gradient and box-shadow is forced off (`box-shadow: none !important`) and surfaces flatten to a plain bordered rect — paper has no elevation.

### Named Rules
**The Overlay-Only Shadow Rule.** If a component is not a dropdown, tooltip, toast, command palette, or the hero terminal, it does not get a drop shadow. New components should default to flat + hairline first and justify a shadow only if they are a genuinely floating, dismissible overlay.

## Shapes

**Radius 0** on all UI chrome — buttons, badges, chips, tabs, cards, panels, inputs, dropdowns. Actionable vs container is read by **fill vs outline** (and density), not by pill vs rounded rect. True circles (`999px` / `50%`) remain only where geometry demands it: spinners, live dots, avatars, progress thumbs.

Device mockups (phone frames) may still use bespoke bezel radii — they simulate hardware, not UI chrome.

Borders are uniformly 1px hairline; the only thicker strokes are decorative chevron corner-strokes / bracket docs marks and a slider thumb's focus ring.

**The Shape-Carries-Meaning Rule (v0.1).** Do not reintroduce pills "for friendliness." Loud = ink/paper rectangle; quiet = hairline rectangle; structure marks (brackets) are allowed ornaments, not radius.

## Components

**Instrumentation, not decoration.** Every control is built from zero-radius rects, mono type, and color spent only where it signals state — a selection, a focus, a gain, a loss, a live process. Nothing is styled to look busy.

### Buttons
- **Shape:** rectangle (`border-radius: 0`), 1px border baseline, `0.62rem 1.3rem` padding.
- **Primary (loud):** solid `--ink` fill on dark (paper fill on light), label from `--bg` — **not** accent-filled. Module liveries do not recolor the primary marketing CTA. No hover treatment on the plain primary; only the "magnetic," pointer-following variant gets motion feedback ("the one earned exception to the one-motion-moment law").
- **Ghost:** transparent, hairline border, hover tints the border toward accent — default for non-primary actions. Docs sibling may use bracket corners (agentmail) instead of a second fill.
- **Quiet:** transparent, no border, reads as a low-emphasis text link (`ink-mute` → `ink` on hover).
- **Danger:** transparent, loss-tinted text and border, hover fills a faint loss-tinted wash.
- **Disabled:** `opacity: 0.4`, `cursor: not-allowed`.
- **Loading:** an inline 11px two-tone spinner (`currentColor`), killed under `prefers-reduced-motion`.

### Chips / Tabs / Segmented Controls (the selection family)
- **Style:** zero-radius bordered strip, hairline border, `ink-mute`/`ink-soft` idle text.
- **Selected state:** text promotes to `ink`, border and background both tint toward the accent via `color-mix` — a soft wash, never competing with the primary CTA fill.
- **Livery chip specifically:** carries a small glowing accent dot as its leading icon, tinted per-module via an inline `--chip` custom property.

### Cards / Containers
- **Corner Style:** `0` (`--r-sm` / `--r-md` / `--r-lg` all zero). Tonal slab = `--surface` fill + hairline.
- **Background:** flat `--surface`, no gradient, no glass.
- **Shadow Strategy:** none (see Elevation & Depth) — depth is the hairline + value step alone.
- **Border:** 1px `--hair`, escalating to `--hair-strong` on hover where the card is interactive.
- **Internal Padding:** `1.1–1.8rem`, roughly double the compact-control padding band.

### Inputs / Fields
- **Style:** `0` radius, hairline border, `--bg`-colored fill (canvas cut into the surrounding surface), mono type regardless of field type.
- **Focus:** border tints toward accent (~55%) plus a 3–4px accent-tinted glow ring.
- **Error:** the entire recipe swaps to `--down` — border, ring, and (via a wrapper class hook) the field's own text.
- **Disabled:** `opacity: 0.5–0.55`, `not-allowed` cursor.

### Navigation
NavShell settles (gains a blurred hairline backdrop) after 8px of scroll and either yields off-screen past 180px of downward scroll (returning immediately on any upward scroll) or, on app-like surfaces, reveals within a top hot-zone and releases once the pointer clears it. A dropdown menu pins the bar open. Below `880px` the inline strip becomes a hamburger opening a full-height sheet — mono link stack (no serif mobile exception). Sparse ghost nav: few links, one filled Login/Install max. The wordmark's suffix (the part of "digithings" after "digi") is always the accent-colored emphasis, everywhere the brand appears.

### Chat Transcript (signature — the terminal-style chatbot)
- **No bubbles.** Every turn is a two-column CSS grid row (marker + body) inside one continuous scrollback pane — never a boxed message bubble.
- **Role is read by glyph shape, not color.** `>` marks a user turn, `▸` an assistant turn, `·` a system aside; both user and assistant markers render in the *same* accent color.
- **Rail for process, frame for object.** A collapsible tool-call or thinking chain hangs off a colored left border-rail, never a box. Only genuinely rich embedded objects — a chart, a route graph, an approval-gate card — get a full hairline-bordered frame. Plain text is never boxed.
- **One sans-serif island.** The composer's live textarea is the system's only sans-serif input inside an otherwise all-mono surface — typing feels like editing prose even though the transcript around it reads as terminal output.
- **Accent is furniture, never prose.** Inside rendered markdown, accent touches only list markers, the blockquote rule, and links; body text stays ink/ink-soft so a long streamed answer stays calm despite a saturated module color.
- **The streaming cursor** is a solid 7×14px accent block with a hard binary blink (`steps(1)`, no fade) — the same primitive should back every wait-state and streaming caret in the system rather than a bespoke redraw per surface.

### Dashboard / Finance Panels (signature — the olympus surface)
- **Money vs. identity are different tokens, always.** An equity curve or allocation bar wears `--accent` (identity/chrome) even when its values are positive; only a signed P&L or return figure wears `--up`/`--down`. Never let a positive-but-non-financial value borrow the gain color.
- **Charts stay flat and token-themed.** Canvas charts (candles, equity curves, drawdown) are transparent-background, re-themed live via a `data-theme` observer — never a page reload. Anything with a PDF export path uses the separate SVG tearsheet family instead of canvas, because canvas rasterizes and races the print dialog.
- **Dense hairline grids** (ratio strips, returns matrices, ledger tables) key their internal dividers off a `data-cols` attribute since Tailwind can't express `nth-child` — a documented, intentional CSS escape hatch.

## Do's and Don'ts

### Do:
- **Do** build under the `[data-theme]`-scoped token system (`--bg` / `--surface` / `--ink` family, `--r-sm/md/lg` = 8/12/16px) — this is the normative, currently-shipping scale.
- **Do** treat Geist Mono as the production display/body default; treat `serif-legacy` / Fraunces as reference-app furniture or a rare editorial escape hatch, not a target to copy onto product heroes.
- **Do** keep money colors (`--up`/`--down`/`--warn`) fixed to their own token or literal, never `var(--accent)` — a livery switch must never repaint a P&L number.
- **Do** give every interactive control the same focus recipe: `outline: none` plus a 2–4px `color-mix(var(--accent) or var(--down), ~50%, transparent)` box-shadow ring.
- **Do** reserve solid, filled-accent surfaces for exactly one control per viewport; every sibling control should be a transparent, hairline-bordered outline.
- **Do** use the five scoped prompt/marker glyphs (`$ ❯ > ▸ ·`) exactly as documented — never invent a sixth or reuse one across registers.
- **Do** keep buy-side/positive-chrome markers on `--accent` and sell-side/negative markers on `--down` in the tearsheet/finance charting family — the split is deliberate, not an oversight to "fix" into symmetry.

### Don't:
- **Don't** mix the legacy unscoped `:root` token system (`--radius-sm/md/lg` = 6/8/12px, `--space-1..9`, Inter as `--font-family`) into new work — it exists only to serve un-migrated legacy pages and is a genuinely different scale from the current one, not a rename.
- **Don't** apply a box-shadow to ordinary content (cards, panels, dashboard composites). If it isn't a dropdown, tooltip, toast, command palette, or the hero terminal, it stays flat.
- **Don't** color two different module liveries in the same view — the system is strictly one-livery-at-a-time.
- **Don't** let `atlas`, `hermes`, or `kairos` render as colored products on a redesigned surface — they name backend LangGraph sub-graphs and must collapse to plain ink.
- **Don't** reuse the diff palette (`--rv-add`/`--rv-del`) for anything except unified-diff review UI, and don't reuse money colors for a non-financial positive/negative read (olympus's bull/bear sentiment bar deliberately uses `--accent`/`--warn`, not `--up`/`--down`, for exactly this reason).
- **Don't** put a message in a bubble or box inside the chat transcript — plain turns are grid rows; only rich embedded objects earn a frame.
- **Don't** carry forward the reference implementation's remaining known gaps as if they were intentional: missing `:disabled` styling on ghost/quiet/danger buttons, and the digichat light-theme accent (`--accent-digichat`, 2.4:1 contrast) failing to fall back to the AA-safe neutral teal the codebase itself documents as the fix. Treat these as bugs to fix in new work, not patterns to imitate. (The reference implementation's undeclared `--surface-inverse` fallback — the cause of illegible button text under the default monochrome livery — was fixed by routing every `.btn-primary`/`.ctl-btn-ref--primary`/`.cw-btn--primary`/toggle-knob text color through the already-correct `--on-accent` token instead.)
