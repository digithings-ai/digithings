# Agent backlog index

**Status vocabulary:** `todo` → `in_progress` → `done` (or `blocked` with reason in the issue).

Update this file when themes start/complete. Link **GitHub Issues** (not bare TODOs) so remote agents can resolve IDs.

| Theme | Status | Primary issues | Notes / ADRs |
|-------|--------|----------------|--------------|
| Design evolution (Graphite/Cursor/xAI primitives) | done | [#1200](https://github.com/digithings-ai/digithings/issues/1200) epic, #1201–#1231 · [backlog index](design-evolution/INDEX.md) | [`EVOLUTION.md`](../../frontend/digiweb/design/EVOLUTION.md) — all phases shipped except the #1212 changelog band (deferred: no releases data source) · extends #235 |
| Agent ops & doc hygiene | in_progress | _(add GitHub issue URLs)_ | [ADR template](../adr/0000-template.md) |
| digiskills — agent-skill compiler | in_progress | [#1453](https://github.com/digithings-ai/digithings/issues/1453) epic, #1454 P0 (ADR, done), #1458 P1 (compiler core, done), [#1472](https://github.com/digithings-ai/digithings/issues/1472) P2 (dogfood) | [ADR-0023](../adr/0023-digiskills-agent-skill-compiler.md) |
| Self-host GHCR + OpenAPI | in_progress | [#2016](https://github.com/digithings-ai/digithings/issues/2016) epic, #2017–#2021 | GHCR publish, pull compose, committed OpenAPI |
| Execution tenancy | done | [#3391](https://github.com/digithings-ai/digithings/issues/3391) live-proof follow-up · [kairos-tenancy/](kairos-tenancy/README.md) · [HUMAN-UNBLOCK](kairos-tenancy/HUMAN-UNBLOCK.md) | Owner closed 2026-09-01 without a live E2E / house schedule. All 12 WPs on `develop`. `origin/main` is `c532fc096` after squash-merge #3343 → #3348 → #3351 → #3354 → [#3387](https://github.com/digithings-ai/digithings/pull/3387) → [#3356](https://github.com/digithings-ai/digithings/pull/3356) → [#3359](https://github.com/digithings-ai/digithings/pull/3359) → [#3340](https://github.com/digithings-ai/digithings/pull/3340). Pick up [#3391](https://github.com/digithings-ai/digithings/issues/3391) after the next `pipeline-olympus.yml` `17 9/10/11/12 * * *` run (never `workflow_dispatch`). Live probes 2026-09-01T10:04Z (not proof): house **3** (waiting for schedule after `2026-09-01T10:03:42Z`); `--dispatch` **4**; pages gate **3** (`/dashboard/*` still 404 — do not `--apply`). Overlay private books stay fail-closed until staged `cutover/113` after a green scheduled run proves the widened upserts. Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183)/[#3256](https://github.com/digithings-ai/digithings/pull/3256); never apply cutover 900. |
| Product rebrand (retire olympus / atlas / hermes / kairos) | in_progress | [ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md) | [Scope](../plans/2026-08-30-product-rebrand-scope.md) — [#3325](https://github.com/digithings-ai/digithings/pull/3325) on `develop`: public path `/dashboard/` only, workspace `frontend/dashboard`. Live Pages still `/olympus` until a human coordinates Pages+EF cutover. Python packages and SQL tables stay until later hops. |
| Flagship follow-up (recovery / live-path insert / dashboard SSOT) | in_progress | [#3426](https://github.com/digithings-ai/digithings/issues/3426) | Must-fixes from reviews of #3328, #3329, #3337. One PR into `develop`. |
| _(example) digigraph hub mode_ | todo |  | |

## Quick links

- [ROADMAP.md](../../ROADMAP.md) — phases
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — human + agent rules
- [docs/agents/PLAYBOOK.md](../agents/PLAYBOOK.md) — when to use explore / CI / shell sub-agents

## Repository

Canonical remote: **[digithings-ai/digithings](https://github.com/digithings-ai/digithings)** (organization repo). File issues and agent tasks there even when developing from a personal fork.

- Issues: https://github.com/digithings-ai/digithings/issues
- New agent task: https://github.com/digithings-ai/digithings/issues/new?template=agent_task.yml
