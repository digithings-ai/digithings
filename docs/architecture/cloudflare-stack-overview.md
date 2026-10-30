# The Cloudflare stack: how it is wired

What runs where, how a request finds it, and what the digithings chat and the OCC
chat share versus what keeps them apart. Every claim here names the file that
makes it true.

## The shape in one paragraph

Cloudflare serves three different jobs. **Cloudflare Pages** serves the two static
sites (`digithings.ai`, `digiquant.io`) — pre-built HTML, no server. **Workers**
are the edge logic: they own the hostnames, decide who may pass, inject tenant
config, and proxy to containers. **Containers** are the stateful services — a
Next.js app for chat, a supervised Linux image running digigraph, digikey,
digisearch, digivault and friends. Everything that must persist lives in **KV**,
**R2** or **D1**.

There is no server behind Pages, and no public port on any container: a container
is reachable only through the Worker that hosts it.

## Workers

| Worker | Owns | Source |
|---|---|---|
| `digithings-digichat` | `digithings.ai` — `/chat*`, `/chat/occ*`, `/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`, `/api/health`, `/api/mcp/helpdesk*`, `/_dtchat*`, `/_digichat/meta`, `/_digichat-admin*` | `apps/digichat-cloudflare/wrangler.toml:57-133` |
| `digithings-stack` | `graph.digithings.ai`, `key.digithings.ai`, `search.digithings.ai` (custom domains) | `apps/digithings-stack-cloudflare/wrangler.toml:43-83` |
| `digiquant-runner`, `twelvex-runner` | no routes; service-bound workers (`twelvex-runner` also serves the twelve-x data API, ex-`digidata-api`) | `apps/digiquant-runner/wrangler.toml:34-39`, `apps/twelvex-runner/wrangler.toml:38-43` |
| `digitrace-langfuse` | `trace.digithings.ai` (route commented out) | `apps/digitrace-langfuse/wrangler.toml:27-30` |
| `digithings-cron`, `corpus-index`, `dashboard-api` | workers.dev only, no routes | `apps/digithings-cron/wrangler.toml:9-13` etc. |

The two that matter for chat are `digithings-digichat` and `digithings-stack`.

## Containers

| Container | Hosted by | Port | Sleep | Runs |
|---|---|---|---|---|
| `DigiChatContainer` | digichat | 3000 | 1m | the Next.js chat app (basePath `/chat`) + in-image helpdesk-mcp on 8770 |
| `DigiStackContainer` | stack | 8000 | 5m | digigraph 8000, digikey 8005, digisearch 8002, digivault 8004, litellm 4000, searxng 8080, redis 6379, and the MCP servers digisearch-mcp 8765, digigraph-mcp 8766, digivault-mcp 8769 |
| `DigiQuantMcpContainer` | stack | 8767 | 1m | quant MCP |
| `DigiQuantRunnerContainer` | digiquant-runner | 8080 | 1m→30m | backtests |
| `TwelveXRunnerContainer` | twelvex-runner | 8080 | 2m | strategy runner |
| `LangfuseWebContainer` / `LangfuseWorkerContainer` | digitrace-langfuse | 3000 / 3030 | 5m / 7d | tracing |

Ports are from `apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf:23-177`
and the per-app `wrangler.toml` container blocks.

## Storage

| Store | Binding | Namespace / bucket | Used by |
|---|---|---|---|
| KV | `DIGICHAT_TENANTS_KV` | `361b710bee56466097053275404535ba` | digichat Worker: `embed-tenants`, `config-yaml` |
| KV | `TENANT_CONFIG` | **the same id** | stack Worker: `digikey-jwks` |
| R2 | `MARKET_DATA` | `digithings-archive` | stack market data |
| R2 | `ARCHIVE` | `digithings-archive` | digiquant-runner |
| D1 | `TWELVEX_DB` | `twelvex` | digidata-api |

One KV namespace is shared by two Workers (`apps/digichat-cloudflare/wrangler.toml:214`,
`apps/digithings-stack-cloudflare/wrangler.toml:287-289`). That is deliberate: the
digichat Worker publishes the config, the stack Worker caches the digikey JWKS
beside it.

## Three request paths

### 1. `digithings.ai/chat`

```
browser → Pages? no: the route wins
  → digithings-digichat Worker  (route /chat*)
  → isChatSurfacePath → containerPathFor (already /chat, passed through)
  → DigiChatContainer.fetch → Next.js on :3000
```

The container id is `shared-<rev12>`, injected at deploy time
(`apps/digichat-cloudflare/src/paths.ts:191,261-266`), so a new deploy addresses a
new instance rather than a warm one.

Before proxying, the Worker reads KV once per container boot and sets two env
vars on the container: `DIGICHAT_EMBED_TENANTS` from `embed-tenants`, and
`DIGICHAT_CONFIG_YAML` from `config-yaml`
(`apps/digichat-cloudflare/src/index.ts:149-157`).

If the container is down or at its instance limit, the Worker retries a bodyless
request twice, then answers `503 {"error":"container_unavailable"}` with
`Retry-After: 5` (`apps/digichat-cloudflare/src/container-retry.ts:47-78`).

The Pages shell waits for the iframe's `digichat:ready` for **30 seconds**, then
shows the error card (`apps/digithings-web/components/ChatEmbedShell.tsx:21-22,488,502`).
A cold start longer than that is what a stuck loading banner actually is.

### 2. `digithings.ai/chat/occ`

```
browser → digithings-digichat Worker (/chat*)
  → isLegacyInviteShellPath → legacyInviteGate
  → valid ?token= or occ_invite cookie?  (OCC_INVITE_KEY, constant-time)
      no  → fetch /__not-found__ → the site's own 404
      yes → set cookie, rewrite to /chat/embed?host=the gated tenant host,
            move the key to x-embed-token, drop ?token=
  → the SAME digichat Worker's container proxy → the SAME container
  → the app's embed route renders the chat directly (no Pages shell, no iframe)
```

One gate, one behaviour: `apps/digichat-cloudflare/src/legacy-invite-gate.ts` is the only
place the invite is checked. The token is `OCC_INVITE_KEY`; the Pages shell and
its twin gate were removed in the 2026-10-27 consolidation.

### 3. MCP: `search.digithings.ai/_stack/mcp/digisearch/mcp`

```
digichat container → https://search.digithings.ai/_stack/mcp/…
  → digithings-stack Worker (custom domain)
  → path prefix wins over host routing
  → authorizeMcpEdge:
        x-digi-mcp-key matches MCP_EDGE_KEY / MCP_EDGE_KEYS[id]?  → allow
        else Bearer JWT: RS256, JWKS by kid (KV-cached, else DIGIKEY_SELF),
                        exp/nbf/iat, iss, aud, scope mcp:<id>
  → mcpEdgeTarget: host becomes 127.0.0.1:<port>   (the Python MCP SDK 421s any other Host)
  → switchPort → DigiStackContainer on 8765 / 8769
```

`/_stack/mcp/*` is handled before host routing
(`apps/digithings-stack-cloudflare/src/index.ts:761-805`), so the same code serves
digisearch, digivault and the ticket server regardless of which hostname was
dialled. Auth modes are in `src/mcp-edge-auth.ts:507-539`, the host rewrite in
`src/mcp-edge-target.ts:13-18`.

## Shared versus siloed

**Shared, deliberately:**

- one Worker (`digithings-digichat`)
- one container instance for every tenant (`shared-<rev>`)
- one KV namespace
- one MCP edge and one stack container

**Siloed, by tenant key:**

| | digithings chat | OCC chat |
|---|---|---|
| entry URL | `/chat` | `/chat/occ` |
| gate | none | `OCC_INVITE_KEY` (token or cookie) |
| tenant key | `digithings.ai` | `the gated tenant host` |
| config source | KV `config-yaml` → `deployment` | KV `embed-tenants` → `the gated tenant host` |
| identity | `authScheme: jwt`, minted in the app | same path, same identity key |
| MCP servers | digisearch, digivault | helpdesk (static key), digisearch, digivault |
| tool visibility | house catalog | OCC catalog + skills pack `occ` |

The separation is made in exactly two places: the Worker's `legacyInviteGate` rewrites
`/chat/occ` onto the app's `/chat/embed` route with `host=occ.digithings.ai`
(`apps/digichat-cloudflare/src/legacy-invite-gate.ts`), and the `occ.digithings.ai` row exists
only in KV (`embed-tenants`) and in the `config-yaml` document. There is no second
Worker, no second container, no second KV, and no second shell.

That is the design's strength and its risk: one deployment serves every tenant,
so a defect in tenant resolution is not contained to one surface — which is what
happened when the MCP identity key was not forwarded and only the house tenant
could mint a token.

## Where configuration lives

| What | Where | Precedence |
|---|---|---|
| house deployment | KV `config-yaml` | KV → `[vars]`/secret `DIGICHAT_CONFIG_YAML` → file `DIGICHAT_CONFIG_PATH` → `defaults.yaml` |
| tenants (OCC, trials) | KV `embed-tenants` | KV host row (after `tokenEnv` refs resolve) → legacy secret → host dropped |
| MCP credentials | Worker secrets, referenced by name (`tokenEnv`) | never in KV |
| digikey JWKS | KV `digikey-jwks` | KV → `DIGIKEY_SELF` fetch → 401 |
| corpus routing | `DIGI_TENANT_CORPUS_MAP` + `_EXTRA` | primary wins on slug collision |

Config is read **once per container boot**, not per request
(`apps/digichat-cloudflare/src/index.ts:120-160`); the container's own loader caps
its memo at 5s (`apps/digichat/src/lib/deploy-config/loader.ts:65`). A KV edit
therefore takes effect on the next boot — the container sleeps after 1 minute of
idle — not instantly.

## Failure behaviour worth knowing

- **Container asleep**: first request pays a cold start; digikey measured 42.9 s
  cold against 0.6 s warm. The shell's patience is 30 s, so a cold stack can show
  the loading banner past the shell's threshold.
- **Instance limit**: 503 `container_unavailable` with `Retry-After: 5`.
- **MCP auth failure**: 401 with no detail in the body; the reason
  (`jwks_unavailable`, `missing_scope`, …) is only in the Worker log.
- **Wrong tenant**: falls back to `hosts[0]`, which is how `/chat` answered 307 to
  `/chat/embed` for weeks — a fallback that looks like a redirect bug.

## What is not here

the trial tenant's trial and dev chat do not run on this stack: they are the same image on
Azure Container Apps, configured by their own YAML. The Cloudflare stack is the
public surface (digithings.ai, OCC) plus the internal runners.
