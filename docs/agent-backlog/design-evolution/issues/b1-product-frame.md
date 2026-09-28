## Goal

Build a shared **`ProductFrame`** primitive — container-query-scaled ~800px UI embed for marketing pages — inspired by Graphite artboards and Cursor rounded product screenshots ([`components-catalog.md`](../../../../packages/design/references/scans/components-catalog.md)).

## Component

- [x] cross-cutting (`packages/design/` + `packages/ui/` if React wrapper needed)

## Acceptance Criteria

- [ ] CSS in `packages/design/site/site.css` (or `components.css`):
  - `.product-frame` — max-width `var(--product-frame-w)`, `container-type: inline-size`
  - Inner `.product-frame__surface` — flat dark/light panel, 1px `--hair` border, `border-radius: var(--radius-lg)`, **no mesh gradient on UI**
  - CQ scale: UI content scales down below 800px using `cqw` or `clamp()` (document chosen approach)
- [ ] Optional React component `ProductFrame` in `packages/ui/` (or shared landing package) accepting `children` + `caption?`
- [ ] Demo usage in `packages/design/smoke/index.html` or existing demo page
- [ ] `packages/design/site/README.md` documents API (class names, props, atmosphere rule: *surgical inside*)
- [ ] Works in both `[data-theme="light"]` and `[data-theme="dark"]`
- [ ] Referenced from `EVOLUTION.md` primitives table as implemented

## Test Requirements

**Visual smoke:**
```bash
# Open smoke page; frame scales at 390px and 1280px viewports without horizontal scroll
open packages/design/smoke/index.html
```

**Build:**
```bash
cd apps/digithings-web && npm run build
```

## Documentation to Update

- [ ] `packages/design/site/README.md` — ProductFrame section
- [ ] `packages/design/EVOLUTION.md` — Phase B checkbox

## Scoring Targets

| Dimension | Target | Notes |
|-----------|--------|-------|
| Security | ≥8 | No user HTML injection in primitive itself |
| Quality | ≥8 | Matches existing `site.css` patterns |
| Optimization | ≥7 | CSS-only scaling preferred over JS resize |
| Accuracy | ≥9 | Matches Graphite 800px CQ reference |

## Out of Scope

- Wiring into digithings/digiquant landings (Phase C issues)
- Video embeds inside frame

## Dependencies

- Blocked by: A1 (motion/layout tokens), #1195 (hoist landing primitives — coordinate package location)
- Unblocks: B4, B7, C1, C5

## Human Gate Required?

- [ ] No
