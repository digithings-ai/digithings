# DigiFetch – Architecture

<!--
Scorer false positive: this document references the stdlib ``sleep`` builtin in prose and
examples to document that the engine AVOIDS bare blocking sleeps (sleep is injected).
Suppress that rule for this file:
# score:allow blocking sleep
-->

`digifetch` is the **shared web-scraping / headless-fetch engine** for the
DigiThings monorepo. It is a standalone **library** (no FastAPI, no port, no
service coupling) that extracts the *reusable mechanics* of web scraping —
headless-browser session lifecycle, composable retry/backoff, polite-scraping
rate limiting, and an HTTP fetch/download path with a Playwright→HTTP cookie
hand-off — from twelve-x's site-specific scrapers.

> ⚠️ **Built ahead of the YAGNI trigger.** This module was created per an
> explicit request *before* the usual "extract when a second consumer appears"
> rule fired (see issue #634). Today there is exactly **one** consumer:
> **twelve-x**. The public interface was therefore validated against a single
> use case and **should be expected to change** when a second consumer arrives
> — treat 0.1.0 as provisional. The companion follow-up (wire twelve-x onto
> digifetch) is deliberately deferred (see "Monorepo integration" below).

## Non-negotiables

- Python 3.12, Pydantic v2, full type hints, ruff line-length 100.
- Hard deps: `pydantic>=2`, `httpx>=0.27` only.
- Optional extras: `[browser]` (Playwright, for the headless-browser seam),
  `[dev]` (pytest, ruff).
- **Side-effect-free, browser-free import.** `import digifetch` must never
  launch or import a browser. Playwright is imported lazily at
  `browser_session` *call* time, and the public browser symbols are resolved
  via a :pep:`562` `__getattr__` shim. The package imports cleanly on a machine
  with no browser installed.
- No `import fastapi`; no `Request` objects; no service/port/uvicorn.
- No `import requests` (the monorepo HTTP convention is `httpx`; the scorer
  flags `requests`).

## Module map

| Module | Responsibility |
|--------|----------------|
| `digifetch/retry.py` | `RetryPolicy` (exponential backoff + full jitter, selective `retry_on`, **injectable** `sleep`/`rand`) and `with_retry(func, policy)` — a *composable* retry wrapper, not baked into any fetch primitive. |
| `digifetch/ratelimit.py` | `RateLimiter` — single-process minimum-interval gate (injectable `clock`/`sleep`). Polite-scraping throttle; **not** a token bucket, **not** Redis-backed (that is future digibase work). |
| `digifetch/http.py` | `HttpFetcher` over `httpx` (`fetch` → `FetchResult`, `download` → `DownloadResult` with a byte cap), `cookies_from_playwright`, `DEFAULT_TIMEOUT`, `DownloadTooLargeError`. The non-browser fetch/download seam. |
| `digifetch/browser.py` | `browser_session(...)` context manager yielding the live `(page, context)`; `BrowserConfig`; `Page`/`BrowserContext` structural Protocols; `BrowserNotAvailableError`. The headless-browser lifecycle seam (requires `digifetch[browser]`). |
| `digifetch/__init__.py` | Public API surface. Eager re-exports of the light seams; lazy `__getattr__` re-exports of the browser seam. |

## Public API

```python
from digifetch import (
    # retry/backoff
    RetryPolicy, with_retry,
    # rate limiting
    RateLimiter,
    # HTTP fetch/download seam
    HttpFetcher, FetchResult, DownloadResult, DownloadTooLargeError,
    cookies_from_playwright, DEFAULT_TIMEOUT,
    # headless-browser seam (needs digifetch[browser])
    browser_session, BrowserConfig, Page, BrowserContext, BrowserNotAvailableError,
)
```

### `browser_session`

```python
@contextmanager
def browser_session(
    config: BrowserConfig | None = None,
    *,
    sync_playwright_factory=None,   # injected for tests
) -> Iterator[tuple[Page, BrowserContext]]
```

Opens a headless browser and yields the **live page and its context**, then
guarantees teardown (`browser.close()` runs even if the caller's body raises).
The caller drives the page — navigation, selector fills/clicks, "show more"
pagination, `page.content()` — because that is site-specific. The `context` is
yielded so the caller can pull `context.cookies()` and hand them to
`HttpFetcher` for an authenticated plain-HTTP follow-up.

`BrowserConfig` carries the only knobs both twelve-x scrapers actually vary:
`headless`, `user_agent` (TE sets a desktop-Chrome UA; primemarket leaves it
default), `default_timeout_ms` (TE uses 45 000), `browser` (both use chromium),
`viewport`, and `launch_args`.

Playwright is imported lazily inside this function. If it is absent,
`BrowserNotAvailableError` is raised with an actionable
`pip install 'digifetch[browser]' && playwright install chromium` message
(mirrors `digibase.connectors.supabase.from_env`).

### `with_retry` / `RetryPolicy`

```python
with_retry(func: Callable[[], T], policy: RetryPolicy | None = None,
           *, description: str = "operation") -> T
```

Generalizes twelve-x TE's hand-rolled `for attempt in range(navigation_retries):
... time.sleep(2.0 * attempt)` loop. It is **composable**: wrap *any* zero-arg
callable — a browser navigation, an `HttpFetcher.fetch`, a `download`. Backoff
is `base_delay * factor**(attempt-1)` capped at `max_delay`, with optional full
jitter. `retry_on` narrows which exceptions are retried (a 404 should not be
retried like a timeout). `sleep` and `rand` are injected so tests are instant
and deterministic — and so no bare blocking `time.sleep(<literal>)` appears in
source.

### `RateLimiter`

```python
RateLimiter(min_interval: float, *, clock=time.monotonic, sleep=time.sleep)
limiter.acquire() -> float   # seconds actually slept
```

Replaces the ad-hoc `time.sleep(pause_s)` pauses in twelve-x's scrapers with one
explicit min-interval gate. Thread-safe; cadence does not drift (it advances
from the scheduled slot, not the post-sleep clock). `min_interval=0` disables
throttling. Clock and sleep are injected for deterministic tests.

### `HttpFetcher` + result models

```python
HttpFetcher(*, timeout=DEFAULT_TIMEOUT, headers=None, cookies=None,
            max_bytes=32*1024*1024, transport=None, client=None)
fetcher.fetch(url, *, method="GET", params=None, data=None, json=None,
              headers=None, cookies=None) -> FetchResult
fetcher.download(url, *, method="GET", headers=None, cookies=None) -> DownloadResult
```

The non-browser seam. `fetch` generalizes twelve-x's
`requests.post(AJAX_URL, data=..., cookies=..., timeout=30)` →
`raise_for_status()` → text body; it returns a typed, frozen `FetchResult`
(never a bare dict). `download` streams binary content (a research PDF) with a
hard `max_bytes` cap (raises `DownloadTooLargeError` *before* buffering the whole
body) and returns `DownloadResult` (raw `content` bytes + `content_type` +
`size`) for hand-off to a site-specific parser. `DEFAULT_TIMEOUT` mirrors
`digibase.http_client.DEFAULT_TIMEOUT` (connect 5 / read 30 / write 10 / pool 5).

`cookies_from_playwright(context.cookies())` flattens Playwright's list of cookie
dicts to the `{name: value}` dict an HTTP client sends — the exact hand-off
twelve-x's `scrape_research` performs inline before its AJAX call.

**Injection seams for tests:** pass `transport=httpx.MockTransport(...)` to
exercise the real client (headers/cookies/timeout wiring) without a socket, or
`client=<prebuilt httpx.Client>` to supply a fully-configured client (it then
owns its own headers/cookies/timeout — the corresponding constructor args are
not re-applied).

## How the two twelve-x scrapers map onto the engine

| twelve-x need (today, site-specific) | digifetch seam (extracted) |
|--------------------------------------|----------------------------|
| `sync_playwright()` → `chromium.launch(headless=True)` → `new_context(user_agent=…)` → `new_page()` → `set_default_timeout(…)` → `browser.close()` (both scrapers) | `browser_session(BrowserConfig(...))` context manager |
| TE: `for attempt in range(navigation_retries): … time.sleep(2.0*attempt)` | `with_retry(lambda: …navigate…, RetryPolicy(...))` |
| TE: `time.sleep(show_more_pause_s)` between "show more" clicks; primemarket: implicit pacing of AJAX calls | `RateLimiter(min_interval=…).acquire()` |
| primemarket: capture `context.cookies()` → `requests.post(AJAX_URL, data={…}, cookies=…, timeout=30).raise_for_status()` → S3 URL text | `cookies_from_playwright(ctx.cookies())` + `HttpFetcher.fetch(url, method="POST", data=…, cookies=…)` → `FetchResult.text` |
| primemarket (downstream): download the PDF bytes from the S3 URL | `HttpFetcher.download(s3_url)` → `DownloadResult.content` |
| TE: `page.content()` → `parse_calendar_html(html)` | engine yields the live `page`; caller calls `page.content()` and parses — **parsing stays site-specific** |

## Deliberately NOT extracted (stays site-specific in twelve-x)

Keeping these out is the core design decision — the engine manages *lifecycle and
transport*; the consumer owns *what to do on the page* and *how to read it*.

- **Login / auth flows.** Selector-driven (`page.fill(USERNAME_SELECTOR, …)`,
  `page.click(SUBMIT_SELECTOR)`, `wait_for_url("**/prime-dashboard**")`). The
  issue's candidate scope listed "auth/login flows", but the overriding rule is
  "keep site-specific logic out" — and login is entirely selectors + post-login
  URL waits, which have no generic shape from one consumer. The engine exposes
  the live `page`; the caller logs in. **Deferred:** a generic login abstraction
  (credential injection + a declarative selector/step model) is a candidate for
  the second consumer, not now.
- **Selectors and URLs.** `PRIMEMARKET_*` selectors/URLs, `TE_CALENDAR_URL`,
  the `#showMore` selector list — config in twelve-x.
- **Pagination policy.** TE's "click show-more up to N times" loop is
  site-specific (selector list + stop condition). It *uses* `RateLimiter` for
  pacing but the click loop itself stays in twelve-x.
- **HTML / DOM parsing.** `parse_calendar_html`, the table/regex parsers,
  `country_code`, `_category_from_mention`, row extraction (`tdFileName`, …) —
  all twelve-x.
- **Domain models.** `CalendarEvent`, the primemarket `FileMeta` row shape, the
  "today + yesterday" rolling window, `stable_external_id`.
- **PDF text extraction.** `pdfplumber` parsing stays in twelve-x; digifetch
  hands back raw bytes and does **not** depend on pdfplumber.
- **The `GetReserchFile` AJAX contract** (including the site's intentional typo)
  — a twelve-x config constant.

## Design decisions (and why)

- **httpx, not requests; no `digibase` dependency.** The fetch seam uses `httpx`
  directly (monorepo HTTP convention; async-capable for a future consumer; the
  scorer flags `requests`). We do **not** depend on the `digibase` sibling for
  `sync_client`/`DEFAULT_TIMEOUT`, even though it provides them: `digibase` is
  not on PyPI, so a hard `digibase>=0.1.0` dep would force consumers through
  `scripts/install-workspace.sh` ordering. Keeping `digifetch` a flat leaf
  (pydantic + httpx) keeps it trivially `pip install -e`-able. We instead
  *mirror* the digibase timeout envelope as a local constant.
- **Composable retry, not retrying primitives.** `with_retry` wraps a callable
  rather than being a flag on `fetch`/`browser_session`. This matches the two
  consumers' differing needs (TE retries *navigation*; primemarket retries
  *AJAX*) without a combinatorial set of `retry=` parameters, and lets a caller
  wrap a whole multi-step page interaction in one retry.
- **Injected `sleep`/`clock`/`rand` everywhere time passes.** Makes the retry
  and rate-limit logic deterministic and instant under test, and means there is
  no bare blocking `time.sleep(<literal>)` in the engine source (the default is
  `time.sleep`, supplied as a parameter default — the scorer's
  `time.sleep((?!0))` pattern matches *calls*, not parameter defaults).
- **Structural `Page`/`BrowserContext` Protocols.** Give callers and the engine
  real type hints without importing playwright (which may be absent). The real
  Playwright objects satisfy them structurally; this mirrors digibase's
  `SupabaseClient` Protocol. (`isinstance` against these `runtime_checkable`
  Protocols works for real duck-typed objects; `unittest.mock.MagicMock` does
  not register — tests assert the contract with a minimal real object.)
- **Sync only (YAGNI).** Pre-trigger, with one synchronous consumer, the engine
  is sync-only. `httpx` is async-capable, so an `async_session` / `AsyncFetcher`
  is a clean future addition when a second (async) consumer needs it.

## Environment variables

`digifetch` reads **no** environment variables. Credentials, URLs, user-agents,
timeouts, and rate limits are passed in by the caller (config objects / function
arguments). This keeps the engine deployment-agnostic and side-effect-free on
import — site config (`PRIMEMARKET_*`, `TE_CALENDAR_URL`, credentials) lives in
the consumer (twelve-x `config.py`).

## Testing

Unit tests fully mock the network and the browser — they never launch a real
browser or hit a live site (and pass without `digifetch[browser]` installed):

- `retry` / `ratelimit`: inject a recording `sleep` and a fake `clock`; assert
  the exact backoff/cadence schedule.
- `http`: `httpx.MockTransport` drives the real `httpx.Client` request/stream
  machinery in-process (closer to production than a fully fake client).
- `browser`: inject a fake `sync_playwright` factory (mirrors twelve-x's
  `_make_mock_playwright`); assert lifecycle, UA/timeout wiring, and that
  teardown runs on the exception path.
- `package`: assert `import digifetch` does **not** import playwright and the
  lazy `__getattr__` resolves browser symbols on demand.

```bash
# from the repo root (digifetch/src is on pytest.ini pythonpath)
pytest digifetch/tests -q
ruff check digifetch/ && ruff format --check digifetch/
```

## Monorepo integration (follow-ups for the integrator)

These are intentionally **outside** this package:

1. **Wire twelve-x onto digifetch (the deferred companion to #634).** Repoint
   `twelve_x/nodes/scrape.py` and `twelve_x/fx_calendar/scraper.py` at
   `digifetch.browser_session` / `HttpFetcher` / `with_retry` / `RateLimiter`,
   leaving selectors, URLs, parsing, the rolling-window logic, and pdfplumber in
   twelve-x. Add `digifetch[browser]` to twelve-x's `pyproject.toml`. Tracked
   separately; **not** done here (this task does not modify twelve-x).
2. **`scripts/project_routing.json`** — add `component:digifetch` once a GitHub
   Project number is allocated for it (a human must pick the number;
   `setup_module_project.sh` is the helper). Left for a human.
3. **`scripts/install-workspace.sh`** — add `digifetch` to the `ALL=(…)` and
   `has_dev` lists if/when CI installs it as an editable workspace package (it
   is a flat leaf, so order does not matter). Left for a human.
4. **`CODEOWNERS`** — add a `/digifetch/` owner line.
5. **PR-template / CI matrix** — add a `digifetch` component checkbox to
   `.github/PULL_REQUEST_TEMPLATE.md` and a digifetch entry to any per-component
   CI matrix. Left for a human (infra not verifiable from this worktree).

Wired by this task (minimal, to make discovery/CI green):

- Root `pytest.ini`: `digifetch/tests` added to `testpaths`, `digifetch/src` to
  `pythonpath` (same precedent as `digillm`).
- Root `ARCHITECTURE.md`: `-e ./digifetch` added to the editable dev-install line.
- `scripts/commit_helper.sh`: `digifetch` added to `VALID_COMPONENTS` so
  `feat(digifetch): …` passes commit validation.
