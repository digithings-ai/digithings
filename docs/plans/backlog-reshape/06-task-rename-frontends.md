# Task: Simplify frontend folder naming

**Title:** `[agent] Rename frontend/website/ → frontend/digithings/ and frontend/digiquant-web/ → frontend/digiquant/`

**Labels:** `agent-task`, `component:root`, `priority:high`, `complexity:S`, `type:migration`, `risk:low`

**Component:** website / root docs
**Risk:** low
**Execution tier:** cursor
**Model:** sonnet

## Goal

Consistent, minimal names across `frontend/`. Today the directories mix types (`website`, `design-system`) with products (`digichat`, `digiquant-web`). Standardize on the product name — no `-web`, no `website` — so each folder is `frontend/<product>/`.

Final layout:
```
frontend/
├── digithings/       (was website/)         → digithings.ai
├── digiquant/        (was digiquant-web/)   → digiquant.io
├── digichat/         (unchanged)            → chat.digithings.ai
├── atlas/            (added by task 05)     → atlas.digiquant.io
└── design-system/    (unchanged)            → shared workspace package
```

## Acceptance criteria

- [ ] `git mv frontend/website frontend/digithings`.
- [ ] `git mv frontend/digiquant-web frontend/digiquant`.
- [ ] Root `package.json` workspaces `frontend/*` glob continues to resolve; `npm install` clean.
- [ ] `.github/workflows/static.yml` updated: `cp -r frontend/website/. dist/` → `cp -r frontend/digithings/. dist/`.
- [ ] CNAME files preserved inside the renamed dirs (content unchanged: `digithings.ai`, `digiquant.io`).
- [ ] `CLAUDE.md` frontend umbrella section updated to reflect new names.
- [ ] `docs/adr/0009-frontend-umbrella.md` updated with new paths.
- [ ] `docs/adr/0002-domain-unification.md` updated if it mentions old paths.
- [ ] `AGENTS.md` root updated if it mentions `frontend/website/` or `frontend/digiquant-web/`.
- [ ] READMEs inside the renamed dirs updated (title + any self-references).
- [ ] `frontend/design-system/README.md` updated if it lists consumers by old name.
- [ ] GitHub Pages deploy from `static.yml` still serves digithings.ai after merge (verify on develop push or via workflow_dispatch).
- [ ] Any documentation of the setup in `docs/` grepped for `frontend/website` or `frontend/digiquant-web` — all updated.

## Documentation

- `CLAUDE.md`
- `docs/adr/0009-frontend-umbrella.md`
- `docs/adr/0002-domain-unification.md`
- `AGENTS.md`
- Per-folder READMEs inside the renamed dirs.

## Context / links

- Precedes task "Move Atlas frontend → `frontend/atlas/`" so the final layout settles in one coherent sweep.
- Naming locked in conversation with Chris: drop `-web`, drop `website`, product names only.

## Non-goals

- No content changes inside the renamed folders.
- No deployment target changes — CNAMEs unchanged, Pages still serves digithings.ai from the same artifact.
- No change to `frontend/digichat/` or `frontend/design-system/`.
