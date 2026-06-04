# DigiThings Full Monorepo Audit — June 2026

**Date:** 2026-06-05  
**Scope:** Read-only synthesis of nine parallel module reviews plus prior monorepo and production-CI deep dives.  
**Sources:** Module subagents (Cursor transcript IDs, not repo paths): `94200ecd`, `c218510f`, `8026d926`, `ee640ea0`, `01c8c7d9`, `881710b2`, `f34bb6cb`, `c830698c`, `9d79f896`.  
**No application code was changed** — this document is the sole deliverable.

---

## 1. Executive summary

1. **MCP servers bind `0.0.0.0` without auth** on DigiGraph (`:8766`) and DigiSearch (`:8767`); tools bypass HTTP middleware and can invoke workflows directly when the port is reachable.
2. **DigiSearch ingest is broken for real backends** — `POST /ingest` writes only to the in-memory stub; Chroma/Azure paths return 200 but data is never queryable; path traversal on ingest accepts any server-readable file.
3. **Most scheduled GitHub workflows are red** for fixable reasons: `printf` flag parsing, missing `claude` CLI, org policy blocking bot PRs, Polars Date/Datetime bug in `compute-technicals`, and LLM rate limits on Atlas cron.
4. **`make score` is policy-only** — enforced on `task/*` via `create_pr.sh` and agent dispatch, but **never runs in GHA**; e2e, integration, baseline, contracts, and provider_review pytest suites are also absent from CI.
5. **DigiKey JWT revocation is implemented** (`blocklist.py`, revoke endpoint) but **docs still say absent**; default Compose never wires `DIGIKEY_BLOCKLIST_REDIS_URL`, so revoke is a no-op and live JWTs survive.
6. **DigiClaw heartbeat is auth-blocked** — drift check and `/run_optimize` require DigiKey scopes but send no `Authorization` header; failures are swallowed silently.
7. **Olympus has no CI** and reads Supabase via public anon key with `USING (true)` RLS on all core tables; ~284 KB committed `dashboard-data.json` ships as a public artifact.
8. **DigiChat embed/auth mismatch** — `/embed` posts to auth-gated `/api/chat` without session; SSRF allowlist has no unit tests and allows single-label hostnames.
9. **LangGraph recompiled every request** in DigiGraph (`workflow.py`) and DigiQuant (`graph/pipeline.py`); model_modes YAML re-read per call — hot-path performance debt.
10. **pandas drift outside Nautilus boundary** — strategies, `data/prices/fetchers.py`, `tearsheet.py`, and ruff-excluded `scripts/atlas/` contradict Polars-only AGENTS rule.

**Bottom line:** Core Python services are reasonably tested and auth-aware at HTTP boundaries, but **production automation, governance, and integration seams** lag application code. Highest ROI: fix broken cron jobs, wire DigiKey blocklist + heartbeat auth, repair DigiSearch ingest, and tighten MCP defaults — mostly without touching business logic.

---

## 2. Severity matrix

Counts are **distinct findings** aggregated across module reviews (doc-only items included where they block operators/agents).

| Module | Critical | High | Medium | Low | **Total** |
|--------|:--------:|:----:|:------:|:---:|:---------:|
| digigraph | 1 | 12 | 18 | 14 | **45** |
| digiquant | 0 | 9 | 16 | 10 | **35** |
| digisearch | 2 | 11 | 17 | 12 | **42** |
| digibase | 0 | 2 | 5 | 4 | **11** |
| digismith | 0 | 1 | 6 | 4 | **11** |
| digikey | 5 | 6 | 4 | 2 | **17** |
| digiclaw | 1 | 3 | 4 | 2 | **10** |
| frontend/digichat | 2 | 8 | 14 | 6 | **30** |
| frontend/olympus + design + landings | 0 | 9 | 14 | 8 | **31** |
| scripts + config + tests + agents | 0 | 4 | 18 | 7 | **29** |
| github/workflows | 0 | 6 | 8 | 6 | **20** |
| **Cross-cutting / doc drift** | — | — | 12 | 8 | **20** |
| **Grand total** | **11** | **71** | **132** | **83** | **~297** |

*Master inventory below consolidates to **105** prioritized, deduplicated action items.*

---

## 3. Module sections (top findings)

### digigraph — `94200ecd`

| Sev | Finding | Location |
|-----|---------|----------|
| **Critical** | `exec()` "sandbox" injects real `__builtins__` when `DIGI_ALLOW_CODE_EXEC=1` — not a security boundary | `tools/analytics/execute_python.py:59-74` |
| **High** | MCP `streamable-http` on `0.0.0.0:8766`, no auth; `workflow` tool bypasses `DigiAuthMiddleware` | `mcp_server.py:193-213` |
| **High** | Thread/checkpoint APIs have no JWT `sub` binding; default `thread_id` is `"default"` | `server.py:290-369`, `workflow.py:126` |
| **High** | `build_workflow_graph()` recompiles LangGraph on every request | `workflow.py:124`, `graph/graph.py:159-197` |
| **High** | No tests for `execute_python`, vertical hubs, MCP server, `optimize_node`/`supervisor_node` | `tests/dg/` gaps |
| **Medium** | Rate limiter trusts spoofed `X-Forwarded-For` | `rate_limit.py:36-39` |
| **Medium** | Streaming uses unbounded queue; no cancel on client disconnect | `server.py:502-595` |
| **Medium** | `data_engineer_agent` registered without `code_execution_allowed()` gate | `orchestration/builtin.py:726-743` |

**CI:** `digigraph-test.yml` runs ruff + unit only; no format check, coverage, or e2e.

---

### digiquant — `c218510f`

| Sev | Finding | Location |
|-----|---------|----------|
| **High** | `GET /check_drift` omits `current_sharpe` — ADDM almost always `implemented=False` | `server.py:228-233` |
| **High** | Drawdown constraint sign mismatch — deep drawdowns may never reject | `constraints.py:20-22`, `nautilus_runner.py:274-295` |
| **High** | `tearsheet_path` accepts absolute paths outside export dir | `nautilus_runner.py:414-420` |
| **High** | Linux CI skips Nautilus — 7 test modules collect-ignored; core quant unverified in merge gate | `digiquant-test.yml`, `tests/dq/conftest.py` |
| **High** | ADDM docs say "stub always false" — `addm.py` implements Z-score drift | `AGENTS.md:45` |
| **Medium** | pandas in strategies, fetchers, tearsheet; ruff-excluded `scripts/atlas/` | multiple |
| **Medium** | Hermes chain hard-depends on `digigraph.graph.pipeline_builder` at runtime | `hermes/chain.py:106-110` |
| **Medium** | `execute_at_open.py` not in scheduled workflows | `scripts/atlas/` |

**CI:** Atlas/Hermes only in path-filtered `atlas-graph-ci.yml`, not in main `ci.yml` orchestrator.

---

### digisearch — `8026d926`

| Sev | Finding | Location |
|-----|---------|----------|
| **Critical** | Ingest calls stub-only `add_chunks()` — production Chroma/Azure never receive writes | `server.py:614`, `search/_stub.py:175-177` |
| **High** | Ingest path traversal — no `DIGISEARCH_INGEST_ROOT` containment | `server.py:591-595` |
| **High** | `workspace_id` accepted but never enforced at query time | `core/models.py:53`, backends |
| **High** | MCP on `0.0.0.0`, silent stub fallback on client failure | `mcp_server.py:212-214`, `:59-70` |
| **High** | Dockerfile omits `[ingestion]` extra; MCP compose build context broken | `Dockerfile:29`, `docker-compose.yml:230-252` |
| **High** | `digisearch_fetch_all` unbounded pagination — DoS vector | `server.py:476-527` |
| **High** | Ingest synchronous, no embedding step before Chroma add | `server.py:582-633` |
| **Medium** | `CHROMA_HOST` startup gate but HTTP client not implemented | `search/_stub.py:67-75` |

**CI:** Strong unit coverage on query/OData; zero ingest round-trip or path-traversal tests.

---

### digibase + digismith — `ee640ea0`

| Sev | Finding | Location |
|-----|---------|----------|
| **High** | Shallow audit redaction — nested secrets pass through | `digibase/audit.py:10-20` |
| **High** | `digibase/otel.py` has zero tests | `otel.py:12-40` |
| **High** | LangSmith redaction silently skipped on older SDK | `digismith/trace.py:54-63` |
| **Medium** | No W3C traceparent on outbound httpx | `digibase/otel.py:34-39` |
| **Medium** | DigiSmith Dockerfile omits `digibase[otel]` | `digismith/Dockerfile:20` |
| **Medium** | `tests/integration/test_request_id_hops.py` not in digibase CI | workflow gap |
| **Low** | ARCHITECTURE stale: file inventory, healthcheck path, "no Prometheus" claim | both ARCHITECTURE.md |

---

### digikey + digiclaw — `01c8c7d9`

| Sev | Finding | Location |
|-----|---------|----------|
| **Critical** | Docs say "no JWT revocation" — code implements ADR-0007 blocklist | `digikey/AGENTS.md:44`, `ARCHITECTURE.md` |
| **Critical** | Compose never sets `DIGIKEY_BLOCKLIST_REDIS_URL` — revoke is no-op | `docker-compose.yml:18-25` |
| **Critical** | DigiClaw heartbeat calls protected DigiQuant routes without JWT | `heartbeat_runner.py:62-93` |
| **High** | BFF session tokens get `jti` but no `JtiIssuedRow` — no revocation path | `digikey/server.py:197-211` |
| **High** | Redis blocklist not repopulated from `jti_issued` on restart | `blocklist.py` |
| **High** | ADDM "stub" doc drift; `HEARTBEAT.md` path wrong for Docker | `digiclaw/AGENTS.md`, `ARCHITECTURE.md` |
| **Medium** | Revoke succeeds in DB but `jtis_invalidated=0` when Redis unset | `digikey/server.py:296-305` |

---

### frontend/digichat — `881710b2`

| Sev | Finding | Location |
|-----|---------|----------|
| **Critical** | `/embed` posts to auth-gated `/api/chat` — broken in production iframe | `embed/page.tsx:114`, `api/chat/route.ts:24-31` |
| **High** | SSRF allowlist permits any single-label hostname; **zero tests** | `lib/ecosystem.ts:53` |
| **High** | `replaceConversationMessages` not transactional — data loss risk | `conversations-repo.ts:123-134` |
| **Medium** | Fresh DigiKey exchange on every chat message | `digigraph-upstream.ts:23-70` |
| **Medium** | Machine key prefix doc drift (`digi_live_` vs `dgk_live_`) | `request-auth.ts:21`, docs |
| **Medium** | No CSP on main app; markdown XSS risk | `chat-panel.tsx:41-42` |
| **Medium** | ~0% API route test coverage (9 handlers) | `src/app/api/**` |

**CI:** `digichat-test.yml` runs lint + vitest + build; not in `make test-unit`.

---

### frontend/olympus + design + static landings — `f34bb6cb`

| Sev | Finding | Location |
|-----|---------|----------|
| **High** | Supabase anon RLS `USING (true)` on all core tables — full public read | `supabase/migrations/001_initial_schema.sql:169-176` |
| **High** | No Olympus workflow in CI; Cloudflare deploys without monorepo gate | `.github/workflows/ci.yml` |
| **High** | Committed `public/dashboard-data.json` (~284 KB) publicly downloadable | `frontend/olympus/public/` |
| **Medium** | ReactMarkdown without `rehype-sanitize` across 7+ library views | `components/library/*` |
| **Medium** | `innerHTML` with unescaped data in design package (ticker, typewriter) | `frontend/design/*.js` |
| **Medium** | Missing `og.png`; relative OG URLs break social previews | `frontend/digithings/index.html` |
| **Medium** | Docs reference missing `deploy-digiquant.yml`; `static.yml` retired | READMEs, ADR-0012 |

---

### scripts + config + tests + agents surface — `c830698c`

| Sev | Finding | Location |
|-----|---------|----------|
| **High** | `make score` never in GHA; PR template honor-system only | `scripts/score.py`, workflows |
| **High** | `tests/test_e2e.py` (8 tests) never in GHA | root tests |
| **High** | Unmarked tests deselected by `-m unit` (scopes, jwt_roundtrip, edgar) | `tests/dk/`, `tests/ds/` |
| **High** | `atlas-graph-ci.yml` path-filtered — atlas/hermes can merge without running | workflow |
| **Medium** | `integration`, `baseline`, `contracts`, `provider_review` pytest never in CI | `tests/` |
| **Medium** | Orphan agent sources: `security-reviewer`, `ci-triage` not in `agents.yml` | `agents/sources/` |
| **Medium** | `docs/scoring/README.md` thresholds disagree with `agents.yml` | scoring docs |
| **Low** | `tests/README.md` still says "no CI workflow committed" | stale |

---

### github/workflows — `9d79f896`

| Sev | Finding | Location |
|-----|---------|----------|
| **High** | `enforce-project-assignment.yml` — 10/10 failure (`printf` treats `- [` as flags) | daily cron |
| **High** | `project-fields-coverage.yml` — 10/10 failure (bad TSV models + `pilot` unbound) | daily cron |
| **High** | `provider-review.yml` — 5/5 failure (`claude: command not found`) | weekly cron |
| **High** | `agent-backlog-snapshot.yml` — 7/7 failure (org blocks bot PRs) | weekly cron |
| **High** | `digiquant-prices.yml` intraday — Polars `is_in` Date vs Datetime | `compute-technicals` |
| **High** | Atlas baseline/delta — LLM `RateLimitError`, 2h timeouts/cancellations | cron |
| **Medium** | `pr-quality-gate.yml` referenced but missing | `ci-failure-triage.yml` |
| **Medium** | Local agent workflow renames not merged to `develop` | git status |

---

## 4. Master actionable inventory

**105 items** — deduplicated, cross-module prioritized.  
**Severity:** P0 = ship blocker / security / broken automation; P1 = high risk; P2 = standards/CI; P3 = backlog.

| ID | Sev | Module | File:line / workflow | Issue | Recommended fix | Effort |
|----|-----|--------|----------------------|-------|-----------------|--------|
| AUDIT-001 | P0 | digisearch | `server.py:614` | Ingest writes stub only; Chroma/Azure never indexed | Route ingest through backend `add()` mirroring query router | L |
| AUDIT-002 | P0 | digigraph | `mcp_server.py:193-213` | MCP on `0.0.0.0:8766` without auth | Default `127.0.0.1`; require gateway auth/TLS | M |
| AUDIT-003 | P0 | digisearch | `mcp_server.py:212-214` | MCP on `0.0.0.0` without auth | Default loopback; document ACL | S |
| AUDIT-004 | P0 | digiclaw | `heartbeat_runner.py:62-93` | No JWT on protected DigiQuant calls | Machine API key + Bearer on drift/optimize | M |
| AUDIT-005 | P0 | digikey | `docker-compose.yml:18-25` | `DIGIKEY_BLOCKLIST_REDIS_URL` never wired | Add Redis + env on DigiKey and consumers | M |
| AUDIT-006 | P0 | workflows | `enforce-project-assignment.yml` | Daily cron 10/10 red — `printf` flag bug | Use `printf '%s\n'` or heredoc for list lines | S |
| AUDIT-007 | P0 | workflows | `project-fields-coverage.yml` | Daily cron 10/10 red — bad TSV + unbound `pilot` | Fix model column values; initialize `pilot` | S |
| AUDIT-008 | P0 | workflows | `provider-review.yml` | Weekly cron 5/5 red — `claude` CLI missing | Use `claude-code-action` or install CLI | S |
| AUDIT-009 | P0 | workflows | `digiquant-prices.yml` | Intraday failing — Polars Date/Datetime `is_in` | Cast types in `compute-technicals` | M |
| AUDIT-010 | P0 | digichat | `embed/page.tsx:114` | Embed posts to auth-gated `/api/chat` | Embed token or block prod embed until designed | L |
| AUDIT-011 | P0 | digisearch | `server.py:591-595` | Ingest path traversal — any readable file | Require `DIGISEARCH_INGEST_ROOT` + resolve containment | M |
| AUDIT-012 | P0 | digigraph | `execute_python.py:59-74` | Broken exec sandbox when code exec enabled | Subprocess/container isolation; keep flag off in prod | L |
| AUDIT-013 | P1 | digikey | `digikey/AGENTS.md:44` | Docs say no revocation; code has blocklist | Rewrite revocation section (opt-in Redis) | S |
| AUDIT-014 | P1 | digikey | `digikey/ARCHITECTURE.md:134` | §6/§11 deny blocklist exists | Update architecture + API surface docs | M |
| AUDIT-015 | P1 | digikey | `ARCHITECTURE.md:222` | Root stack doc stale on revocation | Conditional-revocation wording | S |
| AUDIT-016 | P1 | digikey | `SECURITY.md:167` | Revocation guidance omits Redis blocklist | Point to revoke endpoint when configured | S |
| AUDIT-017 | P1 | digikey | `server.py:296-305` | Revoke no-op when Redis unset | Fail revoke with 503 or require Redis in prod | M |
| AUDIT-018 | P1 | digikey | `server.py:197-211` | BFF session JTIs not tracked | Insert `JtiIssuedRow` for BFF tokens | M |
| AUDIT-019 | P1 | digikey | `blocklist.py` | No Redis repopulation after restart | Startup rehydrate from `jti_issued` | M |
| AUDIT-020 | P1 | digisearch | `core/models.py:53` | `workspace_id` not enforced at query | Per-tenant collection prefix or mandatory filter | L |
| AUDIT-021 | P1 | digisearch | `mcp_server.py:59-70` | Silent stub fallback on MCP failure | Fail closed in production | S |
| AUDIT-022 | P1 | digisearch | `Dockerfile:29` | Missing `[ingestion]` extra | Install `.[azure,chroma,ingestion]` | S |
| AUDIT-023 | P1 | digisearch | `docker-compose.yml:230-252` | MCP build context breaks Dockerfile COPY | Align context with main service | S |
| AUDIT-024 | P1 | digisearch | `server.py:476-527` | Unbounded `digisearch_fetch_all` | Server default cap + hard ceiling | M |
| AUDIT-025 | P1 | digigraph | `server.py:290-369` | Thread APIs lack JWT tenant binding | Prefix `thread_id` with authenticated `sub` | M |
| AUDIT-026 | P1 | digigraph | `workflow.py:126` | Default shared `thread_id` `"default"` | Require explicit session or derive from JWT | M |
| AUDIT-027 | P1 | digigraph | `rate_limit.py:36-39` | Spoofed XFF bypasses rate limit | Implement `DIGI_TRUSTED_PROXIES` | M |
| AUDIT-028 | P1 | digiquant | `server.py:228-233` | `/check_drift` missing Sharpe input | Wire latest Sharpe from backtest/DB | M |
| AUDIT-029 | P1 | digiquant | `constraints.py:20-22` | Drawdown sign mismatch vs Nautilus output | Normalize sign in `_build_result` | M |
| AUDIT-030 | P1 | digiquant | `nautilus_runner.py:414-420` | `tearsheet_path` path escape | Confine under `BACKTEST_RESULTS_DIR` | S |
| AUDIT-031 | P1 | digiquant | `digiquant-test.yml` | Nautilus never on Linux CI | Add `[nautilus]` smoke job on Ubuntu | L |
| AUDIT-032 | P1 | digichat | `lib/ecosystem.ts:53` | SSRF allowlist too permissive | Known service names + env allowlist | M |
| AUDIT-033 | P1 | digichat | `lib/ecosystem.ts` | Zero SSRF unit tests | Table-driven Vitest for allowlist | S |
| AUDIT-034 | P1 | digichat | `conversations-repo.ts:123-134` | Message replace not transactional | Wrap in `db.transaction()` | S |
| AUDIT-035 | P1 | olympus | `001_initial_schema.sql:169-176` | Anon read all tables | Auth + scoped RLS or document public model | L |
| AUDIT-036 | P1 | olympus | `lib/supabase.ts:4-10` | Anon key in static export | BFF with auth or accept public threat model | L |
| AUDIT-037 | P1 | olympus | `public/dashboard-data.json` | Committed portfolio artifact public | Remove from git + deploy | S |
| AUDIT-038 | P1 | olympus | CI gap | No Olympus lint/test/build workflow | Add `olympus-test.yml` to `ci.yml` | M |
| AUDIT-039 | P1 | digibase | `audit.py:10-20` | Shallow redaction misses nested secrets | Recursive redaction + tests | M |
| AUDIT-040 | P1 | digismith | `trace.py:54-63` | Redaction skipped silently on old SDK | Pin langsmith min version; INFO warning | S |
| AUDIT-041 | P1 | workflows | `agent-backlog-snapshot.yml` | Org blocks Actions from opening PRs | Enable org setting or use PAT token input | S |
| AUDIT-042 | P1 | workflows | `atlas-baseline.yml` | Schedule failures — LLM rate limits | Reduce parallelism; upgrade quotas | M |
| AUDIT-043 | P1 | workflows | `atlas-delta.yml` | Timeouts/cancellations at ~2h | Tune timeout; improve idempotency docs | M |
| AUDIT-044 | P1 | workflows | `ci-failure-triage.yml` | References missing `pr-quality-gate.yml` | Remove dead trigger or implement workflow | S |
| AUDIT-045 | P1 | tests/CI | `scripts/score.py` | Scoring gate not in GHA | Add optional PR score job or document gap | M |
| AUDIT-046 | P1 | tests/CI | `tests/test_e2e.py` | 8 e2e tests never in GHA | Compose-up + `pytest -m e2e` job | L |
| AUDIT-047 | P1 | digigraph | `workflow.py:124` | LangGraph recompiled every request | Module-level compiled graph singleton | M |
| AUDIT-048 | P1 | digiquant | `graph/pipeline.py:291` | Same graph recompile on every workflow | Cache compiled graph | M |
| AUDIT-049 | P2 | digigraph | `orchestration/builtin.py:726-743` | `data_engineer_agent` not gated at registration | Add `when: code_execution_allowed()` | S |
| AUDIT-050 | P2 | digigraph | `models.py:48` | ChatCompletionRequest uses `extra="ignore"` | Change to `extra="forbid"` + tests | S |
| AUDIT-051 | P2 | digigraph | `server.py:502-595` | Streaming no cancel/backpressure | Bounded queue + cancel event | M |
| AUDIT-052 | P2 | digigraph | `llm.py` | `model_modes.yaml` re-read per call | Cache with mtime invalidation | S |
| AUDIT-053 | P2 | digigraph | `tests/dg/` | No execute_python / hub / MCP tests | Add security-focused unit tests | M |
| AUDIT-054 | P2 | digigraph | `digigraph-test.yml:31` | No ruff format or coverage | Align with root CI standards | S |
| AUDIT-055 | P2 | digiquant | `nautilus_runner.py:83-88` | `data_path` no root allowlist | Require under `DIGIQUANT_DATA_ROOT` | M |
| AUDIT-056 | P2 | digiquant | `server.py:276` | Job TTL documented but never enforced | Prune stale `_backtest_jobs` | S |
| AUDIT-057 | P2 | digiquant | `AGENTS.md:30,45-46` | pandas boundary docs stale | Update allowlist or migrate code | M |
| AUDIT-058 | P2 | digiquant | `scripts/atlas/*.py` | pandas-heavy; ruff excluded | Migrate to `data/prices` Polars path | L |
| AUDIT-059 | P2 | digiquant | `hermes/chain.py:106-110` | Hard runtime dep on DigiGraph | Extract minimal pipeline builder | L |
| AUDIT-060 | P2 | digiquant | `tests/dq/test_constraints.py:8` | Wrong import path — likely ImportError | Import from `digiquant.constraints` | S |
| AUDIT-061 | P2 | digisearch | `search/_stub.py:67-75` | `CHROMA_HOST` gate but no HTTP client | Implement or remove env var | M |
| AUDIT-062 | P2 | digisearch | `server.py:582-633` | Ingest skips embedding step | Wire `BatchEmbedder` on ingest | M |
| AUDIT-063 | P2 | digisearch | `core/chroma_where.py:36-40` | Filter field names not allowlisted | Enforce index-config allowlist | M |
| AUDIT-064 | P2 | digisearch | `ingestion/web_scrape.py:100-102` | SSRF via scraped hrefs | Host/scheme allowlist | M |
| AUDIT-065 | P2 | digisearch | `tests/ds/` | No ingest round-trip or traversal tests | Add Chroma integration tests | M |
| AUDIT-066 | P2 | digibase | `http.py:93-103` | X-Request-ID missing on unhandled 500 | try/except in middleware | S |
| AUDIT-067 | P2 | digibase | `otel.py:12-40` | Zero OTel tests | Add `tests/db/test_otel.py` | S |
| AUDIT-068 | P2 | digibase | `otel.py:34-39` | No W3C traceparent propagation | Add helper in outbound headers | M |
| AUDIT-069 | P2 | digibase | `tests/integration/` | Request-id hops not in CI | Include in digibase-test job | S |
| AUDIT-070 | P2 | digismith | `Dockerfile:20` | Missing `digibase[otel]` | Install otel extra when OTLP desired | S |
| AUDIT-071 | P2 | digismith | `config.py:31-40` | `langsmith_host_sanitized` untested | Add credential-bearing URL tests | S |
| AUDIT-072 | P2 | digiclaw | `digiclaw/ARCHITECTURE.md:40` | HEARTBEAT.md path wrong for Docker | Fix lookup or copy to workspace root | S |
| AUDIT-073 | P2 | digiclaw | `heartbeat_runner.py:96-103` | Always exit 0 on unhealthy | Return non-zero for orchestration | S |
| AUDIT-074 | P2 | digiclaw | `AGENTS.md:30` | ADDM "stub" wording stale | Match `digiquant/addm.py` behavior | S |
| AUDIT-075 | P2 | digichat | `digigraph-upstream.ts:23-70` | JWT exchange every message | Cache until exp minus skew | M |
| AUDIT-076 | P2 | digichat | `chat-panel.tsx:41-42` | Markdown XSS risk | Add `rehype-sanitize` | S |
| AUDIT-077 | P2 | digichat | `next.config.ts:14-43` | CSP only on embed | Global CSP for main app | M |
| AUDIT-078 | P2 | digichat | `src/app/api/**` | 0% route handler tests | Mock auth/fetch contract tests | M |
| AUDIT-079 | P2 | digichat | `request-auth.ts:21` | `digi_live_` vs `dgk_live_` doc drift | Single glossary in ARCHITECTURE | S |
| AUDIT-080 | P2 | olympus | `components/library/*` | Unsanitized ReactMarkdown (7 files) | Shared `SafeMarkdown` + rehype-sanitize | M |
| AUDIT-081 | P2 | design | `ticker.js:24-28` | innerHTML without escape | textContent or shared escapeHtml | S |
| AUDIT-082 | P2 | design | `typewriter.js:20` | innerHTML for typed text | Use textContent | S |
| AUDIT-083 | P2 | landings | `digithings/index.html:14` | Missing `og.png`; relative OG URLs | Add asset; use absolute URLs | S |
| AUDIT-084 | P2 | landings | READMEs | Reference missing `deploy-digiquant.yml` | Reconcile with Cloudflare `build-digiquant.sh` | S |
| AUDIT-085 | P2 | tests/CI | `tests/dk/test_scopes.py` | Unmarked — deselected by `-m unit` | Add `@pytest.mark.unit` | S |
| AUDIT-086 | P2 | tests/CI | `tests/dk/test_jwt_roundtrip.py` | Unmarked — deselected | Add unit marker | S |
| AUDIT-087 | P2 | tests/CI | `tests/baseline/` | Never in GHA | Add `pytest -m baseline` job | M |
| AUDIT-088 | P2 | tests/CI | `tests/contracts/` | OpenAPI contracts never in CI | Add to digigraph-test | M |
| AUDIT-089 | P2 | tests/CI | `tests/provider_review/` | 14 tests never in GHA | Wire into provider-review workflow | S |
| AUDIT-090 | P2 | tests/CI | `atlas-graph-ci.yml` | Not in `ci.yml` orchestrator | workflow_call or weekly full run | M |
| AUDIT-091 | P2 | agents | `agents/sources/subagents/security-reviewer.md` | Orphan — not in agents.yml | Declare or remove | S |
| AUDIT-092 | P2 | agents | `agents/sources/skills/ci-triage/SKILL.md` | Orphan skill | Declare or remove | S |
| AUDIT-093 | P2 | agents | `docs/scoring/README.md:9-14` | Thresholds disagree with agents.yml | Align Block Merge If text | S |
| AUDIT-094 | P2 | agents | `agents.yml:155` | digichat test_cmd wrong path | Fix to `frontend/digichat` workspace | S |
| AUDIT-095 | P2 | config | `ci.yml:104-105` | Compose validate only — no litellm lint | Run `validate_model_routing.py` | S |
| AUDIT-096 | P2 | workflows | `static.yml` | RETIRED but cited in CLAUDE.md | Update deploy docs to Cloudflare | S |
| AUDIT-097 | P2 | workflows | local vs develop | Agent workflow renames unmerged | Merge renames; update EXECUTION_TIERS | M |
| AUDIT-098 | P2 | workflows | Copilot paths ×3 | Redundant dispatch/review | Consolidate to one path | M |
| AUDIT-099 | P3 | digigraph | `graph/graph.py:49-51` | Default MemorySaver checkpointer | Document Postgres requirement for HA | S |
| AUDIT-100 | P3 | digigraph | `registry.py:248-310` | `register_mcp_server` doesn't register tools | Wire or remove until #401 | S |
| AUDIT-101 | P3 | digiquant | `backtest.py:32-37` | Unbounded SHA-256 cache | LRU/TTL cap | S |
| AUDIT-102 | P3 | digiquant | `execute_at_open.py` | Not in cron | Wire post-market-open schedule | M |
| AUDIT-103 | P3 | digisearch | `embedding/cache.py:32-33` | Cache keys lack model namespace | Prefix with model spec | S |
| AUDIT-104 | P3 | digikey | `ratelimit.py:86-101` | Per-IP not per-key-prefix on token endpoint | Add key-prefix bucket | M |
| AUDIT-105 | P3 | digichat | `package.json:37` | Unused `zod` dependency | Remove or use for validation | S |

---

## 5. CI & scheduled workflow health

Data from `gh run list` on **`digithings-ai/digithings` / `develop`** (2026-06-05). Local tree may have unmerged workflow renames.

| Workflow | Schedule (UTC) | Last 10 runs | Root cause (if red) | Notifications |
|----------|----------------|--------------|---------------------|---------------|
| `scheduled-maintenance.yml` | Mon 08:00 | ✅ all success | — | Issues for some sub-jobs |
| `pip-audit.yml` | Mon 06:00 | ✅ schedule OK | — | Via maintenance overlap |
| `agent-quota-reset.yml` | 1st month 09:00 | ✅ | — | None external |
| `continuous-improvement.yml` | Sun 22:00 | ✅ (1 old Apr failure) | — | Tracker issue |
| `agent-backlog-snapshot.yml` | Mon 06:00 | ❌ 7/7 | Org blocks Actions from opening PRs | None on failure |
| `enforce-project-assignment.yml` | Daily 09:00 | ❌ 10/10 | `printf: - : invalid option` | None |
| `project-fields-coverage.yml` | Daily 06:00 | ❌ 10/10 | Bad TSV model values; `pilot` unbound | None |
| `provider-review.yml` | Sun 00:00 | ❌ 5/5 | `claude: command not found` | Issues from findings step (never reached) |
| `digiquant-prices.yml` | */15 13–20 UTC weekdays; 21:00 EOD | ⚠️ mixed | Polars `is_in` Date vs Datetime in compute-technicals | Issue #563 pattern ✅ |
| `atlas-baseline.yml` | Sat 12:00 | ❌ schedule fails | Gemini/Ollama `RateLimitError` | `ci:failure` issue ✅ |
| `atlas-delta.yml` | Weekdays 12:00 | ❌ latest fail | Timeouts/cancellations ~2h | Comments on #569 ✅ |
| `atlas-monthly.yml` | 28–31 14:00 + guard | ✅ mostly skip | Guard skips non–last-weekday | Issue on real runs ✅ |
| `ci.yml` | PR/push | ✅ (when code OK) | Full monorepo cost every push | Copilot review side effect |
| `digigraph-test.yml` etc. | workflow_call + path | ✅ | Double-run with ci.yml | — |
| `digichat-test.yml` | workflow_call + path | ✅ | — | — |
| **Olympus** | — | **N/A — no workflow** | — | — |
| `static.yml` | dispatch only (RETIRED) | N/A | Replaced by Cloudflare Pages | — |

**PR merge gate coverage (what CI actually enforces):**

| Check | In GHA? |
|-------|---------|
| Per-component ruff + `pytest -m unit` | ✅ via `ci.yml` |
| `pip-audit` HIGH/CRITICAL block | ✅ |
| `doc-check` + `agents_init --check` | ✅ via `docs.yml` |
| `make score` / rubric thresholds | ❌ |
| `pytest -m e2e` | ❌ |
| `pytest -m integration` | ❌ |
| `pytest -m baseline` | ❌ |
| Nautilus backtests on Linux | ❌ |
| Atlas/Hermes graph (unless path hit) | ⚠️ partial |
| Olympus frontend | ❌ |
| Hook bash tests | ❌ |
| Compose `up` + health probes | ❌ |

---

## 6. Doc drift register

Consolidated doc-vs-code mismatches that mislead operators or agents.

| ID | Document | Code reality | Impact |
|----|----------|--------------|--------|
| DOC-01 | `digikey/AGENTS.md:44`, `ARCHITECTURE.md` §6 | `blocklist.py` + revoke endpoint shipped (ADR-0007) | Agents may duplicate or avoid revocation work |
| DOC-02 | `SECURITY.md:167`, `ROADMAP.md:27` | Redis blocklist opt-in | Security reviews underestimate capability |
| DOC-03 | `docs/adr/0007-digikey-revocation.md` status `proposed` | Implemented in tree | ADR process drift |
| DOC-04 | `digiquant/AGENTS.md:45` "ADDM stub" | `addm.py` Z-score implementation | Heartbeat/drift expectations wrong |
| DOC-05 | `digiclaw/AGENTS.md`, `ARCHITECTURE.md` ADDM stub | Same as DOC-04 + auth-blocked not logic-blocked | Operators think re-optimize inert |
| DOC-06 | `digiclaw/docs/HEARTBEAT.md` path | Docker `DIGI_WORKSPACE=/workspace` — file not at root | Checklist gate never fires |
| DOC-07 | `digigraph/AGENTS.md:30` `require_scope` per route | `DigiAuthMiddleware` only | Agent pre-flight wrong |
| DOC-08 | `digigraph/ARCHITECTURE.md:386-387` data_engineer gate | Gate only in execute_python, not registration | Security posture overstated |
| DOC-09 | `digisearch/ARCHITECTURE.md` `/azure_status` public | Middleware requires `digisearch:query` | Integration config errors |
| DOC-10 | `digisearch/ARCHITECTURE.md` FAISS/Pinecone backends | Only Chroma + Azure in repo | Architecture inventory stale |
| DOC-11 | `digismith/ARCHITECTURE.md` "no Prometheus" | `/metrics` via digibase | Observability section wrong |
| DOC-12 | `digismith/ARCHITECTURE.md` healthcheck `/health` | Compose uses `/healthz` | Ops runbook drift |
| DOC-13 | `digibase/ARCHITECTURE.md` "seven source files" | 12+ modules incl. cors, connectors | File map incomplete |
| DOC-14 | `tests/README.md:71-75` "no CI workflow" | Full `ci.yml` + component workflows | Onboarding confusion |
| DOC-15 | `docs/scoring/README.md` Block Merge thresholds | `agents.yml` ≥8/≥8/≥7/≥9 | Scoring gate misapplied |
| DOC-16 | `docs/agents/CI_CONVENTIONS.md` enforce-project resolved | Still 10/10 failing | False confidence |
| DOC-17 | `CLAUDE.md`, `DEPLOYMENT.md` `static.yml` deploy | RETIRED; Cloudflare production | Wrong deploy path |
| DOC-18 | `frontend/digiquant/README.md` `deploy-digiquant.yml` | File absent; `build-digiquant.sh` | Deploy instructions broken |
| DOC-19 | `digichat OPERATIONS.md` `dgk_live_` for BFF | Code uses `digi_live_` for machine auth | Credential confusion |
| DOC-20 | `digichat README.md` unauthenticated embed | `/api/chat` requires session/key | Embed appears supported |
| DOC-21 | `AGENTS.md` digichat `make test-unit` | Makefile pytest-only | Wrong test command |
| DOC-22 | `agents/sources/README.md` catalogue | Missing finish-task, triage, ci-triage, security-reviewer | Agent surface drift |
| DOC-23 | `LOCAL_STACK.md` / seed script | Ingest broken for Chroma (#1) | Local stack docs overpromise |
| DOC-24 | `olympus/README.md` `NEXT_PUBLIC_ATLAS_VERSION` | Code uses `NEXT_PUBLIC_OLYMPUS_VERSION` | Env var typo |
| DOC-25 | `digikey/AGENTS.md:71` example scope `digigraph:run` | Valid scope is `digigraph:workflow` | Copy-paste auth errors |

---

## 7. Suggested remediation phases

### Phase 0 — Broken cron & silent automation (1–2 weeks, mostly S/M effort)

**Goal:** Restore trust in scheduled jobs; stop daily red noise.

| Priority | Items | Owner hint |
|----------|-------|------------|
| Now | AUDIT-006, 007, 008, 009 — printf, TSV, claude CLI, Polars | Platform / digiquant |
| Now | AUDIT-041 — backlog snapshot org PR policy or PAT | Org admin |
| Now | AUDIT-004, 072, 073 — heartbeat auth + exit codes + HEARTBEAT path | digiclaw + digikey |
| Week 2 | AUDIT-042, 043 — Atlas rate limits (quota upgrade or throttle) | digiquant ops |
| Week 2 | AUDIT-044, 096, 097 — dead workflow refs; merge agent renames | Platform |

**Exit criteria:** All daily/weekly maintenance workflows green for 7 consecutive runs; heartbeat completes drift check with auth in Compose profile.

---

### Phase 1 — Security & trust boundaries (2–4 weeks)

**Goal:** Close unauthenticated MCP, broken ingest, auth seams, public data exposure decisions.

| Priority | Items |
|----------|-------|
| P0 security | AUDIT-001, 002, 003, 011, 012 — ingest, MCP bind, path traversal, sandbox |
| Auth plane | AUDIT-005, 013–019 — Redis blocklist, docs, BFF jti, fail-closed revoke |
| DigiSearch tenant | AUDIT-020, 021, 024 — workspace_id, MCP fail-closed, fetch cap |
| DigiGraph isolation | AUDIT-025, 026, 027 — thread binding, rate limit XFF |
| Frontend | AUDIT-010, 032, 033, 035, 036 — embed, SSRF, Supabase RLS decision |
| Shared audit | AUDIT-039, 040 — nested redaction, LangSmith SDK pin |

**Exit criteria:** MCP defaults loopback in Compose; ingest round-trip test passes on Chroma; DigiKey revoke works in dev stack with Redis; embed either works with token or is disabled in prod; Supabase RLS threat model documented or tightened.

---

### Phase 2 — CI & test depth (2–3 weeks)

**Goal:** Merge gate matches production paths; scheduled jobs stay green.

| Priority | Items |
|----------|-------|
| Scoring | AUDIT-045, 093 — score in CI or explicit policy doc |
| E2E / integration | AUDIT-046, 069, 087, 088 — e2e, baseline, contracts, request-id hops |
| Quant engine | AUDIT-031, 090 — Nautilus Linux job; atlas-graph in orchestrator |
| Frontend CI | AUDIT-038, 033, 078 — Olympus workflow; digichat SSRF + route tests |
| Markers | AUDIT-085, 086, 089 — unmarked tests; provider_review pytest |
| Agents surface | AUDIT-091, 092, 094 — orphan cleanup; path fixes |

**Exit criteria:** `pytest -m e2e` job exists (optional manual/secrets); Nautilus smoke on Ubuntu; Olympus in `ci.yml`; zero deselected unit tests in dk/ds.

---

### Phase 3 — Standards, performance & doc hygiene (ongoing)

**Goal:** Polars-only enforcement, hot-path caching, documentation accuracy.

| Priority | Items |
|----------|-------|
| Performance | AUDIT-047, 048, 052, 075 — graph singleton, YAML cache, JWT cache |
| Polars / pandas | AUDIT-057, 058 — strategy migration; shrink atlas script exclude |
| DigiSearch quality | AUDIT-062, 063, 065 — embeddings on ingest; filter allowlist |
| Frontend hardening | AUDIT-076, 077, 080, 081, 082, 083 — sanitize markdown/HTML |
| Docs sweep | DOC-01 through DOC-25 batch PRs by component |
| Backlog P3 | AUDIT-099–105 |

**Exit criteria:** `make doc-check` clean after doc PRs; graph compile once per process; pandas grep CI gate passes outside Nautilus boundary; Olympus SafeMarkdown rolled out.

---

## Appendix: Review methodology

- **Nine module subagents** each read component `AGENTS.md` + `ARCHITECTURE.md`, then targeted line review of `src/`, tests, Docker, and relevant workflows.
- **Prior deep dives** covered monorepo-wide patterns (MCP, SSRF, agent dispatch, pandas drift) and production CI with `gh run list` / `gh run view --log-failed`.
- **Honesty bound:** Not every file was read line-by-line (~400+ Python modules, 41 workflows); findings prioritize security, production paths, and CI gaps. Sampling + grep used for analytics helpers and atlas scripts.
- **No code changes** were made during this audit.

---

*Generated 2026-06-05. For task tracking, map AUDIT-NNN items to GitHub Issues on Project #1 per repo policy.*
