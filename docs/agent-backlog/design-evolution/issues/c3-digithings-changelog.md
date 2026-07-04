## Goal

Add a **changelog/releases band** to digithings.ai landing using the shared `ChangelogBand` primitive ([`cursor-full.md`](../../../frontend/design/references/scans/cursor-full.md)).

## Component

- [x] `frontend/digithings-web/`

## Acceptance Criteria

- [ ] Section placed above footer (or below bento) with kicker `// releases`
- [ ] 3–5 recent entries from repo `CHANGELOG.md` or static `releases.json` (document maintenance process)
- [ ] "View all releases →" links to GitHub releases or `/changelog` if exists
- [ ] Matches site theme; mono dates
- [ ] `npm run build` passes

## Test Requirements

- Verify links resolve (no 404)
- Mobile layout readable

## Documentation to Update

- [ ] `frontend/digithings-web/README.md` — how to update release entries
- [ ] `frontend/design/EVOLUTION.md`

## Out of Scope

- digiquant changelog (could reuse primitive in follow-up)
- Automated release feed

## Dependencies

- Blocked by: B6
- Unblocks: none

## Human Gate Required?

- [ ] No
