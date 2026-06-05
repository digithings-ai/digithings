# Wave 7 — Simplify / Deslop completion

**Branch:** `task/577-audit-wave0-remediation` · [PR #578](https://github.com/digithings-ai/digithings/pull/578)  
**Audit source:** [`2026-06-simplify-deslop-audit.md`](./2026-06-simplify-deslop-audit.md) (42 `SIMP-*` + 38 `DESLOP-*` = **80** items)  
**Date closed:** 2026-06-05

## Summary

| Status | Count |
|--------|------:|
| **Done** | 59 |
| **Partial** | 15 |
| **Deferred** | 0 |
| **N/A** | 6 |
| **Weighted completion** | **83.1%** — `(done + 0.5 × partial) / 80` |

Wave 7 landed in sub-waves **7a–7i** on PR #578 (commits from `10ac4d0e` through wave **7i** atlas IO typing closeout). Largest wins: tearsheet split/deslop, digigraph orchestration and server error narrowing, digisearch server DTOs/probes, shared agent runners, olympus diff hook and theme hydration, design typewriter/ticker DOM safety, wave **7g** atlas phase deslop + straggler closeout, wave **7h** ResearchClient URL-derived `docKey` + design terminal `mountTrustedHtml`/`replaceChildren`, wave **7i** `supabase_io`/`macro_ingest`/`simulator` TypedDict coverage.

Remaining debt concentrates in digigraph `WorkflowState` alignment (`SIMP-001`–`002`), digisearch Pydantic graph migration (`SIMP-019`–`020`), and olympus portfolio URL-sync dedupe (`DESLOP-024`).

## Inventory (80 items)

| ID | Module | Status | Evidence |
|----|--------|--------|----------|
| SIMP-001 | digigraph | partial | `WorkflowState` TypedDict still overlaps `models.py` with `dict[str, Any]` slots — full Pydantic alignment deferred post-merge |
| SIMP-002 | digigraph | partial | `research.py` adds `_load_research_settings()` but config accessors still use `except Exception` |
| SIMP-003 | digigraph | done | `builtin.py` narrows to `_ORCHESTRATOR_CLIENT_ERRORS` and logs manifest/invoke failures |
| SIMP-004 | digigraph | partial | `has_tool` wired in `registry.py`; `register_mcp_server` remains test-only until #401 |
| SIMP-005 | digigraph | done | `llm.py` adds `ChatCompletionMessage` / `ToolDefinition` / `JsonSchemaResponseFormat` TypedDicts for completion payloads |
| SIMP-006 | digigraph | done | `executor.py` collapses to single `_PLAN_STEP_ERRORS` boundary |
| SIMP-007 | digigraph | done | `server.py` maps thread errors via `_THREAD_GRAPH_ERRORS` / `json_error_response` |
| SIMP-008 | digigraph | done | `workflow.py` loads profile with `_PROJECT_CONFIG_ERRORS` fallback, not silent swallow |
| SIMP-009 | digigraph | done | Shared `agents/_common.py` (`run_tool_safe`, `finalize_agent_output`) used by runners |
| SIMP-010 | digiquant | done | `tearsheet.py` split to `tearsheet_charts.py`; broad `except Exception` removed, typed/section fallbacks |
| SIMP-011 | digiquant | done | `update_tearsheet.py` deslopped; warnings replace silent skips, mirrors library patterns |
| SIMP-012 | digiquant | done | `atlas/state.py` TypedDict slots (phase6–9, rebalance rows, `DebateTickerState`); `SegmentPayload.body` stays `dict[str, Any]` |
| SIMP-013 | digiquant | done | `supabase_io.py` — `DocumentRowPayload`, read-row TypedDicts, `Phase7DigestPayload` snapshots |
| SIMP-014 | digiquant | done | `macro_ingest.py` — `MacroObservation` end-to-end; `FredRawObservation`/`FrankfurterRatesPayload`/`FngApiEntry` |
| SIMP-015 | digiquant | done | `nautilus_runner.py` narrows bar-period inference to `_POLARS_DT_ERRORS` |
| SIMP-016 | digiquant | done | `_node_factory.py` trimmed in wave 7g; redundant phase docstrings removed |
| SIMP-017 | digiquant | done | `hermes/state.py` re-exports atlas TypedDict payloads; phase7 state slots typed (phase nodes keep LangGraph `dict` returns) |
| SIMP-018 | digisearch | done | `server.py` reorganized; startup/rate-limit helpers no longer mid-file import block |
| SIMP-019 | digisearch | partial | `ResearchTurnTraceStep` TypedDict added; full Pydantic `ResearchTurnState` deferred |
| SIMP-020 | digisearch | partial | `server.py` adds orchestrator response models but nested fields still `dict[str, Any]` |
| SIMP-021 | digisearch | done | `search/_stub.py` docstring clarifies registry/stub dispatch and fail-closed startup |
| SIMP-022 | digibase | done | `errors.py` documents vulture false-positive handlers (SIMP-022 comment) |
| SIMP-023 | digismith | partial | `trace.py` still has langsmith fallback branch (narrowed, not pinned/dropped) |
| SIMP-024 | digikey | done | `jwt_verify.py` re-raises as `JwtVerificationError` |
| SIMP-025 | digiclaw | partial | `heartbeat_runner.py` adds drift `audit_log` reasons; not split into separate drift module/exit codes |
| SIMP-026 | digichat | done | `embed-gate.ts` header trimmed to short module comment |
| SIMP-027 | digichat | done | `route.ts` delegates auth/upstream to `lib/digigraph-upstream.ts` |
| SIMP-028 | olympus | done | `use-async-data.ts` shared fetch lifecycle; single centralized eslint-disable |
| SIMP-029 | olympus | done | `ResearchClient.tsx` derives `effDate` from URL/state (no date-sync effect); docKey effect has full deps + abort cleanup |
| SIMP-030 | design | partial | `app-shell-terminal/index.js` documents innerHTML contract; static slots not migrated to DOM APIs |
| SIMP-031 | scripts | N/A | Audit says keep `score.py` as deslop CI source of truth |
| SIMP-032 | scripts | done | `scripts/preload-history.py` imports shared `call_with_retry` from digiquant `_utils` |
| SIMP-033 | digiquant | done | `simulator.py` — `FixtureResponse` union, canned seed TypedDicts, state payload re-exports |
| SIMP-034 | digigraph | done | `research_brief_models.py` split; `research_brief.py` imports `parse_brief_from_llm` |
| SIMP-035 | digiquant | done | `graph/pipeline.py` adds `PipelineTraceStep`; trace refs only, no embedded bodies |
| SIMP-036 | digisearch | done | `orchestrator_tools.py` adds `OpenAIToolDict` / `FunctionToolSchema` typed defs |
| SIMP-037 | digigraph | done | `vertical_orchestrator/_common.py` dedupes hub manifest/error handling |
| SIMP-038 | digiquant | N/A | Active path `digiquant prices fetch-macro` delegates to `macro_ingest`; FROZEN `scripts/atlas/fetch-macro.py` out of scope |
| SIMP-039 | digiquant | done | `preload-history.py` batches yfinance + chunked Supabase upserts via `call_with_retry` |
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
| DESLOP-014 | digiquant | N/A | Phase Pydantic fields are intentional LLM schema slots; `find_stale` ≥80% reports no unused symbols in `atlas/phases/` |
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
| DESLOP-027 | design | done | `terminal/index.js` uses `mountTrustedHtml` + `replaceChildren`; highlight via `html-escape.js` |
| DESLOP-028 | design | done | `ticker.js` clears via `replaceChildren()`, not `innerHTML` |
| DESLOP-029 | scripts | N/A | Meta item — `score.py` intentionally flags silenced exceptions |
| DESLOP-030 | scripts | done | `preload-history.py` drops BLE001 noqa; uses typed errors + `call_with_retry` |
| DESLOP-031 | scripts | done | `validate_model_routing.py` prints FAIL context before exit |
| DESLOP-032 | digiquant | done | `strategies/__init__.py` single side-effect import comment + grouped noqa |
| DESLOP-033 | digigraph | partial | `skills/registry.py` noqa side-effect import intentional — registry bootstrap |
| DESLOP-034 | digiquant | partial | `hermes/chain.py` noqa import for docstring linkage — lazy-load deferred |
| DESLOP-035 | digisearch | done | `atlas_ingest.py` broad except/noqa removed in wave 7e |
| DESLOP-036 | digichat | done | `byok-settings-panel.tsx` eslint-disable removed |
| DESLOP-037 | static | partial | `olympus/components/starfield.tsx` duplicates canvas logic vs `@digithings/design/starfield.js` |
| DESLOP-038 | digigraph | done | `ResearchBrief` models wired through `research_brief.py` / `parse_brief_from_llm` |

## REM crosswalk (wave 7 closed gaps)

| REM | Audit mapping | Wave 7 outcome |
|-----|---------------|----------------|
| REM-080 | Olympus `SafeMarkdown` | Done — `LibraryDocumentBody` uses `rehype-sanitize` |
| REM-081 | `ticker.js` innerHTML | Done — `replaceChildren()` clear (wave 7h) |
| REM-082 | `typewriter.js` innerHTML | Done — `textContent` typing |
| REM-014 | digikey ARCHITECTURE blocklist | Done — §6 Redis blocklist (prior wave 4 + doc pass) |
| REM-038 | `olympus-test.yml` in CI | Done — wired in `ci.yml` orchestrator |

## N/A rationale (selected)

| ID | Why N/A |
|----|---------|
| SIMP-038 | CLI `digiquant prices fetch-macro` already calls `macro_ingest`; legacy `scripts/atlas/fetch-macro.py` is FROZEN per PROTECTED-SCRIPTS.md |
| DESLOP-014 | Segment report models keep optional fields for LLM structured output; static `find_stale` cannot prove wiring without runtime graph traces |

Post-merge follow-up for partials: digigraph `WorkflowState` merge, digisearch Pydantic graph state, starfield dedupe, olympus portfolio URL-sync (`DESLOP-024`).
