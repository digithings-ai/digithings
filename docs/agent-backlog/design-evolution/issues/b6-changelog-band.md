## Goal

Build **`ChangelogBand`** — Cursor-style dated release rows for marketing landings ([`cursor-full.md`](../../../../cloudflare/digiweb/design/references/scans/cursor-full.md)).

## Component

- [x] cross-cutting (`cloudflare/digiweb/design/`)

## Acceptance Criteria

- [ ] CSS `.changelog-band` — section with mono date column + title + optional tag (`release`, `fix`)
- [ ] Data shape documented (JSON or TS type): `{ date, version?, title, href, tag? }[]`
- [ ] Static example JSON in `cloudflare/digiweb/design/` or consumed from `CHANGELOG.md` excerpt (document source of truth)
- [ ] "View all releases →" footer link pattern
- [ ] Responsive: stacked on mobile, row layout on desktop
- [ ] Demo with 3–5 entries in smoke page

## Test Requirements

```bash
cd cloudflare/digithings-web && npm run build
```

## Documentation to Update

- [ ] `cloudflare/digiweb/design/site/README.md`
- [ ] `cloudflare/digiweb/design/EVOLUTION.md`

## Out of Scope

- Automated CHANGELOG ingestion from GitHub Releases
- digithings/digiquant landing wiring (C3)

## Dependencies

- Blocked by: A1
- Unblocks: C3

## Human Gate Required?

- [ ] No
