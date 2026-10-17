# Surfaces (canonical list)

| Surface | Code | Production | Local preview |
|---|---|---|---|
| digithings site | `apps/digithings-web` | digithings.ai | http://localhost:4040/ |
| digiquant site | `apps/digiquant-web` | digiquant.io | http://localhost:4020/ |
| **digiquant app (Brief desk)** | `apps/digiquant-web/app/app` | digiquant.io/app | http://localhost:4020/app |
| digichat | `apps/digichat` | digithings.ai/chat | http://localhost:3000/ |
| design kit | `packages/design` | — | http://localhost:4030/ |
| digiquant TUI | `clients/digiquant-tui` | — | `bun run` in that folder |
| digichat TUI / devkit | `clients/digichat-tui`, `clients/digichat-devkit` | — | `bun run` in those folders |

The Brief desk is the one digiquant app (ADR D2). It is served at `/app`;
`/app/brief` redirects there. `apps/digiquant-app` was deleted on 2026-10-11 and
its keyboard map moved to the desk: see `digiquant-app-shortcuts.md`.

Start all local previews with `scripts/preview_surfaces.sh`.
