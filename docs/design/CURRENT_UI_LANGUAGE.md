# Current UI language

Reconstructed from live source on branch `feat/deslop-s0-design-language` (#6327).
Every claim below carries a `file:line`. Where the prose docs disagree with the code,
the code is treated as the record and the disagreement is listed in
[Contradictions](#6-contradictions).

Reconstruction method: repository evidence only (tokens → shared sheets → surface
consumers), no rendered inspection. Anything that needed a browser is listed under
[What I could not determine](#9-what-i-could-not-determine) rather than guessed.

**Live baseline:** digiweb's home page (`apps/digiweb/app/page.tsx`, run with
`npm run dev --workspace @digithings/digiweb -- --port 4013`) renders these rules
in the shipped tile grammar — hairline mosaic, tile chrome, density ladder, and
the deltas named rather than hidden.

---

## 1. Surface inventory and generation

### Current

| Surface | Path | Port | Role |
|---|---|---|---|
| digithings.ai | `apps/digithings-web` | 4012 | marketing site, landing v15 (#4429) |
| digiquant.io | `apps/digiquant-web` | 4011 | quant product: marketing bands **and** the desk |
| dashboard | `apps/dashboard` | 4014 | digiquant operator surface |
| digichat | `apps/digichat` | 3005 | chat product |
| digichat TUI | `clients/digichat-tui` | — | OpenTUI terminal client |
| digiquant TUI | `clients/digiquant-tui` | — | OpenTUI terminal client |
| hero-banner | `packages/hero-banner` | — | pixel wordmark definitions + renderers |
| digiweb | `apps/digiweb` | 4013 | the live design reference + brand studio (local only) |

Ports: `.claude/launch.json:44-107`. All six are npm workspaces
(`package.json:11-14`, `apps/*` + `packages/*`).

The **current generation** is a pixel-terminal one: a 7×10 square-pixel wordmark font
(`packages/hero-banner/src/font.ts:4-8`), 1px hairlines instead of shadows, zero radius,
mono everywhere. Its markers are `PIXEL_7X10` (`font.ts:68`), `.pixel-hero` /
`.pixel-word` (`apps/digithings-web/app/globals.css:886-924`), the desk rail and tiles
(`apps/digiquant-web/app/globals.css:602-700`), and the hero-banner definition table
(`packages/hero-banner/src/definitions/index.ts:498-514`).

One app holds two generations on purpose: `apps/digiquant-web` ships sparse marketing
bands (`app/_bands/*.tsx`, composed in `app/page.tsx:12-24`) next to an instrument-dense
desk (`app/app/**` → `DeskRouteBody`, `app/app/page.tsx:2-11`). Same tokens, two
densities.

### Historical — do not treat as canon

- **`apps/reference`** — the retired 2026-08 blend gallery. It was replaced in October 2026
  by **`apps/digiweb`**, which is now the live design reference (port 4013, local only). The
  old corpus's fifteen specimen families were deleted with it; the current app carries only
  the language pages and the brand work. `c2b133273e chore(design): retire the old
  design-reference corpus (#5677)` is the earlier retirement of its competitor-scan corpus.
  Nothing imports either app.
- **`packages/ui/DESIGN.md`, `packages/ui/PRODUCT.md`** — describe the 2026-08-30
  "utilitarian terminal" v0.1 blend. Correct in spirit, wrong in specific values (§6).
- **`packages/design/{README,BLEND,EVOLUTION,ROLLOUT}.md`** — the blend ledger and its
  promotion plan. `EVOLUTION.md:3` is explicitly "Historical ledger … Do not extend".
- **`apps/digithings-web/app/variants/**`** — retained alternative landings. They are the
  only consumers of `--type-hero` and `--type-section`.

---

## 2. The language

### 2.1 Palette roles

Roles, not a hex dump. Ground → line → ink → signal → money → state → terminal, plus
generated palettes.

| Role family | Tokens | Meaning |
|---|---|---|
| ground | `--bg`, `--surface`, `--surface-2` | page, slab, nested slab. Tonal steps only, never gradients |
| line | `--hair`, `--hair-2`, `--hair-strong` (= alias of `--hair-2`) | the only depth cue; 1px, never 2px |
| ink | `--ink`, `--ink-soft`, `--ink-mute` | primary text, body, meta |
| signal | `--accent`, `--accent-weak`, `--on-accent` | focus, live/selected, chart identity, livery |
| liveries | `--accent-<module>` × 18 | per-module identity, applied via `.accent-<module>` |
| money | `--up`, `--down`, `--warn` | signed P&L only |
| state | `--danger` | non-financial failure red |
| chart | `--chart-sma/ema/vwap/bollinger/...`, `--chart-candle-up/down`, `--chart-grid`, `--chart-axis` | series identity |
| terminal | `--term-bg`, `--term-ink`, `--term-mute`, `--term-hair`, `--term-fill` | terminal-family surfaces |
| heat | `--heat-ink`, `--heat-ink-strong` | contrast-on-heatmap |
| atmosphere | `--grain-opacity`, `--grain-blend` | noise overlay |

Definitions: ground/line/ink/signal/money/state/terminal at `packages/design/tokens.css:68-112`
(dark) and `:114-166` (light); chart aliases `:170-175`; liveries `:8-25` with scope
classes `:53-66`.

Bare `:root` (no `[data-theme]`) sets `--accent: #ffffff` (`tokens.css:27`) — an unthemed
document is ink-on-paper. Themed: teal `#3DD6C4` dark (`:83`) / `#0C7C71` light (`:128`).

32 third-party palettes override the whole role set via `data-palette`
(`packages/design/palettes.css`, generated — header says 32 palettes, `:1-2`; file is
imported first by `tokens.css:1`). The script that generates it also retargets
`.digichat-thread` / `.dc-embed-shell` because those set their own tokens
(`palettes.css:3-6`), and states "Dashboard never sets `data-palette`" (`:6`).

### 2.2 Type

**One voice.** `--font-stack-sans`, `-mono` and `-display` all resolve to the mono face
(`tokens.css:29-31`), and `[data-theme]` makes it explicit: `--font-sans: var(--font-stack-mono)`
(`tokens.css:181-185`). "Sans" is a token name, not a face. Fallback chain: Geist Mono →
`ui-monospace` → SF Mono → Menlo → Consolas → DejaVu Sans Mono.

Two scales coexist:

- **Document scale** (px, comment: "Terminal cells: 11, 13, 16, 20, 28, 40") —
  `--text-xs` 11px, `--text-sm` 13, `--text-md` 16, `--text-lg` 20, `--text-xl` 28,
  `--text-2xl` 40; `--leading-tight` 1.2, `--leading` 1.55 (`tokens.css:225-233`).
- **Editorial scale** — `--type-display: clamp(2.75rem, 6vw, 5rem)`,
  `--type-hero: clamp(2rem, 4.5vw, 2.75rem)`,
  `--type-page-title: clamp(1.5rem, 3vw, 2rem)`,
  `--type-section-stand: clamp(1.6rem, 3.2vw, 2.5rem)`, `--type-section: 1.375rem`,
  `--type-body: 1rem`, `--type-meta: 0.75rem` with `--tracking-meta: 0.08em`
  (`tokens.css:207-215`).

What is actually on screen today is **neither** of those at the top: hero `h1` is
hardcoded `1.5rem` → `1.7rem` at `sm`, weight 600, tracking `-0.02em`
(`apps/digithings-web/components/landing/LandingPage.tsx:55`;
`apps/digiquant-web/app/_bands/top.tsx:37`); band `h2` uses `--type-section-stand` at
weight 500 with `-0.025em` (`.../landing/SectionHead.tsx:23`). `--type-display` is
exercised on digiweb's `/foundations` type ladder, and `--type-hero` only by
`app/variants/**`. The large display clamp is a reference-only value in practice.

Prose: `--measure-prose: 72ch`, `--leading-prose: 1.8`, `--leading-prose-narrow: 1.75`
(`tokens.css:217-219`).

### 2.3 Spacing rhythm

4px base: `--space-1..9` = 0.25 / 0.5 / 1 / 1.5 / 2 / 3 / 4 / 6 / 8 rem
(`tokens.css:37-45`); `--spacing-base: 1.5rem` (`:36`).
Vertical rhythm is two clamps — standard `clamp(4.5rem, 9vw, 8rem)`, tight
`clamp(2.5rem, 5vw, 4rem)` (`:198-199`).
Frames: `--wrap: 1180px`, `--wrap-wide: 1280px`, `--product-frame-w: 800px`,
`--gutter: clamp(1.25rem, 4vw, 3.25rem)` (`:187-190`); chunkier chrome knobs `--rail: 240px`,
`--bar-app: 32px`, `--bar-site: 56px` (`:234-236`).

Drift worth knowing: the landing does **not** use the space scale — it uses arbitrary rem
utilities (`mt-[0.75rem]`, `gap-[0.65rem]`, `py-[1.4rem]`,
`LandingPage.tsx:61-88`). The scale is for shared primitives, not for hand-built bands.

### 2.4 Radii

Zero, everywhere: `--radius-sm/md/lg: 0` (`tokens.css:47-49`) and `--r-sm/md/lg: 0`
(`:192-194`). It is enforced, not merely declared — the desk zeroes a third-party widget
with `border-radius: 0 !important` on every descendant except progress rings
(`apps/digiquant-web/app/globals.css:590-592`).

Surviving circles are geometry only: spinners, live dots, avatars, slider thumbs.

### 2.5 Borders

1px `--hair`, escalating to `--hair-strong` on hover/emphasis. Borders carry all of the
structural information; they are the only separator between bands (`line-b`), rails
(`.rail { border-right: 1px solid var(--hair-strong) }`,
`apps/digiquant-web/app/globals.css:612-621`), and table cells.

Focus is an **outline**, not a ring shadow: `outline: 1px solid var(--ink); outline-offset: 3px`
(`apps/digithings-web/app/globals.css:1051-1053`), `1px`/`2px` offsets on the desk
(`dq globals:595-599`), and a global `:focus-visible { outline: 2px solid var(--accent) }`
(`packages/design/site/site.css:37`).

### 2.6 Depth

There is **no shadow token in `tokens.css`** — `grep -n shadow packages/design/tokens.css`
returns nothing. Depth is hairline + tonal step.

Shadows exist in exactly two places:
- dashboard's single overlay token, `--shadow-overlay: 0 18px 40px -28px rgba(0,0,0,0.6)`
  dark / `-30px rgba(0,0,0,0.18)` light (`apps/dashboard/app/globals.css:135,142`), for
  floating chrome only;
- one dropdown on the landing (`AppFirstSection.tsx:417`) plus `inset` accent marks used
  as selection state (`:44,:448`) — inset marks read as borders, not lift.

Blur is used once, on the nav's scrolled band: `backdrop-filter: blur(14px)`
(`packages/ui/src/styles/nav-shell.css:43-46`). No glass on content.

### 2.7 Motion

One house curve, `--ease: cubic-bezier(0.22, 1, 0.36, 1)` (`tokens.css:196`), upgraded
under `@supports` to an equivalent sampled `linear()` spring with ~15 stops
(`:242-246`) — same curve, smoother interpolation.

| Token | Value | Use |
|---|---|---|
| `--duration-hover` | 180ms | hover/focus transitions |
| `--duration-reveal` | 600ms | scroll reveal |
| `--duration-copied` | 1500ms | copy confirmation |
| `--duration-build` | 1400ms | build-in |
| `--dur-fast` / `--dur` / `--dur-slow` | 120 / 240 / 600ms | document-scale UI |

(`tokens.css:202-205, 237-239`.)

`packages/design/motion.json` mirrors the four durations and adds the frame ticks that
the banner/terminal code runs on: `tick` 40ms, `spinner` 80, `caret` 530, `type` 16,
`clock` 100; `reduced: { duration: 0, frame: null }`.

Hero choreography: text settles via `hero-rise` at 0.7s with a 90ms per-step stagger,
gated behind `prefers-reduced-motion: no-preference`
(`apps/digithings-web/app/globals.css:1032-1041`). The wordmark builds per cell
(`pixel-build` / `pixel-stray` / `pixel-glint`, `:1000-1016`); digiquant's build is sized
in data: 78 columns × 16ms + 360ms rise = 1858ms
(`packages/hero-banner/src/definitions/index.ts:64-76`).

Reduced motion is always "the final state", never "no content": `sampleBanner` returns the
settled frame and no timer (`packages/hero-banner/src/engine.ts:59-61`).

### 2.8 Texture and terminal motifs

- **Pixel grid** — 7×10 cells, 2px strokes, `gap: 2`, square pixels
  (`packages/hero-banner/src/font.ts:4-8,68`). Rendered with `shape-rendering: crispEdges`
  on the kit wordmark (`apps/digithings-web/app/globals.css:910`).
- **Half-block terminal cells** — one cell holds two square pixels: `▀`, `▄`, `█`, or
  `▀` with fg/bg; one colour mode per run (truecolor `38;2` or xterm-256 `38;5`)
  (`packages/hero-banner/src/tui.ts:5-19`).
- **Hairline rules** as the only divider (`line-b`, `border-hair`), never a band fill
  (`LandingPage.tsx:168-208`).
- **Vertical rails** for wayfinding (`SectionRail`; `.rail` with a 1.75rem
  `rail-head`, `dq globals:612-632`).
- **Glyph markers** — `>` user turn, `▸` current/assistant indicator, `·` aside
  (`dq globals:1004`; `clients/digichat-tui/src/theme.ts:17-26` uses `>`, `◆`, `↑`, `■`).
- **Braille spinner** `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏` (`clients/digichat-tui/src/chrome.ts:4`).
- **Hero field** — a live canvas of pixels behind the hero, with a hand-written radial
  vignette `rgb(0 0 0/0.82)` (`apps/digiquant-web/app/_bands/top.tsx:32-33`;
  `.pixel-field`, `dt globals:893-902`).
- **Grain** — an SVG `feTurbulence` overlay is *defined and available*
  (`packages/design/site/site.css:40-44`, tokens `tokens.css:110-111,156-157`) but **no
  live app mounts `.grain`** (only digichat's embed has its own `dc-grain`,
  `apps/digichat/src/app/(digichat)/embed/embed-client.tsx:391`). Treat noise as
  available, not shipped.
- No scanlines, no dither, no gradient headline text, no glass.

---

## 3. Hero banner system

### What a banner is

A word drawn in the 7×10 pixel font, defined **once as data** and painted to three
targets: canvas (web), half-blocks (terminal), and a CSS mask (SSR/no-JS fallback). A
definition is `{ id, text, label, font, gap, palette, animation, live, seed }`; the
engine *enforces* the contract — text must be ALL CAPS, label must be lowercase, glyph
rows must be even, every character needs a glyph, and the palette needs `ink` and
`ground` (`packages/hero-banner/src/engine.ts:19-29`).

Frames are pure in time: the layout and animation state are prepared once per definition
and then sampled (`engine.ts:4-16`).

### The 15 module definitions

`BANNERS` is the registry (`definitions/index.ts:498-514`). Each module gets a distinct
metaphor, not a palette swap.

| # | id | Metaphor | Source |
|---|---|---|---|
| 1 | `digithings` | build sweep with glints and strays | `:32-42` |
| 2 | `digiquant` | columns rise, up/down tones, Vela build timing | `:47-79` |
| 3 | `digichat` | scramble → lock; LIVE = streaming token pass | `:95-114` |
| 4 | `digivoice` | voice meter: syllables, phrases, peak caps | `:478-488` |
| 5 | `digillm` | router: request fans out to lanes, reply returns | `:138-163` |
| 6 | `digibase` | table fills row by row, rows commit to ink | `:168-193` |
| 7 | `digikey` | pin tumbler: key in, pins drop, key turns | `:197-222` |
| 8 | `digigraph` | workflow graph floods along letter strokes | `:227-253` |
| 9 | `digibook` | flipbook riffle; last, slowest turn lays the word | `:258-282` |
| 10 | `digidev` | typed at a prompt (one typo, backspaced), then built | `:288-312` |
| 11 | `digibot` | arcade claw plucks glyphs; one seeded grab slips | `:319-346` |
| 12 | `digivault` | dial turns, bolts slide, leaves part, word lights | `:352-367` |
| 13 | `digisearch` | scan beam finds the word in decoy pixels | `:372-396` |
| 14 | `digitrace` | trace waterfall lanes open and grow right | `:402-426` |
| 15 | `digifetch` | request pixel out, packet stream returns | `:432-456` |

Not in `BANNERS`, deliberately: `DIGIVOICE_BASELINE` (parity reference, `:119-134`),
`DIGIVOICE_VARIANTS` (review previews, `:493-496`), `DIGICHAT_SCRAMBLE` (timing table,
`:82-91`).

The live visual index is the **brand studio** at `/brand` (in
`apps/digiweb`). It renders every registered definition from `BANNERS`, so the
gallery cannot drift from the source.

### Where it appears

- **digithings.ai nav** — `ScrollBanner` on the `digithings` definition, replaying
  LOADING every visit (`apps/digithings-web/app/_nav.tsx:9,17-24`).
- **digiquant.io** — nav (`app/_nav.tsx:7,16`), hero (`app/_bands/top.tsx:6,34`), the
  integrations band (`app/_bands/integrations.tsx:5`), footer
  (`app/_chrome/FooterWordmark.tsx:45`).
- **digithings.ai landing + footer** — the kit's `PixelWordmark`
  (`@digithings/ui/pixel-wordmark`, `LandingPage.tsx:9,53`;
  `.../landing/FooterWordmark.tsx:6,21`), not the package renderer.
- **Terminals** — `clients/digichat-tui/src/{hero-banner,wordmark,hero-preview}.tsx`,
  `clients/digichat-devkit/src/wordmark.tsx`.

Two renderers therefore coexist: the package's canvas path (nav, digiquant bands) and the
kit's rect/SVG path (landing hero, digithings footer). A change to the mark has to be made
in both.

### Sizing and behaviour

- Width is **derived**, never declared: `text.length × font.cols + gaps`
  (`packages/hero-banner/src/web.tsx:37`). The canvas follows its container and keeps
  pixels square and whole at device pixel ratio (`web.tsx:12-13`).
- On-page widths are CSS breakpoint steps: 264 / 352 (≥380px) / 528 (≥640px) / 616
  (≥768px) px (`apps/digithings-web/app/globals.css:904-924`; same steps in
  `top.tsx:34`). Nav marks are 126×18 on digiquant (`_nav.tsx:16`) and `8.5rem` on
  digithings (`_nav.tsx:22`).
- LOADING plays **once per tab / process**, claimed through a store
  (`engine.ts:113-130`; `web.tsx:13`); `replayLoading` forces it per mount for the marks
  that must build with the page (`web.tsx:28-30`, `_nav.tsx:14-16`).
- Repaint cadence: 40ms during LOADING, the definition's `liveTickMs` when live, `null`
  (timer stops) when still (`engine.ts:76-80`).
- `armed=false` holds the banner blank until a scroll trigger lets it start —
  used by footer marks (`web.tsx:15,66`).
- Terminal fit clips to the available columns/rows (`terminalFit`,
  `engine.ts:82-84`), and half-blocks halve the vertical resolution (`tui.ts:63-70`).
- Determinism: seeded `mulberry32`, with seeds pinned per definition
  (`layout.ts:6-14`; e.g. `seed: 0xd161` at `definitions/index.ts:41`) so a ported mark
  draws the same cells.

### Fallback rules

This subsystem is the strictest in the codebase; keep all four paths.

1. **Reduced motion** → the settled mark, no timer
   (`engine.ts:59-61`; web matchMedia at `web.tsx:67-68`). Terminals honour `NO_MOTION`
   or `HERO_BANNER_MOTION=reduce|off|none` (`engine.ts:95-105`).
2. **No canvas / SSR / no JS** → the settled frame serialised as a CSS mask whose colour
   is `var(--ink)`, so the fallback follows the theme instead of baking a hex
   (`packages/hero-banner/src/ssr.ts:1-14,109`; applied at `web.tsx:38-61`). The fallback
   is the *same* frame the still banner draws, not an approximation.
3. **LIVE off** → settles after LOADING and stays (`engine.ts:45-48`).
4. **Colour mode** → terminal picks truecolor only when `COLORTERM` says so, otherwise the
   256 cube (`tui.ts:16-19`), and a definition may carry both a `hex` and a `cube`
   (`definitions/index.ts:28-29`).

---

## 4. Per-surface deltas

What is shared: tokens, zero radius, hairlines, the mono voice, `--ease`, the pixel
mark. What differs is density, chrome, and how much colour is spent.

**digithings.ai (persuade).** Centred `max-w-[64rem]` hero on a pixel field; wordmark,
claim, one-line subhead, then a clone-command box beside two ghost CTAs and a
lowercase slash-separated meta row (`LandingPage.tsx:48-104`). Bands separated by
`line-b` hairlines, each `px-[var(--page-pad)] py-[var(--page-step)]`, with a vertical
section rail for wayfinding (`sections.ts:4-12`). No eyebrow kickers, no alternating
band fills (`SectionHead.tsx:20-32`). Sparse.

**digiquant.io marketing (persuade, but fuller).** Same grammar, different hero: full
`100svh` chart field under a transparent nav, then wordmark, claim, subhead, two ghost
CTAs (`top.tsx:26-55`). One file per band, so a pass touches one section
(`app/page.tsx:1-24`).

**digiquant desk (operate, instrument density).** A terminal shell: 200px rail
(`--rail-w`, default 200px) with a 1.75rem `rail-head`, hairline borders, no radius,
desk tiles that ease to new rects on the 0.5s mosaic timing (`dq globals:602-700`),
mono at 0.6875–0.75rem for chrome (`:629,648`), `--term-*` surfaces for panes (`:608-610`).
Third-party embeds are forcibly squared (`:590-592`). This is where the "terminal" claim
is literally true.

**dashboard (operate, instrument density, different loader).** Mono-only: it is the only
app that loads no sans face (`packages/design/README.md:103`), and it re-states the font
roles itself (`apps/dashboard/app/globals.css:121-127`). Charts are flat and token-themed:
`--chart-grid` hairline grid, `--ink-mute` axes (`:193-200`), one overlay shadow
(`:135`). Migration in progress: the Today page mounts `BriefDesk` behind
`deskShellEnabled()` and otherwise a legacy brief (`app/page.tsx:27-31`).

**digichat (operate).** An app shell, not a bare scrollback: `aside.app-sidebar` +
`header.app-topbar` + main column (`apps/digichat/src/components/chat-shell.tsx:452,615-618`).
Inside, the thread is still bubble-free: marker + body grid rows, one continuous
scrollback (`packages/ui/src/styles/chat-core.css:5,61,164`). Composer radius is pinned
to 0 (`chat-digichat.css:22`) and every rule in that sheet is mono
(`chat-digichat.css:49,59,115,400,483,561,615,740`). The app's own `globals.css` is 29
lines that delegate to the shared theme bridge (`app/(digichat)/globals.css:6`).

**TUI (operate, same palette, different glyphs).** Exact web hexes, restated in TypeScript
(`clients/digichat-tui/src/theme.ts:1-11`), so the terminal matches the dark theme.
Glyph substitutions stand in for the web's 5×5 cube icons (`theme.ts:13-26`); the thread
has four tones — ink / soft / mute / danger (`chrome.ts:9`); half-block rendering and
one colour mode per run (`packages/hero-banner/src/tui.ts:5-19`).

**The intentional differences, stated plainly**

1. **Density**: sparse marketing vs instrument desk (`BLEND.md:59` codifies the split;
   realized by `LandingPage.tsx:168-208` vs `dq globals:602-700`).
2. **Hero geometry**: full-viewport chart vs centred 64rem column (`top.tsx:30` vs
   `LandingPage.tsx:52`).
3. **Wordmark renderer**: canvas definitions vs kit SVG rects (see §3).
4. **Chrome**: ghost nav with a dropdown group (`_nav.tsx:37-53`) vs rail + command/path
   field (`dq globals:602-689`).
5. **Chat shape**: app sidebar shell outside, bubble-free rows inside
   (`chat-shell.tsx:452` vs `chat-core.css:5`).
6. **Terminal**: simplified glyphs, 2:1 cells, no fonts at all (`theme.ts:13-16`,
   `tui.ts:5-9`).
7. **Colour spend**: the site holds accent back almost entirely; the desk uses `--up` /
   `--down` for values and `--term-*` for panes (`dq globals:608-617`).
8. **Nav height**: one knob, two names — `--nav-shell-h: 62px` with `--dq-nav-h` as a
   deliberate alias so historical `pt-[var(--dq-nav-h)]` offsets cannot drift
   (`apps/digithings-web/app/globals.css:208-218`).

---

## 5. Copy voice

Evidence: `apps/digithings-web/app/about/page.tsx`, `.../components/landing/LandingPage.tsx`,
`apps/digiquant-web/app/_bands/top.tsx`, page metadata, and the (partly stale)
`packages/design/COPY_GUIDE.md`.

**Sentence length.** Short. Hero subheads are one line, 10–14 words
("Chat, research and quant modules on your own keys and hardware.",
`LandingPage.tsx:64`). Property/lede bodies are 12–20 words
(`about/page.tsx:28-43`). Nothing I read runs over ~25 words.

**Casing.** Sentence case for headings and titles, including h1s: "Infrastructure, not a
product." (`about/page.tsx:64`), "AI infrastructure, in a glass box you own."
(`LandingPage.tsx:58`), "Open source, and still shipping" (`:176`), "Built to compose"
(`about:82`). No title case anywhere I read.

**Punctuation.** Full stops on sentences; the second sentence of a claim often shortens to
a fragment ("Take one piece and leave the rest.", `about:83`). Meta rows are lowercase and
slash-separated, no commas: `self-hosted / your own keys / no hosted tier`
(`LandingPage.tsx:42,91-96`). CTAs carry no trailing period and no arrow-stapled verb:
"Read the docs", "GitHub", "Modules", "Open the terminal" (`:77,80,140`; `top.tsx:48-51`).
Em dashes appear in metadata, not in body copy (`page.tsx:20`).

**Person and tense.** Second person, ownership-framed: "you own", "your own keys",
"the stack you already run" (`LandingPage.tsx:58-64`; `page.tsx:22-24`). First person
plural only for what the company sells: "What we sell is the integration work"
(`LandingPage.tsx:128`). Present tense for what ships; the future is reserved for clearly
flagged roadmap (`LandingPage.tsx:26-28`).

**Mono register.** Lowercase names, no marketing adjectives, `digi` names never
capitalised (`AGENTS.md:135-154`; `COPY_GUIDE.md:16`).

**Banned — explicit, in-repo:**

- naked "Get started" CTAs; CTAs name their literal destination (`COPY_GUIDE.md:18`).
- fabricated proof — real data only (`COPY_GUIDE.md:19`).
- performance figures, a live-trading promise, and hosted MCP stated as shipped
  (`LandingPage.tsx:26-28`: "no performance figures, open weights 'at par or close', no
  live-trading promise, hosted MCP spelled as roadmap").
- Digi names in CamelCase or with a space (`AGENTS.md:135-154`).
- serif as the marketing hero face (`COPY_GUIDE.md:20`).

**Banned — conspicuous absence, scoped to what I read.** No exclamation marks, no
"revolutionary / powerful / seamless / effortless / elevate / unlock / supercharge", no
"empower", no three-adjective rhythm. This is an observation over ~6 files, not a
repo-wide sweep.

**Voice in three words:** *plain, owned, checkable.* "Every request carries one id through
every service, and each step lands in an audit log you keep." (`about:41-42`) — concrete,
second person, verifiable.

---

## 6. Contradictions

Claims in the old docs that the live code no longer supports. Both sides cited.

| # | Old doc claim | Live code | Verdict |
|---|---|---|---|
| 1 | `packages/ui/DESIGN.md:12` — `ink-mute: "#6B7177"` | `tokens.css:81` — `--ink-mute: #7D8389` | wrong value |
| 2 | `DESIGN.md:163` — light ink-mute `#8A9097` | `tokens.css:126` — `#666C73` | wrong value |
| 3 | `DESIGN.md:33,184` — display `clamp(2rem, 5vw, 3.4rem)` | `tokens.css:207` — `--type-display: clamp(2.75rem, 6vw, 5rem)`; no live app consumes it, only digiweb's `/foundations` ladder | wrong value, and describing a dead token |
| 4 | `DESIGN.md:36` — display tracking `-0.04em` | `LandingPage.tsx:55`, `top.tsx:37` — `-0.02em`; band heads `-0.025em` (`SectionHead.tsx:23`) | wrong value |
| 5 | `DESIGN.md:327` — focus is `outline: none` + a 2–4px accent **box-shadow** ring | `dt globals:1051-1053` and `dq globals:595-599` — `outline: 1px solid var(--ink)`; global `outline: 2px solid var(--accent)` (`site.css:37`) | wrong mechanism |
| 6 | `DESIGN.md:54-57` — spacing `control 0.6 / card 1.2 / generous 1.6rem` | `tokens.css:37-45` — `--space-1..9` = .25/.5/1/1.5/2/3/4/6/8rem; the landing uses arbitrary rem (`LandingPage.tsx:61-88`) | scale does not exist |
| 7 | `DESIGN.md:28-29` — declares `diff-add` / `diff-del` | no `--rv-add` / `--rv-del` anywhere in `packages/design` or `packages/ui` | token family absent |
| 8 | `DESIGN.md:220` — `--type-hero` "reserved for a landing hero" | hero h1 is hardcoded 1.5/1.7rem (`LandingPage.tsx:55`); `--type-hero` is used only by `app/variants/**` | rule not followed |
| 9 | `DESIGN.md:312` — "one sans-serif island … the composer's live textarea" | `tokens.css:181` makes `--font-sans` the mono stack; the composer rules are `var(--font-mono)` (`chat-digichat.css:49,115`) | cannot exist |
| 10 | `DESIGN.md:306` — the wordmark's suffix "is always the accent-colored emphasis" | marks are single-tone ink; accent is the transient glint (`dt globals:909-911`; `definitions/index.ts:38` maps accent to `--glint`) | wrong |
| 11 | `PRODUCT.md:40` — "one motion moment per surface" | landing runs hero-rise stagger + continuous pixel field + per-cell build/glint + scroll `Reveal` + a scroll-driven FAQ morph (`dt globals:1032-1041`; `LandingPage.tsx:51,119,122,207`) | wrong |
| 12 | `PRODUCT.md:29`, `ROLLOUT.md:12` — digiweb is "the live, browsable canon … first place to check", Phase 0 | resolved in October 2026: the old corpus was replaced by `apps/digiweb`, which is the live reference again | superseded |
| 13 | `BLEND.md:85` — "Do not synthwave / **pixel wordmarks**" | the hero *is* a pixel wordmark: `font.ts:68`, `LandingPage.tsx:53`, `definitions/index.ts:32-42`, `.pixel-word` (`dt globals:904-924`) | outright reversed |
| 14 | `BLEND.md:66`, `ROLLOUT.md:20` — one white (paper) **filled** rect per viewport | both heroes ship two ghost CTAs and a clone box, no filled rect (`LandingPage.tsx:70-84`; `top.tsx:47-52`) | rule not followed |
| 15 | `COPY_GUIDE.md:60` — "Keep `// section` mono eyebrows on marketing" | `SectionHead` renders title + lede only, no kicker (`SectionHead.tsx:20-32`); `DESIGN.md:211` explicitly says "no eyebrow kickers" — the docs also contradict each other | double contradiction |
| 16 | `DESIGN.md:193,329` — five glyphs, "never invent a sixth or reuse one across registers" | more than five ship, and `▸` is reused: as the open-thread marker (`dq globals:1004`, `components/desk/chat-threads.tsx:7`) and as a collapse indicator (`apps/dashboard/components/overview/today-actions-panel.tsx:187`); the TUI adds `◆` example, `↑` send, `■` stop (`digichat-tui/src/theme.ts:17-26`) | rule already exceeded |
| 17 | `ROLLOUT.md:48` — heroes "keep the existing mesh composition" | heroes are a canvas pixel field, no mesh (`LandingPage.tsx:51`; `.pixel-field`, `dt globals:893-902`) | superseded |

Two more, from code comments rather than docs, worth fixing when touched:

- `packages/hero-banner/src/definitions/index.ts:31` points at
  `apps/digithings-web/components/landing/PixelWordmark.tsx`, which moved to
  `@digithings/ui/pixel-wordmark` (DIG-3695, `LandingPage.tsx:9`).
- `LANDING_SECTIONS` (`sections.ts:4-12`) labels the first band "stack" while its id is
  `architecture` (`ModuleGrid.tsx:92`) — the rail and the anchor disagree on the name.

---

## 7. Anti-slop rules for this product

### Never introduce

**Shape and depth**
- Any border radius outside geometry (`tokens.css:47-49,192-194`; enforced on embeds at
  `dq globals:590-592`).
- A drop shadow on content. Shadow means "floating overlay" or nothing.
- Glass / glassmorphism on content; the one blur is the scrolled nav band
  (`nav-shell.css:43-46`).
- Pills, soft cards, "friendly" rounding, icon-inside-a-rounded-square.

**Colour**
- Gradient headlines, mesh gradients, floating blobs, gradient hero backgrounds.
- Purple/indigo, violet washes, synthwave palettes, multi-accent chrome.
- `--accent` as a primary CTA fill. Loud = ink/paper rect; accent = focus, live, identity.
- A second module livery in the same view.
- A new colour that does not route through an existing role. `--up`/`--down`/`--warn` are
  P&L-only and never follow a livery.
- Hardcoded hex in surface code. The documented exception is a banner palette, which is
  renderer data, not a theme (`definitions/index.ts:102-106`).

**Type**
- A second typeface. No sans display, no serif marketing hero, no Inter.
- Decorative all-caps mono labels as chrome; uppercase survives only for Fig captions and
  table headers (`DESIGN.md:220`).
- Display-size hero type on a product page — hero `h1` is 1.5–1.7rem (`LandingPage.tsx:55`).

**Structure and motif**
- Bubbles or boxes around chat turns (`chat-core.css:5`).
- Alternating band fills or background changes to separate sections — use a hairline.
- Decorative `01 / 02 / 03` numbering, testimonial triads, centered-hero-over-three-cards.
- Eyebrow kickers on public pages (`DESIGN.md:211` overrides `COPY_GUIDE.md:60`).
- A new banner module without a `BANNERS` entry, a seed, and the parity/tick tests.

**Copy**
- Emoji, exclamation marks, superlatives, "elevate/unlock/supercharge/seamless".
- "Get started" without a named destination (`COPY_GUIDE.md:18`).
- Unverifiable claims: no performance figures, no live-trading promise, no "at parity"
  without the qualifier.

### Always preserve

1. **Hairline + tonal step as the only depth cue**, zero radius on all chrome.
2. **One mono voice** — including keeping "sans" tokens resolving to mono
   (`tokens.css:181`). The moment a real sans face appears, the system is a different one.
3. **Ink/paper as the loud control, accent as state** (`DESIGN.md:113`; realized in
   `HERO_ACTION` ghost styling, `LandingPage.tsx:38-39`).
4. **Money colours fenced from livery** (`tokens.css:87-89`; `DESIGN.md:155`).
5. **Bubble-free transcript**: marker + body rows, one continuous scrollback
   (`chat-core.css:5,61,164`).
6. **The settled mark as every non-animated fallback** — reduced motion, SSR, no-JS all
   show the same final frame (`engine.ts:59-61`; `ssr.ts:1-14,109`).
7. **Reduced motion is the final state, never a blank or a spinner** (`engine.ts:59-61`;
   `motion.json`: `reduced.duration = 0`, `reduced.frame = null`).
8. **The 7×10 grid and 2px strokes** for any brand mark (`font.ts:4-8`).
9. **Lowercase digi names** in every string, heading, and commit (`AGENTS.md:135-154`).
10. **Hairline rules between bands**, no band fills (`line-b`, `LandingPage.tsx:168-208`).

---

## 8. Evidence table

| Claim | Evidence |
|---|---|
| Tokens are the single source for colour, type, space, motion | `packages/design/tokens.css:2-4` |
| 18 module liveries exist, scoped by class | `tokens.css:8-25`, `:53-66` |
| Money tokens are literals, not accent references | `tokens.css:87-89` |
| Terminal family has its own palette | `tokens.css:104-108`, `:149-154` |
| Chart tokens alias role tokens | `tokens.css:170-175` |
| `--font-sans` resolves to mono | `tokens.css:181-185` |
| Two type scales (document px + editorial clamp) | `tokens.css:207-215`, `:225-233` |
| Radius is 0, twice-declared | `tokens.css:47-49`, `:192-194` |
| Spacing is a 4px-based 9-step scale | `tokens.css:37-45` |
| Section rhythm is two clamps | `tokens.css:198-199` |
| House easing + `linear()` upgrade | `tokens.css:196`, `:242-246` |
| Four named durations + three document durations | `tokens.css:202-205`, `:237-239` |
| Frame ticks and reduced-motion contract | `packages/design/motion.json:1-6` |
| 32 generated palettes, dashboard excluded | `palettes.css:1-6` |
| No shadow token exists | `grep -n shadow tokens.css` → none |
| One overlay shadow, dashboard only | `apps/dashboard/app/globals.css:135,142` |
| Focus is an outline, not a ring shadow | `apps/digithings-web/app/globals.css:1051-1053`; `site.css:37`; `dq globals:595-599` |
| Grain is defined but unmounted | `site.css:40-44`; `tokens.css:110-111` |
| Nav blurs after 8px, yields past 180px | `packages/ui/src/styles/nav-shell.css:27,43-46` |
| Landing bands are hairline-separated, no kickers | `LandingPage.tsx:168-208`; `SectionHead.tsx:20-32` |
| Hero h1 is 1.5/1.7rem at -0.02em | `LandingPage.tsx:54-59`; `top.tsx:35-41` |
| Hero field is canvas with a radial vignette | `LandingPage.tsx:51`; `top.tsx:32-33` |
| Pixel word sizes: 264/352/528/616 | `dt globals:904-924` |
| digiquant hero is 100svh | `top.tsx:30` |
| Desk rail + tiles + forced-zero embeds | `dq globals:590-592`, `:602-700` |
| Desk transition is 0.5s on `--ease` | `dq globals:693-699` |
| Dashboard charts: hairline grid, mute axes | `apps/dashboard/app/globals.css:193-200` |
| Dashboard is the only mono-only loader | `packages/design/README.md:103`; `dashboard/app/globals.css:121-127` |
| Chat shell = sidebar + topbar + main | `apps/digichat/src/components/chat-shell.tsx:452,615-618` |
| Transcript is marker+body rows, no bubbles | `packages/ui/src/styles/chat-core.css:5,61,164` |
| Composer radius 0, mono | `chat-digichat.css:22,49,115` |
| TUI palette mirrors the web hexes | `clients/digichat-tui/src/theme.ts:1-11` |
| TUI glyph substitutions | `theme.ts:13-26`; `chrome.ts:4,9` |
| Banner contract is enforced at runtime | `packages/hero-banner/src/engine.ts:18-29` |
| Reduced motion → settled frame | `engine.ts:46-61,95-105` |
| One LOADING play per session | `engine.ts:113-130` |
| SSR fallback is a themed CSS mask | `packages/hero-banner/src/ssr.ts:1-14,109`; `web.tsx:38-61` |
| Width is derived from text and gap | `web.tsx:37` |
| 15 modules in the registry | `definitions/index.ts:498-514` |
| Half-block cells, one colour mode per run | `packages/hero-banner/src/tui.ts:5-19` |
| 7×10 font, 2px strokes | `packages/hero-banner/src/font.ts:4-8,68` |
| Seeded determinism | `layout.ts:6-14` |
| Reference is a workspace but retired | `package.json:11-14`; `.claude/launch.json:72-81`; commit `c2b133273e` |
| Copy honesty rules | `LandingPage.tsx:26-28` |
| CTA destinations must be literal | `packages/design/COPY_GUIDE.md:18` |
| Lowercase digi names | `AGENTS.md:135-154` |

---

## 9. What I could not determine

Recorded rather than guessed, so the next slice does not inherit an invented rule.

- **Whether every digiweb route survives a full `next build`.** I ran the dev server and the
  route/nav tests, not `next build`. The old app's static export was blocked by a pre-existing
  `/effects` function-prop error; that route was deleted with the corpus, so the new app should
  export cleanly, but that is unverified here.
- **Anything that needs a rendered page**: actual contrast ratios, optical alignment,
  whether the composer really looks mono in the browser (the CSS says mono and
  `--font-sans` resolves to mono, but a UI-lib default could still apply a sans face),
  and whether the grain overlay is visible in the digichat embed.
- **Whether `--type-display`, `--grain-*`, `--bar-app`, `--bar-site`, `--product-frame-w`
  are intended to be revived or are dead.** No ADR or consumer found for the display clamp
  or the grain outside digiweb's `/foundations` ladder.
- **Dashboard structure beyond the page loader.** I read `app/page.tsx:27-31` and its
  `globals.css`; I did not open `BriefDesk`'s panes, so the "command band then ledger"
  shape in `DESIGN.md:201` is unverified for the current panes.
- **Which of the 32 palettes each surface exposes.** `palettes.css` is global, but the only
  switcher evidence I saw is digichat's `/theme` (commit `40729ef8c3`). digiquant-web may
  or may not expose it.
- **`tabular-nums` coverage.** `DESIGN.md:186` claims tabular numerals "wherever a digit
  might change"; I did not sweep tables and charts for it.
- **`packages/hero-banner/README.md` does not exist**, although the brief lists it. The
  package's `package.json:12` points at `docs/architecture/hero-banner-spec.md` — I did
  not open that spec, so any rule it states is not reflected here.
