# Phase A Spec — OSS Web Search: URL Ingest + SearXNGBackend (2026-09-14)

## Goal

Close the fetch gap toward an open-source EXA equivalent: ingest arbitrary URLs through digifetch into the existing digisearch parse→chunk→embed→index path, and ship a self-hosted SearXNG query backend behind the existing `WebSearchData` contract, with EXA kept as the paid high-recall fallback.

## Architecture

URL ingest is a new `digisearch.pipeline.url_ingest` entry point that fetches via digifetch `HttpFetcher.download()` + decode (the byte cap lives ONLY in `download()` — see Task 3), reuses the existing `ingestion.web_scrape.is_allowed_scrape_url` SSRF jail (extended, not duplicated — see Task 1), extracts readability markdown (**Crawl4AI wins by default** per EXTRACTOR RULING; trafilatura only behind explicit legal sign-off — Task 2 is spike-then-confirm), then reuses `pipeline.ingest.ingest_source` / `index_chunks` unchanged — this fetch-plus-sandboxing design is exactly what lifts the `digisearch/AGENTS.md` ban on raw-URL `POST /ingest` `source`. Redirects are followed by a manual per-hop loop (`follow_redirects=False` + re-validation each hop, max 5 — Task 3, requires a small digifetch change) because `HttpFetcher.__init__` currently hardcodes `follow_redirects=True`. The SearXNG backend is a new `digisearch.web_providers.searxng.SearXNGBackend` that queries a loopback SearXNG sidecar (`GET /search?format=json`) and maps rows into `WebSearchData{results, output, search_type, cost_dollars}` — the same shape `web_exa.exa_search` returns — with degraded-mode behavior (CAPTCHA-walled engines → DuckDuckGo-flavored results flagged in `output`) and EXA fallback preserved behind `is_exa_configured()`.

## Tech Stack

Python 3.12, pydantic v2, httpx (only transport; never `requests`), digifetch `HttpFetcher` / `with_retry` / `RateLimiter` (composed, never embedded flags), FastAPI + FastMCP + Typer ([server] extra), SearXNG sidecar (`searxng/searxng` + valkey, loopback-only), readability extraction default Crawl4AI (Apache-2.0; Ollama-native, local-only) with trafilatura (GPL-3.0) only behind explicit legal sign-off, ruff line-length 100.

## Consumes / Produces (vs other phases)

- **CONSUMES: nothing.** Phase A is the foundation; it builds only on already-merged code (`web_exa.WebSearchData`, `pipeline.ingest`, `ingestion.web_scrape.is_allowed_scrape_url`, digifetch `HttpFetcher`).
- **PRODUCES (for later phases):** `ingest_url()` (+ `UrlIngestResult` / `UrlFetchError`), `SearXNGBackend.query()` returning `WebSearchData`, `web_providers/models.py` with the shared `Citation{url, title="", excerpt=""}` model + shared `normalize_url()` helper (owned by Phase A; Phases B/D import these, never redefine them), the SSRF-jail extension + byte-cap + sandboxing policy that justifies lifting the raw-URL ban, the EXA-response-shape mirror table (§0 below), and the degraded-mode contract (`output.degraded`, engine provenance per result).
- **Access rule (R2):** all Phase A surfaces are consumed by direct import within the `digisearch` package; HTTP is used only at process/component boundaries (REST routes, SearXNG sidecar calls). No new HTTP client seams between in-package modules.
- Later phases (provider registry/router, MCP/REST/orchestrator wiring, digigraph caller swap, frontend defaults) consume these surfaces and MUST NOT change their signatures without a spec amendment.

## §0 — Normative EXA response shapes to mirror (from /tmp/exa-review)

- `/search` (`s1_auto.json`): `{requestId, resolvedSearchType, results[{id, title, url, publishedDate, author?, highlights[], image?}], searchTime, costDollars{total, search{neural}}}`. `web_exa.exa_search` maps this to `WebSearchData{results, output=None, search_type=searchType or resolvedSearchType or requested, cost_dollars=costDollars}` — mirror that fallback order exactly (`searchType` first, then `resolvedSearchType`, then the requested value; see `digisearch/src/digisearch/web_exa.py:167`).
- `/search` deep-structured (`s4_deep_structured.json`): adds `output{content{...schema-shaped}, grounding[{field, citations[{url, title}], confidence}]}` and `costDollars{total}` without sub-breakdown. `WebSearchData.output` carries the whole `output` dict verbatim.
- `/contents` (`c1_contents.json`): `{requestId, results[{id, title, url, publishedDate, author, text, highlights[], summary}], statuses[{id, status, source}], costDollars{total, contents{text, highlights, summary}}, searchTime}`. Phase A SearXNG rows map: SearXNG `url→url`, `title→title`, `content→highlights[0]` (snippet), engine name preserved per-row; `publishedDate` passed through when present else omitted (never fabricated).
- `cost_dollars` for OSS backends (advisory-only total): `{"total": 0.0, "provider": "searxng", "breakdown": {"searches": 1, "pages_fetched": 0, "llm_calls": 0}, "note": "self-hosted; total is advisory, not billed"}` — `total` is advisory-only; consumers MUST NOT treat it as a bill. Mapper sets `breakdown.searches=1`; URL-ingest-attributed fetches (later phases) increment `pages_fetched`.

## File Structure

Create:

- `digisearch/src/digisearch/pipeline/url_ingest.py` — `ingest_url()`, manual redirect loop, byte-capped fetch-via-`download()`, sandbox staging, extraction dispatch.
- `digisearch/src/digisearch/pipeline/url_policy.py` — `UrlFetchPolicy` (allowlist/blocklist, max_bytes, timeout, user-agent), `assert_url_allowed()` wrapping `is_allowed_scrape_url` (Task 1).
- `digisearch/src/digisearch/extract/readability.py` — `extract_markdown(html, url)` on Crawl4AI by default (Task 2 confirms).
- `digisearch/src/digisearch/web_providers/__init__.py` — re-exports `SearXNGBackend`, `SearXNGConfig`, `SearXNGDegradedError`; re-exports `WebSearchData` from `web_exa` (single result shape, no second type).
- `digisearch/src/digisearch/web_providers/models.py` — shared `Citation` + `normalize_url` owned by Phase A (R5; Phases B/D import from here).
- `digisearch/src/digisearch/web_providers/searxng.py` — `SearXNGBackend` + `SearXNGConfig.from_env()`.
- `digisearch/src/digisearch/web_providers/mapping.py` — `searxng_rows_to_web_search_data()` pure mapper (EXA-shape mirror, §0).
- `config/searxng/settings.yml` — sidecar config (`search.formats: [html, json]`, `server.secret_key`, engine allowlist).
- `tests/ds/test_url_ingest.py`, `tests/ds/test_url_policy.py`, `tests/ds/test_readability_extract.py`, `tests/ds/test_searxng_backend.py`, `tests/ds/test_searxng_mapping.py`, `tests/ds/test_url_ingest_api.py` — one per surface, all offline (httpx.MockTransport / fixture HTML), every file carrying `@pytest.mark.unit`.
- `tests/ds/fixtures/url_pages/` — 5 local HTML fixtures for Task 2 (article with nav/chrome, table-heavy, list-heavy, JS-shell with `<noscript>` fallback, non-HTML-served-as-HTML edge case).

Modify:

- `digifetch/src/digifetch/http.py` — add `follow_redirects: bool = True` ctor arg to `HttpFetcher` (default preserves current behavior) + `headers: dict[str, str]` field (default `{}`) on `FetchResult`/`DownloadResult` so the manual loop can read `Location` on 3xx responses (Task 3 specifies; tests in `digifetch/tests/test_http_redirect.py`).
- `digisearch/src/digisearch/server.py` — add `POST /ingest/url` route (NOT a change to `POST /ingest` `source` semantics); add `GET /v1/web_providers` status route. Both behind existing `DigiAuthMiddleware` scopes.
- `digisearch/src/digisearch/cli.py` — add `digisearch ingest-url <url>` thin adapter over `ingest_url()`.
- `digisearch/src/digisearch/orchestrator_tools.py` — extend `build_web_search_tool()` description to name `searxng` provider option; no schema break (additive `provider` enum value only).
- `digisearch/pyproject.toml` — add optional extras `url-ingest` (Crawl4AI default; trafilatura only with legal-sign-off comment) and `searxng` (no client dep; documents sidecar). Base deps unchanged (`pydantic` + `httpx` already present).
- `docker-compose.yml` — loopback-only `searxng` + `valkey` sidecar services (both image tags pinned, no `:latest`).
- `.env.example` — document the six new vars: `DIGISEARCH_URL_MAX_BYTES`, `DIGISEARCH_URL_TIMEOUT_S`, `DIGISEARCH_URL_ALLOW_PRIVATE_IPS`, `DIGISEARCH_URL_BLOCKED_HOSTS`, `DIGISEARCH_URL_STAGING_DIR`, `DIGISEARCH_SEARXNG_URL`.
- `digisearch/ARCHITECTURE.md` — §3 new routes, §5 new modules, record raw-URL ban lift + extraction decision.
- `digisearch/AGENTS.md` — amend the "Ingest source is a filesystem path" rule to permit `POST /ingest/url` via `url_ingest` (fetch + SSRF jail + sandboxing satisfied); record the narrow exception that `pipeline/url_ingest.py` + `pipeline/url_policy.py` are the only non-filesystem ingest modules.

Explicitly NOT touched in Phase A (later phases): `mcp_server.py` tool wiring beyond description copy, `digigraph/` caller swap, `digillm/` telemetry, `digiquant/` grounding, any frontend, `ingest_worker.py`, `search/_stub.py` backend registry ordering for owned-corpus backends.

## Interfaces (produced this phase — frozen for later phases)

```python
# digisearch.pipeline.url_policy
class UrlFetchPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_bytes: int = 8 * 1024 * 1024
    timeout_s: float = 20.0
    user_agent: str = "digisearch-url-ingest/1.0 (+https://digithings.ai)"
    allow_private_ips: bool = False
    allowed_schemes: list[str] = ["http", "https"]
    blocked_hosts: list[str] = []
    @classmethod
    def from_env(cls) -> "UrlFetchPolicy": ...

def assert_url_allowed(url: str, policy: UrlFetchPolicy) -> str:
    """Thin policy wrapper over ingestion.web_scrape.is_allowed_scrape_url
    (scheme allowlist + getaddrinfo + private/loopback rejection — the tested
    SSRF jail, see tests/ds/test_web_scrape_ssrf.py). Adds ONLY what the jail
    lacks: blocked_hosts suffix match, allow_private_ips override, and a typed
    UrlFetchError (vs bool) + normalized-URL return. No second jail: any rule
    expressible in is_allowed_scrape_url stays there.
    Returns normalized URL. Raises UrlFetchError(code=..., http_status=400)."""
```

```python
# digisearch.pipeline.url_ingest
class UrlIngestResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    chunks_created: int
    index_name: str
    status: str = "ok"
    backend: str | None = None
    source_url: str
    final_url: str
    extractor: str  # "crawl4ai" (default) | "trafilatura" (legal sign-off only)

class UrlFetchError(IngestError): ...  # same code/http_status contract as IngestError

def ingest_url(
    url: str,
    *,
    index_name: str = "default",
    metadata: Mapping[str, Any] | None = None,
    chunker_name: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    policy: UrlFetchPolicy | None = None,
    extractor: str | None = None,
    fetcher: HttpFetcher | None = None,  # injectable for tests (MockTransport)
) -> UrlIngestResult:
    """Byte-capped fetch via digifetch download() + decode → extract markdown →
    stage to sandboxed temp file → ingest_source() → index_chunks().
    Never writes outside staging dir; never calls POST /ingest source path.
    Sends policy.user_agent as the User-Agent header on every fetch
    (the field exists solely for this; if unwired, delete it)."""
```

```python
# digisearch.extract.readability
def extract_markdown(html: str, url: str = "") -> tuple[str, str]:
    """Return (markdown, extractor_name), default extractor "crawl4ai"
    (Task 2 confirms; trafilatura only with legal sign-off). Returns
    ("", extractor) on empty input, never raises on malformed HTML."""
```

```python
# digisearch.web_providers.models (owned by Phase A per R5; B/D import from here)
class Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str
    title: str = ""
    excerpt: str = ""

def normalize_url(url: str) -> str:
    """Lowercase scheme/host, strip default ports + trailing slash, drop
    fragments. Shared by Phases A/B/D — no local copies."""
```

```python
# digisearch.web_providers.searxng
class SearXNGConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:8080"
    timeout_s: float = 15.0
    backend_name: str = "searxng"
    @classmethod
    def from_env(cls) -> "SearXNGConfig":
        """Reads DIGISEARCH_SEARXNG_URL at call time (never at import)."""

class SearXNGDegradedError(RuntimeError): ...  # sidecar down/unreachable

class SearXNGBackend:
    name = "searxng"
    def __init__(self, config: SearXNGConfig | None = None,
                 client: httpx.Client | None = None,
                 limiter: RateLimiter | None = None) -> None:
        """limiter defaults to RateLimiter(min_interval=1.0) for single-IP
        SearXNG politeness; acquire()d before every query. Tests inject
        RateLimiter(min_interval=0) (or injected clock/sleep no-ops)."""
    def query(
        self,
        query: str,
        *,
        num_results: int = 8,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        category: str | None = None,
        timeout_s: float | None = None,
    ) -> WebSearchData:
        """GET {base}/search?q=...&format=json. Always returns WebSearchData
        (the web_exa type — never a second shape). Degraded engines flagged
        in output.degraded (see mapping). Raises SearXNGDegradedError when
        the sidecar is unreachable; never falls through to EXA silently —
        fallback is the caller's explicit decision."""
```

```python
# digisearch.web_providers.mapping
def searxng_rows_to_web_search_data(
    rows: list[dict[str, Any]],
    *,
    query: str,
    degraded_engines: list[str] | None = None,
) -> WebSearchData:
    """Pure mapper: SearXNG item {url,title,content,engine,score,publishedDate?}
    → EXA-mirror result dicts {id,title,url,publishedDate,highlights,engine}.
    Sets output={"degraded": [...], "provider": "searxng"} when degraded_engines
    non-empty, else output=None. cost_dollars={"total": 0.0,
    "provider": "searxng", "breakdown": {"searches": 1, "pages_fetched": 0,
    "llm_calls": 0}, "note": "self-hosted; total is advisory, not billed"}."""
```

REST produced:

- `POST /ingest/url {url, index_name="default", metadata?, extractor?}` → `UrlIngestResult`, scope `digisearch:ingest`, rate limit 30 req/min per IP (same bucket as `/ingest`).
- `GET /v1/web_providers` → `{providers: [{name: "searxng", configured: bool}, {name: "exa", configured: bool}], default: "searxng"|"exa"}`, scope `digisearch:query`. `default` is `"searxng"` when the sidecar answers, else `"exa"` when `is_exa_configured()`, else `"none"` (fail-closed, no stub).

## Global Constraints

- Python 3.12, pydantic v2 everywhere, strict typing, ruff line-length 100; `ruff check` + `ruff format --check` zero errors on every task.
- Every new model declares `model_config` explicitly (`extra="forbid"` for policy/config inputs, `extra="ignore"` for result/envelope outputs mirroring external shapes).
- Every new test file carries `@pytest.mark.unit` (module-level `pytestmark` or per-test marks); tests live in `tests/ds/` (never `digisearch/tests/`).
- No pandas anywhere (`import pandas` fails review); polars only.
- `DIGISEARCH_ALLOW_STUB=1` test-only; never set in production code paths; new tests use `httpx.MockTransport` + fixture HTML, never live network.
- Retry-path tests inject a no-op sleep (`RetryPolicy(..., sleep=lambda _: None)`) so suites stay instant and deterministic.
- Scopes via existing `DigiAuthMiddleware`: `digisearch:ingest` for `/ingest/url`, `digisearch:query` for `/v1/web_providers`. No new scopes, no digikey change.
- No new hard deps without human gate: Crawl4AI lands as an optional extra (Apache-2.0, no gate beyond normal review); trafilatura (GPL-3.0) additionally needs explicit legal sign-off for closed distributions; network-capable dep = human review trigger per root AGENTS.md.
- `import digifetch` stays browser-free: url_ingest uses `HttpFetcher` only, never `browser_session` (no Playwright in Phase A fetch path). Crawl4AI needs its browser-install step (`crawl4ai-setup` at dev/image setup, NOT at import); its import stays behind the `url-ingest` extra so the base package keeps the browser-free boundary.
- digifetch reads no env: all policy/config passed in; `from_env()` lives in digisearch, never in digifetch.
- Lowercase digi naming in prose/docs/commits (`digisearch`, `digifetch`, `searxng`).
- Chunker selection stays config-only (`DIGISEARCH_CHUNKER` / per-index `chunker:` via `get_ingest_chunker`); `ChromaBackend` constructions keep explicit `embedding_provider`.
- No full doc bodies in digismith spans; chunk content logged as lengths/hashes only.

## Relationship to existing drafts (consolidate, do not contradict)

- `2026-09-10-web-search-mcp-tool.md`: Phase A adopts its SearXNG-sidecar shape (`format=json`, loopback compose) and its readability evaluation structure, but REJECTS its invented envelope names — all provider code returns `WebSearchData`. Its CLI search fallback, MCP/HTTP/orchestrator wiring (Tasks 5–6), digillm/digiquant swaps (Tasks 7–8), and frontend rollout (Task 9) are explicitly later-phase work, not Phase A. Its unified-router service name is reserved for a later phase; Phase A exposes only `SearXNGBackend.query()` + `ingest_url()`.
- `2026-09-11-web-search-default-on-tool-only.md`: default-ON semantics, service-JWT auth, and tool-only fail-hard grounding are later-phase consumer decisions built ON TOP of Phase A surfaces; Phase A itself is fail-closed (`default: none` when neither backend configured) and adds no auth machinery.
- `2026-09-12-web-search-followups.md`: frontend hardening + docs consistency items presuppose Phase A shapes; Phase A produces the `ok:False`-free raise contracts (`UrlFetchError`, `SearXNGDegradedError`) those tests will pin.

## Tasks

### Task 1 — SSRF jail extension + fetch policy (`url_policy.py`)

How: new file `digisearch/src/digisearch/pipeline/url_policy.py` with `UrlFetchPolicy.from_env()` reading `DIGISEARCH_URL_MAX_BYTES` (default 8388608), `DIGISEARCH_URL_TIMEOUT_S` (default 20.0), `DIGISEARCH_URL_ALLOW_PRIVATE_IPS` (default false), `DIGISEARCH_URL_BLOCKED_HOSTS` (comma-separated, default empty) at call time. `assert_url_allowed()` is a thin wrapper: it calls the EXISTING `ingestion.web_scrape.is_allowed_scrape_url` (scheme allowlist + `getaddrinfo` + private/loopback rejection, tested in `tests/ds/test_web_scrape_ssrf.py`) and adds ONLY what the jail lacks — `blocked_hosts` suffix match, the `allow_private_ips` override, a typed `UrlFetchError` (vs bool), and a normalized-URL return. A second jail is NOT permitted: any rule expressible in `is_allowed_scrape_url` stays there (extend that function instead of duplicating it). Subclass `UrlFetchError(IngestError)` with codes `url_scheme_rejected` (400), `url_host_blocked` (400), `url_private_ip` (400), `url_unresolvable` (400). Redirect targets are re-validated per-hop in Task 3 by calling `assert_url_allowed` on each `Location`.

Deliverable: SSRF policy unit-tested; `socket.getaddrinfo` monkeypatched, no live DNS.

Verify:

```bash
pytest tests/ds/test_url_policy.py -v
ruff check digisearch/src/digisearch/pipeline/url_policy.py tests/ds/test_url_policy.py && ruff format --check digisearch/src/digisearch/pipeline/url_policy.py tests/ds/test_url_policy.py
```

### Task 2 — Readability extraction spike-then-confirm (`readability.py`)

How: Crawl4AI wins BY DEFAULT per EXTRACTOR RULING; the spike confirms (not re-decides) it. Install both candidates in the dev venv only (`pip install trafilatura crawl4ai`), run the 5-page fixture set (local HTML fixtures under `tests/ds/fixtures/url_pages/`: article with nav/chrome, table-heavy page, list-heavy page, JS-shell page with `<noscript>` fallback text, non-HTML-served-as-HTML edge case) through `trafilatura.extract(html, output_format="markdown", include_tables=True, include_links=True, include_images=False, url=url)` and through Crawl4AI `AsyncWebCrawler` with `result.markdown.fit_markdown` capture (NOT a top-level attribute — the fit path lives at `result.markdown.fit_markdown`; file:// or raw-html config, no live fetch). Score: markdown cleanliness (nav dropped, tables/lists preserved), citations/footnotes presence, no-LLM-needed structured path (CSS selector extraction availability), Ollama-native structured extraction availability, dep weight + license (trafilatura GPL-3.0 vs Crawl4AI Apache-2.0). Record the decision table as a module docstring + `digisearch/ARCHITECTURE.md` paragraph in the same diff; the table MUST show Crawl4AI selected by default with trafilatura listed as "rejected pending explicit legal sign-off". Implement `extract_markdown(html, url) -> tuple[str, str]` on Crawl4AI with trafilatura documented as rejected; empty/whitespace input returns `("", "crawl4ai")`; never raises on malformed HTML (try/except → `""`). Crawl4AI runs local-only (no cloud API key, Ollama endpoint configurable, sync wrapper over its async API via `asyncio.run` in a dedicated function so callers stay sync like `HttpFetcher`). Crawl4AI's browser-install step (`crawl4ai-setup` at dev/image setup) is documented in the module docstring + ARCHITECTURE paragraph, and the import stays behind the `url-ingest` extra so base `import digifetch` keeps the browser-free boundary.

Deliverable: extraction decision recorded (Crawl4AI default) + `extract_markdown` returning clean markdown for all 5 fixtures.

Verify:

```bash
pytest tests/ds/test_readability_extract.py -v
ruff check digisearch/src/digisearch/extract/readability.py tests/ds/test_readability_extract.py && ruff format --check digisearch/src/digisearch/extract/readability.py tests/ds/test_readability_extract.py
```

### Task 3 — `ingest_url()` fetch→stage→ingest (`url_ingest.py`)

How: new file `digisearch/src/digisearch/pipeline/url_ingest.py`. `fetch()` NEVER checks `max_bytes` (see `digifetch/src/digifetch/http.py:162` — the cap exists only in `download()`, `http.py:197`), so the byte-cap path MUST be fetch-via-`download()`+decode, never `fetch()`. Flow: `assert_url_allowed(url, policy)` → construct `HttpFetcher(timeout=policy.timeout_s, max_bytes=policy.max_bytes, follow_redirects=False)` (new ctor arg from the digifetch change below; injected `fetcher` param takes precedence for tests with `httpx.MockTransport`) → manual redirect loop: `with_retry(lambda: fetcher.download(current, headers={"User-Agent": policy.user_agent}), RetryPolicy(attempts=3, base_delay=1.0, factor=2.0, max_delay=8.0, retry_on=(httpx.TimeoutException, httpx.ConnectError), sleep=<injected>), description="url_ingest fetch")` → on 3xx (301/302/303/307/308) read `Location` from the result headers, resolve relative targets with `urllib.parse.urljoin`, re-validate via `assert_url_allowed` (cap 5 hops, code `url_too_many_redirects`, 502) — a redirect to link-local/private MUST raise `UrlFetchError`, never escape — then decode bytes to text (charset from content-type, fallback utf-8 w/ errors="replace") → reject non-2xx (mapped to `UrlFetchError` code `url_fetch_status`, 502) and non-text content-types (allow `text/*`, `application/xhtml+xml`; code `url_content_rejected`, 415) → `extract_markdown(html, final_url)` → stage markdown to `tempfile` dir under `DIGISEARCH_URL_STAGING_DIR` (default `tempfile.gettempdir()/digisearch-url-staging` — `tempfile`, NOT `shutil`, which has no `gettempdir`; mode 0o700, filename `sha256(final_url)[:16] + ".md"`) → `ingest_source(staged_path, index_name=..., metadata={**(metadata or {}), "source_url": final_url, "evidence_tier": "web"}, chunker_name=..., embedding_provider=...)`. Metadata merge order: caller metadata wins over `source_url`/`evidence_tier` defaults only if caller explicitly sets those keys. Temp file removed in `finally`. Byte cap enforced by `download()` raising `DownloadTooLargeError` → mapped to `UrlFetchError` code `url_too_large`, 413 (this mapping is load-bearing for the ban-lift safety case). Retry-path tests inject `sleep=lambda _: None`. This module + `url_policy.py` are the sanctioned exception to the digisearch AGENTS.md single-filesystem-ingest-path rule (recorded in the Task 7 AGENTS.md amendment).

Required digifetch change (same task, separate diff + review): `HttpFetcher.__init__` gains `follow_redirects: bool = True` (default preserves current behavior; url_ingest passes `False`), and `FetchResult`/`DownloadResult` gain `headers: dict[str, str]` (default `{}`) carrying response headers so the manual loop can read `Location` without a second request. Tests in `digifetch/tests/test_http_redirect.py` (MockTransport: 302→private-IP target must surface headers and NOT auto-follow when `follow_redirects=False`; cap path in `download()` unchanged).

Deliverable: URL → chunks in index via existing `ingest_source`, offline-tested end to end with mocked transport.

Verify:

```bash
pytest tests/ds/test_url_ingest.py tests/ds/test_url_policy.py -v
pytest digifetch/tests/test_http_redirect.py -v
ruff check digisearch/src/digisearch/pipeline/url_ingest.py && ruff format --check digisearch/src/digisearch/pipeline/url_ingest.py
```

### Task 4 — SearXNG row mapper (`mapping.py`)

How: new file `digisearch/src/digisearch/web_providers/mapping.py` with pure function `searxng_rows_to_web_search_data()` per Interfaces. Row mapping: `url=str(it["url"])`, `title=str(it.get("title") or "")`, `highlights=[str(it.get("content") or "")]` when content non-empty, `publishedDate` passed through only when present and non-empty, `engine=str(it.get("engine") or "searxng")`, `id=url`, `score=float(it.get("score") or 0.0)`. Sort by score desc, drop rows with empty url, cap at caller's `num_results` (param, default 8). Domain include/exclude filtering uses substring-suffix host match identical to the 09-10 draft `apply_domain_filter` semantics (host == domain or endswith "." + domain, casefolded) — reimplemented here on dict rows, not imported from a non-existent module. `output` is `None` when no degradation, else `{"provider": "searxng", "degraded": [...], "note": "single-IP engines CAPTCHA-walled; results are DuckDuckGo-flavored"}`. `cost_dollars={"total": 0.0, "provider": "searxng", "breakdown": {"searches": 1, "pages_fetched": 0, "llm_calls": 0}, "note": "self-hosted; total is advisory, not billed"}` always.

Deliverable: pure mapper with EXA-shape parity proven against §0 fixtures (replay `s1_auto.json` result dicts through the mapper shape assertion).

Verify:

```bash
pytest tests/ds/test_searxng_mapping.py -v
ruff check digisearch/src/digisearch/web_providers/mapping.py tests/ds/test_searxng_mapping.py && ruff format --check digisearch/src/digisearch/web_providers/mapping.py tests/ds/test_searxng_mapping.py
```

### Task 5 — `SearXNGBackend.query()` + degraded mode (`searxng.py`)

How: new file `digisearch/src/digisearch/web_providers/searxng.py`. `SearXNGConfig.from_env()` reads `DIGISEARCH_SEARXNG_URL` (default `http://127.0.0.1:8080`) at call time. `query()` calls `self._limiter.acquire()` first (module-level `RateLimiter(min_interval=1.0)` default; injectable for tests — this wires the SearXNG politeness claim; no limiter, no claim), then issues `GET {base}/search` with params `q, format=json, pageno=1, language=en, safesearch=1, categories=general, time_range=<category news ? "month" : omit>`; on non-2xx raises `SearXNGDegradedError` (never returns partial rows silently). Degraded-mode detection reads BOTH envelope keys — `unresponsiveEngines` (camelCase, current SearXNG) and `unresponsive_engines` (snake_case, tolerant alias): entries for `google`/`brave`/`bing` in either → `degraded_engines` list passed to mapper; per-row engine provenance preserved so callers can see the DuckDuckGo flavor (`engine` values `duckduckgo`, `wikipedia`, `marginalia`, etc. pass through verbatim). Injected `httpx.Client` (MockTransport) for tests; when `client is None`, construct `httpx.Client(timeout=config.timeout_s)` and close in `finally`. No retry inside (caller composes `with_retry` with injected no-op sleep in tests); no EXA import (fallback is the caller's explicit branch on `SearXNGDegradedError`, documented in docstring with a 6-line example). Also create `web_providers/models.py` (`Citation` + `normalize_url`, per Interfaces/R5) in this task if not already landed — B/D convergence has no owner otherwise; mapper imports `normalize_url` for row-URL normalization.

Deliverable: live-web query backend returning `WebSearchData`, sidecar-down raising `SearXNGDegradedError`, all offline-tested.

Verify:

```bash
pytest tests/ds/test_searxng_backend.py tests/ds/test_searxng_mapping.py -v
ruff check digisearch/src/digisearch/web_providers/ tests/ds/test_searxng_backend.py && ruff format --check digisearch/src/digisearch/web_providers/ tests/ds/test_searxng_backend.py
```

### Task 6 — Service surface: `POST /ingest/url`, `GET /v1/web_providers`, CLI, manifest copy

How: in `server.py`, add `POST /ingest/url` handler calling `ingest_url()` with `enforce_ingest_root` N/A (URL path, not filesystem — state this in a code comment so the AGENTS.md path-jail rule is visibly satisfied by the SSRF jail instead), mapping `UrlFetchError.http_status` via `HTTPException` exactly like `api_ingest` does; add `GET /v1/web_providers` probing SearXNG with a 2s `httpx` timeout (unreachable → `configured: False`, never raises) and EXA via `is_exa_configured()`. In `cli.py`, add `ingest-url` command calling `ingest_url()` and printing `doc_id/chunks_created/extractor`. In `orchestrator_tools.py`, extend `build_web_search_tool()` description with "Providers: `exa` (paid, high-recall, needs EXA_API_KEY) and `searxng` (self-hosted, same WebSearchData shape, may degrade to DuckDuckGo-flavored results on single-IP instances)." plus additive `provider` enum `["auto", "exa", "searxng"]` default `"auto"`. No dispatch change (invoke still routes `exa` until a later phase wires `searxng`).

Deliverable: HTTP + CLI surfaces independently exercisable against mocked backends, proven by the new `tests/ds/test_url_ingest_api.py` (carries `@pytest.mark.unit`): FastAPI `TestClient` route tests for `POST /ingest/url` (ok + `UrlFetchError` status mapping) and `GET /v1/web_providers` (sidecar-up/sidecar-down/EXA-configured matrix), Typer `CliRunner` test for `ingest-url`, and a manifest assertion that `build_web_search_tool()` exposes the additive `provider` enum with default `"auto"` and unchanged `required: ["query"]`.

Verify:

```bash
pytest tests/ds/test_url_ingest_api.py -v
pytest tests/ds/test_url_ingest.py tests/ds/test_searxng_backend.py -v
ruff check digisearch/src/digisearch/server.py digisearch/src/digisearch/cli.py digisearch/src/digisearch/orchestrator_tools.py && ruff format --check digisearch/src/digisearch/server.py digisearch/src/digisearch/cli.py digisearch/src/digisearch/orchestrator_tools.py
```

### Task 7 — Ops + docs: compose sidecar, settings.yml, extras, ban-lift record

How: append loopback-only `searxng` (image pinned by digest at implementation time — resolve the digest then, record it; `ports: ["127.0.0.1:8080:8080"]`, read-only `settings.yml` mount) + `valkey` (image tag pinned, e.g. `valkey/valkey:8.1-alpine` — never `:latest`) services to `docker-compose.yml`; write `config/searxng/settings.yml` with `search.formats: [html, json]`, `server.secret_key` set by the operator via `openssl rand -hex 32` (run this command, paste output — no placeholder/empty secret ships), engine allowlist (`duckduckgo, wikipedia, marginalia, brave, google, bing` with comment that single-IP instances expect google/brave CAPTCHA walls). In `digisearch/pyproject.toml`, add `url-ingest = ["crawl4ai==<pinned>"]` (Crawl4AI default, Apache-2.0; trafilatura entry present ONLY as a commented line noting GPL-3.0 needs explicit legal sign-off for closed distributions) and extend `dev` to include the winner so CI exercises it. Add the six new vars to `.env.example` (`DIGISEARCH_URL_MAX_BYTES`, `DIGISEARCH_URL_TIMEOUT_S`, `DIGISEARCH_URL_ALLOW_PRIVATE_IPS`, `DIGISEARCH_URL_BLOCKED_HOSTS`, `DIGISEARCH_URL_STAGING_DIR`, `DIGISEARCH_SEARXNG_URL` with defaults matching `from_env()`). In `digisearch/ARCHITECTURE.md` (§3 routes, §5 modules) document `POST /ingest/url`, `GET /v1/web_providers`, `SearXNGBackend`, extraction decision (Crawl4AI default + browser-install step), degraded-mode table (engine → expected behavior single-IP vs proxy-pooled). In `digisearch/AGENTS.md`, amend the ingest-source rule: "…Never accept a raw URL in `POST /ingest source`; URL ingest goes through `POST /ingest/url` → `pipeline.url_ingest.ingest_url` (SSRF jail + byte cap + sandbox staging), which satisfies the fetch + sandboxing precondition. `pipeline/url_ingest.py` + `pipeline/url_policy.py` are the only sanctioned non-filesystem ingest modules."

Deliverable: `docker compose up searxng valkey` serves `GET http://127.0.0.1:8080/search?q=test&format=json`; docs record the ban lift.

Verify:

```bash
docker compose up -d searxng valkey && curl -s "http://127.0.0.1:8080/search?q=test&format=json" | head -c 500
pytest tests/ -m unit -k "digisearch" -v
ruff check digisearch/ && ruff format --check digisearch/
```

## Open risks / cross-phase contract risks

1. The 09-10 draft's invented envelope names do not exist in code and MUST NOT be revived — any later phase importing those names will fail at import; scope the review grep to the exact symbols, e.g. `rg -n "WebSearchResult|WebSearchResponse" --include '*.py' digisearch/src tests/ds`.
2. `SearXNGBackend.query()` signature intentionally differs from `exa_search()` (provider-neutral args vs EXA-native args); the later-phase unified router must adapt, not rename Phase A surfaces.
3. trafilatura is GPL-3.0: it ships ONLY behind explicit legal sign-off (commented extra + ARCHITECTURE.md flag); the default path (Crawl4AI, Apache-2.0) avoids this. Verify no active trafilatura dep with `rg -n "^[^#]*trafilatura" --include '*.toml' digisearch/`.
4. Single-IP SearXNG recall will underperform EXA on Google/Brave-dependent queries — degraded-mode flagging is load-bearing for honest evals; later phases must not silently blend degraded rows with owned-corpus hits.
