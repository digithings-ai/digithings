# Skills audit (graph-loaded skills / tasks / AGENTS)

**Purpose:** List `skills/<slug>/SKILL.md` folders that are **not** referenced by path in:

- [`skills/digest/SKILL.md`](../../skills/digest/SKILL.md)
- [`AGENTS.md`](../../AGENTS.md)
- [`cowork/tasks/*.md`](../../cowork/tasks/)

These are **candidates for future consolidation** or explicit linking — **not** delete targets unless you are retiring a feature.

> **Note:** This audit covers graph-loaded skills only. Retired human-session wrappers have been removed from the skill directories and are no longer tracked here.

## Not referenced in those three locations

| Skill slug | Notes |
|------------|--------|
| `digest` | Supporting skill; may be inlined in pipeline narrative. |

**Referenced count** in those files: the majority of graph-loaded skills. Widen the grep to `docs/agentic/`, `RUNBOOK.md`, and `docs/agentic/SKILLS-CATALOG.md` to see additional links — this pass matches [`PRE-MIGRATION-CLEANUP.md`](PRE-MIGRATION-CLEANUP.md) § P4.
