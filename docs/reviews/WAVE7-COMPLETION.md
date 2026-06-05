# Wave 7 — Simplify / Deslop completion

**Branch:** `task/577-audit-wave0-remediation` · [PR #578](https://github.com/digithings-ai/digithings/pull/578)  
**Audit source:** [`2026-06-simplify-deslop-audit.md`](./2026-06-simplify-deslop-audit.md) (42 `SIMP-*` + 38 `DESLOP-*` = **80** items)  
**Date closed:** 2026-06-05

## Summary

| Status | Count |
|--------|------:|
| **Done** | 50 |
| **Partial** | 19 |
| **Deferred** | 7 |
| **N/A** | 4 |
| **Weighted completion** | **74.4%** — `(done + 0.5 × partial) / 80` |

Wave 7 landed in sub-waves **7a–7h** on PR #578 (`refactor: wave 7h close deferred items`). **7h** closes: SIMP-001/004 N/A comments, `dashboard_digest.load_prefetched_prices`, `html-escape.js` + integrator contract, `research_brief_graph_patch`, olympus `useLibraryDocument` / `useBrushRange`. Remaining debt: `supabase_io` / `macro_ingest` / `fetch-macro` (`SIMP-013`–`014`, `038`), terminal highlight innerHTML, starfield dedupe, PortfolioShell URL tab sync (DESLOP-024).

## Inventory (80 items)

| ID | Module | Status | Evidence |
|----|--------|--------|----------|
| SIMP-001 | digigraph | done | N/A (7h): LangGraph checkpoints need JSON dict slots; HTTP uses `models.py` Pydantic |
| SIMP-002 | digigraph | partial | `research.py` adds `_load_research_settings()` but still uses `except Exception` in config accessors |
| SIMP-003 | digigraph | done | `builtin.py` narrows to `_ORCHESTRATOR_CLIENT_ERRORS` and logs manifest/invoke failures |
| SIMP-004 | digigraph | done | N/A (7h): `register_mcp_server` descriptor-only until #401; `has_tool` guards `run_tool` |
| SIMP-005 | digigraph | done | `llm.py` adds `ChatCompletionMessage` / `ToolDefinition` / `JsonSchemaResponseFormat` TypedDicts for completion payloads |
| SIMP-006 | digigraph | done | `executor.py` collapses to single `_PLAN_STEP_ERRORS` boundary |
| SIMP-007 | digigraph | done | `boundaries.py` + `server.py`/`workflow.py`: `GRAPH_RUNTIME_ERRORS` / `STREAM_SSE_ERRORS` on thread + SSE stream paths |
| SIMP-008 | digigraph | done | `workflow.py` logs `PROJECT_CONFIG_ERRORS` and falls back to `full_stack` (not silent swallow) |
| SIMP-009 | digigraph | done | `agents/_common.py` (`run_tool_safe`, `finalize_agent_output`) on all runners incl. data_engineer |
| SIMP-010 | digiquant | done | `tearsheet.py` split to `tearsheet_charts.py`; broad `except Exception` removed, typed/section fallbacks |
| SIMP-011 | digiquant | done | `dashboard_digest.load_prefetched_prices`; `update_tearsheet.py` delegates digest helpers |
| SIMP-012 | digiquant | done | `atlas/state.py` TypedDict slots (phase6–9, rebalance rows, debate rounds); `SegmentPayload.body` stays `dict[str, Any]` |
| SIMP-013 | digiquant | deferred | `atlas/supabase_io.py` not in wave 7 diff; ~16 `dict[str, Any]` remain |
| SIMP-014 | digiquant | deferred | `data/prices/macro_ingest.py` not touched; manifest typing unchanged |
| SIMP-015 | digiquant | done | `nautilus_runner.py` `_POLARS_DT_ERRORS` + `_TEARSHEET_ERRORS` (tearsheet render boundary) |
| SIMP-016 | digiquant | deferred | `atlas/phases/_node_factory.py` not changed in wave 7 range |
| SIMP-017 | digiquant | done | `hermes/state.py` re-exports atlas TypedDict payloads; phase7 state slots typed (phase modules keep node return `dict` for LangGraph) |
| SIMP-018 | digisearch | done | `server.py` reorganized; startup/rate-limit helpers no longer mid-file import block |
| SIMP-019 | digisearch | partial | `pipeline.py` still `ResearchTurnState` TypedDict + `dict[str, Any]` trace (not Pydantic model) |
| SIMP-020 | digisearch | partial | `server.py` adds orchestrator response models but nested fields still `dict[str, Any]` |
| SIMP-021 | digisearch | done | `search/_stub.py` docstring clarifies registry/stub dispatch and fail-closed startup |
| SIMP-022 | digibase | done | `errors.py` documents vulture false-positive handlers (SIMP-022 comment) |
| SIMP-023 | digismith | partial | `trace.py` still has langsmith fallback branch (narrowed, not pinned/dropped) |
| SIMP-024 | digikey | done | `jwt_verify.py` re-raises as `JwtVerificationError` |
| SIMP-025 | digiclaw | partial | `heartbeat_runner.py` adds drift `audit_log` reasons; not split into separate drift module/exit codes |
| SIMP-026 | digichat | done | `embed-gate.ts` header trimmed to short module comment |
| SIMP-027 | digichat | done | `route.ts` delegates auth/upstream to `lib/digigraph-upstream.ts` |
| SIMP-028 | olympus | done | `use-async-data.ts`, `use-library-document.ts`, `use-brush-range.ts`; portfolio charts + PM shell wired |
| SIMP-029 | olympus | done | `ResearchClient.tsx` + `useLibraryDocument`; URL doc sync without inline fetch |
| SIMP-030 | design | done | `html-escape.js` + `escapeHtml` export; integrator slot contract in `app-shell-terminal` |
| SIMP-031 | scripts | N/A | Audit says keep `score.py` as deslop CI source of truth |
| SIMP-032 | scripts | done | `scripts/preload-history.py` imports shared `call_with_retry` from digiquant `_utils` |
| SIMP-033 | digiquant | deferred | `atlas/testing/simulator.py` not in diff; ~19 `dict[str, Any]` fixtures remain |
| SIMP-034 | digigraph | done | `research_brief_graph_patch()` canonical state keys; builder uses `parse_brief_from_llm` only |
| SIMP-035 | digiquant | partial | `graph/pipeline.py` touched but state/trace still `dict[str, Any]` with node-level broad catches |
| SIMP-036 | digisearch | partial | `orchestrator_tools.py` adds `OpenAIToolDict` alias; not full digigraph-style typed registry |
| SIMP-037 | digigraph | done | `vertical_orchestrator/_common.py` dedupes hub manifest/error handling |
| SIMP-038 | digiquant | deferred | `fetch-macro.py` marked FROZEN; still standalone script, not delegating to `macro_ingest` |
| SIMP-039 | digiquant | done | `scripts/preload-history.py` Polars `select` row build; atlas preload uses vectorized pandas `assign` + chunked upserts |
| SIMP-040 | digichat | done | `chat-shell.tsx` documents `@digithings/design/app-shell-terminal` bridge |
| SIMP-041 | scripts | N/A | Audit says `agents_init.py` already clean — no change required |
| SIMP-042 | tests | N/A | Audit says keep broad except in integration probes |
| DESLOP-001 | digigraph | done | Silent `except Exception: pass` removed from `builtin.py` manifest fetch |
| DESLOP-002 | digigraph | done | `write_search_results` failures logged via `_STORE_ERRORS` warning |
| DESLOP-003 | digigraph | done | `openwebui.py` uses format-specific `(OSError, ValueError, UnicodeError)` handling |
| DESLOP-004 | digigraph | done | `digistore.py` surfaces store errors as `(OSError, json.JSONDecodeError)` |
| DESLOP-005 | digigraph | done | `data_manipulation/_helpers.py` broad excepts replaced with typed tuples |
| DESLOP-006 | digigraph | done | `server.py` BLE001 noqa removed; chat/thread paths use narrowed error tuples |
| DESLOP-007 | digigraph | partial | `llm.py` adds `_sleep_transient_retry` but still uses blocking `time.sleep` |
| DESLOP-008 | digigraph | done | `graph/state.py` docstring trimmed to AGENTS-style one-liner |
| DESLOP-009 | digiquant | done | `tearsheet.py` logo load catches `OSError` only |
| DESLOP-010 | digiquant | done | Tearsheet uses `section_unavailable_html` instead of silent section skips |
| DESLOP-011 | digiquant | done | `update_tearsheet.py` replaces `pass  # silently skip` with `logger.warning` |
| DESLOP-012 | digiquant | done | `nautilus_runner.py` uses top-level `ImportError` for optional plotly path |
| DESLOP-013 | digiquant | done | `atlas/state.py` module docstring shortened to ADR pointer |
| DESLOP-014 | digiquant | deferred | Atlas phase schemas/unused fields not remediated in diff range |
| DESLOP-015 | digisearch | done | `server.py` startup Azure probe logs exception instead of bare `pass` |
| DESLOP-016 | digisearch | partial | `_stub.py` clarified; stub/backend branches largely unchanged |
| DESLOP-017 | digisearch | partial | Some parsers touched; `pdf.py` still has `except Exception` |
| DESLOP-018 | digibase | done | `connectors/notion.py` / `upsert_database_row` absent from tree |
| DESLOP-019 | digiclaw | done | Drift skip now writes `drift_check_skipped` audit event |
| DESLOP-020 | digiclaw | done | `_request` handles `URLError` only; redundant broad except removed |
| DESLOP-021 | digichat | done | `embed-gate.ts` banner reduced to one-line header |
| DESLOP-022 | digichat | done | Storage catches call `logStorageFailure` via `storage-debug.ts` |
| DESLOP-023 | olympus | done | `theme-provider.tsx` hydrates via `useSyncExternalStore` (no set-state disable) |
| DESLOP-024 | olympus | partial | `PortfolioShellInner.tsx` still has separate legacy-tab + URL-sync effects |
| DESLOP-025 | olympus | done | `GenericDiffDocumentView.tsx` uses `useGenericDocumentDiff` hook |
| DESLOP-026 | design | done | `typewriter.js` uses `textContent`, not `innerHTML` |
| DESLOP-027 | design | partial | `terminal/index.js` highlight still uses `innerHTML` on escaped `naiveHighlight` output |
| DESLOP-028 | design | done | `quant-native/ticker.js` builds rows with DOM APIs (`replaceChildren` / `textContent`) |
| DESLOP-029 | scripts | N/A | Meta item — `score.py` intentionally flags silenced exceptions |
| DESLOP-030 | scripts | done | `preload-history.py` drops BLE001 noqa; uses typed errors + `call_with_retry` |
| DESLOP-031 | scripts | done | `validate_model_routing.py` prints FAIL context before exit |
| DESLOP-032 | digiquant | partial | `strategies/__init__.py` grouped noqa imports; not single consolidated lazy-import comment |
| DESLOP-033 | digigraph | partial | `skills/registry.py` noqa side-effect import unchanged |
| DESLOP-034 | digiquant | partial | `hermes/chain.py` noqa import block remains; not lazy-loaded module |
| DESLOP-035 | digisearch | done | `atlas_ingest.py` broad except/noqa removed in wave 7e |
| DESLOP-036 | digichat | done | `byok-settings-panel.tsx` eslint-disable removed |
| DESLOP-037 | static | partial | `olympus/components/starfield.tsx` duplicates canvas logic vs `@digithings/design/starfield.js` |
| DESLOP-038 | digigraph | done | `ResearchBrief` models wired through `research_brief.py` / `parse_brief_from_llm` |

## REM crosswalk (wave 7 closed gaps)

| REM | Audit mapping | Wave 7 outcome |
|-----|---------------|----------------|
| REM-080 | Olympus `SafeMarkdown` | Done — `LibraryDocumentBody` uses `rehype-sanitize` |
| REM-081 | `ticker.js` innerHTML | Done — DOM APIs (wave 7h) |
| REM-082 | `typewriter.js` innerHTML | Done — `textContent` typing |
| REM-014 | digikey ARCHITECTURE blocklist | Done — §6 Redis blocklist (prior wave 4 + doc pass) |
| REM-038 | `olympus-test.yml` in CI | Done — wired in `ci.yml` orchestrator |

Deferred to post-merge follow-up: atlas `supabase_io` / `macro_ingest` typing, Hermes phase7 schemas, `fetch-macro` delegation, terminal highlight DOM migration, starfield dedupe, PortfolioShell duplicate URL-sync effects (DESLOP-024).
