# digiquant-atlas — Cowork project briefing

**Read this file at the start of every Cowork session** for this repository. Scheduled tasks add a second step: open the specific file under `cowork/tasks/` that this run is tied to.

**First-time Cowork setup:** Tell the agent to follow [`SETUP-ATLAS-COWORK.md`](SETUP-ATLAS-COWORK.md) (or paste that path). It will ask how often to run jobs, timezone, router vs modular tasks, and will write [`OPERATOR-COWORK.md`](OPERATOR-COWORK.md) plus update `config/schedule.json` → `cowork_operator` with paste-ready instructions for the Cowork UI.

---

## What this codebase is

- **DB-first** market intelligence: agents produce **JSON artifacts** → publish to **Supabase** (`daily_snapshots`, `documents`, `positions`, …). UI markdown is **derived**.
- **Three-tier cadence:** Sunday **baseline** (weekly anchor row + phased **review** of last week: carry-forward, append-first, selective rewrites, week-ahead bias—not necessarily a full rewrite), Mon–Sat **delta**, month-end rollup (see `RUNBOOK.md`, `skills/weekly-baseline/SKILL.md`).
- **Two runnable tracks:**
  - **Track A — Research only:** positioning-blind; produce `research_delta` JSON and publish with **`validate_artifact.py -`** + **`publish_document.py --payload -`** (stdin). Unique `document_key` under `research-delta/…` (see `skills/research-daily/SKILL.md`). No `preferences` / `investment-profile` / `portfolio.json`. The repo **does not commit** `data/agent-cache/`; Supabase is canonical.
  - **Track B — Portfolio / analyst:** uses preferences + profile; `rebalance-decision.json` and related portfolio JSON.
- **Combined flow:** full digest + PM in one session (see `scripts/cowork-daily-prompt.txt`).

---

## What runs where (do not confuse these)

| Layer | Who | What |
|--------|-----|------|
| **GitHub Actions** | CI | Weekday **price_history** / **price_technicals** / **refresh_performance_metrics** — **not** digest, not agent research |
| **Cowork / you** | Agent | Research JSON, materialize, `update_tearsheet`, optional `execute_at_open`, validation |

Evening job details: `RUNBOOK.md` → Schedules table.

**In Cloud desktop:** if **Supabase MCP** is connected, treat the database as the first-class source for **prices** (`price_history`), **technicals** (`price_technicals`), and **portfolio-facing tables** (e.g. `positions`, `daily_snapshots`, `documents`, `nav_history`, metrics) when you need current or historical state for analysis. Prefer MCP **reads** over inferring from stale local files or training data.

**Writes:** upsert artifacts with **`scripts/publish_document.py`** (use **`--payload -`** with JSON on stdin when no disk path exists). Optional **`scripts/update_tearsheet.py`** for local dashboard mirrors only. A run is done when **`documents`** / related tables are updated — not when files land under `data/agent-cache/`. Avoid hand-written MCP SQL for large JSON payloads. See `cowork/tasks/README.md` → “Supabase-first writes”.

---

## MCP toolkit (Cloud desktop — use judgment)

Your environment may expose more than one MCP server. **Tool definitions list what is actually callable**; this section is orientation only.

| Kind | Suggested use | Required? |
|------|----------------|-----------|
| **Supabase** | Read/query structured app data: OHLCV, technicals, snapshots, documents, positions, events | **Prefer this** for anything already in the DB |
| **Market / macro MCPs** (e.g. FRED, Alpha Vantage, CoinGecko, Frankfurter, SEC, crypto fear & greed, Polymarket, etc.) | Extra series, quotes, filings, alt-data when research needs them | **Optional** — use when they clearly improve accuracy vs a generic web search |
| **Web search** | News, fast-changing context, when no MCP fits | As needed |

Do **not** feel obligated to invoke every connector on every run. Pick tools that match the segment (e.g. macro → FRED; crypto spot → CoinGecko; equities fundamentals → SEC). Phase→tool hints: [`docs/ops/data-sources.md`](../docs/ops/data-sources.md); MCP fallback patterns: [`skills/mcp-data-fetch/SKILL.md`](../skills/mcp-data-fetch/SKILL.md).

---

## Environment (required for publish)

- **Python 3.11+**, repo root as cwd.
- `pip install -r requirements.txt` (includes `jsonschema` for `validate_artifact.py`).
- **Supabase service role** (writes for scripts):
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_KEY`  
  Optional file: `config/supabase.env` (loaded by scripts).

**Note:** Supabase **MCP** (read/query in the agent) complements but does not replace env vars for **Python publishers** (`run_db_first.py`, `update_tearsheet.py`, etc.) unless your setup injects the same credentials.

---

## Commands you will use often

```bash
python3 scripts/run_db_first.py    # after JSON artifacts exist; see flags in RUNBOOK
./scripts/fetch-market-data.sh     # optional local cache before long research
./scripts/status.sh                # quick sanity
```

**Execution / cadence hints:** `config/schedule.json` (e.g. `rebalance_source_for_opens.mode` for `execute_at_open.py`).

---

## Read order (when in doubt)

1. This file (`cowork/PROJECT.md`)
2. The **task** file for this run (`cowork/tasks/…`)
3. [`RUNBOOK.md`](../RUNBOOK.md) — authoritative publish/validate/schedules
4. [`AGENTS.md`](../AGENTS.md) — rules, Track A/B, scripts list
5. The **skill** named in the task (e.g. `skills/research-daily/SKILL.md`, `skills/daily-delta/SKILL.md`, `skills/orchestrator/SKILL.md`)

**Long copy-paste prompts (optional):**

- Track B combined: [`scripts/cowork-daily-prompt.txt`](../scripts/cowork-daily-prompt.txt)
- Track A: [`scripts/cowork-research-prompt.txt`](../scripts/cowork-research-prompt.txt)

---

## Tasks you can schedule

See [`tasks/README.md`](tasks/README.md). Typical patterns:

- **One recurring job (8h/12h/24h):** [`tasks/recurring-scheduled-run.md`](tasks/recurring-scheduled-run.md) — branches month-end / Sunday vs weekday, then portfolio.
- **Separate jobs:** [`tasks/research-daily-delta.md`](tasks/research-daily-delta.md), [`tasks/research-weekly-baseline.md`](tasks/research-weekly-baseline.md), [`tasks/research-monthly-synthesis.md`](tasks/research-monthly-synthesis.md), [`tasks/portfolio-pm-rebalance.md`](tasks/portfolio-pm-rebalance.md).

Each modular task file stays short; the router delegates to them.

---

## Guardrails

- Do **not** treat **`data/agent-cache/`** as product state — it is **gitignored** scratch. Canonical data is in **Supabase**.
- **Track A:** never load `config/preferences.md`, `config/investment-profile.md`, or `config/portfolio.json`.
- If `validate_db_first.py` fails, fix artifacts or Supabase rows, then re-run validation for the date (`RUNBOOK.md`).
- Pre-market runs may record **null** execution prices until opens exist; then `python3 scripts/backfill_execution_prices.py --date YYYY-MM-DD` (`RUNBOOK.md`).

---

## Optional post-run

```bash
./scripts/scaffold_evolution_day.sh
```

Produce evolution JSON (`evolution_sources`, `evolution_quality_log`, `evolution_proposals`), validate with `validate_artifact.py -`, publish each with `publish_document.py --payload -` and the correct `document_key` per `RUNBOOK.md` (optional `update_tearsheet.py` for local mirror).

**Per-track pipeline review + GitHub backlog:** after Track A and/or Track B, follow [`cowork/tasks/post-mortem-research-github.md`](cowork/tasks/post-mortem-research-github.md) and [`cowork/tasks/post-mortem-portfolio-github.md`](cowork/tasks/post-mortem-portfolio-github.md). Publish `doc_type: pipeline_review` to keys `pipeline-review/research/{DATE}.json` and `pipeline-review/portfolio/{DATE}.json`, then run `scripts/pipeline_review_to_github.py` with authenticated [`gh`](https://cli.github.com/). Labels: [`docs/ops/GITHUB_PIPELINE_LABELS.md`](docs/ops/GITHUB_PIPELINE_LABELS.md). Roadmap: [`docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md`](docs/agentic/EVOLUTION_GITHUB_IMPLEMENTATION_PLAN.md).
