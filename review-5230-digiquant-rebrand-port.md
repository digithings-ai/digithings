# Review — PR #5230, digiquant.io rebrand port (DIG-1599)

| | |
|---|---|
| **Reviewer** | fresh-context review subagent (`ses_eed071eb9ffePBvm6JbCaLJQ1m`) |
| **Author** | separate session (Frontend agent, DIG-1599) |
| **Subject** | PR #5230, `de88c7226` → `fix` commit on `DIG-1599-digiquant-rebrand-port` |
| **Range** | `origin/develop` (`e1f42ca07`) … review head |
| **Verdict** | `changes-requested` → all 3 majors + 2 minors fixed in this branch |
| **Severity** | 3 major, 3 minor, 5 nit raised → 3 major + 2 minor fixed, 3 nit fixed as a side effect, 3 nit not actioned (justified below) |

Scope: 20 files, +697/−500. A port of the abandoned branch
`cursor/digiquant-section-new-brand-dev-1a1c` (19 files, +661/−500) plus one new
regression test. Presentation-only frontend.

---

## Fixed on this branch

### Major 1 — fixed band height truncated the enlarged footer wordmark

`apps/digithings-web/app/globals.css:939`

`.pixel-word-band` gained a **fixed** `height: clamp(4.5rem,12vw,9rem)` (144px max)
while `overflow-x: clip` was widened to `overflow: clip`. The wordmark is an SVG with
`viewBox="0 0 88 10"` (`PixelWordmark.tsx:105`), so its height is always `width / 8.8`.
At the enlarged footer width the mark outgrows the band and lost its top and bottom
glyph rows — every desktop viewport ≥1400px. On develop the band was
`padding: clamp(3rem,8vw,6rem) var(--page-pad) 0` with `overflow-x: clip` and never
clipped.

Measured in Chrome (exact pre/post rules, real `viewBox`, real
`--gutter: clamp(1.25rem,4vw,3.25rem)`), `cutPx` = rows of the mark lost off the top
and bottom:

```
iw     POST band  mark       cutPx  rowsLost || PRE(develop) band  cutPx
1280   144       1178x134    0      0.00     || 230                 0
1440   144       1336x152    8      0.51     || 248                 0
1512   144       1408x160    16     1.00     || 255                 0
1600   144       1496x170    26     1.50     || 255                 0
1728   144       1600x182    38     2.08     || 255                 0
1920   144       1600x182    38     2.08     || 255                 0
```

Fix: `height` → `min-height`, and `overflow: clip` → `overflow-x: clip` so the band
grows with the mark and only the deliberate horizontal bleed is clipped.

### Major 2 — `width: min(118%,1600px)` was inert

`apps/digithings-web/app/globals.css:950`

`.pixel-word-band` became `display: flex` and `.pixel-word-footer` kept its default
`flex-shrink: 1`, so the 118% hypothetical main size folded straight back to the band
width. The only real enlargement was the 1400→1600px cap change, which only bites
above a 1656px viewport. Computed styles confirmed it: mark `1177.61px` against a
`1389.6px` 118% hypothetical, `flex-shrink: 1`.

Fix: `flex-shrink: 0` on `.pixel-word-footer`. Fixed together with major 1 —
enlarging the mark while the band was still a fixed 144px box would have made the
clipping strictly worse.

### Major 3 — the pipeline rail was keyboard-unreachable (WCAG 2.1.1)

`apps/digithings-web/components/landing/QuantSection.tsx:172`

19 phase cards (real copy: names plus one-line mechanisms) sat inside
`overflow-x-auto` with no `tabIndex` and no focusable descendants, replacing develop's
wrapping `<ol>` where everything was reachable without scrolling. A keyboard-only
reader lost 16 of the 19 phase descriptions. This violates a contract the repo already
states, in the sibling rail in the same component:

```
packages/ui/src/components/data-layout/CardRail.tsx:30-31
  "Arrows are a convenience, not the only way through: the track is focusable and
   scrolls with the keyboard, and it is the sanctioned mobile fallback..."
packages/ui/src/components/data-layout/CardRail.tsx:173
  tabIndex={0}
```

Fix: `tabIndex={0}` on the rail, with a comment citing the CardRail contract.
Browser auto-focus of scrollers (Chrome 127+/FF 132+/Safari 18.4) mitigates this on
new browsers only and does not satisfy the in-repo contract.

### Minor 4 — rest-glide rAF loop ran off-screen with no visibility guard

`packages/ui/src/components/diagrams/ArchitectureTour.tsx:685`

`beginRest` started a ~31-frame `requestAnimationFrame` loop after **every** scroll
stop, wherever the reader stopped. Each frame does two `getBoundingClientRect()` reads
plus two `offsetHeight` reads and writes per-camera transforms. The effect is gated
only on `mode !== "static"` (`ArchitectureTour.tsx:455`), so it was live for every
reduced-motion-clean visitor ≥1024px regardless of scroll position — a reader who
stopped at the top of the page paid a forced-reflow loop for a tour thousands of px
below. Develop had no such loop.

Fix: early return when the pin's box is outside the viewport.

### Minor 5 — the test did not pin the smoothstep it claimed to

`packages/ui/src/motion/scroll-glide.test.ts:33`

The test is named "smoothsteps across the glide", but a linear ramp passed all its
asserts. The reviewer's mutation harness confirmed it — 6 of 7 mutations were caught,
and mutation E (linear ramp) passed everything.

Fix: assert the quarter points, where linear and smoothstep differ most —
`REST_GLIDE_MS/4` → `0.15625` and `3 * REST_GLIDE_MS/4` → `0.84375`.

**Mutation proof:** with the fix in place, replacing the smoothstep body with `return t;`
now fails the suite —
`AssertionError: expected 0.25 to be close to 0.15625, received difference is 0.09375`.
Before the fix the same mutation passed.

### Minor 6 — `quietThreshold` was untested dead API surface

`packages/ui/src/motion/scroll-glide.ts:34`

`RestGlideInput.quietThreshold` is optional, defaulted, referenced at
`scroll-glide.ts:43`, and passed by no caller —
`ArchitectureTour.tsx:698` is the only `shouldStartRestGlide` call site and omits it.
No test covered it.

Fix: added the boundary test (`200/100` → true, `100/100` → true, `99/100` → false)
rather than deleting the parameter. The knob is a reasonable seam for a second
consumer and it is now pinned; deleting public surface from a ported branch is the
larger change.

### Nits fixed alongside

- **Nit 8** — `snap-start` on the phase cards was inert because the rail set no
  `scroll-snap-type`. Added `snap-x snap-proximity` to the rail.
- **Nit 11** — `role="list"` had bare `<span>` engine labels as direct children
  (invalid ARIA) and the labels were not tied to their cards. Engine groups are now
  `role="group"` + `aria-label={engine.label}`, with the visible span `aria-hidden`.

---

## Not actioned, with reasons

- **Nit 7** — `ArchitectureTour.tsx:659`'s "Scroll position is never rewritten" is
  contradicted by `remeasure()`'s `window.scrollTo` at `:609`. The comment is on a
  pre-existing line outside this PR's diff, and `:609` is pre-existing too. Correcting
  it is a separate one-word change to someone else's comment; folding it in here would
  put unrelated churn in a port.
- **Nit 9** — `SecondaryCard.contract.test.ts`'s `toContain("Card")` / `toContain("Reveal")`
  are satisfied by the import statements alone. Real, but the genuinely behavioural part
  of that file (the `secondaryDelay` block, which imports and calls the live function)
  already has signal, and the reviewer's own suggested rewrite — `renderToStaticMarkup`
  on a client component — is a test-infrastructure change larger than the finding.
- **Nit 10** — the pipeline-rail test over-fits a class string. The reviewer would accept
  it as-is, and a Playwright test is not available here (`PWTEST_SOCKETS_DIR` limit; the
  dev server cannot render this worktree's landing page because of the develop casing
  collision). Left as-is.

---

## Verified clean by the reviewer

- `flex shrink-0` is the right, minimal fix — independently reproduced in Chrome:
  branch groups `[w=700.3 sw=1808] [w=634.5 sw=1638] [w=89.2 sw=230]`, 15 card overlaps;
  port `[w=1808.2 sw=1808] [w=1638.2 sw=1638] [w=230.2 sw=230]`, 0 overlaps. And
  `document.scrollWidth == innerWidth` at 900px and 420px, so no page-level
  horizontal-overflow regression on narrow screens.
- The "19 phase folders" claim is true: `apps/digithings-web/lib/digiquantPipeline.ts`
  has 10 research + 9 portfolio phases, pinned by a pre-existing passing guard test.
- `scroll-glide` is wired to a real consumer (`ArchitectureTour.tsx:59-64,529,698,719`),
  never returns a scroll offset, has no wheel/`touchmove` listener and no
  `preventDefault`, and is skipped entirely for `mode === "static"`.
- Deleting `ModuleManifest.tsx` is safe — no import, no dynamic import, no barrel
  re-export, no string reference anywhere outside prose in `docs/superpowers/` and two
  comments in `TerminalManifest.tsx`.
- No new colour tokens, so there was nothing to contrast-check.
- Nothing was silently dropped: per-file diff against the abandoned branch across all 19
  shared files shows only the 3 documented adaptations.
- `SecondaryGrid` column mapping is correct (`one: ""`, `two: "sm:grid-cols-2"`,
  `three: "sm:grid-cols-2 lg:grid-cols-3"`).
- The strategy "example" badges are an honesty improvement — `showExampleBadge` gates
  both the rail label and the per-card suffix, so a live mark can never sit over a
  deterministic example.
- Naming and canon: `scripts/check_frontend_canon.py` clean, no app-local `cursor-*`,
  all prose lowercase.

## Pre-existing, not this PR

`apps/digithings-web` typecheck fails on 4 errors and `next build` fails, both on clean
`develop`, because BOTH `components/landing/Sections.tsx` AND `components/landing/sections.ts`
are tracked (`git ls-tree` shows all three blobs: `Sections.tsx`, `sections.test.ts`,
`sections.ts`). Webpack resolves the wrong one, so `FaqList` and `OpenSource` are missing
from `./Sections`. Neither file is touched by this PR. Proven by stash-and-rebuild: the
failure is byte-identical on clean `develop`. `packages/ui` has 68 pre-existing typecheck
errors, all from `@types/node` missing in that tsconfig; none in any file this PR touches.
