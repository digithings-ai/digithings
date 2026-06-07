# Skills audit (orchestrator / tasks / AGENTS)

**Purpose:** List `skills/<slug>/SKILL.md` folders that are **not** referenced by path in:

- [`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md)
- [`AGENTS.md`](../../AGENTS.md)
- [`cowork/tasks/*.md`](../../cowork/tasks/)

These are **candidates for future consolidation** or explicit linking — **not** delete targets unless you are retiring a feature.

## Not referenced in those three locations (49 skills total)

| Skill slug | Notes |
|------------|--------|
| `deep-dive` | Often used from docs / other tasks; link when adding deep-dive runs. |
| `digest` | Supporting skill; may be inlined in orchestrator narrative. |
| `earnings` | Sector / calendar workflow. |
| `github-workflow` | Meta; referenced from docs/agentic elsewhere. |
| `orchestrator` | Hub skill — **expected** not to self-link as `skills/orchestrator/`. |
| `premarket-pulse` | Optional cadence. |
| `profile-setup` | Onboarding. |
| `research-daily` | Referenced from [`RUNBOOK.md`](../../RUNBOOK.md) / research tasks. |
| `research-library` | Library publish/fetch flow. |
| `sector-heatmap` | Analytics. |
| `sector-rotation` | Analytics. |
| `thesis` | Thesis layer; may chain via other skills. |
| `thesis-tracker` | Aligns with `agents/thesis-tracker.agent.md`. |

**Referenced count** in those files: **36** of **49** skills (by `skills/<slug>/` path pattern).

Widening the grep to `docs/agentic/`, `RUNBOOK.md`, and `docs/agentic/SKILLS-CATALOG.md` will show additional links — this pass matches [`PRE-MIGRATION-CLEANUP.md`](PRE-MIGRATION-CLEANUP.md) § P4.
