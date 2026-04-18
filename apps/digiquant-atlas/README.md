# digiquant-atlas

Daily market intelligence with an AI-orchestrated pipeline. **Canonical state is DB-first (Supabase)**; JSON artifacts are the source of truth and markdown is derived.

## Start here

| Doc | Purpose |
|-----|---------|
| **[RUNBOOK.md](RUNBOOK.md)** | **Authoritative** operator steps (env, publish, validate) |
| [AGENTS.md](AGENTS.md) | Agent behavior + `python3 scripts/run_db_first.py` |
| [docs/agentic/WORKFLOWS.md](docs/agentic/WORKFLOWS.md) | Procedures (baseline, delta, rollups) |
| [docs/agentic/PLATFORMS.md](docs/agentic/PLATFORMS.md) | IDE / platform setup |
| [docs/ops/PRE-MIGRATION-CLEANUP.md](docs/ops/PRE-MIGRATION-CLEANUP.md) | **Before monorepo move:** lean repo (scripts/skills audit, data hygiene) |
| [docs/ops/REPOSITORY-INVENTORY.md](docs/ops/REPOSITORY-INVENTORY.md) | **Full folder/file accounting** for migration (tracked paths + gitignore policy) |
| [docs/ops/MIGRATION-ROADMAP-DIGITHINGS.md](docs/ops/MIGRATION-ROADMAP-DIGITHINGS.md) | **After cleanup:** DigiThings + DigiGraph + multi-tenant roadmap (Wave 1: [docs/ops/DIGITHINGS-WAVE1-PLAN.md](docs/ops/DIGITHINGS-WAVE1-PLAN.md); Wave 2: [docs/ops/DIGITHINGS-WAVE2-GRAPH-SKETCH.md](docs/ops/DIGITHINGS-WAVE2-GRAPH-SKETCH.md)) |
| [cowork/](cowork/) | **Claude Cowork:** start at [`cowork/README.md`](cowork/README.md); paste [`cowork/PROJECT-PROMPT.md`](cowork/PROJECT-PROMPT.md) into project settings; tasks in [`cowork/tasks/`](cowork/tasks/) |

## One command

```bash
python3 scripts/run_db_first.py
```

## Repository layout (high level)

```
config/           Runtime inputs: watchlist, portfolio, investment profile
skills/<slug>/    Instruction packages (orchestrator, macro, sector-*, …)
templates/schemas/JSON schemas for artifacts
scripts/          Automation (run_db_first.py, materialize_snapshot.py, …)
data/             Contents are **gitignored** (price cache, optional scratch). **`data/README.md`** is tracked and explains the tree. **Supabase** is canonical — see [RUNBOOK.md](RUNBOOK.md)
docs/research/    Curated research doctrine (see skills/research-library)
frontend/         Next.js dashboard
supabase/         SQL migrations
```

## Skills

Skills live in **`skills/<skill-slug>/SKILL.md`**. Load **only** the skill for the phase you are running (see `skills/orchestrator/SKILL.md`).

## Scripts (common)

```bash
python3 scripts/run_db_first.py   # DB-first entry
./scripts/new-day.sh               # Print baseline/delta prompt for Claude
./scripts/status.sh                # Supabase validation
./scripts/weekly-rollup.sh         # Weekly JSON scaffold + prompt
./scripts/monthly-rollup.sh       # Monthly JSON scaffold + prompt
./scripts/scaffold_evolution_day.sh  # Post-mortem JSON scaffolds
./scripts/git-commit.sh            # Commit (runs ETL)
```

## Documentation index

| File | Contents |
|------|----------|
| `CLAUDE.md` | Claude Code quick commands |
| `CLAUDE_PROJECT_INSTRUCTIONS.md` | Claude.ai Projects: pointers only (paste `cowork/PROJECT-PROMPT.md`) |
| `docs/agentic/ARCHITECTURE.md` | System design (**canonical**; [`docs/ARCHITECTURE-REVIEW.md`](docs/ARCHITECTURE-REVIEW.md) is a short redirect for old links) |
| `docs/agentic/MEMORY-SYSTEM.md` | Memory format |
| `docs/agentic/SKILLS-CATALOG.md` | Skill index (keep short; filesystem is source of truth) |
| `docs/ops/SCRIPTS.md` | Script index (publish, data, migration) |
| `docs/ops/` | Sourcing / email ops (non-runtime reference) |
