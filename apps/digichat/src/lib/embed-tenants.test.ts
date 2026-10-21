import { describe, it, expect, afterEach, vi } from "vitest";
import {
  parseEmbedTenants,
  normalizeEmbedHost,
  resolveEmbedTenantByHost,
  resetEmbedTenantRegistryForTests,
  DIGIQUANT_DASHBOARD_EMBED_HOST,
  isDigiquantDashboardTenantConfig,
  isPlanTierSatisfied,
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
  it("refuses a palette: an embed owns its theme, so the key could never paint", () => {
    const base = JSON.parse(VALID) as Record<string, Record<string, unknown>>;
    const [host] = Object.keys(base);
    base[host].palette = "dracula";
    expect(() => parseEmbedTenants(JSON.stringify(base))).toThrow(/palette is not supported on embeds/);
  });

  it("refuses bad values for the chrome seed keys", () => {
    const cases: Array<[string, unknown, RegExp]> = [
      ["density", "dense", /density must be/],
      ["effort", "max", /effort must be/],
      ["toolbar", "no", /toolbar must be a boolean/],
      ["scrollbars", "never", /scrollbars must be/],
      ["searchEngine", "bing", /searchEngine is not a known engine/],
    ];
    for (const [key, value, message] of cases) {
      const base = JSON.parse(VALID) as Record<string, Record<string, unknown>>;
      const [host] = Object.keys(base);
      base[host][key] = value;
      expect(() => parseEmbedTenants(JSON.stringify(base)), key).toThrow(message);
    }
  });

  it("keeps valid chrome seed keys", () => {
    const base = JSON.parse(VALID) as Record<string, Record<string, unknown>>;
    const [host] = Object.keys(base);
    Object.assign(base[host], {
      density: "airy",
      effort: "high",
      toolbar: false,
      scrollbars: "auto",
      searchEngine: " Exa ",
    });
    const t = parseEmbedTenants(JSON.stringify(base)).get(host);
    expect(t).toMatchObject({
      density: "airy",
      effort: "high",
      toolbar: false,
      scrollbars: "auto",
      searchEngine: "exa",
    });
  });

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
    expect(reg.get("datatapstream.com")?.skin).toBe("base");
  });

  it("keeps operator MCP servers from the env registry", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: {
            type: "digigraph",
            digisearchIndex: "occ_help",
            vaultPathPrefix: "clients/online-compliance-center",
          },
          gateMode: "ungated",
          token: "first-party-unused",
          mcp: {
            servers: [
              {
                id: "zammad",
                url: "http://zammad-mcp:8770/mcp",
                label: "Zammad tickets",
                default: true,
                token: "edge-test-token",
                authHeader: "x-digi-mcp-key",
                allowedTools: ["search_tickets", "get_ticket"],
                mutatingTools: [],
              },
              {
                id: "digivault",
                url: "http://digivault-mcp:8769/mcp",
                label: "Knowledge vault",
                default: true,
                setup: { path_prefix: "clients/online-compliance-center" },
              },
            ],
            allowUserServers: false,
            allowAddForm: false,
          },
        },
      }),
    );
    expect(reg.get("occ.digithings.ai")?.mcp).toEqual({
      servers: [
        {
          id: "zammad",
          url: "http://zammad-mcp:8770/mcp",
          label: "Zammad tickets",
          default: true,
          token: "edge-test-token",
          authHeader: "x-digi-mcp-key",
          allowedTools: ["search_tickets", "get_ticket"],
          mutatingTools: [],
        },
        {
          id: "digivault",
          url: "http://digivault-mcp:8769/mcp",
          label: "Knowledge vault",
          default: true,
          setup: { path_prefix: "clients/online-compliance-center" },
        },
      ],
      allowUserServers: false,
      allowAddForm: false,
    });
  });

  it("keeps an MCP tool allowlist on an operator server row (DIG-284)", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp: {
            servers: [
              {
                id: "zammad",
                url: "http://zammad-mcp:8770/mcp",
                // RAW MCP names — bare, never zammad_-prefixed.
                allowedTools: ["list_tickets", "get_ticket"],
              },
              {
                id: "digivault",
                url: "http://digivault-mcp:8769/mcp",
                allowedTools: ["search_vault"],
                mutatingTools: [],
              },
            ],
          },
        },
      }),
    );
    const servers = reg.get("occ.digithings.ai")?.mcp?.servers;
    // Exact values, not truthiness: a broken parser that dropped the key would
    // still leave two server rows in place.
    expect(servers?.[0].allowedTools).toEqual(["list_tickets", "get_ticket"]);
    expect(servers?.[1].allowedTools).toEqual(["search_vault"]);
    // Explicit [] is preserved — "nothing on this row mutates".
    expect(servers?.[1].mutatingTools).toEqual([]);
    // Absent keys stay absent, on the row and on the parsed object.
    expect(servers?.[0]).not.toHaveProperty("mutatingTools");
    expect(servers?.[0].mutatingTools).toBeUndefined();
  });

  it("drops an out-of-bounds MCP tool allowlist whole, never truncating it", () => {
    const withAllowed = (allowedTools: unknown) =>
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp: { servers: [{ id: "zammad", url: "http://zammad-mcp:8770/mcp", allowedTools }] },
        },
      });
    const firstServer = (allowedTools: unknown) =>
      parseEmbedTenants(withAllowed(allowedTools)).get("occ.digithings.ai")?.mcp?.servers[0];

    // 257 entries (bound 256): dropped whole, NOT trimmed to 256.
    const tooMany = Array.from({ length: 257 }, (_, i) => `tool_${i}`);
    const many = firstServer(tooMany);
    expect(many).not.toHaveProperty("allowedTools");
    expect(many?.allowedTools).toBeUndefined();

    // A single 65-char entry (bound 64): the whole list goes, not just that name.
    const tooLong = ["a".repeat(65)];
    const long = firstServer(tooLong);
    expect(long).not.toHaveProperty("allowedTools");
    expect(long?.allowedTools).toBeUndefined();

    // A non-string entry also fails closed.
    const nonString = firstServer(["list_tickets", 7]);
    expect(nonString).not.toHaveProperty("allowedTools");
    expect(nonString?.allowedTools).toBeUndefined();

    // Control: a list exactly at both bounds survives intact and in order.
    const atBound = Array.from({ length: 256 }, (_, i) => `t${i}`.padEnd(64, "x"));
    const ok = firstServer(atBound);
    expect(ok?.allowedTools).toHaveLength(256);
    expect(ok?.allowedTools?.[255]).toBe(atBound[255]);
  });

  it("treats an empty allowedTools as absent but preserves an empty mutatingTools", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp: {
            servers: [
              { id: "zammad", url: "http://zammad-mcp:8770/mcp", allowedTools: [], mutatingTools: [] },
            ],
          },
        },
      }),
    );
    const server = reg.get("occ.digithings.ai")?.mcp?.servers[0];
    expect(server).not.toHaveProperty("allowedTools");
    expect(server?.allowedTools).toBeUndefined();
    expect(server?.mutatingTools).toEqual([]);
  });

  it("rejects a non-array MCP tool allowlist", () => {
    const withMcp = (mcp: unknown) =>
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp,
        },
      });
    expect(() =>
      parseEmbedTenants(
        withMcp({ servers: [{ id: "zammad", url: "http://zammad-mcp:8770/mcp", allowedTools: "list_tickets" }] }),
      ),
    ).toThrow(/mcp\.servers\[0\]\.allowedTools must be an array/);
    expect(() =>
      parseEmbedTenants(
        withMcp({ servers: [{ id: "zammad", url: "http://zammad-mcp:8770/mcp", mutatingTools: {} }] }),
      ),
    ).toThrow(/mcp\.servers\[0\]\.mutatingTools must be an array/);
  });

  it("rejects malformed MCP setup values", () => {
    const withMcp = (mcp: unknown) =>
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp,
        },
      });
    expect(() =>
      parseEmbedTenants(
        withMcp({ servers: [{ id: "v", url: "http://v.test/mcp", setup: ["x"] }] }),
      ),
    ).toThrow(/mcp\.servers\[0\]\.setup must be an object/);
    expect(() =>
      parseEmbedTenants(
        withMcp({ servers: [{ id: "v", url: "http://v.test/mcp", setup: { n: 1 } }] }),
      ),
    ).toThrow(/mcp\.servers\[0\]\.setup\.n must be a string/);
    // An empty map is legal and simply omitted (no setup to forward).
    const reg = parseEmbedTenants(
      withMcp({ servers: [{ id: "v", url: "http://v.test/mcp", setup: {} }] }),
    );
    expect(reg.get("occ.digithings.ai")?.mcp?.servers[0]).toEqual({
      id: "v",
      url: "http://v.test/mcp",
    });
  });

  it("rejects malformed MCP server entries", () => {
    const withMcp = (mcp: unknown) =>
      JSON.stringify({
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          mcp,
        },
      });
    expect(() =>
      parseEmbedTenants(withMcp({ servers: [{ id: "BAD ID", url: "http://x.test/mcp" }] })),
    ).toThrow(/mcp\.servers\[0\]\.id/);
    expect(() => parseEmbedTenants(withMcp({ servers: [{ id: "zammad", url: "  " }] }))).toThrow(
      /mcp\.servers\[0\]\.url/,
    );
  });

  it("defaults unset skin to digichat for first-party hosts, base otherwise", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          aliases: ["www.digithings.ai"],
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
        },
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "occ-t",
        },
        "client.example": {
          slug: "acme",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "c",
        },
      }),
    );
    expect(reg.get("digithings.ai")?.skin).toBe("digichat");
    expect(reg.get("www.digithings.ai")?.skin).toBe("digichat");
    expect(reg.get("occ.digithings.ai")?.skin).toBe("digichat");
    expect(reg.get("client.example")?.skin).toBe("base");
  });

  it("keeps an explicit first-party skin, including catalog base", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          skin: "base",
        },
      }),
    );
    expect(reg.get("digithings.ai")?.skin).toBe("base");
  });

  it("accepts an official thread skin", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "shh",
          skin: "perplexity",
        },
      }),
    );
    expect(reg.get("example.com")?.skin).toBe("perplexity");
  });

  it("fails closed on unknown thread skin", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            token: "shh",
            skin: "ink",
          },
        }),
      ),
    ).toThrow(/skin/);
  });

  it("defaults theme to dark and attribution to true when omitted", () => {
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
    expect(reg.get("example.com")?.attribution).toBe(true);
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

  it("accepts view/thinking modes and rejects unknown values", () => {
    const entry = (keys: Record<string, unknown>) =>
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "turn_limited",
          token: "t",
          ...keys,
        },
      });
    const reg = parseEmbedTenants(entry({ view: "verbose", thinking: "open" }));
    expect(reg.get("example.com")?.view).toBe("verbose");
    expect(reg.get("example.com")?.thinking).toBe("open");
    expect(() => parseEmbedTenants(entry({ view: "expanded" }))).toThrow(/view/);
    expect(() => parseEmbedTenants(entry({ thinking: "yes" }))).toThrow(/thinking/);
  });

  it("folds a tenant that still carries the retired hidden view", () => {
    // `hidden` described the one-line trace; the folded chain shows that line
    // as its header now, so the tenant means the titles only.
    const reg = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "turn_limited",
          token: "t",
          view: "hidden",
        },
      }),
    );
    expect(reg.get("example.com")?.view).toBe("quiet");
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
    expect(t.skin).toBe("digichat");
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

  it("accepts showContextMeter and rejects a non-boolean", () => {
    const on = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          showContextMeter: true,
        },
      }),
    );
    expect(on.get("example.com")?.showContextMeter).toBe(true);
    const off = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          showContextMeter: false,
        },
      }),
    );
    expect(off.get("example.com")?.showContextMeter).toBe(false);
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            token: "t",
            showContextMeter: "yes",
          },
        }),
      ),
    ).toThrow(/showContextMeter must be a boolean/);
    const unset = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
        },
      }),
    );
    expect(unset.get("example.com")?.showContextMeter).toBeUndefined();
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

  it("accepts pageContext off/silent/visible and leaves it undefined when unset", () => {
    const registry = parseEmbedTenants(
      JSON.stringify({
        "example.com": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
          pageContext: "silent",
        },
      }),
    );
    expect(registry.get("example.com")?.pageContext).toBe("silent");
    const unset = parseEmbedTenants(
      JSON.stringify({
        "example.org": {
          slug: "example",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "t",
        },
      }),
    );
    expect(unset.get("example.org")?.pageContext).toBeUndefined();
  });

  it("rejects an unknown pageContext", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          "example.com": {
            slug: "example",
            backend: { type: "digigraph" },
            gateMode: "ungated",
            token: "t",
            pageContext: "hidden",
          },
        }),
      ),
    ).toThrow(/pageContext must be "off", "silent", or "visible"/);
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

describe("digiquant dashboard tenant contract (#3662)", () => {
  const dashboardEntry = {
    slug: "digiquant-dashboard",
    aliases: ["www.digiquant.io"],
    backend: { type: "digigraph" },
    gateMode: "ungated",
    llmAccess: "operator",
    showByok: true,
    requiredPlanTier: "desk",
    token: "dash-secret",
  };

  it("accepts the canonical digiquant.io entry: ungated + operator + showByok true, no gate", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({ [DIGIQUANT_DASHBOARD_EMBED_HOST]: dashboardEntry }),
    );
    const cfg = reg.get("digiquant.io");
    expect(cfg?.slug).toBe("digiquant-dashboard");
    // www alias rides the same entry.
    expect(reg.get("www.digiquant.io")).toBe(cfg);
    expect(isDigiquantDashboardTenantConfig(cfg!)).toBe(true);
  });

  it("showByok is true on digiquant.io tenant config", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({ [DIGIQUANT_DASHBOARD_EMBED_HOST]: dashboardEntry }),
    );
    const cfg = reg.get("digiquant.io")!;
    expect(cfg.showByok).toBe(true);
  });

  it("rejects turn_limited: Desk+ must never be capped at free-3", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          ...dashboardEntry,
          gateMode: "turn_limited",
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects trial_form: baseline gets an upgrade CTA, not free-3 then lock", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          ...dashboardEntry,
          gateMode: "trial_form",
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects free_then_byok: dashboard spend rides operator keys, not visitor BYOK", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          ...dashboardEntry,
          llmAccess: "free_then_byok",
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects a gate.consumeUrl: no per-message server quota for entitled users", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          ...dashboardEntry,
          gate: { consumeUrl: "https://api.test/consume" },
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects a missing llmAccess: the contract must be explicit, not defaulted", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          slug: "digiquant-dashboard",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          token: "dash-secret",
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects when requiredPlanTier is absent — fail closed (#3662)", () => {
    const reg = parseEmbedTenants(
      JSON.stringify({
        [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
          slug: "digiquant-dashboard",
          backend: { type: "digigraph" },
          gateMode: "ungated",
          llmAccess: "operator",
          showByok: true,
          token: "dash-secret",
        },
      }),
    );
    expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(false);
  });

  it("rejects when requiredPlanTier is free or brief — baseline must not bypass Desk+", () => {
    for (const tier of ["free", "brief"]) {
      expect(() =>
        parseEmbedTenants(
          JSON.stringify({
            [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
              ...dashboardEntry,
              requiredPlanTier: tier,
            },
          }),
        ),
      ).toThrow(/requiredPlanTier must be/);
    }
  });

  it("accepts requiredPlanTier desk, studio, enterprise", () => {
    for (const tier of ["desk", "studio", "enterprise"]) {
      const reg = parseEmbedTenants(
        JSON.stringify({
          [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
            ...dashboardEntry,
            requiredPlanTier: tier,
          },
        }),
      );
      expect(isDigiquantDashboardTenantConfig(reg.get("digiquant.io")!)).toBe(true);
    }
  });

  it("rejects an invalid requiredPlanTier value", () => {
    expect(() =>
      parseEmbedTenants(
        JSON.stringify({
          [DIGIQUANT_DASHBOARD_EMBED_HOST]: {
            ...dashboardEntry,
            requiredPlanTier: "premium",
          },
        }),
      ),
    ).toThrow(/requiredPlanTier must be/);
  });
});

describe("isPlanTierSatisfied", () => {
  const deskCfg = { requiredPlanTier: "desk" as const } as import("./embed-tenants").EmbedTenantConfig;

  it("returns true when no requiredPlanTier is set", () => {
    expect(isPlanTierSatisfied(null, null)).toBe(true);
    expect(isPlanTierSatisfied({} as never, "free")).toBe(true);
  });

  it("denies when callerTier is absent", () => {
    expect(isPlanTierSatisfied(deskCfg, null)).toBe(false);
    expect(isPlanTierSatisfied(deskCfg, undefined)).toBe(false);
  });

  it("denies free and brief for desk+ requirement", () => {
    expect(isPlanTierSatisfied(deskCfg, "free")).toBe(false);
    expect(isPlanTierSatisfied(deskCfg, "brief")).toBe(false);
  });

  it("allows desk, studio, enterprise for desk+ requirement", () => {
    expect(isPlanTierSatisfied(deskCfg, "desk")).toBe(true);
    expect(isPlanTierSatisfied(deskCfg, "studio")).toBe(true);
    expect(isPlanTierSatisfied(deskCfg, "enterprise")).toBe(true);
  });

  it("denies unknown/spoofed tier strings", () => {
    expect(isPlanTierSatisfied(deskCfg, "premium")).toBe(false);
    expect(isPlanTierSatisfied(deskCfg, "")).toBe(false);
  });
});

describe("lockSessionControls (DIG-1210)", () => {
  const entry = (lock: unknown) => ({
    "example.com": {
      slug: "example",
      backend: { type: "digigraph" as const },
      gateMode: "ungated" as const,
      token: "t",
      ...(lock === undefined ? {} : { lockSessionControls: lock }),
    },
  });

  it("parses true and keeps it out of the client projection", () => {
    const registry = parseEmbedTenants(JSON.stringify(entry(true)));
    expect(registry.get("example.com")?.lockSessionControls).toBe(true);
  });

  it("leaves the flag unset when absent or false", () => {
    expect(parseEmbedTenants(JSON.stringify(entry(undefined))).get("example.com")?.lockSessionControls).toBeUndefined();
    expect(parseEmbedTenants(JSON.stringify(entry(false))).get("example.com")?.lockSessionControls).toBeUndefined();
  });

  it("rejects a non-boolean value", () => {
    expect(() => parseEmbedTenants(JSON.stringify(entry("yes")))).toThrow(/lockSessionControls/);
  });
});
