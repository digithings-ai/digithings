---
type: library-guide
title: digibase Connectors
description: digibase outbound clients — bounded httpx factories, connector DTOs, and the Supabase write connector.
tags: [digibase, connectors, http-client, supabase]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
sources:
  - id: openwiki-source-d8b3f9cb7f77d6aa23c2355e
    resource: repo://digibase/src/digibase/connectors/base.py
  - id: openwiki-source-37e5df3c483ecf56f52f5f87
    resource: repo://digibase/src/digibase/connectors/supabase.py
  - id: openwiki-source-bbac12ef032ec955dbcfa5e8
    resource: repo://digibase/src/digibase/http_client.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digibase Connectors

Beyond the in-process helpers (errors, metrics, CORS, audit), digibase
owns the fleet's outbound-call posture: every service-to-service HTTP call
goes through bounded-timeout factories, and writes to external services go
through small connector DTOs. Both keep failure behavior uniform.

## Bounded httpx factories

Bare `httpx.AsyncClient()` waits forever on a slow upstream — unacceptable
on request paths. `digibase.http_client` centralizes one timeout envelope
and two factories:

- `DEFAULT_TIMEOUT`: connect 5s, read 30s (LLM streams legitimately idle
  between chunks), write 10s, pool 5s (a starved pool is a bug, not a
  reason to wedge a caller).
- `async_client(**kwargs)` / `sync_client(**kwargs)`: pre-configured
  clients; any `httpx` kwarg (including an explicit `timeout=` override)
  forwards verbatim. Passing `timeout=None` disables timeouts and is
  discouraged.

## Connector DTOs

`digibase.connectors.base` defines the abstract write-action protocol:
`ConnectorPayload` (`operation` + `data` dict) in, `ConnectorResult`
(`success`, `external_id`, `error`) out. Connectors are thin adapters over
these shapes, not frameworks.

## Supabase connector

`digibase.connectors.supabase.SupabaseConnector` (requires the
`digibase[supabase]` extra) wraps an injected Supabase client with
`upsert`, filtered `select`, and guarded filtered `delete`, plus audit
emission on writes. Construction is explicit (`__init__(client)` or
`from_env(...)`); `SupabaseNotConfiguredError` surfaces missing
configuration as a `RuntimeError` rather than an implicit `None` client.

## Roadmap boundary

A future digibase data-plane *service* (credential vending, quota, handle
brokering) does not exist — do not document or scaffold it. These
connectors are library code consumed at import time, with no port, no
listener, and no state.
