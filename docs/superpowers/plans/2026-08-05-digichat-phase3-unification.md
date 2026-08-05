# DigiChat Phase 3 Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut digithings.ai `/chat` over to a digichat `/embed` iframe (digithings-owned digichat runtime), land `digichat:ready` → `digichat:seed` handoff, first-party host auth (no token), independent tenant UI flags, and delete the Cloudflare Function + `useStackChat` + `chatStream` in **one PR**.

**Architecture:** digithings-web keeps URL `/chat` and `DtNav` outside the iframe. The pane is digichat `/embed?host=https://digithings.ai` on `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` (prod: `https://digithings.ai` — same-origin path; CF routes `/embed*` to DigiThings-owned DigiChat Node). First-party allowlisted hosts skip embed tokens; customer tenants still require tokens. Landing `writeHandoff` stays localStorage on digithings.ai; the parent `readAndClearHandoff`s and posts seed after ready. Digithings digichat is a DigiThings-owned GHCR install with digivault env-name refs (Phase 2), not DataTap’s ACA and not `chat.digithings.ai`.

**Tech Stack:** TypeScript, Next.js 16 (digichat App Router + digithings-web static export), Vitest, `@digithings/digichat-ui`, Cloudflare Pages `_headers` CSP, postMessage origin checks.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-digichat-phase3-unification-design.md`. Do not relitigate Phase 1/2, DataTap `gateMode` / trial_form, or the accent bug.
- **One PR** covers digichat + digithings-web cutover + deletes. No iframe-first / delete-later sequence; no long-lived dual path.
- **Hostname (locked here):** DigiChat public origin is `https://digithings.ai` with path `/embed` (Cloudflare route → DigiThings-owned Node). digithings.ai `/chat` remains the Pages shell (DtNav + iframe). Env var: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai` (no trailing slash). Do **not** use `chat.digithings.ai`. Leave `DIGICHAT_BASE_PATH` unset. CSP: `frame-src 'self'`.
- **First-party allowlist (prod only):** hostnames `digithings.ai` and `www.digithings.ai`. Preview `*.pages.dev` is **not** allowlisted. Do not add preview hosts in this phase.
- **UI flags:** `showByok`, `showStatusBar`, `layout` live on `EmbedTenantConfig` (tenant JSON), projected to the client via `/api/embed/tenant-config`. Never derive `showByok = !ungated`. Defaults when omitted: `showByok: false`, `showStatusBar: false`, `layout: "embed"`.
- Digithings tenant (ops JSON): `slug: "digithings"`, `gateMode: "ungated"`, `showByok: true`, `showStatusBar: true`, `layout: "page"`, `activityDetail: "full"`, `backend.type: "digivault"` with `*Env` name refs, `aliases: ["www.digithings.ai"]`, `token` still required in schema (skipped at request time for first-party hosts only).
- postMessage types: `digichat:ready` and `digichat:seed` only (parallel to DataTap `datatap:gated` / `datatap:unlocked` — leave DataTap alone). Never `targetOrigin: "*"`.
- Seed payload caps: `MAX_SEED_MESSAGES = 40`, `MAX_SEED_CONTENT_CHARS = 8000`, `MAX_SEED_PENDING_CHARS = 4000`, `MAX_SEED_AGE_MS = 5 * 60 * 1000`. Ready wait: `READY_TIMEOUT_MS = 8000`. Timeout / load-failure copy: `"Chat is taking too long to load. Refresh to try again."`
- Digivault secrets remain env **names** only; missing → fail-closed `chat_not_configured` 503.
- ACR automation is out of scope; rollout checklist must mention manual GHCR→ACR mirror if the digithings install pulls from ACR.
- Run digichat tests: `cd frontend/digichat && npx vitest run <path>`. Run digithings-web tests: `cd frontend/digithings-web && npx vitest run <path>` (vitest added in Task 8).
- Presentation-only digithings-web CSS/shell changes are exempt from `make score` Python rubrics; digichat TypeScript still needs green Vitest.

---

## File Structure

| File | Responsibility |
|---|---|
| `frontend/digichat/src/lib/embed-first-party.ts` | First-party hostname set + `isFirstPartyEmbedHost` |
| `frontend/digichat/src/lib/embed-chat-tenant.ts` | Skip token when first-party + registered |
| `frontend/digichat/src/lib/embed-tenants.ts` | Parse `showByok` / `showStatusBar` / `layout` |
| `frontend/digichat/src/hooks/use-embed-tenant-config.ts` | Client-safe UI flag fields |
| `frontend/digichat/src/app/api/embed/tenant-config/route.ts` | Project UI flags |
| `frontend/digichat/src/app/embed/page.tsx` | Honor flags; emit ready; accept seed |
| `frontend/digichat/src/lib/embed-seed-messages.ts` | ready/seed validators + caps |
| `frontend/digichat/src/hooks/use-embed-digi-chat.ts` | Expose `seed(messages)` |
| `frontend/digichat/src/lib/security-headers.ts` | Add `www.digithings.ai` to first-party ancestors |
| `frontend/digichat/ARCHITECTURE.md` + `.env.example` | Digithings tenant + first-party + seed protocol |
| `frontend/digithings-web/lib/chatHandoff.ts` | Keep write/read; own `ChatMessage` type |
| `frontend/digithings-web/lib/digichatEmbed.ts` | iframe URL + origin helpers |
| `frontend/digithings-web/lib/digichatSeedBridge.ts` | Parent ready listener + seed post |
| `frontend/digithings-web/components/ChatEmbedShell.tsx` | Full-height iframe + handoff bridge + error UI |
| `frontend/digithings-web/app/chat/page.tsx` | DtNav + `ChatEmbedShell` |
| `frontend/digithings-web/public/_headers` | CSP `frame-src` for digichat origin |
| `frontend/digithings-web/.env.example` | `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` |
| `scripts/build-digithings.sh` | Drop chat Function assert; tolerate empty/no functions |
| **Delete** | `functions/api/chat.ts`, `lib/useStackChat.ts`, `lib/chatStream.ts`, `components/DigiChatSession.tsx`, `components/ProviderSettings.tsx`, `lib/providerSettings.ts`, `functions/api/byok/test.ts`, dead `.dc-settings-*` CSS |

---

### Task 1: First-party host allowlist (no token)

**Files:**
- Create: `frontend/digichat/src/lib/embed-first-party.ts`
- Create: `frontend/digichat/src/lib/embed-first-party.test.ts`
- Modify: `frontend/digichat/src/lib/embed-chat-tenant.ts`
- Modify: `frontend/digichat/src/lib/embed-chat-tenant.test.ts`
- Modify: `frontend/digichat/src/app/api/embed/tenant-config/route.test.ts`

**Interfaces:**
- Consumes: `normalizeEmbedHost`, `resolveEmbedTenantByHost`
- Produces:
  - `FIRST_PARTY_EMBED_HOSTS: ReadonlySet<string>` = `digithings.ai`, `www.digithings.ai`
  - `isFirstPartyEmbedHost(host: string | null | undefined): boolean`
  - `resolveVerifiedEmbedTenant(req)` returns registered tenant when first-party **or** token matches

- [ ] **Step 1: Write the failing test**

Create `frontend/digichat/src/lib/embed-first-party.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { isFirstPartyEmbedHost, FIRST_PARTY_EMBED_HOSTS } from "./embed-first-party";

describe("isFirstPartyEmbedHost", () => {
  it("allows digithings.ai and www only", () => {
    expect(FIRST_PARTY_EMBED_HOSTS.has("digithings.ai")).toBe(true);
    expect(FIRST_PARTY_EMBED_HOSTS.has("www.digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://www.digithings.ai/chat")).toBe(true);
    expect(isFirstPartyEmbedHost("digithings.ai")).toBe(true);
  });

  it("rejects customer and preview hosts", () => {
    expect(isFirstPartyEmbedHost("https://datatapstream.com")).toBe(false);
    expect(isFirstPartyEmbedHost("https://digithings-ai.pages.dev")).toBe(false);
    expect(isFirstPartyEmbedHost(null)).toBe(false);
  });
});
```

Append to `frontend/digichat/src/lib/embed-chat-tenant.test.ts` (keep existing DataTap “no token → 503” cases):

```ts
const DIGITHINGS_REGISTRY = JSON.stringify({
  "digithings.ai": {
    slug: "digithings",
    aliases: ["www.digithings.ai"],
    backend: {
      type: "digivault",
      supabaseUrlEnv: "DIGITHINGS_SUPABASE_URL",
      supabaseAnonKeyEnv: "DIGITHINGS_SUPABASE_ANON_KEY",
      openRouterKeyEnv: "DIGITHINGS_OPENROUTER_API_KEY",
    },
    gateMode: "ungated",
    activityDetail: "full",
    token: "digithings-schema-token",
  },
});

describe("first-party digithings host", () => {
  it("resolves without X-Embed-Token when host is allowlisted and registered", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", DIGITHINGS_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://digithings.ai" }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("digithings");
    expect(result.embedConfig?.gateMode).toBe("ungated");
  });

  it("still requires a token for non-first-party registered hosts", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://datatapstream.com" }),
    );
    expect(result).toBeInstanceOf(Response);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-first-party.test.ts src/lib/embed-chat-tenant.test.ts`
Expected: FAIL — `embed-first-party` module missing / first-party digithings case still 503

- [ ] **Step 3: Implement allowlist + auth branch**

Create `frontend/digichat/src/lib/embed-first-party.ts`:

```ts
import { normalizeEmbedHost } from "@/lib/embed-tenants";

/** Prod marketing hosts only — no *.pages.dev in Phase 3. */
export const FIRST_PARTY_EMBED_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
]);

export function isFirstPartyEmbedHost(host: string | null | undefined): boolean {
  const normalized = normalizeEmbedHost(host);
  return normalized !== null && FIRST_PARTY_EMBED_HOSTS.has(normalized);
}
```

In `embed-chat-tenant.ts`, change `resolveVerifiedEmbedTenant`:

```ts
import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";

export function resolveVerifiedEmbedTenant(req: Request): EmbedTenantConfig | null {
  const registered = resolveEmbedTenantByHost(embedHostOf(req));
  if (!registered) return null;
  if (isFirstPartyEmbedHost(embedHostOf(req))) return registered;
  const token = req.headers.get("x-embed-token")?.trim();
  return token && token === registered.token ? registered : null;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-first-party.test.ts src/lib/embed-chat-tenant.test.ts src/app/api/embed/tenant-config/route.test.ts`
Expected: PASS — DataTap still needs token; digithings first-party succeeds; tenant-config GET returns digithings config without token when host is first-party (add a matching case if route tests only cover token path)

Add to `tenant-config/route.test.ts` if missing:

```ts
it("returns digithings config for first-party host without token", async () => {
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", DIGITHINGS_REGISTRY);
  resetEmbedTenantRegistryForTests();
  const res = await GET(
    new Request("https://chat.example.com/api/embed/tenant-config", {
      headers: { "X-Embed-Host": "https://digithings.ai" },
    }),
  );
  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.slug).toBe("digithings");
  expect(body.gateMode).toBe("ungated");
});
```

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-first-party.ts \
  frontend/digichat/src/lib/embed-first-party.test.ts \
  frontend/digichat/src/lib/embed-chat-tenant.ts \
  frontend/digichat/src/lib/embed-chat-tenant.test.ts \
  frontend/digichat/src/app/api/embed/tenant-config/route.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): allow first-party digithings hosts without embed token

EOF
)"
```

---

### Task 2: Tenant UI flags on EmbedTenantConfig

**Files:**
- Modify: `frontend/digichat/src/lib/embed-tenants.ts`
- Modify: `frontend/digichat/src/lib/embed-tenants.test.ts`

**Interfaces:**
- Consumes: existing `validateEntry` / `EmbedTenantConfig`
- Produces: optional `showByok?: boolean`, `showStatusBar?: boolean`, `layout?: "page" | "embed"` on `EmbedTenantConfig` (defaults applied at read sites, not forced into parsed object when omitted)

- [ ] **Step 1: Write the failing test**

Append to `embed-tenants.test.ts`:

```ts
it("parses showByok, showStatusBar, layout independent of gateMode", () => {
  const reg = parseEmbedTenants(
    JSON.stringify({
      "digithings.ai": {
        slug: "digithings",
        backend: {
          type: "digivault",
          supabaseUrlEnv: "A_URL",
          supabaseAnonKeyEnv: "A_ANON",
          openRouterKeyEnv: "A_OR",
        },
        gateMode: "ungated",
        showByok: true,
        showStatusBar: true,
        layout: "page",
        activityDetail: "full",
        token: "t",
      },
    }),
  );
  const t = reg.get("digithings.ai")!;
  expect(t.gateMode).toBe("ungated");
  expect(t.showByok).toBe(true);
  expect(t.showStatusBar).toBe(true);
  expect(t.layout).toBe("page");
});

it("rejects invalid layout", () => {
  expect(() =>
    parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "ex",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          layout: "fullscreen",
          token: "t",
        },
      }),
    ),
  ).toThrow(/layout/);
});

it("omits UI flags when absent (callers default)", () => {
  const reg = parseEmbedTenants(
    JSON.stringify({
      "example.com": {
        slug: "ex",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        token: "t",
      },
    }),
  );
  const t = reg.get("example.com")!;
  expect(t.showByok).toBeUndefined();
  expect(t.showStatusBar).toBeUndefined();
  expect(t.layout).toBeUndefined();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts`
Expected: FAIL — properties not on type / not parsed

- [ ] **Step 3: Extend type + validateEntry**

In `embed-tenants.ts` add to `EmbedTenantConfig`:

```ts
  /** When true, embed shows BYOK/settings. Independent of gateMode. */
  showByok?: boolean;
  /** When true, embed shows digichat-ui status bar. Independent of gateMode. */
  showStatusBar?: boolean;
  /** page = full content chrome inside iframe; embed = compact iframe child. */
  layout?: "page" | "embed";
```

In `validateEntry`, before the return:

```ts
  if (v.showByok !== undefined && typeof v.showByok !== "boolean") {
    throw new Error(`${ctx}: showByok must be a boolean`);
  }
  if (v.showStatusBar !== undefined && typeof v.showStatusBar !== "boolean") {
    throw new Error(`${ctx}: showStatusBar must be a boolean`);
  }
  if (v.layout !== undefined && v.layout !== "page" && v.layout !== "embed") {
    throw new Error(`${ctx}: layout must be "page" or "embed"`);
  }
```

Include on the returned object:

```ts
    showByok: typeof v.showByok === "boolean" ? v.showByok : undefined,
    showStatusBar: typeof v.showStatusBar === "boolean" ? v.showStatusBar : undefined,
    layout: v.layout === "page" || v.layout === "embed" ? v.layout : undefined,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-tenants.ts frontend/digichat/src/lib/embed-tenants.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): parse independent embed UI flags from tenant config

EOF
)"
```

---

### Task 3: Project UI flags to client config API

**Files:**
- Modify: `frontend/digichat/src/hooks/use-embed-tenant-config.ts`
- Modify: `frontend/digichat/src/app/api/embed/tenant-config/route.ts`
- Modify: `frontend/digichat/src/app/api/embed/tenant-config/route.test.ts`

**Interfaces:**
- Consumes: `EmbedTenantConfig.showByok` / `showStatusBar` / `layout`
- Produces: same optional fields on `EmbedTenantClientConfig`; defaults in `DEFAULT_EMBED_TENANT_CONFIG`: `showByok: false`, `showStatusBar: false`, `layout: "embed"`

- [ ] **Step 1: Write the failing test**

```ts
it("projects showByok, showStatusBar, layout to the client body", async () => {
  vi.stubEnv(
    "DIGICHAT_EMBED_TENANTS",
    JSON.stringify({
      "digithings.ai": {
        slug: "digithings",
        backend: {
          type: "digivault",
          supabaseUrlEnv: "A_URL",
          supabaseAnonKeyEnv: "A_ANON",
          openRouterKeyEnv: "A_OR",
        },
        gateMode: "ungated",
        showByok: true,
        showStatusBar: true,
        layout: "page",
        activityDetail: "full",
        token: "t",
      },
    }),
  );
  resetEmbedTenantRegistryForTests();
  const res = await GET(
    new Request("https://chat.example.com/api/embed/tenant-config", {
      headers: { "X-Embed-Host": "https://digithings.ai" },
    }),
  );
  const body = await res.json();
  expect(body.showByok).toBe(true);
  expect(body.showStatusBar).toBe(true);
  expect(body.layout).toBe("page");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/app/api/embed/tenant-config/route.test.ts`
Expected: FAIL — fields undefined

- [ ] **Step 3: Project fields**

Update `EmbedTenantClientConfig`:

```ts
export type EmbedTenantClientConfig = {
  slug: string;
  gateMode: "turn_limited" | "ungated" | "trial_form";
  theme: "dark" | "light";
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
  title?: string;
  welcome?: string;
  suggestions?: string[];
  placeholder?: string;
  lockedContact?: string;
  showByok?: boolean;
  showStatusBar?: boolean;
  layout?: "page" | "embed";
};

export const DEFAULT_EMBED_TENANT_CONFIG: EmbedTenantClientConfig = {
  slug: "embed",
  gateMode: "turn_limited",
  theme: "dark",
  accent: null,
  attribution: false,
  showByok: false,
  showStatusBar: false,
  layout: "embed",
};
```

In `route.ts` body when `cfg` is present, add:

```ts
        showByok: cfg.showByok ?? false,
        showStatusBar: cfg.showStatusBar ?? false,
        layout: cfg.layout ?? "embed",
```

And on the gated fallback body, include the same defaults (`false` / `false` / `"embed"`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/app/api/embed/tenant-config/route.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/hooks/use-embed-tenant-config.ts \
  frontend/digichat/src/app/api/embed/tenant-config/route.ts \
  frontend/digichat/src/app/api/embed/tenant-config/route.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): project embed UI flags through tenant-config API

EOF
)"
```

---

### Task 4: Honor UI flags on embed page

**Files:**
- Modify: `frontend/digichat/src/app/embed/page.tsx`
- Create: `frontend/digichat/src/lib/embed-ui-flags.ts`
- Create: `frontend/digichat/src/lib/embed-ui-flags.test.ts`

**Interfaces:**
- Consumes: `EmbedTenantClientConfig`
- Produces: `resolveEmbedUiFlags(cfg) → { showByok: boolean; showStatusBar: boolean; layout: "page" | "embed" }` — never uses `gateMode`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest";
import { resolveEmbedUiFlags } from "./embed-ui-flags";

describe("resolveEmbedUiFlags", () => {
  it("keeps showByok true under ungated", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "digithings",
        gateMode: "ungated",
        theme: "dark",
        accent: null,
        attribution: false,
        showByok: true,
        showStatusBar: true,
        layout: "page",
      }),
    ).toEqual({ showByok: true, showStatusBar: true, layout: "page" });
  });

  it("does not derive showByok from gateMode", () => {
    expect(
      resolveEmbedUiFlags({
        slug: "x",
        gateMode: "turn_limited",
        theme: "dark",
        accent: null,
        attribution: false,
      }),
    ).toEqual({ showByok: false, showStatusBar: false, layout: "embed" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-ui-flags.test.ts`
Expected: FAIL — module missing

- [ ] **Step 3: Implement helper and wire page**

```ts
import type { EmbedTenantClientConfig } from "@/hooks/use-embed-tenant-config";

export function resolveEmbedUiFlags(cfg: EmbedTenantClientConfig): {
  showByok: boolean;
  showStatusBar: boolean;
  layout: "page" | "embed";
} {
  return {
    showByok: cfg.showByok === true,
    showStatusBar: cfg.showStatusBar === true,
    layout: cfg.layout === "page" ? "page" : "embed",
  };
}
```

In `embed/page.tsx` replace:

```ts
  const showByok = !ungated && !isTrialForm;
```

and the hardcoded DigiChatSession props with:

```ts
  const uiFlags = resolveEmbedUiFlags(tenantCfg);
  // trial_form still hides BYOK until parent unlock — product rule for DataTap only
  const showByok = isTrialForm ? false : uiFlags.showByok;
```

```tsx
      showByok={showByok}
      showStatusBar={uiFlags.showStatusBar}
      layout={uiFlags.layout}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-ui-flags.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-ui-flags.ts \
  frontend/digichat/src/lib/embed-ui-flags.test.ts \
  frontend/digichat/src/app/embed/page.tsx
git commit -m "$(cat <<'EOF'
feat(digichat): drive embed BYOK/status/layout from tenant flags

EOF
)"
```

---

### Task 5: digichat:ready / digichat:seed validators

**Files:**
- Create: `frontend/digichat/src/lib/embed-seed-messages.ts`
- Create: `frontend/digichat/src/lib/embed-seed-messages.test.ts`

**Interfaces:**
- Consumes: first-party parent origins via hostname allowlist
- Produces:
  - `READY_MESSAGE = { type: "digichat:ready" }`
  - `SEED_MESSAGE_TYPE = "digichat:seed"`
  - `READY_TIMEOUT_MS = 8000`
  - `MAX_SEED_MESSAGES = 40`, `MAX_SEED_CONTENT_CHARS = 8000`, `MAX_SEED_PENDING_CHARS = 4000`, `MAX_SEED_AGE_MS = 300_000`
  - `SeedMessage = { type; messages: { role; content }[]; pending: string; ts: number }`
  - `parseSeedMessage(event, allowedParentOrigins: ReadonlySet<string>): SeedMessage | null`
  - `isAllowedSeedParentOrigin(origin: string): boolean` — hostname ∈ first-party set

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from "vitest";
import {
  READY_MESSAGE,
  parseSeedMessage,
  isAllowedSeedParentOrigin,
  MAX_SEED_MESSAGES,
} from "./embed-seed-messages";

describe("embed-seed-messages", () => {
  it("exports digichat:ready", () => {
    expect(READY_MESSAGE.type).toBe("digichat:ready");
  });

  it("accepts a well-formed seed from digithings.ai", () => {
    const event = {
      origin: "https://digithings.ai",
      data: {
        type: "digichat:seed",
        messages: [{ role: "user", content: "hi" }],
        pending: "follow up?",
        ts: Date.now(),
      },
    } as MessageEvent;
    const parsed = parseSeedMessage(event, new Set(["https://digithings.ai"]));
    expect(parsed?.pending).toBe("follow up?");
    expect(parsed?.messages).toHaveLength(1);
  });

  it("ignores wrong origin", () => {
    const event = {
      origin: "https://evil.example",
      data: {
        type: "digichat:seed",
        messages: [],
        pending: "x",
        ts: Date.now(),
      },
    } as MessageEvent;
    expect(parseSeedMessage(event, new Set(["https://digithings.ai"]))).toBeNull();
  });

  it("drops over-cap message lists", () => {
    const messages = Array.from({ length: MAX_SEED_MESSAGES + 1 }, () => ({
      role: "user" as const,
      content: "x",
    }));
    const event = {
      origin: "https://digithings.ai",
      data: { type: "digichat:seed", messages, pending: "", ts: Date.now() },
    } as MessageEvent;
    expect(parseSeedMessage(event, new Set(["https://digithings.ai"]))).toBeNull();
  });

  it("recognizes first-party parent origins", () => {
    expect(isAllowedSeedParentOrigin("https://digithings.ai")).toBe(true);
    expect(isAllowedSeedParentOrigin("https://www.digithings.ai")).toBe(true);
    expect(isAllowedSeedParentOrigin("https://datatapstream.com")).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-seed-messages.test.ts`
Expected: FAIL — module missing

- [ ] **Step 3: Implement module**

```ts
import { isFirstPartyEmbedHost } from "@/lib/embed-first-party";

export const READY_MESSAGE = { type: "digichat:ready" } as const;
export const SEED_MESSAGE_TYPE = "digichat:seed" as const;
export const READY_TIMEOUT_MS = 8000;
export const MAX_SEED_MESSAGES = 40;
export const MAX_SEED_CONTENT_CHARS = 8000;
export const MAX_SEED_PENDING_CHARS = 4000;
export const MAX_SEED_AGE_MS = 5 * 60 * 1000;

export type SeedChatMessage = { role: "user" | "assistant"; content: string };

export type SeedMessage = {
  type: typeof SEED_MESSAGE_TYPE;
  messages: SeedChatMessage[];
  pending: string;
  ts: number;
};

export function isAllowedSeedParentOrigin(origin: string): boolean {
  return isFirstPartyEmbedHost(origin);
}

export function parseSeedMessage(
  event: MessageEvent,
  allowedParentOrigins: ReadonlySet<string>,
): SeedMessage | null {
  if (!allowedParentOrigins.has(event.origin)) return null;
  const data = event.data as Record<string, unknown> | null;
  if (!data || data.type !== SEED_MESSAGE_TYPE) return null;
  if (typeof data.ts !== "number" || Date.now() - data.ts > MAX_SEED_AGE_MS) return null;
  if (typeof data.pending !== "string") return null;
  if (data.pending.length > MAX_SEED_PENDING_CHARS) return null;
  if (!Array.isArray(data.messages) || data.messages.length > MAX_SEED_MESSAGES) return null;
  const messages: SeedChatMessage[] = [];
  for (const raw of data.messages) {
    if (!raw || typeof raw !== "object") return null;
    const m = raw as Record<string, unknown>;
    if (m.role !== "user" && m.role !== "assistant") return null;
    if (typeof m.content !== "string") return null;
    if (m.content.length > MAX_SEED_CONTENT_CHARS) return null;
    messages.push({ role: m.role, content: m.content });
  }
  return {
    type: SEED_MESSAGE_TYPE,
    messages,
    pending: data.pending,
    ts: data.ts,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-seed-messages.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-seed-messages.ts \
  frontend/digichat/src/lib/embed-seed-messages.test.ts
git commit -m "$(cat <<'EOF'
feat(digichat): add digichat ready/seed postMessage validators

EOF
)"
```

---

### Task 6: Emit ready, accept seed, apply to controller

**Files:**
- Modify: `frontend/digichat/src/hooks/use-embed-digi-chat.ts`
- Create: `frontend/digichat/src/hooks/use-embed-digi-chat.seed.test.ts` (unit the mapper + seed helper if hook is hard to mount; prefer extracting `toUiMessages` + documenting seed call)
- Modify: `frontend/digichat/src/app/embed/page.tsx`

**Interfaces:**
- Consumes: `parseSeedMessage`, `READY_MESSAGE`, `SeedChatMessage`
- Produces: `useEmbedDigiChat` returns `seed: (messages: DigiChatMessage[]) => void` via AI SDK `setMessages`; embed applies seed once then `send(pending)` when non-empty; sets intro off when seeded

- [ ] **Step 1: Write the failing test**

Create a pure helper test file `frontend/digichat/src/lib/embed-seed-apply.ts` + test (keep React out of the unit):

```ts
// embed-seed-apply.test.ts
import { describe, it, expect, vi } from "vitest";
import { applyEmbedSeed } from "./embed-seed-apply";

describe("applyEmbedSeed", () => {
  it("seeds transcript and auto-sends pending", () => {
    const seed = vi.fn();
    const send = vi.fn();
    applyEmbedSeed(
      {
        messages: [{ role: "user", content: "a" }, { role: "assistant", content: "b" }],
        pending: "c",
      },
      { seed, send },
    );
    expect(seed).toHaveBeenCalledWith([
      { role: "user", content: "a" },
      { role: "assistant", content: "b" },
    ]);
    expect(send).toHaveBeenCalledWith("c");
  });

  it("seeds without send when pending empty", () => {
    const seed = vi.fn();
    const send = vi.fn();
    applyEmbedSeed({ messages: [], pending: "  " }, { seed, send });
    expect(seed).toHaveBeenCalledWith([]);
    expect(send).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-seed-apply.test.ts`
Expected: FAIL — module missing

- [ ] **Step 3: Implement apply helper + seed on hook + page effects**

`embed-seed-apply.ts`:

```ts
export type SeedApplyInput = {
  messages: ReadonlyArray<{ role: "user" | "assistant"; content: string }>;
  pending: string;
};

export function applyEmbedSeed(
  input: SeedApplyInput,
  ctrl: {
    seed: (messages: SeedApplyInput["messages"]) => void;
    send: (q: string) => void;
  },
): void {
  ctrl.seed(input.messages);
  const pending = input.pending.trim();
  if (pending) ctrl.send(pending);
}
```

In `use-embed-digi-chat.ts`, expose `setMessages` from `useChat` and:

```ts
  const seed = useCallback(
    (msgs: DigiChatMessage[]) => {
      setMessages(
        msgs.map((m) => ({
          id: crypto.randomUUID(),
          role: m.role,
          parts: [{ type: "text" as const, text: m.content }],
        })),
      );
    },
    [setMessages],
  );

  return { messages: digiMessages, busy, error: chatError, send, onRetry: () => regenerate(), seed };
```

In `embed/page.tsx` (EmbedSession body), after chat hook is created:

```ts
  const [seedApplied, setSeedApplied] = useState(false);
  const [hideIntroForSeed, setHideIntroForSeed] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !host) return;
    const parentOrigin = host.includes("://") ? new URL(host).origin : `https://${host}`;
    window.parent.postMessage(READY_MESSAGE, parentOrigin);
  }, [host]);

  useEffect(() => {
    if (typeof window === "undefined" || seedApplied) return;
    const allowed = new Set<string>();
    if (host) {
      try {
        allowed.add(host.includes("://") ? new URL(host).origin : `https://${host}`);
      } catch {
        /* ignore */
      }
    }
    // Also accept canonical first-party origins when host is digithings
    for (const h of ["https://digithings.ai", "https://www.digithings.ai"]) {
      if (isAllowedSeedParentOrigin(h)) allowed.add(h);
    }

    const onMessage = (event: MessageEvent) => {
      const parsed = parseSeedMessage(event, allowed);
      if (!parsed) return;
      applyEmbedSeed(
        { messages: parsed.messages, pending: parsed.pending },
        { seed: chat.seed, send: chat.send },
      );
      setSeedApplied(true);
      setHideIntroForSeed(true);
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [host, seedApplied, chat.seed, chat.send]);
```

Pass `showIntro={!gate.locked && !trialLocked && !hideIntroForSeed}`.

Keep DataTap gated/unlocked effects unchanged.

- [ ] **Step 4: Run tests**

Run: `cd frontend/digichat && npx vitest run src/lib/embed-seed-apply.test.ts src/lib/embed-seed-messages.test.ts`
Expected: PASS. Also run a quick typecheck: `cd frontend/digichat && npx tsc --noEmit` (or project’s existing check) if `seed` typing breaks DigiChatController — extend local controller type only if needed; digichat-ui `DigiChatController` does not require `seed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-seed-apply.ts \
  frontend/digichat/src/lib/embed-seed-apply.test.ts \
  frontend/digichat/src/hooks/use-embed-digi-chat.ts \
  frontend/digichat/src/app/embed/page.tsx
git commit -m "$(cat <<'EOF'
feat(digichat): wire ready/seed protocol into embed session

EOF
)"
```

---

### Task 7: Digithings digivault tenant docs + GHCR install shape

**Files:**
- Modify: `frontend/digichat/ARCHITECTURE.md` (embed tenants + Phase 3 section)
- Modify: `frontend/digichat/.env.example` (document digithings env names + first-party)
- Create: `docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md`

**Interfaces:**
- Consumes: Phase 2 digivault `*Env` shape
- Produces: documented `DIGICHAT_EMBED_TENANTS` digithings entry + ops checklist (hostname, GHCR tag, ACR mirror, env vars)

- [ ] **Step 1: Write the checklist content (no test — docs task folded here)**

Create `docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md` with:

```markdown
# DigiChat Phase 3 — digithings ops checklist

## Hostname
- Public digichat origin: `https://chat.digithings.ai`
- DNS: CNAME `chat` → digithings-owned Azure Container App (or equivalent) hostname
- digithings.ai `/chat` stays on Cloudflare Pages (shell + iframe)

## Image
- Pull same DigiChat GHCR release DataTap uses: `ghcr.io/digithings-ai/digichat:<tag>`
- If this install pulls via ACR: after each digichat release run manual `az acr import` (not automated in Phase 3)

## Runtime env (names must match tenant JSON)
- `DIGITHINGS_SUPABASE_URL`, `DIGITHINGS_SUPABASE_ANON_KEY`, `DIGITHINGS_OPENROUTER_API_KEY` (or chosen names)
- `DIGICHAT_EMBED_TENANTS` includes digithings entry below
- `DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,...` at **build** for CSP
- Do **not** put tenant `token` values in Docker build-args

## Tenant JSON fragment
\`\`\`json
{
  "digithings.ai": {
    "slug": "digithings",
    "aliases": ["www.digithings.ai"],
    "gateMode": "ungated",
    "showByok": true,
    "showStatusBar": true,
    "layout": "page",
    "activityDetail": "full",
    "attribution": false,
    "token": "<schema-required; unused for first-party requests>",
    "backend": {
      "type": "digivault",
      "supabaseUrlEnv": "DIGITHINGS_SUPABASE_URL",
      "supabaseAnonKeyEnv": "DIGITHINGS_SUPABASE_ANON_KEY",
      "openRouterKeyEnv": "DIGITHINGS_OPENROUTER_API_KEY"
    }
  }
}
\`\`\`

## digithings-web build
- `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://chat.digithings.ai`
```

Update ARCHITECTURE.md embed section: first-party allowlist, UI flags, ready/seed, Phase 3 deletes CF path on digithings-web.

- [ ] **Step 2: Sanity — no secrets in docs**

Grep the new files for `dgk_`, `sk-`, raw supabase keys. Expected: none.

- [ ] **Step 3: Commit**

```bash
git add frontend/digichat/ARCHITECTURE.md frontend/digichat/.env.example \
  docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md
git commit -m "$(cat <<'EOF'
docs(digichat): Phase 3 digithings tenant + GHCR install checklist

EOF
)"
```

---

### Task 8: digithings-web — vitest + handoff type + embed URL helper

**Files:**
- Modify: `frontend/digithings-web/package.json` (add `vitest`, `"test": "vitest run"`)
- Create: `frontend/digithings-web/vitest.config.ts`
- Modify: `frontend/digithings-web/lib/chatHandoff.ts`
- Create: `frontend/digithings-web/lib/chatHandoff.test.ts`
- Create: `frontend/digithings-web/lib/digichatEmbed.ts`
- Create: `frontend/digithings-web/lib/digichatEmbed.test.ts`
- Create: `frontend/digithings-web/.env.example`

**Interfaces:**
- Consumes: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`
- Produces:
  - `ChatMessage = { role: "user" | "assistant"; content: string }` in `chatHandoff.ts` (no import from deleted `useStackChat`)
  - `getDigichatEmbedOrigin(): string`
  - `buildDigichatEmbedSrc(opts?: { parentOrigin?: string }): string` → `{origin}/embed?host={parentOrigin}` **without** `token`

- [ ] **Step 1: Add vitest + write failing tests**

`vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: { environment: "node" },
  resolve: {
    alias: { "@": path.resolve(__dirname, ".") },
  },
});
```

`digichatEmbed.test.ts`:

```ts
import { describe, it, expect, afterEach, vi } from "vitest";
import { buildDigichatEmbedSrc, getDigichatEmbedOrigin } from "./digichatEmbed";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("digichatEmbed", () => {
  it("builds /embed URL with host and without token", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://chat.digithings.ai");
    const src = buildDigichatEmbedSrc({ parentOrigin: "https://digithings.ai" });
    expect(src).toBe("https://chat.digithings.ai/embed?host=https%3A%2F%2Fdigithings.ai");
    expect(src).not.toMatch(/token=/);
  });

  it("reads origin from env", () => {
    vi.stubEnv("NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN", "https://chat.digithings.ai");
    expect(getDigichatEmbedOrigin()).toBe("https://chat.digithings.ai");
  });
});
```

`chatHandoff.test.ts` — exercise `writeHandoff` / `readAndClearHandoff` with a minimal `localStorage` mock (or skip storage and only type-level if jsdom not available — prefer `happy-dom` / `jsdom` as vitest environment for this file via `// @vitest-environment happy-dom` comment at top).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend/digithings-web && npm install -D vitest && npx vitest run lib/digichatEmbed.test.ts`
Expected: FAIL — module missing

- [ ] **Step 3: Implement**

`digichatEmbed.ts`:

```ts
const DEFAULT_ORIGIN = "https://chat.digithings.ai";

export function getDigichatEmbedOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN?.trim();
  if (!raw) return DEFAULT_ORIGIN;
  return raw.replace(/\/$/, "");
}

export function buildDigichatEmbedSrc(opts?: { parentOrigin?: string }): string {
  const origin = getDigichatEmbedOrigin();
  const parent = opts?.parentOrigin ?? "https://digithings.ai";
  const url = new URL("/embed", origin);
  url.searchParams.set("host", parent);
  return url.toString();
}
```

In `chatHandoff.ts` replace the `useStackChat` import with:

```ts
export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};
```

`.env.example`:

```
# Digichat iframe origin (no trailing slash). Prod: https://chat.digithings.ai
NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://chat.digithings.ai
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend/digithings-web && npx vitest run lib/`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digithings-web/package.json frontend/digithings-web/package-lock.json \
  frontend/digithings-web/vitest.config.ts \
  frontend/digithings-web/lib/chatHandoff.ts \
  frontend/digithings-web/lib/chatHandoff.test.ts \
  frontend/digithings-web/lib/digichatEmbed.ts \
  frontend/digithings-web/lib/digichatEmbed.test.ts \
  frontend/digithings-web/.env.example
git commit -m "$(cat <<'EOF'
feat(website): add digichat embed URL helper and handoff self-types

EOF
)"
```

---

### Task 9: digithings-web seed bridge + ChatEmbedShell

**Files:**
- Create: `frontend/digithings-web/lib/digichatSeedBridge.ts`
- Create: `frontend/digithings-web/lib/digichatSeedBridge.test.ts`
- Create: `frontend/digithings-web/components/ChatEmbedShell.tsx`
- Modify: `frontend/digithings-web/app/chat/page.tsx`

**Interfaces:**
- Consumes: `readAndClearHandoff`, `getDigichatEmbedOrigin`, `buildDigichatEmbedSrc`, `READY_TIMEOUT_MS` (duplicate constant `8000` locally to avoid cross-package import)
- Produces:
  - `createSeedPayload(handoff) → { type: "digichat:seed"; messages; pending; ts }`
  - `shouldAcceptReady(event, digichatOrigin): boolean`
  - `ChatEmbedShell` client component: iframe + listener + timeout error UI

- [ ] **Step 1: Write the failing bridge tests**

```ts
import { describe, it, expect } from "vitest";
import { createSeedPayload, shouldAcceptReady } from "./digichatSeedBridge";

describe("digichatSeedBridge", () => {
  it("builds digichat:seed from handoff", () => {
    const p = createSeedPayload({
      messages: [{ role: "user", content: "q" }],
      pending: "more",
      ts: 123,
    });
    expect(p).toEqual({
      type: "digichat:seed",
      messages: [{ role: "user", content: "q" }],
      pending: "more",
      ts: 123,
    });
  });

  it("accepts ready only from digichat origin", () => {
    expect(
      shouldAcceptReady(
        { origin: "https://chat.digithings.ai", data: { type: "digichat:ready" } } as MessageEvent,
        "https://chat.digithings.ai",
      ),
    ).toBe(true);
    expect(
      shouldAcceptReady(
        { origin: "https://evil.example", data: { type: "digichat:ready" } } as MessageEvent,
        "https://chat.digithings.ai",
      ),
    ).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digithings-web && npx vitest run lib/digichatSeedBridge.test.ts`
Expected: FAIL

- [ ] **Step 3: Implement bridge + shell**

`digichatSeedBridge.ts`:

```ts
import type { ChatHandoff } from "./chatHandoff";

export const READY_TIMEOUT_MS = 8000;
export const CHAT_LOAD_ERROR_COPY =
  "Chat is taking too long to load. Refresh to try again.";

export function createSeedPayload(handoff: ChatHandoff) {
  return {
    type: "digichat:seed" as const,
    messages: handoff.messages.map((m) => ({ role: m.role, content: m.content })),
    pending: handoff.pending,
    ts: handoff.ts,
  };
}

export function shouldAcceptReady(event: MessageEvent, digichatOrigin: string): boolean {
  if (event.origin !== digichatOrigin) return false;
  const data = event.data as { type?: unknown } | null;
  return !!data && data.type === "digichat:ready";
}
```

`ChatEmbedShell.tsx` (`"use client"`):

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { readAndClearHandoff } from "@/lib/chatHandoff";
import { buildDigichatEmbedSrc, getDigichatEmbedOrigin } from "@/lib/digichatEmbed";
import {
  CHAT_LOAD_ERROR_COPY,
  createSeedPayload,
  READY_TIMEOUT_MS,
  shouldAcceptReady,
} from "@/lib/digichatSeedBridge";

export function ChatEmbedShell() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const handoffRef = useRef(readAndClearHandoff());
  const readySeen = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const digichatOrigin = getDigichatEmbedOrigin();
  const src = buildDigichatEmbedSrc({ parentOrigin: "https://digithings.ai" });

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!shouldAcceptReady(event, digichatOrigin)) return;
      readySeen.current = true;
      setError(null);
      const win = iframeRef.current?.contentWindow;
      if (!win) return;
      const handoff = handoffRef.current;
      handoffRef.current = null;
      if (handoff) {
        win.postMessage(createSeedPayload(handoff), digichatOrigin);
      }
    };
    window.addEventListener("message", onMessage);
    const t = window.setTimeout(() => {
      if (!readySeen.current) setError(CHAT_LOAD_ERROR_COPY);
    }, READY_TIMEOUT_MS);
    return () => {
      window.removeEventListener("message", onMessage);
      window.clearTimeout(t);
    };
  }, [digichatOrigin]);

  return (
    <main
      className="dc-page"
      style={{ display: "flex", flexDirection: "column", minHeight: "calc(100vh - 4rem)" }}
    >
      {error ? (
        <p role="alert" style={{ padding: "1.5rem" }}>
          {error}{" "}
          <button type="button" onClick={() => window.location.reload()}>
            Refresh
          </button>
        </p>
      ) : null}
      <iframe
        ref={iframeRef}
        title="digichat"
        src={src}
        style={{ flex: 1, width: "100%", border: 0, minHeight: "70vh" }}
        onError={() => setError(CHAT_LOAD_ERROR_COPY)}
      />
    </main>
  );
}
```

`app/chat/page.tsx`:

```tsx
import type { Metadata } from "next";
import { DtNav } from "@/components/DtNav";
import { ChatEmbedShell } from "@/components/ChatEmbedShell";

export const metadata: Metadata = {
  title: "digichat — the digithings assistant",
  description:
    "Ask digichat anything about the digithings architecture — grounded in the digivault docs, " +
    "running on a free model pool. No sign-up.",
};

export default function ChatPage() {
  return (
    <>
      <DtNav />
      <ChatEmbedShell />
    </>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend/digithings-web && npx vitest run lib/`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digithings-web/lib/digichatSeedBridge.ts \
  frontend/digithings-web/lib/digichatSeedBridge.test.ts \
  frontend/digithings-web/components/ChatEmbedShell.tsx \
  frontend/digithings-web/app/chat/page.tsx
git commit -m "$(cat <<'EOF'
feat(website): iframe digichat shell with postMessage handoff seed

EOF
)"
```

---

### Task 10: digithings-web CSP `frame-src`

**Files:**
- Modify: `frontend/digithings-web/public/_headers`
- Create: `frontend/digithings-web/public/_headers` comment + CSP line (no vitest for static headers — add a tiny node assert in `lib/cspFrameSrc.test.ts` that documents the expected origin string used in `_headers`, OR a shell check in Step 2)

**Interfaces:**
- Consumes: `https://chat.digithings.ai` (must match `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` prod value)
- Produces: `Content-Security-Policy` including `frame-src 'self' https://chat.digithings.ai`

- [ ] **Step 1: Write a grep/assert test**

Create `frontend/digithings-web/lib/cspHeaders.contract.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

describe("_headers CSP", () => {
  it("allows digichat origin in frame-src", () => {
    const text = readFileSync(resolve(__dirname, "../public/_headers"), "utf8");
    expect(text).toMatch(/Content-Security-Policy:/);
    expect(text).toMatch(/frame-src[^;]*https:\/\/chat\.digithings\.ai/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digithings-web && npx vitest run lib/cspHeaders.contract.test.ts`
Expected: FAIL

- [ ] **Step 3: Update `_headers`**

```
# Cloudflare Pages headers for digithings.ai. Fonts are self-hosted (next/font).
# frame-src allows the digichat iframe at chat.digithings.ai (Phase 3).
# X-Frame-Options: DENY still blocks digithings.ai itself from being framed.
/*
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self'; frame-src 'self' https://chat.digithings.ai; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'
```

Keep CSP minimal; adjust `script-src` / `style-src` if the existing site already needs more (match current Pages behavior — if build/smoke shows CSP violations, widen only what the static export already uses). Prefer starting from the lines above and verifying `npm run build` + manual load.

Also add `https://www.digithings.ai` to digichat `FIRST_PARTY_FRAME_ANCESTORS` in Task 11 if not done yet.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend/digithings-web && npx vitest run lib/cspHeaders.contract.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/digithings-web/public/_headers \
  frontend/digithings-web/lib/cspHeaders.contract.test.ts
git commit -m "$(cat <<'EOF'
fix(website): allow digichat origin in frame-src CSP

EOF
)"
```

---

### Task 11: Digichat `www` frame-ancestors + delete native digithings chat stack

**Files:**
- Modify: `frontend/digichat/src/lib/security-headers.ts`
- Modify: `frontend/digichat/src/lib/security-headers.test.ts`
- Delete: `frontend/digithings-web/functions/api/chat.ts`
- Delete: `frontend/digithings-web/functions/api/byok/test.ts`
- Delete: `frontend/digithings-web/lib/useStackChat.ts`
- Delete: `frontend/digithings-web/lib/chatStream.ts`
- Delete: `frontend/digithings-web/components/DigiChatSession.tsx`
- Delete: `frontend/digithings-web/components/ProviderSettings.tsx`
- Delete: `frontend/digithings-web/lib/providerSettings.ts`
- Modify: `frontend/digithings-web/app/globals.css` (remove `.dc-settings-*` block)
- Modify: `scripts/build-digithings.sh`
- Modify: `frontend/digithings-web/.dev.vars.example` (note secrets move to digichat runtime; optional delete of CF-only keys)

**Interfaces:**
- Consumes: none from deleted modules
- Produces: build script that does not require `functions/api/chat.ts`; if `functions/` is empty after deletes, skip mirror or mirror only remaining files

- [ ] **Step 1: Write failing security-headers test + deletion smoke**

```ts
it("includes www.digithings.ai in first-party frame-ancestors", () => {
  const list = embedFrameAncestors();
  expect(list).toContain("https://www.digithings.ai");
  expect(list).toContain("https://digithings.ai");
});
```

Also add a build-script contract test or Step 4 shell check that `functions/api/chat.ts` is gone.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend/digichat && npx vitest run src/lib/security-headers.test.ts`
Expected: FAIL — www missing

- [ ] **Step 3: Implement deletes + headers + build script**

`security-headers.ts`:

```ts
const FIRST_PARTY_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://www.digithings.ai",
  "https://digiquant.io",
] as const;
```

Replace the chat Function assert in `scripts/build-digithings.sh`:

```bash
echo "--- mirroring Pages Functions to repo root (if any) ---"
rm -rf functions
if [ -d frontend/digithings-web/functions ] && [ -n "$(find frontend/digithings-web/functions -type f 2>/dev/null | head -1)" ]; then
  cp -r frontend/digithings-web/functions functions
else
  echo "No Pages Functions to mirror (Phase 3: /api/chat retired)."
fi
# Must NOT reintroduce the retired chat Function
if [ -f functions/api/chat.ts ]; then
  echo "ERROR: functions/api/chat.ts must stay deleted (Phase 3)" >&2
  exit 1
fi
```

Delete the listed files. Remove `.dc-settings-*` from `globals.css`. Confirm `ModuleManifest.tsx` still imports `writeHandoff` only.

- [ ] **Step 4: Verify**

```bash
cd frontend/digichat && npx vitest run src/lib/security-headers.test.ts
test ! -f frontend/digithings-web/functions/api/chat.ts
test ! -f frontend/digithings-web/lib/useStackChat.ts
test ! -f frontend/digithings-web/lib/chatStream.ts
rg -n "useStackChat|chatStream|functions/api/chat" frontend/digithings-web scripts/build-digithings.sh && exit 1 || true
cd frontend/digithings-web && npx vitest run lib/ && npm run build
```

Expected: PASS; static export succeeds; no dead imports.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/digichat/src/lib/security-headers.ts \
  frontend/digichat/src/lib/security-headers.test.ts \
  frontend/digithings-web scripts/build-digithings.sh
git commit -m "$(cat <<'EOF'
feat(website): retire CF chat Function and native useStackChat stack

EOF
)"
```

---

### Task 12: Final regression suites + ARCHITECTURE cross-links

**Files:**
- Modify: `frontend/digichat/ARCHITECTURE.md` (confirm Phase 3 section complete)
- Modify: `frontend/digithings-web` README or comment on chat page if one exists
- Touch: `docs/DEPLOYMENT.md` only if it still claims ADR-0018 path-routing *is* DigiChat — add a short note that Phase 3 keeps `/chat` as Pages shell + iframe to `chat.digithings.ai` (do not rewrite the whole ADR in this PR; one clarifying paragraph is enough)

**Interfaces:** none new

- [ ] **Step 1: Run digichat regression**

```bash
cd frontend/digichat && npx vitest run \
  src/lib/embed-first-party.test.ts \
  src/lib/embed-chat-tenant.test.ts \
  src/lib/embed-tenants.test.ts \
  src/lib/embed-ui-flags.test.ts \
  src/lib/embed-seed-messages.test.ts \
  src/lib/embed-seed-apply.test.ts \
  src/lib/security-headers.test.ts \
  src/lib/embed-trial-messages.test.ts \
  src/app/api/embed/tenant-config/route.test.ts \
  src/app/api/chat/route.test.ts
```

Expected: PASS — DataTap token + trial messages unchanged; digivault route still green

- [ ] **Step 2: Run digithings-web**

```bash
cd frontend/digithings-web && npx vitest run lib/ && npm run lint && npm run build
```

Expected: PASS

- [ ] **Step 3: Manual smoke checklist (record in PR body)**

- [ ] Landing ModuleManifest ask → `/chat` iframe loads → seeded pending sends
- [ ] BYOK visible with ungated digithings tenant
- [ ] Status bar visible; layout page fills under DtNav
- [ ] Mermaid in assistant markdown still renders (existing digichat-ui)
- [ ] `POST https://digithings.ai/api/chat` → 404 / no Function
- [ ] DataTap embed still requires token (staging or unit coverage already)

- [ ] **Step 4: Commit docs clarifications if any**

```bash
git add frontend/digichat/ARCHITECTURE.md docs/DEPLOYMENT.md
git commit -m "$(cat <<'EOF'
docs: note Phase 3 /chat iframe cutover vs path-routing ADR

EOF
)"
```

---

## Self-review (plan vs design)

| Design requirement | Task(s) |
|---|---|
| iframe architecture; DtNav outside | Task 9 |
| digithings-owned digichat; hostname decided | Global Constraints + Task 7 (`chat.digithings.ai`, `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`) |
| One PR cutover + delete CF / useStackChat / chatStream | Global Constraints + Task 11 |
| gateMode ungated + showByok true independent | Tasks 2–4 |
| showStatusBar true; layout page; activityDetail full | Tasks 2–4, 7 |
| digichat:ready → digichat:seed; messages + pending | Tasks 5–6, 9 |
| First-party allowlist no token; customers still token | Task 1 |
| Preview pages.dev not on allowlist | Task 1 + Global Constraints |
| digivault env-name tenant config / GHCR docs | Task 7 |
| frame-src CSP; digichat frame-ancestors (+ www) | Tasks 10–11 |
| Ready timeout / load error copy; no silent hang | Task 9 (`CHAT_LOAD_ERROR_COPY`) |
| Seed caps | Task 5 |
| ACR automation non-goal | Task 7 checklist |
| Leave DataTap trial channel alone | Tasks 1, 6, 12 |
| Mermaid via existing digichat-ui | Task 12 smoke (no new package) |

**Placeholder scan:** No TBD/TODO left for hostname, caps, env var name, preview allowlisting, or timeout copy.

**Type consistency:** `showByok` / `showStatusBar` / `layout` names match across `EmbedTenantConfig`, client config, `resolveEmbedUiFlags`, and digithings tenant JSON. Message types are exactly `digichat:ready` / `digichat:seed`. Env var is exactly `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-digichat-phase3-unification.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints.

Which approach?
