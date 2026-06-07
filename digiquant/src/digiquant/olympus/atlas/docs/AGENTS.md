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

## Full Documentation

- Architecture: `docs/agentic/ARCHITECTURE.md`
- Platform setup: `docs/agentic/PLATFORMS.md`
- Skills catalog: `docs/agentic/SKILLS-CATALOG.md`
- Workflows: `docs/agentic/WORKFLOWS.md`
- Development conventions: `CLAUDE.md`
