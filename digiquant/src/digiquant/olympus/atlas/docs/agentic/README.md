# docs/agentic/ — Agentic development documentation

Central reference for running the digiquant-atlas pipeline on any AI platform.

**How production runs are driven:** scheduled **Claude Cowork** jobs should attach one task file from [`cowork/tasks/README.md`](../cowork/tasks/README.md) (research → portfolio → postmortem/GitHub). That is the primary operational loop; the docs below describe behavior those tasks invoke.

## Canonical model (read this first)

- **Supabase + JSON** are the source of truth; markdown in the app is **derived**.
- **Operator steps:** [`RUNBOOK.md`](../../RUNBOOK.md) — env, publish, validation, GitHub vs Co-work, Track A/B.
- **One CLI entrypoint:** `python3 scripts/run_db_first.py` (after segment JSON is published to Supabase). No local agent-cache required — see [`data/README.md`](../../data/README.md).

## What is digiquant-atlas?

A **9-phase** AI research pipeline (alternative data → institutional → macro → asset classes → equities/sectors → earnings → digest → portfolio layer) with a **three-tier cadence**: Sunday baseline, Mon–Sat deltas, month-end synthesis. Phases emit **structured JSON** (and optional segment markdown during transition); the digest is **`snapshot.json` / `delta-request.json`** materialized into `daily_snapshots` and `documents` in Supabase.

## Quick start (DB-first)

**Detect mode and commands:**

```bash
python3 scripts/run_db_first.py
```

**Track A — generic research only (no portfolio preferences):**

- Skill: [`skills/research-daily/SKILL.md`](../../skills/research-daily/SKILL.md)
- Prompt: [`scripts/cowork-research-prompt.txt`](../../scripts/cowork-research-prompt.txt)
- After publish: `python3 scripts/run_db_first.py --skip-execute --validate-mode research`

**Track B — portfolio / analyst (uses preferences + investment profile):**

- Prompt: [`scripts/cowork-daily-prompt.txt`](../../scripts/cowork-daily-prompt.txt)
- Cowork: [`cowork/README.md`](../../cowork/README.md), [`cowork/tasks/README.md`](../../cowork/tasks/README.md)
- Validate: `--validate-mode pm` or `full`

**Full pipeline (combined):** [`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md) or [`skills/weekly-baseline/SKILL.md`](../../skills/weekly-baseline/SKILL.md) / [`skills/daily-delta/SKILL.md`](../../skills/daily-delta/SKILL.md) per day type.

**Single segment:** read `skills/{segment}/SKILL.md`, write **JSON** where the skill specifies, publish to Supabase per [`RUNBOOK.md`](../../RUNBOOK.md).

## Platform setup

| Platform | Config file | Notes |
|----------|-------------|-------|
| Claude Code | `CLAUDE.md` | Repo root |
| Claude.ai Projects | `cowork/PROJECT-PROMPT.md` | Paste into project instructions; root `CLAUDE_PROJECT_INSTRUCTIONS.md` is pointers only |
| GitHub Copilot | `.github/copilot-instructions.md` | `applyTo: "**"` frontmatter |
| Cursor | `.cursor/rules/` or `.cursorrules` | Rules |
| Windsurf | `.windsurfrules` | Auto-read |
| OpenHands / Devin | [`AGENTS.md`](../../AGENTS.md) | Cross-platform |

See [`PLATFORMS.md`](PLATFORMS.md) for details.

## Documentation index

| File | Contents |
|------|----------|
| `README.md` | This file |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System design and data flow (**canonical**; [`../ARCHITECTURE-REVIEW.md`](../ARCHITECTURE-REVIEW.md) redirects here) |
| [`WORKFLOWS.md`](WORKFLOWS.md) | Step workflows (includes GitHub Actions) |
| [`PLATFORMS.md`](PLATFORMS.md) | IDE / platform setup |
| [`AGENTS.md`](AGENTS.md) | Stub → root [`AGENTS.md`](../../AGENTS.md) |
| [`MEMORY-SYSTEM.md`](MEMORY-SYSTEM.md) | Legacy memory format spec (superseded by Supabase) |
| [`SKILLS-CATALOG.md`](SKILLS-CATALOG.md) | Skill package index (filesystem is authoritative) |
| [`PROMPTS.md`](PROMPTS.md) | Copy-paste patterns (legacy `.md` paths noted where applicable) |
| [`COMPILED-RESEARCH-VIEW.md`](COMPILED-RESEARCH-VIEW.md) | On-read baseline + delta fold |

## Agent definitions

Named roles live in `agents/` (see table in root [`AGENTS.md`](../../AGENTS.md)).

## Key rules

1. Publish to **Supabase** (`daily_snapshots`, `documents`) — not to local memory files.
2. Prefer **JSON artifacts** and Supabase publish over hand-editing derived markdown.
3. Read `config/watchlist.md` every session; read `config/preferences.md` and `config/investment-profile.md` only for **Track B**, not Track A.
4. Use `{DATE}` / `YYYY-MM-DD` in paths, not hardcoded dates.
5. macOS: `sed -i ""` not `sed -i`.
