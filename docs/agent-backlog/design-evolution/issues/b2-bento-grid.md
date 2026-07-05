## Goal

Build a shared **`BentoGrid`** layout primitive — Cursor-style 2×2 (and responsive 1-col) linked feature cells for marketing sections ([`EVOLUTION.md` §6](../../../../frontend/design/EVOLUTION.md)).

## Component

- [x] cross-cutting (`frontend/design/`)

## Acceptance Criteria

- [ ] CSS classes in `frontend/design/site/site.css`:
  - `.bento` — CSS grid, gap from spacing tokens, `--wrap-wide` max-width
  - `.bento__cell` — linked card surface (`<a>` or `.bento__cell--static`), hairline border, hover lift using `--duration-hover` + `--ease-glide`
  - Responsive: 2×2 at `min-width: 768px`, single column below
  - Optional `.bento__cell--span-2` for wide cell
- [ ] Cell anatomy documented: kicker (mono), title, body, optional thumbnail slot, arrow suffix CTA (`Learn more →`)
- [ ] Demo in `frontend/design/smoke/index.html` with 4 placeholder cells
- [ ] Light + dark theme tested
- [ ] No glass morphism on cells (flat `--surface` steps)

## Test Requirements

```bash
cd frontend/digiquant-web && npm run build
cd frontend/digithings-web && npm run build
```

## Documentation to Update

- [ ] `frontend/design/site/README.md` — BentoGrid section
- [ ] `frontend/design/EVOLUTION.md` — Phase B checkbox

## Scoring Targets

| Dimension | Target |
|-----------|--------|
| Security | ≥8 |
| Quality | ≥8 |
| Optimization | ≥7 |
| Accuracy | ≥9 |

## Out of Scope

- Real module content (Phase C)
- JavaScript grid logic

## Dependencies

- Blocked by: A1
- Unblocks: B7, C2, C5

## Human Gate Required?

- [ ] No
