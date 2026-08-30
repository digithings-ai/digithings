# Agent backlog index

**Status vocabulary:** `todo` → `in_progress` → `done` (or `blocked` with reason in the issue).

Update this file when themes start/complete. Link **GitHub Issues** (not bare TODOs) so remote agents can resolve IDs.

| Theme | Status | Primary issues | Notes / ADRs |
|-------|--------|----------------|--------------|
| Design evolution (Graphite/Cursor/xAI primitives) | done | [#1200](https://github.com/digithings-ai/digithings/issues/1200) epic, #1201–#1231 · [backlog index](design-evolution/INDEX.md) | [`EVOLUTION.md`](../../frontend/digiweb/design/EVOLUTION.md) — all phases shipped except the #1212 changelog band (deferred: no releases data source) · extends #235 |
| Agent ops & doc hygiene | in_progress | _(add GitHub issue URLs)_ | [ADR template](../adr/0000-template.md) |
| digiskills — agent-skill compiler | in_progress | [#1453](https://github.com/digithings-ai/digithings/issues/1453) epic, #1454 P0 (ADR, done), #1458 P1 (compiler core, done), [#1472](https://github.com/digithings-ai/digithings/issues/1472) P2 (dogfood) | [ADR-0023](../adr/0023-digiskills-agent-skill-compiler.md) |
| Self-host GHCR + OpenAPI | in_progress | [#2016](https://github.com/digithings-ai/digithings/issues/2016) epic, #2017–#2021 | GHCR publish, pull compose, committed OpenAPI |
| Execution tenancy | blocked | [kairos-tenancy/](kairos-tenancy/README.md) · [HUMAN-UNBLOCK](kairos-tenancy/HUMAN-UNBLOCK.md) | All 12 WPs on `develop`. [#3325](https://github.com/digithings-ai/digithings/pull/3325) (`a8bd41741`) pins `/dashboard/` + `frontend/dashboard`. Staging E2E Observer hop `GET /settings/app-urls` fails that contract while live Pages still serve `/olympus` (exit 3). Do not weaken `public_app_urls_ok`. Vendor secrets still missing (would be exit 2 after the path hop). House documents upsert [#3278](https://github.com/digithings-ai/digithings/pull/3278), ledger stamp [#3331](https://github.com/digithings-ai/digithings/pull/3331) (`9f898ec1d`, `on_conflict=date`), and UUID stringify [#3334](https://github.com/digithings-ai/digithings/pull/3334) (`3601f72df`) are on `main`. Develop port [#3335](https://github.com/digithings-ai/digithings/pull/3335). H9 recovery CLI [#3337](https://github.com/digithings-ai/digithings/pull/3337) (`eb791dd99`); economic_calendar authenticated SELECT ledger [#3338](https://github.com/digithings-ai/digithings/pull/3338) (`db3745b7e`, migration **114** — do not steal 113). Do **not** merge [#3332](https://github.com/digithings-ai/digithings/pull/3332) or [#3321](https://github.com/digithings-ai/digithings/pull/3321). Scheduled house GHA `33426508863` **failed** (`23502` then UUID `TypeError` on pre-#3331/#3334 main). [#3342](https://github.com/digithings-ai/digithings/pull/3342) (`3f3119988`) on `develop` maps `bias='cautious'` and caps H6 amendment reasons at 2000; main cherry-pick [#3343](https://github.com/digithings-ai/digithings/pull/3343) is human-merge only. [#3349](https://github.com/digithings-ai/digithings/pull/3349) (`b7cc98fad`) on `develop` flattens Gemini pair-list Finding maps and unwraps H6 `{terms:…}` envelopes (tenor from H5 base only); main [#3348](https://github.com/digithings-ai/digithings/pull/3348) is human-merge only (PatchOp add + Finding coerce + pair-list). [#3353](https://github.com/digithings-ai/digithings/pull/3353) (`6f45d073f`) on `develop` maps digest `horizon_hourse` and clamps H6 `conviction_delta`; main [#3354](https://github.com/digithings-ai/digithings/pull/3354) is human-merge only. Monday 2026-08-31 ledger recovered operator-side (`8ab9840f-…`); that is not a green GHA run. Next `0 12 * * *` cron is the live pipeline proof — do not `workflow_dispatch`. Overlay private books fail-closed [#3277](https://github.com/digithings-ai/digithings/pull/3277); unique-drop staged as `cutover/113` (not applied while main writers are date-only). Do not merge draft [#3183](https://github.com/digithings-ai/digithings/pull/3183)/[#3256](https://github.com/digithings-ai/digithings/pull/3256); never apply cutover 900. |
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
