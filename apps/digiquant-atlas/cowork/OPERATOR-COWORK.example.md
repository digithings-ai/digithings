# Cowork operator setup — example output

This file shows what the setup agent **creates** as [`OPERATOR-COWORK.md`](OPERATOR-COWORK.md) after the interview. Copy the pattern; replace all bracketed values.

---

## Summary

- **Last configured:** YYYY-MM-DD  
- **Timezone:** America/New_York  
- **Cadence:** Every 8 hours (UTC minute 0)  
- **Pattern:** Single router → `cowork/tasks/recurring-scheduled-run.md`  
- **Month-end:** Last US equity session of each calendar month  
- **Portfolio:** After each recurring run (same task via router)

---

## Paste into Cowork — project

*(Full contents of `cowork/PROJECT-PROMPT.md` go here — the agent should paste the live file text when generating the real `OPERATOR-COWORK.md`.)*

---

## Paste into Cowork — scheduled task: Atlas — 8h router

**Schedule:** Every 8 hours at :00 UTC (adjust in Cowork UI for your timezone).

**Task instructions:**

```text
Workspace root = this repository (digiquant-atlas).

1. Read cowork/PROJECT.md in full.
2. Read and execute cowork/tasks/recurring-scheduled-run.md in full (verbatim steps).
3. For anything not specified there, follow RUNBOOK.md and AGENTS.md at repo root.
```

---

## `config/schedule.json` — `cowork_operator` snapshot

*(Optional: agent pastes the JSON object it merged for quick reference.)*
