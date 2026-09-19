---
type: library-guide
title: digibase Connectors
description: digibase outbound clients — bounded httpx factories and the Supabase write/read connector with guarded delete, idempotent upserts, and redacted audit.
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
  - id: openwiki-source-6c0b9f345db11c6891ed83e5
    resource: repo://tests/db/connectors/test_supabase_connector.py
generated: { by: "openwiki/0.5.0", at: "2026-09-19T12:20:11.463Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-19T12:20:11.463Z
---

# digibase Connectors

Beyond the in-process helpers (errors, metrics, CORS, audit), digibase
owns the fleet's outbound-call posture: every service-to-service HTTP call
goes through bounded-timeout factories, and writes to external services go
through the `SupabaseConnector` with typed result DTOs and redacted audit.

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

## Supabase connector

`digibase.connectors.supabase.SupabaseConnector` (requires the
`digibase[supabase]` extra) consolidates hand-rolled Supabase access
scattered across services into a single dependency-injectable wrapper. It
replaces ad-hoc `client.table(T).upsert(...)` / `.select(...).eq(...)`
chains with typed, exception-safe methods.

### Construction

The connector accepts an injected `SupabaseClient` Protocol — the minimal
surface of the real `supabase` Python client (`table(name) -> query
builder`). This Protocol shape lets unit tests use in-memory fakes without
the optional dependency or a live database.

Two construction paths exist:

- **`SupabaseConnector(client)`** — direct injection for tests, or callers
  that already hold a live `supabase.Client`.
- **`SupabaseConnector.from_env(**kwargs)`** — resolves `SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` (overridable via `url_var` / `key_var`),
  defers the `supabase` package import (so importing the module never
  requires the optional dependency), and constructs a live client.

When either environment variable is unset or blank, `from_env` raises
`SupabaseNotConfiguredError` (a `RuntimeError`) rather than returning an
implicit `None` client.

### Result types

The connector defines its own concrete result dataclasses — there is no
abstract base protocol.

- **`SupabaseWriteResult`** — `success: bool`, `table: str`, `rows: int`
  (rows *sent*, not the count PostgREST echoes back), `error: str`.
- **`SupabaseReadResult`** — `success: bool`, `rows: list[dict[str, Any]]`
  (decoded `response.data`), `count: int | None` (server-side count when
  `count=` is requested), `error: str`.

### Upsert

`upsert(table, rows, *, on_conflict=None, chunk=DEFAULT_CHUNK)` accepts a
single row dict or a list of row dicts. Idempotent when `on_conflict` names
the row's unique key(s) — replays update in place instead of duplicating.

Large lists are sent in batches of `chunk` rows (default 500, matching the
settled value from both twelve-x and digiquant services), so a single
request never exceeds PostgREST default request-size limits.

When `on_conflict` is `None`, the kwarg is omitted entirely from the
underlying `client.table(t).upsert(rows)` call — byte-identical to the bare
form used in production (e.g. digiquant ledger writes).

Failures are caught and returned as `SupabaseWriteResult(success=False,
error=...)` rather than raising. An empty list is a no-op success.

### Select

`select(table, columns="*", *, eq, gte, lte, in_, order, desc, limit, count)`
runs a filtered `select` with PostgREST filter composition (logical AND
across all provided filters). Each filter dict maps `column → value`;
`in_` maps `column → iterable of values`.

When `count` is supplied (e.g. `"exact"`, `"planned"`, `"estimated"`),
`SupabaseReadResult.count` is populated independently of `limit`.

### Guarded delete

`delete(table, *, eq, in_)` refuses unfiltered deletes: if neither `eq`
nor a non-empty `in_` filter is provided, it returns
`SupabaseWriteResult(success=False, error="refusing unfiltered delete: …")`
without issuing any request. This is a safety guard — the caller must
always specify which rows to delete.

On success, `SupabaseWriteResult.rows` reflects the count of deleted rows
from PostgREST's response.

### Audit

Every `upsert` and `delete` call emits a redacted audit line via
`digibase.audit.redact_mapping`. Only non-sensitive **metadata** is
audited: `table`, `operation`, `rows`, `on_conflict`, and (for deletes)
`filter_columns`. Row bodies are never logged — they may carry PII or
licensed data the shallow, key-name-based redactor cannot scrub. The audit
contract matches the explicit warnings in both digiquant Supabase modules.

### Package-level lazy loading

`digibase.connectors.__init__` makes `SupabaseConnector`,
`SupabaseReadResult`, and `SupabaseWriteResult` accessible via
`__getattr__` lazy lookup. The `supabase` submodule is only imported when a
caller actually references one of those names, so
`import digibase.connectors` stays usable without the optional
`supabase` dependency.

## Roadmap boundary

A future digibase data-plane *service* (credential vending, quota, handle
brokering) does not exist — do not document or scaffold it. These
connectors are library code consumed at import time, with no port, no
listener, and no state.
