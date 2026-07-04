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
