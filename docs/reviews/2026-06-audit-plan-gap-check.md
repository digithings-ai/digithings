# June 2026 Audit ↔ Implementation Plan — Gap Check

**Date:** 2026-06-05  
**Inputs:** [`2026-06-full-audit.md`](./2026-06-full-audit.md) (105 `AUDIT-*`, 25 `DOC-*`, phases 0–3) · [`2026-06-full-audit-implementation-plan.md`](./2026-06-full-audit-implementation-plan.md) (137 `REM-*`)  
**Method:** Read-only crosswalk; no application code changed.

---

## Executive summary

| Metric | Result |
|--------|--------|
| **AUDIT → REM mapping** | **105 / 105 (100%)** — strict 1:1 `REM-001` … `REM-105` |
| **DOC-* coverage in REM** | **25 / 25 touched (100%)** — **20** with dedicated REM rows; **5** partial / split across other REM |
| **Extra plan items (no AUDIT row)** | **32** (`REM-106` … `REM-137`) — meta, CI gaps, DOC-only |
| **Raw subagent findings (~297)** | **~35%** elevated to `AUDIT-*`; remainder deduplicated or doc-only |
| **P0 (12 AUDIT items)** | **12 / 12** mapped; **3** need human gate before merge (embed, exec sandbox, Redis/auth) |
| **Deferred in plan §7** | **6** AUDIT rows (041–043, 058 full, 059 full, 100 conditional) — track as follow-up issues |

**Verdict:** The implementation plan is **complete for the master inventory**. Gaps are **(a)** subagent findings never promoted to `AUDIT-*`, **(b)** thin DOC rows (ROADMAP, digiclaw ARCHITECTURE, `tests/ds` markers), and **(c)** ops/org work (REM-041–043) marked defer. **Recommend adding 6–8 REM items** (below) before wave-0 execution.

**Critical gaps before execution**

1. **Unmarked `tests/ds/` + edgar tests** — cited in audit §3 scripts; no `AUDIT-*` or `REM-*`.
2. **DOC-02 `ROADMAP.md`** — only `SECURITY.md` in REM-016; roadmap still understates revocation.
3. **DOC-04 / DOC-05 architecture files** — REM-112 targets `digiquant/AGENTS.md` only; `digiquant/ARCHITECTURE.md` and `digiclaw/ARCHITECTURE.md` ADDM/auth wording not explicit.
4. **DigiGraph MCP `workflow` tool** — bypasses `DigiAuthMiddleware` (audit §3 digigraph); bind fix (REM-002) does not document tool-level auth.
5. **DigiChat in monorepo test gate** — `make test-unit` omission (audit §3 digichat); REM-122 fixes `AGENTS.md` only, not `Makefile`.
6. **Org / quota cron** — REM-041–043 deferred; daily red noise from Atlas may persist through Phase 0.

---

## 1. AUDIT → REM master map

**Legend:** Mapped = **Y** + `REM-NNN` (1:1 per implementation plan §3).

| AUDIT | Mapped | REM | Sev | Module |
|-------|:------:|-----|-----|--------|
| AUDIT-001 | Y | REM-001 | P0 | digisearch |
| AUDIT-002 | Y | REM-002 | P0 | digigraph |
| AUDIT-003 | Y | REM-003 | P0 | digisearch |
| AUDIT-004 | Y | REM-004 | P0 | digiclaw |
| AUDIT-005 | Y | REM-005 | P0 | digikey |
| AUDIT-006 | Y | REM-006 | P0 | workflows |
| AUDIT-007 | Y | REM-007 | P0 | workflows |
| AUDIT-008 | Y | REM-008 | P0 | workflows |
| AUDIT-009 | Y | REM-009 | P0 | digiquant |
| AUDIT-010 | Y | REM-010 | P0 | digichat |
| AUDIT-011 | Y | REM-011 | P0 | digisearch |
| AUDIT-012 | Y | REM-012 | P0 | digigraph |
| AUDIT-013 | Y | REM-013 | P1 | digikey |
| AUDIT-014 | Y | REM-014 | P1 | digikey |
| AUDIT-015 | Y | REM-015 | P1 | digikey |
| AUDIT-016 | Y | REM-016 | P1 | digikey |
| AUDIT-017 | Y | REM-017 | P1 | digikey |
| AUDIT-018 | Y | REM-018 | P1 | digikey |
| AUDIT-019 | Y | REM-019 | P1 | digikey |
| AUDIT-020 | Y | REM-020 | P1 | digisearch |
| AUDIT-021 | Y | REM-021 | P1 | digisearch |
| AUDIT-022 | Y | REM-022 | P1 | digisearch |
| AUDIT-023 | Y | REM-023 | P1 | digisearch |
| AUDIT-024 | Y | REM-024 | P1 | digisearch |
| AUDIT-025 | Y | REM-025 | P1 | digigraph |
| AUDIT-026 | Y | REM-026 | P1 | digigraph |
| AUDIT-027 | Y | REM-027 | P1 | digigraph |
| AUDIT-028 | Y | REM-028 | P1 | digiquant |
| AUDIT-029 | Y | REM-029 | P1 | digiquant |
| AUDIT-030 | Y | REM-030 | P1 | digiquant |
| AUDIT-031 | Y | REM-031 | P1 | digiquant |
| AUDIT-032 | Y | REM-032 | P1 | digichat |
| AUDIT-033 | Y | REM-033 | P1 | digichat |
| AUDIT-034 | Y | REM-034 | P1 | digichat |
| AUDIT-035 | Y | REM-035 | P1 | olympus |
| AUDIT-036 | Y | REM-036 | P1 | olympus |
| AUDIT-037 | Y | REM-037 | P1 | olympus |
| AUDIT-038 | Y | REM-038 | P1 | olympus |
| AUDIT-039 | Y | REM-039 | P1 | digibase |
| AUDIT-040 | Y | REM-040 | P1 | digismith |
| AUDIT-041 | Y | REM-041 | P1 | workflows |
| AUDIT-042 | Y | REM-042 | P1 | workflows |
| AUDIT-043 | Y | REM-043 | P1 | workflows |
| AUDIT-044 | Y | REM-044 | P1 | workflows |
| AUDIT-045 | Y | REM-045 | P1 | tests/CI |
| AUDIT-046 | Y | REM-046 | P1 | tests/CI |
| AUDIT-047 | Y | REM-047 | P1 | digigraph |
| AUDIT-048 | Y | REM-048 | P1 | digiquant |
| AUDIT-049 | Y | REM-049 | P2 | digigraph |
| AUDIT-050 | Y | REM-050 | P2 | digigraph |
| AUDIT-051 | Y | REM-051 | P2 | digigraph |
| AUDIT-052 | Y | REM-052 | P2 | digigraph |
| AUDIT-053 | Y | REM-053 | P2 | digigraph |
| AUDIT-054 | Y | REM-054 | P2 | digigraph |
| AUDIT-055 | Y | REM-055 | P2 | digiquant |
| AUDIT-056 | Y | REM-056 | P2 | digiquant |
| AUDIT-057 | Y | REM-057 | P2 | digiquant |
| AUDIT-058 | Y | REM-058 | P2 | digiquant |
| AUDIT-059 | Y | REM-059 | P2 | digiquant |
| AUDIT-060 | Y | REM-060 | P2 | digiquant |
| AUDIT-061 | Y | REM-061 | P2 | digisearch |
| AUDIT-062 | Y | REM-062 | P2 | digisearch |
| AUDIT-063 | Y | REM-063 | P2 | digisearch |
| AUDIT-064 | Y | REM-064 | P2 | digisearch |
| AUDIT-065 | Y | REM-065 | P2 | digisearch |
| AUDIT-066 | Y | REM-066 | P2 | digibase |
| AUDIT-067 | Y | REM-067 | P2 | digibase |
| AUDIT-068 | Y | REM-068 | P2 | digibase |
| AUDIT-069 | Y | REM-069 | P2 | digibase |
| AUDIT-070 | Y | REM-070 | P2 | digismith |
| AUDIT-071 | Y | REM-071 | P2 | digismith |
| AUDIT-072 | Y | REM-072 | P2 | digiclaw |
| AUDIT-073 | Y | REM-073 | P2 | digiclaw |
| AUDIT-074 | Y | REM-074 | P2 | digiclaw |
| AUDIT-075 | Y | REM-075 | P2 | digichat |
| AUDIT-076 | Y | REM-076 | P2 | digichat |
| AUDIT-077 | Y | REM-077 | P2 | digichat |
| AUDIT-078 | Y | REM-078 | P2 | digichat |
| AUDIT-079 | Y | REM-079 | P2 | digichat |
| AUDIT-080 | Y | REM-080 | P2 | olympus |
| AUDIT-081 | Y | REM-081 | P2 | design |
| AUDIT-082 | Y | REM-082 | P2 | design |
| AUDIT-083 | Y | REM-083 | P2 | landings |
| AUDIT-084 | Y | REM-084 | P2 | landings |
| AUDIT-085 | Y | REM-085 | P2 | tests/CI |
| AUDIT-086 | Y | REM-086 | P2 | tests/CI |
| AUDIT-087 | Y | REM-087 | P2 | tests/CI |
| AUDIT-088 | Y | REM-088 | P2 | tests/CI |
| AUDIT-089 | Y | REM-089 | P2 | tests/CI |
| AUDIT-090 | Y | REM-090 | P2 | tests/CI |
| AUDIT-091 | Y | REM-091 | P2 | agents |
| AUDIT-092 | Y | REM-092 | P2 | agents |
| AUDIT-093 | Y | REM-093 | P2 | agents |
| AUDIT-094 | Y | REM-094 | P2 | agents |
| AUDIT-095 | Y | REM-095 | P2 | config |
| AUDIT-096 | Y | REM-096 | P2 | workflows |
| AUDIT-097 | Y | REM-097 | P2 | workflows |
| AUDIT-098 | Y | REM-098 | P2 | workflows |
| AUDIT-099 | Y | REM-099 | P3 | digigraph |
| AUDIT-100 | Y | REM-100 | P3 | digigraph |
| AUDIT-101 | Y | REM-101 | P3 | digiquant |
| AUDIT-102 | Y | REM-102 | P3 | digiquant |
| AUDIT-103 | Y | REM-103 | P3 | digisearch |
| AUDIT-104 | Y | REM-104 | P3 | digikey |
| AUDIT-105 | Y | REM-105 | P3 | digichat |

**Reverse check:** All `REM-001` … `REM-105` entries in the plan declare `→ AUDIT-NNN` with matching number. No orphan REM in the 1:1 range.

---

## 2. DOC-* → REM coverage

| DOC | Topic | Covered in REM? | Primary REM | Notes |
|-----|-------|:-------------:|-------------|-------|
| DOC-01 | digikey docs deny revocation | Y | REM-013, 014, 015 | — |
| DOC-02 | SECURITY + **ROADMAP** revocation | **Partial** | REM-016 | `ROADMAP.md:27` not named |
| DOC-03 | ADR-0007 status `proposed` | Y | REM-111 | — |
| DOC-04 | digiquant AGENTS ADDM stub | **Partial** | REM-112, 028, 074 | `digiquant/ARCHITECTURE.md` not explicit |
| DOC-05 | digiclaw AGENTS + **ARCHITECTURE** ADDM | **Partial** | REM-074, 112 | ARCHITECTURE + “auth-blocked” narrative thin |
| DOC-06 | HEARTBEAT.md Docker path | Y | REM-072 | — |
| DOC-07 | digigraph `require_scope` per route | Y | REM-113 | — |
| DOC-08 | data_engineer registration gate | Y | REM-114, 049 | — |
| DOC-09 | digisearch `/azure_status` auth | Y | REM-115 | — |
| DOC-10 | FAISS/Pinecone inventory | Y | REM-116 | — |
| DOC-11 | digismith “no Prometheus” | Y | REM-117 | — |
| DOC-12 | healthcheck `/health` vs `/healthz` | Y | REM-117 | — |
| DOC-13 | digibase file inventory | Y | REM-118 | — |
| DOC-14 | tests/README no CI | Y | REM-119 | — |
| DOC-15 | scoring README thresholds | Y | REM-093 | — |
| DOC-16 | CI_CONVENTIONS enforce-project | Y | REM-120, 006 | — |
| DOC-17 | static.yml / Cloudflare deploy | Y | REM-096, 084 | — |
| DOC-18 | deploy-digiquant.yml missing | Y | REM-084 | — |
| DOC-19 | `digi_live_` vs `dgk_live_` | Y | REM-079 | — |
| DOC-20 | digichat README embed claims | Y | REM-121, 010 | — |
| DOC-21 | AGENTS digichat test command | Y | REM-122, 094 | — |
| DOC-22 | agents catalogue orphans | Y | REM-123, 091, 092 | — |
| DOC-23 | LOCAL_STACK ingest | Y | REM-124, 001 | — |
| DOC-24 | Olympus env var name | Y | REM-125 | — |
| DOC-25 | digikey example scope | Y | REM-126 | — |

**DOC coverage score:** 25/25 referenced (**100% touch**); **20/25 fully scoped** (**80%** dedicated or unambiguous).

---

## 3. REM items without AUDIT rows (`REM-106` … `REM-137`)

These are **intentional plan extensions** (meta, CI holes, DOC-only), not mapping failures.

| REM | Purpose |
|-----|---------|
| REM-106–110 | Epic, branch, runbook, `make score`, PR sign-off |
| REM-111–126 | DOC-03 … DOC-25 (see §2) |
| REM-127 | Hook bash tests in GHA (audit §5 matrix, no AUDIT) |
| REM-128 | Compose `/healthz` smoke (audit §5 matrix) |
| REM-129 | COMPONENT_ROUTING digisearch test_cmd |
| REM-130 | Olympus / `make test-unit` documentation |
| REM-131 | security-reviewer sign-off on auth delta |
| REM-132 | pandas grep CI gate (extends AUDIT-057) |
| REM-133 | e2e digisearch ingest smoke |
| REM-134 | workflow dry-run script |
| REM-135 | `.env.example` for new vars |
| REM-136–137 | Post-merge cron watch; close epic |

---

## 4. Subagent findings **not** in AUDIT inventory

Sourced from audit **§3 module tables** and **§5 CI matrix** (~297 raw → 105 `AUDIT-*`). Items below were **not** assigned `AUDIT-NNN` but remain operationally relevant.

| # | Severity | Module | Finding (from subagent synthesis) | Plan coverage today |
|---|----------|--------|-----------------------------------|---------------------|
| G-01 | High | digigraph | MCP **`workflow` tool** invokes graph **without** `DigiAuthMiddleware` (not just `0.0.0.0` bind) | Implicit in REM-002 only — **no explicit REM** |
| G-02 | High | digigraph | No tests for **`optimize_node` / `supervisor_node`** (named separately from hubs/MCP) | Folded into REM-053 generically |
| G-03 | High | tests/CI | **`tests/ds/`** pytest files **unmarked** — deselected by `make test-unit` | **None** (AUDIT-085/086 cover `tests/dk/` only) |
| G-04 | High | tests/CI | **`edgar`** (or related) tests unmarked — deselected | **None** |
| G-05 | Medium | digichat | **`digichat-test.yml` not in `make test-unit`** | REM-122 doc-only; **no Makefile REM** |
| G-06 | Medium | workflows | **Double CI** — path workflows + `ci.yml` both run on some PRs | **None** |
| G-07 | Medium | digiquant | **`digiquant/ARCHITECTURE.md`** ADDM / drift docs stale (DOC-04 scope) | REM-112 → AGENTS only |
| G-08 | Medium | digiclaw | **`digiclaw/ARCHITECTURE.md`** ADDM + auth-blocked narrative (DOC-05) | REM-074 → AGENTS only |
| G-09 | Low | docs | **`ROADMAP.md:27`** revocation understated (DOC-02) | REM-016 → SECURITY only |
| G-10 | Low | digigraph | **`vertical` hub** tools untested (named in §3) | REM-053 bundle |
| G-11 | Low | landings | **Cloudflare Olympus deploy** without monorepo gate | REM-038 partial (CI only) |

**Already captured elsewhere (not gaps):** DigiChat embed (AUDIT-010), execute_python sandbox (AUDIT-012), ingest stub (AUDIT-001), heartbeat JWT (AUDIT-004), hook tests / compose health (REM-127/128), pandas strategies (AUDIT-057/058).

---

## 5. Recommended REM items to add before execution

Add to implementation plan as **`REM-138` … `REM-145`** (or fold into wave-0 batch 1):

| Proposed ID | Maps | Title | Wave | Effort |
|-------------|------|-------|------|--------|
| **REM-138** | G-01 | Document + enforce auth on DigiGraph MCP `workflow` tool (scope or disable when unauthenticated) | 1 | M |
| **REM-139** | G-03 | Add `@pytest.mark.unit` to deselected **`tests/ds/**`** modules | 2 | S |
| **REM-140** | G-04 | Locate and mark **`edgar`** (or named) tests with `@pytest.mark.unit` | 2 | S |
| **REM-141** | DOC-02 | Update **`ROADMAP.md`** revocation / Redis opt-in (with REM-016) | 4 | S |
| **REM-142** | DOC-04 | Fix **`digiquant/ARCHITECTURE.md`** ADDM / drift sections | 4 | S |
| **REM-143** | DOC-05 | Fix **`digiclaw/ARCHITECTURE.md`** ADDM + auth-blocked vs logic-blocked | 4 | S |
| **REM-144** | G-05 | Wire **`frontend/digichat`** into `make test-unit` or documented aggregate target | 2 | S |
| **REM-145** | G-06 | Document or dedupe **double workflow** triggers (`ci.yml` vs path filters) | 2 | S |

**Optional (defer ok):** REM for G-02 explicit supervisor/optimize_node tests; G-11 deploy gate doc in `DEPLOYMENT.md`.

**Do not block Wave 0 on:** REM-041 (org), REM-042–043 (LLM quota) — keep as separate ops tickets per plan §7.

---

## 6. Phase alignment (audit §7 vs plan waves)

| Audit phase | AUDIT IDs (summary) | Plan waves | Gap |
|-------------|---------------------|------------|-----|
| **Phase 0** — broken cron | 006–009, 041, 004, 072–073, 042–043, 044, 096–097 | Wave 0 | 042–043 deferred; 041 org |
| **Phase 1** — security P0/P1 | 001–003, 005, 010–012, 013–027, 032–040 | Wave 0–1 | Human gates 010, 012, 035–036 |
| **Phase 2** — CI depth | 031–033, 038, 045–046, 085–090, 078 | Wave 2–3 | G-03/04/05 need REM-139–144 |
| **Phase 3** — perf/docs/P3 | 047–048, 052, 057–058, 062–065, 076–083, DOC-* | Wave 4–5 | DOC partials §2 |

---

## 7. Deferrals and execution risk

| AUDIT | REM | Plan status | Risk if executed blindly |
|-------|-----|-------------|---------------------------|
| 041 | 041 | Defer §7 — org policy | Weekly snapshot stays red |
| 042–043 | 042–043 | Defer §7 — quota/ops | Atlas cron may stay red |
| 058 | 058 | Partial defer — large pandas migration | Scope creep in mega-PR |
| 059 | 059 | Defer / thin shim | Hermes still coupled to DigiGraph |
| 100 | 100 | Depends on issue #401 | Registry dead code vs wire-up |
| 010 | 010 | Human gate | Wrong embed design shipped |
| 012 | 012 | Human gate — container TBD | False sense of sandbox security |
| 035–036 | 035–036 | Human gate — RLS/BFF | Wrong public-data posture |

---

## 8. Git status — review documents

As of gap-check date (`git status docs/reviews/`):

```
?? docs/reviews/
```

| File | Status |
|------|--------|
| `docs/reviews/2026-06-full-audit.md` | **Untracked** — commit with epic / housekeeping PR |
| `docs/reviews/2026-06-full-audit-implementation-plan.md` | **Untracked** — commit together |
| `docs/reviews/2026-06-audit-plan-gap-check.md` | **Untracked** (this file) |
| `docs/reviews/2026-06-repository-janitor-audit.md` | **Untracked** — 32 `JAN-*`; Wave 6 in implementation plan |

**Note:** Workspace also had other untracked docs (`docs/superpowers/...`) and **modified** workflow files on branch per initial snapshot — not part of `docs/reviews/` but may affect AUDIT-097 (agent workflow renames) before execution.

**Recommendation:** Single doc-only PR (or appendix to audit epic) adding all `docs/reviews/2026-06-*.md` files so agents and humans share one committed baseline before `make task ISSUE=N`.

**Update (same day):** `REM-138` … `REM-145` from §5 are now in [`2026-06-full-audit-implementation-plan.md`](./2026-06-full-audit-implementation-plan.md) §4b; janitor items map to **Wave 6** in that plan.

---

## 9. Coverage rollup

| Layer | Numerator | Denominator | % |
|-------|-----------|-------------|---|
| AUDIT → REM (1:1) | 105 | 105 | **100%** |
| DOC → any REM | 25 | 25 | **100%** touch |
| DOC → dedicated / full REM | 20 | 25 | **80%** |
| P0 AUDIT with REM + acceptance | 12 | 12 | **100%** |
| Subagent-only gaps (§4) with proposed REM | 8 | 11 listed | **73%** after REM-138–145 |
| Plan defer / human gate (needs explicit issue) | 8 | — | Track outside mega-PR |

---

*Gap check generated 2026-06-05. Re-run after editing the implementation plan or adding `AUDIT-106+`.*
