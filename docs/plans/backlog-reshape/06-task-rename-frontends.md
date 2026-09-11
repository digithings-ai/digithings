# Task: Simplify frontend folder naming

**Historical record — completed task.** The `chat.digithings.ai` domain target named below (ADR-0002) was later superseded by [ADR-0018](../../adr/0018-digichat-path-routing.md), which routes digichat at `digithings.ai/chat`. The folder-rename work itself is unaffected and already shipped.

**Title:** `[agent] Rename cloudflare/digithings/ → cloudflare/digithings/ and cloudflare/digiquant/ → cloudflare/digiquant/`

**Labels:** `agent-task`, `component:root`, `priority:high`, `complexity:S`, `type:migration`, `risk:low`

**Component:** website / root docs
**Risk:** low
**Execution tier:** cursor
**Model:** sonnet

## Goal

Consistent, minimal names across `cloudflare/`. Today the directories mix types (`website`, `design`) with products (`digichat`, `digiquant-web`). Standardize on the product name — no `-web`, no `website` — so each folder is `cloudflare/<product>/`.

Final layout:
```
cloudflare/
├── digithings/       (was website/)         → digithings.ai
├── digiquant/        (was digiquant-web/)   → digiquant.io
├── digichat/         (unchanged)            → chat.digithings.ai
├── atlas/            (added by task 05)     → atlas.digiquant.io
└── design/    (unchanged)            → shared workspace package
```

## Acceptance criteria

- [ ] `git mv cloudflare/digithings cloudflare/digithings`.
- [ ] `git mv cloudflare/digiquant cloudflare/digiquant`.
- [ ] Root `package.json` workspaces `cloudflare/*` glob continues to resolve; `npm install` clean.
- [ ] `.github/workflows/static.yml` updated: `cp -r cloudflare/digithings/. dist/` → `cp -r cloudflare/digithings/. dist/`.
- [ ] CNAME files preserved inside the renamed dirs (content unchanged: `digithings.ai`, `digiquant.io`).
- [ ] `CLAUDE.md` frontend umbrella section updated to reflect new names.
- [ ] `docs/adr/0009-frontend-umbrella.md` updated with new paths.
- [ ] `docs/adr/0002-domain-unification.md` updated if it mentions old paths.
- [ ] `AGENTS.md` root updated if it mentions `cloudflare/digithings/` or `cloudflare/digiquant/`.
- [ ] READMEs inside the renamed dirs updated (title + any self-references).
- [ ] `cloudflare/digiweb/design/README.md` updated if it lists consumers by old name.
- [ ] GitHub Pages deploy from `static.yml` still serves digithings.ai after merge (verify on develop push or via workflow_dispatch).
- [ ] Any documentation of the setup in `docs/` grepped for `cloudflare/digithings` or `cloudflare/digiquant` — all updated.

## Documentation

- `CLAUDE.md`
- `docs/adr/0009-frontend-umbrella.md`
- `docs/adr/0002-domain-unification.md`
- `AGENTS.md`
- Per-folder READMEs inside the renamed dirs.

## Context / links

- Precedes task "Move Atlas frontend → `cloudflare/atlas/`" so the final layout settles in one coherent sweep.
- Naming locked in conversation with Chris: drop `-web`, drop `website`, product names only.

## Non-goals

- No content changes inside the renamed folders.
- No deployment target changes — CNAMEs unchanged, Pages still serves digithings.ai from the same artifact.
- No change to `cloudflare/digichat/` or `cloudflare/digiweb/design/`.
