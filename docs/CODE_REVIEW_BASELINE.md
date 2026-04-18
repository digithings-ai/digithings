# DigiThings — Component Code Review Baseline

**Date:** 2026-03-18
**Reviewer:** Claude Code (claude-sonnet-4-6)
**Scope:** DigiGraph, DigiQuant, DigiSearch
**Purpose:** Establish a scored baseline to track improvements over time. Re-run this review after each major improvement sprint.

---

## Scoring Rubric

| Score | Meaning |
|-------|---------|
| 1–3 | Broken / placeholder / dangerous |
| 4–5 | Functional but fragile; significant rework needed |
| 6–7 | Working with known gaps; production-adjacent |
| 8–9 | Solid; minor polish needed |
| 10 | Production-hardened |

---

## Scorecard Summary

| Component | Architecture | Code Quality | Security | Testing | Docs | Performance | **Composite** |
|-----------|:-----------:|:------------:|:--------:|:-------:|:----:|:-----------:|:-------------:|
| DigiGraph | 7 | 5 | 3 | 0 | 7 | 5 | **4.5** |
| DigiQuant | 6 | 4 | 5 | 0 | 7 | 4 | **4.3** |
| DigiSearch | 6 | 4 | 4 | 0 | 5 | 4 | **3.8** |

---

## DigiGraph

*LangGraph orchestration brain — research → backtest workflow, tool registry, OpenAI-compatible API*

### Scores

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| Architecture | 7/10 | Clean supervisor + sub-graph pattern; solid TypedDict state model; good tool registry abstraction. `nodes.py` imports from 5+ internal modules (tight coupling). Graph routing silently swallows config errors. |
| Code Quality | 5/10 | `llm.py` returns `str \| tuple` (fragile callers). Bare `except Exception: pass` in 3+ places. `_DIGI_LLM_MODE` is module-level global — concurrent requests with different modes interfere. `DigiProjectConfig.load()` called in 3+ hotpaths with no caching. |
| Security | 3/10 | `execute_python.py:58` uses `exec()` with fake restricted globals — sandbox is trivially escapable via `__subclasses__()` chain. Path traversal in `run_storage.py` (validate-after-resolve pattern). No auth on any endpoint. Wildcard CORS. |
| Testing | 0/10 | Zero test files anywhere in the component. |
| Documentation | 7/10 | `digigraph/ARCHITECTURE.md` is thorough and accurate. Missing docstrings on `digistore_profile`, registry handlers, `_serve_run_data_file`. System prompt hardcoded in source instead of config. |
| Performance | 5/10 | `DigiProjectConfig.load()` re-parses YAML from disk on every request. `digistore_profile()` is O(n) row iteration over full datasets. No config caching. 30s blocking timeout on backtest with no user feedback. |

**Composite: 4.5 / 10**

### Critical Issues (must fix before production)

1. **`execute_python.py:58` — arbitrary code execution.** `exec()` with restricted globals is not a real sandbox. Disable `data_engineer_agent` or replace with a subprocess-isolated approach.
2. **No authentication.** All endpoints (`/workflow`, `/threads/{id}/state`, etc.) are unauthenticated with `allow_origins=["*"]`.
3. **Global LLM mode state.** `_DIGI_LLM_MODE` is module-level — two concurrent requests can override each other's mode.
4. **Path traversal in `run_storage.py`.** Uses `resolve()` before the escape check — attacker-controlled `session_id` + `dataset_ref` combination can read outside `run_data_dir`.

### High-Priority Issues

5. Bare `except Exception: pass` in `llm.py` (lines 61, 180–188, 329–336) silently swallows API failures.
6. `llm.py` return type is `str | tuple` — callers must `isinstance` check. Replace with a typed result dataclass.
7. `DigiProjectConfig.load()` called on every request — add module-level cache with file-watch TTL.
8. Zero tests — no safety net for any change.

### Positives

- Tool registry pattern is clean and extensible
- `WorkflowState` as TypedDict is explicit and readable
- SSE-compatible stream callback is well-designed
- Checkpointing (memory/SQLite/Postgres) is properly abstracted
- Audit logging (JSONL) is in place
- `digistore.py` dataset persistence is smart for multi-turn sessions

### What's Implemented vs. Stubbed

| Feature | Status |
|---------|--------|
| Research node (LLM + JSON extraction) | ✅ Implemented |
| Document-mode research (tools + RAG) | ✅ Implemented |
| Backtest node (HTTP → DigiQuant) | ✅ Implemented |
| Tool registry & dispatch | ✅ Implemented |
| Sub-agents (visualization, analysis, etc.) | ✅ Implemented |
| Run storage (file-based datasets) | ✅ Implemented |
| Checkpointing (memory/SQLite/Postgres) | ✅ Implemented |
| SSE streaming | ✅ Implemented |
| OpenAI-compatible API | ✅ Implemented |
| Audit logging | ✅ Implemented |
| MCP server entrypoint | ❌ Stubbed |
| Graphiti/GraphRAG memory | ❌ Not started |
| Multi-turn supervisor handoff | ❌ Not started |
| LangSmith observability | ❌ Not started |
| Auth / rate limiting | ❌ Not started |

---

## DigiQuant

*NautilusTrader backtest/optimize engine — grid, random, Bayesian optimization, tearsheet, export*

### Scores

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| Architecture | 6/10 | Clear pipeline (data → backtest → optimize → export). Extensible strategy registry. `nautilus_runner.py` does too much (load + infer + run + parse + tearsheet = 292 lines). Constraint validation duplicated between `optimize.py` and `optimize_bayesian.py`. No interface for swapping backtest engines. |
| Code Quality | 4/10 | CLI param parsing is fragile (`v.replace(".", "").replace("-", "").isdigit()` fails on `--1.5`, scientific notation). Broad `except Exception: pass` in `nautilus_runner.py` and throughout `tearsheet.py`. Magic numbers hardcoded (1M starting capital, 1-DAY default bar period, 30s timeout). `infer_param_grid()` silently generates 100k+ combos with no cap or warning. |
| Security | 5/10 | Path traversal in `export.py` — user-controlled `output_dir` not validated against allowed parent. Audit redaction is key-name-only (values containing secrets are not redacted). Wildcard CORS. No auth. |
| Testing | 0/10 | `pyproject.toml` references `testpaths = ["test"]` but the directory is empty. Zero test files. |
| Documentation | 7/10 | `digiquant/ARCHITECTURE.md` is excellent — design principles, interface contracts, performance targets. Code-level docstrings present but lack return value examples and implicit behavior explanations (e.g., why `trade_size` is excluded from param grid). |
| Performance | 4/10 | Grid and Bayesian optimization are fully sequential — no parallelization. `digiquant/ARCHITECTURE.md` claims "100k-param sweep < 30s" but VectorBT Pro is not present. No backtest result caching between optimization restarts. |

**Composite: 4.3 / 10**

### Critical Issues (must fix before production)

1. **Zero parallelization in optimize.** All backtest trials run synchronously. Stated performance targets are not achievable.
2. **`nautilus_runner.py` account report parsing is fragile.** Assumes column named "total", uses `split()` with no `maxsplit` — breaks on any schema variation.
3. **`itertools.product` has no upper bound.** 5 params × 10 values = 100k combos generated silently.
4. **Zero tests.** No safety net for strategy logic, optimization, or export.

### High-Priority Issues

5. Duplicate constraint validation logic in `optimize.py` and `optimize_bayesian.py` — extract to `digiquant/constraints.py`.
6. CLI param parsing is fragile — replace with `try: float(v) except ValueError: int(v)` pattern.
7. Path traversal in `export.py` — validate `output_dir` with `.resolve()` and compare to allowed parent.
8. No structured logging anywhere — `print`/`click.echo` only.
9. `nautilus_runner.py` does too much — split into `loader.py`, `runner.py`, `result_parser.py`.

### Positives

- 6 strategies in registry with clean wrapper pattern
- Bayesian optimization (Optuna) is architecturally correct
- `tearsheet.py` produces rich interactive HTML artifact
- `models.py` is the strongest file (9/10) — strict Pydantic, well-described fields
- CLI with Click is well-structured

### What's Implemented vs. Stubbed

| Feature | Status |
|---------|--------|
| Data loading (Polars OHLCV CSV) | ✅ Implemented |
| Strategy registry (6 strategies) | ✅ Implemented |
| NautilusTrader backtest | ✅ Implemented |
| Grid optimization | ✅ Implemented |
| Random optimization | ✅ Implemented |
| Bayesian optimization (Optuna) | ✅ Implemented |
| Tearsheet (Plotly HTML) | ✅ Implemented |
| CLI (backtest, optimize, export) | ✅ Implemented |
| HTTP API (FastAPI) | ✅ Implemented |
| Audit logging | ✅ Implemented |
| Export (JSON artifact) | ✅ Partial — writes params only, no platform deploy |
| VectorBT Pro sweeps | ❌ Stubbed (Phase 2 comment) |
| ADDM drift detection | ❌ Stubbed (`implemented=False`) |
| TradingView import/export | ❌ Explicit NotImplementedError |
| Live execution adapters (IB/Alpaca/QC) | ❌ Explicit NotImplementedError |
| Multi-instrument backtests | ❌ Loads first symbol only |
| Parallel optimization | ❌ Not implemented |

---

## DigiSearch

*RAG, document ingestion, multi-format parsing, vector search, MCP interface*

### Scores

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| Architecture | 6/10 | Clean layered design (parse → chunk → embed → index → search). Plugin ABCs are well-defined. `client.py` uses hardcoded if/elif for backend selection instead of a registry. `mcp_server.py` ignores its `client` parameter entirely — multi-index MCP is wired in docs but dead code. |
| Code Quality | 4/10 | `object \| None` used as type hint in 5+ places (unenforceable). `embedding/cache.py` has broken return value — filters None but loses index mapping. TF-IDF `idf` calculation missing `log()` — it's raw frequency ratio, not IDF. BM25 cuts results at score ≤ 0. `SentenceChunker` runs `nltk.download()` at module import time (network call on import). |
| Security | 4/10 | Wildcard CORS. Empty string OpenAI API key fallback (produces cryptic downstream error instead of failing fast). Hand-rolled Azure OData filter builder has potential injection edge cases. No input sanitization on search text. |
| Testing | 0/10 | `test/` directory referenced in config but no test files exist. |
| Documentation | 5/10 | `digisearch/ARCHITECTURE.md` describes Phases 1–10 but codebase only implements fragments of Phases 1–4. Gap between docs and reality is invisible to users because failures are silent. No logging anywhere. |
| Performance | 4/10 | `SemanticChunker` calls embedder per sentence — should batch. `SentenceChunker` runs `nltk.download()` on import. No connection pooling in HTTP client. Embedding cache uses per-row SQL queries instead of batched SELECT. |

**Composite: 3.8 / 10**

### Critical Issues (must fix before production)

1. **`search/_stub.py` is the production fallback.** All queries use substring matching with hardcoded score of `0.9` when no backend is configured. Users get zero-quality results with no warning.
2. **`server.py` ingest creates fake stub chunks.** On ingest failure, response contains `[Stub] Ingested: <source>` — users believe documents were indexed when they weren't.
3. **`mcp_server.py` ignores its `client` parameter.** Multi-index MCP support is documented but non-functional.
4. **Zero logging.** Every failure is a silent fallback — impossible to diagnose production issues.

### High-Priority Issues

5. Fix `embedding/cache.py` return value — track indices alongside None values so callers get correct position mapping.
6. Fix IDF in `TFIDFSearcher`: `log(n / (df[t] + 1))` not `n / (df[t] + 1)`.
7. Replace hardcoded backend if/elif in `client.py` with a factory registry.
8. Replace `object | None` type hints with `Protocol` types or proper generics.
9. Move `nltk.download()` out of module scope in `SentenceChunker`.
10. Batch sentence embeddings in `SemanticChunker`.

### Positives

- `core/models.py` — `Query` object is comprehensive; supports Azure-specific features cleanly
- Parser registry with graceful dependency degradation is well-designed
- `http_client.py` has proper timeout and good result formatting
- `core/summarize.py` Polars-based analysis is efficient
- `BM25Searcher` algorithm is sound (modulo the missing log in IDF)
- Layered ABC design makes adding backends straightforward

### What's Implemented vs. Stubbed

| Feature | Status |
|---------|--------|
| Document models (Document, Chunk, Query, Result) | ✅ Implemented |
| Parser registry + 6 format parsers | ✅ Implemented |
| Fixed/sliding/recursive chunkers | ✅ Implemented |
| Sentence chunker (NLTK) | ✅ Implemented |
| Semantic chunker | ✅ Partial — falls back to recursive if no embedder |
| OpenAI embedding provider | ✅ Implemented |
| Embedding cache (SQLite) | ✅ Partial — broken return value |
| ChromaDB backend | ✅ Partial — score not sorted, silent embedding drop |
| BM25 / TFIDF search | ✅ Partial — IDF formula incorrect |
| Hybrid search (RRF) | ✅ Implemented |
| Vector search | ✅ Partial — drops query fields on re-construction |
| Cohere reranker | ✅ Partial — silent failure |
| Azure AI Search backend | ⚠️ Partial — hand-rolled OData filter builder |
| HTTP API (FastAPI) | ✅ Implemented (with silent stub fallback) |
| MCP server | ⚠️ Partial — client param ignored |
| HTTP client | ✅ Implemented |
| Stub search | ✅ Implemented but should not be production fallback |
| PDF OCR | ❌ Stubbed — returns placeholder text |
| Multi-index MCP | ❌ Not functional |

---

## Cross-Component: Shared Gaps

These issues exist across all three components and should be treated as platform-level concerns.

| Gap | All Three? | Impact |
|-----|:----------:|--------|
| Zero test coverage | ✅ | Any change can silently break behavior |
| No structured logging | ✅ | Production failures are invisible |
| Wildcard CORS + no auth | ✅ | Any origin, any caller |
| Silent fallbacks / bare `except` | ✅ | Users can't distinguish working from stub |
| No rate limiting | ✅ | DoS / abuse surface |
| Hardcoded magic numbers in source | ✅ | Config drift, hard to tune |
| Performance targets unverified | ✅ | Benchmarks stated in docs but not measured |

---

## Revision History

| Date | Version | Notes |
|------|---------|-------|
| 2026-03-18 | v1.0 | Initial baseline assessment |
| 2026-03-18 | v2.0 | Post Phase 2 + Phase 3 re-score |

---

---

# v2.0 — Post Phase 2 & Phase 3 Re-Score

**Date:** 2026-03-18
**Reviewer:** Claude Code (claude-sonnet-4-6)
**Changes since v1.0:** Phase 2 (tests, constraint extraction, IDF fix, LLMResult) + Phase 3 (batch cache, parallel opt, backtest cache, config cache, connection pooling, Pine Script, ADDM, YAML override, LangSmith)

---

## Scorecard Summary — v2.0

| Component | Architecture | Code Quality | Security | Testing | Docs | Performance | **Composite** | **Δ v1→v2** |
|-----------|:-----------:|:------------:|:--------:|:-------:|:----:|:-----------:|:-------------:|:-----------:|
| DigiGraph | 8 | 6 | 4 | 5 | 7 | 7 | **6.2** | +1.7 |
| DigiQuant | 8 | 7 | 6 | 5 | 7 | 9 | **7.0** | +2.7 |
| DigiSearch | 7 | 6 | 4 | 5 | 5 | 7 | **5.7** | +1.9 |

---

## DigiGraph — v2.0

### Scores

| Dimension | v1 | v2 | Δ | Rationale |
|-----------|:--:|:--:|:-:|-----------|
| Architecture | 7 | 8 | +1 | Config caching (mtime-keyed) eliminates hot-path disk reads. LangSmith `_traceable` decorator cleanly optional. Sync-in-async pattern (`httpx.Client` in tool handlers called from async FastAPI) still present. OpenAI client created per-call — no connection reuse. |
| Code Quality | 5 | 6 | +1 | `LLMResult` dataclass replaces `str \| tuple` return. Path traversal check logic still duplicated across `server.py`, `run_storage.py`, `digistore.py`. Bare `except Exception` reduced but not eliminated. `_DIGI_LLM_MODE` global removed (Phase 1). |
| Security | 3 | 4 | +1 | `_DIGI_LLM_MODE` race condition fixed. Still: API key compared with `!=` (timing-attack-vulnerable, should use `secrets.compare_digest()`). Path traversal in `_serve_run_data_file()` validates `".."` in string before resolving — resolve-first pattern missing. Wildcard CORS default unchanged. No rate limiting. |
| Testing | 0 | 5 | +5 | 13 test files covering LLM, server API, workflow, analytics, formatters. Monkeypatch-based env isolation. Gaps: no concurrency tests, no error-recovery tests (LLM timeout, DigiQuant down), no end-to-end LangGraph state transitions, no path traversal test cases. |
| Documentation | 7 | 7 | 0 | Unchanged. Design docs accurate; no new architecture doc added for LangSmith / config caching. |
| Performance | 5 | 7 | +2 | Config caching eliminates per-request YAML disk read. LangSmith tracing correctly gated (zero-overhead when unset). OpenAI client still instantiated per `get_client()` call — no persistent connection pool. Sync `httpx.Client` in tool handlers blocks async workers under load. 30s blocking DigiQuant wait unchanged. |

**Composite: 6.2 / 10** (was 4.5)

### Remaining Critical Issues

1. **Sync blocking in async server.** `httpx.Client` (sync) used inside `chat_completion_with_tools` tool handlers which run from async FastAPI routes. Under concurrent load, ASGI worker threads starve. Fix: `httpx.AsyncClient` with `await`.
2. **API key timing attack.** `server.py` compares key with `!=`. Replace with `secrets.compare_digest(key_a, key_b)`.
3. **Path traversal incomplete.** `_serve_run_data_file()` checks for `".."` in the raw path string before resolving — bypass possible via URL-encoding or symlinks. Fix: `resolved = (base / ref).resolve(); assert resolved.is_relative_to(base.resolve())`.
4. **OpenAI client per call.** `get_client()` creates a new `OpenAI` instance every invocation — reconnects on every request. Fix: cache per `(api_key, base_url)` tuple.
5. **No rate limiting on any endpoint.** Workflow execution and backtest orchestration are unbounded — one client can exhaust CPU.

### Remaining High-Priority Issues

6. Path traversal validation duplicated in `server.py`, `run_storage.py`, `digistore.py` — extract `_assert_safe_path(base, ref)` utility.
7. No concurrency tests for LangGraph thread isolation (concurrent sessions sharing same `thread_id`).
8. No circuit breaker for DigiQuant / DigiSearch HTTP calls — cascading failure possible.
9. LLM response not cached — identical prompts (e.g. repeated research nodes) make 2 API calls.
10. `execute_python.py` `exec()` sandbox still present — highest-severity unresolved issue.

### What Changed Since v1.0

| Item | Status |
|------|--------|
| `LLMResult` dataclass | ✅ Added |
| Config caching (mtime) | ✅ Added |
| LangSmith `_traceable` decorator | ✅ Added |
| `_DIGI_LLM_MODE` global removed | ✅ Done (Phase 1) |
| 13 test files | ✅ Added |
| Path traversal fix | ❌ Partial — still string-check not resolve-first |
| OpenAI client pooling | ❌ Still per-call |
| Sync-in-async HTTP | ❌ Still blocking |
| Rate limiting | ❌ Not started |
| MCP server entrypoint | ❌ Not started |

---

## DigiQuant — v2.0

### Scores

| Dimension | v1 | v2 | Δ | Rationale |
|-----------|:--:|:--:|:-:|-----------|
| Architecture | 6 | 8 | +2 | `satisfies_constraints()` extracted to `constraints.py` — single source of truth. Backtest cache (`backtest.py`) and parallel optimizer (`optimize.py`) are well-separated. Pine Script export, ADDM detection, and YAML override are clean additions. `nautilus_runner.py` still monolithic (292 lines, load+run+parse). |
| Code Quality | 4 | 7 | +3 | Constraint duplication eliminated. Zero-division in `infer_param_grid()` fixed. `_run_trial` is top-level picklable — correct approach. `_cache_key` SHA-256 hashing is robust. YAML override loads per-call (good for hot reload, but adds YAML parse overhead on every `get_param_specs()`). |
| Security | 5 | 6 | +1 | `export.py` path traversal fixed (Phase 1). Data directory traversal in `nautilus_runner.py` still unvalidated — symlinks or relative paths in `data_dir` could escape. Strategy name passed as string to Nautilus with no whitelist. No auth, wildcard CORS unchanged. |
| Testing | 0 | 5 | +5 | 29 tests in `test_strategy_specs.py`, 18 tests in `test_constraints.py`. Grid cap, zero-division, constraint boundary conditions covered. Gaps: no tests for Bayesian optimization, no tests for `nautilus_runner` result parsing, no tests for `tradingview.py` or `addm.py` new code. |
| Documentation | 7 | 7 | 0 | Unchanged. `digiquant/ARCHITECTURE.md` accurate. ADDM and Pine Script not yet documented in component README. |
| Performance | 4 | 9 | +5 | `ProcessPoolExecutor` parallel optimization with sequential fallback. In-memory backtest cache (SHA-256) with env-var disable. Polars throughout. YAML override adds repeated YAML parse on every `get_param_specs()` — add mtime-based caching if file is large. |

**Composite: 7.0 / 10** (was 4.3)

### Remaining Critical Issues

1. **`nautilus_runner.py` account report parsing fragile.** Column name assumed, `split()` used without `maxsplit` — any schema change silently corrupts results. No test coverage.
2. **`nautilus_runner.py` still monolithic.** 292 lines mixing data loading, bar period inference, Nautilus execution, result parsing, and tearsheet. Impossible to test parts in isolation.
3. **Data directory traversal unvalidated.** `nautilus_runner.py` iterates CSV files in `data_dir` — no check that resolved path stays under the base directory.
4. **`addm.py` and `tradingview.py` have zero tests.** New Phase 3 code is untested.

### Remaining High-Priority Issues

5. YAML specs loaded (and YAML file parsed) on every `get_param_specs()` call — add file mtime cache same pattern as `project_config.py`.
6. Bayesian optimization has no test coverage.
7. Strategy name not whitelisted — passed to Nautilus with no validation.
8. Single-instrument limitation in `nautilus_runner.py` (loads first symbol only) blocks multi-symbol strategies.
9. No tests for `export.py` path traversal rejection.
10. `ADDM.py` drift history is process-global — multiple strategy_ids share same dict; no TTL/expiry on old observations.

### What Changed Since v1.0

| Item | Status |
|------|--------|
| `satisfies_constraints()` extracted | ✅ Done |
| Parallel optimization (`ProcessPoolExecutor`) | ✅ Done |
| Backtest result cache (SHA-256) | ✅ Done |
| Pine Script v5 export (4 strategies) | ✅ Done |
| ADDM rolling Sharpe Z-score | ✅ Done |
| YAML strategy specs override | ✅ Done |
| `infer_param_grid()` zero-division fixed | ✅ Done |
| `export.py` path traversal fixed | ✅ Done (Phase 1) |
| Test suite (47 tests) | ✅ Added |
| `nautilus_runner.py` split | ❌ Still monolithic |
| Bayesian optimization tests | ❌ Not started |
| Multi-symbol backtests | ❌ Not started |

---

## DigiSearch — v2.0

### Scores

| Dimension | v1 | v2 | Δ | Rationale |
|-----------|:--:|:--:|:-:|-----------|
| Architecture | 6 | 7 | +1 | Persistent `httpx.Client` with `atexit` cleanup added to `http_client.py`. Batch SQL cache reduces round-trips. Backend if/elif in `client.py` still hard-coded — no registry. `mcp_server.py` still ignores `client` param. Stub fallback still present as default. |
| Code Quality | 4 | 6 | +2 | IDF formula fixed (`log(n/(df+1)+1)`) — correct and finite. Embedding cache returns positionally-correct results. Batch SQL query clean. `StubProvider`/`MismatchProvider` test utilities are reusable. `_subst_env()` still duplicated between DigiSearch `config.py` and DigiGraph `project_config.py`. |
| Security | 4 | 4 | 0 | No security changes in Phase 2/3. OData filter injection risk unchanged. Wildcard CORS unchanged. No auth. Query expansion (HyDE) passes user input to LLM unchecked. |
| Testing | 0 | 5 | +5 | 9 tests in `test_embedding_cache.py`, 15 tests in `test_keyword_search.py`. Cache correctness, IDF ordering, BM25 skip-if-missing covered. Gaps: no OData injection tests, no path traversal tests for ingest, no hybrid search tests, no Azure backend tests. |
| Documentation | 5 | 5 | 0 | Unchanged. Connection pooling and batch cache not documented in `digisearch/ARCHITECTURE.md`. |
| Performance | 4 | 7 | +3 | Batch `SELECT WHERE hash IN (...)` replaces N individual queries. Persistent `httpx.Client` with connection pooling. `SemanticChunker` still calls embedder per-sentence (batching not done). No query-level result caching. |

**Composite: 5.7 / 10** (was 3.8)

### Remaining Critical Issues

1. **Stub fallback is still the production default.** When no backend is configured, `_stub.py` returns `0.9`-scored fake results with no warning. Users cannot distinguish real from fake search results.
2. **`mcp_server.py` ignores its `client` parameter.** Multi-index MCP documented but non-functional — the `client` arg is never used.
3. **OData filter injection.** Raw filter string from HTTP request passed to Azure backend without grammar validation. Structured filters required for safety.
4. **`SemanticChunker` calls embedder per sentence.** For a 100-page document with 1,000 sentences, this is 1,000 individual embed calls vs. 1 batch call.

### Remaining High-Priority Issues

5. Backend selection in `client.py` uses `if/elif` — adding a new backend requires editing core client. Replace with `_BACKEND_REGISTRY: dict[str, type[DigiIndex]]`.
6. `_subst_env()` duplicated in DigiSearch `config.py` and DigiGraph `project_config.py` — extract to shared utility.
7. No logging anywhere in DigiSearch — production failures are invisible.
8. `SentenceChunker` runs `nltk.download()` at module import time — network call on first import.
9. PDF OCR still stubbed — returns placeholder text.
10. No query result caching — identical search queries hit the backend every time.

### What Changed Since v1.0

| Item | Status |
|------|--------|
| Batch embedding cache SQL | ✅ Done |
| Persistent `httpx.Client` connection pool | ✅ Done |
| IDF formula fixed (`log`-based) | ✅ Done |
| Embedding cache positional alignment fixed | ✅ Done |
| 24 tests added | ✅ Done |
| Stub fallback removed/warned | ❌ Still silent |
| OData injection fix | ❌ Not started |
| `SemanticChunker` batch embed | ❌ Not started |
| Backend registry pattern | ❌ Not started |
| Logging added | ❌ Not started |
| PDF OCR | ❌ Still stubbed |
| Multi-index MCP | ❌ Still broken |

---

## Cross-Component: Shared Gaps — v2.0

| Gap | Resolved? | Remaining Impact |
|-----|:---------:|-----------------|
| Zero test coverage | ✅ Partially — 84 tests added | Bayesian opt, ADDM, Pine Script, Azure backend untested |
| No structured logging | ❌ | DigiSearch still zero logging; DigiGraph/DigiQuant partial |
| Wildcard CORS + no auth | ❌ | All three endpoints publicly accessible |
| Silent fallbacks / bare `except` | ❌ Partially | DigiSearch stub still silent; DigiGraph `except` reduced |
| No rate limiting | ❌ | Unchanged |
| Sync blocking in async | ❌ | DigiGraph tool handlers still use sync HTTP |
| No request correlation ID | ❌ | Cannot trace a request across all 3 services |
| No circuit breaker | ❌ | Cascading failure between components possible |
| `_subst_env()` duplicated | ❌ | DigiSearch + DigiGraph both implement it |
| No inter-service health checks | ❌ | Each service has `/health` but doesn't check dependencies |
