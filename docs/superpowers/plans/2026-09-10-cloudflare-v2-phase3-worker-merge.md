# Phase 3 — Cloudflare v2: merge `digithings-digichat` + `digithings-stack` into one Worker

> **Plan only — do not implement from this document until a human approves.**
> Spec only; no code changes land with this file.

- **Status:** Draft (2026-09-10)
- **Scope:** `frontend/digichat-cloudflare/`, `frontend/digithings-stack-cloudflare/`,
  `Dockerfile.digichat-cloudflare`, `Dockerfile.digithings-stack-cloudflare`,
  `digiquant/Dockerfile.mcp`, `.github/workflows/deploy-digichat-cloudflare-container.yml`,
  `.github/workflows/sync-cheaperinference-cf-secrets.yml`. Stay inside
  `/Users/chrisstefan/Code/digithings`; never touch sibling repos.
- **Parent:** [ADR-0018](../../adr/0018-digichat-path-routing.md) (path model + "one digichat
  process / sibling stack container" topology — this merge changes Worker packaging only).
- **Goal:** one Worker (`digithings-edge`) owning all Cloudflare zone routes + custom domains,
  fronting the same **3 container classes unchanged** (separate images, separate sleep policies),
  dispatched by hostname + path. `digithings-cron` stays a separate Worker (blast radius).
- **Tracking:** file a tracking issue before implementing; branch `task/<N>-edge-merge`
  per `AGENTS.md` (component routing: Cloudflare edge work PRs into `develop` via the
  website/one-hop path only if `scripts/project_routing.json` says so — check at branch time).

## Current state (verified 2026-09-10 — read from repo, not from memory)

### Worker A — `digithings-digichat` (`frontend/digichat-cloudflare/`)

- `name = "digithings-digichat"`, `main = "src/index.ts"`, `compatibility_date = "2026-08-01"`,
  `compatibility_flags = ["nodejs_compat"]`. No `workers_dev` key (workers.dev off).
- 7 zone routes on `digithings.ai` (all `zone_name = "digithings.ai"`, patterns byte-exact):
  `embed*`, `api/chat*`, `api/embed*`, `api/byok*`, `api/plan-proof*`, `api/health` (exact),
  `_dtchat*`.
- `src/paths.ts`: `shouldProxyToDigiChat(pathname)` — exact `/embed`, prefix `/embed/`,
  exact `/api/chat`, prefix `/api/chat/`, prefixes `/api/embed/`, `/api/byok/`, exact
  `/api/plan-proof`, prefix `/api/plan-proof/`, exact `/api/health`, prefix `/_dtchat/`.
  `SHARED_DIGICHAT_CONTAINER_ID = "shared-v6"`.
- `src/index.ts`: `DigiChatContainer extends Container`, `defaultPort = 3000`,
  `sleepAfter = "15m"`, 13-key `envVars` (see § Env audit). `Env` has `DIGICHAT:
  DurableObjectNamespace<DigiChatContainer>` + the 13 strings. `fetch()` 404s unless
  `shouldProxyToDigiChat`, else `getContainer(workerEnv.DIGICHAT, "shared-v6")`.
- `[[containers]]`: `class_name = "DigiChatContainer"`,
  `image = "../../Dockerfile.digichat-cloudflare"`, `max_instances = 5`. No `instance_type`
  (default lite). `[[durable_objects.bindings]] DIGICHAT`. `[[migrations]] tag = "v1"`,
  `new_sqlite_classes = ["DigiChatContainer"]`.
- Deploy: `.github/workflows/deploy-digichat-cloudflare-container.yml` — push to `main`,
  **version gate** (`frontend/digichat/package.json` version change) OR wrapper change
  (`frontend/digichat-cloudflare/**`, `Dockerfile.digichat-cloudflare`), plus
  `workflow_dispatch`. Deploys with `cloudflare/wrangler-action@v3`, workspace wrangler
  (lockfile 4.120.x line — accepts `deploy --message digichat-v<VERSION>`), secrets
  `CHEAPERINFERENCE_API_KEY`, `OPENROUTER_API_KEY` via the action's `secrets:` input.
- Tests: `src/paths.test.ts` (embed/API paths proxied; `/`, `/chat`, `/chat/occ`, `/docs`,
  `/_next/*` left alone). No combined test with stack routing.

### Worker B — `digithings-stack` (`frontend/digithings-stack-cloudflare/`)

- `name = "digithings-stack"`, `main = "src/index.ts"`, same compat date/flags,
  `workers_dev = true`.
- Custom domains: `graph.digithings.ai`, `key.digithings.ai` (`custom_domain = true`);
  `mcp.digithings.ai` route present but **commented out** (HUMAN GATE — MCP tools are
  unauthenticated localhost; enable only with Worker-edge digikey JWT enforcement).
- `src/ports.ts`: `DIGIGRAPH_PORT = 8000`, `DIGIKEY_PORT = 8005`, `DIGIQUANT_MCP_PORT = 8767`,
  `DIGIQUANT_MCP_HOSTNAME = "mcp.digithings.ai"`, `MCP_CONTAINER_ID = "mcp-v1"`,
  `SHARED_STACK_CONTAINER_ID = "shared-v14"`. `portForHostname`: `graph.*` → 8000,
  `key.*` → 8005, `*.workers.dev`/`localhost`/`127.0.0.1` → 8000, else `null`.
- `src/index.ts`: `DigiStackContainer` (`defaultPort = 8000`, `requiredPorts = [8000]`,
  `sleepAfter = "2h"`, ~30-key `envVars`, custom `fetch()` doing `startAndWaitForPorts`
  180s/60s then `containerFetch(request, targetPort)` via `cf-container-target-port` header)
  and `DigiQuantMcpContainer` (`defaultPort = 8767`, `sleepAfter = "24h"`, 6-key `envVars`).
  Worker `fetch()` order today: (1) `/_stack/meta` exact → JSON (no container);
  (2) `/_stack/key/*` → strip prefix → digikey :8005; (3) mcp hostname → MCP container;
  (4) `portForHostname` → stack container via `switchPort`, else 404.
- `[[containers]]` × 2: stack image `../../Dockerfile.digithings-stack-cloudflare`
  (`max_instances = 5`, `instance_type = "standard-2"`); MCP image
  `../../digiquant/Dockerfile.mcp` (`max_instances = 1`, `instance_type = "standard-2"`).
  Plus `[[containers.authorized_keys]] stack-debug`. DO bindings `STACK`, `MCP_STACK`.
  `[[migrations]] tag = "v1"` (stack) + `tag = "v2"` (mcp).
- Deploy: **manual** — `npx wrangler deploy` from `frontend/digithings-stack-cloudflare`
  (README). No push workflow. Secrets via `npx wrangler secret put` (long list in
  wrangler.toml comments) except `CHEAPERINFERENCE_API_KEY`/`OPENROUTER_API_KEY`, which go
  through `.github/workflows/sync-cheaperinference-cf-secrets.yml` via the **raw Workers
  Secrets HTTP API**, because wrangler 4.28 rejects `instance_type = "standard-2"`.
- Tests: `src/ports.test.ts` (graph/key/workers.dev/unknown), `src/env-vars-pin.test.js`
  (Env↔envVars parity both directions + key↔ref pairing + MCP-scoped vars confined to the
  MCP block). No combined test with digichat paths.

### Explicitly NOT changing

- Containers keep **separate images** (`Dockerfile.digichat-cloudflare`,
  `Dockerfile.digithings-stack-cloudflare`, `digiquant/Dockerfile.mcp`) — merging images is
  blocked by ADR-0018 ("digigraph is **not** packed into the digichat image").
- `sleepAfter` values are frozen: `15m` digichat, `2h` stack, `24h` mcp. Never touch.
- Traffic stays public HTTPS digichat→graph/key (`DIGIGRAPH_INTERNAL_URL`,
  `DIGIKEY_URL`); **no service bindings** between the containers.
- `digithings-cron` (`frontend/digithings-cron/`, thin Worker, no containers) is untouched —
  no shared code, no shared workflow, no shared wrangler config. Blast-radius isolation.
- `mcp.digithings.ai` stays dark (commented route) until its own JWT-gate issue lands.

## Global Constraints (blocking — violation fails the task PR)

1. **TDD.** Write the combined router precedence tests FIRST (T2), watch them fail against
   either current Worker, then implement. `npm run test` + `npm run typecheck` in the new
   package must be green before any deploy step is attempted.
2. **Per-class env audit is a blocking gate.** The 3-block parity/deny-list test (T3) must
   pass in CI; any `AUTH_SECRET` appearance outside the digichat block, or any
   `DIGIKEY_PRIVATE_KEY_PEM` appearance outside the stack block, fails the build.
3. **Never touch `sleepAfter` values** (`15m` / `2h` / `24h`) or container `defaultPort`s
   (`3000` / `8000` / `8767`) or DO container IDs (`shared-v6`, `shared-v14`, `mcp-v1`).
4. **Stay in-repo** (`/Users/chrisstefan/Code/digithings` only). No sibling repos.
5. **Cron untouched.** No import from `frontend/digithings-cron/`, no workflow edits there.
6. **No behavior change at cutover** except the Worker name: same routes, same containers,
   same secrets, same 404 surfaces. Any intentional surface change needs its own issue.

## Target design

New package `frontend/digithings-edge-cloudflare/` (Worker `digithings-edge`) that is the
union of both Workers. Old packages stay deployed until cutover (T7), then are archived
(not deleted — rollback needs their wrangler.tomls; see § Rollback).

### Merged dispatch order (normative — implement exactly this)

For `(hostname, pathname)` with `host = hostname.trim().toLowerCase()`:

1. `pathname === "/_stack/meta"` (any host) → worker-level JSON (no container). Unchanged
   payload: `{ ok, service, containerId: "shared-v14", note }` — keep `service:
   "digithings-stack"` string byte-identical so existing probes don't flap; only the
   Worker name in wrangler changes.
2. `pathname === "/_stack/key" || pathname.startsWith("/_stack/key/")` (any host) →
   strip `/​_stack/key` prefix, `switchPort(..., 8005)` on the STACK binding. Verbatim
   from stack `index.ts` (`rewriteKeyStackPath`).
3. `host === "mcp.digithings.ai"` → MCP container (`MCP_STACK`, `mcp-v1`). Route stays
   unreachable until the commented `[[routes]]` is enabled with the JWT gate (unchanged).
4. Apex chat host (`host === "digithings.ai"`, plus `www.`/`occ.` prefixes only insofar as
   zone routes deliver them — route patterns themselves are byte-identical to today's 7) →
   `shouldProxyToDigiChat(pathname)` ? digichat container (`DIGICHAT`, `shared-v6`, :3000)
   : `404 "digichat Worker: path not routed. Marketing /chat shells are on Pages."`
   (keep the exact 404 body so smoke-site probes keep matching).
5. `portForHostname(host)` → stack container via `switchPort` (`graph.*` → 8000,
   `key.*` → 8005, `*.workers.dev`/`localhost`/`127.0.0.1` → 8000), else 404 with the exact
   stack 404 body (`"digithings-stack: unknown host. Use graph.digithings.ai, …"` — keep
   the string; update only if the human approves a rename).

Why this order: rules 1–3 and 5 are today's stack order verbatim (zero behavior change for
graph/key/workers.dev). Rule 4 slots into the exact hole where stack's `portForHostname`
returns `null` for `digithings.ai` today (stack 404s apex; digichat serves it) — so the
merge is additive and the only new precedence surface is apex paths, which is what the
combined tests pin (§ T2). Critical pin: apex `/healthz` must **404** (never fall through
to digigraph), and `graph.digithings.ai/api/health` must hit **digigraph** (hostname wins;
digichat prefixes apply on apex only).

### Merged wrangler surface

- `name = "digithings-edge"`, `main = "src/index.ts"`, `compatibility_date = "2026-08-01"`,
  `compatibility_flags = ["nodejs_compat"]`, `workers_dev = true` (stack had it; digichat
  probes gain a workers.dev fallback — smoke-only, no traffic impact).
- Zone routes: today's 7 digichat `[[routes]]` verbatim + `graph`/`key` custom domains +
  still-commented `mcp` route with its HUMAN GATE comment intact.
- `[[containers]]` × 3 with today's `class_name`/`image`/`max_instances`/`instance_type`
  values copied byte-for-byte (digichat has no `instance_type`; do not add one).
  Keep `[[containers.authorized_keys]] stack-debug` with the same ed25519 key.
- DO bindings `DIGICHAT`, `STACK`, `MCP_STACK` (all three; names unchanged so container
  `getContainer` call sites copy verbatim).
- `[[migrations]]`: today's tags **collide** (`v1` exists in both workers with different
  classes — legal in separate workers, illegal merged). Renumber preserving order:
  `v1 = ["DigiChatContainer"]`, `v2 = ["DigiStackContainer"]`, `v3 =
  ["DigiQuantMcpContainer"]`. Class names are distinct so SQLite namespaces never clashed
  and still don't; only the tags needed linearizing. Full fragment in T4.

## Tasks

### T0 — Spike: wrangler `instance_type` + image-rebuild behavior (time-box 1h)

Files: none (scratch notes go in the tracking issue, not the repo).

- [ ] `npx wrangler --version` in repo root; record whether the workspace wrangler parses
  `instance_type = "standard-2"` (4.28.0 rejects it per `sync-cheaperinference-cf-secrets.yml`;
  lockfile comment in the digichat deploy workflow claims 4.120.x accepts `--message` —
  verify both flags together: `npx wrangler deploy --dry-run` equivalent or `wrangler
  containers` config validation from the new package dir once T4 exists).
- [ ] Verify whether `wrangler deploy` with 3 `[[containers]]` rebuilds all images or only
  changed ones (deploy twice with no changes; compare build output). This decides whether
  T6's change-detection can truly skip image rebuilds or only skip deploys.
- [ ] Verify whether `image = "<registry>@sha256:<digest>"` (GHCR, cf. `publish-service-images.yml`
  / `publish-digichat-image.yml`) is accepted for `[[containers]]` as an alternative to local
  Dockerfiles. If yes, T6 may pin digests; if no, local Dockerfiles stay and T6 documents
  the all-or-nothing rebuild as accepted cost.
- [ ] Record answers in the tracking issue; if wrangler still rejects `standard-2`, T5 keeps
  the raw-API secret sync for stack secrets and T6's deploy step must use a wrangler version
  that both accepts `instance_type` and `deploy --message` (or drop `--message`).

### T1 — Scaffold `frontend/digithings-edge-cloudflare/`

Files: `frontend/digithings-edge-cloudflare/{package.json,tsconfig.json,vitest.config.ts,src/}`.

- [ ] `package.json` — copy stack package verbatim, rename to `digithings-edge-cloudflare`:
  scripts `deploy`/`dev`/`test`/`typecheck`, devDeps `@cloudflare/containers ^0.0.30`,
  `@cloudflare/workers-types ^4.20250801.0`, `typescript ^5.8.0`, `vitest ^4.1.0`,
  `wrangler ^4.28.0` (bump only if T0 proves a newer minor is required for `instance_type`;
  record reason in the PR body).
- [ ] `tsconfig.json` — copy stack variant (`module ESNext`, `types
  ["@cloudflare/workers-types"]`, `include ["src/**/*.ts"]`; keeps `env-vars-pin.test.js`
  invisible to `tsc` while vitest runs it).
- [ ] `vitest.config.ts` — copy stack variant (`include: ["src/**/*.test.ts",
  "src/**/*.test.js"]` with the `.test.js` comment preserved).
- [ ] Root `package.json` workspaces (`frontend/*`) pick the package up automatically; run
  `npm install` at root and confirm `npm run test --workspace digithings-edge-cloudflare`
  runs (0 tests, green) before T2.

### T2 — Combined router: port `paths.ts` + `ports.ts` verbatim, add dispatcher + precedence tests (TDD)

Files: `frontend/digithings-edge-cloudflare/src/{routes.ts,routes.test.ts,ports.ts}`.
`routes.ts` = digichat `paths.ts` copied verbatim (`shouldProxyToDigiChat`,
`SHARED_DIGICHAT_CONTAINER_ID = "shared-v6"`). `ports.ts` = stack `ports.ts` copied
verbatim (all 7 exports, `SHARED_STACK_CONTAINER_ID = "shared-v14"`).

- [ ] Write `src/routes.test.ts` FIRST (combined precedence — this file is the new coverage
  neither worker has today). It imports `shouldProxyToDigiChat` from `./routes` and
  `portForHostname` from `./ports` plus the new `route()` dispatcher from `./dispatch`
  (written to satisfy the test):

```ts
import { describe, expect, it } from "vitest";
import { route } from "./dispatch";

describe("merged router precedence", () => {
  it("serves digichat BFF paths on the apex host", () => {
    expect(route("digithings.ai", "/embed?x=1").kind).toBe("digichat");
    expect(route("digithings.ai", "/embed").kind).toBe("digichat");
    expect(route("digithings.ai", "/api/chat/stream").kind).toBe("digichat");
    expect(route("digithings.ai", "/api/embed/tenant-config").kind).toBe("digichat");
    expect(route("digithings.ai", "/api/byok/test").kind).toBe("digichat");
    expect(route("digithings.ai", "/api/plan-proof/mint").kind).toBe("digichat");
    expect(route("digithings.ai", "/api/health").kind).toBe("digichat");
    expect(route("digithings.ai", "/_dtchat/_next/static/x.js").kind).toBe("digichat");
  });

  it("never leaks digigraph onto apex paths", () => {
    // Pages owns these; the merged worker must 404, not fall through to :8000.
    expect(route("digithings.ai", "/").kind).toBe("not-found");
    expect(route("digithings.ai", "/chat").kind).toBe("not-found");
    expect(route("digithings.ai", "/chat/occ").kind).toBe("not-found");
    expect(route("digithings.ai", "/healthz").kind).toBe("not-found");
    expect(route("digithings.ai", "/api/healthz").kind).toBe("not-found");
    expect(route("digithings.ai", "/_stack/meta").kind).toBe("meta"); // worker-level wins
  });

  it("keeps /api/health (digichat) distinct from /healthz (digigraph)", () => {
    expect(route("digithings.ai", "/api/health").kind).toBe("digichat");
    expect(route("graph.digithings.ai", "/healthz").kind).toBe("stack");
    expect(route("graph.digithings.ai", "/healthz")).toMatchObject({ kind: "stack", port: 8000 });
    // Hostname wins over path prefix: graph host never routes to digichat.
    expect(route("graph.digithings.ai", "/api/health").kind).toBe("stack");
    expect(route("key.digithings.ai", "/api/health").kind).toBe("stack");
  });

  it("preserves stack workers.dev fallbacks", () => {
    expect(route("digithings-edge.x.workers.dev", "/healthz")).toMatchObject({ kind: "stack", port: 8000 });
    expect(route("digithings-edge.x.workers.dev", "/_stack/meta").kind).toBe("meta");
    const k = route("digithings-edge.x.workers.dev", "/_stack/key/healthz");
    expect(k).toMatchObject({ kind: "stack", port: 8005, strippedPath: "/healthz" });
  });

  it("keeps the mcp hostname reserved and off workers.dev", () => {
    expect(route("mcp.digithings.ai", "/mcp").kind).toBe("mcp");
    expect(route("mcp.digithings.ai", "/_stack/meta").kind).toBe("meta");
    expect(route("digithings-edge.x.workers.dev", "/_stack/mcp/x").kind).toBe("not-found");
  });
});
```

- [ ] Implement `src/dispatch.ts` to satisfy it (pure function; no container imports so it
  runs under plain vitest). Actual sketch (no placeholders — ship this shape):

```ts
import { shouldProxyToDigiChat } from "./routes";
import {
  DIGIGRAPH_PORT,
  DIGIKEY_PORT,
  DIGIQUANT_MCP_HOSTNAME,
  portForHostname,
} from "./ports";

export type Target =
  | { kind: "digichat" }
  | { kind: "stack"; port: number; strippedPath?: string }
  | { kind: "mcp" }
  | { kind: "meta" }
  | { kind: "not-found" };

const APEX = new Set(["digithings.ai", "www.digithings.ai", "occ.digithings.ai"]);

export function route(hostname: string, pathname: string): Target {
  const host = hostname.trim().toLowerCase();
  if (pathname === "/_stack/meta") return { kind: "meta" };
  if (pathname === "/_stack/key" || pathname.startsWith("/_stack/key/")) {
    return { kind: "stack", port: DIGIKEY_PORT, strippedPath: pathname.replace(/^\/_stack\/key/, "") || "/" };
  }
  if (host === DIGIQUANT_MCP_HOSTNAME) return { kind: "mcp" };
  if (APEX.has(host)) return shouldProxyToDigiChat(pathname) ? { kind: "digichat" } : { kind: "not-found" };
  const port = portForHostname(host);
  return port === null ? { kind: "not-found" } : { kind: "stack", port };
}
```

  Note: `APEX` set lists today's embed hosts verbatim (`DIGICHAT_EMBED_HOSTS` default).
  Hostnames outside it that `portForHostname` also rejects (e.g. `evil.com`) stay 404 —
  same as both workers today. Case-insensitivity comes free via both helpers' existing
  normalization; add explicit `route("DIGITHINGS.AI", "/api/health")` → digichat case test.

### T3 — Port the 3 container classes + merged `Env` + per-class env audit (blocking gate)

Files: `frontend/digithings-edge-cloudflare/src/{index.ts,env-vars-pin.test.js}`.

- [ ] `src/index.ts`: copy `DigiChatContainer` (with its `fetch()` override — none; default),
  `DigiStackContainer` (with `startAndWaitForPorts` override verbatim), and
  `DigiQuantMcpContainer` (verbatim) into one file. `sleepAfter`/`defaultPort`/
  `requiredPorts`/`max_instances` untouched. `Env` = union of both current interfaces:
  `DIGICHAT` + `STACK` + `MCP_STACK` bindings plus every string member (digichat's 13 +
  stack's ~30; `DIGIKEY_BFF_TOKEN` declared once). Worker `fetch()` implements § Target
  design order, reusing `rewriteKeyStackPath`, `isMcpHostname`, `switchPort`,
  `getContainer` with today's container IDs.
- [ ] Extend `env-vars-pin.test.js` (copy stack's file verbatim first — its regexes expect
  `envVars = {` blocks at 2-space indent and `Env` string members) with a third block and
  cross-block deny lists. Actual additions (no placeholders):

```js
// Phase 3 merged worker: three envVars blocks in order — digichat, stack, mcp.
// Leak audit (blocking): a secret usable in one trust domain must never be
// forwarded into another container's process env.
const DIGICHAT_ONLY = new Set([
  "AUTH_SECRET",
  "DIGICHAT_EMBED_TENANTS",
  "DIGICHAT_PLAN_PROOF_SECRET",
  "DIGICHAT_DASHBOARD_SUPABASE_URL",
  "DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY",
  "DIGIGRAPH_INTERNAL_URL",
  "DIGIKEY_URL",
]);
const STACK_ONLY = new Set([
  "DIGIKEY_PRIVATE_KEY_PEM",
  "DIGIKEY_ADMIN_TOKEN",
  "DIGIKEY_DATABASE_URL",
]);
const MCP_ONLY = new Set([
  "DIGIQUANT_MARKET_DATA_BACKEND",
  "FRED_API_KEY",
  "R2_ACCOUNT_ID",
  "R2_BUCKET",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
]);
// Small by design: the only vars intentionally shared across blocks.
const SHARED_ALLOW = new Set([
  "DIGIKEY_BFF_TOKEN",
  "CHEAPERINFERENCE_API_KEY",
  "OPENROUTER_API_KEY",
]);
```

  Tests: (a) `blocks.length === 3`; (b) every `DIGICHAT_ONLY` key is in block 0 and absent
  from blocks 1–2; every `STACK_ONLY` key in block 1 only; every `MCP_ONLY` key in block 2
  only (replaces the old 2-block MCP duplication test, same technique:
  `extractEnvVarsKeysFromBody` per block); (c) any key appearing in >1 block must be in
  `SHARED_ALLOW`, else fail with the offending key names; (d) keep all four existing
  parity tests running against the union of the three blocks + merged `Env`.
- [ ] Keep today's overlap behavior explicit: `DIGIKEY_BFF_TOKEN` value must match across
  digichat/stack secrets at deploy time (same value, two `wrangler secret put` calls or one
  raw-API call each — T5). The test pins the *shape* (shared allowlist); T7 pins the *value*.

### T4 — Merged `wrangler.toml`

File: `frontend/digithings-edge-cloudflare/wrangler.toml`. Assemble from today's two files;
fragments below are the normative content (copy comments that carry live operator knowledge:
TRAP paragraph, HUMAN GATEs, DIGICHAT_VERSION note):

```toml
# digithings-edge — merged Cloudflare Worker (Phase 3 worker merge).
# One Worker, three containers (images + sleep policies unchanged):
#   DigiChatContainer      :3000 sleepAfter 15m  (digichat BFF, shared-v6)
#   DigiStackContainer     :8000 sleepAfter 2h   (Profile A stack, shared-v14)
#   DigiQuantMcpContainer  :8767 sleepAfter 24h  (market-data MCP, mcp-v1)
# digithings-cron stays a SEPARATE Worker (blast radius) — never merge it here.
name = "digithings-edge"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat"]
workers_dev = true

# --- Zone routes: digichat BFF on the apex (from digithings-digichat, verbatim) ---
[[routes]]
pattern = "digithings.ai/embed*"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/api/chat*"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/api/embed*"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/api/byok*"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/api/plan-proof*"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/api/health"
zone_name = "digithings.ai"
[[routes]]
pattern = "digithings.ai/_dtchat*"
zone_name = "digithings.ai"

# --- Custom domains: Profile A stack (from digithings-stack, verbatim) ---
[[routes]]
pattern = "graph.digithings.ai"
zone_name = "digithings.ai"
custom_domain = true

[[routes]]
pattern = "key.digithings.ai"
zone_name = "digithings.ai"
custom_domain = true

# HUMAN GATE — infra/network: mcp.digithings.ai exposes unauthenticated MCP tools.
# Enable ONLY together with Worker-edge digikey JWT enforcement (see T7 + #3780).
# [[routes]]
# pattern = "mcp.digithings.ai"
# zone_name = "digithings.ai"
# custom_domain = true

[[containers]]
class_name = "DigiChatContainer"
image = "../../Dockerfile.digichat-cloudflare"
# DIGICHAT_VERSION baked from frontend/digichat/package.json inside the Dockerfile.
max_instances = 5

[[containers]]
class_name = "DigiStackContainer"
image = "../../Dockerfile.digithings-stack-cloudflare"
max_instances = 5
# Multi-process Profile A needs real RAM/disk. NOTE: wrangler 4.28 rejects
# instance_type — see T0; keep raw-API secret sync until the floor version parses this.
instance_type = "standard-2"

[[containers]]
class_name = "DigiQuantMcpContainer"
image = "../../digiquant/Dockerfile.mcp"
max_instances = 1
instance_type = "standard-2"

[[containers.authorized_keys]]
name = "stack-debug"
public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOWKJSXCImobvGW1hFjW5VV4mSM5ZnFoC/sTsW/cdFD9 digithings-stack-debug"

[[durable_objects.bindings]]
name = "DIGICHAT"
class_name = "DigiChatContainer"

[[durable_objects.bindings]]
name = "STACK"
class_name = "DigiStackContainer"

[[durable_objects.bindings]]
name = "MCP_STACK"
class_name = "DigiQuantMcpContainer"

# Tags linearized: v1 digichat + v1/v2 stack collided across the two old workers.
# Class names are distinct, so only tags needed renumbering.
[[migrations]]
tag = "v1"
new_sqlite_classes = ["DigiChatContainer"]

[[migrations]]
tag = "v2"
new_sqlite_classes = ["DigiStackContainer"]

[[migrations]]
tag = "v3"
new_sqlite_classes = ["DigiQuantMcpContainer"]
```

- [ ] `[vars]` = union of both current `[vars]` blocks, digichat keys first then stack keys,
  values byte-identical (including the `DIGI_TENANT_CORPUS_MAP` JSON and the
  `DIGI_ALLOWED_TOOLS`/`digiproject.yaml` sync comment). On conflict the stack value wins
  only where the key is literally the same name — today there are no same-name `[vars]`
  conflicts (overlap is secrets-only); assert that in the PR body with a diff.
- [ ] Secret comments: merge both files' secret lists + keep the `CLOUDFLARE_API_TOKEN`
  TRAP paragraph verbatim (it bites every new operator).
- [ ] Validate: `npx wrangler deploy --dry-run` (or T0's proven equivalent) from the new
  dir parses routes + all three `[[containers]]`.

### T5 — Secrets inventory + sync workflow update

- [ ] Inventory (source of truth — set each via `wrangler secret put` on `digithings-edge`
  except where noted):
  digichat-scoped: `AUTH_SECRET`, `DIGICHAT_EMBED_TENANTS`, `DIGIGRAPH_INTERNAL_URL`
  (= `https://graph.digithings.ai`), `DIGIKEY_URL` (= `https://key.digithings.ai`),
  `DIGIKEY_BFF_TOKEN` (same value as stack), `DIGICHAT_PLAN_PROOF_SECRET`,
  `DIGICHAT_DASHBOARD_SUPABASE_URL`, `DIGICHAT_DASHBOARD_SUPABASE_ANON_KEY`;
  stack-scoped: `DIGIKEY_BFF_TOKEN`, `DIGIKEY_PRIVATE_KEY_PEM`, `DIGIKEY_ADMIN_TOKEN`,
  `GROQ_API_KEY`/`OPENROUTER_API_KEY`/`OPENAI_API_KEY`, `CHEAPERINFERENCE_API_KEY`
  (+ optional `_BASE`, `DIGI_HOUSE_UPSTREAM`, `LITELLM_*`), Cloudflare/D1/Vectorize names,
  `D1_DATABASE_MAP`; mcp-scoped: `FRED_API_KEY`, `R2_ACCOUNT_ID`, `R2_BUCKET`,
  `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `DIGIQUANT_MARKET_DATA_BACKEND`.
- [ ] Update `sync-cheaperinference-cf-secrets.yml`: retarget `script="digithings-edge"`,
  keep the raw-API path for stack-scoped keys until T0 clears a wrangler floor; add an
  `inputs.deploy_edge` flag mirroring `deploy_digichat`. Keep syncing the two OLD workers
  until T7 cutover completes (rollback needs live secrets there), then remove them in the
  decommission PR.
- [ ] `DIGIKEY_BFF_TOKEN` equality check becomes a cutover checklist item (T7): read back
  both workers' secret presence via `wrangler secret list` on each script name (values are
  never readable — equality is established by writing the same value to both in one step).

### T6 — Unified deploy workflow with image-level change detection

New file `.github/workflows/deploy-digithings-edge.yml` (push to `main` + `workflow_dispatch`);
reconciles digichat's main+version-gate with stack's manual deploys (manual goes away —
everything rides this workflow). Old digichat workflow is disabled (not deleted) at cutover.

- [ ] Trigger paths (union; docs-only pushes deploy nothing):
  worker: `frontend/digithings-edge-cloudflare/**`,
  `.github/workflows/deploy-digithings-edge.yml`;
  digichat image: `frontend/digichat/package.json`, `frontend/digichat/**`,
  `frontend/digichat-ui/**`, `frontend/digiweb/design/**`, `frontend/digiweb/web/**`,
  `Dockerfile.digichat-cloudflare`;
  stack image: `Dockerfile.digithings-stack-cloudflare`,
  `frontend/digithings-stack-cloudflare/container/**`, `digibase/**`, `digikey/**`,
  `digismith/**`, `digillm/**`, `digigraph/**`, `digisearch/**`, `digivault/**`,
  `config/litellm.cheaperinference.yaml`, `infra/digichat-release/config/**`;
  mcp image: `digiquant/Dockerfile.mcp`, `digiquant/src/**`.
- [ ] `detect` job (mirrors the digichat workflow's `before`-SHA technique, extended per image):
  `git diff --name-only "$BEFORE" "$GITHUB_SHA"` mapped to outputs `worker`, `image_digichat`,
  `image_stack`, `image_mcp`, plus the digichat **version gate** (`BEFORE:frontend/digichat/
  package.json` vs current — deploy when the version changed even if paths above somehow
  miss it). Unresolvable `BEFORE` → fall back to live deployment message
  (`wrangler deployments list --name digithings-edge --json`, same `jq` annotation read the
  old workflow uses). `deploy = worker || image_* || version_changed || workflow_dispatch`.
  Log which images changed in the step summary — this is the change-detection record that
  justifies (or skips) the expensive rebuild.
- [ ] Accepted limitation (document in the workflow header + T0 findings): `wrangler deploy`
  rebuilds **all three** container images even when only one changed (verified in T0; if T0
  proves digest-pinned `image =` references work, switch the unchanged images to their last
  known GHCR digests instead). The gate above still avoids all-or-nothing rebuilds on
  unrelated pushes (the common case today: backend PRs that touch neither worker nor images
  deploy nothing), and per-image outputs tell the operator what actually needed rebuilding.
- [ ] `deploy` job: `npm ci` at root, `npm run test/typecheck --workspace
  digithings-edge-cloudflare`, then `wrangler deploy --message edge-<sha>-<digichat-v>`
  from the new dir (keeps the old `--message` convention greppable; drop `--message` only
  if T0 proves the floor wrangler rejects it). Secrets via `wrangler-action` `secrets:` for
  digichat-scoped + house keys; stack/mcp secrets via the T5 raw-API step in the same
  workflow (one job, two steps, same run — no split-brain window).
- [ ] `concurrency: group: deploy-digithings-edge`, `cancel-in-progress: false` (same as both
  predecessors — never cancel a container deploy mid-build).
- [ ] Keep `publish-digichat-image.yml` / `publish-service-images.yml` untouched (GHCR images
  serve self-hosted/client compose, never these Containers).

### T7 — Cutover runbook (human-gated steps marked 🔒)

- [ ] Pre: T0–T6 merged to `main`; edge package tests/typecheck green in CI.
- [ ] `wrangler secret put` full T5 inventory onto `digithings-edge` (staging values first if
  the account supports a second script name; else production values — secrets are the same
  values as the old workers, so this is a copy, not a rotation).
- [ ] Deploy edge from `main`; smoke on workers.dev:
  `/_stack/meta` → `{"ok":true}`, `/healthz` → digigraph, `/_stack/key/healthz` → digikey.
- [ ] 🔒 Move zone routes: remove the 7 `[[routes]]` from `frontend/digichat-cloudflare/
  wrangler.toml` and the 2 custom domains from `frontend/digithings-stack-cloudflare/
  wrangler.toml`, redeploy both old workers (now routeless), then deploy edge (now routed).
  Cloudflare allows a route on one worker at a time — the window serves Pages 404s on
  `/embed*` etc.; do this off-peak and announce in the tracking issue first.
- [ ] Smoke matrix (all must pass): `https://digithings.ai/api/health` (version ==
  `frontend/digichat/package.json`), `/embed?host=digithings.ai` 200,
  `https://graph.digithings.ai/healthz`, `https://key.digithings.ai/healthz`,
  `/_stack/meta` on workers.dev, apex `/` + `/chat` still Pages (200, not worker 404
  bodies), apex `/healthz` → worker 404 body (proves no digigraph leak).
- [ ] 🔒 Decommission (7 days after green): disable (not delete)
  `deploy-digichat-cloudflare-container.yml` via `on:` removal, stop `digithings-digichat`
  + `digithings-stack` workers in Dashboard, delete after the soak. Keep old packages +
  READMEs in-repo with a one-line "superseded by `frontend/digithings-edge-cloudflare/`"
  header (rollback + archaeology).

### T8 — Rollback (split back to two workers)

Trigger: any smoke-matrix failure in T7 not fixed within 1h, or container boot failures
(port probes 1101/503) on edge only.

- [ ] Restore the 7 `[[routes]]` + 2 custom domains in the two old wrangler.tomls (kept on
  `main` until decommission — never force-push them away), redeploy `digithings-digichat`
  via `workflow_dispatch` on the old workflow, redeploy stack manually per its README.
- [ ] Remove routes from edge (`wrangler deploy` a routeless edge) or delete the
  `digithings-edge` script; old workers' secrets were kept live through cutover (T5), so no
  secret restore is needed.
- [ ] DO state note: bindings create NEW namespaces (`digithings-edge`'s `DIGICHAT` ≠ old
  worker's `DIGICHAT`), so edge containers boot fresh Firecracker instances — digikey's
  sqlite (`sqlite:////data/digikey.db`) starts empty on edge and re-seeds; rollback
  returns to the old instances (old DOs persist until sleep + GC). No shared container
  disk is ever migrated; if digikey key material must survive, export/import via digikey
  ops tooling before cutover (confirm in T7 pre-checks).

## Acceptance criteria

- [ ] `npm run test --workspace digithings-edge-cloudflare` green: ported `paths`-equivalent,
  `ports`-equivalent, 3-block env audit, and the 5 combined precedence groups in T2
  (apex isolation, `/api/health` vs `/healthz`, workers.dev fallbacks, mcp reservation,
  meta-wins-everywhere).
- [ ] `npm run typecheck` green; `wrangler deploy --dry-run` (or T0 equivalent) parses the
  merged TOML with 9 routes + 3 containers + 3 migrations.
- [ ] Staging/workers.dev smoke (T7 matrix) green on `digithings-edge` before any zone route
  moves.
- [ ] Production smoke matrix green after route move; digichat version endpoint matches
  `frontend/digichat/package.json`; Pages `/chat` + `/chat/occ` unaffected.
- [ ] Old deploy workflow disabled, old workers stopped, edge workflow owns all future
  deploys; `sync-cheaperinference-cf-secrets.yml` targets `digithings-edge` only.
- [ ] `sleepAfter`, ports, container IDs, images, and secret VALUES identical to pre-merge
  (only Worker name + migration tags changed).

## Risks / open questions

1. **Wrangler `instance_type` floor (T0).** 4.28.0 rejects `standard-2`; the lockfile comment
   claims 4.120.x works. If no single version accepts both `instance_type` and
   `deploy --message`, drop `--message` (cosmetic) and keep `instance_type` (functional).
   Raw-API secret sync stays regardless until proven otherwise.
2. **All-or-nothing image rebuilds (T6).** `wrangler deploy` likely rebuilds all 3 images per
   push touching any of them (Node + Python + MCP toolchains on every deploy). The detect
   gate fixes the common case (unrelated pushes deploy nothing); per-image digest pinning
   needs the T0 GHCR-spike to be real. Cost of being wrong: ~10min Cloudflare builds on
   stack-only changes — accepted, documented, not silent.
3. **Route-move window (T7).** Routes are single-owner; the move has a minutes-long window
   where `/embed*` serves Pages 404s. Mitigation: off-peak, announce, pre-verified edge.
   No blue/green exists for zone routes on one zone.
4. **Fresh DO namespaces.** New worker = new container instances = cold boot of all three
   images at cutover + empty digikey sqlite until re-seed. Schedule the move when a cold
   start is affordable; warm via the smoke matrix itself (each probe boots its container).
5. **`workers_dev = true` widens digichat's surface** (it never had workers.dev). Only
   digichat paths served there are the same BFF paths as production; embed hosts still
   gate framing. Accepted; note in the PR body.
6. **MCP route stays dark.** The commented `mcp.digithings.ai` block moves verbatim; its
   HUMAN GATE (Worker-edge JWT) is out of scope for this merge — do not enable it here.
7. **No service bindings** (per constraints): digichat→graph/key stays public HTTPS. If
   latency/egress ever forces private routing, that's a new ADR, not part of this merge.
