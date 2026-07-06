import { describe, it, expect, afterEach, vi } from "vitest";
import {
  parseEmbedTenants,
  normalizeEmbedHost,
  resolveEmbedTenantByHost,
  resetEmbedTenantRegistryForTests,
} from "./embed-tenants";

const VALID = JSON.stringify({
  "datatapstream.com": {
    slug: "datatapstream",
    aliases: ["www.datatapstream.com", "dev.datatap.stream"],
    backend: {
      type: "external-relay",
      url: "https://datatap-digichat-relay.azurewebsites.net/api/digichat",
    },
    gateMode: "ungated",
    theme: "light",
    accent: { color: "#b5562b", foreground: "#fff7f2" },
    attribution: true,
    token: "datatapstream-secret",
  },
});

afterEach(() => {
  vi.unstubAllEnvs();
  resetEmbedTenantRegistryForTests();
});

describe("normalizeEmbedHost", () => {
  it("extracts hostnames from origins, URLs, and bare hosts", () => {
    expect(normalizeEmbedHost("https://Dev.DataTapStream.com")).toBe("dev.datatapstream.com");
    expect(normalizeEmbedHost("https://dev.datatapstream.com/chat/page")).toBe("dev.datatapstream.com");
    expect(normalizeEmbedHost("datatapstream.com")).toBe("datatapstream.com");
    expect(normalizeEmbedHost("localhost:8080")).toBe("localhost");
    expect(normalizeEmbedHost("")).toBeNull();
    expect(normalizeEmbedHost(null)).toBeNull();
  });
});

describe("parseEmbedTenants", () => {
  it("returns an empty registry for unset or blank env", () => {
    expect(parseEmbedTenants(undefined).size).toBe(0);
    expect(parseEmbedTenants("  ").size).toBe(0);
  });

  it("parses a valid registry and indexes aliases", () => {
    const reg = parseEmbedTenants(VALID);
    expect(reg.get("datatapstream.com")?.slug).toBe("datatapstream");
    expect(reg.get("www.datatapstream.com")?.slug).toBe("datatapstream");
    expect(reg.get("dev.datatap.stream")?.backend).toEqual({
      type: "external-relay",
      url: "https://datatap-digichat-relay.azurewebsites.net/api/digichat",
    });
    expect(reg.get("datatapstream.com")?.theme).toBe("light");
  });

  it("defaults theme to dark and attribution to false when omitted", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "turn_limited",
          token: "shh",
        },
      })
    );
    expect(reg.get("example.com")?.theme).toBe("dark");
    expect(reg.get("example.com")?.attribution).toBe(false);
  });

  it("throws on malformed JSON", () => {
    expect(() => parseEmbedTenants("{nope")).toThrow(/not valid JSON/);
  });

  it("throws on a non-https relay URL", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "external-relay", url: "http://insecure.example.com/x" },
            gateMode: "ungated",
          },
        })
      )
    ).toThrow(/https/);
  });

  it("throws on invalid accent hex", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            accent: { color: "red", foreground: "#ffffff" },
          },
        })
      )
    ).toThrow(/hex/);
  });

  it("throws on a duplicate host/alias", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "a.example.com": {
            slug: "a",
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            token: "a-secret",
          },
          "b.example.com": {
            slug: "b",
            aliases: ["a.example.com"],
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            token: "b-secret",
          },
        })
      )
    ).toThrow(/duplicate/);
  });

  it("throws when a tenant entry is missing a token", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": { slug: "example", backend: { type: "digigraph" }, gateMode: "turn_limited" },
        })
      )
    ).toThrow(/token/);
  });

  it("throws when a tenant entry's token is an empty string", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            token: "   ",
          },
        })
      )
    ).toThrow(/token/);
  });

  it("throws on an invalid gateMode or theme", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": { slug: "example", backend: { type: "digigraph" }, gateMode: "open" },
        })
      )
    ).toThrow(/gateMode/);
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            theme: "midnight",
          },
        })
      )
    ).toThrow(/theme/);
  });
});

describe("resolveEmbedTenantByHost", () => {
  it("resolves via the env-backed registry, including origins and aliases", () => {
    vi.stubEnv("DIGICHAT_EMBED_TENANTS", VALID);
    resetEmbedTenantRegistryForTests();
    expect(resolveEmbedTenantByHost("https://www.datatapstream.com")?.slug).toBe("datatapstream");
    expect(resolveEmbedTenantByHost("https://unknown.example.com")).toBeNull();
    expect(resolveEmbedTenantByHost(null)).toBeNull();
  });
});
