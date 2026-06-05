# Simplify / Deslop Audit — DigiThings Monorepo

**Date:** 2026-06-05  
**Method:** Read-only heuristics (`except Exception`, `dict[str, Any]`, `# noqa`, `pass #`, `find_stale.py`), sampled worst files per module, cross-check vs [`AGENTS.md`](../../AGENTS.md) minimal-comment style.  
**Scope:** Application + agent scripts only — no application code edits in this pass.  
**Related:** [`2026-06-full-audit.md`](./2026-06-full-audit.md), [`2026-06-full-audit-implementation-plan.md`](./2026-06-full-audit-implementation-plan.md)

---

## Executive summary

| Metric | Count |
|--------|------:|
| **SIMP-*** inventory items | 42 |
| **DESLOP-*** inventory items | 38 |
| **Perf** findings (tagged in module tables) | 14 |
| **Reuse** findings (tagged in module tables) | 12 |
| Modules with highest slop density | **digiquant** (tearsheet + atlas scripts), **digigraph** (orchestration + graph), **digisearch** (server + agent pipeline) |
| Modules with lowest slop density | **digibase**, **digismith**, **digikey**, **digiclaw** |

**Wave recommendation:** Schedule as **Wave 7 — simplify/deslop** in a *new* epic/PR series **after** security/remediation Waves 1–4 from the June full audit complete (or after Wave 5 perf items land on `develop`). **Do not fold** into Wave 5 — Wave 5 is already scoped to REM-099…105 (caching, cron, deps). Merging simplify/deslop with security fixes creates merge hell on `digigraph/server.py`, `digisearch/server.py`, `digikey/`, and `frontend/digichat/`.

**Estimated total cleanup effort:** ~18–28 person-days (mostly M/L in digiquant + digigraph; S sweeps elsewhere).

**Tooling:** `python3 scripts/find_stale.py` ran successfully (vulture-style unused symbols); many “unused” FastAPI route handlers are false positives from static analysis — triage before deletion.

---

## Master inventory

### Simplification (`SIMP-*`)

| ID | Module | Path (anchor) | One-line fix |
|----|--------|---------------|--------------|
| SIMP-001 | digigraph | `graph/state.py` + `models.py` | Align `WorkflowState` TypedDict with Pydantic workflow models; drop duplicate optional keys |
| SIMP-002 | digigraph | `graph/research.py:108-142` | Replace per-getter `try/except Exception` with single config load + early return |
| SIMP-003 | digigraph | `orchestration/builtin.py:120-201` | Narrow digisearch tool-fetch failures; avoid bare `pass` fallback schema |
| SIMP-004 | digigraph | `orchestration/registry.py` | Remove or wire `register_mcp_server` / `has_tool` (see REM-100) |
| SIMP-005 | digigraph | `llm.py:185-214` | Split config/YAML failures into typed errors; reduce `dict[str, Any]` on model_modes |
| SIMP-006 | digigraph | `planning/executor.py` | Collapse nested agent-runner try blocks to one boundary |
| SIMP-007 | digigraph | `server.py:243-590` | Map thread/chat errors to `digibase.errors` codes; shrink broad `except Exception` |
| SIMP-008 | digigraph | `workflow.py:42` | Document or remove silent config-load swallow |
| SIMP-009 | digigraph | `agents/*/runner.py` | Shared runner wrapper instead of copy-pasted except+log |
| SIMP-010 | digiquant | `tearsheet.py` (~1.6k lines) | Split HTML builders; replace 16× `except Exception` with typed optional sections |
| SIMP-011 | digiquant | `scripts/atlas/update_tearsheet.py` | Same as SIMP-010; dedupe with library module |
| SIMP-012 | digiquant | `atlas/state.py` | Migrate `dict[str, Any]` segment slots toward phase Pydantic models |
| SIMP-013 | digiquant | `atlas/supabase_io.py` | Typed row models instead of raw dict IO |
| SIMP-014 | digiquant | `data/prices/macro_ingest.py` | Single manifest type; reduce `list[dict[str, Any]]` manifests |
| SIMP-015 | digiquant | `nautilus_runner.py` | Keep pandas boundary; narrow `_infer_bar_period` except to Polars errors |
| SIMP-016 | digiquant | `atlas/phases/_node_factory.py` | Reduce factory indirection if phases share one shape |
| SIMP-017 | digiquant | `hermes/phases/phase7*.py` | Consolidate analyst/debate dict payloads to Hermes schemas |
| SIMP-018 | digisearch | `server.py:66-78` | Move rate-limit globals below imports; module-level `_time` import block |
| SIMP-019 | digisearch | `agent/pipeline.py` | Prefer Pydantic `ResearchTurnState` over TypedDict + `dict[str, Any]` trace |
| SIMP-020 | digisearch | `server.py` (15× `dict[str, Any]`) | Response DTOs for orchestrator invoke/query |
| SIMP-021 | digisearch | `search/_stub.py` | Clarify stub vs real backend dispatch (fail-closed already at startup) |
| SIMP-022 | digibase | `errors.py:62-74` | vulture flags handlers as unused — register via FastAPI app only (document, don’t delete) |
| SIMP-023 | digismith | `trace.py:54-58` | Pin langsmith min version; drop TypeError fallback branch |
| SIMP-024 | digikey | `jwt_verify.py:68-70` | Re-raise as `JwtVerificationError`; avoid log+re-raise duplicate |
| SIMP-025 | digiclaw | `heartbeat_runner.py:58-93` | Split drift stub from heartbeat; explicit exit codes per failure |
| SIMP-026 | digichat | `lib/embed-gate.ts` | Trim block comment header to 2–3 lines (behavior is clear from names) |
| SIMP-027 | digichat | `app/api/chat/route.ts` | Extract tenant/upstream resolution helpers |
| SIMP-028 | olympus | `components/portfolio/*` | Extract shared “fetch lifecycle” hook to cut eslint-disable set-state-in-effect |
| SIMP-029 | olympus | `app/research/ResearchClient.tsx` | Fix exhaustive-deps properly vs disable |
| SIMP-030 | design | `app-shell-terminal/index.js` | Prefer DOM APIs over repeated `innerHTML` where static |
| SIMP-031 | scripts | `score.py` | Already documents heuristics — keep as source of truth for deslop CI |
| SIMP-032 | scripts | `preload-history.py` | Share retry helper with digiquant price scripts |
| SIMP-033 | digiquant | `atlas/testing/simulator.py` | Reduce 20× `dict[str, Any]` for test fixtures |
| SIMP-034 | digigraph | `graph/research_brief.py` | Merge with `research_brief_models.py` flow |
| SIMP-035 | digiquant | `graph/pipeline.py` | Align quant pipeline state with `BacktestResult` refs only |
| SIMP-036 | digisearch | `orchestrator_tools.py` | Mirror digigraph registry pattern (typed tool defs) |
| SIMP-037 | digigraph | `vertical_orchestrator/*_hub.py` | Deduplicate hub invoke/error strings |
| SIMP-038 | digiquant | `scripts/atlas/fetch-macro.py` | Delegate to `macro_ingest` module (6× broad except) |
| SIMP-039 | digiquant | `scripts/atlas/preload-history.py` | Batch Supabase writes vs per-row loops |
| SIMP-040 | digichat | `components/chat-shell.tsx` | Document design-system bridge; avoid duplicating terminal shell |
| SIMP-041 | scripts | `agents_init.py` | No `except Exception` — good; keep complexity in data-driven YAML only |
| SIMP-042 | tests | agent scripts only | Keep broad except in integration probes; narrow unit tests |

### Deslop (`DESLOP-*`)

| ID | Module | Path (anchor) | One-line fix |
|----|--------|---------------|--------------|
| DESLOP-001 | digigraph | `orchestration/builtin.py:130-131` | Remove silent `except Exception: pass` on tool dict fetch |
| DESLOP-002 | digigraph | `orchestration/builtin.py:200-201` | Log or surface `write_search_results` failures |
| DESLOP-003 | digigraph | `formatters/openwebui.py:96` | Replace bare except with format-specific handling |
| DESLOP-004 | digigraph | `digistore.py:104` | Don’t swallow store errors in research path |
| DESLOP-005 | digigraph | `tools/analytics/data_manipulation/_helpers.py` | Two broad excepts — document expected types |
| DESLOP-006 | digigraph | `server.py:404` | `# noqa: BLE001` on chat path — narrow exception types |
| DESLOP-007 | digigraph | `llm.py:422` | `time.sleep` retry — use backoff helper (see Perf) |
| DESLOP-008 | digigraph | `graph/state.py:1-14` | Trim redundant TypedDict docstring vs AGENTS style |
| DESLOP-009 | digiquant | `tearsheet.py:32-33` | Logo load: catch `OSError` only, not `Exception` |
| DESLOP-010 | digiquant | `tearsheet.py` (bulk) | Replace silent section skips with structured “section unavailable” |
| DESLOP-011 | digiquant | `update_tearsheet.py:376` | `pass  # silently skip` — log at warning |
| DESLOP-012 | digiquant | `nautilus_runner.py:437` | `pass  # plotly` — optional import pattern at top |
| DESLOP-013 | digiquant | `atlas/state.py:1-11` | Long module docstring — keep ADR pointer, drop repetition |
| DESLOP-014 | digiquant | `atlas/phases/*.py` | Many unused Pydantic fields (find_stale) — wire or remove from schema |
| DESLOP-015 | digisearch | `server.py:40-63` | Startup backend probe: log azure exception, don’t `pass` |
| DESLOP-016 | digisearch | `search/_stub.py` | Remove dead branches if stub-only in tests |
| DESLOP-017 | digisearch | `ingestion/parsers/*.py` | Consistent parser error types vs `except Exception` |
| DESLOP-018 | digibase | `connectors/notion.py` | Unused `upsert_database_row` — implement or delete |
| DESLOP-019 | digiclaw | `heartbeat_runner.py:68-69` | Drift check silent return — audit_log skip reason |
| DESLOP-020 | digiclaw | `heartbeat_runner.py:29-30` | Redundant `except Exception` after URLError |
| DESLOP-021 | digichat | `embed-gate.ts:1-13` | Shrink banner comment block |
| DESLOP-022 | digichat | `lib/embed-gate.ts:52-62` | Empty catch blocks — add debug hook behind flag |
| DESLOP-023 | olympus | `theme-provider.tsx:58` | eslint-disable set-state-in-effect — hydrate pattern |
| DESLOP-024 | olympus | `PortfolioShellInner.tsx:227-237` | Duplicate URL-sync effects |
| DESLOP-025 | olympus | `GenericDiffDocumentView.tsx` | Triple set-state-in-effect — one data hook |
| DESLOP-026 | design | `typewriter.js:20` | `innerHTML` for cursor — use text node |
| DESLOP-027 | design | `terminal/index.js:111` | `naiveHighlight` + innerHTML — sanitize or use marked |
| DESLOP-028 | design | `quant-native/ticker.js` | Template innerHTML for tickers |
| DESLOP-029 | scripts | `score.py:83-84` | Meta: flags `except Exception: pass` in diffs (good) |
| DESLOP-030 | scripts | `preload-history.py:218` | noqa BLE001 — use typed provider errors |
| DESLOP-031 | scripts | `validate_model_routing.py:203` | Print failure context before exit |
| DESLOP-032 | digiquant | `strategies/__init__.py` | Multiple `# noqa` lazy imports — document in one comment |
| DESLOP-033 | digigraph | `skills/registry.py` | noqa import — align with agents_init generated surface |
| DESLOP-034 | digiquant | `hermes/chain.py:1` | noqa on heavy imports — lazy-load module |
| DESLOP-035 | digisearch | `atlas_ingest.py` | noqa + broad except in ingest path |
| DESLOP-036 | digichat | `byok-settings-panel.tsx:38` | eslint-disable — use key=open reset pattern |
| DESLOP-037 | static | `frontend/digithings`, `digiquant` | Duplicate starfield — consume `@digithings/design` only |
| DESLOP-038 | digigraph | `research_brief_models.py` | Unused models (find_stale) — delete or wire to graph |

---

## Per-module findings

Effort key: **S** = ≤1 day, **M** = 2–4 days, **L** = 5+ days / needs design.

### digigraph/ — effort **L**

Heuristic density: **~35 files** with `except Exception`; **~60 files** with `dict[str, Any]`; `# noqa` in `server.py`, `pipeline_builder.py`, `research_agent.py`.

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `graph/state.py:8-54` | Simplify | M | TypedDict overlaps `models.py`; consolidate or generate from Pydantic |
| `graph/research.py:108-142` | Simplify | M | Four nested config try/except → one loader |
| `graph/research.py:272-557` | Deslop | M | Broad except on research invoke — map to connector errors |
| `orchestration/builtin.py:130-131` | Deslop | H | Silent pass hides DigiSearch outage |
| `orchestration/builtin.py:159-217` | Reuse | M | Duplicates connector invoke patterns in `connectors/digisearch.py` |
| `orchestration/builtin.py:43` | Simplify | M | 43× `dict[str, Any]` in one file — typed tool results |
| `orchestration/registry.py:212,248` | Simplify | S | Dead `has_tool` / `register_mcp_server` (REM-100) |
| `llm.py:195-754` | Simplify | M | 6× broad except + 21× Any dict — phase model registry |
| `llm.py:422` | Perf | M | Blocking `time.sleep` in retry loop — async or shared backoff |
| `server.py:243-590` | Simplify | M | Thread API: narrow exceptions, use `json_error_response` |
| `server.py:404` | Deslop | L | noqa BLE001 on hot OpenAI-compat path |
| `planning/executor.py:92-104` | Simplify | M | Nested except identical to agent runners |
| `agents/data_manipulation/runner.py:52+` | Reuse | S | Same pattern as analysis/visualization runners |
| `graph/nodes.py:177` | Perf | S | `time.sleep(0.5)` poll — event-driven or backoff |
| `tools/analytics/execute_python.py:70` | Deslop | S | Unused `frame`/`signum` (find_stale) — rename to `_` |
| `workflow.py:42` | Deslop | M | Silent failure loading workflow profile |

### digiquant/ (incl. atlas/, hermes/, scripts/atlas/) — effort **L**

Heuristic density: **~45 files** `except Exception` (core + scripts); **`tearsheet.py` 16**; **`update_tearsheet.py` 20**; atlas core low except count, high `dict[str, Any]` in `state.py`, `macro_ingest.py`, `simulator.py`.

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `tearsheet.py:32-847` | Deslop | H | 16× `except Exception` — per-section typed errors |
| `tearsheet.py:50-64` | Simplify | M | pandas `iterrows` in equity extract — Polars slice at boundary |
| `scripts/atlas/update_tearsheet.py:67-1017` | Deslop | H | Mirror tearsheet slop; split script vs lib |
| `scripts/atlas/fetch-macro.py` | Reuse | M | Should call `data/prices/macro_ingest.py` only |
| `data/prices/macro_ingest.py:1-50` | Simplify | M | 32× Any dict — `MacroObservation` model |
| `atlas/state.py:55-58` | Simplify | M | `dict[str, dict[str, Any]]` analyst reducer → typed |
| `atlas/state.py:1-11` | Deslop | S | Trim verbose module docstring |
| `atlas/supabase_io.py` | Simplify | M | 14× Any — row schemas |
| `atlas/phases/phase1_altdata.py` + phase2-5 | Deslop | M | find_stale: many unused schema fields |
| `atlas/graph.py:2` | Simplify | S | 2× except — graph compile boundary only |
| `atlas/testing/simulator.py` | Simplify | M | 20× Any dict fixtures |
| `hermes/phases/phase7c_analyst.py:10` | Simplify | M | Typed analyst outputs vs dict |
| `hermes/phases/phase7cd_debate.py:9` | Simplify | M | Same |
| `hermes/chain.py:1` | Deslop | S | noqa import block — lazy imports |
| `hermes/phases/phase9_evolution.py:1` | Simplify | S | Single broad except |
| `nautilus_runner.py:53-54` | Simplify | S | Narrow Polars datetime except |
| `nautilus_runner.py:437` | Deslop | S | plotly optional import at module level |
| `server.py:4` | Simplify | S | Align error handling with digibase |
| `scripts/atlas/preload-history.py:4` | Perf | M | N+1 network — batch price fetch |
| `scripts/atlas/generate-snapshot.py:303` | Deslop | S | `pass  # Fall through` — explicit reason enum |

**Atlas/Hermes high-level:** Core graph code is relatively clean on `except Exception` (atlas 4 files, hermes 2). Slop concentrates in **reporting/tearsheet**, **Supabase IO**, and **atlas scripts** — not phase node logic.

### digisearch/ — effort **M**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `server.py:40-64` | Deslop | H | Startup: swallow Azure config errors |
| `server.py:66-78` | Simplify | S | Mid-file imports after startup hook |
| `server.py` (orchestrator routes) | Simplify | M | 15× `dict[str, Any]` on responses |
| `agent/pipeline.py:20-34` | Simplify | M | TypedDict + Any trace list |
| `agent/pipeline.py:57+` | Simplify | S | node_retrieve except — backend errors |
| `orchestrator_tools.py:9` | Reuse | M | Align tool schema with digigraph registry |
| `indexes/backends/azure_search.py:3` | Deslop | M | 3× broad except — classify Azure SDK |
| `search/_stub.py:3` | Simplify | S | Stub dispatch clarity |
| `embedding/batch.py:2` | Perf | M | Uncached re-embed risk — ensure cache keys (REM-103) |
| `http_client.py:1` | Reuse | S | Should use digibase HTTP helpers consistently |
| `cli.py:1` | Simplify | S | Single broad except on CLI boundary OK |
| `mcp_server.py:1` | Simplify | S | Match digigraph MCP error envelope |
| `core/summarize.py:6` | Simplify | S | Any-heavy summarize payloads |
| `ingestion/web_scrape.py:2` | Perf | M | Sequential fetch — batch where safe |

### digibase/ — effort **S**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `errors.py:62-74` | Simplify | S | “Unused” handlers — document FastAPI registration pattern |
| `connectors/notion.py:41` | Deslop | M | Dead `upsert_database_row` |
| `metrics.py:268` | Deslop | S | Unused `_metrics` helper |
| `http.py:93` | Deslop | S | Unused `_correlation_id` — wire or remove |
| `connectors/base.py:13,22` | Deslop | S | Unused protocol params |
| `otel.py:1` | Reuse | S | Any escape — tighten when otel extra enabled |

### digismith/ — effort **S**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `trace.py:54-58` | Simplify | S | Drop legacy langsmith TypeError fallback |
| `trace.py:48-53` | Deslop | S | `except TypeError` for SDK version — pin dep |
| `config.py:1` | Deslop | S | noqa import |
| `redaction.py:2` | Simplify | S | Any in redactor — TypedDict for span payloads |

### digikey/ — effort **S**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `jwt_verify.py:68-70` | Simplify | S | Log+re-raise → custom exception type |
| `jwt_verify.py:12` | Deslop | S | noqa F401 on JwtOptions |
| `service_middleware.py:1` | Simplify | S | Broad except on verify — fail closed (audit OK) |
| `server.py:42` | Deslop | S | find_stale “unused” routes — false positive |
| `blocklist.py:57` | Deslop | S | `reset_client_cache` test-only — mark `# test helper` |

### digiclaw/ — effort **S**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `heartbeat_runner.py:29-30` | Deslop | M | Redundant Exception after URLError |
| `heartbeat_runner.py:68-69` | Deslop | M | Silent drift check return |
| `heartbeat_runner.py:92-93` | Simplify | S | Reoptimize failures only in audit — OK |
| `audit.py:1` | Simplify | S | Single except — keep fire-and-forget contract |

### frontend/digichat/ — effort **M**

No `any` / `as any` in TS; **~22** `catch (` sites; slop is **comment density** and **eslint-disable** patterns.

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `lib/embed-gate.ts:1-13` | Deslop | S | Over-long file header comment |
| `lib/embed-gate.ts:29-38` | Simplify | S | Nested try for parent.origin — extract helper |
| `lib/embed-gate.ts:52-62` | Deslop | M | Silent localStorage failures |
| `app/api/chat/route.ts:34-80` | Simplify | M | Deep nesting — early return helpers |
| `lib/stream-digigraph-trace.ts:2` | Perf | S | Ensure stream cleanup on client abort |
| `components/chat-shell.tsx:9` | Reuse | S | Document design-system terminal bridge |
| `components/byok-settings-panel.tsx:38` | Deslop | S | eslint-disable set-state-in-effect |
| `lib/ecosystem.ts:2` | Deslop | S | catch — classify SSRF vs network |
| `hooks/use-byok-key.ts:2` | Simplify | S | Consolidate storage access with embed-gate |
| `app/api/byok/test/route.ts:3` | Deslop | S | Multiple catch — shared error mapper |
| package.json | Simplify | S | Unused `zod` (REM-105) |

### frontend/olympus/ — effort **M**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `components/portfolio/PositionDrilldown.tsx:109` | Deslop | M | set-state-in-effect eslint-disable |
| `components/portfolio/GenericDiffDocumentView.tsx:250-281` | Deslop | H | Triple effect-disable — custom hook |
| `components/portfolio/PortfolioShellInner.tsx:227-237` | Deslop | M | Duplicate URL sync effects |
| `app/research/ResearchClient.tsx:197,267` | Deslop | M | exhaustive-deps disable — fix deps |
| `components/theme-provider.tsx:58` | Deslop | S | localStorage hydrate pattern |
| `app/layout.tsx:41` | Deslop | S | `dangerouslySetInnerHTML` for theme — acceptable; document |
| `components/sidebar-settings.tsx:69` | Deslop | S | Portaled panel measure effect |
| `components/portfolio/PerformanceTab.tsx:170` | Deslop | S | deps disable — encode comparableKey |
| `components/app-shell-context.tsx:33` | Reuse | S | Same sidebar width pattern as digichat shell |

### frontend/design/ + static landings — effort **M**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `design/typewriter.js:20` | Deslop | M | innerHTML injection surface for text |
| `design/terminal/index.js:111,131` | Deslop | M | innerHTML + highlight — sanitize |
| `design/app-shell-terminal/index.js:28-269` | Deslop | M | Heavy innerHTML shell — template elements |
| `design/quant-native/ticker.js:24-90` | Deslop | M | Template strings → DOM APIs |
| `digichat/.../chat-shell.tsx:9` | Reuse | S | Intentional mirror of design terminal |
| `digithings/`, `digiquant/` static | Reuse | S | Ensure single design package import (ADR-0009) |
| `design/terminal/index.js:100` | Deslop | S | eslint-disable no-await-in-loop — batch |

### scripts/ + tests/ (agent scripts only) — effort **S**

| Path:line | Cat | Sev | One-line fix |
|-----------|-----|-----|--------------|
| `scripts/score.py:45-89` | Reuse | S | Canonical deslop patterns — wire into CI optional job |
| `scripts/score.py:84` | Deslop | S | Flags silenced exceptions in diff (good) |
| `scripts/preload-history.py:218,334` | Deslop | M | noqa BLE001 — typed errors |
| `scripts/validate_model_routing.py:203` | Deslop | S | Broad except on file read |
| `scripts/validate-provider-keys.py:74` | Deslop | S | Same |
| `scripts/provider_review/probe.py:109` | Deslop | S | Probe script — OK if logs exc |
| `scripts/parse_traceback.py:59` | Deslop | S | `pass` on relative path — comment only |
| `scripts/agents_init.py` | Reuse | S | Clean — no broad except |
| `scripts/reindex_digithings_guide.py:88` | Deslop | S | noqa BLE001 for dry-run |
| `tests/dg/test_concurrency.py:1` | Deslop | S | Test-only broad except — keep |
| `tests/ds/test_logging.py:129` | Deslop | S | `pass  # non-fatal` in test — OK |

**digiquant/scripts/atlas/** (agent-operated): Treat as **part of digiquant L effort** — highest `except Exception` counts in `update_tearsheet.py`, `fetch-macro.py`, `fetch-quotes.py`, `ingest_treasury_curve.py`.

---

## Implementation plan mapping

| Recommendation | Rationale |
|----------------|-----------|
| **New Wave 7 — simplify/deslop** | Orthogonal to security AUDIT items; touches same files but different hunks; lower conflict risk after Waves 1–4 merge |
| **Do not fold into Wave 5** | Wave 5 = REM-099…105 (perf/docs/deps). This audit is code-quality debt, not P3 perf |
| **Optional Wave 7 sub-waves** | 7a digigraph+digisearch, 7b digiquant scripts+tearsheet, 7c frontends, 7d digibase/digikey/digiclaw/digismith |
| **Gate** | Run after `make score` security wave; each 7x PR must still pass `pytest -m unit` + `ruff` |
| **Epic link** | New GitHub issue: “June 2026 simplify/deslop (SIMP/DESLOP)” referencing this doc |

### Suggested REM IDs (if tracking on same epic)

| Proposed REM | Maps | Effort |
|--------------|------|--------|
| REM-138 | SIMP-001…010 digigraph graph+orchestration | L |
| REM-139 | SIMP-010…011 tearsheet split | L |
| REM-140 | SIMP-012…017 atlas/hermes typing | M |
| REM-141 | DESLOP-001…010 digigraph+digiquant silent except | M |
| REM-142 | SIMP-018…021 digisearch DTOs | M |
| REM-143 | DESLOP-021…028 frontend hooks/innerHTML | M |
| REM-144 | SIMP-031…032 scripts dedupe | S |

---

## Appendix: heuristic totals (grep)

| Module | `except Exception` (files) | `dict[str, Any]` (files) | `# noqa` (sample) |
|--------|---------------------------:|-------------------------:|------------------:|
| digigraph | 35 | 57 | 6 |
| digiquant | 39 (+scripts) | 33 | 15+ |
| digisearch | 17 | 19 | 2 |
| digibase | 2 | 0 | 1 |
| digismith | 2 | 0 | 1 |
| digikey | 4 | 0 | 1 |
| digiclaw | 2 | 0 | 0 |
| frontend/digichat | 0 (TS catch ~22 sites) | 0 | 2 |
| frontend/olympus | 0 | 0 | 12+ eslint-disable |
| scripts/*.py | 8 | — | 4 |

---

## Document metadata

| Field | Value |
|-------|-------|
| Path | `docs/reviews/2026-06-simplify-deslop-audit.md` |
| SIMP items | 42 |
| DESLOP items | 38 |
| Modules audited | 11 |
| Application code changed | **None** (read-only audit) |
