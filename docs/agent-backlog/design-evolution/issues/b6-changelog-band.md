## Goal

Build **`ChangelogBand`** — Cursor-style dated release rows for marketing landings ([`cursor-full.md`](../../../../packages/design/references/scans/cursor-full.md)).

## Component

- [x] cross-cutting (`packages/design/`)

## Acceptance Criteria

- [ ] CSS `.changelog-band` — section with mono date column + title + optional tag (`release`, `fix`)
- [ ] Data shape documented (JSON or TS type): `{ date, version?, title, href, tag? }[]`
- [ ] Static example JSON in `packages/design/` or consumed from `CHANGELOG.md` excerpt (document source of truth)
- [ ] "View all releases →" footer link pattern
- [ ] Responsive: stacked on mobile, row layout on desktop
- [ ] Demo with 3–5 entries in smoke page

## Test Requirements

```bash
cd apps/digithings-web && npm run build
```

## Documentation to Update

- [ ] `packages/design/site/README.md`
- [ ] `packages/design/EVOLUTION.md`

## Out of Scope

- Automated CHANGELOG ingestion from GitHub Releases
- digithings/digiquant landing wiring (C3)

## Dependencies

- Blocked by: A1
- Unblocks: C3

## Human Gate Required?

- [ ] No
