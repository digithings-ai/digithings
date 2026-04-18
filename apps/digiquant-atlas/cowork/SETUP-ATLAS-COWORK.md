# Atlas + Claude Cowork — interactive setup (agent playbook)

**When to use this file:** The user asks to **set up**, **configure**, **schedule**, or **bootstrap** digiquant-atlas in **Claude Cowork** (project + tasks). Treat this as a **wizard**: interview → persist choices → emit **paste-ready** instructions.

**Prerequisites:** Workspace root = this repository. User has (or will add) Cowork access to this repo and can paste text into Cowork **project** and **task** settings.

---

## 1) Confirm basics

1. Repository path is the **digiquant-atlas** root (where `RUNBOOK.md` and `cowork/` live).
2. **Supabase:** For publishes, the Cowork runtime needs `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (or equivalent env injection). If missing, say what to add and continue with file-based instructions.

---

## 2) Interview the operator (ask until you can fill §4)

Ask in clear, plain language. Use **defaults** only if the user says “defaults are fine.”

| Topic | What to learn | Notes |
|--------|----------------|--------|
| **Cadence** | How often should the **main** job run? (e.g. every **8h**, **12h**, **24h**, or custom) | Maps to Cowork recurrence / cron. |
| **Timezone** | IANA timezone (e.g. `America/New_York`) for human-readable schedule labels | Cowork may still use UTC; document both if needed. |
| **Task pattern** | **(A)** One job → [`tasks/recurring-scheduled-run.md`](tasks/recurring-scheduled-run.md) (router: month-end / Sunday vs weekday, then portfolio), or **(B)** **Separate** Cowork tasks for research weekly / daily / monthly / portfolio | (B) = clearer ops, more scheduler slots. |
| **Month-end** | When is “month-end” for [`tasks/research-monthly-synthesis.md`](tasks/research-monthly-synthesis.md)? (e.g. last **US equity** session of calendar month, or first session of new month) | Router uses this in natural language; optionally add a dedicated monthly-only task. |
| **Portfolio** | Should **every** recurring run include **Track B** after research (router default), or a **separate** portfolio-only schedule (e.g. once daily pre-market)? | Affects how many tasks you define. |
| **Optional extras** | Pre-market-only vs 24h clock, skip weekends, second “post-close” job | Document in `cowork_operator` notes. |

---

## 3) Write in-repo configuration

1. **Update** [`config/schedule.json`](../config/schedule.json):
   - Set `research_cadence.interval_hours` to the chosen value when it is 8, 12, or 24 (or leave as-is if custom).
   - Set or merge the **`cowork_operator`** object (see shape below). Create it if absent.

2. **Create or overwrite** [`OPERATOR-COWORK.md`](OPERATOR-COWORK.md) in this folder (same directory as this file):
   - Short summary of choices (cadence, timezone, pattern A/B, month-end rule, portfolio rule).
   - **Exact copy-paste blocks** from §4 (so the user can reopen the file anytime).
   - Date line: `Last configured: YYYY-MM-DD` (session date).

**`cowork_operator` shape (in `config/schedule.json`):**

```json
"cowork_operator": {
  "configured": true,
  "configured_at": "YYYY-MM-DD",
  "timezone": "IANA/Zone",
  "cadence_summary": "e.g. every 8 hours UTC",
  "pattern": "recurring_router | modular_tasks",
  "month_end_policy": "free text",
  "portfolio_schedule": "with_each_recurring_run | separate_task",
  "primary_task_file": "cowork/tasks/recurring-scheduled-run.md or null",
  "modular_task_files": ["optional", "list"],
  "notes": "optional operator notes"
}
```

---

## 4) Emit Cowork UI instructions (must give copy-paste text)

Deliver this to the user in the chat (and duplicate into `OPERATOR-COWORK.md`).

### 4a — Project instructions

Tell the user: open Cowork **Project** → **Instructions** (or system prompt), paste the **entire** contents of [`PROJECT-PROMPT.md`](PROJECT-PROMPT.md) (the block between the `---` lines, or the whole file if their UI expects one field).

### 4b — Scheduled task(s)

For **each** Cowork scheduled task, output:

1. **Suggested task name** (e.g. `Atlas — 8h router` or `Atlas — research delta only`).
2. **Schedule:** Plain language + if applicable a **cron** expression (e.g. `0 */8 * * *` for every 8 hours at minute 0 UTC — **warn** if their timezone differs).
3. **Task instructions body** — use this **template**; replace `TASK_FILE` with the chosen path under `cowork/tasks/`.

```text
Workspace root = this repository (digiquant-atlas).

1. Read cowork/PROJECT.md in full.
2. Read and execute cowork/tasks/TASK_FILE in full (verbatim steps).
3. For anything not specified there, follow RUNBOOK.md and AGENTS.md at repo root.
```

**Pattern A (single router):** `TASK_FILE` = `recurring-scheduled-run.md`.

**Pattern B (modular examples):**

| Job | Typical `TASK_FILE` |
|-----|---------------------|
| Frequent research + portfolio | `recurring-scheduled-run.md` *or* chain two tasks: first `research-daily-delta.md`, second `portfolio-pm-rebalance.md` with delay |
| Sunday only | `research-weekly-baseline.md` (+ optional second task `portfolio-pm-rebalance.md`) |
| Month-end only | `research-monthly-synthesis.md` |
| Portfolio once daily | `portfolio-pm-rebalance.md` |

If the user chose **separate** tasks, generate **one block per task** with distinct names and schedules.

### 4c — Checklist for the user

- [ ] Project instructions pasted from `PROJECT-PROMPT.md`
- [ ] Each scheduled task has repo root set to this project
- [ ] Each task body uses the template in §4b with the correct `TASK_FILE`
- [ ] Env vars for Supabase available to the agent/session that runs tasks
- [ ] Optional: commit `config/schedule.json` + `cowork/OPERATOR-COWORK.md`

---

## 5) After setup

- Point the user to [`tasks/README.md`](tasks/README.md) for task file meanings.
- If they change cadence later, re-run this wizard (update `cowork_operator` + `OPERATOR-COWORK.md` + Cowork UI).

---

## Trigger phrase (for PROJECT-PROMPT)

Users may say: **“Set up Atlas in Cowork”** or **“Configure Cowork tasks for digiquant-atlas.”** The agent must open **this file** and execute §1–§4.
