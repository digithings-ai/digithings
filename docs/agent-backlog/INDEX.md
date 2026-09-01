# Agent backlog index

**Status vocabulary:** `todo` → `in_progress` → `done` (or `blocked` with reason in the issue).

Update this file when themes start/complete. Link **GitHub Issues** (not bare TODOs) so remote agents can resolve IDs.

| Theme | Status | Primary issues | Notes / ADRs |
|-------|--------|----------------|--------------|
| Design evolution (Graphite/Cursor/xAI primitives) | done | [#1200](https://github.com/digithings-ai/digithings/issues/1200) epic, #1201–#1231 · [backlog index](design-evolution/INDEX.md) | [`EVOLUTION.md`](../../frontend/digiweb/design/EVOLUTION.md) — all phases shipped except the #1212 changelog band (deferred: no releases data source) · extends #235 |
| Agent ops & doc hygiene | in_progress | _(add GitHub issue URLs)_ | [ADR template](../adr/0000-template.md) |
| digiskills — agent-skill compiler | in_progress | [#1453](https://github.com/digithings-ai/digithings/issues/1453) epic, #1454 P0 (ADR, done), #1458 P1 (compiler core, done), [#1472](https://github.com/digithings-ai/digithings/issues/1472) P2 (dogfood) | [ADR-0023](../adr/0023-digiskills-agent-skill-compiler.md) |
| Self-host GHCR + OpenAPI | in_progress | [#2016](https://github.com/digithings-ai/digithings/issues/2016) epic, #2017–#2021 | GHCR publish, pull compose, committed OpenAPI |
| Execution tenancy | done | [#3388](https://github.com/digithings-ai/digithings/issues/3388) live-proof follow-up · [kairos-tenancy/](kairos-tenancy/README.md) · [HUMAN-UNBLOCK](kairos-tenancy/HUMAN-UNBLOCK.md) | Owner closed 2026-09-01 without a live E2E / house schedule. All 12 WPs on `develop`. Pick up [#3388](https://github.com/digithings-ai/digithings/issues/3388) after the next `pipeline-olympus.yml` `0 12 * * *` run (never `workflow_dispatch`). Last probes (not proof): house proof exit **5** while `origin/main` is UUID-hotfix `3601f72df` (merge fail-softs #3343 → #3348 → #3351 → #3354, then unique-conflict [#3387](https://github.com/digithings-ai/digithings/pull/3387); authoring agent must not merge `main`). Pages twin [#3356](https://github.com/digithings-ai/digithings/pull/3356) HEAD `ebbb311b5` is CI-green (Alpaca `/dashboard/settings/brokers/callback/` export required); human-merge only. Do not `--apply` until `/dashboard/` **and** that callback are 200. Staging E2E still exit **3** (`/olympus` vs `/dashboard` pin). Vendor secrets still missing. Overlay private books fail-closed until staged `cutover/113` after unique writers are on `main` and a green scheduled run proves them. Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183)/[#3256](https://github.com/digithings-ai/digithings/pull/3256); never apply cutover 900. |
| Product rebrand (retire olympus / atlas / hermes / kairos) | in_progress | [ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md) | [Scope](../plans/2026-08-30-product-rebrand-scope.md) — [#3325](https://github.com/digithings-ai/digithings/pull/3325) on `develop`: public path `/dashboard/` only, workspace `frontend/dashboard`. Live Pages still `/olympus` until a human coordinates Pages+EF cutover. Python packages and SQL tables stay until later hops. |
| _(example) digigraph hub mode_ | todo |  | |

## Quick links

- [ROADMAP.md](../../ROADMAP.md) — phases
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — human + agent rules
- [docs/agents/PLAYBOOK.md](../agents/PLAYBOOK.md) — when to use explore / CI / shell sub-agents

## Repository

Canonical remote: **[digithings-ai/digithings](https://github.com/digithings-ai/digithings)** (organization repo). File issues and agent tasks there even when developing from a personal fork.

- Issues: https://github.com/digithings-ai/digithings/issues
- New agent task: https://github.com/digithings-ai/digithings/issues/new?template=agent_task.yml
