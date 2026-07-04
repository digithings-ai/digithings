## Goal

Create and maintain **`frontend/design/COPY_GUIDE.md`** — authoritative voice, CTA library, section maps, and IA templates extracted from Layer D research ([design spec §Layer D](../../../superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md)).

## Component

- [x] cross-cutting (`frontend/design/` — docs only)

## Acceptance Criteria

- [ ] `frontend/design/COPY_GUIDE.md` exists with:
  - Voice & tone, headline formulas, subhead patterns, section title patterns, feature cell structure
  - Literal CTA library (per-surface matrix)
  - Friction reducers, footer IA, marketing vs dashboard IA templates
  - Per-surface section maps (digithings, digiquant, DigiChat, Olympus/twelve-x)
  - Anti-patterns, announcement bar copy template
- [ ] Links to `EVOLUTION.md` and `references/scans/copy-patterns.md`
- [ ] `frontend/design/README.md` one-line link to COPY_GUIDE
- [ ] `frontend/design/EVOLUTION.md` links COPY_GUIDE in Related files

## Test Requirements

```bash
make doc-check  # or verify internal links manually
```

## Documentation to Update

- [ ] `frontend/design/README.md`
- [ ] `frontend/design/EVOLUTION.md` §11 Related files

## Out of Scope

- Landing copy implementation in code (#1210–#1213)
- Automated copy linting

## Dependencies

- Blocked by: none
- Unblocks: E7, all Phase C landing copy work

## Human Gate Required?

- [ ] No
