import { describe, it, expect, afterEach, vi } from "vitest";
import { GET } from "./route";
import { DATATAPSTREAM_SUGGESTION_POOL } from "@/lib/embed-suggestion-pools";
import { resetEmbedTenantRegistryForTests } from "@/lib/embed-tenants";
import { resetDigichatConfigForTests } from "@/lib/deploy-config/loader";
import { DEFAULT_EMBED_TENANT_CONFIG } from "@/lib/embed-client-config";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
  resetDigichatConfigForTests();
});

const REGISTRY = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    backend: {
      type: "foundry",
      projectEndpoint: "https://example.services.ai.azure.com",
      agentName: "agent",
    },
    gateMode: "ungated",
    theme: "light",
    accent: { color: "#b5562b", foreground: "#fff7f2" },
    attribution: true,
    token: "datatapstream-secret",
  },
});

describe("GET /api/embed/tenant-config", () => {
  it("returns the client-safe config for a registered host with a valid token — never the backend", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const res = await GET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: {
          "x-embed-host": "https://datatapstream.com",
          "x-embed-token": "datatapstream-secret",
        },
      })
    );
    expect(res.status).toBe(200);
    expect(res.headers.get("cache-control")).toBe("no-store");
    const body = await res.json();
    expect(body).toEqual({
      slug: "datatapstream",
      gateMode: "ungated",
      theme: "light",
      skin: "base",
      accent: { color: "#b5562b", foreground: "#fff7f2" },
      attribution: true,
      suggestions: [...DATATAPSTREAM_SUGGESTION_POOL],
      showByok: false,
      layout: "embed",
      showLanguageSelector: true,
      webSearch: false,
      attachments: false,
      backendType: "foundry",
      mcp: { servers: [], allowUserServers: false, allowAddForm: false },
      models: { available: [] },
    });
    expect(JSON.stringify(body)).not.toContain("example.services.ai.azure.com");
    expect(JSON.stringify(body)).not.toContain("datatapstream-secret");
  });

  it("returns baseline defaults for a registered host when the token is missing (#1339)", async () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
    resetEmbedTenantRegistryForTests();
    const res = await GET(
      new Request("http://127.0.0.1/api/embed/tenant-config", {
        headers: { "x-embed-host": "https://datatapstream.com" },
      })
    );
    const body = await res.json();
    expect(body).toEqual(DEFAULT_EMBED_TENANT_CONFIG);
  });

  it("returns baseline defaults for unknown hosts", async () => {
    const res = await GET(new Request("http://127.0.0.1/api/embed/tenant-config"));
    expect(await res.json()).toEqual(DEFAULT_EMBED_TENANT_CONFIG);
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
    expect(body.skin).toBe("digichat");
  });

  it("projects showByok, layout to the client body", async () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          showByok: true,
          layout: "page",
          llmAccess: "free_then_byok",
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
    expect(body.layout).toBe("page");
    expect(body.llmAccess).toBe("free_then_byok");
  });
});
