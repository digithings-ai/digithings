## Goal

Align `frontend/digiweb/design/README.md` typography documentation with reality: **Geist Sans + Geist Mono** are the canonical fonts in Next.js apps; deprecate Inter/JetBrains Mono as documented defaults per [`EVOLUTION.md` §4](../../../../frontend/digiweb/design/EVOLUTION.md).

## Component

- [x] cross-cutting (docs)

## Acceptance Criteria

- [ ] `frontend/digiweb/design/README.md` typography table lists Geist Sans (body), Geist Mono (labels/code/data), Fraunces or Instrument Serif (marketing display only)
- [ ] Legacy Inter/JetBrains entries marked **deprecated** with migration note
- [ ] Role table matches `EVOLUTION.md` §4 (display / body / label / data / code)
- [ ] `frontend/digiweb/design/EVOLUTION.md` Phase A typography checkbox marked done
- [ ] No code changes to font loading in this task (docs-only)

## Test Requirements

- Doc link check: `make doc-check` passes (or manual verify internal links)

## Documentation to Update

- [ ] `frontend/digiweb/design/README.md`
- [ ] `frontend/digiweb/design/EVOLUTION.md`

## Scoring Targets

| Dimension | Target |
|-----------|--------|
| Security | ≥8 |
| Quality | ≥8 |
| Optimization | ≥7 |
| Accuracy | ≥9 |

## Out of Scope

- Changing actual `@font-face` imports in apps
- DigiChat token migration (#240)

## Dependencies

- Blocked by: none
- Unblocks: none (parallel with A1)

## Human Gate Required?

- [ ] No
