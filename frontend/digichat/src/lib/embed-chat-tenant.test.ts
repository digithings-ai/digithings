import { resolve } from "node:path";
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import {
  embedHostOf,
  resolveAnonymousInstallChat,
  resolveEmbedChatTenant,
  resolveEmbedClientConfigForPaint,
} from "./embed-chat-tenant";
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";
import { DEFAULT_EMBED_TENANT_CONFIG } from "@/lib/embed-client-config";

const REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: {
      type: "foundry",
      projectEndpoint: "https://example.services.ai.azure.com",
      agentName: "agent",
    },
    gateMode: "ungated",
    token: "datatapstream-secret",
  },
});

function embedRequest(headers: Record<string, string>): Request {
  return new Request("https://chat.example.com/api/chat", { method: "POST", headers });
}

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

beforeEach(() => {
  vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "");
  vi.stubEnv("DIGICHAT_EMBED_ENABLED", "");
  vi.stubEnv("DIGICHAT_EMBED_TOKEN", "");
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
  vi.stubEnv("DIGICHAT_CHROME_SKIN", "");
  vi.stubEnv("DIGICHAT_CONFIG_PATH", "");
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
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
  it("resolves the tenant slug and config when the tenant's own token is presented", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({
        "x-embed-host": "https://datatapstream.com",
        "x-embed-token": "datatapstream-secret",
      })
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("datatapstream");
    expect(result.ownerUserSub).toBe("embed:anonymous");
    expect(result.embedConfig?.backend).toEqual({
      type: "foundry",
      projectEndpoint: "https://example.services.ai.azure.com",
      agentName: "agent",
    });
  });

  it("does NOT resolve tenant-specific config from the host alone — no token means impersonation is possible otherwise (#1339)", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(embedRequest({ "x-embed-host": "https://datatapstream.com" }));
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("does NOT resolve tenant-specific config when the presented token is wrong", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({
        "x-embed-host": "https://datatapstream.com",
        "x-embed-token": "guessed-wrong",
      })
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("falls back to the generic legacy embed tenant (not the registered one) when the token is missing but legacy embed is globally enabled", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "1");
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(embedRequest({ "x-embed-host": "https://datatapstream.com" }));
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("embed");
    expect(result.embedConfig).toBeNull();
  });
});

describe("resolveEmbedChatTenant legacy behavior (unknown host)", () => {
  it("keeps the env-gated legacy identity with a null embedConfig", () => {
    vi.stubEnv("DIGICHAT_LEGACY_EMBED_ENABLED", "1");
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

const DIGITHINGS_REGISTRY = JSON.stringify({
  "digithings.ai": {
    slug: "digithings",
    aliases: ["www.digithings.ai"],
    backend: { type: "digigraph" },
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

const LOCALHOST_REGISTRY = JSON.stringify({
  localhost: {
    slug: "digithings",
    aliases: ["127.0.0.1"],
    backend: { type: "digigraph" },
    gateMode: "ungated",
    activityDetail: "full",
    token: "local-dev-token",
  },
});

describe("dev loopback first-party (dogfood)", () => {
  it("resolves localhost without X-Embed-Token in development when registered", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", LOCALHOST_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "http://localhost:3000" }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("digithings");
    expect(result.embedConfig?.gateMode).toBe("ungated");
  });

  it("resolves 127.0.0.1 via alias without token in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", LOCALHOST_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "http://127.0.0.1:3000" }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("digithings");
  });

  it("returns 503 for localhost in production even when registered", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", LOCALHOST_REGISTRY);
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "http://localhost:3000" }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("returns 503 for unregistered localhost in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "http://localhost:3000" }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });
});

const CHATGPT_YAML = resolve(__dirname, "../../config/examples/skins/chatgpt.yaml");
const WEBPAGE_YAML = resolve(
  __dirname,
  "../../config/examples/skins/webpage-assistant.yaml",
);

describe("client-container YAML install", () => {
  it("paints /embed from the baked chatgpt.yaml without DIGICHAT_EMBED_TENANTS", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", CHATGPT_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const painted = resolveEmbedClientConfigForPaint(undefined, undefined);
    expect(painted).not.toEqual(DEFAULT_EMBED_TENANT_CONFIG);
    expect(painted.skin).toBe("chatgpt");
    expect(painted.slug).toBe("client-chatgpt");
    expect(painted.gateMode).toBe("ungated");
    expect(painted.theme).toBe("light");
  });

  it("lets POST /api/chat through for an unregistered parent host", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", CHATGPT_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://acme.example" }),
    );
    expect(result).not.toBeInstanceOf(Response);
    if (result instanceof Response) return;
    expect(result.tenantSlug).toBe("client-chatgpt");
    expect(result.ownerUserSub).toBe("embed:anonymous");
    expect(result.embedConfig?.skin).toBe("chatgpt");
  });

  it("does not override a registered customer host that lacks a token (#1339)", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", CHATGPT_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const result = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://datatapstream.com" }),
    );
    expect(result).toBeInstanceOf(Response);
    if (result instanceof Response) expect(result.status).toBe(503);
  });

  it("requires the YAML token when the operator set one", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", CHATGPT_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TOKEN", "install-secret");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const denied = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://acme.example" }),
    );
    expect(denied).toBeInstanceOf(Response);
    const allowed = resolveEmbedChatTenant(
      embedRequest({
        "x-embed-host": "https://acme.example",
        "x-embed-token": "install-secret",
      }),
    );
    expect(allowed).not.toBeInstanceOf(Response);
    if (allowed instanceof Response) return;
    expect(allowed.tenantSlug).toBe("client-chatgpt");
  });

  it("unlocks anonymous app chat for layout templates on /", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", WEBPAGE_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const ctx = resolveAnonymousInstallChat();
    expect(ctx?.tenantSlug).toBe("client-webpage-assistant");
    expect(ctx?.embedConfig?.skin).toBe("webpage-assistant");
    expect(ctx?.embedConfig?.layout).toBe("page");
  });
});

const DIGITHINGS_EMBED_YAML = resolve(
  __dirname,
  "../../config/examples/digithings-ai-embed.yaml",
);
const OCC_EMBED_YAML = resolve(__dirname, "../../config/examples/occ-embed.yaml");

describe("product embed YAML hosts", () => {
  it("paints digithings.ai from hosts YAML as digichat skin with tools", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", DIGITHINGS_EMBED_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const painted = resolveEmbedClientConfigForPaint(
      undefined,
      "https://digithings.ai",
    );
    expect(painted.skin).toBe("digichat");
    expect(painted.slug).toBe("digithings-ai");
    expect(painted.backendType).toBe("digigraph");
    expect(painted.webSearch).toBe(true);
    expect(painted.gateMode).toBe("ungated");
  });

  it("paints OCC YAML host without web_search", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", OCC_EMBED_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const painted = resolveEmbedClientConfigForPaint(
      undefined,
      "https://occ.digithings.ai",
    );
    expect(painted.skin).toBe("digichat");
    expect(painted.slug).toBe("occ");
    expect(painted.backendType).toBe("digigraph");
    expect(painted.webSearch).toBe(false);
  });

  it("does not leak the first YAML host to an unknown parent", () => {
    vi.stubEnv("DIGICHAT_CONFIG_PATH", DIGITHINGS_EMBED_YAML);
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", "");
    resetDigichatConfigForTests();
    resetEmbedTenantRegistryForTests();
    const painted = resolveEmbedClientConfigForPaint(
      undefined,
      "https://unknown.example",
    );
    expect(painted).toEqual(DEFAULT_EMBED_TENANT_CONFIG);
    const denied = resolveEmbedChatTenant(
      embedRequest({ "x-embed-host": "https://unknown.example" }),
    );
    expect(denied).toBeInstanceOf(Response);
  });
});
