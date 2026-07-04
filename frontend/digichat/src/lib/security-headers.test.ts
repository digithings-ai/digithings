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
