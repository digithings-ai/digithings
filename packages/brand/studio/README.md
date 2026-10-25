# brand studio assets

Source assets for the **brand studio** at `/brand/studio` in `apps/digiweb`.

The studio composes the digithings 60×60 logo with the 4×4 hero wordmark over
the embedding field, previews every upload format, and exports PNG/SVG. The
module wordmark gallery is rendered live from
`packages/hero-banner/src/definitions/index.ts`; no module banner files are
stored here, so a definition change reaches the gallery automatically.

## Files

| file | role |
|---|---|
| `logo-animated.svg` | 60×60-pixel-grid three-column Jenga mark (100×100 viewBox), per-pixel classes + animation timing |
| `logo-mark.svg` | static `currentColor` mark used for the favicon and thumbnail masks |
| `wordmark-animated.svg` | 4×4 contiguous hero wordmark, 6,880 sub-pixels + passive animation classes |
| `wordmark-mask.svg` | 4×4 wordmark as a single mask for thumbnails |
| `field-*.svg` | embedding-field patterns, one per format aspect |
| `presets.json` | 15 read-only format presets (dimensions, background, theme, layout, layer sizes) |
| `palettes.json` | the 33 theme palettes consumed by the studio selectors |

## Mirror

The digiweb app can only serve files from its own `public/` directory, so the
same bytes are copied to `apps/digiweb/public/brand/studio/`. The canonical
copy is this folder. After changing a source asset:

```bash
python3 packages/brand/build-studio.py           # write the mirror
python3 packages/brand/build-studio.py --check   # verify, write nothing
```

## Rules

- **One or the other, never both.** The wordmark carries headers, web pages and
  docs; the logo carries app icons and favicons. Presets follow that rule.
- **Default is monochrome.** The default theme sets the accent to the ink
  colour; colour is an explicit palette choice.
- **Do not redraw the mark.** If a composition looks wrong, change the preset
  or the studio, not the SVG by hand. The source SVGs are generated from the
  pixel system.
