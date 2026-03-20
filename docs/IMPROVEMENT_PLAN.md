# DigiThings — Component Improvement Plan

**Based on:** `docs/CODE_REVIEW_BASELINE.md` (v1.0, 2026-03-18)
**Goal:** Raise all three components to composite score ≥ 8.0
**Target score per dimension:** Testing ≥ 8, Security ≥ 7, Code Quality ≥ 7, Architecture ≥ 8, Docs ≥ 8, Performance ≥ 7

---

## Strategy

Work is organized into three phases prioritized by risk:

- **Phase 1 — Safety & Correctness** (blockers; nothing ships without these)
- **Phase 2 — Reliability & Quality** (bring code quality and testing up)
- **Phase 3 — Performance & Completeness** (fulfill the stated spec)

Each phase is broken into component-specific tracks that can be worked in parallel. Cross-component items are listed separately.

---

## Phase 1 — Safety & Correctness

*Goal: Eliminate critical security vulnerabilities, silent failures, and broken functionality. Estimated composite lift: +1.0–1.5 pts.*

### Cross-Component (do first — affects all three)

- [ ] **Add API key middleware** to all three FastAPI apps. A single shared `digiclaw/auth.py` module that reads `DIGI_API_KEY` env var and returns 401 on mismatch. All three servers import and apply it.
- [ ] **Replace wildcard CORS** with an allow-list read from `DIGI_ALLOWED_ORIGINS` env var (default: `["http://localhost:*"]`).
- [ ] **Add structured logging** using Python `logging` module. One `get_logger(name)` utility in each component's `__init__.py`. Every silent `except Exception: pass` block must log at `WARNING` or `ERROR` before continuing.
- [ ] **Add input validation** on all HTTP endpoints — Pydantic models already exist; enforce `ge`/`le` constraints and return HTTP 422 on violation.

### DigiGraph

- [ ] **Disable `data_engineer_agent`** (or gate behind `DIGI_ALLOW_CODE_EXEC=true` env flag). The `exec()` in `execute_python.py` is the highest-severity issue in the entire codebase. If kept, replace with a `subprocess` call with `--restrict-resources` and a hard 5s wall-clock timeout.
- [ ] **Fix path traversal in `run_storage.py`**: Validate each component of `session_id` and `dataset_ref` before joining (`re.fullmatch(r'[a-zA-Z0-9_\-]+', part)`). Test with `../`, `%2e%2e`, and symlink paths.
- [ ] **Fix `_DIGI_LLM_MODE` global state**: Move to a per-request context variable (`contextvars.ContextVar`) or pass explicitly through call chain. Never stored at module level.
- [ ] **Fix `llm.py` return type**: Replace `str | tuple` with a typed dataclass `LLMResult(content: str, tool_calls: list | None)`. Update all callers.

### DigiQuant

- [ ] **Fix path traversal in `export.py`**: After resolving `output_dir`, assert it starts with an allowed export root (`EXPORT_OUTPUT_DIR` env var). Raise `ValueError` if not.
- [ ] **Fix fragile account report parsing in `nautilus_runner.py`**: Don't assume column names or string split format. Use `.get()` with explicit None checks. Log which column was used.
- [ ] **Cap param grid explosion**: In `strategy_specs.py`, add `MAX_GRID_SIZE = 10_000`. Raise `ValueError` with a clear message if `itertools.product` would exceed it.
- [ ] **Fix CLI param parsing in `cli.py`**: Replace the fragile `isdigit()` chain with `try: float(v) except ValueError: try: int(v) except ValueError: v`.

### DigiSearch

- [ ] **Replace stub search with an explicit error**: `search/_stub.py` must not silently return fake `0.9` scores. When no backend is configured, return an empty result set with a `SearchResponse(status="no_backend_configured")` flag — never fake results.
- [ ] **Fix `server.py` ingest stub response**: When ingest fails, return HTTP 503 with `{"error": "backend_unavailable"}` instead of creating a `[Stub] Ingested:` chunk.
- [ ] **Fix `mcp_server.py`**: Wire the `client` parameter to actual search calls. The multi-index path must use the passed client, not the global `mcp` fallback.
- [ ] **Fix `embedding/cache.py` return value**: Return `list[tuple[int, list[float]]]` (index, embedding) pairs so callers can correctly align hits with misses. Update all callers.

---

## Phase 2 — Reliability & Quality

*Goal: Comprehensive test coverage, eliminate code smells, harden error handling. Estimated composite lift: +2.0–2.5 pts.*

### Testing (all components — highest leverage item)

Reach **≥ 80% unit test coverage** on all non-stub code. Use `pytest` with `pytest-cov`.

**DigiGraph test targets:**
- [ ] `tests/digigraph/test_models.py` — Pydantic model validation, edge cases
- [ ] `tests/digigraph/test_registry.py` — Tool registration, dispatch, missing handler
- [ ] `tests/digigraph/test_digistore.py` — Profile inference, path traversal rejection
- [ ] `tests/digigraph/test_run_storage.py` — Session isolation, path escape attempts
- [ ] `tests/digigraph/test_llm.py` — `LLMResult` dataclass, tool call parsing (mock OpenAI)
- [ ] `tests/digigraph/test_workflow.py` — Research node, backtest node, error routing (mock HTTP)

**DigiQuant test targets:**
- [ ] `tests/digiquant/test_strategy_specs.py` — Grid generation, range inference, grid cap
- [ ] `tests/digiquant/test_constraints.py` — Constraint satisfaction, date range, metric bounds
- [ ] `tests/digiquant/test_optimize.py` — Grid/random/Bayesian result shapes (mock backtest)
- [ ] `tests/digiquant/test_models.py` — BacktestResult, OptimizeResult field validation
- [ ] `tests/digiquant/test_cli.py` — Param parsing edge cases (negative, scientific, string)
- [ ] `tests/digiquant/test_export.py` — Output directory validation, path traversal rejection

**DigiSearch test targets:**
- [ ] `tests/digisearch/test_parsers.py` — All 6 parsers with valid + invalid inputs
- [ ] `tests/digisearch/test_chunkers.py` — Chunk sizes, overlap correctness, empty content
- [ ] `tests/digisearch/test_embedding_cache.py` — Hit/miss/index alignment, concurrent writes
- [ ] `tests/digisearch/test_bm25.py` — Ranking order, score > 0 guarantee, tokenization
- [ ] `tests/digisearch/test_hybrid.py` — RRF merge, alpha validation
- [ ] `tests/digisearch/test_chroma.py` — CRUD, score sort order, result cap (mock Chroma)
- [ ] `tests/digisearch/test_odata.py` — OData filter builder, injection edge cases

### Code Quality

**DigiGraph:**
- [ ] Extract hardcoded system prompts from `nodes.py` to `digigraph/prompts/research.txt` (loaded at startup, not import)
- [ ] Add `@lru_cache(maxsize=1)` + file mtime check to `DigiProjectConfig.load()`
- [ ] Replace bare `except Exception` in `llm.py` with specific catches (`httpx.TimeoutException`, `openai.APIError`, etc.) and `logger.error()`
- [ ] Add docstrings to `digistore_profile()`, `_serve_run_data_file()`, all registry handler types

**DigiQuant:**
- [ ] Extract `satisfies_constraints()` to `digiquant/constraints.py` — single implementation imported by both `optimize.py` and `optimize_bayesian.py`
- [ ] Extract `nautilus_runner.py` into `loader.py` (data loading + bar period inference), `runner.py` (Nautilus execution), `result_parser.py` (account report + stats)
- [ ] Replace all magic numbers with named constants in a `digiquant/constants.py`: `DEFAULT_STARTING_CAPITAL`, `DEFAULT_BAR_PERIOD`, `MAX_GRID_SIZE`, `CODE_EXEC_TIMEOUT`
- [ ] Add `logger.info()` progress output during optimization: `Trial {n}/{total}: {params} → Sharpe {sharpe:.3f}`

**DigiSearch:**
- [ ] Replace `object | None` type hints with `Protocol` types: `EmbedCallable = Callable[[str], list[float]]`, `IndexProtocol`
- [ ] Fix IDF formula in `TFIDFSearcher`: `math.log(n / (df[t] + 1))` — add regression test
- [ ] Move `nltk.download()` from module scope to lazy init inside `SentenceChunker.__init__()` with a flag guard
- [ ] Replace hardcoded backend if/elif in `client.py` with a `BackendRegistry` dict: `{"chroma": ChromaBackend, "azure": AzureBackend}`
- [ ] Batch sentence embedding in `SemanticChunker`: collect all sentences, call `embed_batch([...])` once, then split on similarity

### Error Handling

- [ ] All three components: audit every `except Exception` block — add log statement before `pass` or re-raise. No silent swallowing.
- [ ] All three components: API errors must propagate as structured JSON responses with `{"error": "...", "detail": "..."}` — not 500 with stack trace.
- [ ] DigiQuant: `nautilus_runner.py` Nautilus import failure must log which import failed and raise `ImportError` with a helpful install message.
- [ ] DigiSearch: All backend connection failures must return `SearchResponse(status="error", error_message="...")` — never an empty list.

---

## Phase 3 — Performance & Completeness

*Goal: Meet documented performance targets, implement promised-but-stubbed features. Estimated composite lift: +1.0–1.5 pts.*

### Performance

**DigiQuant:**
- [x] **Parallel grid optimization**: `ProcessPoolExecutor` with top-level `_run_trial` worker; falls back to sequential. `DIGIQUANT_OPTIMIZE_WORKERS` env var.
- [x] **Backtest result cache**: SHA-256 hash of `(strategy, symbols, params, data_path, data_dir)` → in-memory `BacktestResult`. Skipped when `tearsheet_path` set. `DIGIQUANT_BACKTEST_CACHE=false` disables.
- [ ] **Lazy tearsheet**: Only build charts that are requested. Default to Sharpe/drawdown/equity curve; skip distribution charts unless `--full` flag is passed.

**DigiSearch:**
- [x] **Batch embedding cache**: Single `SELECT WHERE hash IN (...)` query replaces N individual selects.
- [x] **Connection pooling**: Persistent `httpx.Client` (`_shared_client`) in `http_client.py`; closed via `atexit`.
- [ ] **Benchmark SemanticChunker**: Profile per-sentence vs. batched embedding on a 100-page document. Document result in `DIGISEARCH.md`.

**DigiGraph:**
- [x] **Config caching**: `_config_cache: dict[tuple[str, float], DigiProjectConfig]` keyed by `(resolved_path, mtime)` in `project_config.py`.
- [ ] **Streaming backtest progress**: Instead of 30s blocking wait on DigiQuant, switch to SSE or polling with `httpx.stream()`. Surface intermediate progress tokens to the user.

### Feature Completeness

**DigiQuant:**
- [x] Implement `tradingview.py` Pine Script v5 export: Pine v5 templates for `ema_cross`, `bollinger_mr`, `rsi_momentum`, `macd_trend`; alias resolution; optional `output_path`.
- [x] Implement ADDM drift detection (`addm.py`): rolling Sharpe Z-score (configurable window + threshold); `record_sharpe()` / `clear_history()` helpers.
- [x] Add `strategy_specs.py` external config override: `DIGIQUANT_STRATEGY_SPECS_PATH` points to a YAML file; loaded and merged per-call in `get_param_specs()`.

**DigiSearch:**
- [ ] Wire OCR in `pdf.py`: Try `pdfplumber` first (text PDF), fall back to `pytesseract` + `pdf2image` for scanned pages. Gate behind `DIGISEARCH_OCR_ENABLED` env flag.
- [ ] Complete Azure OData filter builder: Replace hand-rolled builder with parameterized Azure SDK filter objects where supported.
- [ ] Implement multi-index MCP: Fix `mcp_server.py` to accept and use the passed `client` argument for cross-index search.

**DigiGraph:**
- [ ] Implement MCP server entrypoint: Add `digiclaw/skills/digigraph_skill.py` exposing `workflow`, `chat`, and `thread_state` as MCP tools.
- [x] Add LangSmith integration (optional): `_traceable` decorator in `llm.py` wraps `chat_completion` and `chat_completion_with_tools` with `langsmith.traceable` when `LANGSMITH_API_KEY` is set and `langsmith` is installed.

---

## Target Scores After Each Phase

| Component | Baseline | After Phase 1 | After Phase 2 | After Phase 3 |
|-----------|:--------:|:------------:|:-------------:|:-------------:|
| DigiGraph | 4.5 | 5.5 | 7.5 | 8.5 |
| DigiQuant | 4.3 | 5.3 | 7.3 | 8.3 |
| DigiSearch | 3.8 | 5.0 | 7.0 | 8.2 |

---

## Dimension-Level Targets

| Dimension | Baseline Avg | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|-----------|:-----------:|:--------------:|:--------------:|:--------------:|
| Architecture | 6.3 | 6.5 | 7.5 | 8.5 |
| Code Quality | 4.3 | 5.0 | 7.5 | 8.0 |
| Security | 4.0 | 7.0 | 8.0 | 8.5 |
| Testing | 0.0 | 0.0 | 8.0 | 9.0 |
| Documentation | 6.3 | 6.5 | 8.0 | 8.5 |
| Performance | 4.3 | 4.5 | 6.0 | 8.0 |

---

## Revision History

| Date | Notes |
|------|-------|
| 2026-03-18 | Initial plan created from baseline review v1.0 |
| 2026-03-18 | Phase 2 completed: unit tests, constraint extraction, IDF fix, LLMResult model |
| 2026-03-18 | Phase 3 completed (partial): batch cache, parallel opt, backtest cache, config cache, connection pooling, Pine Script export, ADDM drift, YAML override, LangSmith integration |
