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
      type: "foundry",
      projectEndpoint: "https://example.services.ai.azure.com",
      agentName: "agent",
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

  it("parses digigraph corpus routing fields for OCC-style tenants", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: {
            type: "digigraph",
            digisearchIndex: "occ_help",
            vaultPathPrefix: "/clients/online-compliance-center/",
          },
          gateMode: "ungated",
          token: "occ-tok",
        },
      })
    );
    expect(reg.get("occ.digithings.ai")?.backend).toEqual({
      type: "digigraph",
      digisearchIndex: "occ_help",
      vaultPathPrefix: "clients/online-compliance-center",
    });
  });

  it("rejects empty digigraph digisearchIndex", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "occ.digithings.ai": {
            slug: "occ",
            backend: { type: "digigraph", digisearchIndex: "  " },
            gateMode: "ungated",
            token: "tok",
          },
        })
      )
    ).toThrow(/digisearchIndex/);
  });

  it("throws on malformed JSON", () => {
    expect(() => parseEmbedTenants("{nope")).toThrow(/not valid JSON/);
  });

  it("rejects removed backend types (external-relay, digivault)", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "external-relay", url: "https://relay.example.com/x" },
            gateMode: "ungated",
            token: "tok",
          },
        })
      )
    ).toThrow(/digigraph.*foundry|foundry.*digigraph/);
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            token: "tok",
            gateMode: "ungated",
            backend: {
              type: "digivault",
              supabaseUrlEnv: "CORE_SUPABASE_URL",
              supabaseAnonKeyEnv: "CORE_SUPABASE_ANON_KEY",
              openRouterKeyEnv: "OPENROUTER_API_KEY",
            },
          },
        })
      )
    ).toThrow(/digigraph.*foundry|foundry.*digigraph/);
  });

  it("parses a foundry backend", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: {
            type: "foundry",
            projectEndpoint: "https://dg-agentic-ai.ai.azure.com/api/projects/dg-agentic-search",
            agentName: "digichat",
          },
          gateMode: "turn_limited",
          token: "shh",
        },
      })
    );
    expect(reg.get("example.com")?.backend).toEqual({
      type: "foundry",
      projectEndpoint: "https://dg-agentic-ai.ai.azure.com/api/projects/dg-agentic-search",
      agentName: "digichat",
    });
  });

  it("throws on a non-https foundry projectEndpoint", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: {
              type: "foundry",
              projectEndpoint: "http://insecure.example.com/api/projects/x",
              agentName: "digichat",
            },
            gateMode: "ungated",
            token: "tok",
          },
        })
      )
    ).toThrow(/https/);
  });

  it("throws on a foundry backend missing agentName", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "foundry", projectEndpoint: "https://dg-agentic-ai.ai.azure.com/api/projects/x" },
            gateMode: "ungated",
            token: "tok",
          },
        })
      )
    ).toThrow(/agentName/);
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
            token: "tok",
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

  it("accepts trial_form as a gate mode", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "trial_form",
          token: "t",
        },
      }),
    );
    expect(reg.get("example.com")?.gateMode).toBe("trial_form");
  });

  it("throws on an invalid gateMode or theme", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": { slug: "example", backend: { type: "digigraph" }, gateMode: "open", token: "t" },
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
            token: "t",
          },
        })
      )
    ).toThrow(/theme/);
  });

  it("throws when lockedContact is not a string", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "turn_limited",
            token: "t",
            lockedContact: 123,
          },
        })
      )
    ).toThrow(/lockedContact/);
  });

  it("parses a valid lockedContact", () => {
    vi.stubEnv(
      "DIGICHAT_EMBED_TENANTS",
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "turn_limited",
          token: "t",
          lockedContact: "info@example.com",
        },
      })
    );
    resetEmbedTenantRegistryForTests();
    expect(resolveEmbedTenantByHost("example.com")?.lockedContact).toBe("info@example.com");
  });

  describe("activityDetail", () => {
    const entry = (extra: Record<string, unknown> = {}) =>
      JSON.stringify({
        "tenant.example": {
          slug: "tenant",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "tok",
          ...extra,
        },
      });

    // Conservative by construction: a tenant nobody configured must not stream
    // retrieved document titles to anonymous visitors.
    it("defaults to labels when unspecified", () => {
      const cfg = parseEmbedTenants(entry()).get("tenant.example")!;
      expect(cfg.activityDetail).toBe("labels");
    });

    it("accepts each valid level", () => {
      for (const level of ["off", "labels", "full"] as const) {
        const cfg = parseEmbedTenants(entry({ activityDetail: level })).get("tenant.example")!;
        expect(cfg.activityDetail).toBe(level);
      }
    });

    it("rejects an unknown level at startup rather than silently downgrading", () => {
      expect(() => parseEmbedTenants(entry({ activityDetail: "verbose" }))).toThrow(
        /activityDetail must be/
      );
    });
  });

  it("parses showByok, layout independent of gateMode", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          showByok: true,
          layout: "page",
          activityDetail: "full",
          token: "t",
        },
      }),
    );
    const t = reg.get("digithings.ai")!;
    expect(t.gateMode).toBe("ungated");
    expect(t.showByok).toBe(true);
    expect(t.layout).toBe("page");
  });

  it("parses llmAccess free_then_byok for digithings-style tenants", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          showByok: true,
          llmAccess: "free_then_byok",
          token: "t",
        },
      }),
    );
    expect(reg.get("digithings.ai")!.llmAccess).toBe("free_then_byok");
  });

  it("parses llmAccess backend_only for foundry / DataTap-style tenants", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "datatapstream.com": {
          slug: "datatap",
          backend: {
            type: "foundry",
            projectEndpoint: "https://example.services.ai.azure.com",
            agentName: "agent",
          },
          gateMode: "trial_form",
          showByok: false,
          llmAccess: "backend_only",
          token: "t",
        },
      }),
    );
    const t = reg.get("datatapstream.com")!;
    expect(t.llmAccess).toBe("backend_only");
    expect(t.showByok).toBe(false);
  });

  it("rejects invalid llmAccess", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "ex",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            llmAccess: "paid_only",
            token: "t",
          },
        }),
      ),
    ).toThrow(/llmAccess must be/);
  });

  it("rejects invalid layout", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "ex",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            layout: "fullscreen",
            token: "t",
          },
        }),
      ),
    ).toThrow(/layout/);
  });

  it("omits UI flags when absent (callers default)", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "ex",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
        },
      }),
    );
    const t = reg.get("example.com")!;
    expect(t.showByok).toBeUndefined();
    expect(t.layout).toBeUndefined();
  });

  it("accepts showLanguageSelector: false", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          showLanguageSelector: false,
        },
      }),
    );
    expect(registry.get("example.com")?.showLanguageSelector).toBe(false);
  });

  it("rejects a non-boolean showLanguageSelector", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            token: "t",
            showLanguageSelector: "yes",
          },
        }),
      ),
    ).toThrow(/showLanguageSelector must be a boolean/);
  });

  it("leaves showLanguageSelector undefined when unset", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
        },
      }),
    );
    expect(registry.get("example.com")?.showLanguageSelector).toBeUndefined();
  });

  it("accepts a gate block with an https consumeUrl", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "dev.datatap.stream": {
          slug: "datatap",
          backend: { type: "digigraph" },
          gateMode: "trial_form",
          token: "t",
          gate: { consumeUrl: "https://api.test/consume" },
        },
      }),
    );
    expect(reg.get("dev.datatap.stream")?.gate?.consumeUrl).toBe("https://api.test/consume");
  });

  it("rejects a gate whose consumeUrl is not https", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "dev.datatap.stream": {
            slug: "datatap",
            backend: { type: "digigraph" },
            gateMode: "trial_form",
            token: "t",
            gate: { consumeUrl: "http://api.test/consume" },
          },
        }),
      ),
    ).toThrow(/consumeUrl/);
  });

  it("leaves gate undefined when absent", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "dev.datatap.stream": {
          slug: "datatap",
          backend: { type: "digigraph" },
          gateMode: "trial_form",
          token: "t",
        },
      }),
    );
    expect(reg.get("dev.datatap.stream")?.gate).toBeUndefined();
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
