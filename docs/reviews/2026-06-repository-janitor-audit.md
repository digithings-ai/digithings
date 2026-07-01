# DigiThings Repository Janitor Audit — June 2026

**Date:** 2026-06-05  
**Scope:** Read-only inventory of top-level and component folders, git hygiene, stale references, generated artifacts.  
**Method:** `ls`, `git ls-files`, `git log`, `git check-ignore`, `grep`, `scripts/find_stale.py` (398 candidates @ ≥60% confidence), cross-read with [`2026-06-full-audit.md`](./2026-06-full-audit.md).  
**Related plan:** [`2026-06-full-audit-implementation-plan.md`](./2026-06-full-audit-implementation-plan.md) — **Wave 6** (this audit) · **Wave 7** (pending [`2026-06-simplify-deslop-audit.md`](./2026-06-simplify-deslop-audit.md))

---

## Executive summary

| Metric | Value |
|--------|------:|
| **JAN proposals** | **32** (`JAN-001` … `JAN-032`) |
| Core service trees | **Keep** — all six Python components + `frontend/*` active |
| Local-only artifacts (OK) | `dist/`, `digiquant/data/*.csv`, root `data/price-history/`, `node_modules/` |
| Committed artifacts to remove | `frontend/olympus/public/dashboard-data.json` (~284 KB), `digiquant/tearsheet.html` (~1.3 MB) |
| Stale references | `apps/digiquant-atlas/`, `frontend/atlas/` in lockfile + docs; `website/` in DEPLOYMENT |
| Recommended delivery | **Wave 6 housekeeping PR** (separate from security mega-PR); overlap **REM-037** / **REM-038** for Olympus |

---

## 1. Top-level map

| Path | Purpose | Used by | Keep / remove / gitignore | Confidence |
|------|---------|---------|---------------------------|------------|
| `digigraph/` | LangGraph orchestration API, MCP, workflows | Docker Compose `:8000`, `make test`, CI `digigraph-test.yml` | **Keep** | High |
| `digiquant/` | Nautilus backtest/optimize, Atlas + Hermes subgraphs | Compose `:8001`, CLI, cron workflows (`atlas-*`) | **Keep** | High |
| `digisearch/` | RAG ingest/search | Compose `:8002`, seeds, CI | **Keep** | High |
| `digismith/` | Tracing + `/v1/status` | Compose `:8003` | **Keep** | High |
| `digikey/` | JWT/API keys | Compose `:8005`, all services | **Keep** | High |
| `digibase/` | Shared HTTP/audit/OTel | Imported by all Python services | **Keep** | High |
| `digiclaw/` | Heartbeat + audit MCP | `make up-heartbeat`, CI | **Keep** | High |
| `frontend/` | Web umbrella: design, landings, DigiChat, Olympus | npm workspaces, Cloudflare/build scripts | **Keep** | High |
| `tests/` | Cross-component pytest suites | `make test`, CI | **Keep** | High |
| `scripts/` | Agent kit, stack runners, build/deploy assembly | Makefile, hooks, GHA | **Keep** (trim stale — see JAN) | High |
| `docs/` | ADRs, agents, scoring, plans, reviews | `make doc-check`, humans/agents | **Keep** | High |
| `config/` | LiteLLM, shared stack config | Compose, services | **Keep** | High |
| `agents/` + `agents.yml` | Generated agent surface source | `make agents-init`, CI drift check | **Keep** | High |
| `.github/workflows/` | CI, Atlas cron, agent dispatch | GHA | **Keep** (fix missing workflow refs — JAN) | High |
| `.claude/` | Claude Code config (generated + hooks) | Claude sessions | **Keep**; `.claude/worktrees/` already ignored | High |
| `.cursor/` | Cursor rules (generated) | Cursor | **Keep** | High |
| `dist/` | **Local** Pages assembly output (`build-digithings.sh`, `build-digiquant.sh`) | Deploy scripts only; **not in git** | **Gitignore** (already); delete local copies freely | High |
| `node_modules/` | Root npm workspace install | `npm install` at repo root for Olympus/design | **Gitignore** (already); do not commit | High |
| `digiquant/data/` | OHLCV samples for backtests/Docker | Compose mount, `run_stack_local.sh`, tests/docs | **Keep README in git**; CSVs **gitignored** (correct) | High |
| `data/` (repo root) | Atlas **price-history** CSV cache + agent-cache paths in scripts | `history_cache`, frozen `scripts/atlas/compute-technicals.py` | **Gitignore** entire tree; document as runtime cache | Medium |
| `projects/` | Confidential per-project Docker stacks (SITAAS, twelve_x, local) | Operators; **entire tree gitignored** | **Keep locally**; never commit contents; optional allowlist `projects/README.md` (JAN-014) | High |
| `docs/projects/` | Public dogfood project specs | DigiGraph indexing, guides | **Keep** | High |
| `docs/superpowers/` | Ad-hoc agent specs/plans | Human/agent planning only | **Keep**; commit untracked June 2026 files or move to issues | Medium |
| `package.json` + `package-lock.json` | npm workspaces `frontend/*` | CI, local frontend builds | **Keep** lockfiles; **regenerate** to drop stale `apps/digiquant-atlas` entries (JAN-003) | High |
| `conftest.py` | Root pytest hooks | `pytest` from repo root | **Keep** | High |
| `htmlcov/`, `.coverage*` | Coverage HTML/XML | `make test-cov-html` | **Gitignore** (already) | High |
| `.venv/`, `.venv-ci/` | Local Python envs | dev | **Gitignore** (already) | High |
| `.remember/` | Local agent memory (archive/logs) | Cursor/agent tooling | **Not tracked**; add **gitignore** (JAN-005) | Medium |
| `__pycache__/` (root) | Accidental bytecode | none | **Gitignore** via `*.pyc` / delete locally | High |
| `.local_digikey.sqlite`, `.env` | Local dev secrets/state | `run_stack_local.sh` | **Gitignore** (`.env` yes); consider `*.sqlite` at root (JAN-006) | Medium |
| `apps/` | Legacy Atlas app tree | **Removed** (ADR-0014); only doc/lockfile ghosts | **Do not restore**; clean references | High |

**No `apps/` directory** exists today. Atlas lives under `digiquant/src/digiquant/olympus/atlas/`; UI at `frontend/olympus/`.

---

## 2. Per-component deep dives

### 2.1 `digiquant/data/`

| Item | Detail |
|------|--------|
| **Purpose** | Demo/backtest OHLCV: synthetic `*.csv`, optional `*_real.csv` from Yahoo |
| **Git** | Only `digiquant/data/README.md` is tracked. All `*.csv` ignored via `.gitignore` |
| **On disk** | `AAPL.csv`, `AAPL_real.csv`, `BTC-USD.csv`, etc. — local/dev only |
| **`AAPL_real.csv`** | Created by `digiquant/scripts/fetch_real_ohlcv.py`; **never committed** |
| **Consumers** | `docker-compose.yml` `./digiquant/data:/app/data:ro`; stack-local scripts auto-synthesize if empty |
| **Verdict** | **Keep folder + README**; CSVs correctly out of git (JAN-018 doc clarify) |

### 2.2 Root `data/` (not `digiquant/data/`)

| Item | Detail |
|------|--------|
| **Purpose** | `data/price-history/` — Atlas price pipeline CSV cache |
| **Git** | **0 tracked files** under `data/` |
| **Code** | `digiquant/src/digiquant/data/prices/history_cache.py` → `DEFAULT_CACHE_DIR = Path("data/price-history")` |
| **Verdict** | **Gitignore** `data/` at repo root (JAN-004); treat as runtime cache like `digiquant/results/` |

### 2.3 `dist/`

| Item | Detail |
|------|--------|
| **Purpose** | Assembled static site bundle: digiquant.io root + `design/` + `olympus/` |
| **Producers** | `scripts/build-digiquant.sh`, `scripts/build-digithings.sh` |
| **Git** | Ignored (`dist/`) |
| **Verdict** | **Do not commit**; safe to delete locally; CI/Cloudflare should build fresh |

### 2.4 `frontend/*`

| Package | Type | Deploy / use | Keep? |
|---------|------|--------------|-------|
| `frontend/design/` | npm workspace `@digithings/design` | Imported by digichat, olympus, static sites | **Keep** |
| `frontend/digithings/` | Static HTML | Cloudflare / `build-digithings.sh` | **Keep** |
| `frontend/digiquant/` | Static HTML + `atlas.html` | `build-digiquant.sh`; ADR-0012 publish repo | **Keep** |
| `frontend/digichat/` | Next.js 16 BFF + chat | Compose profile `digichat` | **Keep** |
| `frontend/olympus/` | Next.js dashboard (`basePath: /olympus`) | Built into `dist/olympus/`; Supabase at runtime | **Keep** |

**Olympus artifact:** `frontend/olympus/public/dashboard-data.json` (~284 KB) **is committed**. Atlas ops docs claim it is gitignored — **doc is wrong**. Aligns with **AUDIT-037 / REM-037** (JAN-001).

### 2.5 `digiquant/scripts/atlas/`

~55 tracked Python ops scripts (~1 MB). Many marked **FROZEN** (migrated to `digiquant.data.prices`). Invoked by `digiquant-prices.yml`, `atlas-*` workflows.

**Verdict:** **Keep** for production ops; consolidation belongs to Wave 5 (**REM-058**), not janitor delete (JAN-017 deferred).

### 2.6 `projects/`

`/projects/` gitignored (confidential per AGENTS.md). Public mirror: `docs/projects/`. **Do not commit** `projects/` contents (JAN-029).

### 2.7 `docs/superpowers/`

Planning docs (provider review, FX automation). Some June 2026 files were untracked at audit time — commit or fold into issues (JAN-012).

### 2.8 `find_stale.py` summary

398 vulture hits @ ≥60% — triage input only; not a deletion gate (JAN-021).

---

## 3. Committed artifacts that should not be in git

| Path | ~Size | Issue | Overlaps audit |
|------|------:|-------|----------------|
| `frontend/olympus/public/dashboard-data.json` | 284 KB | Portfolio static fallback shipped as public asset | **AUDIT-037**, **REM-037**, JAN-001 |
| `digiquant/tearsheet.html` | 1.3 MB | Generated Plotly HTML sample in component tree | JAN-002 |
| `package-lock.json` (root) | 519 KB | Stale `apps/digiquant-atlas/frontend` + `frontend/atlas` extraneous packages | JAN-003 |
| `docs/superpowers/plans/2026-05-01-provider-review.md` | 95 KB | Large planning doc (OK if intentional) | JAN-026 optional |

**Correctly excluded (local only):** `dist/`, `node_modules/`, `digiquant/data/*.csv`, `htmlcov/`, `projects/*`, root `data/price-history/`.

---

## 4. Doc/code references to deleted paths

| Stale reference | Where | Should point to |
|-----------------|-------|-----------------|
| `apps/digiquant-atlas/` | `docs/plans/`, ADRs 0009–0014, backlog-reshape | `digiquant/src/digiquant/olympus/atlas/`, `frontend/olympus/` |
| `frontend/atlas/` | Root `package-lock.json` | `frontend/olympus/` |
| `website/` | `docs/DEPLOYMENT.md`, `docs/VISION.md` | `frontend/digithings/` |
| `deploy-digiquant.yml` | `CLAUDE.md`, ADR-0012 | `scripts/build-digiquant.sh` or restore workflow (**AUDIT-084**) |
| `dashboard-data.json` gitignored | Atlas `REPOSITORY-INVENTORY.md` | **Committed** until REM-037 |

---

## 5. Janitor proposals (JAN-001 … JAN-032)

| ID | Action | Target | Effort | Risk |
|----|--------|--------|--------|------|
| **JAN-001** | Remove from git + pipeline | `frontend/olympus/public/dashboard-data.json` | S | Low — **REM-037** |
| **JAN-002** | Gitignore + stop committing | `digiquant/tearsheet.html` | S | Low |
| **JAN-003** | Regenerate lockfile | Root `package-lock.json` drop `apps/digiquant-atlas`, `frontend/atlas` | S | Low |
| **JAN-004** | Gitignore | `data/` (repo root price-history + agent-cache) | S | Low |
| **JAN-005** | Gitignore | `.remember/` | S | Low |
| **JAN-006** | Gitignore | `.local_digikey.sqlite`, `*.sqlite` at repo root | S | Low |
| **JAN-007** | Gitignore | `frontend/olympus/public/dashboard-data.json` after removal | S | Low |
| **JAN-008** | Doc sweep | Replace `apps/digiquant-atlas` in `docs/plans/` + ADRs (historical banners) | M | Low |
| **JAN-009** | Doc fix | `docs/DEPLOYMENT.md`: `website/` → `frontend/digithings/` | S | Low |
| **JAN-010** | Doc/workflow | Reconcile `deploy-digiquant.yml` vs Cloudflare (**AUDIT-084**) | S | Low |
| **JAN-011** | Doc fix | Atlas inventory: dashboard JSON not gitignored | S | Low |
| **JAN-012** | Commit or issue | Untracked `docs/superpowers/*2026-06-04*` | S | Low |
| **JAN-013** | Commit reviews | Untracked `docs/reviews/2026-06-*.md` | S | Low |
| **JAN-014** | Allowlist in git | `projects/README.md` only (exception to `/projects/`) | S | Low |
| **JAN-015** | Delete local only | Stale `dist/` (already gitignored) | S | None |
| **JAN-016** | Delete local only | Root `node_modules/` when not doing frontend work | S | None |
| **JAN-017** | Archive/move | FROZEN `digiquant/scripts/atlas/*` after `digiquant.data.prices` parity | L | Med |
| **JAN-018** | Doc | `digiquant/data/README.md`: CSVs local-only, stack creates synthetics | S | Low |
| **JAN-019** | CI/doc | Olympus: generate `dashboard-data.json` at deploy, not git | M | Low — **REM-038** |
| **JAN-020** | Doc | Retired `static.yml` — remove from operator runbooks | S | Low |
| **JAN-021** | Vulture triage | Top `digisearch/search/*` unused classes | M | Med |
| **JAN-022** | Doc | ONBOARDING: root `npm install` only when needed | S | Low |
| **JAN-023** | Verify | `digiquant/results/` gitignored — no accidental commits | S | Low |
| **JAN-024** | Doc | `data/price-history/` vs `digiquant/data/` operator table | S | Low |
| **JAN-025** | Optional | Smaller tearsheet sample or link to generated artifact | S | Low |
| **JAN-026** | PR hygiene | Split or relocate large `docs/superpowers/plans/*` | S | Low |
| **JAN-027** | Pre-commit | Size limits catch >200 KB JSON/HTML | S | Low |
| **JAN-028** | Unify | `scripts/build-digiquant.sh` vs missing GHA workflow | M | Low |
| **JAN-029** | Keep | `projects/sitaas`, `projects/twelve_x` — confidential, gitignored | — | — |
| **JAN-030** | Keep | All six Python service trees | — | — |
| **JAN-031** | Keep | `frontend/design` + static landings | — | — |
| **JAN-032** | Done | This file (`docs/reviews/2026-06-repository-janitor-audit.md`) | S | None |

---

## 6. Integration with implementation plan waves

| Janitor work | Wave / REM |
|--------------|------------|
| **JAN-001, 007, 011, 019** | **Wave 3** with **REM-037**, **REM-038** (Olympus artifact + deploy) |
| **JAN-008, 009, 010, 020** | **Wave 4** doc drift (**REM-111–137**, **REM-141–143**) |
| **JAN-003–007, 015–016, 022–024** | **Wave 6 — Repository hygiene** (housekeeping PR, 1–2 person-days) |
| **JAN-017, 021** | **After Wave 5** — needs test coverage before deleting ops scripts |
| **JAN-002, 025** | Optional with digiquant export/tearsheet (**REM-028–030**) |
| **JAN-012, 013, 026** | Docs-only; `automerge-docs` eligible |

**Wave 6 (new):** Repository hygiene — execute **JAN-003–007, 015–016, 022–024** in a **separate PR** from the security mega-PR. Low risk; no runtime logic changes required for most items.

**Update (PR #578):** JAN-002, 004–007 landed in the mega-PR `.gitignore`; JAN-003 lockfile regen and JAN-014 `projects/README.md` remain follow-ups — see [`REM-deferred-ops.md`](./REM-deferred-ops.md).

**Wave 7 (placeholder):** Simplify/deslop — pending [`2026-06-simplify-deslop-audit.md`](./2026-06-simplify-deslop-audit.md). Run **after** Waves 0–1 security fixes so refactors do not fight P0 patches.

**Do not bundle:** confidential `projects/` content or mass deletion of `digiquant/scripts/atlas/` into the main audit PR.

---

## Quick reference (user examples)

| Example | Finding |
|---------|---------|
| `dist/` | Build output; **gitignored**; safe to delete locally |
| `frontend/*` | All active; olympus = ex-atlas UI |
| `digiquant/data/AAPL_real.csv` | **Local only**; from `fetch_real_ohlcv.py`; never in git |
| `projects/` | **Gitignored** confidential; keep on disk |
| `docs/superpowers/` | Planning docs; commit or issue-track |
| `apps/` | **Gone**; stale in docs + lockfile |
| `htmlcov/`, `node_modules/` | **Gitignored** correctly |
| `dashboard-data.json` | **Committed** — remove per REM-037 / JAN-001 |
| `tearsheet.html` | **Committed** sample — gitignore per JAN-002 |

---

*Janitor audit generated 2026-06-05. Cross-links: [`2026-06-audit-plan-gap-check.md`](./2026-06-audit-plan-gap-check.md), [`2026-06-full-audit-implementation-plan.md`](./2026-06-full-audit-implementation-plan.md).*
