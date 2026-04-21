# Epic: Migrate `apps/digiquant-atlas/` into the `digiquant/` module

**Title:** `[Epic] Migrate Atlas from apps/ into digiquant module — unify Atlas as a DigiQuant product`

**Labels:** `epic`, `component:digiquant`, `priority:high`, `type:migration`

## Goal

Atlas is a DigiQuant product, not a sibling app. Today it lives at `apps/digiquant-atlas/` — parallel to the monorepo, with its own `.github/workflows/`, `.claude/`, `.cursor/`, supabase migrations, Python package (`src/digiquant_atlas/`), skills tree, and Next.js frontend. The split creates drift (duplicated tooling, parallel CI, separate agent instructions) and obscures that Atlas, Hermes, and Kairos are one product family built on the same quant core.

This epic folds Atlas **into** `digiquant/` so the DigiQuant module owns its flagship product end-to-end. The frontend joins the `frontend/` umbrella alongside every other web surface (ADR-0009). This also reverses the precedent set by `apps/digiquant-atlas/` and therefore requires an ADR.

## Target layout (proposal — requires ADR approval)

```
digiquant/
├── src/digiquant/
│   ├── atlas/                      ← NEW. Atlas Python package (from apps/digiquant-atlas/src/digiquant_atlas/)
│   ├── data/                       ← existing, absorbs the price pipeline from #149
│   ├── strategies/
│   └── …
├── docs/
│   └── atlas/                      ← NEW. From apps/digiquant-atlas/docs/
├── supabase/
│   └── migrations/                 ← NEW (or top-level infra/supabase/). From apps/digiquant-atlas/supabase/
└── ARCHITECTURE.md                 ← adds Atlas section

frontend/
└── digiquant-atlas/                ← MOVED from apps/digiquant-atlas/frontend/ (joins workspace cleanly)

digiquant/atlas-skills/             ← or promote to a shared home; decision point
```

Workflows in `apps/digiquant-atlas/.github/workflows/` fold into the monorepo's `.github/workflows/` as `atlas-*.yml`, or die if already covered.

## Phased migration

**Phase 0 — preconditions**
- [ ] #149 (price pipeline migration) merged and stable. Do not start Phase 1 on top of an in-flight branch.
- [ ] ADR-00XX filed and accepted: "Atlas belongs in digiquant, not apps/". Captures the frontend-umbrella alignment and reverses the `apps/` precedent.

**Phase 1 — Python package move**
- [ ] Move `apps/digiquant-atlas/src/digiquant_atlas/` → `digiquant/src/digiquant/atlas/`.
- [ ] Rename import root from `digiquant_atlas` → `digiquant.atlas`.
- [ ] Update `digiquant/pyproject.toml` to include the new subpackage.
- [ ] Keep a shim `digiquant_atlas/` that re-exports from `digiquant.atlas` during one release cycle, then delete.
- [ ] Update all callers (scripts, tests, agent skill manifests).

**Phase 2 — frontend move**
- [ ] Move `apps/digiquant-atlas/frontend/` → `frontend/digiquant-atlas/`.
- [ ] Update `package.json` workspace paths; verify `@digithings/design-system` resolves.
- [ ] Update any CI `paths:` filters.

**Phase 3 — docs + supabase + scripts**
- [ ] Move `apps/digiquant-atlas/docs/` → `digiquant/docs/atlas/`.
- [ ] Move `apps/digiquant-atlas/supabase/` → `digiquant/supabase/` (or top-level `infra/supabase/atlas/`).
- [ ] Move `apps/digiquant-atlas/scripts/` into `digiquant/scripts/atlas/` or fold into existing scripts.
- [ ] Move `apps/digiquant-atlas/config/` into `digiquant/config/atlas/`.

**Phase 4 — skills and agent surface**
- [ ] Decide: do Atlas's 40+ skills move under `digiquant/skills/atlas/`, promote to `.claude/skills/` as shared, or stay a private Atlas thing? Recommend: keep private under `digiquant/atlas/skills/` for now — they are Atlas-specific.
- [ ] Delete Atlas's own `.claude/`, `.cursor/`, `.agents/` surfaces — harness pulls from the monorepo root. Preserve any content that isn't duplicated.
- [ ] Update `AGENTS.md` at monorepo root + at `digiquant/` to include Atlas section; delete `apps/digiquant-atlas/AGENTS.md` (or reduce to a pointer).

**Phase 5 — CI + workflows**
- [ ] Fold `apps/digiquant-atlas/.github/workflows/` into root `.github/workflows/` as `atlas-*.yml`.
- [ ] Reconcile with existing `digiquant-test.yml`, `digiquant-prices.yml` — Atlas tests become part of the digiquant test matrix.

**Phase 6 — cleanup**
- [ ] Delete `apps/digiquant-atlas/` (after one release cycle if shims were used).
- [ ] Remove shim `digiquant_atlas/` re-export package.
- [ ] Update `CLAUDE.md`, `ARCHITECTURE.md`, `docs/VISION.md`, all paths.
- [ ] Update the three memory files that reference Atlas architecture.

## Non-goals

- Functional changes to Atlas behavior — this is a move, not a refactor. A separate epic can clean up code afterward.
- Merging Hermes / Kairos — they're still vaporware or early. When they land, they follow the same pattern: `digiquant/src/digiquant/<product>/`.
- Changing the Supabase schema or data contracts.

## Open questions

1. **ADR needed?** Yes — `apps/digiquant-atlas/` was deliberate (per the `apps/` pattern). Reversing that is an ADR-level call.
2. **Shim or hard cut on imports?** Shim is safer but costs one release cycle of dead code. Hard cut is cleaner if no external consumers exist — which is likely true here. Recommend: **hard cut**, given this is pre-1.0.
3. **Skills home?** Atlas skills are Atlas-specific; recommend keep private under `digiquant/atlas/skills/`. If any are genuinely shareable, promote individually later.
4. **Supabase location?** `digiquant/supabase/` couples the schema to the module; `infra/supabase/` treats it as shared infrastructure. Recommend: `digiquant/supabase/` for now — Atlas is the only consumer.
5. **Sequencing vs. Atlas daily-update epic (#NEW-Atlas-daily)**: start this migration AFTER the daily-update backend ships, to avoid churning under an active product launch? Or before, so daily-update is built in the new location? Recommend: **before daily-update matures**, so we only build the GHA cron once against final paths.

## Dependencies and sequencing

- **Hard blocker:** #149 price pipeline migration lands first.
- **Soft sequence:** complete before the Atlas daily-update epic's GHA cron task so the workflow references final paths.
- **No blocker on:** DigiKey SSO, DigiChat work, website deploys.

## Acceptance

- [ ] `apps/digiquant-atlas/` no longer exists (or contains only a README pointer).
- [ ] `digiquant/src/digiquant/atlas/` imports work end-to-end; tests pass.
- [ ] `frontend/digiquant-atlas/` builds via workspace; design-system imports resolve.
- [ ] CI runs Atlas tests as part of digiquant suite.
- [ ] All docs, CLAUDE.md, AGENTS.md, ARCHITECTURE.md, and memory pointers updated.
- [ ] One full daily Atlas run succeeds in the new layout before closing the epic.
