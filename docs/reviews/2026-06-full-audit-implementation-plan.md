# Full Audit Remediation — Implementation Plan

**Source audit:** [`2026-06-full-audit.md`](./2026-06-full-audit.md) (105 `AUDIT-*` items, 25 `DOC-*` drift entries)  
**Janitor audit:** [`2026-06-repository-janitor-audit.md`](./2026-06-repository-janitor-audit.md) (32 `JAN-*` items)  
**Gap check:** [`2026-06-audit-plan-gap-check.md`](./2026-06-audit-plan-gap-check.md) (`REM-138` … `REM-145`)  
**Date:** 2026-06-05  
**Status:** Plan only — no application code changes in this document  
**Goal:** One major PR (`task/<N>-full-audit-remediation`) with full test validation at merge time; **Wave 6** housekeeping PR optional and separate

---

## Quick reference

| Metric | Value |
|--------|------:|
| `AUDIT-*` items | 105 |
| `REM-*` subtasks (1:1 audit) | 105 (`REM-001` … `REM-105`) |
| Additional `REM-*` (meta + doc gaps) | 32 (`REM-106` … `REM-137`) |
| Gap-check `REM-*` (subagent findings) | 8 (`REM-138` … `REM-145`) |
| **Total `REM-*` subtasks** | **145** |
| `JAN-*` (repository hygiene) | 32 (`JAN-001` … `JAN-032`) — see Wave 6 |
| Suggested logical commits | 24–28 |
| Estimated effort (focused team) | **35–50 person-days** |
| Estimated calendar (8 parallel agents + coordinator) | **3–4 weeks** |

---

## 1. PR strategy

### 1.1 GitHub issue and branch

Per repo policy ([`AGENTS.md`](../../AGENTS.md)), open a tracking epic before coding:

| Step | Action |
|------|--------|
| 1 | `make new-task` or `gh issue create` — title: **Epic: June 2026 full audit remediation**; label `agent-task`; link audit doc; paste wave checklist |
| 2 | `make task ISSUE=<N>` → branch `task/<N>-full-audit-remediation` |
| 3 | Optional module branch: `module/develop` or work directly on task branch from `develop` |

**Suggested branch name:** `task/<N>-full-audit-remediation` (replace `<N>` with epic issue number).

### 1.2 Is one PR realistic?

**Yes, with discipline** — but treat it as a **integration branch**, not a single commit.

| Aspect | Recommendation |
|--------|----------------|
| Scope | All 105 audit items that are **code/config/docs in-repo**; defer §6 out-of-scope items to follow-up issues |
| Reviewability | **24–28 logical commits** grouped by wave/component; PR description links each commit → `REM-*` |
| CI | Expect long PR checks; use draft PR early; rebase onto `develop` daily |
| Risk | Merge conflicts if `develop` moves fast — coordinator rebases once per day max |
| Alternative | If review stalls >2 weeks, split into **Wave PRs** merging into `task/<N>-…` then one final PR to `develop` (still “one user-facing merge” if squash) |

### 1.3 Suggested commit grouping (24–28 commits)

| # | Commit theme | `REM-*` range (approx.) |
|---|--------------|-------------------------|
| 1 | `chore(audit): epic tracking + plan` | REM-106 |
| 2 | `fix(ci): printf + project-fields cron` | REM-006, REM-007 |
| 3 | `fix(ci): provider-review claude CLI` | REM-008, REM-089 |
| 4 | `fix(digiquant): compute-technicals Polars types` | REM-009 |
| 5 | `fix(infra): compose Redis blocklist wiring` | REM-005 |
| 6 | `fix(digiclaw): heartbeat JWT + exit codes` | REM-004, REM-073 |
| 7 | `fix(workflows): dead refs + agent renames` | REM-044, REM-097, REM-096 |
| 8 | `fix(digisearch): ingest backend + path containment` | REM-001, REM-011 |
| 9 | `fix(digisearch): MCP loopback + fail-closed + docker` | REM-003, REM-021, REM-022, REM-023 |
| 10 | `fix(digigraph): MCP loopback + thread binding` | REM-002, REM-025, REM-026 |
| 11 | `fix(digigraph): rate limit XFF + exec sandbox hardening` | REM-027, REM-012 |
| 12 | `fix(digikey): revoke fail-closed + BFF jti + rehydrate` | REM-017, REM-018, REM-019 |
| 13 | `docs(digikey): revocation + ADR status` | REM-013–016, REM-120 |
| 14 | `fix(digiquant): drift Sharpe + drawdown + tearsheet path` | REM-028, REM-029, REM-030 |
| 15 | `fix(digichat): embed auth + SSRF + transactional messages` | REM-010, REM-032, REM-033, REM-034 |
| 16 | `fix(digibase): nested audit redaction + otel` | REM-039, REM-067, REM-068 |
| 17 | `fix(digismith): langsmith pin + docker otel extra` | REM-040, REM-070, REM-071 |
| 18 | `fix(olympus): remove committed artifact + CI workflow` | REM-037, REM-038 |
| 19 | `fix(olympus): RLS threat model doc OR tighten policies` | REM-035, REM-036 (human gate) |
| 20 | `ci: e2e job + baseline + contracts + nautilus smoke` | REM-046, REM-087, REM-088, REM-031 |
| 21 | `ci: score job + markers + atlas-graph orchestrator` | REM-045, REM-085, REM-086, REM-090 |
| 22 | `ci: olympus + digichat route tests + integration hops` | REM-078, REM-069, REM-033 |
| 23 | `perf: graph singletons + yaml/jwt cache` | REM-047, REM-048, REM-052, REM-075 |
| 24 | `fix(digisearch): workspace_id + fetch cap + embeddings` | REM-020, REM-024, REM-062, REM-063, REM-065 |
| 25 | `fix(digiquant): pandas boundary + test import + data_path` | REM-057, REM-060, REM-055 |
| 26 | `fix(frontend): sanitize markdown + design innerHTML + OG` | REM-076–082, REM-083 |
| 27 | `docs: drift sweep batch 1–3` | REM-111–137 (subset) |
| 28 | `chore(audit): validation matrix sign-off` | REM-108–110 |

### 1.4 Human gates (must not be agent-only)

| Area | `REM-*` / `AUDIT-*` | Why |
|------|---------------------|-----|
| **DigiKey / JWT / crypto** | REM-005, REM-017–019, REM-018 | Auth plane + Redis in prod-like compose |
| **Live trading** | None direct; verify no edits under live-trading paths | Pre-push hook |
| **Agent dispatch workflows** | REM-097, REM-098 | `.github/workflows/agent-*-dispatch.yml` protected |
| **Olympus Supabase RLS** | REM-035, REM-036 | Product/security decision: public read vs BFF |
| **DigiChat embed prod** | REM-010 | UX + auth model sign-off |
| **execute_python sandbox** | REM-012 | Security architecture; container vs subprocess |
| **Org GitHub settings** | REM-041 | Not mergeable in repo alone |
| **Atlas LLM quotas** | REM-042, REM-043 | Billing/ops, not code-only |
| **Scoring below threshold** | REM-109 | Human review per `docs/scoring/` |

### 1.5 Effort estimate (buckets)

| Bucket | Person-days | Items (approx.) |
|--------|------------:|-----------------|
| **S** (~0.25–0.5 d each) | 12–15 | ~45 REM |
| **M** (~1 d each) | 18–22 | ~48 REM |
| **L** (~2–4 d each) | 8–14 | ~14 REM + partial defer |
| **Meta / coordination** | 3–5 | REM-106–110, coordinator |
| **Total** | **35–50** | 137 REM |

---

## 2. Wave overview

Waves define **parallel agent batches**. Complete earlier waves before starting dependent work in later waves.

| Wave | Name | Parallel batch size | Primary paths |
|------|------|:-------------------:|---------------|
| **0** | Cron, shell, compose wiring | 6–8 | `.github/workflows/`, `docker-compose.yml`, `digiclaw/` |
| **1** | Security P0 + auth plane | 6–8 | `digisearch/`, `digigraph/`, `digikey/`, `digiclaw/` |
| **2** | CI & test infrastructure | 6–8 | `.github/workflows/`, `tests/`, `scripts/score.py` |
| **3** | Per-module P1 fixes | 8–10 (by component) | `digiquant/`, `digichat/`, `olympus/`, `digibase/` |
| **4** | Docs-only & drift | 8–10 | `**/AGENTS.md`, `**/ARCHITECTURE.md`, `docs/` |
| **5** | Performance, P2/P3, standards | 6–8 | hot paths, `scripts/atlas/`, pandas migration |
| **6** | Repository hygiene (janitor) | 2–4 | `.gitignore`, lockfiles, local artifacts — [`2026-06-repository-janitor-audit.md`](./2026-06-repository-janitor-audit.md) |
| **7** | Simplify / deslop (placeholder) | TBD | Per-module quality pass — pending `2026-06-simplify-deslop-audit.md` |

**Dependency rule:** Wave 1 `REM-001` before `REM-065`; Wave 0 `REM-005` before `REM-004`, `REM-017`; Wave 2 CI jobs after their code fixes land (or stub tests `@pytest.mark.skip` until fixed — avoid). **Wave 6** may merge in parallel with Waves 3–4 but should not block the security mega-PR. **Wave 7** runs after Waves 0–1 P0 security land (avoid refactor churn on hot paths).

### 2.1 Wave 6 — Repository hygiene (`JAN-001` … `JAN-032`)

Separate **housekeeping PR** (1–2 person-days). Full inventory: [`2026-06-repository-janitor-audit.md`](./2026-06-repository-janitor-audit.md).

| Theme | JAN IDs | Notes |
|-------|---------|-------|
| Gitignore / local-only | JAN-004–007, 015–016 | Root `data/`, `.remember/`, sqlite; delete stale `dist/` locally |
| Lockfile cleanup | JAN-003 | Drop stale `apps/digiquant-atlas`, `frontend/atlas` from root `package-lock.json` |
| Committed artifacts | JAN-001, 002, 007 | Overlap **REM-037** (`dashboard-data.json`); `digiquant/tearsheet.html` |
| Doc drift | JAN-008–011, 018–020, 022–024 | `apps/`, `website/`, deploy workflow, operator tables |
| Docs commit | JAN-012–014, 026, 032 | `docs/superpowers/`, `docs/reviews/`, `projects/README.md` allowlist |
| Deferred (post–Wave 5) | JAN-017, 021 | FROZEN atlas scripts; digisearch stub backends |

**Do not** mass-delete `digiquant/scripts/atlas/` or commit `projects/` confidential content in Wave 6.

### 2.2 Wave 7 — Simplify / deslop (placeholder)

**Status:** Pending dedicated audit (`docs/reviews/2026-06-simplify-deslop-audit.md` when subagent completes).

Per-module `/simplify` + `/deslop` pass (code quality, performance hot paths, reuse). Expected `SIMP-*` / `DESLOP-*` items mapped to REM rows after audit lands. **Execute after** Wave 0–1 security fixes; may split by component (`module/<name>`) rather than one mega-PR.

---

## 3. Subtask catalog (`REM-001` … `REM-105`)

Format per entry: **Title** | Component | Files | Depends | Parallel | Acceptance | Effort

---

### Wave 0 — Cron, shell, silent automation

#### REM-001 → AUDIT-001
- **Title:** Route ingest through real search backend `add()`, not stub-only
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/server.py`, `digisearch/src/digisearch/search/` (router/backends), `tests/ds/test_ingest*.py` (new)
- **Depends:** —
- **Parallel:** no (blocks REM-065, REM-062)
- **Acceptance:** `pytest tests/ds/ -m unit -k ingest` passes; Chroma round-trip: ingest file → query returns chunk
- **Effort:** L

#### REM-002 → AUDIT-002
- **Title:** Bind DigiGraph MCP to loopback by default; document TLS/auth
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/mcp_server.py`, `docker-compose.yml`, `digigraph/ARCHITECTURE.md`
- **Depends:** —
- **Parallel:** yes (disjoint from digisearch MCP)
- **Acceptance:** Default host `127.0.0.1`; unit test asserts bind config; compose exposes MCP only on internal network
- **Effort:** M

#### REM-003 → AUDIT-003
- **Title:** Bind DigiSearch MCP to loopback; document ACL
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/mcp_server.py`, `docker-compose.yml`
- **Depends:** REM-023 (compose context) optional same commit
- **Parallel:** yes
- **Acceptance:** MCP not `0.0.0.0` in default compose; README/ARCHITECTURE notes
- **Effort:** S

#### REM-004 → AUDIT-004
- **Title:** Send machine API key Bearer on DigiQuant drift/optimize from heartbeat
- **Component:** digiclaw
- **Files:** `digiclaw/src/digiclaw/heartbeat_runner.py`, `docker-compose.yml` (env for key), `tests/dc/test_heartbeat*.py`
- **Depends:** REM-005
- **Parallel:** no
- **Acceptance:** With stack up + key env, heartbeat logs show 200 on drift; fails loudly without auth
- **Effort:** M

#### REM-005 → AUDIT-005
- **Title:** Wire `DIGIKEY_BLOCKLIST_REDIS_URL` + Redis service in Compose
- **Component:** digikey / infra
- **Files:** `docker-compose.yml`, `.env.example`, `digikey/README` or `LOCAL_STACK.md`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `docker compose up` → revoke invalidates JWT in integration test `tests/dk/`
- **Effort:** M — **HUMAN GATE**

#### REM-006 → AUDIT-006
- **Title:** Fix `printf` flag parsing in enforce-project-assignment workflow
- **Component:** workflows
- **Files:** `.github/workflows/enforce-project-assignment.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `act` dry-run or manual bash replay; next 7 scheduled runs green
- **Effort:** S

#### REM-007 → AUDIT-007
- **Title:** Fix project-fields TSV models and initialize `pilot` variable
- **Component:** workflows
- **Files:** `.github/workflows/project-fields-coverage.yml`, `scripts/project_fields.tsv`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** Workflow script exits 0 locally; daily cron green
- **Effort:** S

#### REM-008 → AUDIT-008
- **Title:** Fix provider-review workflow missing `claude` CLI
- **Component:** workflows
- **Files:** `.github/workflows/provider-review.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** Weekly job reaches pytest step; REM-089 wires tests
- **Effort:** S

#### REM-009 → AUDIT-009
- **Title:** Fix Polars Date vs Datetime `is_in` in compute-technicals
- **Component:** digiquant / workflows
- **Files:** `digiquant/scripts/atlas/compute-technicals.py`, `.github/workflows/digiquant-prices.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `python digiquant/scripts/atlas/compute-technicals.py` (fixture data) exits 0; intraday workflow green
- **Effort:** M

#### REM-010 → AUDIT-010
- **Title:** Fix embed → `/api/chat` auth mismatch (token or disable prod embed)
- **Component:** digichat
- **Files:** `frontend/digichat/src/app/embed/page.tsx`, `frontend/digichat/src/app/api/chat/route.ts`, `OPERATIONS.md`
- **Depends:** product decision — **HUMAN GATE**
- **Parallel:** no (touches auth contract)
- **Acceptance:** Vitest: embed flow returns 401 without token OR 200 with embed token; manual iframe test documented
- **Effort:** L

#### REM-011 → AUDIT-011
- **Title:** Enforce `DIGISEARCH_INGEST_ROOT` path containment on ingest
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/server.py`, `digisearch/src/digisearch/config.py`, `tests/ds/test_ingest_path_traversal.py` (new)
- **Depends:** —
- **Parallel:** yes (pair with REM-001 same PR commit ok)
- **Acceptance:** pytest: `../../../etc/passwd` → 400; allowed path → 200
- **Effort:** M

#### REM-012 → AUDIT-012
- **Title:** Harden execute_python sandbox when `DIGI_ALLOW_CODE_EXEC=1`
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/tools/analytics/execute_python.py`, `tests/dg/test_execute_python_security.py` (new)
- **Depends:** —
- **Parallel:** yes — **HUMAN GATE** for container approach
- **Acceptance:** No raw `__builtins__` inject; prod compose keeps flag off; security unit tests
- **Effort:** L

---

### Wave 1 — Security P1 & trust boundaries

#### REM-013 → AUDIT-013
- **Title:** Update digikey AGENTS.md revocation section (Redis opt-in)
- **Component:** digikey
- **Files:** `digikey/AGENTS.md`
- **Depends:** REM-005
- **Parallel:** yes
- **Acceptance:** `make doc-check`; text matches `blocklist.py` behavior
- **Effort:** S

#### REM-014 → AUDIT-014
- **Title:** Update digikey ARCHITECTURE.md §6/§11 for blocklist
- **Component:** digikey
- **Files:** `digikey/ARCHITECTURE.md`
- **Depends:** REM-013
- **Parallel:** yes
- **Acceptance:** doc-check; no “no revocation” claims
- **Effort:** M

#### REM-015 → AUDIT-015
- **Title:** Update root ARCHITECTURE.md conditional revocation wording
- **Component:** root docs
- **Files:** `ARCHITECTURE.md`
- **Depends:** REM-013
- **Parallel:** yes
- **Acceptance:** doc-check
- **Effort:** S

#### REM-016 → AUDIT-016
- **Title:** Update SECURITY.md with Redis blocklist + revoke endpoint
- **Component:** root docs
- **Files:** `SECURITY.md`
- **Depends:** REM-013
- **Parallel:** yes
- **Acceptance:** doc-check; security reviewer sign-off
- **Effort:** S

#### REM-017 → AUDIT-017
- **Title:** Fail revoke with 503 when Redis blocklist unset in prod mode
- **Component:** digikey
- **Files:** `digikey/src/digikey/server.py`, `tests/dk/test_revoke.py`
- **Depends:** REM-005
- **Parallel:** no — **HUMAN GATE**
- **Acceptance:** pytest: no Redis + prod flag → 503; with Redis → 200 + jti blocked
- **Effort:** M

#### REM-018 → AUDIT-018
- **Title:** Insert `JtiIssuedRow` for BFF-issued session tokens
- **Component:** digikey
- **Files:** `digikey/src/digikey/server.py`, DB models/migrations, `tests/dk/test_jwt_roundtrip.py`
- **Depends:** REM-005
- **Parallel:** no — **HUMAN GATE**
- **Acceptance:** BFF login creates row; revoke invalidates session JWT
- **Effort:** M

#### REM-019 → AUDIT-019
- **Title:** Rehydrate Redis blocklist from `jti_issued` on DigiKey startup
- **Component:** digikey
- **Files:** `digikey/src/digikey/blocklist.py`, `digikey/src/digikey/lifespan.py` (or startup), `tests/dk/`
- **Depends:** REM-005, REM-017
- **Parallel:** no — **HUMAN GATE**
- **Acceptance:** pytest: restart simulation repopulates revoked jtis
- **Effort:** M

#### REM-020 → AUDIT-020
- **Title:** Enforce `workspace_id` at query time (tenant isolation)
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/core/models.py`, backends, `server.py`, `tests/ds/`
- **Depends:** REM-001
- **Parallel:** no
- **Acceptance:** pytest: query without matching workspace returns empty or 403
- **Effort:** L

#### REM-021 → AUDIT-021
- **Title:** Fail closed when MCP backend client fails (no silent stub)
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/mcp_server.py`
- **Depends:** REM-003
- **Parallel:** yes
- **Acceptance:** unit test: backend error surfaces to MCP client
- **Effort:** S

#### REM-022 → AUDIT-022
- **Title:** Add `[ingestion]` extra to DigiSearch Dockerfile
- **Component:** digisearch
- **Files:** `digisearch/Dockerfile`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `docker compose build digisearch` succeeds; import ingestion modules in container
- **Effort:** S

#### REM-023 → AUDIT-023
- **Title:** Fix MCP service Docker build context / COPY paths
- **Component:** digisearch / infra
- **Files:** `docker-compose.yml`, `digisearch/Dockerfile`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `docker compose build` for MCP profile succeeds
- **Effort:** S

#### REM-024 → AUDIT-024
- **Title:** Cap `digisearch_fetch_all` with server default and hard ceiling
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/server.py`, `tests/ds/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: request above cap → truncated or 413
- **Effort:** M

#### REM-025 → AUDIT-025
- **Title:** Bind thread APIs to authenticated JWT `sub`
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/server.py`, `tests/dg/test_threads.py` (new)
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: user A cannot read user B thread_id
- **Effort:** M

#### REM-026 → AUDIT-026
- **Title:** Remove shared default `thread_id` `"default"`
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/workflow.py`, `server.py`
- **Depends:** REM-025
- **Parallel:** no
- **Acceptance:** pytest: missing thread_id → 400 or derived from JWT
- **Effort:** M

#### REM-027 → AUDIT-027
- **Title:** Implement `DIGI_TRUSTED_PROXIES` for rate limiter XFF
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/rate_limit.py`, `.env.example`, `tests/dg/test_rate_limit.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: spoofed XFF ignored unless from trusted proxy CIDR
- **Effort:** M

#### REM-028 → AUDIT-028
- **Title:** Wire `current_sharpe` into `/check_drift` handler
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/server.py`, `digiquant/src/digiquant/addm.py`, `tests/dq/test_drift.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: drift returns `implemented=True` when Sharpe supplied
- **Effort:** M

#### REM-029 → AUDIT-029
- **Title:** Normalize drawdown sign in constraints vs Nautilus output
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/constraints.py`, `digiquant/src/digiquant/nautilus_runner.py`, `tests/dq/test_constraints.py`
- **Depends:** REM-060
- **Parallel:** yes
- **Acceptance:** pytest: deep drawdown rejects when constraint enabled
- **Effort:** M

#### REM-030 → AUDIT-030
- **Title:** Confine `tearsheet_path` under `BACKTEST_RESULTS_DIR`
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/nautilus_runner.py`, `tests/dq/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: absolute path outside dir → 400
- **Effort:** S

#### REM-031 → AUDIT-031
- **Title:** Add Nautilus smoke job on Linux CI
- **Component:** digiquant / CI
- **Files:** `.github/workflows/digiquant-test.yml`, `tests/dq/conftest.py`
- **Depends:** REM-029, REM-060
- **Parallel:** no (wave 2 overlap — implement in wave 2)
- **Acceptance:** Ubuntu job runs `pytest tests/dq/ -m unit -k nautilus` (or dedicated marker) green
- **Effort:** L

#### REM-032 → AUDIT-032
- **Title:** Tighten DigiChat SSRF allowlist (known hosts + env)
- **Component:** digichat
- **Files:** `frontend/digichat/src/lib/ecosystem.ts`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** REM-033 tests pass; single-label hostnames rejected
- **Effort:** M

#### REM-033 → AUDIT-033
- **Title:** Add Vitest table-driven SSRF allowlist tests
- **Component:** digichat
- **Files:** `frontend/digichat/src/lib/ecosystem.test.ts` (new)
- **Depends:** REM-032
- **Parallel:** no
- **Acceptance:** `cd frontend/digichat && npm run test -- ecosystem`
- **Effort:** S

#### REM-034 → AUDIT-034
- **Title:** Wrap `replaceConversationMessages` in DB transaction
- **Component:** digichat
- **Files:** `frontend/digichat/src/lib/db/conversations-repo.ts`, tests
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** Vitest: simulated failure mid-replace rolls back
- **Effort:** S

#### REM-035 → AUDIT-035
- **Title:** Olympus Supabase RLS — tighten or document public read model
- **Component:** olympus
- **Files:** `frontend/olympus/supabase/migrations/001_initial_schema.sql` (new migration), `olympus/README.md`, ADR (new optional)
- **Depends:** REM-036 — **HUMAN GATE**
- **Parallel:** no
- **Acceptance:** Signed threat model in docs OR migration restricts anon `SELECT`
- **Effort:** L

#### REM-036 → AUDIT-036
- **Title:** Replace static anon Supabase pattern with BFF or documented public model
- **Component:** olympus
- **Files:** `frontend/olympus/src/lib/supabase.ts`, API routes (if BFF)
- **Depends:** REM-035
- **Parallel:** no — **HUMAN GATE**
- **Acceptance:** No service-role/anon key in client bundle OR explicit public-data ADR
- **Effort:** L

#### REM-037 → AUDIT-037
- **Title:** Remove committed `dashboard-data.json` from git + deploy pipeline
- **Component:** olympus
- **Files:** `frontend/olympus/public/dashboard-data.json`, `.gitignore`, deploy scripts
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** file absent from tree; build fetches or generates at deploy
- **Effort:** S

#### REM-038 → AUDIT-038
- **Title:** Add `olympus-test.yml` and wire into `ci.yml`
- **Component:** olympus / CI
- **Files:** `.github/workflows/olympus-test.yml`, `.github/workflows/ci.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** PR triggers lint + vitest + build for `frontend/olympus/**`
- **Effort:** M

#### REM-039 → AUDIT-039
- **Title:** Recursive audit redaction for nested secrets
- **Component:** digibase
- **Files:** `digibase/src/digibase/audit.py`, `tests/db/test_audit_redaction.py` (new)
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: nested dict keys redacted
- **Effort:** M

#### REM-040 → AUDIT-040
- **Title:** Pin LangSmith SDK min version; log when redaction skipped
- **Component:** digismith
- **Files:** `digismith/pyproject.toml`, `digismith/src/digismith/trace.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest or caplog: old SDK → WARNING
- **Effort:** S

#### REM-041 → AUDIT-041
- **Title:** Fix agent-backlog-snapshot bot PR policy (org setting or PAT)
- **Component:** workflows / org
- **Files:** `.github/workflows/agent-backlog-snapshot.yml`, org docs
- **Depends:** org admin — **defer or HUMAN GATE**
- **Parallel:** n/a
- **Acceptance:** Weekly run opens PR or documents manual snapshot process
- **Effort:** S (ops)

#### REM-042 → AUDIT-042
- **Title:** Reduce Atlas baseline LLM rate-limit failures
- **Component:** workflows / digiquant
- **Files:** `.github/workflows/atlas-baseline.yml`, `digiquant/src/digiquant/olympus/atlas/` config
- **Depends:** ops quota — **DEFER §6**
- **Parallel:** n/a
- **Acceptance:** 3 consecutive scheduled greens OR issue linked to quota upgrade
- **Effort:** M (ops)

#### REM-043 → AUDIT-043
- **Title:** Tune atlas-delta timeout and idempotency documentation
- **Component:** workflows
- **Files:** `.github/workflows/atlas-delta.yml`, `digiquant/docs/`
- **Depends:** ops — **DEFER partial**
- **Parallel:** n/a
- **Acceptance:** workflow `timeout-minutes` aligned; runbook for retries
- **Effort:** M

#### REM-044 → AUDIT-044
- **Title:** Remove or implement missing `pr-quality-gate.yml` reference
- **Component:** workflows
- **Files:** `.github/workflows/ci-failure-triage.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `workflow_call` validates; no dead workflow name
- **Effort:** S

#### REM-045 → AUDIT-045
- **Title:** Add optional `make score` job to GHA for PRs
- **Component:** tests/CI
- **Files:** `.github/workflows/score-gate.yml` (new) or extend `ci.yml`, `scripts/score.py`
- **Depends:** REM-093
- **Parallel:** yes (wave 2)
- **Acceptance:** PR comment or check reports 4 dimensions; non-blocking optional first
- **Effort:** M

#### REM-046 → AUDIT-046
- **Title:** Add compose-up `pytest -m e2e` job to GHA
- **Component:** tests/CI
- **Files:** `.github/workflows/e2e.yml` (new), `tests/test_e2e.py`
- **Depends:** REM-005, REM-001 (stack healthy)
- **Parallel:** no
- **Acceptance:** CI job runs 8 e2e tests green (or documented secrets skip)
- **Effort:** L

#### REM-047 → AUDIT-047
- **Title:** Cache compiled LangGraph workflow singleton in DigiGraph
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/workflow.py`, `digigraph/src/digigraph/graph/graph.py`
- **Depends:** —
- **Parallel:** yes (wave 5)
- **Acceptance:** pytest benchmark or log assert: compile once per process
- **Effort:** M

#### REM-048 → AUDIT-048
- **Title:** Cache compiled DigiQuant pipeline graph
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/graph/pipeline.py`
- **Depends:** —
- **Parallel:** yes (wave 5)
- **Acceptance:** unit test: second invoke does not recompile
- **Effort:** M

---

### Wave 2 — CI & test infrastructure (REM-049 … REM-090 continued)

#### REM-049 → AUDIT-049
- **Title:** Gate `data_engineer_agent` registration on `code_execution_allowed()`
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/orchestration/builtin.py`
- **Depends:** REM-012
- **Parallel:** yes
- **Acceptance:** pytest: flag off → agent not registered
- **Effort:** S

#### REM-050 → AUDIT-050
- **Title:** Set ChatCompletionRequest `extra="forbid"` + tests
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/models.py`, `tests/dg/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: unknown field → 422
- **Effort:** S

#### REM-051 → AUDIT-051
- **Title:** Add streaming cancel/backpressure to workflow SSE
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/server.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest or manual: client disconnect stops producer
- **Effort:** M

#### REM-052 → AUDIT-052
- **Title:** Cache `model_modes.yaml` with mtime invalidation
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/llm.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** unit test: second call does not re-read file
- **Effort:** S

#### REM-053 → AUDIT-053
- **Title:** Add security unit tests for execute_python, hubs, MCP
- **Component:** digigraph
- **Files:** `tests/dg/test_execute_python_security.py`, `tests/dg/test_mcp_server.py` (new)
- **Depends:** REM-002, REM-012
- **Parallel:** no
- **Acceptance:** `pytest tests/dg/ -m unit -k "mcp or execute_python"`
- **Effort:** M

#### REM-054 → AUDIT-054
- **Title:** Add ruff format + coverage to digigraph-test.yml
- **Component:** digigraph / CI
- **Files:** `.github/workflows/digigraph-test.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** CI runs `ruff format --check` + coverage upload
- **Effort:** S

#### REM-055 → AUDIT-055
- **Title:** Require `data_path` under `DIGIQUANT_DATA_ROOT`
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/nautilus_runner.py`, `tests/dq/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: path escape → error
- **Effort:** M

#### REM-056 → AUDIT-056
- **Title:** Enforce TTL prune for `_backtest_jobs`
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/server.py`, `tests/dq/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: stale job removed after TTL
- **Effort:** S

#### REM-057 → AUDIT-057
- **Title:** Update digiquant pandas boundary docs or migrate offenders
- **Component:** digiquant
- **Files:** `digiquant/AGENTS.md`, strategy modules per grep
- **Depends:** REM-058 (partial)
- **Parallel:** yes
- **Acceptance:** doc matches ruff/permit list; CI grep gate documented
- **Effort:** M

#### REM-058 → AUDIT-058
- **Title:** Migrate `scripts/atlas/*.py` from pandas to Polars path
- **Component:** digiquant
- **Files:** `digiquant/scripts/atlas/*.py`, `pyproject.toml` ruff excludes
- **Depends:** REM-009
- **Parallel:** no — large; may **split to follow-up PR**
- **Acceptance:** `ruff check digiquant/scripts/atlas`; no pandas import
- **Effort:** L — consider **DEFER partial**

#### REM-059 → AUDIT-059
- **Title:** Extract minimal pipeline builder from DigiGraph Hermes dependency
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/olympus/hermes/chain.py`, new `digiquant/hermes/pipeline_builder.py`
- **Depends:** —
- **Parallel:** no
- **Acceptance:** Hermes chain imports without `digigraph.graph.pipeline_builder`
- **Effort:** L — **DEFER or thin shim in mega PR**

#### REM-060 → AUDIT-060
- **Title:** Fix wrong import in `test_constraints.py`
- **Component:** digiquant
- **Files:** `tests/dq/test_constraints.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `pytest tests/dq/test_constraints.py -v` collects
- **Effort:** S

#### REM-061 → AUDIT-061
- **Title:** Implement Chroma HTTP client or remove `CHROMA_HOST` gate
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/search/_stub.py`, chroma backend module
- **Depends:** REM-001
- **Parallel:** no
- **Acceptance:** integration test with Chroma container or env-gated skip
- **Effort:** M

#### REM-062 → AUDIT-062
- **Title:** Wire `BatchEmbedder` on ingest path
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/server.py`, ingestion pipeline
- **Depends:** REM-001
- **Parallel:** no
- **Acceptance:** ingest → query similarity non-zero
- **Effort:** M

#### REM-063 → AUDIT-063
- **Title:** Allowlist Chroma filter field names in `chroma_where.py`
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/core/chroma_where.py`, `tests/ds/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: unknown field → 400
- **Effort:** M

#### REM-064 → AUDIT-064
- **Title:** SSRF allowlist for scraped hrefs in web_scrape ingestion
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/ingestion/web_scrape.py`, `tests/ds/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: `file://` and internal IPs blocked
- **Effort:** M

#### REM-065 → AUDIT-065
- **Title:** Add ingest round-trip and path-traversal tests
- **Component:** digisearch
- **Files:** `tests/ds/test_ingest_roundtrip.py`, `tests/ds/test_ingest_path_traversal.py`
- **Depends:** REM-001, REM-011
- **Parallel:** no
- **Acceptance:** `pytest tests/ds/ -m unit -k ingest` green
- **Effort:** M

#### REM-066 → AUDIT-066
- **Title:** Ensure X-Request-ID on unhandled 500 in digibase middleware
- **Component:** digibase
- **Files:** `digibase/src/digibase/http.py`, `tests/db/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: forced 500 includes header
- **Effort:** S

#### REM-067 → AUDIT-067
- **Title:** Add unit tests for digibase OTel helpers
- **Component:** digibase
- **Files:** `tests/db/test_otel.py` (new), `digibase/src/digibase/otel.py`
- **Depends:** REM-068 optional same PR
- **Parallel:** yes
- **Acceptance:** `pytest tests/db/test_otel.py -v`
- **Effort:** S

#### REM-068 → AUDIT-068
- **Title:** Propagate W3C traceparent on outbound httpx
- **Component:** digibase
- **Files:** `digibase/src/digibase/otel.py`, consumer services
- **Depends:** REM-067
- **Parallel:** yes
- **Acceptance:** pytest: inject header on mock client
- **Effort:** M

#### REM-069 → AUDIT-069
- **Title:** Run request-id integration hops in digibase CI
- **Component:** digibase / CI
- **Files:** `.github/workflows/digibase-test.yml`, `tests/integration/test_request_id_hops.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** CI job runs integration marker green
- **Effort:** S

#### REM-070 → AUDIT-070
- **Title:** Install `digibase[otel]` in DigiSmith Dockerfile when OTLP set
- **Component:** digismith
- **Files:** `digismith/Dockerfile`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** image build; `/metrics` or otel exporter smoke
- **Effort:** S

#### REM-071 → AUDIT-071
- **Title:** Test `langsmith_host_sanitized` strips credentials
- **Component:** digismith
- **Files:** `digismith/src/digismith/config.py`, `tests/dsm/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: URL with user:pass → sanitized
- **Effort:** S

#### REM-072 → AUDIT-072
- **Title:** Fix HEARTBEAT.md path for Docker `DIGI_WORKSPACE`
- **Component:** digiclaw
- **Files:** `digiclaw/ARCHITECTURE.md`, `digiclaw/src/digiclaw/heartbeat_runner.py` or compose volume
- **Depends:** —
- **Parallel:** yes (wave 0)
- **Acceptance:** heartbeat profile finds checklist file in container
- **Effort:** S

#### REM-073 → AUDIT-073
- **Title:** Return non-zero exit when heartbeat unhealthy
- **Component:** digiclaw
- **Files:** `digiclaw/src/digiclaw/heartbeat_runner.py`, `tests/dc/`
- **Depends:** REM-004
- **Parallel:** yes
- **Acceptance:** pytest: failed drift → exit code != 0
- **Effort:** S

#### REM-074 → AUDIT-074
- **Title:** Update digiclaw AGENTS.md ADDM wording to match addm.py
- **Component:** digiclaw
- **Files:** `digiclaw/AGENTS.md`
- **Depends:** REM-028
- **Parallel:** yes
- **Acceptance:** doc-check
- **Effort:** S

#### REM-075 → AUDIT-075
- **Title:** Cache DigiKey JWT exchange until exp minus skew
- **Component:** digichat
- **Files:** `frontend/digichat/src/lib/digigraph-upstream.ts`, tests
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** Vitest: second message reuses token within TTL
- **Effort:** M

#### REM-076 → AUDIT-076
- **Title:** Add `rehype-sanitize` to DigiChat markdown renderer
- **Component:** digichat
- **Files:** `frontend/digichat/src/components/chat-panel.tsx`, `package.json`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** Vitest: script tag stripped
- **Effort:** S

#### REM-077 → AUDIT-077
- **Title:** Apply global CSP headers on main DigiChat app
- **Component:** digichat
- **Files:** `frontend/digichat/next.config.ts`
- **Depends:** REM-010
- **Parallel:** no
- **Acceptance:** build passes; security headers on `/`
- **Effort:** M

#### REM-078 → AUDIT-078
- **Title:** Add Vitest contract tests for API route handlers
- **Component:** digichat
- **Files:** `frontend/digichat/src/app/api/**/*.test.ts` (new)
- **Depends:** REM-010
- **Parallel:** yes
- **Acceptance:** `npm run test` covers ≥5 routes
- **Effort:** M

#### REM-079 → AUDIT-079
- **Title:** Unify machine key prefix glossary in digichat ARCHITECTURE
- **Component:** digichat
- **Files:** `frontend/digichat/ARCHITECTURE.md`, `OPERATIONS.md`, `request-auth.ts` comments
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** doc-check; single canonical prefix documented
- **Effort:** S

#### REM-080 → AUDIT-080
- **Title:** Roll out `SafeMarkdown` with rehype-sanitize in Olympus library views
- **Component:** olympus
- **Files:** `frontend/olympus/src/components/library/*.tsx`, shared component
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `npm run test` + visual spot-check; script stripped in test
- **Effort:** M

#### REM-081 → AUDIT-081
- **Title:** Replace ticker.js innerHTML with textContent/escape
- **Component:** design
- **Files:** `frontend/design/src/ticker.js` (or path per tree)
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** grep no innerHTML in ticker; manual landings check
- **Effort:** S

#### REM-082 → AUDIT-082
- **Title:** Replace typewriter.js innerHTML with textContent
- **Component:** design
- **Files:** `frontend/design/src/typewriter.js`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** grep clean; landings typewriter works
- **Effort:** S

#### REM-083 → AUDIT-083
- **Title:** Add og.png and absolute OG URLs on digithings landing
- **Component:** landings
- **Files:** `frontend/digithings/index.html`, `frontend/digithings/public/og.png`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** social debugger preview valid URL
- **Effort:** S

#### REM-084 → AUDIT-084
- **Title:** Reconcile digiquant deploy docs with Cloudflare build script
- **Component:** landings
- **Files:** `frontend/digiquant/README.md`, `scripts/build-digiquant.sh`, `DEPLOYMENT.md`
- **Depends:** REM-096
- **Parallel:** yes
- **Acceptance:** doc-check links; no reference to missing workflow file
- **Effort:** S

#### REM-085 → AUDIT-085
- **Title:** Mark `tests/dk/test_scopes.py` with `@pytest.mark.unit`
- **Component:** tests/CI
- **Files:** `tests/dk/test_scopes.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `pytest -m unit tests/dk/test_scopes.py` collects tests
- **Effort:** S

#### REM-086 → AUDIT-086
- **Title:** Mark `tests/dk/test_jwt_roundtrip.py` with `@pytest.mark.unit`
- **Component:** tests/CI
- **Files:** `tests/dk/test_jwt_roundtrip.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** included in `make test-unit`
- **Effort:** S

#### REM-087 → AUDIT-087
- **Title:** Add `pytest -m baseline` job to GHA
- **Component:** tests/CI
- **Files:** `.github/workflows/ci.yml` or `baseline.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `make test-baseline` mirrored in CI
- **Effort:** M

#### REM-088 → AUDIT-088
- **Title:** Run OpenAPI contract tests in digigraph CI
- **Component:** tests/CI
- **Files:** `.github/workflows/digigraph-test.yml`, `tests/contracts/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `pytest tests/contracts/ -v` in CI
- **Effort:** M

#### REM-089 → AUDIT-089
- **Title:** Wire `tests/provider_review/` into provider-review workflow
- **Component:** tests/CI
- **Files:** `.github/workflows/provider-review.yml`, `tests/provider_review/`
- **Depends:** REM-008
- **Parallel:** no
- **Acceptance:** 14 tests run weekly
- **Effort:** S

#### REM-090 → AUDIT-090
- **Title:** Add atlas-graph-ci to ci.yml orchestrator or weekly full run
- **Component:** tests/CI
- **Files:** `.github/workflows/ci.yml`, `.github/workflows/atlas-graph-ci.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** PR touching `digiquant/**/atlas/**` always runs graph CI
- **Effort:** M

#### REM-091 → AUDIT-091
- **Title:** Declare or remove orphan `security-reviewer` subagent source
- **Component:** agents
- **Files:** `agents.yml`, `agents/sources/subagents/security-reviewer.md`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `make agents-init && scripts/agents_init.py --check` pass
- **Effort:** S

#### REM-092 → AUDIT-092
- **Title:** Declare or remove orphan `ci-triage` skill source
- **Component:** agents
- **Files:** `agents.yml`, `agents/sources/skills/ci-triage/SKILL.md`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** agents_init --check pass
- **Effort:** S

#### REM-093 → AUDIT-093
- **Title:** Align docs/scoring/README thresholds with agents.yml
- **Component:** agents
- **Files:** `docs/scoring/README.md`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** text shows ≥8/≥8/≥7/≥9
- **Effort:** S

#### REM-094 → AUDIT-094
- **Title:** Fix digichat `test_cmd` path in agents.yml
- **Component:** agents
- **Files:** `agents.yml`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** agents_init --check; component-router returns correct npm path
- **Effort:** S

#### REM-095 → AUDIT-095
- **Title:** Run `validate_model_routing.py` in CI
- **Component:** config
- **Files:** `.github/workflows/ci.yml`, `scripts/validate_model_routing.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** CI step exits 0 on develop
- **Effort:** S

#### REM-096 → AUDIT-096
- **Title:** Update CLAUDE.md/DEPLOYMENT for retired static.yml → Cloudflare
- **Component:** workflows / docs
- **Files:** `CLAUDE.md`, `docs/DEPLOYMENT.md`, `.github/workflows/static.yml` (banner)
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** doc-check; no dead deploy instructions
- **Effort:** S

#### REM-097 → AUDIT-097
- **Title:** Merge agent workflow renames; update EXECUTION_TIERS.md
- **Component:** workflows
- **Files:** `.github/workflows/agent-*-dispatch.yml`, `docs/agents/EXECUTION_TIERS.md`
- **Depends:** — — **HUMAN GATE**
- **Parallel:** no
- **Acceptance:** `develop` has consistent filenames; dispatch smoke on label
- **Effort:** M

#### REM-098 → AUDIT-098
- **Title:** Consolidate redundant Copilot dispatch/review workflow paths
- **Component:** workflows
- **Files:** `.github/workflows/ci.yml`, copilot workflows
- **Depends:** REM-097
- **Parallel:** no
- **Acceptance:** Single copilot review trigger per PR event
- **Effort:** M

---

### Wave 5 — Performance, P3, standards (REM-099 … REM-105)

#### REM-099 → AUDIT-099
- **Title:** Document Postgres checkpointer requirement for DigiGraph HA
- **Component:** digigraph
- **Files:** `digigraph/ARCHITECTURE.md`, `digigraph/src/digigraph/graph/graph.py` (comment)
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** doc-check; HA section mentions `DIGI_CHECKPOINTER=postgres`
- **Effort:** S

#### REM-100 → AUDIT-100
- **Title:** Wire or remove stub `register_mcp_server` until #401
- **Component:** digigraph
- **Files:** `digigraph/src/digigraph/orchestration/registry.py`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** dead code removed OR tools registered; issue #401 linked
- **Effort:** S

#### REM-101 → AUDIT-101
- **Title:** Add LRU/TTL cap to backtest SHA-256 cache
- **Component:** digiquant
- **Files:** `digiquant/src/digiquant/backtest.py`, `tests/dq/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: eviction after N entries
- **Effort:** S

#### REM-102 → AUDIT-102
- **Title:** Schedule `execute_at_open.py` in cron workflow
- **Component:** digiquant / workflows
- **Files:** `.github/workflows/` (new or extend digiquant-prices), `digiquant/scripts/atlas/execute_at_open.py`
- **Depends:** REM-009
- **Parallel:** yes
- **Acceptance:** workflow_dispatch succeeds; schedule documented
- **Effort:** M

#### REM-103 → AUDIT-103
- **Title:** Namespace embedding cache keys with model id
- **Component:** digisearch
- **Files:** `digisearch/src/digisearch/embedding/cache.py`, `tests/ds/`
- **Depends:** REM-062
- **Parallel:** yes
- **Acceptance:** pytest: model change → cache miss
- **Effort:** S

#### REM-104 → AUDIT-104
- **Title:** Rate-limit token endpoint per API key prefix
- **Component:** digikey
- **Files:** `digikey/src/digikey/ratelimit.py`, `tests/dk/`
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** pytest: two keys independent buckets
- **Effort:** M

#### REM-105 → AUDIT-105
- **Title:** Remove unused `zod` dependency or use for API validation
- **Component:** digichat
- **Files:** `frontend/digichat/package.json`, route handlers
- **Depends:** —
- **Parallel:** yes
- **Acceptance:** `npm run build`; dep used or removed
- **Effort:** S

---

## 4. Additional subtasks (`REM-106` … `REM-137`)

Meta, validation, and **DOC-*** gaps not fully covered by audit rows.

| ID | Maps | Component | Title | Files | Depends | Parallel | Acceptance | Effort |
|----|------|-----------|-------|-------|---------|----------|------------|--------|
| REM-106 | — | meta | Create GitHub epic issue on Project #1 | GitHub | — | yes | Issue #N with all REM checklist linked | S |
| REM-107 | — | meta | Bootstrap `task/N-full-audit-remediation` branch | git | REM-106 | no | Branch tracks develop; PR template filled | S |
| REM-108 | — | meta | Document full validation runbook in plan appendix | this file §5 | REM-110 | yes | Maintainer can run gate without agent | S |
| REM-109 | — | meta | Run `make score` on branch; fix until thresholds met | staged diff | all waves | no | Security≥8 Quality≥8 Opt≥7 Acc≥9 | M |
| REM-110 | — | meta | Pre-PR sign-off checklist completed | PR body | REM-108 | no | All checkboxes in §5.6 ticked | S |
| REM-111 | DOC-03 | digikey | Mark ADR-0007 implemented (not proposed) | `docs/adr/0007-digikey-revocation.md` | REM-013 | yes | ADR status accepted | S |
| REM-112 | DOC-04/05 | digiquant/digiclaw | Fix ADDM stub docs in digiquant AGENTS | `digiquant/AGENTS.md` | REM-028,074 | yes | doc-check | S |
| REM-113 | DOC-07 | digigraph | Fix require_scope per-route doc drift | `digigraph/AGENTS.md` | — | yes | Matches middleware model | S |
| REM-114 | DOC-08 | digigraph | Document data_engineer gate at registration | `digigraph/ARCHITECTURE.md` | REM-049 | yes | Matches code | S |
| REM-115 | DOC-09 | digisearch | Fix `/azure_status` auth in ARCHITECTURE | `digisearch/ARCHITECTURE.md` | — | yes | Matches middleware | S |
| REM-116 | DOC-10 | digisearch | Remove FAISS/Pinecone from architecture inventory | `digisearch/ARCHITECTURE.md` | — | yes | Only Chroma+Azure listed | S |
| REM-117 | DOC-11/12 | digismith | Fix Prometheus + healthcheck paths in ARCHITECTURE | `digismith/ARCHITECTURE.md` | REM-070 | yes | doc-check | S |
| REM-118 | DOC-13 | digibase | Refresh digibase file inventory in ARCHITECTURE | `digibase/ARCHITECTURE.md` | — | yes | Lists cors, connectors, otel | S |
| REM-119 | DOC-14 | tests | Update tests/README.md CI section | `tests/README.md` | REM-046 | yes | Describes ci.yml | S |
| REM-120 | DOC-16 | docs/agents | Update CI_CONVENTIONS enforce-project status | `docs/agents/CI_CONVENTIONS.md` | REM-006 | yes | Notes fix landed | S |
| REM-121 | DOC-20 | digichat | Fix README embed auth claims | `frontend/digichat/README.md` | REM-010 | yes | Matches route auth | S |
| REM-122 | DOC-21 | root | Fix AGENTS.md digichat test command | `AGENTS.md` | REM-094 | yes | `npm run test` in frontend/digichat | S |
| REM-123 | DOC-22 | agents | Sync agents catalogue with sources | `agents/sources/README.md` | REM-091,092 | yes | Lists finish-task, triage, etc. | S |
| REM-124 | DOC-23 | docs | Update LOCAL_STACK ingest expectations | `docs/LOCAL_STACK.md` | REM-001 | yes | Notes Chroma round-trip | S |
| REM-125 | DOC-24 | olympus | Fix `NEXT_PUBLIC_OLYMPUS_VERSION` env name in README | `frontend/olympus/README.md` | — | yes | Matches code constant | S |
| REM-126 | DOC-25 | digikey | Fix example scope `digigraph:workflow` in AGENTS | `digikey/AGENTS.md` | — | yes | Copy-paste works | S |
| REM-127 | — | CI | Add hook bash tests to GHA (if `tests/hooks/` exists) | `.github/workflows/ci.yml` | — | yes | hooks test green | S |
| REM-128 | — | CI | Compose `up` + `/healthz` probe job (optional nightly) | `.github/workflows/stack-smoke.yml` | REM-005 | no | All services 200 | M |
| REM-129 | — | digisearch | Add `make test-unit` digisearch to component routing doc | `docs/agents/COMPONENT_ROUTING.md` | — | yes | doc accurate | S |
| REM-130 | — | olympus | Add Olympus to `make test-unit` or document npm-only | `Makefile`, `frontend/olympus/package.json` | REM-038 | yes | Documented command | S |
| REM-131 | — | security | Run security-reviewer subagent on auth delta | PR | REM-005–019,010 | no | Written sign-off in PR | S |
| REM-132 | — | quant | grep CI gate: no pandas outside Nautilus boundary | `scripts/` or CI step | REM-057 | yes | Fails on new pandas imports | M |
| REM-133 | — | digigraph | Add digisearch to e2e seed path smoke | `tests/test_e2e.py` | REM-001,046 | no | e2e ingest/search step | M |
| REM-134 | — | workflows | Manual `workflow_dispatch` dry-run matrix script | `scripts/dry_run_workflows.sh` (new) | REM-006–009 | yes | Script documents local replay | M |
| REM-135 | — | infra | Update `.env.example` for all new env vars | `.env.example` | wave 0–1 | yes | Comment every new var | S |
| REM-136 | — | meta | Post-merge: watch cron health 7 days | runbook | merge | no | All daily workflows green | S |
| REM-137 | — | meta | Close epic + child issues with `Fixes #N` | GitHub | REM-110 | no | Project board updated | S |

---

## 4b. Gap-check subtasks (`REM-138` … `REM-145`)

Sourced from [`2026-06-audit-plan-gap-check.md`](./2026-06-audit-plan-gap-check.md) §5 — subagent findings not fully covered by `AUDIT-*` alone. Add to execution **before or with Wave 0–2** as noted.

| ID | Maps | Title | Wave | Files | Depends | Acceptance | Effort |
|----|------|-------|------|-------|---------|------------|--------|
| **REM-138** | G-01 | Document + enforce auth on DigiGraph MCP `workflow` tool (scope or disable when unauthenticated) | 1 | `digigraph/src/digigraph/mcp_server.py`, `digigraph/ARCHITECTURE.md`, `tests/dg/` | REM-002 | pytest or doc: unauthenticated MCP cannot invoke workflow without scope | M |
| **REM-139** | G-03 | Add `@pytest.mark.unit` to deselected `tests/ds/**` modules | 2 | `tests/ds/*.py` | — | `make test-unit` collects ds tests | S |
| **REM-140** | G-04 | Locate and mark edgar (or named) tests with `@pytest.mark.unit` | 2 | `tests/**` (grep edgar) | — | `pytest --collect-only -m unit` includes edgar suite | S |
| **REM-141** | DOC-02 | Update `ROADMAP.md` revocation / Redis opt-in (with REM-016) | 4 | `ROADMAP.md` | REM-016 | doc-check; matches SECURITY.md | S |
| **REM-142** | DOC-04 | Fix `digiquant/ARCHITECTURE.md` ADDM / drift sections | 4 | `digiquant/ARCHITECTURE.md` | REM-028 | doc-check; ADDM wording matches `addm.py` | S |
| **REM-143** | DOC-05 | Fix `digiclaw/ARCHITECTURE.md` ADDM + auth-blocked vs logic-blocked | 4 | `digiclaw/ARCHITECTURE.md` | REM-074 | doc-check | S |
| **REM-144** | G-05 | Wire `frontend/digichat` into `make test-unit` or documented aggregate target | 2 | `Makefile`, `docs/agents/COMPONENT_ROUTING.md` | — | `make test-unit` runs digichat vitest OR README documents npm-only gate | S |
| **REM-145** | G-06 | Document or dedupe double workflow triggers (`ci.yml` vs path filters) | 2 | `.github/workflows/ci.yml`, `docs/agents/CI_CONVENTIONS.md` | — | doc-check; one trigger path per PR event documented | S |

---

## 5. Test validation matrix

### 5.1 When to run what

| Trigger | Command | Requires stack? | Covers |
|---------|---------|:---------------:|--------|
| After any Python change | `ruff check . && ruff format --check .` | no | style |
| Per-component unit (local) | `pytest tests/dg/ -m unit -v` (replace `dg`→`dq`,`ds`,`dk`,`db`,`dc`,`dsm`) | no | module unit |
| Monorepo unit gate | `make test-unit` | no | all `@pytest.mark.unit` |
| Baseline gate | `make test-baseline` | no | imports/schemas |
| DigiChat | `cd frontend/digichat && npm run lint && npm run test && npm run build` | no | TS/UI |
| Olympus | `cd frontend/olympus && npm run lint && npm run test && npm run build` | no | after REM-038 |
| Digibase integration | `pytest tests/integration/test_request_id_hops.py -v` | partial | REM-069 |
| Contracts | `pytest tests/contracts/ -v` | no | REM-088 |
| Provider review | `pytest tests/provider_review/ -m unit -v` | no | REM-089 |
| E2E | `make up && make test-e2e` | **yes** Docker | REM-046,133 |
| Full local | `make test` | optional e2e | pre-PR |
| Docs/agents | `make doc-check && python scripts/agents_init.py --check` | no | drift |
| Score gate | `make score` | no | REM-109 |
| Coverage (optional) | `make test-cov` | no | digigraph+dq+dsm |
| Compose build | `docker compose build` | no | REM-022,023,070 |
| Heartbeat profile | `make up-heartbeat` + logs | yes | REM-004,073 |
| Cron replay | `scripts/dry_run_workflows.sh` | no | REM-134 |

### 5.2 Per-wave validation minimum

| Wave | Minimum before merge to integration branch |
|------|---------------------------------------------|
| 0 | REM-006–009 local bash replay; `docker compose config`; heartbeat manual |
| 1 | `make test-unit` + targeted `tests/ds`, `tests/dk`, `tests/dg` for touched modules |
| 2 | GHA-equivalent: `make test-baseline`, contracts, provider_review, markers |
| 3 | + `npm run test` both frontends; olympus CI file green on PR |
| 4 | `make doc-check` only |
| 5 | perf tests optional; full `make test` |
| 6 | `make doc-check`; lockfile `npm install` smoke; no `make test` required for gitignore-only |
| 7 | per `2026-06-simplify-deslop-audit.md` when available |

### 5.3 Scheduled workflow verification (post-merge REM-136)

| Workflow | Verify via |
|----------|------------|
| enforce-project-assignment | 7× daily green |
| project-fields-coverage | 7× daily green |
| provider-review | 1× weekly green |
| digiquant-prices intraday | weekday green |
| agent-backlog-snapshot | 1× weekly (or documented defer) |

### 5.5 Maintainer gate without an agent (REM-108)

Epic [#577](https://github.com/digithings-ai/digithings/issues/577) · integration branch `task/577-audit-wave0-remediation` (REM-106–107).

Run from repo root after pulling the remediation branch:

```bash
scripts/dry_run_workflows.sh          # REM-134 — local replay hints
make test-unit && make test-baseline
make doc-check && python3 scripts/agents_init.py --check
ruff check . && ruff format --check .
make score                            # REM-109 — Security≥8 Quality≥8 Opt≥7 Acc≥9
bash scripts/check_pandas_boundary.sh # REM-132
```

Frontends and optional stack: see §5.4 checklist. Post-merge cron watch: [`POST-MERGE-AUDIT-RUNBOOK.md`](./POST-MERGE-AUDIT-RUNBOOK.md) (REM-136–137).

---

### 5.4 Final gate before PR to `develop` (checklist)

- [ ] `make test-unit` — zero failures, zero unintended deselections (`pytest --collect-only -m unit`)
- [ ] `make test-baseline`
- [ ] `make test-e2e` (stack up) OR CI e2e job green on PR
- [ ] `cd frontend/digichat && npm run lint && npm run test && npm run build`
- [ ] `cd frontend/olympus && npm run lint && npm run test && npm run build`
- [ ] `make doc-check`
- [ ] `python scripts/agents_init.py --check`
- [ ] `ruff check .` && `ruff format --check .`
- [ ] `make score` — all dimensions at threshold
- [ ] Human sign-off: digikey (REM-131), embed (REM-010), RLS (REM-035–036), agent workflows (REM-097)
- [ ] PR body: `Fixes #<epic>` + table of `REM-*` completed / deferred
- [ ] No edits under live-trading paths without `Human-Approved-By:` trailer

---

## 6. Agent execution playbook

### 6.1 Coordinator model

1. One **integration coordinator** owns branch, rebase, conflict resolution, and REM-110 checklist.  
2. Up to **8–10 parallel subagents** per batch; never two agents on same file set.  
3. Subagents open commits on task branch; coordinator squash-reorders into logical commits (§1.3).

### 6.2 File ownership map (disjoint paths)

| Owner agent | Path glob | Example REM |
|-------------|-----------|-------------|
| A0-platform | `.github/workflows/*`, `scripts/project_fields.tsv` | 006–009, 044, 087–090 |
| A1-infra | `docker-compose.yml`, `.env.example` | 005, 023, 135 |
| A2-digisearch | `digisearch/**`, `tests/ds/**` | 001, 011, 020–024, 061–065 |
| A3-digigraph | `digigraph/**`, `tests/dg/**` | 002, 012, 025–027, 047, 049–054 |
| A4-digikey | `digikey/**`, `tests/dk/**` | 013–019, 104 |
| A5-digiquant | `digiquant/**`, `tests/dq/**` | 009, 028–031, 055–060, 101–102 |
| A6-digiclaw | `digiclaw/**`, `tests/dc/**` | 004, 072–074 |
| A7-digibase+smith | `digibase/**`, `digismith/**`, `tests/db/**`, `tests/dsm/**` | 039–040, 066–071 |
| A8-digichat | `frontend/digichat/**` | 010, 032–034, 075–079, 105 |
| A9-olympus+design | `frontend/olympus/**`, `frontend/design/**`, `frontend/digithings/**`, `frontend/digiquant/**` | 035–038, 080–083 |
| A10-docs | `**/AGENTS.md`, `**/ARCHITECTURE.md`, `docs/**`, `CLAUDE.md` | 111–126, 096 |
| A11-agents | `agents.yml`, `agents/sources/**` | 091–094, 123 |

### 6.3 Suggested batch schedule (coordinator)

| Batch | Agents | REM set | Notes |
|-------|:------:|---------|-------|
| 1 | A0, A1, A6 | 005–009, 072–073, 006–007 | Wave 0 foundation |
| 2 | A2, A3 | 001–003, 011, 021–024 | Security ingest/MCP |
| 3 | A4, A6 | 004, 013–019 | Auth plane — **human review** |
| 4 | A5, A0 | 028–030, 060, 031, 087–090 | Quant + CI |
| 5 | A8, A9 | 010, 032–034, 037–038, 076–078 | Frontends |
| 6 | A7, A2 | 039–040, 061–065, 066–069 | Shared + search quality |
| 7 | A3, A5, A8 | 047–048, 052, 075, 049–051 | Perf wave 5 |
| 8 | A10, A11 | 091–096, 111–126 | Docs/agents |
| 9 | All | 099–105, 108–110 | P3 + validation |
| 10 | A10 + housekeeping | 138–145 subset, JAN-003–024 | Gap-check + Wave 6 — disjoint from mega-PR |
| 11 | TBD | Wave 7 SIMP/DESLOP | After simplify-deslop audit |

**Conflict hotspots:** `docker-compose.yml` (A1 only), `ci.yml` (A0 only), `digisearch/server.py` (A2 sequential: 001→011→062→065). **Wave 6** owns root `.gitignore` and `package-lock.json` — single agent only.

### 6.4 Subagent prompt template

```text
You own paths: <glob>. Implement REM-XXX only. Branch: task/N-full-audit-remediation.
Do not touch <forbidden globs>. Acceptance: <from plan>. Run: <test command>. Commit message: fix(<component>): <title> (REM-XXX).
```

---

## 7. Out of scope / defer

Items to **exclude from the mega PR** or track as separate issues:

| Item | Reason | Follow-up |
|------|--------|-----------|
| AUDIT-041 / REM-041 | Org GitHub “Actions can create PRs” — not code | Org admin ticket |
| AUDIT-042–043 / REM-042–043 | LLM quota / provider billing | Ops: upgrade Gemini/Ollama limits |
| AUDIT-058 full migration | Large pandas→Polars in atlas scripts | Dedicated PR after mega |
| AUDIT-059 full extraction | Hermes/DigiGraph decoupling architecture | Issue + ADR |
| AUDIT-035–036 if BFF chosen | Multi-sprint Supabase auth redesign | Phase 2 PR after threat model ADR |
| AUDIT-012 full container sandbox | May land minimal hardening only in mega | Security epic for container runtime |
| AUDIT-100 if #401 open | Registry wiring depends on product | Link #401 |
| Live-trading paths | Policy | Never in audit PR |
| `projects/` confidential | Policy | N/A |

**Partial inclusion OK:** REM-035 documents public-read threat model without migration; REM-012 disables exec in prod compose + subprocess stub; REM-058 migrates highest-traffic script only.

---

## 8. Master index (REM ↔ AUDIT ↔ Wave)

| REM | AUDIT | Wave | P | Effort | Parallel |
|-----|-------|------|---|--------|----------|
| 001 | 001 | 1 | P0 | L | no |
| 002 | 002 | 1 | P0 | M | yes |
| 003 | 003 | 0 | P0 | S | yes |
| 004 | 004 | 0 | P0 | M | no |
| 005 | 005 | 0 | P0 | M | yes |
| 006 | 006 | 0 | P0 | S | yes |
| 007 | 007 | 0 | P0 | S | yes |
| 008 | 008 | 0 | P0 | S | yes |
| 009 | 009 | 0 | P0 | M | yes |
| 010 | 010 | 1 | P0 | L | no |
| 011 | 011 | 1 | P0 | M | yes |
| 012 | 012 | 1 | P0 | L | yes |
| 013–105 | 013–105 | 1–5 | P1–P3 | per §3 | per §3 |

*Full detail for REM-013–105 in §3 sections above.*

---

## Appendix A — Effort rollup by wave

| Wave | REM count | S | M | L |
|------|----------:|--:|--:|--:|
| 0 | 12 | 8 | 4 | 0 |
| 1 | 38 | 10 | 22 | 6 |
| 2 | 28 | 14 | 12 | 2 |
| 3 | 15 | 6 | 7 | 2 |
| 4 | 22 | 22 | 0 | 0 |
| 5 | 17 | 9 | 6 | 2 |
| Meta | 32 | 24 | 7 | 1 |
| Gap-check | 8 | 6 | 2 | 0 |
| **Total REM** | **145** | **~99** | **~60** | **~13** |
| **JAN (Wave 6)** | **32** | 22 | 8 | 2 |

---

*Plan generated 2026-06-05. Updated with REM-138–145, Wave 6 (janitor), Wave 7 placeholder. Update when deferrals, `2026-06-simplify-deslop-audit.md`, or wave assignments change.*
