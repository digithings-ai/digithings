---
type: api-operations-guide
title: digivault Service and Operations
description: digivault service surface and operations — routes, store precedence, scopes, tenant binding, MCP dispatch, and container profile.
tags: [digivault, service, operations, mcp]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-177aa6b06017b843d46bc98a
    resource: repo://digivault/ARCHITECTURE.md
  - id: openwiki-source-ad16574e0f9e829f380e00a8
    resource: repo://digivault/src/digivault/path_scopes.py
  - id: openwiki-source-331e7bc2a90cadb69cd8d283
    resource: repo://digivault/src/digivault/server.py
  - id: openwiki-source-9c6ec740fa4898b68fc6fdd1
    resource: repo://digivault/src/digivault/tool_dispatch.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digivault Service and Operations

The service layer is a thin FastAPI + MCP + CLI shell over the core:
routes enforce scopes and tenant boundaries, then delegate to `Vault`,
the stores, or the canonical tool dispatch. Port 8004, host-loopback,
under the dedicated `digivault` Compose profile (not the always-on core
stack).

## Routes

`GET /healthz` (`{"ok": true}`, exempt) and `GET /v1/status` plus note
CRUD (`GET /v1/notes`, `GET /v1/notes/{name}`, writes), lint/backlinks/
tags endpoints, `POST /v1/notes/by-path` (body-carried `vault_path` /
`path_prefix`), and the orchestrator pair
(`POST /v1/orchestrator_tools`, `POST /v1/orchestrator_invoke`) that
digigraph drives. A per-app rate-limit middleware fronts writes.

## Scopes

`digivault_path_scopes` (defined here, never in digikey): public paths
exempt; reads need `digivault:read`; mutations need `digivault:write`.
`POST /v1/notes/by-path` is read-scoped despite being POST (body carries
the read key, method-gated so future verbs aren't widened);
`orchestrator_invoke` gates at read with the single mutating tool
(`create_note`) enforcing write itself by tool name.

## Tenant binding

`tenant_scope.enforce_tenant_path_prefix` binds a caller-supplied
`path_prefix` to the JWT tenant via `DIGI_TENANT_CORPUS_MAP`, server-side
in digivault: scopes prove route access, not corpus entitlement. No-op
when the map is unset (single-tenant); fails closed (403) once set, 503
when set-but-unusable. Complementary to digigraph's model-side prefix
overwrite (model-supplied prefixes are discarded unconditionally).

## Tool dispatch and MCP

`tool_dispatch.py` is canonical: `DISPATCH_TOOL_NAMES` equals
vault-local handlers plus runtime-only names (asserted), and both MCP
registration and `orchestrator_invoke` route through it — no duplicate
tables. `python -m digivault.mcp_server` is a thin transport wrapper
(default `127.0.0.1:8766`).

## Container

Loopback-bound `:8004` on the `digivault` profile with a `/healthz`
healthcheck. Standard digibase middleware applies.
