---
type: library-guide
title: digifetch Library
description: digifetch shared fetch engine — HTTP fetch/download, retry policy, polite rate limiting, and the lazy browser seam.
tags: [digifetch, fetch, scraping, library]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-5dd6032865f6a0da99b5bf34
    resource: repo://digifetch/ARCHITECTURE.md
  - id: openwiki-source-b629d8effd0ca947d2e8078c
    resource: repo://digifetch/src/digifetch/__init__.py
  - id: openwiki-source-36222e676452a692ac37e182
    resource: repo://digifetch/src/digifetch/http.py
  - id: openwiki-source-da07c4a285964831bd07915c
    resource: repo://digifetch/src/digifetch/retry.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digifetch Library

digifetch is the shared web-fetch engine: a standalone library (no
FastAPI, no port) extracting reusable scraping mechanics — HTTP fetch,
composable retry/backoff, polite rate limiting, and headless-browser
session lifecycle with a Playwright→HTTP cookie hand-off. Hard deps are
`pydantic>=2` + `httpx>=0.27`; Playwright rides the `[browser]` extra.

## HTTP path

`HttpFetcher` (context-managed) offers `fetch()` returning `FetchResult`
and `download()` returning `DownloadResult` with a size cap
(`DownloadTooLargeError` beyond it). `cookies_from_playwright()` hands
browser cookies to the HTTP path so authenticated sessions continue
without re-login. The monorepo convention is httpx throughout — no
`requests`.

## Retry and rate limiting

`RetryPolicy` + `with_retry()` compose backoff around fallible calls
(sleep injected, never bare blocking sleeps); the ratelimiter keeps
scraping polite per host. Both are standalone — usable without the
fetcher.

## Browser seam

`browser_session()` launches Playwright headless sessions, but Playwright
imports only at call time: public browser symbols resolve via a PEP 562
`__getattr__` shim, so `import digifetch` stays side-effect-free and
browser-free on machines with no browser installed.

## Provisional status

Built ahead of the YAGNI trigger for twelve-x, the single consumer as of
0.1.0 — treat the interface as provisional until a second consumer
arrives. No `import fastapi`, no `Request` objects, no service coupling.
