# `data/` (gitignored)

The entire `data/` tree is **ignored by git** (see repo-root `.gitignore`). **Canonical state lives in Supabase** — not on disk.

## Normal operation

Cowork and agent tasks **publish JSON to Supabase** (`documents`, `daily_snapshots`, …) per [`RUNBOOK.md`](../RUNBOOK.md). You do **not** need a populated `data/` directory. Clones often have **no** `data/` folder; you can delete local `data/` whenever nothing is in progress.

## When this directory has files

Some **scripts** create paths under `data/` while they run:

- **Backfill** workflows may place daily exports under `data/agent-cache/daily/` before replaying into Supabase.
- **Fetch** helpers may write transient JSON (e.g. quotes/macro) under `data/agent-cache/daily/<date>/data/` for local use. If Supabase is current, treat Supabase as authoritative.
- **Evolution** post-mortem flows may write JSON before an operator runs `git-commit.sh --evolution`, depending on setup.

Anything here is **tool output**, not the source of truth for the app.
