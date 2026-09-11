## Goal

Migrate **Olympus** dashboard from glass morphism to x.ai-style flat surfaces — hairline borders, `--surface` steps, no decorative shadows ([`EVOLUTION.md` §3 Olympus](../../../../cloudflare/digiweb/design/EVOLUTION.md)).

## Component

- [x] `cloudflare/olympus/`

## Acceptance Criteria

- [ ] Audit all `glass-card`, `backdrop-blur`, heavy `box-shadow` usage in `cloudflare/olympus/`
- [ ] Replace with utility classes:
  - `.surface` / `bg-[var(--surface)]` + `border border-[var(--hair)]`
  - Remove blur on new/changed components (legacy may migrate incrementally — document remaining glass in PR)
- [ ] `globals.css` or shared CSS documents surface elevation scale (`--surface`, `--surface-raised` if added)
- [ ] Cyan accent unification preserved
- [ ] No scroll pinning added to dashboard
- [ ] `npm run build` in olympus passes
- [ ] Visual spot-check: Atlas, Hermes, main dashboard routes

## Test Requirements

```bash
cd cloudflare/olympus && npm run build
```

## Documentation to Update

- [ ] `cloudflare/olympus/ARCHITECTURE.md` — surface system
- [ ] `cloudflare/digiweb/design/EVOLUTION.md` Phase D
- [ ] `cloudflare/digiweb/design/EVOLUTION.md` §10 — glass on new components rejected

## Out of Scope

- twelve-x specific polish (D2)
- Backend API changes

## Dependencies

- Blocked by: A1 (surface tokens if needed)
- Unblocks: D2, D3

## Human Gate Required?

- [ ] No
