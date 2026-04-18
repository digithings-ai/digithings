# Task: Recurring scheduled run (router)

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

Use this as the **single** Cowork task when you schedule one job on an **8h / 12h / 24h** (or similar) cadence. It **branches** by calendar context, then runs the **modular** task files below so you do not maintain separate Cowork schedules per mode.

**Run date:** default **today** (repo local date) unless the session specifies `--date YYYY-MM-DD` / `RUN_DATE` — use one consistent `RUN_DATE` for all sections below.

---

## 1) Research (execute applicable blocks **in order**)

Each block must finish with **research close-out**: a published **`digest`** (+ `daily_snapshots` for `RUN_DATE`) as the **single overview** of all sub-segments. That is the **last step of Track A**, not part of the portfolio task.

### 1a — Month-end (optional but recommended on last trading day or first session after month close)

If this session is your **month-end** run for the **month that just ended** (define your rule: e.g. last US equity session of the calendar month):

- Execute **every step** in [`research-monthly-synthesis.md`](research-monthly-synthesis.md) for that month (replace `YYYY-MM` in that file).

### 1b — Weekly vs daily Track A research

- If `RUN_DATE` is **Sunday** (or you are explicitly doing the weekly research anchor): execute **every step** in [`research-weekly-baseline.md`](research-weekly-baseline.md) for `RUN_DATE`.
- **Else:** execute **every step** in [`research-daily-delta.md`](research-daily-delta.md) for `RUN_DATE`.

**Month-end + weekday example:** do **1a** then **1b** (monthly rollup + same-day delta research).  
**Month-end + Sunday:** do **1a** then **1b** (monthly for prior month + Sunday baseline research for `RUN_DATE`).

### 1c — Post-mortem (research) + GitHub backlog (optional)

After section **1b** (and **1a** if run) has published **`digest`** for `RUN_DATE`:

- Execute every step in [`post-mortem-research-github.md`](post-mortem-research-github.md) for `RUN_DATE`.

---

## 2) Portfolio (Track B)

After section **1** has published **`digest`** for `RUN_DATE` (and related research artifacts):

- Optional gate: `python3 scripts/validate_pipeline_step.py --date RUN_DATE --step track_b_precheck`
- Execute **every step** in [`portfolio-pm-rebalance.md`](portfolio-pm-rebalance.md) for `RUN_DATE`.

### 2b — Post-mortem (portfolio) + GitHub backlog (optional)

After section **2** Track B steps are complete for `RUN_DATE`:

- Execute every step in [`post-mortem-portfolio-github.md`](post-mortem-portfolio-github.md) for `RUN_DATE`.

---

## 3) Optional

- `./scripts/status.sh`
- `python3 scripts/backfill_execution_prices.py --date RUN_DATE` if needed ([`RUNBOOK.md`](../../RUNBOOK.md)).

---

### Alternative: separate Cowork tasks (lower ambiguity, same total work)

If you prefer **not** to branch inside one job (clearer ops, slightly more scheduler setup), create **separate** scheduled tasks that each point at **one** file only: `research-weekly-baseline.md`, `research-daily-delta.md`, `research-monthly-synthesis.md`, `research-document-deltas.md` (optional Track B manifest folds), and `portfolio-pm-rebalance.md`. Skip this router file.
