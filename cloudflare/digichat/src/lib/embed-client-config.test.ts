import { describe, it, expect, afterEach, vi } from "vitest";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  resolveEmbedClientConfigFromParams,
  resolveEmbedHostParamOrReferer,
  toEmbedClientConfig,
} from "./embed-client-config";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "./embed-tenants";
import { BASELINE_EMBED_SUGGESTIONS } from "./baseline-embed";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

const REGISTRY = JSON.stringify({
  "dev.datatap.stream": {
    slug: "datatap-dev",
    backend: {
      type: "foundry",
      projectEndpoint: "https://example.services.ai.azure.com/api/projects/p",
      agentName: "digichat",
    },
    gateMode: "trial_form",
    theme: "light",
    accent: { color: "#b5562b", foreground: "#fff7f2" },
    attribution: true,
    activityDetail: "full",
    token: "datatap-dev-secret",
  },
  "digithings.ai": {
    slug: "digithings",
    backend: { type: "digigraph" },
    gateMode: "turn_limited",
    theme: "light",
    attribution: true,
    token: "digithings-secret",
  },
});

function withRegistry() {
  vi.stubEnv("DIGICHAT_EMBED_TENANTS", REGISTRY);
  resetEmbedTenantRegistryForTests();
}

describe("resolveEmbedClientConfigFromParams", () => {
  it("resolves the tenant's own theme when host and token match", () => {
    withRegistry();
    const cfg = resolveEmbedClientConfigFromParams(
      "datatap-dev-secret",
      "https://dev.datatap.stream",
    );
    // The whole point: a light tenant is known to be light BEFORE any client
    // fetch, so the first paint is light rather than the gated dark default.
    expect(cfg.theme).toBe("light");
    expect(cfg.slug).toBe("datatap-dev");
    expect(cfg.gateMode).toBe("trial_form");
    expect(cfg.accent).toEqual({ color: "#b5562b", foreground: "#fff7f2" });
  });

  it("agrees field-for-field with the config the API route serves for the same tenant", () => {
    withRegistry();
    const registry = parseEmbedTenants(REGISTRY);
    const viaRoute = toEmbedClientConfig(registry.get("dev.datatap.stream")!);
    const viaParams = resolveEmbedClientConfigFromParams(
      "datatap-dev-secret",
      "https://dev.datatap.stream",
    );
    // Any drift here repaints on the client's re-fetch — the exact flash this
    // server resolution exists to remove.
    expect(viaParams).toEqual(viaRoute);
  });

  it("withholds the tenant config when the token is wrong or absent (#1339)", () => {
    withRegistry();
    expect(resolveEmbedClientConfigFromParams(undefined, "https://dev.datatap.stream")).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
    expect(resolveEmbedClientConfigFromParams("guessed", "https://dev.datatap.stream")).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
  });

  it("falls back to baseline defaults for an unregistered or missing host", () => {
    withRegistry();
    expect(resolveEmbedClientConfigFromParams("datatap-dev-secret", "https://evil.example")).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
    expect(resolveEmbedClientConfigFromParams(undefined, undefined)).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
  });

  it("gives an unmatched host the restrictive default, never the tenant's BYOK/MCP/web-search flags", () => {
    withRegistry();
    const unmatched = resolveEmbedClientConfigFromParams(
      "datatap-dev-secret",
      "https://unmatched.example",
    );
    expect(unmatched.showByok).toBe(false);
    expect(unmatched.webSearch).toBe(false);
    expect(unmatched.mcp?.allowUserServers).toBe(false);
    expect(unmatched.mcp?.allowAddForm).toBe(false);
  });

  it("allows the first-party host without a token when the request origin is first-party", () => {
    withRegistry();
    const cfg = resolveEmbedClientConfigFromParams(
      undefined,
      "https://digithings.ai",
      "https://www.digithings.ai",
    );
    expect(cfg.slug).toBe("digithings");
  });

  it("withholds a first-party tenant when only the spoofable host is presented", () => {
    withRegistry();
    expect(resolveEmbedClientConfigFromParams(undefined, "https://digithings.ai")).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
  });

  it("trims whitespace from the token param before comparison (#2006)", () => {
    withRegistry();
    const cfg = resolveEmbedClientConfigFromParams(
      "datatap-dev-secret ",
      "https://dev.datatap.stream",
    );
    expect(cfg.slug).toBe("datatap-dev");
    expect(cfg.theme).toBe("light");
  });
});

describe("resolveEmbedHostParamOrReferer", () => {
  it("prefers explicit host over referer", () => {
    expect(
      resolveEmbedHostParamOrReferer("https://explicit.example", "https://parent.example/page"),
    ).toBe("https://explicit.example");
  });

  it("falls back to referer origin when host param is absent (#2006)", () => {
    expect(resolveEmbedHostParamOrReferer(undefined, "https://dev.datatap.stream/embed")).toBe(
      "https://dev.datatap.stream",
    );
  });

  it("returns undefined when both host and referer are absent", () => {
    expect(resolveEmbedHostParamOrReferer(undefined, undefined)).toBeUndefined();
  });
});

describe("toEmbedClientConfig", () => {
  it("never projects the tenant token or backend secrets into the client config", () => {
    const registry = parseEmbedTenants(REGISTRY);
    const cfg = toEmbedClientConfig(registry.get("dev.datatap.stream")!);
    const serialized = JSON.stringify(cfg);
    expect(serialized).not.toContain("datatap-dev-secret");
    expect(serialized).not.toContain("services.ai.azure.com");
    expect(cfg).not.toHaveProperty("token");
    expect(cfg).not.toHaveProperty("backend");
    expect(cfg).not.toHaveProperty("activityDetail");
    // Discriminator only — enough for Foundry-unsafe chrome (#3466).
    expect(cfg.backendType).toBe("foundry");
  });

  it("projects digigraph backendType for first-party tenants", () => {
    const registry = parseEmbedTenants(REGISTRY);
    expect(toEmbedClientConfig(registry.get("digithings.ai")!).backendType).toBe("digigraph");
  });

  it("projects digichat skin for first-party tenants when DIGICHAT_EMBED_TENANTS omits skin", () => {
    const registry = parseEmbedTenants(REGISTRY);
    expect(toEmbedClientConfig(registry.get("digithings.ai")!).skin).toBe("digichat");
    expect(toEmbedClientConfig(registry.get("dev.datatap.stream")!).skin).toBe("base");
  });

  it("projects pageContext, defaulting legacy entries to visible", () => {
    const registry = parseEmbedTenants(REGISTRY);
    expect(toEmbedClientConfig(registry.get("digithings.ai")!).pageContext).toBe("visible");
    const silent = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          attribution: false,
          token: "t",
          pageContext: "silent",
        },
      }),
    );
    expect(toEmbedClientConfig(silent.get("example.com")!).pageContext).toBe("silent");
  });

  it("carries view/thinking modes into the client config and bridge features", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          attribution: false,
          token: "t",
          view: "detailed",
          thinking: "open",
        },
      }),
    );
    const cfg = toEmbedClientConfig(registry.get("example.com")!);
    expect(cfg.view).toBe("detailed");
    expect(cfg.thinking).toBe("open");
    const projected = clientConfigFromEmbedTenant(cfg);
    expect(projected.features.view).toBe("detailed");
    expect(projected.features.thinking).toBe("open");
  });

  it("strips operator MCP URLs from the client projection", () => {
    const cfg = toEmbedClientConfig({
      slug: "datatap",
      token: "secret",
      theme: "dark",
      attribution: false,
      gateMode: "ungated",
      activityDetail: "labels",
      backend: { type: "digigraph" },
      mcp: {
        servers: [
          {
            id: "datatap",
            url: "https://mcp.datatap.example/mcp",
            label: "DataTap",
            setup: { path_prefix: "clients/acme" },
          },
        ],
        allowUserServers: false,
      },
    });
    const serialized = JSON.stringify(cfg);
    expect(serialized).not.toContain("mcp.datatap.example");
    expect(serialized).not.toContain("clients/acme");
    expect(cfg.mcp?.servers).toEqual([{ id: "datatap", label: "DataTap" }]);
  });
});

describe("toEmbedClientConfig — showLanguageSelector", () => {
  it("defaults to true when the registry entry doesn't set it", () => {
    const registry = parseEmbedTenants(REGISTRY);
    expect(toEmbedClientConfig(registry.get("digithings.ai")!).showLanguageSelector).toBe(true);
  });

  it("passes through an explicit false", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          attribution: false,
          token: "t",
          showLanguageSelector: false,
        },
      }),
    );
    expect(toEmbedClientConfig(registry.get("example.com")!).showLanguageSelector).toBe(false);
  });

  it("passes through an explicit true", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          attribution: false,
          token: "t",
          showLanguageSelector: true,
        },
      }),
    );
    expect(toEmbedClientConfig(registry.get("example.com")!).showLanguageSelector).toBe(true);
  });
});

describe("DEFAULT_EMBED_TENANT_CONFIG", () => {
  it("is the unconfigured container default, not a tenant brand", () => {
    expect(DEFAULT_EMBED_TENANT_CONFIG.showLanguageSelector).toBe(false);
    expect(DEFAULT_EMBED_TENANT_CONFIG.skin).toBe("digichat");
    expect(DEFAULT_EMBED_TENANT_CONFIG.welcome).toBe("Ask a question");
    expect(DEFAULT_EMBED_TENANT_CONFIG.welcomeBody).toEqual([
      "Ask about anything you need help with.",
    ]);
    expect(DEFAULT_EMBED_TENANT_CONFIG.attachments).toBe(true);
    expect(DEFAULT_EMBED_TENANT_CONFIG.pageContext).toBe("visible");
    expect(DEFAULT_EMBED_TENANT_CONFIG.suggestions).toEqual(BASELINE_EMBED_SUGGESTIONS);
    // Least-privilege fallback: unconfigured/unmatched hosts must not get BYOK,
    // web search, or user MCP servers by default (regression #3852).
    expect(DEFAULT_EMBED_TENANT_CONFIG.showByok).toBe(false);
    expect(DEFAULT_EMBED_TENANT_CONFIG.webSearch).toBe(false);
    expect(DEFAULT_EMBED_TENANT_CONFIG.mcp).toEqual({
      servers: [],
      allowUserServers: false,
      allowAddForm: false,
    });
  });

  it("projects baseline mcp user-server flags through the deploy-config bridge", () => {
    const projected = clientConfigFromEmbedTenant(DEFAULT_EMBED_TENANT_CONFIG);
    expect(projected.mcp.allowUserServers).toBe(false);
    expect(projected.mcp.allowAddForm).toBe(false);
    expect(projected.gate.showByok).toBe(false);
    expect(projected.gate.webSearch).toBe(false);
  });

  it("still enables BYOK, web search, and user MCP servers for an explicitly-configured tenant", () => {
    const cfg = toEmbedClientConfig({
      slug: "configured",
      theme: "dark",
      attribution: false,
      gateMode: "ungated",
      activityDetail: "labels",
      backend: { type: "digigraph" },
      showByok: true,
      webSearch: true,
      mcp: { servers: [], allowUserServers: true, allowAddForm: true },
    });
    expect(cfg.showByok).toBe(true);
    expect(cfg.webSearch).toBe(true);
    expect(cfg.mcp?.allowUserServers).toBe(true);
    expect(cfg.mcp?.allowAddForm).toBe(true);
  });
});
