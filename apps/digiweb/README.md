# @digithings/digiweb

The live design reference for digithings — **digiweb**. It renders the current
generation's tokens, kit and brand as working code in a React / Next.js /
Tailwind / Motion app, and its home page is the **baseline design document**:
the rules the shipped surfaces already follow, each with a live witness. When
you build a frontend surface, start here: import the kit, keep its grammar, and
only add a specimen when the pattern belongs to the language.

It replaces the retired 2026-08 blend corpus that lived in `apps/reference`.

## Run it

```bash
npm run dev --workspace @digithings/digiweb -- --port 4013
# Reference:    http://127.0.0.1:4013/
# Brand studio: http://127.0.0.1:4013/brand/
```

It consumes the shared workspaces from source: `@digithings/design` (tokens),
`@digithings/ui` (the kit), and `@digithings/hero-banner` (the wordmark
banners). Edits to those packages hot-reload here.

## Page map

| route | kind | what it is |
|---|---|---|
| `/` | reference | **Baseline** — the eight rules the live surfaces follow, rendered in the tile grammar, plus the surfaces table, density ladder and known deltas |
| `/foundations` | reference | Palette roles, liveries and the type ladder, read from `designTokens` |
| `/components` | reference | Every kit primitive and composite, parsed from the package barrels |
| `/rtl` | reference | The direction proof — the kit under a `dir=ltr`/`dir=rtl` toggle |
| `/brand` | reference-only | Brand studio — compose the logo + 4x4 wordmark, export PNG/SVG, every module banner |

The top bar (`components/site-nav.tsx`) is the only shared chrome. The
route/nav inventory is machine-readable in `lib/specimen-inventory.ts` and
`lib/nav.ts`, and pinned by `lib/*.test.ts`: a page that is not in both fails
the suite.

## It does not drift

- **Tokens** are read from the generated `designTokens` table, so the
  foundations page shows the shipped values.
- **The kit index** parses `packages/ui/src/ui/index.ts` and
  `packages/ui/src/index.ts`; a new export appears without an edit here.
- **The module banners** render from `BANNERS` in
  `@digithings/hero-banner/definitions`; nothing is copied.
- **Brand studio assets** are a byte-identical mirror of `packages/brand/studio/`,
  checked by `make brand-studio-check`.

## What it is meant to absorb

`docs/design/live-ui-inventory.md` is the sourced list of every UI element the
shipped surfaces carry — marketing, desk, dashboard, chat, trace, TUI, icons,
themes, toolbars, motion — with the ones already here marked. It is the backlog
for new specimens.

## Not shipped

This app is a local reference. It is not deployed to digithings.ai or
digiquant.io, and no product surface imports it. Product apps import
`@digithings/ui` and `@digithings/design` directly.
