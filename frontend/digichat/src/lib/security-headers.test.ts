import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DIGICHAT_APP_CSP,
  DIGICHAT_APP_SECURITY_HEADERS,
  DIGICHAT_EMBED_SECURITY_HEADERS,
  embedFrameAncestors,
  embedFrameAncestorsCsp,
} from "./security-headers";
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";

describe("security-headers", () => {
  it("denies framing on the main app CSP", () => {
    expect(DIGICHAT_APP_CSP).toContain("frame-ancestors 'none'");
    expect(DIGICHAT_APP_CSP).toContain("default-src 'self'");
  });

  it("allows only marketing origins on embed frame-ancestors", () => {
    const csp = embedFrameAncestorsCsp();
    const firstPartyOrigins = ["'self'", "https://digithings.ai", "https://digiquant.io"];
    for (const origin of firstPartyOrigins) {
      expect(csp).toContain(origin);
    }
    expect(csp).not.toContain("'none'");
  });

  it("exports app and embed header sets", () => {
    expect(DIGICHAT_APP_SECURITY_HEADERS.some((h) => h.key === "X-Frame-Options")).toBe(
      true,
    );
    expect(
      DIGICHAT_EMBED_SECURITY_HEADERS.find((h) => h.key === "Content-Security-Policy")
        ?.value,
    ).toBe(embedFrameAncestorsCsp());
  });
});

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
          token: "datatapstream-secret",
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

describe("DIGICHAT_EMBED_HOSTS (build-time CSP without the secret registry)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetEmbedTenantRegistryForTests();
  });

  it("derives frame-ancestors from DIGICHAT_EMBED_HOSTS without DIGICHAT_EMBED_TENANTS set", () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "dev.datatapstream.com, dev.datatap.stream");
    resetEmbedTenantRegistryForTests();
    const list = embedFrameAncestors();
    expect(list).toContain("https://dev.datatapstream.com");
    expect(list).toContain("https://dev.datatap.stream");
  });

  it("prefers DIGICHAT_EMBED_HOSTS over the registry when both are set", () => {
    vi.stubEnv("DIGICHAT_EMBED_HOSTS", "hosts-var.example.com");
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "registry-var.example.com": {
          slug: "registryvar",
          backend: { type: "external-relay", url: "https://relay.example.com/api/x" },
          gateMode: "ungated",
          token: "secret",
        },
      })
    );
    resetEmbedTenantRegistryForTests();
    const list = embedFrameAncestors();
    expect(list).toContain("https://hosts-var.example.com");
    expect(list).not.toContain("https://registry-var.example.com");
  });

  it("falls back to the registry when DIGICHAT_EMBED_HOSTS is unset", () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "registry-var.example.com": {
          slug: "registryvar",
          backend: { type: "external-relay", url: "https://relay.example.com/api/x" },
          gateMode: "ungated",
          token: "secret",
        },
      })
    );
    resetEmbedTenantRegistryForTests();
    const list = embedFrameAncestors();
    expect(list).toContain("https://registry-var.example.com");
  });
});
