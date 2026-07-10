# Agent backlog index

**Status vocabulary:** `todo` → `in_progress` → `done` (or `blocked` with reason in the issue).

Update this file when themes start/complete. Link **GitHub Issues** (not bare TODOs) so remote agents can resolve IDs.

| Theme | Status | Primary issues | Notes / ADRs |
|-------|--------|----------------|--------------|
| Design evolution (Graphite/Cursor/xAI primitives) | done | [#1200](https://github.com/digithings-ai/digithings/issues/1200) epic, #1201–#1231 · [backlog index](design-evolution/INDEX.md) | [`EVOLUTION.md`](../../frontend/digiweb/design/EVOLUTION.md) — all phases shipped except the #1212 changelog band (deferred: no releases data source) · extends #235 |
| Agent ops & doc hygiene | in_progress | _(add GitHub issue URLs)_ | [ADR template](../adr/0000-template.md) |
| DigiSkills — agent-skill compiler | in_progress | [#1453](https://github.com/digithings-ai/digithings/issues/1453) epic, #1454 P0 (ADR, done), #1458 P1 (compiler core, done), [#1472](https://github.com/digithings-ai/digithings/issues/1472) P2 (dogfood) | [ADR-0023](../adr/0023-digiskills-agent-skill-compiler.md) |
| _(example) DigiGraph hub mode_ | todo |  | |

## Quick links

- [ROADMAP.md](../../ROADMAP.md) — phases
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — human + agent rules
- [docs/agents/PLAYBOOK.md](../agents/PLAYBOOK.md) — when to use explore / CI / shell sub-agents

## Repository

Canonical remote: **[digithings-ai/digithings](https://github.com/digithings-ai/digithings)** (organization repo). File issues and agent tasks there even when developing from a personal fork.

- Issues: https://github.com/digithings-ai/digithings/issues
- New agent task: https://github.com/digithings-ai/digithings/issues/new?template=agent_task.yml
