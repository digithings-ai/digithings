## Goal

Replace digithings.ai long architecture-only scroll with a **Cursor-style bento module grid** — each cell = module accent + capability card + optional `ProductFrame` UI crop ([`EVOLUTION.md` §3](../../../frontend/design/EVOLUTION.md)).

## Component

- [x] `frontend/digithings-web/`

## Acceptance Criteria

- [ ] New section (or refactor existing architecture section) using `BentoGrid` + `CapabilityCard`
- [ ] Minimum 4 cells covering primary modules (DigiGraph, DigiQuant, DigiSearch, DigiChat) with correct `--accent-*` treatment
- [ ] Each cell links to module docs or GitHub (real hrefs, no `#`)
- [ ] Optional: **one** `ScrollyFeatures` section for "how the stack fits" — if added, must be the only pin on page
- [ ] Remove or shorten redundant architecture prose that duplicates bento content
- [ ] Principles 4-up section retained or merged into bento (document choice in PR)
- [ ] Build + manual visual check light/dark

## Test Requirements

```bash
cd frontend/digithings-web && npm run build
```

## Documentation to Update

- [ ] `frontend/design/EVOLUTION.md`
- [ ] Landing component comments if architecture section renamed

## Out of Scope

- Per-module subpages
- Testimonial band with real quotes (future; placeholder OK)

## Dependencies

- Blocked by: B2, B7, C1
- Unblocks: none

## Human Gate Required?

- [ ] No
