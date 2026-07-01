---
title: DigiFetch
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - web-scraping
  - library
---
# DigiFetch
> The shared web-scraping engine — headless-browser lifecycle, composable retry/backoff, and polite rate limiting, as a library with no service coupling.

## What it is

DigiFetch is the shared web-scraping / headless-fetch engine for the DigiThings stack. It is a standalone library — no FastAPI, no port, no service coupling — that extracts the reusable *mechanics* of web scraping (headless-browser session lifecycle, composable retry/backoff, polite-scraping rate limiting, and an HTTP fetch/download path with a Playwright→HTTP cookie hand-off) from site-specific scrapers, leaving only the site-specific logic in each consumer.

The package is side-effect-free and browser-free on import: `import digifetch` never launches or imports a browser. Playwright is imported lazily at call time, so the library installs and imports cleanly on a machine with no browser present; the headless seam is opt-in via the `[browser]` extra.

## The problem it solves

Every scraper reinvents the same brittle plumbing — backoff loops, throttles, browser session management, cookie hand-off — wrapped tightly around one site's selectors. The mechanics never get reused and never get hardened. DigiFetch separates the durable mechanics (reusable, tested, injectable clocks/sleeps for fast tests) from the disposable site logic, so scraping infrastructure compounds instead of being rebuilt per source.

## How it fits in the ecosystem

DigiFetch is a leaf library that any data-acquisition path can depend on. Hard dependencies are just `pydantic` and `httpx` (the monorepo HTTP convention; `requests` is intentionally excluded). Today there is exactly one consumer — **twelve-x** — so the public interface was validated against a single use case and is treated as provisional (0.1.0); it should be expected to change when a second consumer arrives. It was built ahead of the usual "extract on the second consumer" rule by explicit request.

## Capabilities — Current

Shipped:

- `RetryPolicy` — exponential backoff with full jitter, selective `retry_on`, injectable `sleep`/`rand`; and `with_retry(func, policy)` as a composable wrapper (not baked into any fetch primitive)
- `RateLimiter` — single-process minimum-interval throttle for polite scraping (injectable clock/sleep)
- `HttpFetcher` over `httpx` — `fetch`/`download` with a byte cap and `DownloadTooLargeError`
- `browser_session(...)` — headless-browser lifecycle context manager (requires `digifetch[browser]`), with `cookies_from_playwright` for the browser→HTTP hand-off
- Structural `Page`/`BrowserContext` protocols so consumers can test without a live browser

## Capabilities — 12-month roadmap

- Wire twelve-x's scrapers onto DigiFetch (the deferred companion to the extraction)
- Stabilise the public API to 1.0 once a second consumer validates it
- Distributed/Redis-backed rate limiting (today single-process; shared throttling is future DigiBase work)

## Open source vs. proprietary

**Open (MIT/Apache):** the entire DigiFetch library — retry, rate limiting, HTTP fetch/download, and the headless-browser seam. It is pure open-core infrastructure; any proprietary value lives in the site-specific scrapers and the data they feed, not in DigiFetch.
