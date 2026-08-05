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
| anywhere with a ≤500px cap | `avatar/digithings-avatar-{dark,light}-500.png` | 500×500, ~6.5KB |
| vector / print / resize | `avatar/digithings-avatar-{dark,light}.svg` | the source both PNGs are rendered from |

The avatar is the compact `d` + block cursor — the terminal identity's reduction,
not the full `digi` lockup, which closes up below about 64px.

## What lives here

```
avatar/
  digithings-avatar-dark.svg    digithings-avatar-dark.png    (1024)  -500.png
  digithings-avatar-light.svg   digithings-avatar-light.png   (1024)  -500.png
build-avatar.py                 regenerates all six from the favicon tile
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
| **Open Graph card** | `frontend/digithings-web/public/design/assets/og.png` | 1200×630, and **stale in four ways** — see below |
| **digithings.ai favicons** | `frontend/digithings-web/public/favicon-dg{,-light}.svg` | one per theme polarity; a tile bakes its own background so it cannot inherit ink |
| **digiquant.io favicons** | `frontend/digiquant-web/public/favicon-dg{,-light}.svg` | byte-identical to digithings' — the mark is monochrome, nothing site-specific differs |
| **favicon specimens** | `frontend/digiweb/reference/public/{,digiquant-}favicon-dg{,-light}.svg` | copies for the design-reference specimen page only; not served to users |
| **the marks in code** | `frontend/digiweb/web/src/components/symbols/terminal-marks.tsx` | `TerminalMark`, `TerminalWordmark`, `HairlineWordmark` — inline SVG in `currentColor`, which is why the nav follows `[data-theme]` |
| **module emblems** | `frontend/digiweb/web/src/components/emblems.tsx` | one geometric idea per module, on a 32-grid |

There is no build step syncing the three `public/` directories. If you change a
favicon tile, change all copies, then re-run `build-avatar.py`.

### og.png needs redrawing

It is the image every social share of digithings.ai renders, and it was last
touched in #731 — before the identity work. Opening it shows four problems:

1. the wordmark reads **“DigiThings”**, capitalised, which the brand never is;
2. the tagline is **“An open-core agentic stack”** — superseded by the glass-box
   positioning;
3. the frame is **blue**, and the identity is monochrome;
4. there is **no mark on it at all** — neither the terminal lockup nor the tile.

Redrawing it is open work. Until then, a link preview of digithings.ai shows copy
and colour the site itself no longer uses.

## Colours

The two polarities the tiles and avatar bake in, since they cannot inherit ink:

| polarity | background | ink |
|---|---|---|
| dark | `#0A0E0C` | `#ECEEF0` |
| light | `#FBFBF9` | `#14181B` |

Everything else in the design system takes colour from tokens — see
`frontend/digiweb/design/` — and every mark rendered in code draws in
`currentColor` rather than a literal.
