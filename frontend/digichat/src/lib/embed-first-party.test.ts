import { afterEach, describe, it, expect, vi } from "vitest";
import {
  isFirstPartyEmbedHost,
  FIRST_PARTY_EMBED_HOSTS,
  DEV_LOOPBACK_EMBED_HOSTS,
  isDigichatDevelopment,
} from "./embed-first-party";
import { resetEmbedTenantRegistryForTests } from "./embed-tenants";

const LOCALHOST_REGISTRY = JSON.stringify({
  localhost: {
    slug: "digithings",
    aliases: ["127.0.0.1", "[::1]"],
    backend: { type: "digigraph" },
    gateMode: "ungated",
    activityDetail: "full",
    token: "local-dev-token",
  },
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("isFirstPartyEmbedHost", () => {
  it("allows digithings.ai and www only", () => {
    expect(FIRST_PARTY_EMBED_HOSTS.has("digithings.ai")).toBe(true);
    expect(FIRST_PARTY_EMBED_HOSTS.has("www.digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://digithings.ai")).toBe(true);
    expect(isFirstPartyEmbedHost("https://www.digithings.ai/chat")).toBe(true);
    expect(isFirstPartyEmbedHost("digithings.ai")).toBe(true);
  });

  it("rejects customer and preview hosts", () => {
    expect(isFirstPartyEmbedHost("https://datatapstream.com")).toBe(false);
    expect(isFirstPartyEmbedHost("https://digithings-ai.pages.dev")).toBe(false);
    expect(isFirstPartyEmbedHost(null)).toBe(false);
  });

  it("allows registered loopback hosts in development only", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", LOCALHOST_REGISTRY);
    resetEmbedTenantRegistryForTests();
    expect(isDigichatDevelopment()).toBe(true);
    for (const host of DEV_LOOPBACK_EMBED_HOSTS) {
      const url = host.startsWith("[") ? `http://${host}:3000` : `http://${host}:3000`;
      expect(isFirstPartyEmbedHost(url)).toBe(true);
    }
  });

  it("rejects unregistered loopback hosts even in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(isFirstPartyEmbedHost("http://localhost:3000")).toBe(false);
    expect(isFirstPartyEmbedHost("http://127.0.0.1:3000")).toBe(false);
  });

  it("rejects registered loopback hosts in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", LOCALHOST_REGISTRY);
    resetEmbedTenantRegistryForTests();
    expect(isFirstPartyEmbedHost("http://localhost:3000")).toBe(false);
  });
});
