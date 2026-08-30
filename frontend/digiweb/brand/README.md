# brand assets

The one place to look when something outside the codebase needs a logo — a GitHub
org avatar, a social profile, a slide, a conference listing.

**This folder holds only assets with no other home.** Everything else is listed
below with a pointer to its canonical copy, deliberately *not* copied here: two
copies of a logo become two different logos the first time one is updated. If you
need a file that lives elsewhere, take it from the path given.

## Upload targets

| where | use this | why |
|---|---|---|
| **GitHub org avatar** | `avatar/digithings-avatar-dark.png` | 1024×1024, holds up on GitHub's light and dark UI |
| GitHub org avatar, light preference | `avatar/digithings-avatar-light.png` | same mark, inverted polarity |
| **X (@digithingsai) avatar** | `avatar/digithings-avatar-dark.png` | same 1024 file |
| **X profile header** | `headers/digithings-x-1500x500.png` | 1500×500 compact OG lockup — do not crop `og.png` |
| **LinkedIn (Chris, personal)** | `headers/digithings-linkedin-personal-1584x396.png` | 1584×396; photo uses the dark 1024 avatar |
| **LinkedIn company cover** | `headers/digithings-linkedin-company-1128x191.png` | 1128×191; same avatar |
| anywhere with a ≤500px cap | `avatar/digithings-avatar-{dark,light}-500.png` | 500×500, ~6.5KB |
| vector / print / resize | `avatar/digithings-avatar-{dark,light}.svg` | the source both PNGs are rendered from |
| **company email sign-off** | `email/signoff.{txt,html}` | lowercase digithings, tagline, digithings.ai |

Public downloads of the same bytes are on [digithings.ai/brand](https://digithings.ai/brand) (`/press` redirects there). That page is a mirror with `--check`, not a second set of logos.

The avatar is the compact `d` + block cursor — the terminal identity's reduction,
not the full `digi` lockup, which closes up below about 64px.

## What lives here

```
avatar/
  digithings-avatar-dark.svg    digithings-avatar-dark.png    (1024)  -500.png
  digithings-avatar-light.svg   digithings-avatar-light.png   (1024)  -500.png
og/
  digithings-og.svg             digithings-og.png             (1200x630)
  digiquant-og.svg              digiquant-og.png              (1200x630)
headers/
  digithings-x-1500x500.{svg,png}
  digithings-linkedin-personal-1584x396.{svg,png}
  digithings-linkedin-company-1128x191.{svg,png}
email/
  signoff.txt                   signoff.html
build-avatar.py                 regenerates the six avatars from the favicon tile
build-og.py                     regenerates both cards, wordmark outlined from Geist Mono
build-header.py                 regenerates social headers + the served kit copies
```

**The avatar is derived, never drawn.** `build-avatar.py` reads the `d` glyph path
straight out of `frontend/digithings-web/public/favicon-dg.svg`, so the mark cannot
drift from the one the sites ship. Re-run it after any change to that tile:

```bash
python3 frontend/digiweb/brand/build-avatar.py          # rebuild
python3 frontend/digiweb/brand/build-avatar.py --check   # verify, write nothing
```

It is not a straight copy of the favicon. The favicon is drawn for a rounded-square
browser tile: its ink sits off-centre with a half-diagonal of 48.96 in a 100-unit
box, and GitHub renders avatars in a circle in several places, so the cursor's
corner would be clipped. The script scales the ink until its corners land on a
43-unit radius (50 less a 7-unit margin for antialias spill and GitHub's ring) and
re-centres it. Measured on the output: ink centred to within half a pixel, furthest
ink pixel at 85.9% of the radius — 72px of clearance at 1024px. The square is
full-bleed with no baked corner radius, because GitHub rounds avatars itself and a
radius in the PNG shows as a seam inside its frame.

## Everything else, and where it actually lives

| asset | canonical path | notes |
|---|---|---|
| **Chris Stefan avatar** | `frontend/digithings-web/public/team/chris.png` | 460×460. Under the 500×500 GitHub recommends — re-export larger from the source if you need it for a profile |
| **Open Graph cards** | `frontend/digithings-web/public/og.png`, `frontend/digiquant-web/public/og.png` | 1200×630, generated — see below |
| **digithings.ai favicons** | `frontend/digithings-web/public/favicon-dg{,-light}.svg` | one per theme polarity; a tile bakes its own background so it cannot inherit ink |
| **digiquant.io favicons** | `frontend/digiquant-web/public/favicon-dg{,-light}.svg` | byte-identical to digithings' — the mark is monochrome, nothing site-specific differs |
| **favicon specimens** | `frontend/digiweb/reference/public/{,digiquant-}favicon-dg{,-light}.svg` | copies for the design-reference specimen page only; not served to users |
| **the marks in code** | `frontend/digiweb/web/src/components/symbols/terminal-marks.tsx` | `TerminalMark`, `TerminalWordmark`, `HairlineWordmark` — inline SVG in `currentColor`, which is why the nav follows `[data-theme]` |
| **module emblems** | `frontend/digiweb/web/src/components/emblems.tsx` | one geometric idea per module, on a 32-grid |

There is no build step syncing the three `public/` directories. If you change a
favicon tile, change all copies, then re-run `build-avatar.py`.

### The Open Graph cards

`og/` holds the two link-preview cards, and `build-og.py` generates them:

```bash
python3 frontend/digiweb/brand/build-og.py           # rebuild both
python3 frontend/digiweb/brand/build-og.py --check    # verify, write nothing
```

The rendered PNGs are copied into each app's `public/og.png` and wired through
`openGraph.images` with explicit width, height and alt.

**The wordmark is outlined to paths, not set as SVG `<text>`.** There is no Geist
installed for librsvg, so a `<text>` element would rasterise in whatever fallback
face the machine happens to have — which is exactly how an off-brand card ships
without anyone noticing. `build-og.py` reads the glyphs out of
`node_modules/geist/dist/fonts/geist-mono/GeistMono-Regular.ttf` at weight 400 and
embeds them, and it asserts Geist Mono's advance is still 0.6em so a font update
cannot silently knock the cursor off its cell.

What this replaced is worth recording, because it is how brand art goes stale
quietly. The old digithings card, last touched in #731, had drifted four ways at
once: the wordmark read **"digithings"** capitalised, the tagline was the
superseded **"An open-core agentic stack"**, the frame was **blue** against a
monochrome identity, and it carried **no mark at all**. digiquant.io had no
`images` key in its `openGraph` block, so its links unfurled with no card image.

The copy on each card lives in `HEADLINES` in `build-og.py` and must track that
site's own hero. A card is not a place to invent a new tagline.

### Social headers

X and LinkedIn are much shorter than 1200×630. Cropping the OG card drops the
domain into the platform chrome. `build-header.py` composes the **same** copy
(HEADLINES, outlined Geist Mono, dark/ink, inset frame) as a compact vertical
stack that fits each crop:

```bash
python3 frontend/digiweb/brand/build-header.py          # rebuild headers + kit copies
python3 frontend/digiweb/brand/build-header.py --check   # verify, write nothing
```

`--check` also verifies the served mirrors under
`frontend/digithings-web/public/brand/` (and `public/og.png`) so the marketing
page cannot drift from this folder. Re-run the header builder after an avatar
or OG rebuild so those copies refresh.

## Colours

The two polarities the tiles and avatar bake in, since they cannot inherit ink:

| polarity | background | ink |
|---|---|---|
| dark | `#0A0E0C` | `#ECEEF0` |
| light | `#FBFBF9` | `#14181B` |

Everything else in the design system takes colour from tokens — see
`frontend/digiweb/design/` — and every mark rendered in code draws in
`currentColor` rather than a literal.
