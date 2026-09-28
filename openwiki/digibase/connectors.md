---
type: library-guide
title: digibase Connectors
description: digibase outbound clients — bounded httpx factories and the Supabase write connector (upsert, filtered select, guarded delete).
tags: [digibase, connectors, http-client, supabase]
sources:
  - id: openwiki-source-52ed21edd8e11967c0cbfb8d
    resource: repo://digibase/src/digibase/connectors/__init__.py
  - id: openwiki-source-37e5df3c483ecf56f52f5f87
    resource: repo://digibase/src/digibase/connectors/supabase.py
  - id: openwiki-source-bbac12ef032ec955dbcfa5e8
    resource: repo://digibase/src/digibase/http_client.py
  - id: openwiki-source-78a0b1f0b71bfd7778441cd1
    resource: repo://tests/db/connectors/test_connector_base_removed.py
generated: { by: "openwiki/0.5.0", at: "2026-09-23T13:25:31.068Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-23T13:25:31.068Z
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

## Connector packages

The `digibase.connectors` package (`__init__.py`) is lightweight: it
defines no abstract base class or protocol interface. Its `__all__` is
empty. Supabase connector names (`SupabaseConnector`, `SupabaseReadResult`,
`SupabaseWriteResult`) are exposed through a lazy `__getattr__` so that
`import digibase.connectors` does not require the `supabase` optional
dependency. Callers that need the Supabase connector import it directly
from `digibase.connectors.supabase`.

The former `ConnectorPayload` / `ConnectorResult` abstract protocol and the
`base.py` module were removed; a regression test asserts they stay gone
and that `import digibase.connectors` still succeeds.

## Supabase connector

`digibase.connectors.supabase.SupabaseConnector` (requires the
`digibase[supabase]` extra) consolidates hand-rolled Supabase access
scattered across services (twelve-x node stores, history, calendar_db;
digiquant research, prices). It wraps an injected client behind a
`SupabaseClient` Protocol — callers inject a real `supabase.Client` or a
test fake without pulling the optional dependency.

### Construction

- `SupabaseConnector(client)` — explicit dependency injection, preferred
  for testing and for callers that already hold a `supabase.Client`.
- `SupabaseConnector.from_env(url_var=..., key_var=...)` — resolves
  `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from the environment,
  imports the `supabase` package lazily (so the module imports without it),
  and constructs a live client. Raises `SupabaseNotConfiguredError`
  (a `RuntimeError`) when either variable is missing or blank.

The `.client` property exposes the underlying client as an escape hatch for
unwrapped calls.

### Write operations

**Upsert** (`upsert(table, rows, *, on_conflict=None, chunk=500)`):

- Accepts a single `dict` or a list of `dict`s.
- When `on_conflict` names unique-key columns the upsert is idempotent:
  replays update in place instead of duplicating rows.
- Large lists are split into batches of `chunk` rows (default 500, chosen
  to stay under PostgREST request-size limits).
- Returns `SupabaseWriteResult(success, table, rows, error)` — callers
  branch on `success`/`error` without `try`/`except`.

**Delete** (`delete(table, *, eq=None, in_=None)`):

- Requires at least one equality or non-empty membership filter. An
  unfiltered delete is refused with `success=False` and an error string.
- Returns `SupabaseWriteResult` with the count of actually deleted rows.

### Read operations

**Select** (`select(table, columns="*", *, eq, gte, lte, in_, order, desc, limit, count)`):

- Accepts column-level equality, range, and membership filters composed
  as PostgREST logical AND.
- Optional `count` parameter (`"exact"`, `"planned"`, `"estimated"`)
  populates `SupabaseReadResult.count` with the server-side total.
- Returns `SupabaseReadResult(success, rows, count, error)`. The `rows`
  field is the decoded `response.data` list (or `[]` on failure).

### Error handling

All three operations catch transport/client exceptions internally and
return a result with `success=False` and the error string, rather than
raising. Errors are logged at `ERROR` level.

### Audit

Every write emits a redacted audit line via `digibase.audit.redact_mapping`.
Only non-sensitive metadata — table name, operation, row count,
`on_conflict` columns — is logged. Row bodies are never audited because
they may carry PII or licensed data that the shallow key-name redactor
cannot scrub.

## Roadmap boundary

A future digibase data-plane *service* (credential vending, quota, handle
brokering) does not exist — do not document or scaffold it. These
connectors are library code consumed at import time, with no port, no
listener, and no state.
