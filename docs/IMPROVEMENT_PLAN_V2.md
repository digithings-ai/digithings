# DigiThings — Improvement Plan v2.0

**Based on:** `docs/CODE_REVIEW_BASELINE.md` v2.0 (2026-03-18)
**Starting scores:** DigiGraph 6.2 · DigiQuant 7.0 · DigiSearch 5.7
**Goal:** Reach composite ≥ 8.5 across all three components

---

## Strategy

Three phases ordered by risk and leverage:

- **Phase 1 — Security & Stability** — close all unresolved security gaps; stop the bleeding
- **Phase 2 — Architecture & Code Quality** — remove structural debt that blocks all future work
- **Phase 3 — Testing & Observability** — reach ≥ 80% coverage; make production failures visible
- **Phase 4 — Features & Polish** — complete stubs, multi-symbol, caching, streaming

Each phase lists items by component with file references and estimated line counts.

---

## Phase 1 — Security & Stability

*Goal: No critical or high-severity security issues remain. No silent production failures.*

### 1.1 — API Key Timing Attack (DigiGraph, DigiQuant, DigiSearch)

**All three `server.py` files compare API keys with `!=`.**

```python
# Current (vulnerable)
if request.headers.get("X-API-Key") != expected_key:

# Fix
import secrets
if not secrets.compare_digest(request.headers.get("X-API-Key", ""), expected_key):
```

- Files: `digigraph/src/digigraph/server.py`, `digiquant/src/digiquant/server.py`, `digisearch/src/digisearch/server.py`
- Lines: 1-line change each
- Effort: XS

### 1.2 — Path Traversal: Resolve-First Pattern (DigiGraph)

**Current:** `server.py` and `run_storage.py` check for `".."` in the raw string, then resolve. A URL-encoded path (`%2e%2e`) or symlink bypasses the check.

**Fix:** Resolve before validating. Extract a single shared utility:

```python
# digigraph/src/digigraph/path_utils.py  (new file)
from pathlib import Path

def assert_safe_path(base: Path, ref: str) -> Path:
    """Resolve ref under base and assert it stays within base. Raises ValueError."""
    resolved = (base / ref).resolve()
    base_resolved = base.resolve()
    if not resolved.is_relative_to(base_resolved):
        raise ValueError(f"Path escape attempt: {ref!r} resolves outside {base}")
    return resolved
```

Replace calls in `server.py:92`, `run_storage.py:14-16`, `digistore.py:57-58`, `digistore.py:79-81`.

- Files: `server.py`, `run_storage.py`, `digistore.py`, new `path_utils.py`
- Lines: ~20 new, ~12 replaced
- Effort: S

### 1.3 — OData Filter Injection (DigiSearch)

**`server.py` passes raw `filter` string from HTTP request body directly to the Azure backend.**

Options ranked by effort:
1. **(Easiest)** Accept only structured filter objects — reject raw string filter unless `DIGISEARCH_ALLOW_RAW_FILTER=true` is set.
2. **(Better)** Add a grammar-based validator: allowlist `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `and`, `or`, `not`; reject everything else.

```python
# digisearch/src/digisearch/core/filter_validator.py  (new file)
import re

_SAFE_FILTER = re.compile(
    r"^[\w\s'\"<>=!(),.\-:Tandnorequslihtfbg]+$", re.IGNORECASE
)
_BLOCKED = re.compile(r"(exec|eval|system|__\w+__|<script)", re.IGNORECASE)

def validate_odata_filter(filter_str: str) -> str:
    if _BLOCKED.search(filter_str):
        raise ValueError(f"Blocked pattern in filter: {filter_str!r}")
    if not _SAFE_FILTER.match(filter_str):
        raise ValueError(f"Unsupported characters in filter: {filter_str!r}")
    return filter_str
```

- Files: new `filter_validator.py`, `server.py:142-150`
- Lines: ~40 new
- Effort: S

### 1.4 — Session ID Length Limit (DigiGraph)

**`run_storage.py` sanitizes session IDs to alphanumeric+underscore+hyphen but sets no length limit.**

```python
# run_storage.py:14
_SESSION_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')
```

- Files: `run_storage.py`
- Lines: 1-line change
- Effort: XS

### 1.5 — DigiSearch Stub: Explicit Error When No Backend (DigiSearch)

**`_stub.py` silently returns 0.9-scored fake results when no backend is configured.** Users cannot distinguish real from stub results.

Fix: Return `SearchResponse(status="no_backend_configured", results=[])` and log a warning at startup:

```python
# digisearch/src/digisearch/search/_stub.py
logger.warning("DigiSearch: no backend configured — all queries return empty results. "
               "Set DIGISEARCH_BACKEND or CHROMA_PATH.")
```

- Files: `search/_stub.py`, `server.py` (startup log)
- Lines: ~10 changed
- Effort: XS

### 1.6 — CORS Default: Require Explicit Allowlist (All Three)

**All three servers default to `allow_origins=["*"]` if `DIGI_ALLOWED_ORIGINS` is not set.**

Change default from `["*"]` to `["http://localhost:3000", "http://localhost:8000"]` for development safety. Document in component READMEs.

- Files: all three `server.py`
- Lines: 1-line change each
- Effort: XS

### 1.7 — Data Directory Traversal (DigiQuant)

**`nautilus_runner.py` iterates CSV files in `data_dir` with no path containment check.**

```python
# After resolving candidate path:
candidate = (data_dir / f"{sym}.csv").resolve()
if not candidate.is_relative_to(Path(data_dir).resolve()):
    raise ValueError(f"Symbol path escapes data_dir: {candidate}")
```

- Files: `nautilus_runner.py`
- Lines: 4 lines
- Effort: XS

### 1.8 — Disable or Sandbox `execute_python.py` (DigiGraph)

**`exec()` with restricted globals is not a real sandbox** — `__subclasses__()` chain allows arbitrary code execution. This is the highest-severity unresolved issue.

Options:
1. **(Minimum)** Gate behind `DIGI_ALLOW_CODE_EXEC=true` env var; return structured error if unset.
2. **(Better)** Replace with `subprocess` call to an isolated Python process with `--restrict-resources` and a 5-second wall-clock timeout via `asyncio.wait_for`.

- Files: `execute_python.py`, `server.py` or orchestration router
- Lines: ~30 changed
- Effort: M

---

## Phase 2 — Architecture & Code Quality

*Goal: Remove structural debt. One source of truth per concern.*

### 2.1 — Shared `_subst_env()` Utility (DigiGraph + DigiSearch)

Both `digigraph/project_config.py` and `digisearch/core/config.py` implement identical `_subst_env()` functions.

**Create:** `digigraph/src/digigraph/config_utils.py` (or a shared `digiclaw/` package if it exists).

```python
import os, re

def subst_env(value: str) -> str:
    """Replace ${VAR} and $VAR patterns with environment variable values."""
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', lambda m: os.environ.get(m.group(1) or m.group(2), m.group(0)), value)
```

- Files: new `config_utils.py`, update 2 importers
- Lines: ~15 new, ~20 removed
- Effort: S

### 2.2 — OpenAI Client Connection Pool (DigiGraph)

**`get_client()` creates a new `OpenAI` instance on every call** — no connection reuse.

```python
# digigraph/src/digigraph/llm.py
_client_cache: dict[tuple[str, str], OpenAI] = {}

def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "not-set")
    base_url = os.environ.get("OPENAI_API_BASE") or ""
    key = (api_key, base_url)
    if key not in _client_cache:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url.rstrip("/")
        _client_cache[key] = OpenAI(**kwargs)
    return _client_cache[key]
```

- Files: `llm.py`
- Lines: ~10
- Effort: XS

### 2.3 — Async HTTP in Tool Handlers (DigiGraph)

**`digisearch_tool.py` and `digiquant_tool.py` use `httpx.Client` (sync) inside async FastAPI routes.** Under concurrent load, ASGI workers stall waiting for blocking IO.

Fix: Convert tool handlers to use `httpx.AsyncClient` with `await`. Requires making `execute_tool` callable async-aware.

```python
# tools/digisearch.py
async def _search_async(url: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        return r.json()
```

Tool dispatch in `chat_completion_with_tools` would need to `await` handlers or use `asyncio.to_thread()` as a bridge.

- Files: `tools/digisearch.py`, `tools/digiquant.py`, `llm.py:chat_completion_with_tools`
- Lines: ~40 changed
- Effort: M

### 2.4 — `nautilus_runner.py` Decomposition (DigiQuant)

**292-line monolith** mixes data loading, bar period inference, Nautilus execution, result parsing, and tearsheet generation — untestable in isolation.

Split into:
- `data/loader.py` — OHLCV CSV loading, bar period inference (already started; extend)
- `execution/runner.py` — Nautilus engine setup, run, shutdown
- `execution/result_parser.py` — account report → `BacktestResult` with robust column handling
- `nautilus_runner.py` — thin coordinator that imports the above

Benefit: each can be unit-tested independently; `result_parser.py` can be tested against fixture CSV files without running Nautilus.

- Files: `nautilus_runner.py` → 3-4 new files
- Lines: ~50 net new (interfaces); existing ~292 redistributed
- Effort: L

### 2.5 — DigiSearch Backend Registry (DigiSearch)

**`client.py` uses `if/elif` chain for backend selection.** Adding a backend requires editing core client code.

```python
# digisearch/src/digisearch/client.py
_BACKEND_REGISTRY: dict[str, type[DigiIndex]] = {
    "chroma": ChromaBackend,
    "azure":  AzureBackend,
    "stub":   StubBackend,
}

def _create_backend(name: str, config: DigiSearchConfig) -> DigiIndex:
    cls = _BACKEND_REGISTRY.get(name.lower())
    if cls is None:
        raise ValueError(f"Unknown DigiSearch backend: {name!r}. Choices: {list(_BACKEND_REGISTRY)}")
    return cls(config)
```

- Files: `client.py`
- Lines: ~20 changed
- Effort: S

### 2.6 — YAML Spec File Cache (DigiQuant)

**`_load_yaml_specs()` parses the YAML file on every `get_param_specs()` call.** Cache with file mtime, same pattern as `project_config.py`.

```python
_yaml_spec_cache: dict[tuple[str, float], dict] = {}

def _load_yaml_specs() -> dict[str, dict[str, tuple]]:
    path_str = os.environ.get("DIGIQUANT_STRATEGY_SPECS_PATH")
    if not path_str:
        return {}
    p = Path(path_str)
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {}
    key = (str(p.resolve()), mtime)
    if key in _yaml_spec_cache:
        return _yaml_spec_cache[key]
    # ... load, parse, store in _yaml_spec_cache[key] ...
```

- Files: `strategy_specs.py`
- Lines: ~15
- Effort: XS

### 2.7 — Strategy Name Whitelist (DigiQuant)

**`run_backtest()` accepts any string as `strategy_name` — passed to Nautilus without validation.**

```python
# backtest.py
from digiquant.strategies.registry import list_strategy_names

def run_backtest(strategy_name: str, ...):
    valid = list_strategy_names()
    if strategy_name not in valid:
        raise ValueError(f"Unknown strategy: {strategy_name!r}. Valid: {valid}")
```

- Files: `backtest.py`, `strategies/registry.py` (add `list_strategy_names()`)
- Lines: ~10
- Effort: XS

### 2.8 — `addm.py` History TTL / Expiry (DigiQuant)

**`_sharpe_history` is a process-global dict with no expiry.** Long-running processes accumulate stale keys forever.

Add a simple TTL via `(strategy_id, last_recorded_at)` tracking; prune entries older than `ADDM_HISTORY_TTL_DAYS` (default: 90).

- Files: `addm.py`
- Lines: ~20
- Effort: XS

### 2.9 — `SemanticChunker` Batch Embedding (DigiSearch)

**Calls `embedder.embed([sentence])` per sentence** — 1,000 embed calls for a 100-page document.

```python
# digisearch/src/digisearch/chunking/semantic.py
# Collect all sentences first, then batch-embed
all_sentences = [s for chunk in doc.chunks for s in split_sentences(chunk.content)]
embeddings = self.embedder.embed(all_sentences)  # one call
# Then split on cosine similarity
```

- Files: `chunking/semantic.py`
- Lines: ~30 changed
- Effort: S

### 2.10 — `SentenceChunker` Lazy NLTK Download (DigiSearch)

**`nltk.download()` runs at module import time** — makes a network call on first import of any DigiSearch code.

```python
# Move into __init__ with a flag guard
_NLTK_READY = False

class SentenceChunker:
    def __init__(self):
        global _NLTK_READY
        if not _NLTK_READY:
            import nltk
            nltk.download("punkt", quiet=True)
            _NLTK_READY = True
```

- Files: `chunking/sentence.py`
- Lines: ~8 changed
- Effort: XS

---

## Phase 3 — Testing & Observability

*Goal: ≥ 80% unit test coverage on all non-stub code. Production failures visible within 60 seconds.*

### 3.1 — Test: `nautilus_runner` Result Parser (DigiQuant)

The most fragile untested code. Create fixture CSV files mimicking Nautilus account reports, test against `result_parser.py` (post-2.4 refactor).

- Files: `tests/dq/test_result_parser.py` (new)
- Tests: column variations, missing columns, empty report, scientific notation values
- Lines: ~80 tests
- Effort: M (after 2.4)

### 3.2 — Test: `tradingview.py` and `addm.py` (DigiQuant)

New Phase 3 code has no tests.

**`test_tradingview.py`:**
- Export each of the 4 strategies with default + override params
- Alias resolution (`"ema"` → `"ema_cross"`)
- Unknown strategy returns `success=False`
- `output_path` writes file with correct content
- Template variable substitution correctness

**`test_addm.py`:**
- `record_sharpe` + `check_drift` flow
- Fewer than 3 obs → `implemented=False`
- Z-score ≥ threshold → `drift_detected=True`
- Zero stdev → no drift
- `clear_history()` clears one vs. all

- Files: `tests/dq/test_tradingview.py`, `tests/dq/test_addm.py`
- Lines: ~120 tests total
- Effort: S

### 3.3 — Test: Bayesian Optimization (DigiQuant)

`optimize_bayesian.py` has zero tests.

- Mock `run_backtest` to return deterministic `BacktestResult`
- Test Optuna trial count, constraint filtering, best-result selection
- Test `n_trials=0` edge case

- Files: `tests/dq/test_optimize_bayesian.py`
- Lines: ~60 tests
- Effort: S

### 3.4 — Test: Hybrid Search, RRF Merge (DigiSearch)

Core search logic is untested.

- RRF score merge correctness (two ranked lists → correct combined rank)
- Alpha=0 → keyword-only; alpha=1 → vector-only
- Degenerate: one list empty

- Files: `tests/ds/test_hybrid_search.py`
- Lines: ~50 tests
- Effort: S

### 3.5 — Test: OData Filter Validator (DigiSearch)

After 1.3 is implemented:

- Valid filters pass through
- Blocked patterns (`exec`, `eval`, `__class__`) are rejected
- Unsupported characters raise `ValueError`
- Empty filter passes (no-op)

- Files: `tests/ds/test_filter_validator.py`
- Lines: ~30 tests
- Effort: XS

### 3.6 — Test: Path Traversal Rejection (DigiGraph, DigiQuant)

After 1.2 is implemented:

- `../` escapes rejected
- URL-encoded `%2e%2e` rejected
- Symlink to parent rejected
- Valid sub-paths accepted

- Files: `tests/dg/test_path_utils.py`, `tests/dq/test_export.py` (extend)
- Lines: ~40 tests
- Effort: S

### 3.7 — Test: DigiGraph Concurrency (DigiGraph)

Concurrent sessions should not share state.

- Two `thread_id` values → isolated `WorkflowState`
- Simultaneous LLM mode env vars (via `monkeypatch`) don't bleed between requests
- Checkpointer returns correct state per thread

- Files: `tests/dg/test_concurrency.py` (new)
- Lines: ~50 tests
- Effort: M (needs async test support via `pytest-anyio`)

### 3.8 — Structured Logging Throughout DigiSearch (DigiSearch)

**Zero logging in DigiSearch.** Every failure is a silent fallback.

Add `import logging; logger = logging.getLogger(__name__)` to:
- `client.py` — log backend selection, fallback events
- `search/_stub.py` — `WARNING` on every query (stub in use)
- `embedding/cache.py` — log cache hit rate at INFO
- `indexes/backends/*.py` — log connection errors at ERROR
- `server.py` — log ingest success/failure counts

- Files: ~8 files
- Lines: ~40 total
- Effort: S

### 3.9 — Request Correlation ID (All Three)

**Cannot trace a user request across DigiGraph → DigiQuant → DigiSearch.** Each service logs independently with no shared identifier.

```python
# Middleware in all three server.py files:
import uuid

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

Pass `X-Request-ID` in outgoing HTTP calls from DigiGraph to child services.

- Files: all three `server.py`, `tools/digisearch.py`, `graph/nodes.py`
- Lines: ~25 total
- Effort: S

### 3.10 — Circuit Breaker for Downstream Services (DigiGraph)

**DigiGraph makes synchronous-style HTTP calls to DigiQuant and DigiSearch.** If either is down, all DigiGraph requests fail with a 15-second timeout per call.

Use `tenacity` (already likely available) or a simple in-memory state machine:

```python
# digigraph/src/digigraph/circuit_breaker.py  (new)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8),
       retry=retry_if_exception_type(httpx.HTTPError))
def call_digiquant(url: str, payload: dict) -> dict:
    ...
```

- Files: new `circuit_breaker.py`, `graph/nodes.py`, `tools/digisearch.py`
- Lines: ~60 total
- Effort: M

---

## Phase 4 — Features & Polish

*Goal: Complete stubbed features; reach stated documentation targets.*

### 4.1 — Multi-Symbol Backtest (DigiQuant)

**`nautilus_runner.py` loads only the first symbol** from `data_dir`. Multi-symbol strategies are documented but not functional.

- Extend `data/loader.py` to return `dict[str, pd.DataFrame]` keyed by symbol
- Pass all instruments to Nautilus `BacktestEngine`
- Update `BacktestResult` with per-symbol PnL breakdown

- Files: `nautilus_runner.py` (or post-2.4 `runner.py`), `models.py`
- Lines: ~60 changed
- Effort: L

### 4.2 — Lazy Tearsheet (DigiQuant)

**`tearsheet.py` builds all charts unconditionally** even when caller only wants Sharpe/drawdown.

```python
def build_tearsheet(result: BacktestResult, *, full: bool = False) -> str:
    charts = [equity_curve(result), drawdown(result), metrics_table(result)]
    if full:
        charts += [returns_distribution(result), rolling_sharpe(result), monthly_heatmap(result)]
    ...
```

Expose `full` param in `run_backtest()` and HTTP API.

- Files: `tearsheet.py`, `backtest.py`, `server.py`
- Lines: ~30 changed
- Effort: S

### 4.3 — Streaming Backtest Progress (DigiGraph)

**30-second blocking wait on DigiQuant with no user feedback.**

Replace with SSE polling or DigiQuant progress endpoint:

```python
# DigiQuant: add GET /backtest/{job_id}/progress -> SSE stream
# DigiGraph: use httpx streaming to forward progress tokens to user
async for event in client.stream("GET", f"{DIGIQUANT_URL}/backtest/{job_id}/progress"):
    yield event
```

- Files: DigiQuant `server.py`, DigiGraph `graph/nodes.py`
- Lines: ~80 total
- Effort: L

### 4.4 — PDF OCR Backend (DigiSearch)

**`pdf.py` returns placeholder text for scanned PDFs.**

```python
# digisearch/src/digisearch/parsers/pdf.py
import os
if os.environ.get("DIGISEARCH_OCR_ENABLED"):
    try:
        import pytesseract, pdf2image
        # OCR path
    except ImportError:
        logger.warning("DIGISEARCH_OCR_ENABLED set but pytesseract/pdf2image not installed")
```

Gate behind `DIGISEARCH_OCR_ENABLED=true`. Try `pdfplumber` first (text PDF), fall back to OCR.

- Files: `parsers/pdf.py`
- Lines: ~50
- Effort: M

### 4.5 — Multi-Index MCP Fix (DigiSearch)

**`mcp_server.py` ignores its `client` parameter.** All queries use global default client.

```python
# mcp_server.py
def create_mcp_server(client: DigiSearchClient) -> FastMCP:
    @mcp.tool()
    def search(query: str, index: str = "default") -> str:
        return client.query(query, index_name=index)  # use the passed client
```

- Files: `mcp_server.py`
- Lines: ~15 changed
- Effort: XS

### 4.6 — DigiGraph MCP Server Entrypoint

**No MCP server for DigiGraph.** Agents can't call DigiGraph workflow via MCP.

Create `digigraph/src/digigraph/mcp_server.py`:
- `workflow(prompt, thread_id)` — triggers research+backtest graph
- `chat(message, thread_id)` — OpenAI-compatible chat
- `thread_state(thread_id)` — returns current state

- Files: new `mcp_server.py`
- Lines: ~100
- Effort: M

### 4.7 — LLM Response Caching (DigiGraph)

**Identical LLM prompts (e.g. repeated research node) make 2 API calls.**

```python
# llm.py
import hashlib, functools

@functools.lru_cache(maxsize=256)
def _cached_completion(model: str, messages_key: str, temperature: float) -> str:
    ...
```

Cache key: SHA-256 of `(model, json(messages), temperature)`. TTL: 1 hour (use `cachetools.TTLCache`).

- Files: `llm.py`
- Lines: ~25
- Effort: S

### 4.8 — Rate Limiting (All Three)

**All endpoints are unbounded.** One client can exhaust all workers.

Use `slowapi` (compatible with FastAPI/Starlette):

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.post("/workflow")
@limiter.limit("10/minute")
async def workflow(...): ...
```

Per-endpoint limits:
- `/workflow`, `/query`: 10 req/min (expensive)
- `/health`: unlimited
- `/ingest`: 30 req/min

- Files: all three `server.py`
- Lines: ~20 per server
- Effort: S

---

## Target Scores After Each Phase

| Component | v2.0 Now | After Phase 1 | After Phase 2 | After Phase 3 | After Phase 4 |
|-----------|:--------:|:-------------:|:-------------:|:-------------:|:-------------:|
| DigiGraph | 6.2 | 7.0 | 7.8 | 8.5 | 9.0 |
| DigiQuant | 7.0 | 7.5 | 8.2 | 8.8 | 9.2 |
| DigiSearch | 5.7 | 6.5 | 7.5 | 8.3 | 8.8 |

---

## Dimension-Level Targets

| Dimension | v2 Avg | Ph1 Target | Ph2 Target | Ph3 Target | Ph4 Target |
|-----------|:------:|:----------:|:----------:|:----------:|:----------:|
| Architecture | 7.7 | 7.7 | 8.5 | 8.5 | 9.0 |
| Code Quality | 6.3 | 6.5 | 8.0 | 8.5 | 9.0 |
| Security | 4.7 | 7.5 | 8.0 | 8.5 | 9.0 |
| Testing | 5.0 | 5.0 | 5.5 | 8.5 | 9.0 |
| Documentation | 5.7 | 6.0 | 6.5 | 7.5 | 8.5 |
| Performance | 7.7 | 7.7 | 8.5 | 8.5 | 9.0 |

---

## Priority Matrix

| Item | Component | Impact | Effort | Phase |
|------|-----------|:------:|:------:|:-----:|
| 1.1 API key timing attack | All | Security | XS | 1 |
| 1.2 Path traversal resolve-first | DigiGraph | Security | S | 1 |
| 1.3 OData filter injection | DigiSearch | Security | S | 1 |
| 1.4 Session ID length limit | DigiGraph | Security | XS | 1 |
| 1.5 Stub silent fix | DigiSearch | Reliability | XS | 1 |
| 1.6 CORS default | All | Security | XS | 1 |
| 1.7 Data dir traversal | DigiQuant | Security | XS | 1 |
| 1.8 exec() sandbox/gate | DigiGraph | Security | M | 1 |
| 2.2 OpenAI client pool | DigiGraph | Performance | XS | 2 |
| 2.5 Backend registry | DigiSearch | Architecture | S | 2 |
| 2.6 YAML spec cache | DigiQuant | Performance | XS | 2 |
| 2.7 Strategy whitelist | DigiQuant | Security | XS | 2 |
| 2.8 ADDM TTL | DigiQuant | Reliability | XS | 2 |
| 2.9 SemanticChunker batch | DigiSearch | Performance | S | 2 |
| 2.10 NLTK lazy download | DigiSearch | Reliability | XS | 2 |
| 2.3 Async HTTP tools | DigiGraph | Performance | M | 2 |
| 2.4 nautilus_runner split | DigiQuant | Architecture | L | 2 |
| 3.1 Result parser tests | DigiQuant | Testing | M | 3 |
| 3.2 tradingview/addm tests | DigiQuant | Testing | S | 3 |
| 3.3 Bayesian opt tests | DigiQuant | Testing | S | 3 |
| 3.4 Hybrid search tests | DigiSearch | Testing | S | 3 |
| 3.5 OData validator tests | DigiSearch | Testing | XS | 3 |
| 3.6 Path traversal tests | DigiGraph | Testing | S | 3 |
| 3.7 Concurrency tests | DigiGraph | Testing | M | 3 |
| 3.8 DigiSearch logging | DigiSearch | Observability | S | 3 |
| 3.9 Request correlation ID | All | Observability | S | 3 |
| 3.10 Circuit breaker | DigiGraph | Reliability | M | 3 |
| 4.1 Multi-symbol backtest | DigiQuant | Feature | L | 4 |
| 4.2 Lazy tearsheet | DigiQuant | Performance | S | 4 |
| 4.3 Streaming backtest progress | DigiGraph | Feature | L | 4 |
| 4.4 PDF OCR | DigiSearch | Feature | M | 4 |
| 4.5 Multi-index MCP fix | DigiSearch | Feature | XS | 4 |
| 4.6 DigiGraph MCP server | DigiGraph | Feature | M | 4 |
| 4.7 LLM response cache | DigiGraph | Performance | S | 4 |
| 4.8 Rate limiting | All | Security | S | 4 |

---

## Revision History

| Date | Notes |
|------|-------|
| 2026-03-18 | Initial v2 plan from post-Phase 2+3 re-score |
