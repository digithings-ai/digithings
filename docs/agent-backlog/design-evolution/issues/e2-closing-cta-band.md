## Goal

Build shared **`ClosingCtaBand`** primitive — full-width section before footer with headline + literal primary CTA + optional secondary ([Graphite/Cursor pattern](../../../../packages/design/references/scans/copy-patterns.md), [COPY_GUIDE.md §6](../../../../packages/design/COPY_GUIDE.md)).

## Component

- [x] cross-cutting (`packages/design/`)

## Acceptance Criteria

- [ ] CSS `.closing-cta` — centered h2 + `.btn` primary + optional secondary link
- [ ] Uses `--section-y` rhythm and `--wrap-wide` container
- [ ] Copy slots documented (headline, primary label+href, secondary label+href)
- [ ] `reveal-up` enter on scroll (respect reduced motion)
- [ ] Demo in smoke page with digithings + digiquant copy variants
- [ ] Document in `packages/design/site/README.md`

## Test Requirements

- Build both landing apps after demo integration
- Manual: closing band appears above footer, CTA links resolve

## Documentation to Update

- [ ] `packages/design/site/README.md`
- [ ] `packages/design/COPY_GUIDE.md` — reference primitive

## Out of Scope

- Landing page wiring (E7)
- Hero CTA duplication

## Dependencies

- Blocked by: #1201
- Unblocks: E7

## Human Gate Required?

- [ ] No
