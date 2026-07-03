# DigiChat Embed: Pluggable External Backends + DataTapStream Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DigiChat's `/embed` surface support per-tenant external backends (starting with DataTapStream's Azure Foundry relay) and per-tenant access policy, then migrate the DataTapStream site from its custom `ChatPanel` to the embedded digichat.

**Architecture:** One env-var JSON registry (`DIGICHAT_EMBED_TENANTS`) drives embed host→tenant resolution, backend routing (DigiGraph vs external SSE relay), gate mode, theme, accent, attribution, and CSP frame-ancestors. `/api/chat` grows one branch: external-relay tenants stream through a new adapter that translates the relay's SSE contract into AI SDK UI message stream parts. The DataTapStream site's `/chat` page becomes an iframe of `/embed`.

**Tech Stack:** Next.js 16 App Router, AI SDK v6 (`createUIMessageStream`), vitest; datatap-web side: Next.js 14 static export, vitest + @testing-library/react.

**Spec:** `docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md` (committed with this plan on the task branch).

## Global Constraints

- "digichat" and "digithings" are ALWAYS lowercase in user-facing copy (both repos, hard rule).
- digithings repo: every PR links a GitHub issue (`task/<N>-slug` branch); PRs go into `module/digichat`, never directly into `develop`; run `make score` on staged changes before the PR; the implementing PR **always requires human review** (new external network dependency, per CLAUDE.md); update `frontend/digichat/ARCHITECTURE.md` after interface changes; never hand-edit `.claude/`.
- Legacy embed behavior must be byte-compatible when the registry is empty or the host is unknown: `{tenantSlug: "embed", ownerUserSub: "embed:anonymous"}`, `DIGICHAT_EMBED_ENABLED`/`X-Embed-Token` gating, DigiGraph backend, turn-limited client gate.
- Backend config (relay URLs) is NEVER sent to the client; the tenant-config endpoint returns only `{slug, gateMode, theme, accent, attribution}`.
- The external-relay path must not call `resolveDigigraphUpstreamAuth` or require any DigiGraph/DigiKey env.
- Both rate limiters (per-IP embed limiter + shared BFF bucket) run BEFORE the backend branch and apply to external tenants.
- The relay SSE contract is frozen: events `conversation | text-delta | trace | done | error`, frames `event: <type>\ndata: <json>\n\n`; request `POST {conversationId: string|null, message: string}`.
- datatap-web repo: keep the `api/` relay and `scripts/` knowledge-sync pipeline intact; `npm run build` (static export) must keep passing; work continues on the existing `feat/digichat` branch (PR #5).

## Prerequisites (do these before Task 1)

1. **Create the GitHub issue** (digithings repo — every change must trace to one):
   ```bash
   cd ~/Code/digithings
   gh issue create \
     --title "feat(digichat): pluggable external backends + ungated mode for the /embed surface" \
     --body "Make /embed per-tenant configurable (backend, gate mode, theme, accent, attribution) via a DIGICHAT_EMBED_TENANTS env registry, with an external-relay SSE adapter. First consumer: DataTapStream's Azure Foundry relay. Spec: docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md. Complements Epic #1248 (explicitly outside its scope). Human gate applies: new external network dependency." \
     --label "component:digichat"
   ```
   Note the issue number `<N>` — it names the branch.
2. **Sync `module/digichat` with develop** (it is ~88 commits behind; module branches forbid force-push, so sync via PR):
   ```bash
   git fetch origin
   git rev-list --count origin/module/digichat..origin/develop   # if 0, skip to step 3
   gh pr create --base module/digichat --head develop \
     --title "chore(sync): sync module/digichat with develop" \
     --body "Routine module-branch sync before task/<N> work."
   gh pr merge --merge <that-pr-number>
   git fetch origin
   ```
3. **Create the task branch:**
   ```bash
   git checkout -b task/<N>-digichat-embed-external-backend origin/module/digichat
   git add docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md \
           docs/superpowers/plans/2026-07-02-digichat-embed-external-backend.md
   git commit -m "docs(digichat): spec + plan for pluggable embed backends [#<N>]"
   cd frontend/digichat && npm ci   # workspace deps (run from repo root if workspaces hoist: npm ci at root)
   ```
4. **Test command sanity check:** `cd frontend/digichat && npx vitest run src/lib/embed-ip-rate-limit.test.ts` — expect PASS (proves the vitest setup works before you write anything).
5. Group B (Tasks 11–13) runs in `~/Code/datatap-web` on the existing `feat/digichat` branch. Tasks 11–12 are buildable anytime; **Task 13 is blocked until a deployed digichat embed URL exists** (Epic #1248 Phase 3 or an interim deployment — outside this plan).

---

## Group A — digithings (`~/Code/digithings`, all paths relative to `frontend/digichat/`)

### Task 1: Embed tenant registry module

**Repo:** digithings
**Files:**
- Create: `frontend/digichat/src/lib/embed-tenants.ts`
- Test: `frontend/digichat/src/lib/embed-tenants.test.ts`

**Interfaces:**
- Produces: `EmbedTenantConfig`, `EmbedBackendConfig` types; `normalizeEmbedHost(input: string | null | undefined): string | null`; `parseEmbedTenants(raw: string | undefined): Map<string, EmbedTenantConfig>`; `getEmbedTenantRegistry(): Map<string, EmbedTenantConfig>`; `resolveEmbedTenantByHost(hostOrOrigin: string | null | undefined): EmbedTenantConfig | null`; `resetEmbedTenantRegistryForTests(): void`. Consumed by Tasks 2, 4, 6.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/digichat/src/lib/embed-tenants.test.ts
import { describe, it, expect, afterEach, vi } from "vitest";
import {
  parseEmbedTenants,
  normalizeEmbedHost,
  resolveEmbedTenantByHost,
  resetEmbedTenantRegistryForTests,
} from "./embed-tenants";

const VALID = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    aliases: ["www.datatapstream.com", "dev.datatap.stream"],
    backend: {
      type: "external-relay",
      url: "https://datatap-digichat-relay.azurewebsites.net/api/digichat",
    },
    gateMode: "ungated",
    theme: "light",
    accent: { color: "#b5562b", foreground: "#fff7f2" },
    attribution: true,
  },
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("normalizeEmbedHost", () => {
  it("extracts hostnames from origins, URLs, and bare hosts", () => {
    expect(normalizeEmbedHost("https://Dev.DataTapStream.com")).toBe("dev.datatapstream.com");
    expect(normalizeEmbedHost("https://dev.datatapstream.com/chat/page")).toBe("dev.datatapstream.com");
    expect(normalizeEmbedHost("datatapstream.com")).toBe("datatapstream.com");
    expect(normalizeEmbedHost("localhost:8080")).toBe("localhost");
    expect(normalizeEmbedHost("")).toBeNull();
    expect(normalizeEmbedHost(null)).toBeNull();
  });
});

describe("parseEmbedTenants", () => {
  it("returns an empty registry for unset or blank env", () => {
    expect(parseEmbedTenants(undefined).size).toBe(0);
    expect(parseEmbedTenants("  ").size).toBe(0);
  });

  it("parses a valid registry and indexes aliases", () => {
    const reg = parseEmbedTenants(VALID);
    expect(reg.get("datatapstream.com")?.slug).toBe("datatapstream");
    expect(reg.get("www.datatapstream.com")?.slug).toBe("datatapstream");
    expect(reg.get("dev.datatap.stream")?.backend).toEqual({
      type: "external-relay",
      url: "https://datatap-digichat-relay.azurewebsites.net/api/digichat",
    });
    expect(reg.get("datatapstream.com")?.theme).toBe("light");
  });

  it("defaults theme to dark and attribution to false when omitted", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": { slug: "example", backend: { type: "digigraph" }, gateMode: "turn_limited" },
      })
    );
    expect(reg.get("example.com")?.theme).toBe("dark");
    expect(reg.get("example.com")?.attribution).toBe(false);
  });

  it("throws on malformed JSON", () => {
    expect(() => parseEmbedTenants("{nope")).toThrow(/not valid JSON/);
  });

  it("throws on a non-https relay URL", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "external-relay", url: "http://insecure.example.com/x" },
            gateMode: "ungated",
          },
        })
      )
    ).toThrow(/https/);
  });

  it("throws on invalid accent hex", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            accent: { color: "red", foreground: "#ffffff" },
          },
        })
      )
    ).toThrow(/hex/);
  });

  it("throws on a duplicate host/alias", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "a.example.com": { slug: "a", backend: { type: "digigraph" }, gateMode: "turn_limited" },
          "b.example.com": {
            slug: "b",
            aliases: ["a.example.com"],
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
          },
        })
      )
    ).toThrow(/duplicate/);
  });

  it("throws on an invalid gateMode or theme", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": { slug: "example", backend: { type: "digigraph" }, gateMode: "open" },
        })
      )
    ).toThrow(/gateMode/);
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            theme: "midnight",
          },
        })
      )
    ).toThrow(/theme/);
  });
});

describe("resolveEmbedTenantByHost", () => {
  it("resolves via the env-backed registry, including origins and aliases", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", VALID);
    resetEmbedTenantRegistryForTests();
    expect(resolveEmbedTenantByHost("https://www.datatapstream.com")?.slug).toBe("datatapstream");
    expect(resolveEmbedTenantByHost("https://unknown.example.com")).toBeNull();
    expect(resolveEmbedTenantByHost(null)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd ~/Code/digithings/frontend/digichat && npx vitest run src/lib/embed-tenants.test.ts`
Expected: FAIL — cannot resolve `./embed-tenants`.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/digichat/src/lib/embed-tenants.ts
/**
 * Embed tenant registry — one env var (DIGICHAT_EMBED_TENANTS, JSON keyed by
 * hostname) drives embed host→tenant resolution, backend routing, gate mode,
 * theme, accent, attribution, and CSP frame-ancestors.
 * Spec: docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md
 *
 * NOTE: security-headers.ts imports this at next.config.ts evaluation time,
 * so the env var must be present AT BUILD as well as at runtime.
 */

export type EmbedBackendConfig =
  | { type: "digigraph" }
  | { type: "external-relay"; url: string };

export type EmbedTenantConfig = {
  slug: string;
  aliases?: string[];
  backend: EmbedBackendConfig;
  gateMode: "turn_limited" | "ungated";
  theme: "dark" | "light";
  accent?: { color: string; foreground: string };
  attribution: boolean;
};

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const SLUG = /^[a-z0-9][a-z0-9-]*$/;

export function normalizeEmbedHost(input: string | null | undefined): string | null {
  if (!input) return null;
  const raw = input.trim().toLowerCase();
  if (!raw) return null;
  // Only trust URL parsing when a real scheme separator is present:
  // new URL("localhost:8080") parses "localhost:" as a SCHEME (empty hostname).
  if (raw.includes("://")) {
    try {
      return new URL(raw).hostname.replace(/\.$/, "") || null;
    } catch {
      return null;
    }
  }
  const host = raw.split("/")[0].split(":")[0].replace(/\.$/, "");
  return host || null;
}

function validateEntry(hostKey: string, value: unknown): EmbedTenantConfig {
  const ctx = `DIGICHAT_EMBED_TENANTS["${hostKey}"]`;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${ctx}: entry must be an object`);
  }
  const v = value as Record<string, unknown>;

  if (typeof v.slug !== "string" || !SLUG.test(v.slug)) {
    throw new Error(`${ctx}: "slug" must be lowercase alphanumeric/hyphens`);
  }

  const backend = v.backend as Record<string, unknown> | undefined;
  let backendCfg: EmbedBackendConfig;
  if (backend?.type === "digigraph") {
    backendCfg = { type: "digigraph" };
  } else if (backend?.type === "external-relay") {
    if (typeof backend.url !== "string") {
      throw new Error(`${ctx}: external-relay backend requires a "url"`);
    }
    let parsed: URL;
    try {
      parsed = new URL(backend.url);
    } catch {
      throw new Error(`${ctx}: backend.url is not a valid URL`);
    }
    if (parsed.protocol !== "https:") {
      throw new Error(`${ctx}: backend.url must be https`);
    }
    backendCfg = { type: "external-relay", url: backend.url };
  } else {
    throw new Error(`${ctx}: backend.type must be "digigraph" or "external-relay"`);
  }

  if (v.gateMode !== "turn_limited" && v.gateMode !== "ungated") {
    throw new Error(`${ctx}: gateMode must be "turn_limited" or "ungated"`);
  }

  if (v.theme !== undefined && v.theme !== "dark" && v.theme !== "light") {
    throw new Error(`${ctx}: theme must be "dark" or "light"`);
  }

  let accent: EmbedTenantConfig["accent"];
  if (v.accent !== undefined) {
    const a = v.accent as Record<string, unknown> | null;
    if (
      typeof a?.color !== "string" ||
      !HEX_COLOR.test(a.color) ||
      typeof a?.foreground !== "string" ||
      !HEX_COLOR.test(a.foreground)
    ) {
      throw new Error(`${ctx}: accent.color / accent.foreground must be #rrggbb hex`);
    }
    accent = { color: a.color, foreground: a.foreground };
  }

  if (v.aliases !== undefined && (!Array.isArray(v.aliases) || v.aliases.some((x) => typeof x !== "string"))) {
    throw new Error(`${ctx}: aliases must be an array of strings`);
  }

  return {
    slug: v.slug,
    aliases: v.aliases as string[] | undefined,
    backend: backendCfg,
    gateMode: v.gateMode,
    theme: (v.theme as "dark" | "light" | undefined) ?? "dark",
    accent,
    attribution: v.attribution === true,
  };
}

export function parseEmbedTenants(raw: string | undefined): Map<string, EmbedTenantConfig> {
  const registry = new Map<string, EmbedTenantConfig>();
  if (!raw || !raw.trim()) return registry;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`DIGICHAT_EMBED_TENANTS is not valid JSON: ${(e as Error).message}`);
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("DIGICHAT_EMBED_TENANTS must be a JSON object keyed by hostname");
  }

  for (const [hostKey, value] of Object.entries(parsed as Record<string, unknown>)) {
    const cfg = validateEntry(hostKey, value);
    const hosts = [hostKey, ...(cfg.aliases ?? [])];
    for (const candidate of hosts) {
      const host = normalizeEmbedHost(candidate);
      if (!host) throw new Error(`DIGICHAT_EMBED_TENANTS["${hostKey}"]: invalid host/alias "${candidate}"`);
      if (registry.has(host)) throw new Error(`DIGICHAT_EMBED_TENANTS: duplicate host/alias "${host}"`);
      registry.set(host, cfg);
    }
  }
  return registry;
}

let cachedRegistry: Map<string, EmbedTenantConfig> | null = null;

export function getEmbedTenantRegistry(): Map<string, EmbedTenantConfig> {
  if (!cachedRegistry) {
    cachedRegistry = parseEmbedTenants(process.env.DIGICHAT_EMBED_TENANTS);
    if (cachedRegistry.size > 0) {
      console.log(
        `[embed-tenants] loaded ${cachedRegistry.size} host mapping(s): ${[...cachedRegistry.keys()].join(", ")}`
      );
    }
  }
  return cachedRegistry;
}

/** Test hook — clears the module-level cache so stubbed envs take effect. */
export function resetEmbedTenantRegistryForTests(): void {
  cachedRegistry = null;
}

export function resolveEmbedTenantByHost(
  hostOrOrigin: string | null | undefined
): EmbedTenantConfig | null {
  const host = normalizeEmbedHost(hostOrOrigin);
  if (!host) return null;
  return getEmbedTenantRegistry().get(host) ?? null;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/lib/embed-tenants.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-tenants.ts frontend/digichat/src/lib/embed-tenants.test.ts
git commit -m "feat(digichat): embed tenant registry from DIGICHAT_EMBED_TENANTS env [#<N>]"
```

### Task 2: CSP frame-ancestors derived from the registry

**Repo:** digithings
**Files:**
- Modify: `frontend/digichat/src/lib/security-headers.ts`
- Test: `frontend/digichat/src/lib/security-headers.test.ts` (extend, keep existing assertions)

**Interfaces:**
- Consumes: `getEmbedTenantRegistry`, `resetEmbedTenantRegistryForTests` (Task 1).
- Produces: `embedFrameAncestors(): string[]` (first-party origins + `https://<host>` per registry key + localhost origins outside production). `embedFrameAncestorsCsp()` keeps its existing name/signature; `DIGICHAT_EMBED_SECURITY_HEADERS` unchanged in shape (still consumed by `next.config.ts`).

- [ ] **Step 1: Extend the test file** (add to the existing `security-headers.test.ts`; do not delete existing tests — they pin the first-party behavior with an empty registry)

```ts
// Append to frontend/digichat/src/lib/security-headers.test.ts
import { afterEach as afterEach2, vi as vi2 } from "vitest"; // if imports exist already, just reuse them
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { embedFrameAncestors, embedFrameAncestorsCsp } from "./security-headers";

// NOTE: adapt import style to the file's existing imports — one import block,
// no duplicate specifiers. The snippets below are the assertions to add.

describe("registry-derived frame-ancestors", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetEmbedTenantRegistryForTests();
  });

  it("always includes the first-party origins", () => {
    resetEmbedTenantRegistryForTests();
    const list = embedFrameAncestors();
    expect(list).toContain("'self'");
    expect(list).toContain("https://digithings.ai");
    expect(list).toContain("https://digiquant.io");
  });

  it("appends https origins for every registry host and alias", () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "datatapstream.com": {
          slug: "datatapstream",
          aliases: ["dev.datatap.stream"],
          backend: { type: "external-relay", url: "https://relay.example.com/api/x" },
          gateMode: "ungated",
        },
      })
    );
    resetEmbedTenantRegistryForTests();
    const csp = embedFrameAncestorsCsp();
    expect(csp).toContain("https://datatapstream.com");
    expect(csp).toContain("https://dev.datatap.stream");
    expect(csp.startsWith("frame-ancestors ")).toBe(true);
  });

  it("includes localhost origins only outside production", () => {
    resetEmbedTenantRegistryForTests();
    expect(embedFrameAncestors()).toContain("http://localhost:*"); // NODE_ENV=test
    vi.stubEnv("NODE_ENV", "production");
    expect(embedFrameAncestors()).not.toContain("http://localhost:*");
  });
});
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `npx vitest run src/lib/security-headers.test.ts`
Expected: FAIL — `embedFrameAncestors` is not exported.

- [ ] **Step 3: Implement** — replace the `EMBED_FRAME_ANCESTORS` const and `embedFrameAncestorsCsp` in `security-headers.ts` with:

```ts
import { getEmbedTenantRegistry } from "./embed-tenants";

const FIRST_PARTY_FRAME_ANCESTORS = [
  "'self'",
  "https://digithings.ai",
  "https://digiquant.io",
] as const;

/**
 * First-party origins + one https origin per registered embed-tenant host.
 * Dev/test additionally allow localhost so a local page can iframe /embed.
 * Evaluated when next.config.ts imports this module — DIGICHAT_EMBED_TENANTS
 * must be set at build time for external hosts to appear in the CSP.
 */
export function embedFrameAncestors(): string[] {
  const registryHosts = [...getEmbedTenantRegistry().keys()].map((h) => `https://${h}`);
  const dev =
    process.env.NODE_ENV !== "production" ? ["http://localhost:*", "http://127.0.0.1:*"] : [];
  return [...FIRST_PARTY_FRAME_ANCESTORS, ...registryHosts, ...dev];
}

export function embedFrameAncestorsCsp(): string {
  return `frame-ancestors ${embedFrameAncestors().join(" ")};`;
}
```

Keep everything else in the file as-is (`DIGICHAT_APP_CSP`, both header arrays — `DIGICHAT_EMBED_SECURITY_HEADERS` already calls `embedFrameAncestorsCsp()`). If any existing test imports `EMBED_FRAME_ANCESTORS` directly, update it to call `embedFrameAncestors()` instead.

- [ ] **Step 4: Run the full file's tests**

Run: `npx vitest run src/lib/security-headers.test.ts`
Expected: PASS (old + new).

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/security-headers.ts frontend/digichat/src/lib/security-headers.test.ts
git commit -m "feat(digichat): derive embed frame-ancestors from the tenant registry [#<N>]"
```

### Task 3: External relay SSE stream adapter

**Repo:** digithings
**Files:**
- Create: `frontend/digichat/src/lib/external-relay-stream.ts`
- Test: `frontend/digichat/src/lib/external-relay-stream.test.ts`

**Interfaces:**
- Produces: `parseRelaySse(body: ReadableStream<Uint8Array>): AsyncGenerator<RelayEvent>` where `RelayEvent = {event: string; data: Record<string, unknown>}`; `lastUserMessageText(messages: UIMessage[]): string`; `createExternalRelayStreamResponse(opts: {relayUrl: string; messages: UIMessage[]; conversationId: string | null; responseHeaders: Record<string, string>; signal?: AbortSignal}): Promise<Response>`. Consumed by Task 5.
- Emits UI message stream parts: `text-start/text-delta/text-end` (id `assistant-main`), `data-externalConversation` (`data: {conversationId}`, id `relay-conversation`), `data-digigraphTrace` (`data: {v: 1, type: "external_activity", service: "external", payload: {label, status}}`), and an AI SDK error part via throw + `onError`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/digichat/src/lib/external-relay-stream.test.ts
import { describe, it, expect, afterEach, vi } from "vitest";
import type { UIMessage } from "ai";
import {
  parseRelaySse,
  lastUserMessageText,
  createExternalRelayStreamResponse,
} from "./external-relay-stream";

function sseBody(frames: string[], chunkSize = 7): ReadableStream<Uint8Array> {
  // Deliberately re-chunk across frame boundaries to prove buffering works.
  const whole = frames.join("");
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < whole.length; i += chunkSize) {
        controller.enqueue(encoder.encode(whole.slice(i, i + chunkSize)));
      }
      controller.close();
    },
  });
}

function userMessage(text: string): UIMessage {
  return { id: "u1", role: "user", parts: [{ type: "text", text }] } as UIMessage;
}

async function drain(res: Response): Promise<string> {
  return await new Response(res.body).text();
}

afterEach(() => vi.unstubAllGlobals());

describe("parseRelaySse", () => {
  it("yields typed events across chunk boundaries and skips malformed frames", async () => {
    const body = sseBody([
      'event: conversation\ndata: {"type":"conversation","conversationId":"c1"}\n\n',
      "event: junk\ndata: {not json}\n\n",
      'event: text-delta\ndata: {"type":"text-delta","delta":"Hi"}\n\n',
    ]);
    const events = [];
    for await (const e of parseRelaySse(body)) events.push(e);
    expect(events).toEqual([
      { event: "conversation", data: { type: "conversation", conversationId: "c1" } },
      { event: "text-delta", data: { type: "text-delta", delta: "Hi" } },
    ]);
  });
});

describe("lastUserMessageText", () => {
  it("returns the latest user message's joined text parts", () => {
    const messages = [
      userMessage("first"),
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "reply" }] } as UIMessage,
      userMessage("second question"),
    ];
    expect(lastUserMessageText(messages)).toBe("second question");
  });
});

describe("createExternalRelayStreamResponse", () => {
  it("translates relay events into UI message stream parts", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        sseBody([
          'event: conversation\ndata: {"type":"conversation","conversationId":"conv_9"}\n\n',
          'event: trace\ndata: {"type":"trace","label":"Searching…","status":"in_progress"}\n\n',
          'event: text-delta\ndata: {"type":"text-delta","delta":"Hel"}\n\n',
          'event: text-delta\ndata: {"type":"text-delta","delta":"lo"}\n\n',
          'event: done\ndata: {"type":"done"}\n\n',
        ]),
        { status: 200 }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await createExternalRelayStreamResponse({
      relayUrl: "https://relay.example.com/api/digichat",
      messages: [userMessage("hello?")],
      conversationId: null,
      responseHeaders: { "X-Request-Id": "rid-1" },
    });
    const out = await drain(res);

    expect(fetchMock).toHaveBeenCalledWith(
      "https://relay.example.com/api/digichat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ conversationId: null, message: "hello?" }),
      })
    );
    expect(out).toContain('"type":"data-externalConversation"');
    expect(out).toContain('"conversationId":"conv_9"');
    expect(out).toContain('"type":"data-digigraphTrace"');
    expect(out).toContain('"external_activity"');
    expect(out).toContain('"delta":"Hel"');
    expect(out).toContain('"delta":"lo"');
    expect(res.headers.get("X-Request-Id")).toBe("rid-1");
  });

  it("forwards the stored conversationId on subsequent turns", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(sseBody(['event: done\ndata: {"type":"done"}\n\n']), { status: 200 })
    );
    vi.stubGlobal("fetch", fetchMock);
    await (
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("again")],
        conversationId: "conv_9",
        responseHeaders: {},
      })
    ).body?.cancel();
    expect(fetchMock.mock.calls[0][1].body).toBe(
      JSON.stringify({ conversationId: "conv_9", message: "again" })
    );
  });

  it("surfaces a relay error event as a stream error part", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          sseBody(['event: error\ndata: {"type":"error","message":"agent unavailable"}\n\n']),
          { status: 200 }
        )
      )
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    expect(out).toContain("agent unavailable");
    expect(out).toContain('"type":"error"');
  });

  it("reports a non-200 relay response as readable text", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("boom", { status: 503, statusText: "Service Unavailable" }))
    );
    const out = await drain(
      await createExternalRelayStreamResponse({
        relayUrl: "https://relay.example.com/api/digichat",
        messages: [userMessage("q")],
        conversationId: null,
        responseHeaders: {},
      })
    );
    expect(out).toContain("Upstream error: 503");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npx vitest run src/lib/external-relay-stream.test.ts`
Expected: FAIL — cannot resolve `./external-relay-stream`.

- [ ] **Step 3: Implement**

```ts
// frontend/digichat/src/lib/external-relay-stream.ts
/**
 * External relay backend adapter: translates the DataTapStream-style relay
 * SSE contract (event: conversation|text-delta|trace|done|error) into an AI
 * SDK UI message stream. The relay holds conversation history server-side
 * (Azure Foundry conversations), so each turn sends only the latest user
 * message plus the conversation id echoed by the client
 * (X-External-Conversation, stored in sessionStorage by /embed).
 */
import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessage,
} from "ai";

export type RelayEvent = { event: string; data: Record<string, unknown> };

export async function* parseRelaySse(
  body: ReadableStream<Uint8Array>
): AsyncGenerator<RelayEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "";
      let dataRaw = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataRaw = line.slice(6);
      }
      if (!event || !dataRaw) continue;
      try {
        yield { event, data: JSON.parse(dataRaw) as Record<string, unknown> };
      } catch {
        /* skip malformed frame */
      }
    }
  }
}

export function lastUserMessageText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user") continue;
    return m.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("\n")
      .trim();
  }
  return "";
}

export async function createExternalRelayStreamResponse(opts: {
  relayUrl: string;
  messages: UIMessage[];
  conversationId: string | null;
  responseHeaders: Record<string, string>;
  signal?: AbortSignal;
}): Promise<Response> {
  const message = lastUserMessageText(opts.messages);

  const stream = createUIMessageStream({
    onError: (error) =>
      error instanceof Error ? error.message : "external relay error",
    execute: async ({ writer }) => {
      const textId = "assistant-main";
      let textOpen = false;
      const openText = () => {
        if (!textOpen) {
          writer.write({ type: "text-start", id: textId });
          textOpen = true;
        }
      };
      const closeText = () => {
        if (textOpen) {
          writer.write({ type: "text-end", id: textId });
          textOpen = false;
        }
      };

      const res = await fetch(opts.relayUrl, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ conversationId: opts.conversationId, message }),
        signal: opts.signal,
      });

      if (!res.ok || !res.body) {
        const detail = res.body ? (await res.text().catch(() => "")).trim() : "";
        openText();
        writer.write({
          type: "text-delta",
          id: textId,
          delta: `Upstream error: ${res.status} ${res.statusText}${
            detail ? `\n${detail.slice(0, 500)}` : ""
          }`,
        });
        closeText();
        return;
      }

      let traceSeq = 0;
      try {
        for await (const { event, data } of parseRelaySse(res.body)) {
          if (event === "conversation" && typeof data.conversationId === "string") {
            writer.write({
              type: "data-externalConversation",
              id: "relay-conversation",
              data: { conversationId: data.conversationId },
            });
          } else if (event === "text-delta" && typeof data.delta === "string") {
            openText();
            writer.write({ type: "text-delta", id: textId, delta: data.delta });
          } else if (event === "trace") {
            writer.write({
              type: "data-digigraphTrace",
              id: `relay-trace-${traceSeq++}`,
              data: {
                v: 1,
                type: "external_activity",
                service: "external",
                payload: { label: data.label, status: data.status },
              },
            });
          } else if (event === "error") {
            throw new Error(
              typeof data.message === "string" ? data.message : "external relay error"
            );
          } else if (event === "done") {
            break;
          }
        }
      } finally {
        closeText();
      }
    },
  });

  return createUIMessageStreamResponse({ stream, headers: opts.responseHeaders });
}
```

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/lib/external-relay-stream.test.ts`
Expected: PASS. If the error-part test fails on the exact chunk shape, inspect the drained output — the requirement is that "agent unavailable" reaches the client as an AI SDK error chunk (via `onError`); adjust the assertion to the actual chunk format, not the implementation.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/external-relay-stream.ts frontend/digichat/src/lib/external-relay-stream.test.ts
git commit -m "feat(digichat): external-relay SSE stream adapter [#<N>]"
```

### Task 4: Registry-aware embed tenant resolution

**Repo:** digithings
**Files:**
- Modify: `frontend/digichat/src/lib/embed-chat-tenant.ts`
- Test: `frontend/digichat/src/lib/embed-chat-tenant.test.ts` (create if absent; if a test file already exists, extend it and keep its cases green)

**Interfaces:**
- Consumes: `resolveEmbedTenantByHost`, `EmbedTenantConfig` (Task 1).
- Produces: `EmbedChatTenantContext = ChatTenantContext & {embedConfig: EmbedTenantConfig | null}`; `embedHostOf(req: Request): string | null`; `resolveEmbedChatTenant(req): EmbedChatTenantContext | Response` (same name, widened return type). Consumed by Tasks 5 and 6. Existing exports (`isEmbedReferer`, `isEmbedAllowed`, `isEmbedChatRequest`) unchanged.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/digichat/src/lib/embed-chat-tenant.test.ts
import { describe, it, expect, afterEach, vi } from "vitest";
import { resolveEmbedChatTenant, embedHostOf } from "./embed-chat-tenant";
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";

const REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: { type: "external-relay", url: "https://relay.example.com/api/digichat" },
    gateMode: "ungated",
  },
});

function embedRequest(headers: Record<string, string>): Request {
  return new Request("https://chat.example.com/api/chat", { method: "POST", headers });
}

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("embedHostOf", () => {
  it("prefers X-Embed-Host over the referer", () => {
    const req = embedRequest({
      "x-embed-host": "https://datatapstream.com",
      referer: "https://other.example.com/page",
    });
    expect(embedHostOf(req)).toBe("https://datatapstream.com");
  });
});

describe("resolveEmbedChatTenant with a registered host", () => {
  it("resolves the tenant slug and config, with no env token required", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(embedRequest({ "x-embed-host": "https://datatapstream.com" }));
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("datatapstream");
    expect(result.ownerUserSub).toBe("embed:anonymous");
    expect(result.embedConfig?.backend).toEqual({
      type: "external-relay",
      url: "https://relay.example.com/api/digichat",
    });
  });
});

describe("resolveEmbedChatTenant legacy behavior (unknown host)", () => {
  it("keeps the env-gated legacy identity with a null embedConfig", () => {
    vi.stubEnv("DIGICHAT_EMBED_ENABLED", "1");
    const result = resolveEmbedChatTenant(embedRequest({ "x-embed-host": "https://unknown.example.com" }));
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("embed");
    expect(result.embedConfig).toBeNull();
  });

  it("still returns 503 for unknown hosts when embed is not enabled", () => {
    const result = resolveEmbedChatTenant(embedRequest({ "x-embed-host": "https://unknown.example.com" }));
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/lib/embed-chat-tenant.test.ts`
Expected: FAIL — `embedHostOf` not exported / `embedConfig` missing.

- [ ] **Step 3: Implement** — in `embed-chat-tenant.ts`, add imports and the new export, and extend `resolveEmbedChatTenant`:

```ts
import { resolveEmbedTenantByHost, type EmbedTenantConfig } from "@/lib/embed-tenants";

export type EmbedChatTenantContext = ChatTenantContext & {
  embedConfig: EmbedTenantConfig | null;
};

/** The embedding page's origin: explicit X-Embed-Host header, else the referer URL. */
export function embedHostOf(req: Request): string | null {
  const header = req.headers.get("x-embed-host")?.trim();
  if (header) return header;
  return req.headers.get("referer") ?? req.headers.get("referrer");
}
```

Then change `resolveEmbedChatTenant`'s signature to `EmbedChatTenantContext | Response` and insert the registry lookup between the `not_embed_request` guard and the `isEmbedAllowed` check:

```ts
  const registered = resolveEmbedTenantByHost(embedHostOf(req));
  if (registered) {
    // Presence in the registry IS the embed allowance for this host.
    return {
      tenantSlug: registered.slug,
      ownerUserSub: "embed:anonymous",
      embedConfig: registered,
    };
  }
  if (isEmbedAllowed(req)) {
    return { tenantSlug: "embed", ownerUserSub: "embed:anonymous", embedConfig: null };
  }
  // existing 503 Response unchanged
```

- [ ] **Step 4: Run this file's tests AND the route tests (regression)**

Run: `npx vitest run src/lib/embed-chat-tenant.test.ts src/app/api/chat/route.test.ts`
Expected: PASS. The widened return type is structurally compatible — `route.ts` only destructures `tenantSlug`/`ownerUserSub` today.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/lib/embed-chat-tenant.ts frontend/digichat/src/lib/embed-chat-tenant.test.ts
git commit -m "feat(digichat): resolve embed tenants from the registry in /api/chat context [#<N>]"
```

### Task 5: `/api/chat` external-relay branch

**Repo:** digithings
**Files:**
- Modify: `frontend/digichat/src/app/api/chat/route.ts`
- Test: `frontend/digichat/src/app/api/chat/route.test.ts` (extend — follow the file's existing mocking patterns exactly)

**Interfaces:**
- Consumes: `createExternalRelayStreamResponse` (Task 3), `embedConfig` on the tenant context (Task 4).

- [ ] **Step 1: Read the existing `route.test.ts`** to learn its request-builder/mocking helpers. The new tests below express the required behavior — adapt their setup style (env stubs, fetch stubs, request construction) to match the file's conventions.

- [ ] **Step 2: Add the failing tests**

```ts
// Add to frontend/digichat/src/app/api/chat/route.test.ts
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

const RELAY_REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: { type: "external-relay", url: "https://relay.example.com/api/digichat" },
    gateMode: "ungated",
  },
});

function relaySse(frames: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(c) {
        for (const f of frames) c.enqueue(encoder.encode(f));
        c.close();
      },
    }),
    { status: 200 }
  );
}

describe("external-relay embed tenants", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    resetEmbedTenantRegistryForTests();
  });

  it("streams from the configured relay without touching DigiGraph auth", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", RELAY_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const fetchMock = vi.fn().mockResolvedValue(
      relaySse([
        'event: conversation\ndata: {"type":"conversation","conversationId":"c1"}\n\n',
        'event: text-delta\ndata: {"type":"text-delta","delta":"Hi"}\n\n',
        'event: done\ndata: {"type":"done"}\n\n',
      ])
    );
    vi.stubGlobal("fetch", fetchMock);

    const res = await POST(
      new Request("http://127.0.0.1/api/chat", {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-embed-host": "https://datatapstream.com",
          "x-external-conversation": "c-prev",
        },
        body: JSON.stringify({
          messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: "hello" }] }],
        }),
      })
    );

    expect(res.status).toBe(200);
    const text = await new Response(res.body).text();
    expect(text).toContain('"delta":"Hi"');
    // The relay was called with the echoed conversation id and the latest message:
    expect(fetchMock).toHaveBeenCalledWith(
      "https://relay.example.com/api/digichat",
      expect.objectContaining({
        body: JSON.stringify({ conversationId: "c-prev", message: "hello" }),
      })
    );
    // No DIGIGRAPH_* / DIGIKEY_* env was set in this test — reaching a 200
    // proves resolveDigigraphUpstreamAuth was never invoked on this path.
  });
});
```

Additionally (spec requirement): add one test asserting the **per-IP embed limiter still fires for an external-relay tenant** — repeated requests from one IP against the `datatapstream` tenant must eventually return 429 *before* any relay fetch happens. Mirror the setup already used in `src/lib/embed-ip-rate-limit.test.ts` / the existing route tests for the limiter (same IP-header construction, same threshold env if one exists) — the assertion is `expect(res.status).toBe(429)` with `expect(fetchMock).not.toHaveBeenCalled()` on the over-limit request.

- [ ] **Step 3: Run to verify failure**

Run: `npx vitest run src/app/api/chat/route.test.ts`
Expected: the new test FAILS (route still routes embed tenants to DigiGraph and errors on upstream auth).

- [ ] **Step 4: Implement the branch.** In `route.ts`, add the import:

```ts
import { createExternalRelayStreamResponse } from "@/lib/external-relay-stream";
```

Then insert immediately **after** the `responseHeaders` object is built (after the `X-Digichat-Session`/`X-Request-Id` lines, currently ~line 103-107 on `module/digichat`) and **before** `convertToModelMessages` — i.e., after both rate-limit checks and the `messages` validation, before any BYOK/DigiGraph work:

```ts
  const embedConfig = "embedConfig" in tenantCtx ? tenantCtx.embedConfig : null;
  if (embedConfig?.backend.type === "external-relay") {
    return await createExternalRelayStreamResponse({
      relayUrl: embedConfig.backend.url,
      messages,
      conversationId: req.headers.get("x-external-conversation"),
      responseHeaders,
      signal: req.signal,
    });
  }
```

Nothing else in the route changes — the DigiGraph path below the branch stays byte-identical.

- [ ] **Step 5: Run the full route suite**

Run: `npx vitest run src/app/api/chat/route.test.ts`
Expected: PASS — new test and all pre-existing tests (embed IP rate limiting, legacy embed, authenticated path).

- [ ] **Step 6: Commit**

```bash
git add frontend/digichat/src/app/api/chat/route.ts frontend/digichat/src/app/api/chat/route.test.ts
git commit -m "feat(digichat): route external-relay embed tenants through the relay adapter [#<N>]"
```

### Task 6: Tenant-config endpoint for the embed client

**Repo:** digithings
**Files:**
- Create: `frontend/digichat/src/app/api/embed/tenant-config/route.ts`
- Test: `frontend/digichat/src/app/api/embed/tenant-config/route.test.ts`

**Interfaces:**
- Consumes: `resolveEmbedTenantByHost` (Task 1), `embedHostOf` (Task 4).
- Produces: `GET /api/embed/tenant-config` → `{slug, gateMode, theme, accent, attribution}`; unknown host → `{slug: "embed", gateMode: "turn_limited", theme: "dark", accent: null, attribution: false}`. Consumed by Task 7's client hook.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/digichat/src/app/api/embed/tenant-config/route.test.ts
import { describe, it, expect, afterEach, vi } from "vitest";
import { GET } from "./route";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("GET /api/embed/tenant-config", () => {
  it("returns the client-safe config for a registered host — never the backend", async () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "datatapstream.com": {
          slug: "datatapstream",
          backend: { type: "external-relay", url: "https://relay.example.com/api/digichat" },
          gateMode: "ungated",
          theme: "light",
          accent: { color: "#b5562b", foreground: "#fff7f2" },
          attribution: true,
        },
      })
    );
    resetEmbedTenantRegistryForTests();
    const res = await GET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": "https://datatapstream.com" },
      })
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = await res.json();
    expect(body).toEqual({
      slug: "datatapstream",
      gateMode: "ungated",
      theme: "light",
      accent: { color: "#b5562b", foreground: "#fff7f2" },
      attribution: true,
    });
    expect(JSON.stringify(body)).not.toContain("relay.example.com");
  });

  it("returns legacy defaults for unknown hosts", async () => {
    const res = await GET(new Request("http://127.0.0.1/api/embed/tenant-config"));
    expect(await res.json()).toEqual({
      slug: "embed",
      gateMode: "turn_limited",
      theme: "dark",
      accent: null,
      attribution: false,
    });
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `npx vitest run src/app/api/embed/tenant-config/route.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
// frontend/digichat/src/app/api/embed/tenant-config/route.ts
import { resolveEmbedTenantByHost } from "@/lib/embed-tenants";
import { embedHostOf } from "@/lib/embed-chat-tenant";

/** Client-safe embed tenant config. Backend config (relay URLs) never leaves the server. */
export async function GET(req: Request): Promise<Response> {
  const cfg = resolveEmbedTenantByHost(embedHostOf(req));
  const body = cfg
    ? {
        slug: cfg.slug,
        gateMode: cfg.gateMode,
        theme: cfg.theme,
        accent: cfg.accent ?? null,
        attribution: cfg.attribution,
      }
    : { slug: "embed", gateMode: "turn_limited", theme: "dark", accent: null, attribution: false };
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}
```

- [ ] **Step 4: Run the test**

Run: `npx vitest run src/app/api/embed/tenant-config/route.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/api/embed/tenant-config
git commit -m "feat(digichat): client-safe embed tenant-config endpoint [#<N>]"
```

### Task 7: Embed page — config-driven gate, theme, accent, attribution

**Repo:** digithings
**Files:**
- Create: `frontend/digichat/src/hooks/use-embed-tenant-config.ts`
- Modify: `frontend/digichat/src/app/embed/page.tsx`

**Interfaces:**
- Consumes: `GET /api/embed/tenant-config` (Task 6).
- Produces: `useEmbedTenantConfig(): EmbedTenantClientConfig` where `EmbedTenantClientConfig = {slug: string; gateMode: "turn_limited" | "ungated"; theme: "dark" | "light"; accent: {color: string; foreground: string} | null; attribution: boolean}`, plus `DEFAULT_EMBED_TENANT_CONFIG` (the legacy defaults — default-closed until the fetch resolves). Task 8 modifies the same page.

Note: this app has no React component test infra (no @testing-library). The hook and page changes are verified by Task 10's manual E2E; the server pieces they depend on are unit-tested in Tasks 1–6.

- [ ] **Step 1: Create the hook**

```ts
// frontend/digichat/src/hooks/use-embed-tenant-config.ts
"use client";

import { useEffect, useState } from "react";
import { p } from "@/lib/base-path";
import { resolveEmbedHost } from "@/lib/embed-gate";

export type EmbedTenantClientConfig = {
  slug: string;
  gateMode: "turn_limited" | "ungated";
  theme: "dark" | "light";
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
};

/** Legacy defaults — deliberately the *gated* configuration, so a slow or
 * failed config fetch can only be more restrictive than intended, never less. */
export const DEFAULT_EMBED_TENANT_CONFIG: EmbedTenantClientConfig = {
  slug: "embed",
  gateMode: "turn_limited",
  theme: "dark",
  accent: null,
  attribution: false,
};

export function useEmbedTenantConfig(): EmbedTenantClientConfig {
  const [config, setConfig] = useState<EmbedTenantClientConfig>(DEFAULT_EMBED_TENANT_CONFIG);

  useEffect(() => {
    let cancelled = false;
    fetch(p("/api/embed/tenant-config"), {
      headers: { "X-Embed-Host": resolveEmbedHost() },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((json: EmbedTenantClientConfig | null) => {
        if (
          !cancelled &&
          json &&
          (json.gateMode === "turn_limited" || json.gateMode === "ungated")
        ) {
          setConfig(json);
        }
      })
      .catch(() => {
        /* keep gated defaults */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return config;
}
```

- [ ] **Step 2: Wire the page.** In `src/app/embed/page.tsx`:

(a) `EmbedPage` fetches config once and drives theme + accent on the wrapper, passing config down:

```tsx
import {
  useEmbedTenantConfig,
  type EmbedTenantClientConfig,
} from "@/hooks/use-embed-tenant-config";

export default function EmbedPage({ searchParams }: EmbedPageProps) {
  const [accent, setAccent] = useState<Accent>("digichat");
  const tenantCfg = useEmbedTenantConfig();

  // ...existing searchParams + emit("embed_loaded") effects unchanged...

  const accentStyle = tenantCfg.accent
    ? ({
        "--accent": tenantCfg.accent.color,
        "--accent-foreground": tenantCfg.accent.foreground,
      } as React.CSSProperties)
    : undefined;

  return (
    <>
      <style>{ACCENT_CSS}</style>
      <div className="dc-grain" aria-hidden />
      <div
        className={`${tenantCfg.theme === "light" ? "" : "dark"} accent-${accent} relative z-10 flex min-h-dvh flex-col`}
        style={accentStyle}
      >
        <EmbedChat accent={accent} tenantCfg={tenantCfg} />
      </div>
    </>
  );
}
```

(b) `EmbedChat` takes `tenantCfg: EmbedTenantClientConfig` as a prop and derives:

```tsx
const ungated = tenantCfg.gateMode === "ungated";
const gate = useEmbedGate(byokIsSet || ungated);
```

- In `onSubmit`: guard the lock and the counter with `ungated` — `if (gate.locked && !ungated) return;` and `if (!ungated) gate.increment();`
- In the header, hide the turns badge when ungated, and lowercase the label (repo copy rule):

```tsx
<span className="text-sm font-semibold tracking-tight">digichat</span>
{ungated ? null : (
  <span
    className="text-[10px] uppercase tracking-wider text-muted-foreground"
    aria-label={`Turns used: ${gate.turns} of ${gate.limit}`}
  >
    {byokIsSet ? "BYOK unlocked" : `${gate.turns}/${gate.limit} free`}
  </span>
)}
```

- Paywall: `{gate.locked && !ungated ? <PaywallCard /> : (<form ...>...</form>)}` — the empty-state hint line also skips its "first N are free" copy when ungated:

```tsx
{messages.length === 0 && !gate.locked && (
  <p className="text-sm text-muted-foreground">
    {ungated
      ? "Ask a question to get started."
      : `Ask a question to get started. The first ${EMBED_FREE_TURN_LIMIT} are free.`}
  </p>
)}
```

(c) Attribution footer, rendered after the form/paywall block (lowercase copy is a hard requirement):

```tsx
{tenantCfg.attribution && (
  <p className="border-t border-border px-4 py-2 text-center text-[11px] text-muted-foreground">
    powered by digichat — a{" "}
    <a
      href="https://digithings.ai"
      target="_blank"
      rel="noreferrer noopener"
      className="underline"
      style={{ color: "var(--accent)" }}
    >
      digithings
    </a>{" "}
    product.
  </p>
)}
```

- [ ] **Step 3: Lint + full unit suite**

Run: `npm run lint && npx vitest run`
Expected: clean lint; all unit tests pass (page has no unit tests; this catches type/import errors via eslint + any indirect breakage).

- [ ] **Step 4: Quick smoke** — `npm run dev`, open `http://127.0.0.1:3005/embed` directly: default (unknown host) behavior must look exactly like before this task (dark, turns badge, gate after 3 turns).

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/hooks/use-embed-tenant-config.ts frontend/digichat/src/app/embed/page.tsx
git commit -m "feat(digichat): config-driven embed gate/theme/accent/attribution [#<N>]"
```

### Task 8: Embed page — markdown, activity box, conversation continuity

**Repo:** digithings
**Files:**
- Modify: `frontend/digichat/src/app/embed/page.tsx`

**Interfaces:**
- Consumes: `data-digigraphTrace` and `data-externalConversation` stream parts (Task 3); `gate.host` from `useEmbedGate`.
- Produces: sessionStorage key `digichat_embed_conversation:<host>`; request header `X-External-Conversation` (consumed by Task 5's branch).

- [ ] **Step 1: Markdown for assistant messages.** Replace `MessageBubble`'s plain-text body for assistant messages with markdown (both packages are existing dependencies):

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function MessageBubble({ message }: { message: UIMessage }) {
  const text = message.parts
    .filter((p): p is { type: "text"; text: string } => p.type === "text")
    .map((p) => p.text)
    .join("");
  const mine = message.role === "user";
  return (
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
          mine
            ? "bg-[color:var(--accent)] text-[color:var(--accent-foreground)]"
            : "bg-muted text-foreground"
        }`}
      >
        {mine ? (
          text || <span className="opacity-60">…</span>
        ) : text ? (
          <div className="prose prose-sm dark:prose-invert max-w-none [&_p]:my-1">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : (
          <span className="opacity-60">…</span>
        )}
      </div>
    </div>
  );
}
```

(If the `prose` classes don't exist in this Tailwind setup — no typography plugin — drop the `prose*` classes and keep the wrapper `div` with `[&_p]:my-1 [&_ul]:my-1 [&_ul]:pl-4 [&_li]:list-disc text-sm`; verify rendering in Task 10.)

- [ ] **Step 2: Activity box.** Add below `MessageBubble` in the same file, and render it under each assistant message in the message list (`{messages.map((m) => (<div key={m.id}><MessageBubble message={m} />{m.role === "assistant" && <ActivityBox message={m} />}</div>))}`):

```tsx
type TracePartData = {
  type?: string;
  payload?: { label?: unknown; status?: unknown };
};

function ActivityBox({ message }: { message: UIMessage }) {
  const traces = message.parts.filter(
    (part): part is { type: "data-digigraphTrace"; data: TracePartData } =>
      part.type === "data-digigraphTrace"
  );
  if (traces.length === 0) return null;
  return (
    <div className="mt-1 max-w-[85%] rounded-md border border-border/60 bg-muted/30 px-2.5 py-1.5">
      {traces.map((t, i) => {
        const label = t.data?.payload?.label ?? t.data?.type ?? "activity";
        const done = t.data?.payload?.status === "completed";
        return (
          <p key={i} className="font-mono text-[11px] leading-5 text-muted-foreground">
            {done ? "✓ " : "… "}
            {String(label)}
          </p>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Conversation continuity.** In `EmbedChat`:

```tsx
const CONVERSATION_STORAGE_PREFIX = "digichat_embed_conversation:";

function conversationStorageKey(host: string): string {
  return `${CONVERSATION_STORAGE_PREFIX}${host}`;
}
```

(a) In the transport's `prepareSendMessagesRequest`, after the existing header assembly:

```tsx
try {
  const conversationId = window.sessionStorage.getItem(conversationStorageKey(gate.host));
  if (conversationId) headers["X-External-Conversation"] = conversationId;
} catch {
  /* sessionStorage unavailable (e.g. blocked third-party storage) — start fresh turns */
}
```

(b) New effect that captures the id from incoming stream parts:

```tsx
useEffect(() => {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant") return;
  for (const part of last.parts) {
    if (part.type === "data-externalConversation") {
      const id = (part as { data?: { conversationId?: string } }).data?.conversationId;
      if (id) {
        try {
          window.sessionStorage.setItem(conversationStorageKey(gate.host), id);
        } catch {
          /* ignore */
        }
      }
    }
  }
}, [messages, gate.host]);
```

- [ ] **Step 4: Lint + unit suite + legacy smoke**

Run: `npm run lint && npx vitest run`
Then `npm run dev` → `http://127.0.0.1:3005/embed`: legacy embed still renders and chats (markdown now active on assistant bubbles; no activity box appears for tenants whose stream carries no trace parts... note DigiGraph traces WILL now render in the embed too — that is intended per the spec: "This benefits digithings' own embeds too").

- [ ] **Step 5: Commit**

```bash
git add frontend/digichat/src/app/embed/page.tsx
git commit -m "feat(digichat): embed markdown rendering, activity box, relay conversation continuity [#<N>]"
```

### Task 9: Documentation — ARCHITECTURE.md + env reference

**Repo:** digithings
**Files:**
- Modify: `frontend/digichat/ARCHITECTURE.md` (required by repo rules after interface changes)
- Modify: `frontend/digichat/README.md` (env var table/section, if one exists — otherwise ARCHITECTURE.md's env section only)

- [ ] **Step 1: ARCHITECTURE.md.** Add a subsection at the end of "5. Internal Architecture":

```markdown
### Embed tenant registry & external backends

`DIGICHAT_EMBED_TENANTS` (JSON, keyed by hostname) declares embed tenants:
per-host `slug`, `backend` (`digigraph` | `external-relay` + https URL),
`gateMode` (`turn_limited` | `ungated`), `theme` (`dark` | `light`),
optional `accent` hex pair, `attribution` flag, and `aliases`. Parsed
fail-fast in `src/lib/embed-tenants.ts`; the same registry feeds
`/api/chat` tenant resolution (`src/lib/embed-chat-tenant.ts`), the
client-safe `GET /api/embed/tenant-config` endpoint, and the `/embed`
CSP frame-ancestors (`src/lib/security-headers.ts` — which means the env
var must be present at build time, not just runtime).

`external-relay` tenants bypass DigiGraph entirely: `/api/chat` proxies to
the configured relay via `src/lib/external-relay-stream.ts`, translating
the relay's SSE contract (`conversation`, `text-delta`, `trace`, `done`,
`error`) into AI SDK UI message stream parts. Conversation state lives on
the relay's side (e.g. Azure Foundry conversations); the client echoes the
relay's conversation id via `X-External-Conversation` (sessionStorage,
`digichat_embed_conversation:<host>`). Both rate limiters (per-IP embed +
shared BFF bucket, now keyed by the tenant's real slug) run before the
backend branch. `X-Embed-Host` is attacker-settable but only selects among
preconfigured tenants — relay URLs come from config, never the request, so
there is no open-proxy/SSRF surface. First consumer: DataTapStream
(datatap-web) via its Azure Function relay.
```

- [ ] **Step 2: Env documentation.** In ARCHITECTURE.md section "10. Docker & MCP Composition → Environment variables" (and README if it lists env vars), add:

```markdown
- `DIGICHAT_EMBED_TENANTS` — optional JSON registry of embed tenants (see
  "Embed tenant registry & external backends"). Unset = no external embed
  tenants; first-party embeds behave exactly as before. Must be present at
  build time for CSP frame-ancestors derivation.
```

- [ ] **Step 3: Verify markdown links** — `cd ~/Code/digithings && make doc-check` (repo command). Expected: no broken links.

- [ ] **Step 4: Commit**

```bash
git add frontend/digichat/ARCHITECTURE.md frontend/digichat/README.md
git commit -m "docs(digichat): document embed tenant registry + external backends [#<N>]"
```

### Task 10: Full-suite gate, live E2E, score, PR

**Repo:** digithings

- [ ] **Step 1: Full unit suite + lint + build**

```bash
cd ~/Code/digithings/frontend/digichat
npx vitest run && npm run lint && npm run build
```
Expected: everything green. (`npm run build` needs no registry env — empty registry is valid.)

- [ ] **Step 2: Live E2E against the real DataTapStream relay.** Start digichat with a local registry (note `127.0.0.1` alias so a locally-served page can embed):

```bash
export DIGICHAT_EMBED_TENANTS='{"datatapstream.com":{"slug":"datatapstream","aliases":["dev.datatapstream.com","dev.datatap.stream","127.0.0.1","localhost"],"backend":{"type":"external-relay","url":"https://datatap-digichat-relay.azurewebsites.net/api/digichat"},"gateMode":"ungated","theme":"light","accent":{"color":"#b5562b","foreground":"#fff7f2"},"attribution":true}}'
npm run dev
```

Serve a throwaway host page (do not commit it):

```bash
mkdir -p /tmp/embed-host && cat > /tmp/embed-host/index.html <<'EOF'
<!doctype html><body style="background:#f7f9fc">
<iframe src="http://127.0.0.1:3005/embed" style="width:720px;height:640px;border:1px solid #ddd"></iframe>
</body>
EOF
cd /tmp/embed-host && python3 -m http.server 8080
```

Open `http://127.0.0.1:8080` and verify the checklist:
- [ ] iframe renders (CSP allows the localhost ancestor in dev)
- [ ] light theme + terracotta accent + lowercase "digichat" header, no turns badge
- [ ] ask "What authentication method does the DataTapStream API use?" → streamed markdown answer
- [ ] activity box shows file-search trace lines (searched-for queries and/or cited sources, ✓ when completed)
- [ ] second question gets a contextual answer (conversation continuity — check `X-External-Conversation` on the second `/api/chat` request in devtools)
- [ ] 4th+ message sends fine (no paywall)
- [ ] attribution line "powered by digichat — a digithings product." renders, all lowercase
- [ ] control: open `http://127.0.0.1:3005/embed` directly (no registered ancestor) → legacy dark gated behavior intact

- [ ] **Step 3: Score gate**

```bash
cd ~/Code/digithings && git add -A && make score
```
Expected: Security ≥ 8, Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9. Fix and re-score if below (two attempts, then escalate to human per repo rules).

- [ ] **Step 4: Push + PR into `module/digichat`** (NOT develop):

```bash
git push -u origin task/<N>-digichat-embed-external-backend
gh pr create --base module/digichat \
  --title "feat(digichat): pluggable external backends + ungated mode for /embed" \
  --body "Fixes #<N>. Adds the DIGICHAT_EMBED_TENANTS registry (backend routing, gate mode, theme, accent, attribution, CSP frame-ancestors), the external-relay SSE adapter, the client-safe tenant-config endpoint, and the /embed UI upgrades (markdown, activity box, continuity). Legacy embed behavior is registry-empty-compatible. HUMAN GATE: new external network dependency (relay egress) — do not merge without human review. Spec + plan in docs/superpowers/."
```
**STOP here for human review — do not merge autonomously.**

---

## Group B — datatap-web migration (`~/Code/datatap-web`, branch `feat/digichat`, PR #5)

> Tasks 11–12 are buildable immediately. **Task 13 requires a live, publicly-served digichat embed URL** (Epic #1248 Phase 3 or an interim deployment) plus the Group A PR merged and deployed with the DataTapStream registry entry — do not start it before both exist.

### Task 11: `/chat` page becomes the digichat embed iframe

**Repo:** datatap-web
**Files:**
- Modify: `app/chat/page.tsx`
- Create: `app/chat/chat.module.css`
- Modify: `app/chat/page.test.tsx`

**Interfaces:**
- Consumes: `NEXT_PUBLIC_DIGICHAT_EMBED_URL` build-time env (e.g. `https://digithings.ai/chat/embed`). Unset → friendly fallback note (static export bakes envs at build; the page must not render a broken empty iframe).

- [ ] **Step 1: Rewrite the page test**

```tsx
// app/chat/page.test.tsx  (replace the existing file's test body)
import { test, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import ChatPage from './page';

afterEach(() => {
  vi.unstubAllEnvs();
});

test('renders the digichat embed iframe when the embed URL is configured', () => {
  vi.stubEnv('NEXT_PUBLIC_DIGICHAT_EMBED_URL', 'https://digithings.ai/chat/embed');
  render(<ChatPage />);
  const frame = screen.getByTitle('digichat');
  expect(frame).toHaveAttribute('src', 'https://digithings.ai/chat/embed');
});

test('renders a fallback note when the embed URL is not configured', () => {
  vi.stubEnv('NEXT_PUBLIC_DIGICHAT_EMBED_URL', '');
  render(<ChatPage />);
  expect(screen.getByText(/digichat is warming up/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/Code/datatap-web && npx vitest run app/chat/page.test.tsx`
Expected: FAIL (page still renders `ChatPanel`).

- [ ] **Step 3: Implement the page**

```tsx
// app/chat/page.tsx
import type { Metadata } from 'next';
import styles from './chat.module.css';

export const metadata: Metadata = {
  title: 'digichat — DataTapStream',
  description: 'Ask digichat questions about the DataTapStream API, grounded on the real docs.'
};

export default function ChatPage() {
  const embedUrl = process.env.NEXT_PUBLIC_DIGICHAT_EMBED_URL;
  return (
    <section className="section">
      <div className="container">
        {embedUrl ? (
          <iframe src={embedUrl} title="digichat" className={styles.embed} />
        ) : (
          <p className="muted">digichat is warming up — check back soon.</p>
        )}
      </div>
    </section>
  );
}
```

```css
/* app/chat/chat.module.css */
.embed {
  width: 100%;
  height: 72vh;
  min-height: 480px;
  border: 0;
  border-radius: 8px;
  background: transparent;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run app/chat/page.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add app/chat/page.tsx app/chat/chat.module.css app/chat/page.test.tsx
git commit -m "digichat: /chat serves the embedded digichat instead of the custom panel"
```

### Task 12: Retire the custom chat frontend code

**Repo:** datatap-web
**Files:**
- Delete: `components/ChatPanel.tsx`, `components/ChatPanel.module.css`, `components/ChatPanel.test.tsx`, `components/chat/` (entire directory: `useDigichatStream.ts`, `parseSseStream.ts`, and their test files)
- Modify: `package.json` (+ lockfile), `.github/workflows/deploy-web.yml`, `.github/workflows/deploy-web-preview.yml`, `README.md`
- Keep untouched: `api/` (the relay — digichat now calls it), `scripts/` (knowledge sync), `components/Turnstile.tsx` (used by the trial pages)

- [ ] **Step 1: Delete the dead components**

```bash
cd ~/Code/datatap-web
git rm components/ChatPanel.tsx components/ChatPanel.module.css components/ChatPanel.test.tsx
git rm -r components/chat
```

- [ ] **Step 2: Remove now-unused deps.** Verify then remove (only if the grep is empty):

```bash
grep -rn "react-markdown" app components lib --include="*.tsx" --include="*.ts" | grep -v node_modules
# expect: no matches → safe to remove
npm uninstall react-markdown
```

- [ ] **Step 3: Workflow env swap.** In `.github/workflows/deploy-web-preview.yml`, in the "Install & build" step's `env:` block, replace the `NEXT_PUBLIC_DIGICHAT_RELAY_URL` line with:

```yaml
          NEXT_PUBLIC_DIGICHAT_EMBED_URL: ${{ vars.NEXT_PUBLIC_DIGICHAT_EMBED_URL }}
```

In `.github/workflows/deploy-web.yml`, add the same line to its "Install & build" `env:` block. Then confirm no workflow references the old var:

```bash
grep -rn "DIGICHAT_RELAY_URL" .github/ && echo "STILL REFERENCED — fix" || echo "clean"
```

- [ ] **Step 4: README.** In the env-var table, remove any `NEXT_PUBLIC_DIGICHAT_RELAY_URL` row and add:

```markdown
| `NEXT_PUBLIC_DIGICHAT_EMBED_URL` | digichat embed page this site iframes at /chat | `https://digithings.ai/chat/embed` |
```

- [ ] **Step 5: Full verification**

```bash
npm test && npm run build
```
Expected: all remaining tests pass (chat page tests, scripts/api suites unaffected); static export builds with `/chat` present.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "digichat: retire the custom chat panel — digichat embed is the single chat frontend"
```

### Task 13: Cutover config + live verification on the PR preview  **[BLOCKED until a deployed embed URL exists]**

**Repo:** datatap-web (plus manual config on the digichat deployment and GitHub)

- [ ] **Step 1: digichat deployment config (manual, wherever the digichat container runs).** Its environment must include the DataTapStream tenant — production hosts AND the SWA preview host so the PR preview can embed:

```json
{"datatapstream.com":{"slug":"datatapstream","aliases":["www.datatapstream.com","dev.datatapstream.com","dev.datatap.stream","nice-glacier-0187d6403.7.azurestaticapps.net","nice-glacier-0187d6403-5.westeurope.7.azurestaticapps.net"],"backend":{"type":"external-relay","url":"https://datatap-digichat-relay.azurewebsites.net/api/digichat"},"gateMode":"ungated","theme":"light","accent":{"color":"#b5562b","foreground":"#fff7f2"},"attribution":true}}
```

Remember: present at **build** time of the digichat image (CSP) and at runtime.

- [ ] **Step 2: Set the datatap-web build var** (once the embed URL is known — `https://digithings.ai/chat/embed` after Phase 3, or the interim deployment's URL):

```bash
gh variable set NEXT_PUBLIC_DIGICHAT_EMBED_URL --env dev -R DataTapStream/datatap-web -b "<embed-url>"
```

- [ ] **Step 3: Push and let the preview rebuild**

```bash
cd ~/Code/datatap-web && git push origin feat/digichat
gh run watch -R DataTapStream/datatap-web $(gh run list -R DataTapStream/datatap-web --workflow=deploy-web-preview.yml --branch feat/digichat --limit 1 --json databaseId -q '.[0].databaseId')
```

- [ ] **Step 4: Verify on the live preview** (`https://nice-glacier-0187d6403-5.westeurope.7.azurestaticapps.net/chat/`):
- [ ] iframe loads (no CSP block — check devtools console)
- [ ] light theme, terracotta accent, lowercase "digichat", attribution line
- [ ] streamed markdown answer to a real API question, with the activity/trace box
- [ ] follow-up question is context-aware (continuity)
- [ ] no paywall on the 4th+ message
- [ ] note: the relay's CORS entries for datatapstream hosts are now unused (the browser talks only to the digichat origin; digichat calls the relay server-side) — leave them in place as a rollback path, do not remove in this task

- [ ] **Step 5: Update PR #5's description** (test plan section) to reflect the embed architecture, and hand both PRs (digithings + datatap-web) to human review.

---

## Execution notes for the controller

- Group A tasks 1–6 are mechanical against this plan (complete code provided); Tasks 7–8 modify a large client component and warrant a standard-tier implementer; Task 10 is controller-run (live E2E + score + PR), not a subagent dispatch.
- Task 5's Step 1 requires reading `route.test.ts` first — its mocking conventions were not inspectable when this plan was written; the test code given expresses required behavior, not final form.
- Group B runs in `~/Code/datatap-web` — dispatch those implementers with that repo as their working directory and the existing `feat/digichat` branch checked out.
- If `make score` or the human review rejects the external-egress design, the fallback discussed in the spec (UI-only extraction) is a separate re-plan, not a patch on this one.
