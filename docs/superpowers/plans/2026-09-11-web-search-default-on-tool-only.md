# Web Search Default-ON + Pipeline Tool-Only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Web search is zero-click ON everywhere except the DataTap tenant (explicitly OFF), and the digiquant pipeline uses only the first-party tool with loud abort on failure — green always means the tool worked end-to-end.

**Architecture:** New `digibase.service_auth` helper exchanges a provisioned machine key at digikey (`grant_type=api_key`) for a short-lived JWT (in-process cache, `exp-60s`), giving the headless pipeline a real service identity; pipeline grounding deletes every Gemini-synthesis path (web + X) and raises `DashboardWebSearchError` unconditionally on any requested-search failure; frontend defaults flip to true with explicit-false respected and DataTap pinned off.

**Tech Stack:** Python 3.12, Pydantic v2, httpx, digikey OAuth (`POST /v1/oauth/token`), Next.js digichat BFF tenant YAMLs, ruff line-length 100.

**Spec:** Owner decisions 2026-09-11 (zero-click ON; abort loudly; x_search included) on top of digithings-ai/digithings#3853 (PR #3856 merged). Research briefs: service-auth via machine-key exchange (no scope-table change), defaults control map, synthesis-fallback inventory.

## Global Constraints

- Python 3.12, Pydantic v2 everywhere, strict typing, ruff line-length 100, `ruff check + format --check` zero errors.
- Polars only, never pandas.
- Digi product names always lowercase in prose/docs/commits (`digisearch`, `digigraph`, `digillm`, `digifetch`, `digichat`, `digiquant`, `digibase`, `digikey`, `datatap`).
- MCP-first: capabilities stay discoverable tools; no logic directly in LangGraph nodes.
- digigraph must never `import digisearch` or `digiquant` modules; digiquant must never `import digigraph` or `digisearch` modules at top level (lazy HTTP-hub calls only, per #3856 precedent).
- Fail-closed everywhere; pipeline fail-HARD (raise, never silent fallback, never `None` grounding).
- Never log raw `dgk_live_` key material (log key prefix only).
- Every change traces to a GitHub issue (`task/<N>-slug` branch or `Fixes #N` in PR body); update per-component `ARCHITECTURE.md` on interface change.
- Human gate: new external service dependency or network exposure change blocks agent merge — this plan adds none (reuses digikey/digisearch over existing compose network).

---

### Part A — Service identity for the pipeline

### Task 1: `digibase.service_auth` machine-key exchange + JWT cache

**Files:**
- Create: `digibase/src/digibase/service_auth.py`
- Test: `digibase/tests/test_service_auth.py` (create dir if missing — check `ls digibase` first; if tests live elsewhere mirror existing layout)

**Interfaces:**
- Consumes: `digikey POST /v1/oauth/token` (`{"grant_type":"api_key","api_key","requested_scopes"}` → `{"access_token","expires_in":900}`); `digibase.http.outbound_service_headers` for forwarding.
- Produces: `get_service_jwt(*, key_env="DIGIQUANT_DIGIKEY_API_KEY", digikey_url_env="DIGIKEY_URL", scopes=("digisearch:query",)) -> str` used by Task 2. Raises `ServiceAuthError` (new, in same module) when key/url missing or exchange fails — never returns empty string.

- [ ] **Step 1: Write the failing test**

```python
import httpx
from digibase.service_auth import get_service_jwt, ServiceAuthError, clear_service_jwt_cache

def test_exchange_and_cache(monkeypatch):
    monkeypatch.setenv("DIGIQUANT_DIGIKEY_API_KEY", "dgk_live_testkey1234567890")
    monkeypatch.setenv("DIGIKEY_URL", "http://digikey:8005")
    calls = []
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        assert request.url.path == "/v1/oauth/token"
        return httpx.Response(200, json={"access_token": "jwt-1", "token_type": "Bearer", "expires_in": 900})
    monkeypatch.setattr("digibase.service_auth._http_post", lambda url, payload: httpx.Client(transport=httpx.MockTransport(handler)).post(url, json=payload).json())
    clear_service_jwt_cache()
    assert get_service_jwt() == "jwt-1"
    assert get_service_jwt() == "jwt-1"
    assert len(calls) == 1

def test_missing_key_raises():
    import os
    os.environ.pop("DIGIQUANT_DIGIKEY_API_KEY", None)
    clear_service_jwt_cache()
    try:
        get_service_jwt()
    except ServiceAuthError:
        return
    raise AssertionError("expected ServiceAuthError")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest digibase/tests/test_service_auth.py -v`
Expected: FAIL with "No module named 'digibase.service_auth'"

- [ ] **Step 3: Write minimal implementation**

```python
"""Service-to-service digikey auth for headless callers (no user session)."""
from __future__ import annotations
import os
import threading
import time
import httpx

EXPIRY_SKEW_S = 60.0

class ServiceAuthError(RuntimeError):
    pass

_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()

def clear_service_jwt_cache() -> None:
    with _lock:
        _cache.clear()

def _http_post(url: str, payload: dict) -> dict:
    with httpx.Client(timeout=10.0) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        return r.json()

def get_service_jwt(
    *,
    key_env: str = "DIGIQUANT_DIGIKEY_API_KEY",
    digikey_url_env: str = "DIGIKEY_URL",
    scopes: tuple[str, ...] = ("digisearch:query",),
) -> str:
    raw = os.environ.get(key_env, "")
    base = os.environ.get(digikey_url_env, "").rstrip("/")
    if not raw:
        raise ServiceAuthError(f"{key_env} is not set")
    if not base:
        raise ServiceAuthError(f"{digikey_url_env} is not set")
    cache_key = f"{key_env}:{raw[:16]}:{','.join(scopes)}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cache_key)
        if hit is not None and hit[1] - EXPIRY_SKEW_S > now:
            return hit[0]
    try:
        data = _http_post(
            f"{base}/v1/oauth/token",
            {"grant_type": "api_key", "api_key": raw, "requested_scopes": list(scopes)},
        )
        token = str(data["access_token"])
        ttl = float(data.get("expires_in", 900))
    except Exception as exc:
        raise ServiceAuthError(f"digikey exchange failed: {exc}") from exc
    if not token:
        raise ServiceAuthError("digikey exchange returned empty token")
    with _lock:
        _cache[cache_key] = (token, now + ttl)
    return token
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest digibase/tests/test_service_auth.py -v`
Expected: PASS
Run: `ruff check digibase/src/digibase/service_auth.py digibase/tests/test_service_auth.py && ruff format --check digibase/src/digibase/service_auth.py digibase/tests/test_service_auth.py`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digibase/src/digibase/service_auth.py digibase/tests/test_service_auth.py
git commit -m "feat(digibase): service machine-key jwt exchange with cache"
```

---

### Task 2: Pipeline hub calls carry the service JWT

**Files:**
- Modify: `digiquant/src/digiquant/research/data/web_grounding.py` (thread bearer: `call_web_search_tool` gains `bearer_token` param; `_call_digisearch_web_search(..., bearer_token=bearer_token)`; new ` _pipeline_bearer()` helper calling Task 1 `get_service_jwt()` — import `digibase.service_auth` lazily inside the helper so the module import never fails when digibase is minimal)
- Test: extend `tests/dq/research/data/test_web_grounding.py`

**Interfaces:**
- Consumes: Task 1 `get_service_jwt` / `ServiceAuthError`.
- Produces: authenticated tool calls; `ServiceAuthError` propagates to callers (mapped to raise in Task 4).

- [ ] **Step 1: Write the failing test**

```python
def test_pipeline_bearer_threaded(monkeypatch):
    from digiquant.research.data import web_grounding as mod
    seen = {}
    monkeypatch.setattr(mod, "get_service_jwt", lambda **k: "svc-jwt")
    def fake_call(query, **kw):
        seen.update(kw)
        return {"summary": "s", "sources": ["https://a.com/1"]}
    monkeypatch.setattr(mod, "_call_digisearch_web_search", fake_call)
    out = mod.call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
    assert out["sources"] == ["https://a.com/1"]
    assert seen.get("bearer_token") == "svc-jwt"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/research/data/test_web_grounding.py::test_pipeline_bearer_threaded -v`
Expected: FAIL (no such test / bearer_token not threaded)

- [ ] **Step 3: Write minimal implementation**

```python
def _pipeline_bearer() -> str | None:
    try:
        from digibase.service_auth import get_service_jwt
    except Exception:
        return None
    return get_service_jwt()

def call_web_search_tool(*, query: str, include_domains: list[str], max_results: int):
    from digigraph.orchestration.web_search_tools import _call_digisearch_web_search
    raw = _call_digisearch_web_search(
        query, include_domains=include_domains, max_results=max_results,
        bearer_token=_pipeline_bearer(),
    )
    rows = (raw or {}).get("results", []) if isinstance(raw, dict) else []
    if not rows:
        raise DashboardWebSearchError(f"web_search tool returned no rows for query={query!r}")
    return {
        "summary": "\n".join(f"- [{r.get('metadata', {}).get('title', r.get('doc_id'))}]({r.get('doc_id')}): {r.get('content', '')}" for r in rows),
        "sources": [r.get("doc_id", "") for r in rows],
    }
```

Adapt to the actual `_call_digisearch_web_search` signature in the file (it takes `bearer_token` per #3856 Task 6 — verify before writing; if the param name differs, match it).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/research/data/test_web_grounding.py -v`
Expected: PASS (legacy fallback tests still pass — they are rewritten in Task 4)

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/research/data/web_grounding.py tests/dq/research/data/test_web_grounding.py
git commit -m "feat(digiquant): thread service jwt into web-search tool calls"
```

---

### Part B — Pipeline tool-only + fail-hard (web + X)

### Task 3: Delete synthesis engine in `digigraph.llm_client`

**Files:**
- Modify: `digigraph/src/digigraph/llm_client.py` (delete `_ground_via_completion`, `_INLINE_URL_RE`, `_MD_LINK_URL_RE`, `_urls_from_grounding_text`, `web_search()`, `openrouter_web_search()`, `x_search()`; remove from `__all__` + header comment; keep `digifetch_web_search(model, query, ...)` as the single entry, raising on failure)
- Modify: `digigraph/src/digigraph/orchestration/web_search_tools.py` (delete synthesis chain + empty-result dict; tool call only; error/empty raises; keep opt-in gate + External labeling)
- Test: rewrite `tests/dg/test_llm_client.py::TestGroundingWrappers` → assert tool-raises (delete old class); update `tests/dg/test_web_search_opt_in.py` synthesis-mock tests to tool-boundary mocks expecting raise

**Interfaces:**
- Consumes: Task 2 bearer pattern (handler passes request bearer when present).
- Produces: `digifetch_web_search(model, query, *, usage_kind="web_search") -> tuple[str, list[str]]` that raises on any failure (no `None` return).

- [ ] **Step 1: Write the failing test**

```python
def test_digifetch_web_search_raises_on_tool_failure(monkeypatch):
    from digigraph import llm_client
    import pytest
    monkeypatch.setattr(llm_client, "_call_digisearch_web_search", lambda *a, **k: {})
    with pytest.raises(RuntimeError):
        llm_client.digifetch_web_search("model", "etf flows")
```

Adjust the mocked boundary name to the real one in the file; assert the real exception type the implementation raises.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dg/test_llm_client.py::test_digifetch_web_search_raises_on_tool_failure -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

Delete the synthesis functions; shape `digifetch_web_search` as pure tool call:

```python
def digifetch_web_search(model: str, query: str, *, usage_kind: str = "web_search") -> tuple[str, list[str]]:
    """Tool-only web grounding. Raises on any failure — never synthesizes, never None."""
    raw = _call_digisearch_web_search(query)
    rows = (raw or {}).get("results", []) if isinstance(raw, dict) else []
    if not rows:
        raise RuntimeError(f"web_search tool returned no rows for query={query!r}")
    summary = "\n".join(f"- {r.get('content', '')} ({r.get('doc_id', '')})" for r in rows)
    return summary, [r.get("doc_id", "") for r in rows]
```

Match the real `_call_digisearch_web_search` import path/signature in the file. Handler `_handle_web_search`: replace lines calling `openrouter_web_search`/`xai_web_search` + empty dict with `summary, urls = digifetch_web_search(model, query)` then build results as today; delete `get_grounding_model` import if unused.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dg/test_llm_client.py tests/dg/test_web_search_opt_in.py -v`
Expected: PASS
Run: `ruff check digigraph/src/digigraph/llm_client.py digigraph/src/digigraph/orchestration/web_search_tools.py && ruff format --check digigraph/src/digigraph/llm_client.py digigraph/src/digigraph/orchestration/web_search_tools.py`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/llm_client.py digigraph/src/digigraph/orchestration/web_search_tools.py tests/dg/test_llm_client.py tests/dg/test_web_search_opt_in.py
git commit -m "feat(digigraph): tool-only web grounding, fail hard"
```

---

### Task 4: Pipeline grounding tool-only + unconditional raise

**Files:**
- Modify: `digiquant/src/digiquant/research/data/web_grounding.py` (delete `_openrouter_web_search`; `fetch_web_grounding` tool-only, raises `DashboardWebSearchError` unconditionally on tool error/empty — delete `required` gate usage; delete `dashboard_web_search_required`, `WEB_SEARCH` env + `OLYMPUS_WEB_SEARCH` alias; keep `DashboardWebSearchError`; rewrite module docstring; delete Exa domain-folding, pass `include_domains/exclude_domains/max_results` through; update `search_domains.yaml` header)
- Modify: `digiquant/src/digiquant/research/data/ai_portfolios.py` (delete `openrouter/` prefix gate + synthesis call; X/web read via Task 2 tool path scoped `include_domains=["x.com", "twitter.com"]`; missing roster/empty/error all raise; update docstring)
- Modify: `digiquant/src/digiquant/research/phases/_node_factory.py` (delete `grounding_absent` injection + `live_search_is_fallback` exemption display; `web_grounding is None` unreachable — raise `DashboardWebSearchError`; keep fresh-FRED skip logic, retitled as grounded-by-ingest skip)
- Modify: `digiquant/src/digiquant/dashboard/envcompat.py` (remove `WEB_SEARCH` canonical + alias entries)
- Test: rewrite `tests/dq/research/data/test_web_grounding.py` fallback tests → `pytest.raises(DashboardWebSearchError)` unconditionally (no setenv); rewrite `test_ai_portfolios.py` gate/empty tests → raise; replace `test_grounding_absent.py` + node-factory/phase-flag fallback tests with raise assertions; keep non-search specs

**Interfaces:**
- Consumes: Task 2 `call_web_search_tool` (raises on empty) + Task 3 (no synthesis imports remain).
- Produces: `fetch_web_grounding(...) -> {summary, sources, as_of}` or raise; never `None`.

- [ ] **Step 1: Write the failing test**

```python
def test_fetch_web_grounding_raises_on_empty(monkeypatch):
    from digiquant.research.data import web_grounding as mod
    import pytest
    monkeypatch.setattr(mod, "call_web_search_tool", lambda **k: (_ for _ in ()).throw(RuntimeError("no rows")))
    with pytest.raises(mod.DashboardWebSearchError):
        mod.fetch_web_grounding(model="cheap", segment="macro", run_date="2026-09-11", scope="test")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/research/data/test_web_grounding.py::test_fetch_web_grounding_raises_on_empty -v`
Expected: FAIL (fallback returns None instead of raising)

- [ ] **Step 3: Write minimal implementation**

```python
def fetch_web_grounding(*, model: str, segment: str, run_date, scope: str) -> dict:
    """Tool-only web grounding. Requested search must succeed or raise."""
    query = _build_query(segment=segment, run_date=run_date, scope=scope)
    domains = _domains_for(segment)[:5]
    try:
        tool_out = call_web_search_tool(query=query, include_domains=domains, max_results=4)
    except Exception as exc:
        raise DashboardWebSearchError(f"web_search tool failed for segment={segment!r}: {exc}") from exc
    return {"summary": tool_out["summary"], "sources": tool_out["sources"], "as_of": run_date}
```

Delete `_openrouter_web_search`, the `dashboard_web_search_required` branch, and the `None` return. Mirror for `ai_portfolios` with `include_domains=["x.com", "twitter.com"]` for the X leg.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/research/data/test_web_grounding.py tests/dq/research/data/test_ai_portfolios.py tests/dq/research/test_grounding_absent.py -v`
Expected: PASS (rewrite obsolete tests per file list in this task; delete `test_grounding_absent.py` if it only asserts the removed flag, and remove its references)
Run: `ruff check digiquant/src/digiquant/research/data/web_grounding.py digiquant/src/digiquant/research/data/ai_portfolios.py digiquant/src/digiquant/research/phases/_node_factory.py && ruff format --check` same files
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/research/data/web_grounding.py digiquant/src/digiquant/research/data/ai_portfolios.py digiquant/src/digiquant/research/phases/_node_factory.py digiquant/src/digiquant/research/config/search_domains.yaml digiquant/src/digiquant/dashboard/envcompat.py tests/dq/research/data/test_web_grounding.py
git commit -m "feat(digiquant): tool-only grounding with loud abort"
```

---

### Task 4b: Simulator + phase fixtures stub the tool boundary (added post-review 2026-09-11)

**Files:**
- Modify: `digiquant/src/digiquant/research/testing/simulator.py` (patch `fetch_web_grounding`/`call_web_search_tool`/`build_grounding` alongside existing `completion_text` + `load_skill_edit` patches, returning the same canned-grounding shape as `tests/dq/research/test_phase7d_pm_skill.py:135-147`)
- Modify: `tests/dq/research/test_pipeline_simulation.py`, `tests/dq/portfolio/test_chain_research_then_portfolio.py`, `tests/dq/portfolio/test_delta_commit_freeze_1555.py`, `tests/dq/research/test_phase1_forecast_risk_contracts.py`, `tests/dq/research/test_phase12.py`, `tests/dq/research/test_phase34.py`, `tests/dq/research/test_phase67.py` (use the simulator stub or local canned grounding; assert topology/artifacts, never live search)
- Modify: `digiquant/ARCHITECTURE.md` (replace `grounding_absent=True` fail-soft + `DIGIQUANT_WEB_SEARCH` docs with tool-only + unconditional `DashboardWebSearchError`)
- Modify: `config/digiquant_models.yaml:40` comment (`OLYMPUS_WEB_SEARCH=required` → tool-only, no env gate)
- Modify: `tests/dq/research/test_phase_tool_flags.py:40` comment ("OpenRouter web search" → tool-only), `digiquant/src/digiquant/research/phases/_node_factory.py:135,142` ("paid fallback" → "grounded-by-ingest skip")

**Interfaces:**
- Consumes: Task 4 `fetch_web_grounding` raise contract + Task 2 `call_web_search_tool` shape.
- Produces: green simulator/phase/portfolio suites with zero live-search calls.

- [ ] **Step 1: Write the failing test**

```python
def test_simulator_stubs_grounding():
    from digiquant.research.testing import simulator
    import inspect
    src = inspect.getsource(simulator.simulated_pipeline)
    assert "fetch_web_grounding" in src or "call_web_search_tool" in src or "build_grounding" in src
```

Adapt to the real `simulated_pipeline` patch mechanism in the file (read it first; assert the tool boundary is stubbed, keep semantics).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/research/test_pipeline_simulation.py::test_simulator_stubs_grounding -v`
Expected: FAIL (no stub yet)

- [ ] **Step 3: Write minimal implementation**

Add the tool-boundary patches returning canned `{summary, sources, as_of}` grounding (copy the shape from `test_phase7d_pm_skill.py:135-147`); update the listed test files to use the stub; fix the ARCH/models.yaml/phase_tool_flags/node_factory copy per file list.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dq/research/test_pipeline_simulation.py tests/dq/portfolio/test_chain_research_then_portfolio.py tests/dq/research/test_phase12.py tests/dq/research/test_phase34.py tests/dq/research/test_phase67.py -v`
Expected: PASS
Run: `ruff check digiquant/src/digiquant/research/testing/simulator.py && ruff format --check digiquant/src/digiquant/research/testing/simulator.py`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/research/testing/simulator.py tests/dq/research/test_pipeline_simulation.py tests/dq/portfolio/ tests/dq/research/test_phase12.py tests/dq/research/test_phase34.py tests/dq/research/test_phase67.py digiquant/ARCHITECTURE.md config/digiquant_models.yaml
git commit -m "feat(digiquant): stub tool boundary in simulators, fix docs drift"
```

---

### Task 5: Retire model pins, validator, telemetry purposes

**Files:**
- Modify: `digigraph/src/digigraph/model_config.py` (delete `_HOUSE_CI_GROUNDING_SYNTHESIS_SLUGS`, synthesis branch in `_tier_web_search_pool`, `get_grounding_model`, `is_web_search_capable_model`; fix `is_tool_use_capable_model` docstring)
- Modify: `config/digiquant_models.yaml` (delete `web_search_models` from all tiers + rewrite header; keep phase pools bare-slug tool-capable)
- Modify: `scripts/validate_digiquant_pools.py` (delete `web_search_models` exclusion + grounding stanza)
- Modify: `digillm/src/digillm/telemetry.py` (delete `WEB_GROUNDING`, `X_GROUNDING`; keep `WEB_SEARCH`, `X_SEARCH` for tool calls)
- Modify: `digigraph/src/digigraph/usage.py` (single tool purpose set; tool search counts toward llm tokens — update both projections together)
- Modify: `digiquant/supabase/migrations/067_olympus_provider_telemetry.sql` — do NOT edit (migrations immutable); create new migration dropping `web_grounding`/`x_grounding` from the CHECK + update `tests/dq/research/test_migration_067.py` allowlist assertions only if they enumerate removed purposes
- Test: update `tests/dg/test_digiquant_models.py` (invert web-search-pool assertions → assert no `web_search_models` key), `tests/config/test_litellm_house_models.py`, `digillm/tests/test_cheaperinference_routing.py:150`, `tests/dg/test_usage.py:362`

- [ ] **Step 1: Write the failing test**

```python
def test_no_web_search_models_key():
    import yaml
    with open("config/digiquant_models.yaml") as fh:
        cfg = yaml.safe_load(fh)
    for tier, body in cfg["tiers"].items():
        assert "web_search_models" not in body, tier
```

Place in the existing `tests/dg/test_digiquant_models.py` style (adapt to its loaders).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dg/test_digiquant_models.py::test_no_web_search_models_key -v`
Expected: FAIL (key still present)

- [ ] **Step 3: Write minimal implementation**

Delete the keys + header rewrite + validator/telemetry/usage edits per file list. For `usage.py`, count tool search under llm tokens in both projections.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dg/test_digiquant_models.py tests/dg/test_usage.py digillm/tests/test_cheaperinference_routing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/model_config.py config/digiquant_models.yaml scripts/validate_digiquant_pools.py digillm/src/digillm/telemetry.py digigraph/src/digigraph/usage.py tests/dg/test_digiquant_models.py
git commit -m "feat: retire synthesis model pins and purposes"
```

---

### Part C — Zero-click default-ON (DataTap explicitly OFF)

Rule: default true everywhere; an explicit stored `false` is respected (user opted out); DataTap tenant gate false kills send regardless of pref.

### Task 6: Pref + session defaults to true

**Files:**
- Modify: `frontend/digichat/src/lib/web-search-pref.ts` (missing/invalid → `true`; explicit stored `false` stays `false`)
- Modify: `frontend/digichat/src/components/stock/embed-chat-prefs.tsx` (`DEFAULT_EMBED_CHAT_PREFS.webSearch: false` → `true`)
- Test: update `src/lib/web-search-pref.test.ts` (or nearest pref test file — verify name first) + embed-chat-prefs test

- [ ] **Step 1: Write the failing test**

```ts
it("defaults to true when nothing stored, respects explicit false", () => {
  expect(readWebSearchPref("tenant-a")).toBe(true);
  writeWebSearchPref("tenant-a", false);
  expect(readWebSearchPref("tenant-a")).toBe(false);
});
```

Match the real exported function names in `web-search-pref.ts` (read file first; adapt names, keep semantics).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace digichat -- web-search-pref`
Expected: FAIL (returns false)

- [ ] **Step 3: Write minimal implementation**

Change the default branch from `false` to `true` wherever missing/invalid is handled; leave the explicit-false path untouched. Same for `DEFAULT_EMBED_CHAT_PREFS.webSearch`.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace digichat -- web-search-pref embed-chat-prefs`
Expected: PASS
Run: `npm run lint --workspace digichat`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/web-search-pref.ts frontend/digichat/src/components/stock/embed-chat-prefs.tsx
git commit -m "feat(digichat): web search pref defaults true"
```

---

### Task 7: Tenant allows-ON + DataTap explicitly OFF

**Files:**
- Modify: `frontend/digichat/config/examples/occ-embed.yaml` (add `gate.webSearch: true` + catalog `- id: web_search / default: true / label: "Web search"`)
- Modify: `frontend/digichat/config/examples/local-app.yaml:42` (`default: false` → `true`; gate already true)
- Modify: `frontend/digichat/config/examples/local-app-memory.yaml:37` (same)
- Modify: `frontend/digichat/config/examples/local-cli.yaml:49` (`gate.webSearch: false` → `true` + add catalog `web_search default: true`; note `allowUserToggle: false` hides toggle — default carries it)
- Modify: `frontend/digichat/config/examples/datatap-mcp.yaml` (add explicit `gate.webSearch: false` under `gate:`; keep catalog WITHOUT any `web_search` entry; add comment `# web search explicitly off: docs + MCP surface only`)
- Test: update loader/client-projection/embed-bridge tests asserting old defaults (`loader.test.ts`, `client-projection.test.ts`, `schema.test.ts` — update only assertions that pin the old values)

No change: `dashboard-modal.yaml`, `digithings-ai-embed.yaml` (already gate-true + catalog-true), `digigraph` models/policy/handler, `schema.ts` optionality.

- [ ] **Step 1: Write the failing test**

```ts
it("datatap tenant denies web search", () => {
  const dep = loadTenant("datatap");
  expect(dep.gate.webSearch).toBe(false);
  expect(dep.tools?.catalog?.some((t) => t.id === "web_search")).toBe(false);
});
```

Adapt to the real loader API in `loader.test.ts` (read file first; keep semantics).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace digichat -- loader`
Expected: FAIL (gate undefined, not false)

- [ ] **Step 3: Write minimal implementation**

Apply the YAML edits per file list.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace digichat`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/config/examples/ frontend/digichat/src/lib/deploy-config/
git commit -m "feat(digichat): default-on tenants, datatap explicitly off"
```

---

### Task 8: Server env for authenticated first-party path

**Files:**
- Modify: `frontend/digichat/src/app/api/chat/route.ts` — verify lines ~480-488: when `embedConfig` is null (authenticated first-party), `tenantAllowsWeb` falls back to `DIGICHAT_WEB_SEARCH=="1"`. No code change if true; if the fallback differs, wire `DIGICHAT_WEB_SEARCH=="1"` as the fallback.
- Modify: `.env.example` (document `DIGICHAT_WEB_SEARCH=1` for first-party default-ON)
- Modify: `frontend/digichat/ARCHITECTURE.md` (defaults table: ON everywhere except datatap; pref semantics; env knob)
- Test: extend `src/app/api/chat/route.test.ts` (`:462-502` area): `DIGICHAT_WEB_SEARCH=1` + null embedConfig → header forwarded; unset → not forwarded

- [ ] **Step 1: Write the failing test**

```ts
it("forwards web-search header for first-party when DIGICHAT_WEB_SEARCH=1", async () => {
  process.env.DIGICHAT_WEB_SEARCH = "1";
  const res = await postChat({ enableWebSearch: true, embedConfig: null });
  expect(res.forwardedHeaders["X-Digi-Enable-Web-Search"]).toBe("1");
});
```

Adapt to the real test harness in `route.test.ts` (read file first; keep semantics).

- [ ] **Step 2: Run test to verify it fails**

Run: `npm run test --workspace digichat -- route`
Expected: FAIL (env unset/unsupported)

- [ ] **Step 3: Write minimal implementation**

Set `DIGICHAT_WEB_SEARCH=1` handling per file list + `.env.example` docs + ARCHITECTURE table.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm run test --workspace digichat`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/chat/route.ts frontend/digichat/src/app/api/chat/route.test.ts .env.example frontend/digichat/ARCHITECTURE.md
git commit -m "feat(digichat): first-party web search on via env"
```

Ops note (for PR body, not code): deploy sets `DIGICHAT_WEB_SEARCH=1`; live `DIGICHAT_EMBED_TENANTS` datatap-host entry gets `webSearch:false`; pipeline key issuance: `python -m digikey.cli issue-key --tenant digiquant-pipeline --label pipeline --scopes digisearch:query --kind standard`, secret into `.env` as `DIGIQUANT_DIGIKEY_API_KEY` + compose passthrough.

---

### Part D — Leftover follow-ups batch

### Task 9: Small hardening batch

**Files:**
- Modify: `digigraph/src/digigraph/orchestration/web_search_tools.py` (add public `call_digisearch_web_search(...)` wrapper delegating to `_call_digisearch_web_search`; update `digiquant/.../web_grounding.py:102` import to the public name)
- Modify: `digigraph/src/digigraph/orchestration/web_search_tools.py` `WEB_SEARCH_TOOL` schema (expose `include_domains`, `exclude_domains`, `max_results` alongside `query` — handler already reads them)
- Modify: `digigraph/src/digigraph/orchestration/web_search_tools.py` tool description ("via digillm" → "first-party digisearch web_search tool")
- Test: `digillm/tests/test_web_search_usage_kind.py` (add purpose-pinning test: `digifetch_web_search` runs under `CallPurpose.WEB_SEARCH`, `openrouter` path deleted so only tool purpose asserted — adapt to Task 3 deletions)
- Verify (no change if absent): searxng healthcheck `curl` probe in `docker-compose.yml` (shell into image spec or docs; switch to `wget` only if curl missing)
- Docs: fix `digisearch/ARCHITECTURE.md:80` dispatch sentence (list `web_search`), `web_grounding.py:42,172,179` + `_node_factory.py:309-318` `OLYMPUS_` copy → `DIGIQUANT_WEB_SEARCH`, ARCH week→month sentence for searxng `time_range`

- [ ] **Step 1: Write the failing test**

```python
def test_public_wrapper_delegates(monkeypatch):
    from digigraph.orchestration import web_search_tools as mod
    assert mod.call_digisearch_web_search is not None
```

Replace with a real delegation assertion once the wrapper exists (mock `_call_digisearch_web_search`, assert passthrough of query + bearer_token).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dg/test_web_search_opt_in.py -v -k wrapper`
Expected: FAIL (no public wrapper)

- [ ] **Step 3: Write minimal implementation**

Apply the file list: wrapper + import update + schema params + description + purpose test + healthcheck/docs fixes.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/dg/test_web_search_opt_in.py digillm/tests/test_web_search_usage_kind.py -v`
Expected: PASS
Run: `ruff check digigraph/src/digigraph/orchestration/web_search_tools.py && ruff format --check digigraph/src/digigraph/orchestration/web_search_tools.py`
Expected: zero errors

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/orchestration/web_search_tools.py digiquant/src/digiquant/research/data/web_grounding.py digillm/tests/test_web_search_usage_kind.py digisearch/ARCHITECTURE.md
git commit -m "feat: web-search follow-ups batch"
```

---

### Task 10: Live verification + rollout record

**Files:**
- Modify: `digisearch/ARCHITECTURE.md` (rollout ops: append measured p50/latency + Gemini traffic delta after live run; searxng digest pin; `secret_key` rotation note)

No code. Run order:
- [ ] **Step 1:** `docker compose up -d searxng valkey digisearch` (or stack-local equivalent); confirm `GET http://127.0.0.1:8080/search?q=test&format=json` returns rows
- [ ] **Step 2:** `DIGISEARCH_WEB_SEARCH_LIVE=1 pytest digisearch/tests/test_web_search_eval.py -v` → record p50 + quality; confirm zero `Traceback`
- [ ] **Step 3:** One digiquant segment grounding e2e with service JWT (`DIGIQUANT_DIGIKEY_API_KEY` set) → confirm 200s, no fallback, `DashboardWebSearchError` on forced bad-backend (set `DIGISEARCH_WEB_SEARCH_BACKEND=bogus` → HTTP 503 path)
- [ ] **Step 4:** Baseline `/embed` zero-click check (web cites without toggle) + datatap embed check (no toggle, no web cites) in browser
- [ ] **Step 5: Commit**

```bash
git add digisearch/ARCHITECTURE.md
git commit -m "docs: web-search live verification record"
```

---

## Self-Review

**1. Spec coverage:** owner decisions — zero-click ON (Tasks 6–8) ✓; abort loudly (Tasks 3–4) ✓; x_search included (Tasks 3–5 via domain-scoped tool legs + purpose deletion) ✓; service ID fix (Tasks 1–2) ✓; DataTap off (Task 7) ✓; follow-ups batch (Task 9) ✓; live proof (Task 10) ✓.
**2. Placeholder scan:** no TBD/TODO/bare directives; every step names files, commands, expected outputs.
**3. Type consistency:** `get_service_jwt(*, key_env, digikey_url_env, scopes) -> str` + `ServiceAuthError` used identically in Tasks 1–2; `{summary, sources, as_of}` shape kept in Task 4; `DashboardWebSearchError` unconditional everywhere; `WebSearchRequest` field names (`include_domains`, `max_results`, `recency_days`) match #3856 code.
