# Task: Move Atlas frontend into `frontend/` umbrella

> **Historical note (2026-06):** Completed — Atlas UI is `frontend/olympus/` (not `frontend/atlas/`). Backend is `digiquant/src/digiquant/olympus/atlas/`.

**Title:** `[agent] Move apps/digiquant-atlas/frontend/ → frontend/atlas/ (all web frontends co-located)`

**Labels:** `agent-task`, `component:digiquant`, `priority:high`, `complexity:S`, `type:migration`, `risk:low`

**Component:** digiquant
**Risk:** low
**Execution tier:** claude (cross-module path updates + CI filter updates)
**Model:** sonnet

## Goal

Unify every web frontend under `frontend/`. Today Atlas's Next.js app is the only frontend living outside the umbrella (at `apps/digiquant-atlas/frontend/`). Moving it to `frontend/atlas/` gives a single, predictable home for all UI code (digithings, digiquant, digichat, atlas, design) and makes the npm workspace topology consistent.

Sequence: do **after** the frontend rename task (draft 06), so this moves into a freshly-consistent neighborhood.

This is a **move, not a refactor** — no behavior or dependency changes. The backend Python app stays at `apps/digiquant-atlas/` until the larger migration epic (#NEW-Atlas-into-digiquant) runs.

## Acceptance criteria

- [ ] `frontend/atlas/` exists with the contents previously at `apps/digiquant-atlas/frontend/`.
- [ ] `apps/digiquant-atlas/frontend/` no longer exists.
- [ ] Root `package.json` workspaces already use `frontend/*` glob, so no change needed; `apps/*/frontend` entry can be dropped once Atlas is the last user (verify and clean up).
- [ ] `npm install` at repo root succeeds.
- [ ] `npm --workspace frontend/atlas run build` succeeds.
- [ ] `npm --workspace frontend/atlas run lint` passes.
- [ ] `@digithings/design` workspace dep resolves from the new location (`frontend/atlas/` → `frontend/design/`).
- [ ] Any relative imports that reached up into the Atlas Python app (e.g., for config) are either preserved via explicit config files or documented.
- [ ] CI `paths:` filters updated in every workflow that mentions `apps/digiquant-atlas/frontend/` — especially `digichat-test.yml` pattern analogs, and any Atlas-specific workflow in `apps/digiquant-atlas/.github/workflows/` that references the frontend path.
- [ ] README and `apps/digiquant-atlas/AGENTS.md` updated to note the frontend now lives at `frontend/digiquant-atlas/`.
- [ ] `CLAUDE.md` "Frontend umbrella" section updated to list `frontend/atlas/` alongside the others and remove the `apps/digiquant-atlas/frontend/` exception.
- [ ] ADR-0009 frontmatter/status updated to reflect Atlas now fully in the umbrella (remove the "joins in place" carve-out).
- [ ] No runtime regressions: `npm --workspace frontend/digiquant-atlas run dev` starts, renders, and hits whatever backend it currently hits.

## Documentation

- `CLAUDE.md` — frontend umbrella section.
- `docs/adr/0009-frontend-umbrella.md` — remove the Atlas carve-out.
- `apps/digiquant-atlas/AGENTS.md` — note frontend relocation.
- `apps/digiquant-atlas/README.md` — same.
- `frontend/atlas/README.md` — new; brief pointer explaining this is the Atlas UI for the Python backend at `apps/digiquant-atlas/`.

## Context / links

- ADR-0009 (frontend umbrella) — the pattern this aligns Atlas with.
- Parent epic (future): `[Epic] Migrate Atlas from apps/ into digiquant module` — this task is a piece of it, extracted because it's low-risk and immediately valuable.
- Related: #263 (Atlas adopted design tokens) — already uses `@digithings/design`, so workspace resolution is the only mechanical blocker.

## Explicit non-goals

- Moving Atlas Python code.
- Moving supabase migrations, scripts, skills, or docs.
- Any change to Atlas's backend behavior, data flow, or deployment.
- Consolidating `.github/workflows/` from `apps/digiquant-atlas/`.
