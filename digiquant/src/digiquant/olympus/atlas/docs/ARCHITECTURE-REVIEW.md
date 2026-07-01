# Architecture (redirect)

**This file name is kept for bookmarks.** All architecture content lives in one place:

| Doc | Use |
|-----|-----|
| **[`docs/agentic/ARCHITECTURE.md`](agentic/ARCHITECTURE.md)** | **Canonical** system design: cadence, pipeline phases, dashboard, repo layout |
| [`docs/agentic/WORKFLOWS.md`](agentic/WORKFLOWS.md) | Day-to-day procedures (baseline, delta, rollups, recovery) |
| [`RUNBOOK.md`](../RUNBOOK.md) | Operator truth: env, publish, validate, CI |
| [`docs/SYSTEM-SCORECARD.md`](SYSTEM-SCORECARD.md) | Health / maturity snapshot (dated) |
| [`docs/agentic/PLATFORMS.md`](agentic/PLATFORMS.md) | IDE and agent platform setup |

The former long-form “review” (inventory diagrams, legacy Vite tree, extended schema ASCII) was **folded into** `docs/agentic/ARCHITECTURE.md` and trimmed so the migration baseline does not carry duplicate narratives. Database details: `supabase/migrations/` and generated types in `frontend/lib/database.types.ts`.
