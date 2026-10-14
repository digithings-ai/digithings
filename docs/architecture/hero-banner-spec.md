# Hero banner spec (`@digithings/hero-banner`)

Status: proposed (DIG-2864). Approver: Chris (L lane).

One banner definition renders the module mark in a terminal (half-blocks,
OpenTUI) and on the web (canvas). Every module banner ticket builds on this
package. Do not make a new wordmark component for one surface.

## Rules

- Banner text is ALL CAPS. This is the hero-banner exception. Everywhere
  else, module names are lowercase (`digithings`, `digichat`, ...). The
  accessible label is the lowercase name.
- The family look is terminal pixel/ASCII. A module can use its own font or
  its own glyph overrides, but every glyph must render in a terminal: a
  fixed pixel grid with an even number of rows (two pixels for each
  half-block row).
- The terminal is the reference surface. A banner must render and animate
  in OpenTUI at 120x30 and at 80x24 before it gets web integration.

## Definition format (`src/types.ts`)

| Field | Meaning |
|---|---|
| `id` | Module id, lowercase. Keys the "LOADING played" flag. |
| `text` | ALL CAPS banner text. Every character must have a glyph. |
| `label` | Accessible name (`aria-label` on the web). |
| `font` | `PixelFont`: `{ cols, rows, glyphs }`. Rows are `#` (lit) and `.` (empty). Family default: `PIXEL_7X10`. |
| `glyphs` | Optional per-module overrides on top of `font` (digiquant uses this for A and Q). |
| `gap` | Preferred empty columns between glyphs. Narrow surfaces drop to 1, then 0. |
| `palette` | Named `Tone`s `{ hex, cube, cssVar? }`. `ink` and `ground` are required. `hex` is used for truecolor and canvas, `cube` for xterm-256, and `cssVar` lets the web follow the page theme. |
| `animation` | An `Animation` recipe (see below). |
| `live` | LIVE default (on/off). A surface can override it. |
| `seed` | Seed for every random choice. Frames are deterministic. |

`assertDefinition` enforces these rules. The engine calls it once for each
definition.

## Animation API

An animation is `{ kind, prepare, loadingMs, loading, live, still, liveTickMs }`.

- `prepare(layout, def)` runs once for each definition (cached) and uses only
  the seeded PRNG (`mulberry32`).
- `loading(state, t)` gives the LOADING (intro) frame `t` ms after mount, for
  `0 ≤ t < loadingMs(state)`.
- `live(state, tLive, tMount)` gives the optional LIVE (idle) frame.
- `still(state)` gives the settled mark. It is used for reduced motion and
  for live off.
- Frames are pure functions of time, in glyph-pixel space at the
  definition's gap. Each pixel is `{ tone, alpha }`. The engine repacks the
  frame to a smaller gap and upscales it by an integer factor for the
  surface. Animations never know the surface size.

The four recipes in this package are:

| Kind | Used by | LOADING | LIVE |
|---|---|---|---|
| `build` | digithings | Cells step in through opacity steps, plus strays | Glints |
| `rise` | digiquant | Column sweep with eased rise and up/down tones, plus strays | Glints and blinking strays, each in its own up or down tone (both colours always; never the accent) |
| `scramble` | digichat | Letters spin, lock and flash | `stream` (digichat): every ~7 s the word drops to its dim ghost and streams back left to right in seeded tokens of 1–3 letters, 70–190 ms apart, each landing with a flash. `flash` (legacy): one letter flashes every `idleGapMs` |
| `equalizer` | digivoice | Amplitude envelope over `buildMs` | Equalizer columns |

To add a module, write a definition. Write a new recipe only when no
existing one fits.

## Engine (`src/engine.ts`)

- `sampleBanner(def, { t, live?, motion?, skipLoading?, gap?, scale? })`
  returns `{ frame, phase, gap, scale }`. The phase is `loading`, then `live`
  (when LIVE is on), otherwise `still`.
- `nextTickMs(def, phase)` gives the time to the next repaint: 40 ms while
  loading, `liveTickMs` while live, and `null` when still (stop the timer).
- `resolveMotion({ env, prefersReduced })` returns `reduced` when any of
  these is true: `prefers-reduced-motion`, `NO_MOTION` is set and not `0`,
  or `HERO_BANNER_MOTION=reduce|off`.
- `resolveLive(def, { env, config })` resolves LIVE in this order: the
  surface config, then `HERO_BANNER_LIVE=0|1|on|off`, then `def.live`.
- `claimLoading(def, store)` makes LOADING play once per session. On the
  web, the store is `sessionStorage` (`hero-banner:<id>:played`). In the
  TUI, a process-level origin map keeps the clock across remounts.

## Renderers

- Terminal (`src/tui.ts`): `bannerLines(def, { cols, rows?, mode, t, ... })`
  returns half-block cells. A pixel pair becomes `▀`, `▄` or `█`; when the
  two colours differ, it becomes `▀` with fg = top and bg = bottom. Alpha
  blends onto `ground`. The run uses one colour mode, chosen from
  `COLORTERM`: truecolor (`38;2`) or xterm-256 (`38;5`), never mixed. The fit
  uses `cols − 2`. If the scaled mark takes at most half the rows, it is
  scaled up ×3 or ×2. Otherwise the gap shrinks to 0. If the mark still does
  not fit, the output is the text on one line. `toAnsi` and `toPlain`
  serialise the cells.
- OpenTUI (`clients/digichat-tui/src/hero-banner.tsx`):
  `<HeroBanner def cols rows? live? scale? holdMs? align? env? />`. The
  component lives in the client, because bun resolves `@opentui/*` from the
  importing file and the package has no dependencies. `holdMs` freezes one
  moment for snapshots and tests.
- Canvas (`src/canvas.ts`): `paintFrame(ctx, frame, { pixel, colors })`
  draws one square for each lit pixel at its alpha. `toneColors` resolves
  `cssVar` tones.
- Web (`src/web.tsx`): `<HeroBanner def live? armed? gap? className />`. It
  draws on a canvas, follows the device pixel ratio, uses `role="img"` with
  `aria-label` set to `label`, follows `matchMedia('(prefers-reduced-motion)')`,
  claims LOADING from `sessionStorage`, and runs a timer driven by
  `nextTickMs`. It renders from the same definition object as the TUI.

## Ported banners (no visual regression)

| Module | Legacy source | Proof |
|---|---|---|
| digithings | `apps/digithings-web/components/landing/PixelWordmark.tsx` (seed `0xd161`) | `test/parity.test.ts`: every cell, timing, opacity step, glint and stray equals a copy of the legacy generator |
| digiquant | `QuantWordmark.tsx` on #4986 + #5416 (seed `0x9a17`) | Same check against the legacy `build()`: cells, rise, tone, glint, strays, blinks; plus sampled LOADING and LIVE frames hold both up and down |
| digichat | `packages/ui/src/components/chat/digichat-wordmark.ts` | Every 40 ms frame for 0–20 s at 120, 80 and 70 cols, in both colour modes, equals `heroWordmarkLines` with LIVE `flash`. `DIGICHAT` (LIVE `stream`, DIG-2865) equals it through LOADING |
| digivoice | `digivoice/tui/src/hero.js` (#4965) | Every 60 ms frame for 1.4–8 s, in both colour modes, equals `wordmarkLines`. The still frame equals hero.js at `tMs = 1400` |

digichat-tui now draws its header with `HeroBanner` (`wordmark.tsx`).
`DIGICHAT_WORDMARK_MS` still freezes it.

Acceptance (`clients/digichat-tui/src/hero-banner.test.tsx`): all four
banners render in OpenTUI at 120x30 and at 80x24 as five half-block rows
inside the terminal width. LOADING frames change over time, reduced motion
is constant, LIVE keeps moving, and `HERO_BANNER_LIVE=0` settles.

## Decisions (cheap to reverse)

1. digivoice LOADING is an amplitude envelope over `buildMs = 1400`. hero.js
   had no intro; its default frame was `tMs = 1400`.
2. In the terminal, the digiquant rise shows as opacity, because a cell
   cannot scale on Y. The canvas can draw the true rise in a later change;
   the cell parameters are already in the state.
3. The digiquant hero chart (`hero-build` / `hero-feed` / `hero-series`)
   stays in digiquant-web. It is not part of a banner, but its column timing
   uses the same `startMs` / `columnMs` as the definition.
4. The package has no runtime dependencies. React is an optional peer, used
   only by `./web`.

## Follow-ups

- Port the web consumers onto `./web`: the digithings-web `PixelWordmark` and
  `FooterWordmark`, the digiquant `QuantWordmark` (after #4986 lands), and
  the digichat web `DigichatWordmark`.
- Port the digivoice TUI hero and its Python and Lua copies to the shared
  definition. A non-JS runtime can read a JSON export of the definition plus
  frames.
- Retire `packages/ui/.../digichat-wordmark.ts` after the web consumer moves.
