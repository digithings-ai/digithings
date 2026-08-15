# digiquant-atlas — Agent Instructions

> Universal entry point for AI agents (OpenHands, Devin, Cline, GitHub Copilot, Cursor).

---

## What This Repo Is

Daily market intelligence + portfolio loop. **Supabase-first** (no `data/agent-cache/daily` markdown tree).

**One daily cadence** ([#930](https://github.com/digithings-ai/digithings/issues/930)): Atlas A0–A4 (research with
edit-mode continuity) → Hermes H1–H9 (thesis-first) → `commit_run`. Cost is controlled by
`OLYMPUS_MODEL_TIER` and per-artifact `skip`/`edit`/`full` — not separate baseline/delta graphs.

---

## Quickstart for Agents

### Step 1: Run mode
- **Daily (default):** `python -m digiquant.olympus.hermes.chain --cadence daily`
- **Operator full refresh:** `--refresh-scope all` (Sunday cron sets this automatically)
- **Beliefs only:** `--refresh-scope beliefs`
- **Deprecated shim:** `--run-type baseline|delta` (warns; use `--cadence daily` + `--refresh-scope`)
- Prior context loads from **Supabase** `daily_snapshots` / `documents` via preflight

### Publish path (canonical)
```
JSON → validate → publish_document / in-graph publish_phase
Operator close-out: python3 scripts/run_db_first.py
```

### Key scripts
```bash
./scripts/new-day.sh              # Same as run_db_first.py (no folder scaffold)
python3 scripts/run_db_first.py   # Metrics refresh + execute_at_open + validate_db_first
./scripts/git-commit.sh           # Commit config/docs (not gitignored `data/` — see data/README.md)
./scripts/weekly-rollup.sh        # Prints weekly JSON → Supabase prompt (optional; no monthly cron)
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
- **Edit-mode:** triage maps `carry`→`skip`, `regenerate`→`edit`; segments/digest use `DocumentPatch` when prior exists
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
| Pipeline Evolution | `agents/pipeline-evolution.agent.md` | Fix backlog issues from `pipeline_review` → GitHub Issues → PR |

---

## Full Documentation

- Architecture: `docs/agentic/ARCHITECTURE.md`
- Platform setup: `docs/agentic/PLATFORMS.md`
- Skills catalog: `docs/agentic/SKILLS-CATALOG.md`
- Workflows: `docs/agentic/WORKFLOWS.md`
- Development conventions: `CLAUDE.md`
