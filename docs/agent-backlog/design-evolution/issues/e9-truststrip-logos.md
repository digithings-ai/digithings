## Goal

Extend **`TrustStrip`** (#1204) with **integration logo variant** — x.ai-style partner marks for real stack integrations (NautilusTrader, LangGraph, LiteLLM, Polars) on digithings.ai ([design spec §Layer A §8](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] `.trust-strip--logos` variant — horizontal row of integration logos (~24–32px height), muted/grayscale default, optional hover color
- [ ] Real integrations only — no stock/generic logos
- [ ] Accessible: `alt` text per logo; decorative-only logos use `alt=""`
- [ ] Works alongside text friction variant (`.trust-strip` from B3)
- [ ] Demo in smoke page with 4 integration marks
- [ ] Document usage in `site/README.md` and `COPY_GUIDE.md` §10 trust section

## Test Requirements

- Build digithings-web after C1 integration
- Manual: logos align at mobile; sufficient contrast in light + dark themes

## Documentation to Update

- [ ] `frontend/design/site/README.md`
- [ ] `frontend/design/COPY_GUIDE.md`

## Out of Scope

- Fake enterprise customer logos
- Case study quotes (E10)

## Dependencies

- Blocked by: #1204 (TrustStrip base)
- Unblocks: C1 trust strip enhancement

## Human Gate Required?

- [ ] No
