# Cowork operator setup — live file

**Last configured:** 2026-04-15 (updated: per-segment delta docs for Track A; research-only digest; deliberation schema gates)

---

## Summary

- **Timezone:** America/New_York
- **Pattern:** Modular tasks (Pattern B) — two separate sequential Cowork jobs per weekday
- **Research task:** `cowork/tasks/research-daily-delta.md` → **6:00 AM ET** (10:00 UTC), Mon–Fri
- **Positioning task:** `cowork/tasks/portfolio-pm-rebalance.md` → **8:00 AM ET** (12:00 UTC), Mon–Fri
- **Sequencing:** Research publishes the `digest` first; Positioning (Track B) reads it and won't start until 2 hours later
- **Target:** Both complete before US equity market open at **9:30 AM ET**
- **Month-end:** Last US equity session — swap research task file to `research-monthly-synthesis.md` that day
- **Sunday:** Swap research task file to `research-weekly-baseline.md` (cron `0 10 * * 0`)
- **Portfolio:** Separate task, daily, pre-market only

**DST note:** Crons are UTC-fixed. EDT (UTC-4, Apr–Oct) → 6 AM / 8 AM ET. EST (UTC-5, Nov–Mar) → 5 AM / 7 AM ET. Both remain safely pre-open year-round.

---

## Paste into Cowork — project instructions

Open Cowork **Project → Instructions** and paste the block below (contents of `cowork/PROJECT-PROMPT.md`):

```
digiquant-atlas (workspace = this repo root)

1. Always read cowork/PROJECT.md at the start of every session before doing work.
2. When a scheduled task runs, also read the task file named in that task's instructions (under cowork/tasks/). Do not skip the task file.
3. Canonical operations live in RUNBOOK.md (publish, validate, schedules). Agent behavior in AGENTS.md. Follow them for anything not spelled out here.
4. Supabase + JSON are source of truth; markdown is derived. Do not recreate historical markdown-on-disk workflows.
5. GitHub Actions refresh prices/technicals/metrics into the database on a weekday schedule. When Supabase MCP is available, read that state from the DB (prices, technicals, portfolio tables) instead of guessing or relying on training data. Writes: use scripts/publish_document.py and RUNBOOK.md flows — local data/agent-cache/ alone is not sufficient.
6. Other MCP tools you have enabled (e.g. FRED, Alpha Vantage, CoinGecko, SEC, fear & greed) are optional — use only when they help the specific research question; you are not required to call every tool. See cowork/PROJECT.md (MCP section) and docs/ops/data-sources.md.
7. Never invent live prices, yields, or numbers from model cutoff knowledge; use DB/MCP/search as appropriate.
8. Cowork setup: If the user asks to set up, configure, or schedule Atlas in Claude Cowork (project + tasks), follow cowork/SETUP-ATLAS-COWORK.md end-to-end.
```

---

## Paste into Cowork — Task 1: Atlas — Research Delta (pre-market)

**Schedule:** `0 10 * * 1-5` — every weekday at 10:00 UTC (6:00 AM EDT / 5:00 AM EST)

**Task instructions:**

```
Workspace root = this repository (digiquant-atlas).

1. Read cowork/PROJECT.md in full.
2. Read and execute cowork/tasks/research-daily-delta.md in full (verbatim steps).
3. For anything not specified there, follow RUNBOOK.md and AGENTS.md at repo root.
```

**Sunday variant** (swap task file for weekly baseline):
- Schedule: `0 10 * * 0`
- Replace step 2 with: `Read and execute cowork/tasks/research-weekly-baseline.md in full (verbatim steps).`

**Month-end variant** (last US equity session of each calendar month):
- Same schedule, replace step 2 with: `Read and execute cowork/tasks/research-monthly-synthesis.md in full (verbatim steps).`

---

## Paste into Cowork — Task 2: Atlas — Positioning / PM Rebalance (pre-market)

**Schedule:** `0 12 * * 1-5` — every weekday at 12:00 UTC (8:00 AM EDT / 7:00 AM EST)

**Precondition:** Task 1 must have published `documents.digest` for today before this task runs. The 2-hour stagger provides that buffer. If the research task failed, this task's precondition check will catch it early — stop and re-run research first.

**Task instructions:**

```
Workspace root = this repository (digiquant-atlas).

1. Read cowork/PROJECT.md in full.
2. Read and execute cowork/tasks/portfolio-pm-rebalance.md in full (verbatim steps).
3. For anything not specified there, follow RUNBOOK.md and AGENTS.md at repo root.
```

---

## Setup checklist

- [ ] Project instructions pasted from the block above (or from `cowork/PROJECT-PROMPT.md`)
- [ ] Task 1 created with cron `0 10 * * 1-5` and repo root = this project
- [ ] Task 2 created with cron `0 12 * * 1-5` and repo root = this project
- [ ] `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` available to the agent session that runs tasks
- [ ] Optional: Sunday task (or manual swap) for `research-weekly-baseline.md`
- [ ] Optional: month-end task (or manual swap) for `research-monthly-synthesis.md`
- [ ] Commit `config/schedule.json` + `cowork/OPERATOR-COWORK.md`

---

## config/schedule.json — cowork_operator snapshot

```json
{
  "configured": true,
  "configured_at": "2026-04-15",
  "timezone": "America/New_York",
  "pattern": "modular_tasks",
  "portfolio_schedule": "separate_task",
  "modular_task_files": [
    "cowork/tasks/research-daily-delta.md",
    "cowork/tasks/portfolio-pm-rebalance.md"
  ],
  "scheduled_tasks": [
    {
      "name": "Atlas — Research Delta (pre-market)",
      "cron_utc": "0 10 * * 1-5",
      "local_time": "6:00 AM ET weekdays"
    },
    {
      "name": "Atlas — Positioning / PM Rebalance (pre-market)",
      "cron_utc": "0 12 * * 1-5",
      "local_time": "8:00 AM ET weekdays"
    }
  ]
}
```
