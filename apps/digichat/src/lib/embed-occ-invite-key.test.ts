/**
 * DIG-1381 / DIG-1210 Act B2 — occ.digithings.ai is off FIRST_PARTY_EMBED_HOSTS.
 * The invite key is the only accepted proof. A first-party browser origin does
 * not authorize this tenant.
 *
 *     if (tokenMatches(tenant.token, token)) return true;
 *     return isFirstPartyEmbedHost(host) && isFirstPartyEmbedHost(originHost);
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resolveEmbedChatTenant } from "./embed-chat-tenant";
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

describe("OCC invite key (occ.digithings.ai off the first-party allowlist)", () => {
  it("resolves with the invite key", () => {
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
