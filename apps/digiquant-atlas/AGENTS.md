# digiquant-atlas — Agent Instructions

> Universal entry point for AI agents (OpenHands, Devin, Cline, GitHub Copilot, Cursor).

---

## What This Repo Is

Daily market intelligence system. Three-tier cadence (**Supabase-first**, no `data/agent-cache/daily` markdown tree):
- **Weekly Baseline** (Sunday) — Full digest snapshot JSON → `materialize_snapshot.py`
- **Daily Delta** (Mon–Sat) — Delta-request JSON → materialize (~70% token savings vs full rewrite)
- **Monthly Synthesis** (month end) — `monthly_digest` JSON → `documents`

---

## Quickstart for Agents

### Step 1: Run mode (no `_meta.json`)
- **Sunday** (or explicit baseline) → `skills/weekly-baseline/SKILL.md`
- **Mon–Sat** → `skills/daily-delta/SKILL.md` (load baseline + prior deltas from **Supabase** `daily_snapshots` / `documents`)
- Hint: `python3 scripts/run_db_first.py --dry-run`

### Publish path (canonical)
```
JSON → validate_artifact.py (- or path)
     → publish_document.py --payload -   OR   materialize_snapshot.py --date … --snapshot-json …
Operator close-out: python3 scripts/run_db_first.py
```

### Key scripts
```bash
./scripts/new-day.sh              # Same as run_db_first.py (no folder scaffold)
python3 scripts/run_db_first.py   # Metrics refresh + execute_at_open + validate_db_first
./scripts/git-commit.sh           # Commit config/docs (not gitignored `data/` — see data/README.md)
./scripts/weekly-rollup.sh        # Prints weekly JSON → Supabase prompt
./scripts/monthly-rollup.sh      # Prints monthly JSON → Supabase prompt
python3 scripts/fetch_research_library.py          # List research library index from Supabase
python3 scripts/fetch_research_library.py --ticker NVDA  # Filter by ticker
python3 scripts/publish_research.py --key research/deep-dives/NVDA-DATE --title "..." --type deep-dive --content -
```

---

## Core Rules

- **Search the web** for prices/yields/news — never use training data cutoff values
- **Web fetch**: when following a URL to read an article, news page, speech, or filing — use `defuddle parse <url> --md` instead of WebFetch to strip clutter and save tokens. Not for API endpoints, `.json`, or `.md` files.
- **Read `config/watchlist.md` + `config/investment-profile.md`** at session start
- **Canonical digest** lives in Supabase (`daily_snapshots.snapshot`, `documents`); do not rely on local `DIGEST.md`
- **State a bias** (Bullish/Bearish/Neutral/Conflicted) with rationale for every segment
- Run **Phase 1 (alt-data) BEFORE Phase 3 (macro)** — positioning informs regime read
- Daily δ: always write mandatory deltas: macro, us-equities, crypto
- Analysis and bias are fine; specific buy/sell investment advice is not
- **Token mode**: caveman ON for all process work (announcements, triage, checkpoints, reasoning). Say `normal mode` before authoring any content that publishes to Supabase (narratives, JSON rationale, recommendations). Say `caveman mode` after publishing. Quick test: text going into a DB field → full tokens; text staying in conversation → caveman.

---

## Named Agents

| Agent | File | Purpose |
|-------|------|---------|
| Orchestrator | `agents/orchestrator.agent.md` | Full pipeline driver |
| Sector Analyst | `agents/sector-analyst.agent.md` | Sector deep-dives |
| Alt Data Analyst | `agents/alt-data-analyst.agent.md` | Phase 1 alt-data |
| Institutional Analyst | `agents/institutional-analyst.agent.md` | Phase 2 smart money |
| Research Assistant | `agents/research-assistant.agent.md` | Ad-hoc research |
| Thesis Tracker | `agents/thesis-tracker.agent.md` | Portfolio thesis mgmt |
| Pipeline Evolution | `agents/pipeline-evolution.agent.md` | Fix backlog issues from `pipeline_review` → GitHub Issues → PR |

---

## Scheduled price + macro pipeline

Atlas's price_history / price_technicals / macro_series_observations tables are refreshed by the repo-level workflow [`.github/workflows/digiquant-prices.yml`](../../.github/workflows/digiquant-prices.yml) (owned by the `digiquant` component — not Atlas-specific code). Two separate jobs:

| Job | Schedule | What it does |
|---|---|---|
| **intraday** | `*/15 13-20 * * MON-FRI` (every 15 min during US cash session, 13:00–20:00 UTC) | `digiquant prices fetch-quotes` → `price_history`; `digiquant prices compute-technicals` → `price_technicals` |
| **eod-macro** | `0 21 * * MON-FRI` (weekdays at 21:00 UTC; FRED is day-delayed) | `digiquant prices fetch-macro` (FRED + Frankfurter FX + Crypto FNG) → `macro_series_observations` |

**Manual trigger:** `gh workflow run digiquant-prices -f mode=intraday` (or `-f mode=eod-macro`). Both jobs gate on the `mode` input so only the selected one runs.

**Output destination:** Supabase only. The workflow never writes back to the repo, never uploads artifacts, and never persists local files between runs — the runner's `data/price-history/` is scratch space internal to a single job. Every consumer (the Atlas frontend, downstream phase skills, other agents) reads from Supabase.

**Failure handling:** on step failure a dedicated `actions/github-script` step opens a new issue labeled `ci-failure`, `component:digiquant`, `pipeline:prices` (or `pipeline:macro`), with a link to the failed run.

### Required repository secrets

Configure at `Settings → Secrets and variables → Actions` (repo scope, not environment scope, unless the workflow is updated to reference a named environment):

| Secret | Used by | Purpose |
|---|---|---|
| `SUPABASE_URL` | both jobs | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | both jobs | Service-role key (bypasses RLS for writes) |
| `FRED_API_KEY` | eod-macro | Free registration at fred.stlouisfed.org; used by the FRED branch of `fetch-macro`. Rate-limit identifier only — no private data access. |

Yahoo Finance and Frankfurter FX are unauthenticated — no secret needed. Crypto Fear & Greed (`api.alternative.me/fng/`) is also unauthenticated.

### Cron-firing prerequisite

GitHub only fires `schedule:` triggers from the workflow file on the repository's **default branch** (`main`). A workflow change on a feature branch will not run on cron until merged all the way through `task/… → module/digiquant → develop → main`. `workflow_dispatch` works from any branch that has the file — use it to smoke-test ahead of merge.

---

## Full Documentation

- Architecture: `docs/agentic/ARCHITECTURE.md`
- Platform setup: `docs/agentic/PLATFORMS.md`
- Skills catalog: `docs/agentic/SKILLS-CATALOG.md`
- Workflows: `docs/agentic/WORKFLOWS.md`
- Development conventions: `CLAUDE.md`
