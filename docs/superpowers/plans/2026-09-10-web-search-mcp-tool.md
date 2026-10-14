# Web Search MCP Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a first-party, open-source web-search tool owned by digisearch and backed by digifetch transport, and wire it as the default web-search service in digichat→digigraph, digillm, and digiquant.

**Architecture:** New `digisearch.web_search` module (Pydantic v2 provider protocol + SearXNG primary / ddgs fallback + trafilatura primary / readability fallback) exposed over existing digisearch HTTP 8002 + MCP 8765 + orchestrator manifest; digigraph handler tries tool first with Gemini-completion fallback; digillm splits telemetry; digiquant enforces real domain filtering. No new port, no digifetch server.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, FastMCP (mcp>=1.2,<2), SearXNG sidecar + valkey, ddgs, trafilatura, readability-lxml + markdownify, digifetch HttpFetcher/with_retry/RateLimiter, ruff line-length 100.

**Spec:** digithings-ai/digithings#3853 + CHR-468; companion #3852 baseline embed defaults; invariant #3420 (opt-in, default-off, fail-closed, External-tier only).

## Global Constraints

- Python 3.12, Pydantic v2 everywhere, strict typing, ruff line-length 100, `ruff check + format --check` zero errors.
- Polars only, never pandas.
- Digi product names always lowercase in prose/docs/commits (`digisearch`, `digigraph`, `digillm`, `digifetch`, `digichat`, `digiquant`).
- MCP-first: every capability is a discoverable tool; register in orchestration registry, never logic directly in LangGraph node.
- digigraph must never `import digisearch` or `digiquant` Python modules; all vertical calls via `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke`.
- digifetch stays library-only: no fastapi/Request/port/uvicorn, no `os.environ`, no `parse_*`/selectors/URLs, no `requests`, no bare `time.sleep(<literal>)`, no bare dicts from public functions, browser-free import.
- Auth fail-closed: new routes inherit `DigiAuthMiddleware` + `digisearch:query` scope; MCP stays loopback-only `127.0.0.1:8765`; never expose beyond loopback without gateway auth/TLS.
- #3420 invariant: web_search request-opt-in only, default-off, External supplement never replaces corpus hits, `web_search` excluded from force-tool.
- Every change traces to issue #3853 (`task/3853-slug` branch or `Fixes #3853` in PR body); update per-component `ARCHITECTURE.md` on interface change.
- Human gate: new network-capable deps + new external service dep require human review; do not merge those without it.

---

### Task 1: Web-search models + provider protocol

**Files:**
- Create: `digisearch/src/digisearch/web_search/__init__.py`
- Create: `digisearch/src/digisearch/web_search/models.py`
- Create: `digisearch/tests/test_web_search_models.py`

**Interfaces:**
- Consumes: `digisearch.retrieval.backend.RetrievalResult` pattern (document_id/content/score/metadata/source) as naming precedent only.
- Produces: `WebSearchResult{url,title,snippet,score,engine}`, `WebSearchResponse{query,results,provider}`, `WebSearchRequest{query,include_domains,exclude_domains,max_results,recency_days}` used by Tasks 2-5.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse

def test_request_defaults_fail_closed():
    req = WebSearchRequest(query="bitcoin etf flows")
    assert req.max_results == 4
    assert req.include_domains == []
    assert req.exclude_domains == []

def test_domain_filter_helper():
    from digisearch.web_search.models import apply_domain_filter
    results = [
        {"url": "https://a.com/x", "title": "a", "snippet": "s"},
        {"url": "https://evil.com/x", "title": "e", "snippet": "s"},
    ]
    kept = apply_domain_filter(results, include_domains=["a.com"], exclude_domains=["evil.com"])
    assert [r["url"] for r in kept] == ["https://a.com/x"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_models.py -v`
Expected: FAIL with "No module named 'digisearch.web_search'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Web-search Pydantic models for #3853."""
from __future__ import annotations
from urllib.parse import urlparse
from pydantic import BaseModel, Field

class WebSearchResult(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    engine: str = ""

class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult] = Field(default_factory=list)
    provider: str = ""

class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    include_domains: list[str] = Field(default_factory=list, max_length=5)
    exclude_domains: list[str] = Field(default_factory=list, max_length=20)
    max_results: int = Field(default=4, ge=1, le=10)
    recency_days: int | None = Field(default=7, ge=1, le=365)

def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""

def apply_domain_filter(
    results: list[dict],
    *,
    include_domains: list[str],
    exclude_domains: list[str],
) -> list[dict]:
    inc = {d.lower() for d in include_domains}
    exc = {d.lower() for d in exclude_domains}
    kept: list[dict] = []
    for r in results:
        h = _host(str(r.get("url", ""))).lower()
        if exc and any(h == d or h.endswith("." + d) for d in exc):
            continue
        if inc and not any(h == d or h.endswith("." + d) for d in inc):
            continue
        kept.append(r)
    return kept
```

```python
"""digisearch.web_search package."""
from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
)
__all__ = ["WebSearchRequest", "WebSearchResponse", "WebSearchResult", "apply_domain_filter"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digisearch/tests/test_web_search_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/web_search/__init__.py digisearch/src/digisearch/web_search/models.py digisearch/tests/test_web_search_models.py
git commit -m "feat(digisearch): add web-search request/response models"
```

---

### Task 2: ddgs embedded fallback provider (MIT, zero-ops)

**Files:**
- Create: `digisearch/src/digisearch/web_search/ddgs_provider.py`
- Test: `digisearch/tests/test_web_search_ddgs.py`

**Interfaces:**
- Consumes: `WebSearchRequest`, `WebSearchResponse`, `apply_domain_filter` from Task 1.
- Produces: `DdgsWebSearchProvider.search(req) -> WebSearchResponse` used by Task 5 registry.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.models import WebSearchRequest

class FakeDDGS:
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def text(self, query, max_results=4, **kw):
        return [
            {"href": "https://a.com/1", "title": "A1", "body": "snippet one"},
            {"href": "https://evil.com/2", "title": "E", "body": "bad"},
        ]

def test_ddgs_maps_and_filters(monkeypatch):
    import digisearch.web_search.ddgs_provider as mod
    monkeypatch.setattr(mod, "DDGS", FakeDDGS)
    p = DdgsWebSearchProvider()
    resp = p.search(WebSearchRequest(query="etf flows", include_domains=["a.com"]))
    assert resp.provider == "ddgs"
    assert [r.url for r in resp.results] == ["https://a.com/1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_ddgs.py -v`
Expected: FAIL with "No module named" / "cannot import DdgsWebSearchProvider"

- [ ] **Step 3: Write minimal implementation**

```python
"""ddgs embedded provider (MIT fallback, zero infra) for #3853."""
from __future__ import annotations
from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
)

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - import guard for unit envs
    DDGS = None  # type: ignore[assignment]

class DdgsUnavailableError(RuntimeError):
    pass

class DdgsWebSearchProvider:
    """DuckDuckGo-scrape provider via ddgs with auto-backend failover."""

    name = "ddgs"

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        if DDGS is None:
            raise DdgsUnavailableError("ddgs package not installed")
        rows: list[dict] = []
        with DDGS() as ddgs:
            for row in ddgs.text(req.query, max_results=req.max_results) or []:
                rows.append(
                    {
                        "url": str(row.get("href", "")),
                        "title": str(row.get("title", "")),
                        "snippet": str(row.get("body", "")),
                    }
                )
        rows = apply_domain_filter(
            rows, include_domains=req.include_domains, exclude_domains=req.exclude_domains
        )
        results = [
            WebSearchResult(url=r["url"], title=r["title"], snippet=r["snippet"], engine="ddgs")
            for r in rows[: req.max_results]
            if r["url"]
        ]
        return WebSearchResponse(query=req.query, results=results, provider=self.name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digisearch/tests/test_web_search_ddgs.py digisearch/tests/test_web_search_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/web_search/ddgs_provider.py digisearch/tests/test_web_search_ddgs.py
git commit -m "feat(digisearch): add ddgs embedded web-search provider"
```

Note: add `ddgs` as optional extra in `digisearch/pyproject.toml` in Task 5, not as hard dep. Human gate applies (network-capable dep).

---

### Task 3: SearXNG sidecar provider (AGPL sidecar, primary)

**Files:**
- Create: `digisearch/src/digisearch/web_search/searxng_provider.py`
- Test: `digisearch/tests/test_web_search_searxng.py`

**Interfaces:**
- Consumes: `WebSearchRequest/Response`, `apply_domain_filter` from Task 1; `httpx` only (never `requests`).
- Produces: `SearXNGWebSearchProvider.search(req) -> WebSearchResponse` used by Task 5.

- [ ] **Step 1: Write the failing test**

```python
import httpx
from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider

def test_searxng_json_mapping():
    payload = {"results": [
        {"url": "https://a.com/1", "title": "A", "content": "c1", "score": 2.0},
        {"url": "https://b.com/2", "title": "B", "content": "c2", "score": 1.0},
    ]}
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["format"] == "json"
        assert request.url.params["q"] == "etf flows"
        return httpx.Response(200, json=payload)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = SearXNGWebSearchProvider(base_url="http://127.0.0.1:8080", client=client)
    resp = p.search(WebSearchRequest(query="etf flows"))
    assert resp.provider == "searxng"
    assert resp.results[0].url == "https://a.com/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_searxng.py -v`
Expected: FAIL with "No module named 'digisearch.web_search.searxng_provider'"

- [ ] **Step 3: Write minimal implementation**

```python
"""SearXNG sidecar provider (primary) for #3853."""
from __future__ import annotations
import httpx
from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
)

class SearXNGWebSearchProvider:
    name = "searxng"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        params = {
            "q": req.query,
            "format": "json",
            "pageno": 1,
            "language": "en",
            "safesearch": 1,
        }
        close = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self._timeout)
            close = True
        try:
            r = client.get(f"{self._base}/search", params=params)
            r.raise_for_status()
            items = (r.json().get("results", []) or [])[: req.max_results * 2]
        finally:
            if close:
                client.close()
        rows = [
            {"url": str(it.get("url", "")), "title": str(it.get("title", "")),
             "snippet": str(it.get("content", "")), "score": float(it.get("score", 0.0) or 0.0),
             "engine": str(it.get("engine", ""))}
            for it in items
        ]
        rows = apply_domain_filter(
            rows, include_domains=req.include_domains, exclude_domains=req.exclude_domains
        )
        rows = sorted(rows, key=lambda d: float(d.get("score", 0.0) or 0.0), reverse=True)
        results = [
            WebSearchResult(url=d["url"], title=d["title"], snippet=d["snippet"],
                            score=float(d.get("score", 0.0) or 0.0), engine=str(d.get("engine", "searxng")))
            for d in rows[: req.max_results] if d["url"]
        ]
        return WebSearchResponse(query=req.query, results=results, provider=self.name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digisearch/tests/test_web_search_searxng.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/web_search/searxng_provider.py digisearch/tests/test_web_search_searxng.py
git commit -m "feat(digisearch): add searxng sidecar web-search provider"
```

---

### Task 4: HTML→markdown extractor (trafilatura primary, readability fallback)

**Files:**
- Create: `digisearch/src/digisearch/web_search/extractor.py`
- Test: `digisearch/tests/test_web_search_extractor.py`

**Interfaces:**
- Consumes: raw HTML `str` from `digifetch.HttpFetcher.fetch().text` (caller in Task 5, not here).
- Produces: `extract_markdown(html, url) -> str` used by Task 5 fetch path.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web_search.extractor import extract_markdown

HTML = "<html><body><nav>menu</nav><article><h1>T</h1><p>Hello <b>world</b></p><ul><li>a</li></ul></article></body></html>"

def test_extract_markdown_keeps_content_drops_nav():
    md = extract_markdown(HTML, url="https://a.com/1")
    assert "Hello" in md
    assert "menu" not in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_extractor.py -v`
Expected: FAIL with "No module named 'digisearch.web_search.extractor'"

- [ ] **Step 3: Write minimal implementation**

```python
"""HTML to clean markdown for #3853. trafilatura primary, readability fallback."""
from __future__ import annotations

def _via_trafilatura(html: str, url: str) -> str | None:
    try:
        from trafilatura import extract
    except Exception:
        return None
    try:
        out = extract(html, output_format="markdown", include_tables=True,
                      include_links=True, include_images=False, url=url)
    except Exception:
        return None
    return out if out and out.strip() else None

def _via_readability(html: str) -> str | None:
    try:
        from readability import Document
        from markdownify import markdownify as md
    except Exception:
        return None
    try:
        summary = Document(html).summary()
        if not summary or not summary.strip():
            return None
        return md(summary, heading_style="ATX").strip() or None
    except Exception:
        return None

def extract_markdown(html: str, url: str = "") -> str:
    if not html or not html.strip():
        return ""
    return _via_trafilatura(html, url) or _via_readability(html) or ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digisearch/tests/test_web_search_extractor.py -v`
Expected: PASS (installs trafilatura or readability in dev env; at least one path returns markdown)

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/web_search/extractor.py digisearch/tests/test_web_search_extractor.py
git commit -m "feat(digisearch): add html to markdown extractor"
```

License note: trafilatura is GPLv3 — needs legal sign-off for closed distributions; readability+markdownify (Apache-2.0/MIT) is the permissive fallback already wired above. Human gate applies to both new deps.

---

### Task 5: digisearch service wiring (registry + HTTP + MCP + config + compose)

**Files:**
- Create: `digisearch/src/digisearch/web_search/service.py`
- Modify: `digisearch/src/digisearch/orchestrator_tools.py` (add `web_search` to manifest)
- Modify: `digisearch/src/digisearch/mcp_server.py` (add `web_search` tool)
- Modify: `digisearch/src/digisearch/server.py` (add `POST /v1/web_search` route with `digisearch:query` scope)
- Modify: `digisearch/pyproject.toml` (optional extras `web-search`)
- Modify: `docker-compose.yml` (searxng + valkey loopback sidecar)
- Modify: `digisearch/ARCHITECTURE.md` (new module section)
- Test: `digisearch/tests/test_web_search_service.py`

**Interfaces:**
- Consumes: Tasks 1-4 (`WebSearchRequest/Response`, both providers, `extract_markdown`) + `digifetch.HttpFetcher/with_retry/RateLimiter` as transport (composed, never embedded flags).
- Produces: `run_web_search(req) -> WebSearchResponse`, HTTP `POST /v1/web_search`, MCP `web_search`, orchestrator tool `web_search` consumed by Task 6.

- [ ] **Step 1: Write the failing test**

```python
from digisearch.web_search.models import WebSearchRequest
from digisearch.web_search.service import run_web_search, WebSearchConfig

def test_service_prefers_searxng_falls_back_to_ddgs(monkeypatch):
    from digisearch.web_search import service as svc
    def boom(req):
        raise RuntimeError("searxng down")
    class Ok:
        name = "ddgs"
        def search(self, req):
            from digisearch.web_search.models import WebSearchResponse, WebSearchResult
            return WebSearchResponse(query=req.query, provider="ddgs",
                results=[WebSearchResult(url="https://a.com/1", title="A", snippet="s")])
    monkeypatch.setattr(svc, "SearXNGWebSearchProvider", lambda **k: type("S", (), {"search": staticmethod(boom), "name": "searxng"})())
    monkeypatch.setattr(svc, "DdgsWebSearchProvider", Ok)
    resp = run_web_search(WebSearchRequest(query="etf"), config=WebSearchConfig(backend="auto"))
    assert resp.provider == "ddgs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_service.py -v`
Expected: FAIL with "No module named 'digisearch.web_search.service'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Service orchestration for #3853: search -> fetch via digifetch -> extract."""
from __future__ import annotations
import os
from pydantic import BaseModel
from digifetch import HttpFetcher, RateLimiter, RetryPolicy, with_retry
from digisearch.web_search.ddgs_provider import DdgsWebSearchProvider
from digisearch.web_search.extractor import extract_markdown
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult
from digisearch.web_search.searxng_provider import SearXNGWebSearchProvider

class WebSearchConfig(BaseModel):
    backend: str = "auto"
    searxng_url: str = "http://127.0.0.1:8080"
    fetch_max_pages: int = 3
    fetch_timeout: float = 15.0
    min_interval_s: float = 1.0

    @classmethod
    def from_env(cls) -> "WebSearchConfig":
        return cls(
            backend=os.environ.get("DIGISEARCH_WEB_SEARCH_BACKEND", "auto"),
            searxng_url=os.environ.get("DIGISEARCH_SEARXNG_URL", "http://127.0.0.1:8080"),
        )

_limiter = RateLimiter(min_interval=1.0)

def _search_only(req: WebSearchRequest, config: WebSearchConfig) -> WebSearchResponse:
    last: Exception | None = None
    order = [config.backend] if config.backend in ("searxng", "ddgs") else ["searxng", "ddgs"]
    for name in order:
        try:
            if name == "searxng":
                return SearXNGWebSearchProvider(base_url=config.searxng_url).search(req)
            return DdgsWebSearchProvider().search(req)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError(f"all web-search backends failed: {last}")

def run_web_search(req: WebSearchRequest, config: WebSearchConfig | None = None) -> WebSearchResponse:
    config = config or WebSearchConfig.from_env()
    resp = _search_only(req, config)
    fetcher = HttpFetcher(timeout=config.fetch_timeout)
    policy = RetryPolicy(attempts=2, base_delay=1.0, factor=2.0, max_delay=5.0)
    enriched: list[WebSearchResult] = []
    for hit in resp.results[: config.fetch_max_pages]:
        try:
            _limiter.acquire()
            fetched = with_retry(lambda: fetcher.fetch(hit.url), policy, description="web_search fetch")
            md = extract_markdown(fetched.text or "", url=hit.url)
            enriched.append(hit.model_copy(update={"snippet": md[:2000] if md else hit.snippet}))
        except Exception:
            enriched.append(hit)
    rest = resp.results[config.fetch_max_pages:]
    return WebSearchResponse(query=resp.query, results=enriched + rest, provider=resp.provider)
```

MCP + HTTP + manifest follow existing patterns (do not invent new auth):
```python
# mcp_server.py addition
@mcp.tool()
def web_search(query: str, include_domains: list[str] = [], exclude_domains: list[str] = [], max_results: int = 4) -> str:
    """Search the public web (first-party tool). Returns JSON WebSearchResponse."""
    from digisearch.web_search.models import WebSearchRequest
    from digisearch.web_search.service import run_web_search
    return run_web_search(WebSearchRequest(query=query, include_domains=include_domains, exclude_domains=exclude_domains, max_results=max_results)).model_dump_json()
```

```python
# server.py addition (inside existing app, same DigiAuthMiddleware + digisearch:query scope)
@app.post("/v1/web_search")
def v1_web_search(req: WebSearchRequest):
    return run_web_search(req).model_dump()
```

```yaml
# docker-compose.yml addition (loopback-only sidecar)
searxng:
  image: searxng/searxng:2026.9.5
  ports: ["127.0.0.1:8080:8080"]
  volumes: ["./config/searxng/settings.yml:/etc/searxng/settings.yml:ro"]
  depends_on: [valkey]
valkey:
  image: valkey/valkey:9-alpine
```

`settings.yml` must set `search.formats: [html, json]` plus `server.secret_key` and engine allowlist.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest digisearch/tests/test_web_search_service.py digisearch/tests/test_web_search_models.py digisearch/tests/test_web_search_ddgs.py digisearch/tests/test_web_search_searxng.py digisearch/tests/test_web_search_extractor.py -v`
Expected: PASS
Run: `ruff check digisearch/src/digisearch/web_search/ && ruff format --check digisearch/src/digisearch/web_search/`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/web_search/service.py digisearch/src/digisearch/orchestrator_tools.py digisearch/src/digisearch/mcp_server.py digisearch/src/digisearch/server.py digisearch/pyproject.toml docker-compose.yml digisearch/ARCHITECTURE.md digisearch/tests/test_web_search_service.py
git commit -m "feat(digisearch): wire web-search service over http mcp orchestrator"
```

---

### Task 6: digigraph caller swap (tool-first, synthesis fallback)

**Files:**
- Modify: `digigraph/src/digigraph/orchestration/web_search_tools.py:42-111` (`_handle_web_search`)
- Modify: `digigraph/src/digigraph/llm_client.py` (add `digifetch_web_search` primitive honoring domain params; keep `usage_kind="web_search"`, `CallPurpose.WEB_GROUNDING` for rewrite + `CallPurpose.WEB_SEARCH` for tool)
- Test: `tests/digigraph/test_web_search_tool.py` (update existing)

**Interfaces:**
- Consumes: Task 5 `POST /v1/web_search` + `POST /v1/orchestrator_invoke {tool: web_search}` via existing `vertical_orchestrator/digisearch_hub.py` (never `import digisearch`).
- Produces: same `{content, results[doc_id/content/rank/metadata.evidence_tier=External], rag_sources, name}` shape so downstream `rag_sources` trace + `hit_count/query` logic unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_handle_web_search_prefers_tool(monkeypatch):
    from digigraph.orchestration import web_search_tools as mod
    ctx = type("C", (), {"state": {"enable_web_search": True}})()
    monkeypatch.setattr(mod, "_call_digisearch_web_search", lambda q, **k: {
        "content": "md bullets", "results": [{"doc_id": "https://a.com/1", "content": "md",
         "rank": 0, "metadata": {"title": "A", "source_url": "https://a.com/1",
         "evidence_tier": "External", "source_kind": "external"}}]})
    out = mod._handle_web_search({"query": "etf flows"}, ctx)
    assert out["results"][0]["doc_id"] == "https://a.com/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/digigraph/test_web_search_tool.py -v`
Expected: FAIL with "_call_digisearch_web_search not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def _call_digisearch_web_search(query: str, include_domains=None, exclude_domains=None, max_results: int = 4):
    from digigraph.vertical_orchestrator.digisearch_hub import invoke_digisearch_tool
    return invoke_digisearch_tool("web_search", {"query": query,
        "include_domains": include_domains or [], "exclude_domains": exclude_domains or [],
        "max_results": max_results})

def _handle_web_search(args, context):
    if not _web_search_available(context):
        return {"error": "tool_not_allowed", "tool": WEB_SEARCH_TOOL_NAME,
                "message": "web_search is opt-in and disabled for this session."}
    query = str(args.get("query", "")).strip()
    if not query:
        return "No search query provided."
    try:
        tool_out = _call_digisearch_web_search(query,
            include_domains=args.get("include_domains"), exclude_domains=args.get("exclude_domains"),
            max_results=int(args.get("max_results", 4)))
        if tool_out and tool_out.get("results"):
            return {"content": tool_out.get("content", ""), "results": tool_out["results"][:8],
                    "rag_sources": rag_sources_from_results(tool_out["results"][:8]),
                    "name": WEB_SEARCH_TOOL_NAME}
    except Exception:
        pass
    from digigraph.llm_client import openrouter_web_search
    from digigraph.llm_client import web_search as xai_web_search
    from digigraph.model_config import get_grounding_model, get_model_for_mode
    model = get_grounding_model() or get_model_for_mode()
    grounded = openrouter_web_search(model, query)
    if grounded is None:
        grounded = xai_web_search(model, query)
    if grounded is None:
        return {"content": "Web search returned no results.", "results": [], "rag_sources": [], "name": WEB_SEARCH_TOOL_NAME}
    summary, urls = grounded
    return {"content": summary, "results": urls, "rag_sources": rag_sources_from_results(urls), "name": WEB_SEARCH_TOOL_NAME}
```

Keep `WEB_SEARCH_TOOL` schema + `_web_search_available` + never-escalate `tool_policy.py` + `web_search` excluded from force-tool unchanged. Thread optional `include_domains/exclude_domains/max_results` through `models.py`, `chat_resolve.py`, `workflow.py`, `graph/state.py` only if v1 scope requires it; defaults preserve #3420 fail-closed.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/ -m unit -k "digigraph and web_search" -v`
Expected: PASS
Run: `ruff check digigraph/src/digigraph/orchestration/web_search_tools.py digigraph/src/digigraph/llm_client.py && ruff format --check digigraph/src/digigraph/orchestration/web_search_tools.py digigraph/src/digigraph/llm_client.py`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/orchestration/web_search_tools.py digigraph/src/digigraph/llm_client.py tests/digigraph/test_web_search_tool.py
git commit -m "feat(digigraph): prefer digisearch web-search tool with synthesis fallback"
```

---

### Task 7: digillm telemetry + routing split

**Files:**
- Modify: `digillm/src/digillm/client.py` (`completion(..., usage_kind)`, add `usage_kind="digifetch_web_search"` path)
- Modify: `digillm/src/digillm/telemetry.py` (emit `WEB_SEARCH` for tool call, `WEB_GROUNDING` for rewrite)
- Test: `digillm/tests/test_web_search_usage_kind.py` (new)

**Interfaces:**
- Consumes: Task 6 call path (tool vs synthesis distinction).
- Produces: cost-split telemetry consumed by digiquant provider accounting + `067_olympus_provider_telemetry.sql` allowlist (update if it enumerates purposes).

- [ ] **Step 1: Write the failing test**

```python
from digillm.telemetry import CallPurpose

def test_purposes_exist():
    assert CallPurpose.WEB_SEARCH.value == "web_search"
    assert CallPurpose.WEB_GROUNDING.value == "web_grounding"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digillm/tests/test_web_search_usage_kind.py -v`
Expected: FAIL if `WEB_SEARCH` missing, else adjust to assert `client.completion(usage_kind="digifetch_web_search")` records kind

- [ ] **Step 3: Write minimal implementation**

```python
# telemetry.py: ensure both members exist
class CallPurpose(str, Enum):
    WEB_SEARCH = "web_search"
    WEB_GROUNDING = "web_grounding"
    X_SEARCH = "x_search"
    X_GROUNDING = "x_grounding"

# client.py: pass through usage_kind unchanged, record as kind
def completion(self, *, usage_kind: str = "chat", **kw):
    return self._record_usage(kind=usage_kind, **kw)
```

Keep CheaperInference fail-fast + `DIGI_HOUSE_UPSTREAM` semantics; ensure `DIGIFETCH_*`/`DIGISEARCH_*` env never collides with `OPENAI_API_BASE` routing.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digillm/tests/test_web_search_usage_kind.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digillm/src/digillm/client.py digillm/src/digillm/telemetry.py digillm/tests/test_web_search_usage_kind.py
git commit -m "feat(digillm): split web-search tool vs grounding telemetry"
```

---

### Task 8: digiquant grounding swap + model-pin retirement

**Files:**
- Modify: `digiquant/src/digiquant/research/data/web_grounding.py` (`fetch_web_grounding`, keep `{summary,sources,as_of}` + `required` fail-hard)
- Modify: `digiquant/src/digiquant/research/data/ai_portfolios.py` (drop `openrouter/` prefix gate)
- Modify: `digiquant/src/digiquant/research/config/search_domains.yaml` (document as real `include_domains` contract)
- Modify: `config/digiquant_models.yaml` (point `web_search_models` at cheap synthesis-only pins)
- Modify: `digiquant/src/digiquant/dashboard/envcompat.py` (add `DIGISEARCH_*` canonical + alias entries)
- Test: `digiquant/tests/test_web_grounding.py` (update existing)

**Interfaces:**
- Consumes: Task 5 `run_web_search` via `digigraph.llm_client`-compatible return shape.
- Produces: same `apply_web_grounding_to_inputs()` + `grounding_absent` semantics so `_node_factory.py:build_grounding` + `thesis_grounding.py` inherit automatically.

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_web_grounding_uses_tool(monkeypatch):
    from digiquant.research.data import web_grounding as mod
    monkeypatch.setattr(mod, "call_web_search_tool", lambda **k: {"summary": "s", "sources": ["https://a.com/1"]})
    out = mod.fetch_web_grounding(model="cheap", segment="macro", run_date="2026-09-10", scope="test")
    assert out["sources"] == ["https://a.com/1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digiquant/tests/test_web_grounding.py -v`
Expected: FAIL with "call_web_search_tool not defined"

- [ ] **Step 3: Write minimal implementation**

```python
def call_web_search_tool(*, query: str, include_domains: list[str], max_results: int):
    from digisearch.web_search.models import WebSearchRequest
    from digisearch.web_search.service import run_web_search
    resp = run_web_search(WebSearchRequest(query=query, include_domains=include_domains, max_results=max_results))
    return {"summary": "\n".join(f"- [{r.title}]({r.url}): {r.snippet}" for r in resp.results),
            "sources": [r.url for r in resp.results]}

def fetch_web_grounding(*, model, segment, run_date, scope):
    from digiquant.research.data.web_grounding import _build_query, _domains_for, _openrouter_web_search
    query = _build_query(segment=segment, run_date=run_date, scope=scope)
    domains = _domains_for(segment)[:5]
    try:
        tool_out = call_web_search_tool(query=query, include_domains=domains, max_results=4)
        return {"summary": tool_out["summary"], "sources": tool_out["sources"], "as_of": run_date}
    except Exception:
        pass
    legacy = _openrouter_web_search(model=model, query=query)
    if legacy is None and dashboard_web_search_required():
        raise DashboardWebSearchError("web search required but unavailable")
    return legacy
```

Keep `DIGIQUANT_WEB_SEARCH|OLYMPUS_WEB_SEARCH` default `""` = fail-soft; keep stale-check `live_search_is_fallback` cost logic (now cheap-tool cost); update `search_domains.yaml` header comment from "maps to Exa allowed_domains" to "enforced include_domains for first-party web_search".

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digiquant/tests/test_web_grounding.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/research/data/web_grounding.py digiquant/src/digiquant/research/data/ai_portfolios.py digiquant/src/digiquant/research/config/search_domains.yaml config/digiquant_models.yaml digiquant/src/digiquant/dashboard/envcompat.py
git commit -m "feat(digiquant): use first-party web-search tool for grounding"
```

---

### Task 9: Baseline embed, docs, eval, rollout

**Files:**
- Modify: `frontend/digichat` baseline overlay only (`client-projection.ts`, `embed-client-config.ts`, `tool-catalog-bar.tsx`) — no default flip for `/chat` (#3420 preserved)
- Modify: `digisearch/ARCHITECTURE.md`, `digigraph/ARCHITECTURE.md`, `digiquant/ARCHITECTURE.md`, `config/MODELS.md`, `.env.example`
- Create: `digisearch/tests/test_web_search_eval.py` (20-query markdown-quality + latency harness, mocked by default, live behind `DIGISEARCH_WEB_SEARCH_LIVE=1`)
- Test: full gates

**Interfaces:**
- Consumes: Tasks 1-8.
- Produces: shippable default-ON for baseline slug, documented ops (compose pull cadence, secret_key, formats, engine allowlist), measured cost/latency win.

- [ ] **Step 1: Write the failing eval test**

```python
def test_eval_harness_runs_offline():
    from digisearch.tests.web_search_eval_cases import CASES
    assert len(CASES) >= 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digisearch/tests/test_web_search_eval.py -v`
Expected: FAIL with "No module named" / missing CASES

- [ ] **Step 3: Write minimal implementation**

Create `digisearch/tests/web_search_eval_cases.py` with 20 queries across news/macro/docs/earnings plus per-case `must_contain` substrings; harness asserts offline-mocked markdown path preserves tables/lists and p50 fetch+extract < 5s when live.

Update baseline prompt text to state digifetch-backed External-cite rule; keep BFF anti-spoof gate (empty-host=absent, baseline-tenant required) unchanged.

- [ ] **Step 4: Run all gates to verify they pass**

```bash
pytest digisearch/tests/test_web_search_models.py digisearch/tests/test_web_search_ddgs.py digisearch/tests/test_web_search_searxng.py digisearch/tests/test_web_search_extractor.py digisearch/tests/test_web_search_service.py -v
pytest tests/ -m unit -k "digigraph and web_search" -v
ruff check digisearch/src/digisearch/web_search/ digigraph/src/digigraph/orchestration/web_search_tools.py && ruff format --check digisearch/src/digisearch/web_search/ digigraph/src/digigraph/orchestration/web_search_tools.py
```

Expected: PASS, zero ruff errors. Then live smoke (requires `make stack-local`): baseline `/embed` with websearch ON returns External cites with real URLs; `/chat` default-off unchanged; one digiquant segment grounding e2e.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/deploy-config/client-projection.ts digisearch/ARCHITECTURE.md digigraph/ARCHITECTURE.md digiquant/ARCHITECTURE.md config/MODELS.md .env.example digisearch/tests/test_web_search_eval.py
git commit -m "feat(web-search): baseline default-on, docs, eval harness"
```

Rollout: single flag `DIGISEARCH_WEB_SEARCH_BACKEND=auto|searxng|ddgs|off`; fail-closed to corpus-only; monitor per-engine 403/CAPTCHA rates + Gemini traffic drop; `compose pull searxng` cadence weekly (upstream scraper breakage).
