## Goal

Build shared **`CaseStudyCard`** primitive — Graphite `{Co} × Product` horizontal case-study cells for digithings.ai social proof **when real quotes exist** ([design spec §Layer A §3](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`frontend/digiweb/design/`)

## Acceptance Criteria

- [ ] CSS `.case-study` — label `{org} × digithings`, quote block, logo slot; extends bento cell sizing
- [ ] Content-gated: no placeholder fake quotes — ship primitive + demo with lorem disabled or "example" watermark only
- [ ] Optional horizontal scroll via E1 `HorizontalScrollBand`
- [ ] Real attribution required for production: name, title, company, or public GitHub/OSS reference
- [ ] Document content shape in `site/README.md`

## Test Requirements

- Demo in smoke page with clearly marked example content
- Build digithings-web

## Documentation to Update

- [ ] `frontend/digiweb/design/site/README.md`
- [ ] `frontend/digiweb/design/COPY_GUIDE.md` §12 anti-patterns

## Out of Scope

- Fabricated enterprise testimonials
- Automated quote ingestion

## Dependencies

- Blocked by: #1203 (BentoGrid), E1 (optional scroll)
- Unblocks: digithings social proof band (content-dependent)

## Human Gate Required?

- [ ] No (content approval is human gate at enable time)

## Priority

P3 — defer until real quotes or OSS adopter stories exist.
