## Goal

Build shared **`ClosingCtaBand`** primitive — full-width section before footer with headline + literal primary CTA + optional secondary ([Graphite/Cursor pattern](../../../frontend/design/references/scans/copy-patterns.md), [COPY_GUIDE.md §6](../../../frontend/design/COPY_GUIDE.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] CSS `.closing-cta` — centered h2 + `.btn` primary + optional secondary link
- [ ] Uses `--section-y` rhythm and `--wrap-wide` container
- [ ] Copy slots documented (headline, primary label+href, secondary label+href)
- [ ] `reveal-up` enter on scroll (respect reduced motion)
- [ ] Demo in smoke page with digithings + digiquant copy variants
- [ ] Document in `frontend/design/site/README.md`

## Test Requirements

- Build both landing apps after demo integration
- Manual: closing band appears above footer, CTA links resolve

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/COPY_GUIDE.md` — reference primitive

## Out of Scope

- Landing page wiring (E7)
- Hero CTA duplication

## Dependencies

- Blocked by: #1201
- Unblocks: E7

## Human Gate Required?

- [ ] No
