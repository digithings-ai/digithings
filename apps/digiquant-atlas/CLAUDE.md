# digiquant-atlas — Claude Code Instructions

> For pipeline/behavioral rules see `AGENTS.md`. For Claude.ai Projects, see `CLAUDE_PROJECT_INSTRUCTIONS.md`.

---

## Quick Commands

```bash
python3 scripts/run_db_first.py              # After publishing JSON to Supabase: optional disk validate → metrics → execute_at_open → validate_db_first
./scripts/new-day.sh                         # Thin wrapper (prints the same agent prompt)
python3 scripts/validate_db_first.py --date YYYY-MM-DD --mode full   # Supabase row checks (`--mode research|pm` also)
./scripts/fetch-market-data.sh               # Local quotes + macro → data/agent-cache/daily/.../data/
./scripts/git-commit.sh                      # Commit config / docs (not data/agent-cache/)
./scripts/weekly-rollup.sh                   # Weekly synthesis prompt (JSON → Supabase)
./scripts/monthly-rollup.sh                  # Monthly synthesis prompt
./scripts/validate-portfolio.sh              # portfolio.json vs investment-profile.md
python3 scripts/update_tearsheet.py          # Recovery: rescan scratch tree + refresh Supabase documents/metrics
python3 scripts/preload-history.py           # OHLCV cache under data/price-history/
python3 scripts/fetch_research_library.py    # List/fetch research notes from Supabase (category=research)
python3 scripts/publish_research.py          # Publish deep dive or concept note to Supabase research library
```

---

## Repository Layout

```
config/      watchlist.md, investment-profile.md, portfolio.json, hedge-funds.md
skills/      Skill files (step-by-step instruction sets for AI pipeline phases)
templates/   Output templates — do not delete
data/agent-cache/   Optional local scratch (gitignored); Supabase is canonical
scripts/     Bash + Python automation
agents/      Named agent role definitions
docs/agentic/ Full architecture, platform, workflow docs
frontend/    Next.js dashboard (app/, components/, lib/)
supabase/    Schema migrations
```

---

## Development Guidelines

### Web fetch (all agents)
When following a URL to read any article, news page, speech transcript, or regulatory filing — use `defuddle parse <url> --md` instead of WebFetch. Strips nav/ads/clutter before the LLM reads, saving input tokens. Not for API endpoints, `.json`, or `.md` files.

### When editing skill files:
1. Read the existing file completely before editing
2. Preserve YAML frontmatter (`name`, `description`)
3. Keep step numbering consistent (`### 1.`, `### 2.`, …)
4. Prefer JSON + Supabase paths per `RUNBOOK.md`; do not reintroduce a markdown-first filesystem contract

### When editing Python:
- Match existing style; type hints where the file already uses them
- Load Supabase credentials from `config/supabase.env` where applicable

---

## Additional References

- `RUNBOOK.md` — operator truth for publish and validation
- `docs/agentic/ARCHITECTURE.md` — system design
- `AGENTS.md` — cross-IDE agent behavior
