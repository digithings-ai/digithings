# digichat unification — handoff

**Updated:** 2026-08-09 · digigraph-centric adapters (#2009)

## Current product shape

digichat is a modular frontend + BFF. Adapters translate backend streams into
`DigiChatActivity`. digithings tenants use **digigraph** only (digillm + digivault
hub). Client embeds use **foundry**. Removed: digichat Node `external-relay` and
`digivault` backends.

Canonical note: [`docs/architecture/digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md).
Runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).
ADR: [`docs/adr/0018-digichat-path-routing.md`](../adr/0018-digichat-path-routing.md).

## Status

| Phase | Status |
|---|---|
| 1 Activity protocol | Shipped (#1817) |
| 2 digivault provider in digichat Node | Shipped then **removed** as digichat backend (#2009) — digivault is digigraph-only |
| 3 Marketing chat | digithings.ai/chat iframes digichat digigraph (#2009); Pages OpenRouter Function → 410 |

## Follow-ups

- Foundry adapter polish: #2011
- Operator: stand up Compose + Cloudflare Tunnel; set `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`

## Naming

Digi module names are always lowercase in prose ([PR #2007](https://github.com/digithings-ai/digithings/pull/2007)).
