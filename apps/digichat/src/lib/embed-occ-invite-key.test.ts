/**
 * DIG-1381 (board approval e4c1d067, Act B1) — what the OCC invite key does and
 * does not gate **today**, and what Act B2 changes.
 *
 * Read `hostTenantAuthorized` in ./embed-chat-tenant.ts first:
 *
 *     if (tokenMatches(tenant.token, token)) return true;
 *     return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
 *
 * `occ.digithings.ai` is still in FIRST_PARTY_EMBED_HOSTS (./embed-first-party.ts,
 * `TODO(DIG-1210)`). So while that entry exists the key is **additive, not
 * required**: any caller that can present a first-party browser-attested
 * `Origin`/`Referer` is authorized with the right key, the wrong key, or no key
 * at all. Act B1 (roll the key into `DIGICHAT_EMBED_TENANTS`) therefore adds no
 * denial by itself — it is the precondition that lets Act B2 (delete the
 * allowlist entry) turn the key into the only accepted proof without locking
 * OCC out mid-deploy.
 *
 * The two describe blocks below pin both states. The Act B2 block mutates the
 * exported allowlist `Set` to simulate the one-line deletion, and restores it in
 * `afterEach`; `isFirstPartyEmbedHost` reads the `Set` per call, so no prod code
 * needs a test hook. When Act B2 lands, delete the first block and keep the
 * second — that is the assertion pair the CTO's verification list needs.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveEmbedChatTenant } from "./embed-chat-tenant";
import { FIRST_PARTY_EMBED_HOSTS } from "./embed-first-party";
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";

/** A test fixture, not a credential. Never a real key. */
const OCC_INVITE_KEY = "occ-invite-key-fixture-not-a-secret";
const WRONG_KEY = "occ-invite-key-guess";

/**
 * The production `DIGICHAT_EMBED_TENANTS` OCC entry with only the secret
 * replaced by a fixture. Shape from apps/digichat-cloudflare/README.md §
 * `DIGICHAT_EMBED_TENANTS`; the live entry additionally carries an
 * `mcp.servers` entry for the Zammad route whose literal `token` is the stack
 * Worker's `MCP_EDGE_KEY` — never committed, so not reproduced here.
 */
const OCC_REGISTRY = JSON.stringify({
  "occ.digithings.ai": {
    slug: "occ",
    gateMode: "ungated",
    showByok: true,
    showStatusBar: true,
    layout: "page",
    skin: "digichat",
    activityDetail: "full",
    title: "OCC help assistant",
    attribution: true,
    token: OCC_INVITE_KEY,
    backend: {
      type: "digigraph",
      digisearchIndex: "occ_help,occ_tickets",
      vaultPathPrefix: "clients/online-compliance-center",
    },
  },
});

function occRequest(headers: Record<string, string>): Request {
  return new Request("https://digithings.ai/api/chat", { method: "POST", headers });
}

const FIRST_PARTY_ORIGIN = { origin: "https://digithings.ai" };

beforeEach(() => {
  vi.stubEnv("NODE_ENV", "production");
  vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "");
  vi.stubEnv("DIGICHAT_EMBED_ENABLED", "");
  vi.stubEnv("DIGICHAT_EMBED_TOKEN", "");
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", OCC_REGISTRY);
  vi.stubEnv("DIGICHAT_CONFIG_PATH", "");
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

describe("OCC invite key, Act B1 state (occ.digithings.ai still first-party)", () => {
  it("resolves the occ tenant when the invite key matches", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": OCC_INVITE_KEY,
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("occ");
    expect(result.embedConfig?.backend).toMatchObject({ digisearchIndex: "occ_help,occ_tickets" });
  });

  it("STILL resolves with no key — Act B1 adds no denial of its own", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).not.toBeInstanceOf(Response);
  });

  it("STILL resolves with a wrong key from a first-party origin", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": WRONG_KEY,
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).not.toBeInstanceOf(Response);
  });

  it("rejects a wrong key when no first-party origin is browser-attested", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": WRONG_KEY,
      }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("rejects a wrong key from a third-party origin", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": WRONG_KEY,
        origin: "https://evil.example",
      }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("never authorizes on X-Embed-Host alone", () => {
    const result = resolveEmbedChatTenant(
      occRequest({ "x-embed-host": "https://occ.digithings.ai" }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });
});

describe("OCC invite key, Act B2 state (occ.digithings.ai off the first-party allowlist)", () => {
  const allowlist = FIRST_PARTY_EMBED_HOSTS as Set<string>;

  beforeEach(() => {
    allowlist.delete("occ.digithings.ai");
  });

  afterEach(() => {
    allowlist.add("occ.digithings.ai");
  });

  it("still resolves with the invite key — this is why B1 must land first", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": OCC_INVITE_KEY,
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("occ");
  });

  it("rejects a request with no key (CTO verification 3a)", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("rejects a request with a wrong key (CTO verification 3c)", () => {
    const result = resolveEmbedChatTenant(
      occRequest({
        "x-embed-host": "https://occ.digithings.ai",
        "x-embed-token": WRONG_KEY,
        ...FIRST_PARTY_ORIGIN,
      }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("leaves the digithings.ai marketing tenant tokenless", () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          aliases: ["www.digithings.ai"],
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "unused-for-first-party",
        },
      }),
    );
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      occRequest({ "x-embed-host": "https://digithings.ai", ...FIRST_PARTY_ORIGIN }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("digithings");
  });
});
