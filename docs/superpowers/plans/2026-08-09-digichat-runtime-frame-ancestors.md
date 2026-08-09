# digichat Runtime CSP frame-ancestors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let operators allow any client embed parent on the **stock** digichat GHCR image via **runtime** env (`DIGICHAT_EMBED_HOSTS` and/or `DIGICHAT_EMBED_TENANTS` host keys), without rebuilding for `DIGICHAT_EMBED_HOSTS` / `embed-hosts.txt`.

**Architecture:** Next.js 16.2.4 evaluates `next.config.ts` `headers()` at **build** time and bakes CSP into the routes manifest — that is why today’s GHCR image cannot admit new parents without a rebuild. Move `/embed` `frame-ancestors` ownership to a request-time **`src/proxy.ts`** (Next 16 rename of middleware; digichat AGENTS.md still says “middleware” — follow `node_modules/next/dist/docs/…/proxy.md`). Keep a fail-closed baked header (`frame-ancestors 'none'`) on `/embed` in `next.config.ts` so a missing proxy cannot open framing. Proxy **overwrites** `Content-Security-Policy` with the runtime allowlist. Never emit `frame-ancestors *`.

**Tech Stack:** digichat Next.js 16 App Router (`proxy.ts` + `NextResponse`), existing `src/lib/security-headers.ts` / `embed-tenants.ts`, Vitest, GHCR digichat image, Compose env templates under `infra/digichat-release/`.

**Spec / product input:**
- [`docs/architecture/digichat-self-hosted-release.md`](../../architecture/digichat-self-hosted-release.md) §3 build-time gap + §5 Follow-ups
- [`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md) § Custom embed parent hosts
- Leftover from [`2026-08-09-digichat-self-hosted-release.md`](./2026-08-09-digichat-self-hosted-release.md) Follow-up #2

## Global Constraints

- Digi module names are always lowercase in prose (`digichat`, `digigraph`, `digikey`, `digivault`, `digithings`) — never DigiChat / DigiGraph.
- No shared SaaS digichat; stock install unit remains pinned `ghcr.io/digithings-ai/digichat:vX.Y.Z`.
- **Never** `frame-ancestors *` (or any wildcard origin that opens all parents).
- **Fail closed:** if no valid runtime host sources yield customer parents, `/embed` CSP must not allow arbitrary third-party framing (first-party digithings origins may remain; otherwise `'none'` / first-party-only).
- `DIGICHAT_EMBED_TENANTS` stays **runtime-only** (never a Docker build-arg — tokens leak in layers).
- `DIGICHAT_EMBED_HOSTS` is non-secret hostnames only; after this plan it is primarily a **runtime** container env (build-arg optional/legacy).
- Do **not** implement Pick 2 (stack GHCR) or Pick 3 (`scripts/docs_onboard` client docs onboard) here — note seams only (see **Fit with picks 2–3**).
- Every shipping PR must link a GitHub Issue (`task/<N>-slug` or `Fixes #<N>`).
- Before editing digichat code: read `frontend/digichat/AGENTS.md` + `ARCHITECTURE.md`; read Next 16 `proxy.md` under `node_modules/next/dist/docs/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/digichat/src/lib/security-headers.ts` | Pure host→origin parsing, reject `*`, build `frame-ancestors` string; callable per request |
| `frontend/digichat/src/lib/security-headers.test.ts` | Unit tests for parsing, fail-closed, no `*` |
| `frontend/digichat/src/proxy.ts` | Next 16 Proxy: match `/embed`, set runtime CSP (+ nosniff) |
| `frontend/digichat/src/proxy.test.ts` (or colocated) | Unit-test proxy header output with stubbed env |
| `frontend/digichat/next.config.ts` | `/embed` baked headers → fail-closed `frame-ancestors 'none'` only; app routes unchanged |
| `frontend/digichat/Dockerfile` | Stop requiring build-arg for CSP; comment that hosts are runtime |
| `.github/workflows/publish-digichat-image.yml` | Stop baking `DIGICHAT_EMBED_HOSTS` from `embed-hosts.txt` (or make no-op) |
| `frontend/digichat/embed-hosts.txt` | Reclassify as operator seed / docs list, not image bake input |
| `frontend/digichat/ARCHITECTURE.md` | CSP section + env table: runtime proxy owns `/embed` CSP |
| `docs/digichat/INSTALL.md` | Replace rebuild-first instructions with runtime env |
| `infra/digichat-release/.env.profile-a.example` / `.env.profile-b.example` | Document `DIGICHAT_EMBED_HOSTS` runtime (or registry-only) |
| `infra/digichat-digithings/README.md` | Drop “must build-arg CSP” operator copy |
| `docs/architecture/digichat-self-hosted-release.md` | Mark runtime CSP gap addressed |

---

## Current behavior (baseline — do not re-discover)

```text
publish-digichat-image.yml
  → reads embed-hosts.txt → DIGICHAT_EMBED_HOSTS build-arg
Dockerfile builder
  → ENV DIGICHAT_EMBED_HOSTS during `next build`
next.config.ts headers()
  → imports DIGICHAT_EMBED_SECURITY_HEADERS (evaluated once at build)
security-headers.embedFrameAncestors()
  → DIGICHAT_EMBED_HOSTS ?? registry keys + FIRST_PARTY (+ localhost in non-prod)
runner image
  → does NOT persist builder DIGICHAT_EMBED_HOSTS
  → runtime DIGICHAT_EMBED_HOSTS today has NO effect on baked CSP
```

**Acceptance after this plan:** `docker pull` stock image → set runtime `DIGICHAT_EMBED_HOSTS=client.example.com` (and/or tenants JSON with that host) → `curl -sI` `/embed` shows `frame-ancestors` including `https://client.example.com` → no rebuild.

---

## Security rules (lock these in tests)

1. Reject hostname tokens that are `*`, contain `*`, are empty, or are not valid hostnames after `normalizeEmbedHost`.
2. Never emit the literal `frame-ancestors *`.
3. Precedence (runtime): `DIGICHAT_EMBED_HOSTS` if set and yields ≥1 valid host → use it; else registry host keys from `DIGICHAT_EMBED_TENANTS`; always union with `FIRST_PARTY_FRAME_ANCESTORS`.
4. Production (`NODE_ENV=production`): no `http://localhost:*` in the list.
5. Fail closed for customer parents: with both sources empty/invalid, CSP is first-party only (or `'none'` if first-party is also stripped — prefer keep first-party for digithings.ai/chat).
6. Multiple CSP headers must not leave a restrictive baked policy intersecting a permissive proxy policy. Verify a **single** `Content-Security-Policy` on `/embed` after proxy overwrite (see Task 4 verification).

---

### Task 1: Harden host parsing + fail-closed builders (TDD)

**Files:**
- Modify: `frontend/digichat/src/lib/security-headers.ts`
- Modify: `frontend/digichat/src/lib/security-headers.test.ts`

**Interfaces:**
- Consumes: `normalizeEmbedHost` from `./embed-tenants` (optional — may keep local trim/split if already sufficient).
- Produces:
  - `parseEmbedHostsEnv(raw: string | undefined): string[]` — valid hostnames only; drops `*`, blanks, junk.
  - `embedFrameAncestors(): string[]` — same public name; must re-read `process.env` every call (no frozen module-level CSP string for embed).
  - `embedFrameAncestorsCsp(): string` — `frame-ancestors …;` never containing bare `*`.
  - `DIGICHAT_EMBED_FAIL_CLOSED_CSP` constant: `frame-ancestors 'none';` for next.config bake.
  - Keep `DIGICHAT_APP_*` unchanged.

- [ ] **Step 1: Write failing tests for reject-`*` and empty fail-closed**

Append to `security-headers.test.ts`:

```ts
describe("runtime embed host parsing (fail closed)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetEmbedTenantRegistryForTests();
  });

  it("rejects * and wildcard host tokens from DIGICHAT_EMBED_HOSTS", () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "*, *.example.com, client.example.com");
    resetEmbedTenantRegistryForTests();
    const list = embedFrameAncestors();
    expect(list.join(" ")).not.toMatch(/(^|\s)\*(?:\s|$)/);
    expect(list).not.toContain("https://*");
    expect(list).not.toContain("https://*.example.com");
    expect(list).toContain("https://client.example.com");
  });

  it("with no hosts and empty registry, stays first-party only (no open *)", () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetEmbedTenantRegistryForTests();
    vi.stubEnv("NODE_ENV", "production");
    const list = embedFrameAncestors();
    expect(list).toContain("https://digithings.ai");
    expect(list).not.toContain("https://random-client.example");
    expect(embedFrameAncestorsCsp()).not.toContain("frame-ancestors *");
  });

  it("uses runtime DIGICHAT_EMBED_HOSTS when set", () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "new-client.example.com");
    resetEmbedTenantRegistryForTests();
    expect(embedFrameAncestors()).toContain("https://new-client.example.com");
  });
});
```

- [ ] **Step 2: Run tests — expect FAIL or incomplete reject behavior**

Run:

```bash
cd frontend/digichat && npm run test -- src/lib/security-headers.test.ts
```

Expected: new `*` rejection cases fail until filtering exists (today `*` would become `https://*`).

- [ ] **Step 3: Implement parsing harden + fail-closed constant**

In `security-headers.ts`, replace `embedHostsFromEnv` with something equivalent to:

```ts
import { normalizeEmbedHost } from "./embed-tenants";

export const DIGICHAT_EMBED_FAIL_CLOSED_CSP = "frame-ancestors 'none';";

/** Valid hostnames only — never `*`, never empty. */
export function parseEmbedHostsEnv(raw: string | undefined): string[] {
  if (!raw?.trim()) return [];
  const out: string[] = [];
  for (const part of raw.split(",")) {
    const host = normalizeEmbedHost(part);
    if (!host) continue;
    if (host === "*" || host.includes("*")) continue;
    out.push(host);
  }
  return out;
}

function embedHostsFromEnv(): string[] | null {
  const raw = process.env.DIGICHAT_EMBED_HOSTS;
  if (raw === undefined || !raw.trim()) return null;
  const hosts = parseEmbedHostsEnv(raw);
  return hosts; // may be empty → caller treats as “set but empty” = no customer hosts
}
```

Update `embedFrameAncestors()`:

```ts
export function embedFrameAncestors(): string[] {
  const envParsed = embedHostsFromEnv();
  // If DIGICHAT_EMBED_HOSTS is set (even empty after filter), do not fall back to registry.
  // If unset (null), fall back to registry keys.
  const hosts =
    envParsed !== null ? envParsed : [...getEmbedTenantRegistry().keys()];
  const hostOrigins = hosts
    .map((h) => normalizeEmbedHost(h))
    .filter((h): h is string => !!h && h !== "*" && !h.includes("*"))
    .map((h) => `https://${h}`);
  const dev =
    process.env.NODE_ENV !== "production"
      ? ["http://localhost:*", "http://127.0.0.1:*"]
      : [];
  return [...FIRST_PARTY_FRAME_ANCESTORS, ...hostOrigins, ...dev];
}
```

Update comments: remove “must be present at build time for external hosts”; state proxy owns runtime CSP.

Keep `DIGICHAT_EMBED_SECURITY_HEADERS` **only** if still useful for tests — prefer exporting fail-closed headers for next.config:

```ts
export const DIGICHAT_EMBED_BAKED_SECURITY_HEADERS: ReadonlyArray<{
  key: string;
  value: string;
}> = [
  { key: "Content-Security-Policy", value: DIGICHAT_EMBED_FAIL_CLOSED_CSP },
  { key: "X-Content-Type-Options", value: "nosniff" },
];
```

Deprecate/remove build-time evaluation of `embedFrameAncestorsCsp()` inside a frozen `DIGICHAT_EMBED_SECURITY_HEADERS` value used by next.config (that freeze is the bug).

- [ ] **Step 4: Re-run tests — expect PASS**

```bash
cd frontend/digichat && npm run test -- src/lib/security-headers.test.ts
```

Expected: PASS. Adjust existing “prefers DIGICHAT_EMBED_HOSTS over registry” tests if empty-string semantics change — document chosen rule in test names.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/security-headers.ts \
  frontend/digichat/src/lib/security-headers.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): harden embed host parsing for runtime CSP

EOF
)"
```

---

### Task 2: next.config fail-closed bake (remove build-time allowlist)

**Files:**
- Modify: `frontend/digichat/next.config.ts`
- Modify: `frontend/digichat/src/lib/security-headers.test.ts` (header export assertions)

**Interfaces:**
- Consumes: `DIGICHAT_EMBED_BAKED_SECURITY_HEADERS`, `DIGICHAT_APP_SECURITY_HEADERS`.
- Produces: `/embed` routes always bake `frame-ancestors 'none'` at build; app routes unchanged.

- [ ] **Step 1: Point next.config embed sources at fail-closed headers**

```ts
import {
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_BAKED_SECURITY_HEADERS,
} from "./src/lib/security-headers";

// inside headers():
{
  source: "/embed/:path*",
  headers: [...DIGICHAT_EMBED_BAKED_SECURITY_HEADERS],
},
{
  source: "/embed",
  headers: [...DIGICHAT_EMBED_BAKED_SECURITY_HEADERS],
},
```

- [ ] **Step 2: Update unit expectations**

Replace assertions that `DIGICHAT_EMBED_SECURITY_HEADERS` CSP equals `embedFrameAncestorsCsp()` with: baked export is `'none'`; runtime helper still builds allowlists.

- [ ] **Step 3: Run unit tests**

```bash
cd frontend/digichat && npm run test -- src/lib/security-headers.test.ts
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/digichat/next.config.ts frontend/digichat/src/lib/security-headers.ts \
  frontend/digichat/src/lib/security-headers.test.ts
git commit -m "$(cat <<'EOF'
fix(digichat): bake fail-closed frame-ancestors on /embed

EOF
)"
```

---

### Task 3: `src/proxy.ts` sets runtime CSP on `/embed`

**Files:**
- Create: `frontend/digichat/src/proxy.ts`
- Create: `frontend/digichat/src/proxy.test.ts`
- Modify: `frontend/digichat/AGENTS.md` only if a one-line “Proxy owns embed CSP” note helps (optional)

**Interfaces:**
- Consumes: `embedFrameAncestorsCsp()` from `./lib/security-headers` (Node runtime — Next 16 Proxy defaults to Node.js).
- Produces: For matched `/embed` requests, response header `Content-Security-Policy` = runtime CSP; also set `X-Content-Type-Options: nosniff`.

Read first: `node_modules/next/dist/docs/01-app/03-api-reference/03-file-conventions/proxy.md` (execution order: config `headers` → Proxy). Proxy must **`headers.set`** CSP so the fail-closed bake is overwritten (not appended as a second CSP — browsers intersect multiple CSPs).

- [ ] **Step 1: Write failing proxy unit test**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";
import { resetEmbedTenantRegistryForTests } from "./lib/embed-tenants";

describe("proxy embed CSP", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetEmbedTenantRegistryForTests();
  });

  it("sets frame-ancestors from runtime DIGICHAT_EMBED_HOSTS", async () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "client.example.com");
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const req = new NextRequest("http://127.0.0.1:3000/embed?host=client.example.com");
    const res = proxy(req);
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("https://client.example.com");
    expect(csp).not.toContain("frame-ancestors *");
    expect(csp).not.toBe("frame-ancestors 'none';");
  });

  it("does not open * when hosts unset", async () => {
    vi.stubEnv("NODE_ENV", "production");
    resetEmbedTenantRegistryForTests();
    const req = new NextRequest("http://127.0.0.1:3000/embed");
    const res = proxy(req);
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).not.toContain("frame-ancestors *");
    expect(csp).toContain("https://digithings.ai");
  });
});
```

- [ ] **Step 2: Run test — expect FAIL (module missing)**

```bash
cd frontend/digichat && npm run test -- src/proxy.test.ts
```

Expected: FAIL — `proxy` not found.

- [ ] **Step 3: Implement `src/proxy.ts`**

```ts
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { embedFrameAncestorsCsp } from "./lib/security-headers";

export function proxy(_request: NextRequest) {
  const response = NextResponse.next();
  // Overwrite baked fail-closed CSP from next.config (do not append a second policy).
  response.headers.set("Content-Security-Policy", embedFrameAncestorsCsp());
  response.headers.set("X-Content-Type-Options", "nosniff");
  return response;
}

export const config = {
  matcher: ["/embed", "/embed/:path*"],
};
```

Keep the import graph lean: `security-headers` → `embed-tenants` is already used at build; Proxy runs on Node by default in Next 16 — acceptable. Do **not** import React / client UI.

If Vitest cannot import `next/server` cleanly, mirror the pattern used elsewhere in digichat tests or extract `applyEmbedCspHeaders(headers: Headers): void` and unit-test that without NextRequest.

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd frontend/digichat && npm run test -- src/proxy.test.ts src/lib/security-headers.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/proxy.ts frontend/digichat/src/proxy.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): set /embed frame-ancestors at request time via proxy

EOF
)"
```

---

### Task 4: Dockerfile + publish workflow — stop baking client hosts

**Files:**
- Modify: `frontend/digichat/Dockerfile`
- Modify: `.github/workflows/publish-digichat-image.yml`
- Modify: `frontend/digichat/embed-hosts.txt` (header comment only)

**Interfaces:**
- Consumes: none at build for CSP.
- Produces: published image CSP for new parents comes only from runtime env; `embed-hosts.txt` remains a documented seed list for operators (digithings + DataTap hostnames) to copy into Compose env if desired.

- [ ] **Step 1: Dockerfile comments + remove required build-arg**

Replace the builder DIGICHAT_EMBED_HOSTS block with:

```dockerfile
# /embed frame-ancestors are set at request time by src/proxy.ts from runtime
# DIGICHAT_EMBED_HOSTS and/or DIGICHAT_EMBED_TENANTS host keys.
# Do NOT pass DIGICHAT_EMBED_TENANTS as a build-arg (tokens in layer history).
# DIGICHAT_EMBED_HOSTS build-arg is unused for CSP after runtime proxy; omit it.
```

Delete `ARG DIGICHAT_EMBED_HOSTS` / `ENV DIGICHAT_EMBED_HOSTS=$…` from the builder stage unless something else still needs them (it should not).

- [ ] **Step 2: publish workflow — drop embed_hosts build-arg step**

Remove (or no-op) the “Read embed CSP hostnames” step and the `build-args: DIGICHAT_EMBED_HOSTS=…` from `docker/build-push-action`. Keep image tags unchanged.

- [ ] **Step 3: Retarget embed-hosts.txt header**

```text
# Seed list of known parent hostnames for operators (digithings + DataTap, etc.).
# Not baked into the GHCR image. Copy into runtime DIGICHAT_EMBED_HOSTS or rely on
# DIGICHAT_EMBED_TENANTS host keys — see docs/digichat/INSTALL.md § Custom embed parent hosts.
# One hostname per line; # comments ignored. No secrets.
```

- [ ] **Step 4: Smoke locally without full publish (dev server)**

```bash
cd frontend/digichat
DIGICHAT_EMBED_HOSTS=runtime-client.example.com NODE_ENV=production \
  npx next start --hostname 127.0.0.1 --port 3015 &
# after build: npm run build && next start …
sleep 2
curl -sI "http://127.0.0.1:3015/embed" | tr -d '\r' | tee /tmp/embed-headers.txt
rg -i "content-security-policy" /tmp/embed-headers.txt
# Expect exactly one CSP line containing https://runtime-client.example.com
# and NOT frame-ancestors *
kill %1
```

If `next start` needs a prior `npm run build`, run build with **no** DIGICHAT_EMBED_HOSTS, then start **with** the env set — that is the stock-image scenario.

Expected: CSP reflects runtime host; single header; no `*`.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/Dockerfile \
  .github/workflows/publish-digichat-image.yml \
  frontend/digichat/embed-hosts.txt
git commit -m "$(cat <<'EOF'
build(digichat): stop baking embed hosts into GHCR image CSP

EOF
)"
```

---

### Task 5: Docs + env templates + sketch gap close

**Files:**
- Modify: `docs/digichat/INSTALL.md` (§ Custom embed parent hosts)
- Modify: `frontend/digichat/ARCHITECTURE.md` (CSP + `DIGICHAT_EMBED_HOSTS` row)
- Modify: `infra/digichat-release/.env.profile-a.example`
- Modify: `infra/digichat-release/.env.profile-b.example`
- Modify: `infra/digichat-digithings/README.md` (build-arg CSP bullets)
- Modify: `docs/architecture/digichat-self-hosted-release.md` §3 + §5
- Modify: `frontend/digichat/.env.example` (comment: runtime CSP)

**Interfaces:**
- Consumes: Tasks 1–4 behavior.
- Produces: Operators told to set runtime hosts; rebuild path demoted to optional emergency only.

- [ ] **Step 1: Rewrite INSTALL.md CSP section**

Replace “Custom embed parent hosts (CSP)” with:

```markdown
## Custom embed parent hosts (CSP)

Stock GHCR digichat sets `/embed` `frame-ancestors` at **runtime** from:

1. `DIGICHAT_EMBED_HOSTS` — comma-separated parent hostnames (no secrets), and/or
2. Host keys (and aliases) in `DIGICHAT_EMBED_TENANTS` when `DIGICHAT_EMBED_HOSTS` is unset.

Example (Compose / ACA env):

```bash
DIGICHAT_EMBED_HOSTS=client.example.com,www.client.example.com
# still required for tokens / backend — never a build-arg:
DIGICHAT_EMBED_TENANTS={"client.example.com":{...}}
```

Security: digichat never emits `frame-ancestors *`. If neither source yields hosts,
only first-party digithings origins (plus `'self'`) remain allowlisted.

Optional seed list of known hosts: `frontend/digichat/embed-hosts.txt` (not baked into the image).
```

- [ ] **Step 2: ARCHITECTURE.md**

Update “The `/embed` CSP frame-ancestors…” paragraph: proxy owns runtime CSP; next.config bakes fail-closed `'none'`; build-arg no longer required. Update env table row for `DIGICHAT_EMBED_HOSTS` to say **runtime** (preferred) and mention proxy. Fix stale “EMBED_FRAME_ANCESTORS / digiquant.io only” wording in § CSP headers to match `embedFrameAncestors()` + proxy.

- [ ] **Step 3: Env examples**

Add to both profile `.env.*.example` files (commented or with example.com):

```bash
# Runtime CSP frame-ancestors (stock GHCR — no rebuild). Optional if hosts already
# appear as DIGICHAT_EMBED_TENANTS keys and DIGICHAT_EMBED_HOSTS is unset.
# DIGICHAT_EMBED_HOSTS=example.com,www.example.com
```

- [ ] **Step 4: Operator digithings README + sketch gaps**

- `infra/digichat-digithings/README.md`: replace “pass DIGICHAT_EMBED_HOSTS as a build-arg when building” with runtime env on the digichat service.
- Sketch §3: DIGICHAT_EMBED_HOSTS row → runtime; §5 mark baked-hosts gap **Addressed** with link to this plan + INSTALL; Follow-ups remove or strike “Runtime CSP frame-ancestors”.

- [ ] **Step 5: Naming + link check**

```bash
! rg -n '\bDigi(Chat|Graph|Key|Vault|Things)\b' \
  docs/digichat/INSTALL.md docs/architecture/digichat-self-hosted-release.md \
  frontend/digichat/ARCHITECTURE.md infra/digichat-release/ \
  || (echo "Fix Digi CamelCase in prose" && exit 1)
rg -n "runtime|frame-ancestors|DIGICHAT_EMBED_HOSTS" docs/digichat/INSTALL.md
rg -n "proxy\.ts|fail-closed|DIGICHAT_EMBED_FAIL_CLOSED" frontend/digichat/ARCHITECTURE.md
```

Expected: no CamelCase Digi product names; INSTALL describes runtime; ARCHITECTURE mentions proxy.

- [ ] **Step 6: Commit**

```bash
git add docs/digichat/INSTALL.md frontend/digichat/ARCHITECTURE.md \
  infra/digichat-release/.env.profile-a.example \
  infra/digichat-release/.env.profile-b.example \
  infra/digichat-digithings/README.md \
  docs/architecture/digichat-self-hosted-release.md \
  frontend/digichat/.env.example
git commit -m "$(cat <<'EOF'
docs(digichat): document runtime frame-ancestors for stock GHCR

EOF
)"
```

---

### Task 6: End-to-end acceptance

**Files:** none new — verification only; fix any doc/code drift discovered.

- [ ] **Step 1: Unit suite**

```bash
cd frontend/digichat && npm run test && npm run lint
```

Expected: PASS / zero errors.

- [ ] **Step 2: Build without embed hosts, run with runtime hosts**

```bash
cd frontend/digichat
unset DIGICHAT_EMBED_HOSTS DIGICHAT_EMBED_TENANTS
npm run build
DIGICHAT_EMBED_HOSTS=accept.example.com NODE_ENV=production \
  npm run start -- --hostname 127.0.0.1 --port 3016 &
sleep 3
curl -sI "http://127.0.0.1:3016/embed" | tr -d '\r' | tee /tmp/csp-accept.txt
# Exactly one Content-Security-Policy; includes https://accept.example.com; no *
python3 - <<'PY'
from pathlib import Path
t = Path("/tmp/csp-accept.txt").read_text().lower()
lines = [l for l in t.splitlines() if l.startswith("content-security-policy:")]
assert len(lines) == 1, lines
assert "https://accept.example.com" in lines[0]
assert "frame-ancestors *" not in lines[0]
assert "frame-ancestors 'none'" not in lines[0]
print("ok")
PY
kill %1
```

Expected: `ok`.

- [ ] **Step 3: Fail-closed smoke**

```bash
unset DIGICHAT_EMBED_HOSTS DIGICHAT_EMBED_TENANTS
DIGICHAT_EMBED_HOSTS= NODE_ENV=production npm run start -- --hostname 127.0.0.1 --port 3017 &
sleep 3
curl -sI "http://127.0.0.1:3017/embed" | tr -d '\r' | tee /tmp/csp-closed.txt
python3 - <<'PY'
from pathlib import Path
t = Path("/tmp/csp-closed.txt").read_text().lower()
line = [l for l in t.splitlines() if l.startswith("content-security-policy:")][0]
assert "frame-ancestors *" not in line
assert "https://evil.example" not in line
assert "https://digithings.ai" in line or "frame-ancestors 'none'" in line
print("ok fail-closed")
PY
kill %1
```

- [ ] **Step 4: Final commit only if drift fixes were needed**

```bash
# if any fixes:
git add -u
git commit -m "$(cat <<'EOF'
fix(digichat): runtime CSP acceptance follow-ups

EOF
)"
```

---

## Fit with picks 2–3

Integration assumptions and non-conflicts only — **do not implement** those picks in this plan.

### Pick 2 — stack GHCR (digikey / digigraph / digivault images)

| Seam | Assumption / must not conflict |
|---|---|
| digichat image | This plan only changes digichat Node CSP wiring. Profile A Compose continues to `image: ghcr.io/…/digichat:v…`. |
| Env surface | Runtime `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS` live on the **digichat** service. Stack GHCR work must not move those vars onto digigraph/digikey containers. |
| Compose overlays | `infra/digichat-release/compose.profile-a.yml` may later swap Python services to GHCR; keep digichat env blocks free for CSP hosts — do not bake hosts into stack images. |
| Publish workflows | digichat publish drops embed build-arg; new stack publish workflows must not reintroduce digichat CSP build-args “for consistency.” |

### Pick 3 — `scripts/docs_onboard` (crawl / OCR → digivault and/or digisearch)

| Seam | Assumption / must not conflict |
|---|---|
| Product model | Onboarded docs land in **client digivault** (and/or digisearch); digichat remains the same release. CSP parents are orthogonal to vault content. |
| Embed parents | Doc-chat demos still need the parent marketing host in runtime CSP (this pick) **and** vault notes (Pick 3). Neither replaces the other. |
| Config | Ingest pipelines must not require digichat rebuilds; they also must not put secrets into `DIGICHAT_EMBED_HOSTS`. |
| Scope boundary | Do not add crawl/OCR UI or digichat upload routes in this plan (AGENTS.md Phase 2 / sketch Follow-ups). |

---

## Spec coverage self-check

| Requirement | Task |
|---|---|
| Stock GHCR admits new parents without rebuild | 3, 4, 6 |
| Runtime config (not DIGICHAT_EMBED_HOSTS rebuild) | 1, 3, 5 |
| No `frame-ancestors *` | 1, 3, 6 |
| Fail closed when unset / invalid | 1, 2, 6 |
| Docs INSTALL + ARCHITECTURE + sketch gap | 5 |
| Fits picks 2–3 without implementing them | Fit section |
| Bite-sized TDD + commits | Tasks 1–6 |

## Placeholder scan

No TBD / “implement later” inside Tasks 1–6. Picks 2–3 are explicitly deferred seams only.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-09-digichat-runtime-frame-ancestors.md`.

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
**2. Inline Execution** — execute in-session with executing-plans checkpoints
