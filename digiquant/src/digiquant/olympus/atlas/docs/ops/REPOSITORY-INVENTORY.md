# Repository inventory (complete accounting)

**Purpose:** Account for **every intentional path** in **digiquant-atlas** before DigiThings migration — what ships, what is local-only, and what must never be committed.

**Scope:** **Git-tracked** content (source of truth: `git ls-files`). **Gitignored** paths are listed separately with expected role.

**Regenerate counts** (from repo root):

```bash
git ls-files | wc -l
git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn
```

**Snapshot:** **388** tracked files — last verified **2026-04-15** (`git ls-files | wc -l`; `./scripts/smoke-test.sh` 45/45).

---

## 1. Top-level map (tracked)

| Path | Files (approx.) | Role | Ship to DigiThings Wave 1? |
|------|-----------------|------|----------------------------|
| `frontend/` | 107 | Next.js App Router UI, static export to Pages today | **Yes** — core app |
| `scripts/` | 80 | Python + shell operators, DB-first pipeline | **Yes** |
| `skills/` | 51 | Canonical `SKILL.md` per pipeline segment | **Yes** |
| `templates/` | 27 | JSON Schemas + digest/delta templates | **Yes** |
| `supabase/` | 25 | `migrations/*.sql`, `config.toml` | **Yes** — append-only history |
| `docs/` | 19 | Agentic docs, ops, design; `docs/research/LIBRARY.md` | **Yes** (trim ops duplicates if desired) |
| `cowork/` | 19 | Cowork tasks, `PROJECT.md`, operator prompts | **Yes** — spec until Wave 2 |
| `config/` | 14 | Watchlist, portfolio, profiles, **examples only** (secrets gitignored) | **Yes** — no `supabase.env` / `local.env` |
| `.agents/` | 10 | Cursor/plugin skill stubs (Obsidian, defuddle, etc.) | **Optional** — not runtime; dedupe vs `skills/` over time |
| `agents/` | 8 | `*.agent.md` role definitions | **Yes** |
| `.github/` | 6 | `workflows/*.yml`, copilot instructions, issue template | **Yes** — adapt CI in monorepo |
| `.claude/` | 5 | Claude Code skill symlink/copies | **Optional** — convenience |
| `.cursor/` | 3 | Cursor rules + `mcp.json` fragment | **Optional** |
| `tests/` | 2 | `test_etl.py`, `__init__.py` | **Yes** if CI keeps them |
| **Root files** | 11 | See § 3 | **Yes** |

---

## 2. Tracked subtree detail

### `frontend/`

| Subpath | Role |
|---------|------|
| `app/` | Routes: `/`, `/library`, `/portfolio`, `/research`, `/settings`, `/performance`, `/strategy`, `/architecture`, nested portfolio theses |
| `components/` | UI: library document views, portfolio tabs, sidebar, overview, research |
| `lib/` | Supabase queries, types, snapshot/render helpers, dashboard context |
| `public/` | `favicon.svg`, `icons.svg`; **`dashboard-data.json` is gitignored** (generated) |
| Config | `package.json`, `next.config.mjs`, `tsconfig.json`, ESLint, PostCSS, Tailwind |

### `scripts/`

- **Core DB-first:** `run_db_first.py`, `publish_document.py`, `materialize_snapshot.py`, `validate_db_first.py`, `validate_artifact.py`, `refresh_performance_metrics.py`, `execute_at_open.py`, `sync_positions_from_rebalance.py`, …
- **Data / ingest:** `preload-history.py`, `fetch-quotes.py`, `fetch-macro.py`, `fetch-market-data.sh`, `ingest_*.py`, `compute-technicals.py`
- **Ops / repair / backfill:** many `backfill_*.py`, `repair_supabase_portfolio_data.py`, `update_tearsheet.py`, … — see [SCRIPTS.md](SCRIPTS.md), [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md)
- **`scripts/lib/`** | `scratch_paths.py`, `macro_ingest.py`, `watchlist.py`, `treasury_xml.py`
- **`scripts/sql/`** | Ad-hoc audit SQL
- **Prompts:** `cowork-daily-prompt.txt`, `cowork-research-prompt.txt`
- **Rollups:** `weekly-rollup.sh`, `monthly-rollup.sh`, `new-day.sh`, `smoke-test.sh`, …

### `skills/`

One folder per slug; each has **`SKILL.md`** (or `README.md` for orchestrator/portfolio-manager). Full list is the set of directories under `skills/` — **no separate index file required** for inventory; canonical catalog: [SKILLS-CATALOG.md](../agentic/SKILLS-CATALOG.md).

### `templates/`

| Item | Role |
|------|------|
| `digest-snapshot-schema.json`, `delta-request-schema.json`, `delta-request.example.json` | Core digest/delta |
| `snapshot-schema.json`, `research-manifest.json` | Snapshot / research manifest |
| `schemas/*.schema.json` | **All** `doc_type` and segment payloads |

### `supabase/`

| Item | Role |
|------|------|
| `migrations/001` … `023_*.sql` | **Append-only** — never delete applied files |
| `config.toml` | Supabase CLI |
| `.gitignore` | Supabase CLI ignore rules |
| `.branches/`, `.temp/` | **Not tracked** — if CLI creates them locally, keep them out of git (add to `supabase/.gitignore` if needed) |

### `docs/`

| Path | Role |
|------|------|
| `agentic/*` | Architecture, workflows, prompts, platforms, skills catalog, compiled research view, evolution GitHub plan |
| `ops/*` | SCRIPTS, migration roadmaps, Wave 1/2 plans, protected scripts, audits, PRE-MIGRATION, this inventory |
| `DESIGN-DECISIONS.md`, `ARCHITECTURE-REVIEW.md` (stub), `SYSTEM-SCORECARD.md` | Design / redirects |
| `evolution-changelog.md` | Phase 9 / evolution log |
| `research/LIBRARY.md` | Research library doctrine pointer |

### `cowork/`

| Item | Role |
|------|------|
| `PROJECT.md`, `PROJECT-PROMPT.md`, `README.md`, `SETUP-ATLAS-COWORK.md` | Operator briefing |
| `OPERATOR-COWORK.md`, `.example.md` | Local operator copies |
| `tasks/*.md` | Modular scheduled/ad-hoc tasks (see `tasks/README.md`) |

### `config/` (tracked)

**Examples and non-secrets:** `watchlist.md`, `portfolio.json`, `preferences.md`, `investment-profile.md`, `investment-policy.md`, `hedge-funds.md`, `data-sources.md`, `email-research.md`, `macro_series.yaml`, `schedule.json`, `MCP-SETUP.md`, `mcp.claude-desktop.fragment.json`, `mcp.secrets.env.example`, `local.env.example`

**Gitignored (never ship secrets):** `supabase.env`, `local.env`, `mcp.secrets.env`

### `agents/`

`orchestrator`, `research-assistant`, `portfolio-manager`, `thesis-tracker`, `sector-analyst`, `alt-data-analyst`, `institutional-analyst`, `pipeline-evolution`

### `.github/`

| Path | Role |
|------|------|
| `workflows/ci.yml` | CI |
| `workflows/deploy.yml` | GitHub Pages static export |
| `workflows/daily-price-update.yml` | Scheduled market data |
| `workflows/pipeline-meta-review.yml` | Optional meta review |
| `copilot-instructions.md` | Copilot |
| `ISSUE_TEMPLATE/pipeline-improvement.md` | Issues |

### IDE / agent plugin folders

| Path | Role |
|------|------|
| `.agents/skills/*` | Same families as `.claude/skills` — Obsidian, json-canvas, defuddle |
| `.claude/skills/*` | Symlink-style copies for Claude Code |
| `.cursor/rules/*.mdc` | Cursor project rules |
| `.cursor/mcp.json` | MCP config fragment (may duplicate root `.mcp.json` intent) |

---

## 3. Root-level tracked files

| File | Role |
|------|------|
| `README.md` | Project entry |
| `RUNBOOK.md` | Operator authority |
| `AGENTS.md` | Agent behavior |
| `CLAUDE.md` | Claude Code |
| `CLAUDE_PROJECT_INSTRUCTIONS.md` | Claude Project |
| `SETUP_GUIDE.md` | Setup |
| `requirements.txt` | Python deps for scripts |
| `skills-lock.json` | Lock / manifest (if used by tooling) |
| `.gitignore` | Ignore rules |
| `.cursorrules` | Cursor |
| `.windsurfrules` | Windsurf |
| `.mcp.json` | MCP |

---

## 4. Gitignored but expected (do not “clean” into git)

| Pattern | Purpose |
|---------|---------|
| `data/*` (except `data/README.md`) | Local scratch, fetch cache — **Supabase is canonical** |
| `outputs/` | Deprecated path |
| `knowledge/` | Personal Obsidian vault — **not the app** |
| `config/supabase.env`, `config/local.env`, `frontend/.env.local` | Secrets |
| `node_modules/`, `.next/`, `frontend/out/` | Build artifacts |
| `frontend/public/dashboard-data.json` | Generated dashboard JSON |

---

## 5. “Perfect cleanup” checklist (inventory-driven)

Use this after structural changes or before Wave 1 copy:

- [x] `git ls-files` count stable; **no** accidental adds under `data/` (except `data/README.md`), `outputs/`, `knowledge/`, secrets. *(2026-04-15 pass)*
- [x] `supabase/.branches`, `supabase/.temp` — **not tracked** (see `supabase/.gitignore`).
- [x] Local **`data/agent-cache/`** removed (including mistaken `evolution/--help` and empty `_migrated_md` trees); only **`data/README.md`** at repo root under `data/`. *(Safe to `rm -rf data/agent-cache` anytime.)*
- [x] **`.DS_Store`** — none tracked (`git ls-files` grep DS_Store empty).
- [ ] **Duplicate editor skills** (`.agents`, `.claude`) — optional consolidation; not blocking migration.
- [ ] **docs/research/papers/** — if doctrine PDFs are referenced in README but not in repo, either add them to git or fix docs to match (currently only `LIBRARY.md` is tracked under `docs/research/`).

---

## 6. Relation to other ops docs

| Doc | Relationship |
|-----|----------------|
| [PRE-MIGRATION-CLEANUP.md](PRE-MIGRATION-CLEANUP.md) | Policy + phased checklist — **this inventory** is the full map |
| [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md) | Scripts that must not be deleted casually |
| [SKILLS-AUDIT.md](SKILLS-AUDIT.md) | Skill linkage audit |
| [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md) | Where the tree moves next |

---

## 7. What is *not* in this repo (by design)

- **Production secrets** — only `*.example` and docs
- **Full `node_modules`** / **`.next`** — install per `frontend/package.json`
- **DigiThings / digigraph code** — lives in sibling `../digithings`

When this inventory drifts, update § 1 counts and the checklist in § 5.
