## Goal

Add Graphite-inspired motion and layout tokens to `packages/design/tokens.css` so all surfaces share section rhythm, product-frame sizing, and glide easing — per [`EVOLUTION.md` §5](../../../../packages/design/EVOLUTION.md).

## Component

- [x] cross-cutting (`packages/design/`)

## Acceptance Criteria

- [ ] `tokens.css` defines on `:root` (light + dark via `[data-theme]` if applicable):
  - `--wrap-wide: 1280px`
  - `--product-frame-w: 800px`
  - `--section-y: clamp(4rem, 8vw, 7rem)`
  - `--section-y-tight: clamp(2.5rem, 5vw, 4rem)`
  - `--ease-glide: cubic-bezier(0.22, 1, 0.36, 1)`
  - `--duration-reveal: 0.6s`
  - `--duration-hover: 0.18s`
- [ ] Existing `--transition-speed` / `--transition-ease` unchanged (no breaking consumers)
- [ ] `packages/design/README.md` documents new tokens in Motion + Spacing sections
- [ ] `packages/design/EVOLUTION.md` Phase A checkbox for tokens marked done
- [ ] `npm run build` (or workspace equivalent) passes for `digithings-web` and `digiquant-web`

## Test Requirements

**Unit / visual:**
- No new test framework required; verify tokens resolve in browser devtools on both themes

**Smoke:**
```bash
cd apps/digithings-web && npm run build
cd apps/digiquant-web && npm run build
```

## Documentation to Update

- [ ] `packages/design/README.md` — Motion & layout token tables
- [ ] `packages/design/EVOLUTION.md` — Phase A checkbox

## Scoring Targets

| Dimension | Target | Notes |
|-----------|--------|-------|
| Security | ≥8 | CSS-only |
| Quality | ≥8 | Token naming consistent with existing `--*` convention |
| Optimization | ≥7 | No runtime cost |
| Accuracy | ≥9 | Values match EVOLUTION.md §5 |

## Out of Scope

- Migrating existing components to use new tokens (follow-up primitives/landing issues)
- `linear()` easing upgrade (future polish)

## Dependencies

- Blocked by: none
- Unblocks: all Phase B primitives and landing realignments

## Human Gate Required?

- [ ] No
