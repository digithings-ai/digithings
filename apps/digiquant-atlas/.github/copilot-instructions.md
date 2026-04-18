---
applyTo: "**"
---

# digiquant-atlas — GitHub Copilot Instructions

Daily market intelligence with a **Supabase-first**, **JSON-first** pipeline. Canonical state lives in Supabase (`daily_snapshots`, `documents`); markdown is derived for display.

## Project Context

- **Languages**: Python automation, Bash helpers, Markdown skill files under `skills/`
- **Operator entrypoint**: `python3 scripts/run_db_first.py` (after publishing JSON to Supabase)
- **Authoritative docs**: [`RUNBOOK.md`](../RUNBOOK.md), [`AGENTS.md`](../AGENTS.md), [`skills/orchestrator/SKILL.md`](../skills/orchestrator/SKILL.md)

## Key Paths

| Path | Role |
|------|------|
| `skills/**/SKILL.md` | Phase instructions (YAML frontmatter: `name`, `description`) |
| `templates/schemas/*.json` | JSON Schema for artifacts |
| `scripts/run_db_first.py` | Post-publish metrics + execute-at-open + `validate_db_first.py` |
| `scripts/validate_db_first.py` | Supabase row checks (`--date`, `--mode full\|research\|pm`) |
| `scripts/publish_research.py` | Publish deep dives / concepts to Supabase research library |
| `scripts/fetch_research_library.py` | List / fetch research notes from Supabase |
| `docs/research/papers/` | Static doctrine papers (Tier 1 research library, git-tracked) |
| `data/agent-cache/` | Optional gitignored scratch — **not** source of truth |

## Web Fetch Protocol

When following any URL to read an article, news page, speech, or filing:
```bash
defuddle parse <url> --md   # strips nav/ads/clutter before the LLM reads
```
Do NOT use defuddle for `.md` files, `.json` endpoints, or Supabase/API URLs.

## Token Mode Protocol

- **Caveman ON** for: phase announcements, triage, checkpoints, inter-phase reasoning
- **Normal mode** for: content publishing to Supabase — narratives, rationale, recommendations
- Toggle: say `normal mode` before authoring DB content, `caveman mode` after publishing

## Research Library

Two tiers — check both before starting a deep dive:
- **Tier 1**: `docs/research/papers/` — 7 static doctrine papers (read-only)
- **Tier 2**: Supabase `documents` with `document_key: research/*`

```bash
python3 scripts/fetch_research_library.py --ticker NVDA   # check prior research
python3 scripts/publish_research.py \
  --key research/deep-dives/NVDA-2026-04-14 \
  --title "NVDA Deep Dive" --type deep-dive --content -    # publish result
```

## Conventions

- Prefer **`validate_artifact.py`** + **`publish_document.py --payload -`** for hosted or CI-style runs.
- macOS `sed`: use `sed -i ""` (BSD sed requires the backup extension).
- Run shell scripts from the **repo root**; use `$(date +%Y-%m-%d)` instead of hard-coded dates.
- Do not reintroduce a markdown-first "daily tree" contract; align edits with `RUNBOOK.md`.

## What Not to Do

- Do not treat `data/agent-cache/` scratch as source of truth — Supabase is canonical.
- Do not hand-edit Supabase rows directly — use `publish_document.py` / `materialize_snapshot.py`.
- Do not remove or break `.github/workflows/` without an explicit operator reason.
- Do not change skill frontmatter `name:` fields without cascading updates to `SKILLS-CATALOG.md`.

## More Documentation

- [`docs/agentic/ARCHITECTURE.md`](../docs/agentic/ARCHITECTURE.md)
- [`docs/agentic/WORKFLOWS.md`](../docs/agentic/WORKFLOWS.md)
- [`docs/agentic/SKILLS-CATALOG.md`](../docs/agentic/SKILLS-CATALOG.md)
