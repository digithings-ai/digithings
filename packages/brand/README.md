# brand assets

The one place to look when something outside the codebase needs a logo — a GitHub
org avatar, a social profile, a slide, a conference listing.

**This folder holds only assets with no other home.** Everything else is listed
below with a pointer to its canonical copy, deliberately *not* copied here: two
copies of a logo become two different logos the first time one is updated. If you
need a file that lives elsewhere, take it from the path given.

## Start here: the brand studio

Compose and export the logo + hero wordmark at **`/brand`** in the
digiweb app:

```bash
npm run dev --workspace @digithings/digiweb -- --port 4013
# http://127.0.0.1:4013/brand/
```

The studio is the working surface for marketing, social, docs and any new brand
composition: 15 format presets, the embedding field, the 33 theme palettes, PNG
and self-contained SVG export, and a live gallery of every module wordmark
banner. The gallery reads `packages/hero-banner/src/definitions/index.ts`, so a
module definition change reaches it automatically.

Use the **wordmark** for headers, web pages and docs; use the **logo** for app
icons and favicons. One or the other, never both in the same view.

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

The studio is the preview and composition surface. The files in this folder are
still the canonical upload copies; `build-header.py` no longer mirrors them into
digiweb — only the two live `og.png` unfurls are copied. Neither the studio nor
these files are shipped on digithings.ai.

The avatar is the studio logo, the same mark as the favicon, centred for a
circular crop.

## What lives here

```
avatar/
  digithings-avatar-dark.svg    digithings-avatar-dark.png    (1024)  -500.png
  digithings-avatar-light.svg   digithings-avatar-light.png   (1024)  -500.png
og/
  digithings-og.svg             digithings-og.png             (1200x630)
  digithings-og-square.svg      digithings-og-square.png      (1080x1080)
  digiquant-og.svg              digiquant-og.png              (1200x630)
headers/
  digithings-x-1500x500.{svg,png}
  digithings-linkedin-personal-1584x396.{svg,png}
  digithings-linkedin-company-1128x191.{svg,png}
email/
  signoff.txt                   signoff.html
studio/
  logo-animated.svg             logo-mark.svg
  wordmark-animated.svg         wordmark-mask.svg
  field-{x,og,square,story,linkedin-personal,linkedin-company}.svg
  presets.json                  palettes.json
build-avatar.py                 regenerates the six avatars from studio/logo-mark.svg
build-favicon.py                bakes the site favicon sets from the studio logo
build-og.py                     regenerates the studio link-preview cards
build-header.py                 regenerates social headers + the served kit copies
build-studio.py                 syncs studio assets, including the wordmark mask copies
```

### The brand studio assets

`studio/` holds the generated sources the composer renders: the 60×60-pixel-grid
`logo-animated.svg` (100×100 viewBox), the 4×4 `wordmark-animated.svg`, the
thumbnail masks, the six field patterns, and the preset/palette JSON. The
digiweb app serves a byte-identical copy from
`apps/digiweb/public/brand/studio/`; the canonical copy is this folder.

```bash
python3 packages/brand/build-studio.py           # write the served mirror
python3 packages/brand/build-studio.py --check   # verify, write nothing
# or: make brand-studio-check
```

The studio does not store module banners as files. The gallery renders the 15
definitions from `packages/hero-banner/src/definitions/index.ts` live, so the
source of truth stays the code that the sites and terminals already use.

**The avatar is derived, never drawn.** `build-avatar.py` reads
`studio/logo-mark.svg`, the same mark `build-favicon.py` bakes into the sites.
Re-run it after any change to that file:

```bash
python3 packages/brand/build-avatar.py          # rebuild
python3 packages/brand/build-avatar.py --check   # verify, write nothing
```

It is not a straight copy of the 32px tile. GitHub renders avatars in a circle
in several places, so the script scales the 60-unit logo box until its corners
land on a 43-unit radius (50 less a 7-unit margin for antialias spill and
GitHub's ring) and centres it. The square is full-bleed with no baked corner
radius, because GitHub rounds avatars itself and a radius in the PNG shows as
a seam inside its frame.

## Everything else, and where it actually lives

| asset | canonical path | notes |
|---|---|---|
| **Chris Stefan avatar** | `apps/digithings-web/public/team/chris.png` | 460×460. Under the 500×500 GitHub recommends — re-export larger from the source if you need it for a profile |
| **Open Graph cards** | `apps/digithings-web/public/og.png`, `apps/digithings-web/public/og-square.png`, `apps/digiquant-web/public/og.png`, `apps/digichat/public/og.png` | generated — see below. Digiquant's card is the quant logo, not the digithings wordmark |
| **digithings.ai favicons** | `apps/digithings-web/public/icons/` and `favicon-dg{,-light}.svg` | `build-favicon.py` from `logo-mark.svg`. `favicon-dg.svg` is the light tile (the integrations chip loads it); `favicon-dg-light.svg` is the dark tile |
| **digiquant.io favicons** | `apps/digiquant-web/public/icons/` and `favicon-dg{,-light}.svg` | same filenames, quant up/down bands. Not a byte copy of the digithings tiles |
| **digichat favicons** | `apps/digichat/public/icons/` and `src/app/icon.svg` | the digithings set. `icon.svg` is the dark tile |
| **the marks in code** | `packages/ui/src/components/symbols/terminal-marks.tsx` | `TerminalMark`, `TerminalWordmark`, `HairlineWordmark` — inline SVG in `currentColor`, which is why the nav follows `[data-theme]` |
| **module wordmark banners** | `packages/hero-banner/src/definitions/index.ts` | 15 `BANNERS` definitions (digithings + 14 modules). Rendered live in the brand studio gallery; no copied banner files |
| **module emblems** | `packages/ui/src/components/emblems.tsx` | one geometric idea per module, on a 32-grid |

`build-favicon.py` writes the digithings, digichat, and digiquant tiles.
`build-studio.py` keeps `apps/digiweb/public/brand/studio/` in sync with
`studio/`, and copies `wordmark-mask.svg` to each app that masks it.

### The Open Graph cards

`og/` holds the link-preview cards, and `build-og.py` generates them from the
studio: the digithings wordmark on the field at 1200×630 (preset `open-graph`,
wordmark 9% of the height) and 1080×1080 (preset `square`, wordmark 5.5%),
and the digiquant logo on the same field. One mark per card.

```bash
python3 packages/brand/build-og.py           # rebuild
python3 packages/brand/build-og.py --check    # verify, write nothing
```

The rendered PNGs are what the sites serve:

| file | served at |
|---|---|
| `digithings-og.png` | `apps/digithings-web/public/og.png`, `apps/digichat/public/og.png` |
| `digithings-og-square.png` | `apps/digithings-web/public/og-square.png` (book `summary` cards) |
| `digiquant-og.png` | `apps/digiquant-web/public/og.png` |

`HEADLINES` in `build-og.py` still feeds the social headers. The headers stay
outlined Geist Mono. The link-preview cards do not.

### Social headers

X and LinkedIn are much shorter than 1200×630. Cropping the OG card drops the
domain into the platform chrome. `build-header.py` composes the **same** copy
(HEADLINES, outlined Geist Mono, dark/ink, inset frame) as a compact vertical
stack that fits each crop:

```bash
python3 packages/brand/build-header.py          # rebuild headers + kit copies
python3 packages/brand/build-header.py --check   # verify, write nothing
```

`--check` also verifies the served mirrors under
`apps/digiweb/public/brand/` (and the live `public/og.png` unfurl
cards) so the digiweb kit cannot drift from this folder. Re-run the
header builder after an avatar or OG rebuild so those copies refresh. The
marketing sites do not serve `/brand`.

## Colours

The two polarities the tiles and avatar bake in, since they cannot inherit ink:

| polarity | background | ink |
|---|---|---|
| dark | `#0A0E0C` | `#ECEEF0` |
| light | `#FBFBF9` | `#14181B` |

Everything else in the design system takes colour from tokens — see
`packages/design/` — and every mark rendered in code draws in
`currentColor` rather than a literal.
