# Operations reference (non-runtime)

These files are **guidance** for humans and agents. They are not loaded by validation scripts as canonical config.

| File | Purpose |
|------|---------|
| [SCRIPTS.md](SCRIPTS.md) | Script index (DB-first, data, migration) |
| [data-sources.md](data-sources.md) | URLs, feeds, MCP notes, calendars |
| [email-research.md](email-research.md) | Gmail + newsletter intake |
| [PRE-MIGRATION-CLEANUP.md](PRE-MIGRATION-CLEANUP.md) | **Do first:** lean the repo before moving to DigiThings (data hygiene, script/skill audit, migration file policy) |
| [REPOSITORY-INVENTORY.md](REPOSITORY-INVENTORY.md) | **Full map:** every tracked top-level path, counts, gitignored patterns, pre–Wave 1 verification checklist |
| [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md) | **After cleanup:** DigiThings + DigiQuant + DigiGraph + multi-tenant waves (saved from implementation planning) |
| [DIGITHINGS-WAVE1-PLAN.md](DIGITHINGS-WAVE1-PLAN.md) | **Wave 1:** Monorepo import, Next/basePath, env/CI checklist (companion to roadmap § P1) |
| [DIGITHINGS-WAVE2-GRAPH-SKETCH.md](DIGITHINGS-WAVE2-GRAPH-SKETCH.md) | **Wave 2:** DigiGraph graph families, node types, Cowork→graph mapping, env/idempotency (companion to roadmap § P1b) |
| [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md) | Scripts CI, smoke-test, or core docs depend on—do not remove without review |
| [SKILLS-AUDIT.md](SKILLS-AUDIT.md) | Optional: skills not linked from orchestrator/tasks/AGENTS (consolidation candidates) |

**P0 (migrations):** `supabase/migrations/*.sql` is **append-only** for any database that has already applied those files—do not delete or renumber to “clean up.”

Runtime inputs remain under `config/` (`watchlist.md`, `portfolio.json`, `investment-profile.md`, etc.).
