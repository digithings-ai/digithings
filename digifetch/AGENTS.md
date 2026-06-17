# Agent Guide: DigiFetch

<!--
Scorer false positive: this guide references the stdlib ``sleep`` builtin in prose to
document that the engine AVOIDS bare blocking sleeps (sleep is injected).
Suppress that rule for this file:
# score:allow blocking sleep
-->

## Purpose

DigiFetch is a **shared Python library** (`digifetch` package): the reusable
**web-scraping / headless-fetch engine** for DigiThings. It provides headless-
browser **session lifecycle**, composable **retry/backoff**, a min-interval
**rate limiter**, and an httpx **fetch/download** path with a Playwright→HTTP
**cookie hand-off**. It has **no server, no port, no service coupling** and reads
**no environment variables** — all config is passed in by the caller. Site-
specific scraping logic (login selectors, URLs, HTML parsing, PDF extraction)
stays in the **consumer** (today: twelve-x).

> ⚠️ Built **ahead of** the single-consumer YAGNI trigger, per explicit request
> (#634). One consumer exists today (twelve-x); the interface is provisional and
> will likely change at the second consumer. Wiring twelve-x onto digifetch is a
> **separate, deferred** follow-up — do not do it from this package.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — module map, public API, the
   extracted-vs-site-specific boundary, and design decisions
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
3. [`../CLAUDE.md`](../CLAUDE.md) — scoring gate and human-gate triggers
4. The single consumer's real scrapers (read-only requirements source):
   `twelve-x/nodes/scrape.py`, `twelve-x/fx_calendar/scraper.py`

---

## Pre-Flight Checklist

Before making any change to `digifetch/`:

- [ ] Read `ARCHITECTURE.md` — Module Map, Public API, and "Deliberately NOT
      extracted"
- [ ] Run `pytest digifetch/tests -q` — passes before and after
- [ ] Run `ruff check digifetch/ && ruff format --check digifetch/` — zero errors
- [ ] Confirm **`import digifetch` does not import playwright** (run the import-
      cost check below). Browser code must stay behind the lazy `__getattr__`
      shim + the deferred `from playwright...` import.
- [ ] Confirm **no env reads / no I/O at import time** — the library is side-
      effect-free; all config is passed in.
- [ ] Confirm any time-passing code (`retry`, `ratelimit`) keeps `sleep` / `clock`
      injectable — no bare `time.sleep(<literal>)` in source.
- [ ] Confirm result types are Pydantic v2 models / dataclasses, never bare dicts.
- [ ] Confirm the extracted/site-specific boundary is preserved — do **not** add
      selectors, URLs, HTML parsing, login flows, or `pdfplumber` here.

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Browser-free, side-effect-free on import.** No threads/sockets/file-writes
  and **no browser import** at import time. Playwright loads lazily in
  `browser_session`; public browser symbols resolve via `__init__.__getattr__`.
- **Playwright stays an optional extra.** `digifetch[browser]`. The base package
  (pydantic + httpx) must install and function with no browser present. A missing
  browser raises `BrowserNotAvailableError` with an actionable install hint —
  never an `ImportError` at import time.
- **httpx, not requests.** The fetch seam uses `httpx`. Do not `import requests`
  (the scorer flags it, and it breaks the async-capable convention).
- **No new hard dependencies** without a human gate (network-capable deps are a
  human-review trigger per CLAUDE.md). The hard-dep set is `pydantic` + `httpx`.
- **No sibling-package hard dep.** Do not add `digibase` (or any monorepo
  sibling) to `dependencies` — it is not on PyPI and would break flat installs.
  Mirror small constants locally instead (see `DEFAULT_TIMEOUT`).
- **Keep site-specific logic out.** Selectors, URLs, login/auth flows,
  pagination policy, HTML/DOM parsing, domain models, and PDF text extraction
  belong to the consumer. The engine owns *lifecycle + transport* only.
- **Injectable time.** `sleep`, `clock`, and `rand` are constructor/parameter
  injections so tests are deterministic and instant.
- **Typed results.** Public surfaces return Pydantic models / dataclasses; the
  `page`/`context` typing seam uses the structural `Page`/`BrowserContext`
  Protocols, not bare `Any`.
- **Sync only (for now).** No async engine until a second, async consumer needs
  it (YAGNI) — then add `async_session` / `AsyncFetcher` alongside.

---

## Anti-Patterns (do not do these here)

- ❌ Importing `playwright` at module top level (breaks the browser-free import).
- ❌ Baking `retry=`/`rate_limit=` flags into `fetch`/`browser_session` — retry
  and throttling are **composed** (`with_retry(...)`, `limiter.acquire()`), not
  embedded.
- ❌ Adding `page.fill(...)`/`page.click(...)`/`wait_for_url(...)` login helpers,
  a `parse_*` function, selector constants, or `pdfplumber` — that is consumer
  territory.
- ❌ Reading `os.environ` anywhere in the package.
- ❌ Returning bare `dict`s from public functions.
- ❌ `time.sleep(<literal>)` inside a function body (inject the sleep instead).

---

## Test Commands

```bash
# Unit tests (no network, no browser; passes without digifetch[browser])
pytest digifetch/tests -q

# Single file
pytest digifetch/tests/test_browser.py -v

# Lint + format
ruff check digifetch/ && ruff format --check digifetch/

# Import-cost guard — MUST print False / False
python -c "import sys, digifetch; \
print('playwright imported:', 'playwright' in sys.modules); \
print('browser submodule loaded:', 'digifetch.browser' in sys.modules)"

# Verify the base library installs with no optional extras
pip install -e digifetch/ --dry-run
```

> Note: `digifetch/tests` is on the root `pytest.ini` `pythonpath`/`testpaths`
> (same precedent as `digillm`), so `make test-unit` and CI discover these tests
> without an editable install.

---

## More

The full module map, public API contract, the extracted-vs-site-specific
boundary, design rationale, and the deferred monorepo-integration follow-ups
live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc whenever you change
an interface or behavior.
