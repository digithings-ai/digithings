import { describe, it, expect, afterEach, vi } from "vitest";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  resolveEmbedClientConfigFromParams,
  resolveEmbedHostParamOrReferer,
  toEmbedClientConfig,
} from "./embed-client-config";
import { parseEmbedTenants, resetEmbedTenantRegistryForTests } from "./embed-tenants";

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

  it("falls back to gated defaults for an unregistered or missing host", () => {
    withRegistry();
    expect(resolveEmbedClientConfigFromParams("datatap-dev-secret", "https://evil.example")).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
    expect(resolveEmbedClientConfigFromParams(undefined, undefined)).toEqual(
      DEFAULT_EMBED_TENANT_CONFIG,
    );
  });

  it("allows the first-party host without a token, matching the header path", () => {
    withRegistry();
    const cfg = resolveEmbedClientConfigFromParams(undefined, "https://digithings.ai");
    expect(cfg.slug).toBe("digithings");
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
  it("never projects the tenant token or backend into the client config", () => {
    const registry = parseEmbedTenants(REGISTRY);
    const cfg = toEmbedClientConfig(registry.get("dev.datatap.stream")!);
    const serialized = JSON.stringify(cfg);
    expect(serialized).not.toContain("datatap-dev-secret");
    expect(serialized).not.toContain("services.ai.azure.com");
    expect(cfg).not.toHaveProperty("token");
    expect(cfg).not.toHaveProperty("backend");
    expect(cfg).not.toHaveProperty("activityDetail");
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
  it("is false — an unresolved/gated tenant never shows it", () => {
    expect(DEFAULT_EMBED_TENANT_CONFIG.showLanguageSelector).toBe(false);
  });
});
