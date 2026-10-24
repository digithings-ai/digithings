import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { DEFAULT_CLIENT_CONFIG, toDigichatClientConfig } from "./client-projection";
import { clientConfigFromEmbedTenant } from "./embed-bridge";
import { parseDigichatConfig } from "./schema";
import type { EmbedTenantClientConfig } from "@/lib/embed-client-config";
import type { DigichatDeployment } from "./schema";

const HOUSE_DEFAULTS = resolve(__dirname, "../../../config/defaults.yaml");

function depWithCatalog(
  catalog: Array<{ id: string; default?: boolean; label?: string }>,
): DigichatDeployment {
  return {
    slug: "test",
    chrome: { mode: "embed", theme: "dark" },
    persistence: "none",
    auth: "anonymous",
    features: {},
    models: { available: [] },
    gate: { mode: "turn_limited", activityDetail: "labels" },
    backend: { type: "digigraph" },
    tools: { allowUserToggle: true, catalog },
  } as unknown as DigichatDeployment;
}

describe("mcp.servers client projection never leaks operator secrets (#3841)", () => {
  it("drops url/token/tokenEnv/authHeader, keeps only id/label/default", () => {
    const dep = {
      slug: "test",
      chrome: { mode: "embed", theme: "dark" },
      persistence: "none",
      auth: "anonymous",
      features: {},
      models: { available: [] },
      gate: { mode: "turn_limited", activityDetail: "labels" },
      backend: { type: "digigraph" },
      tools: { allowUserToggle: true, catalog: [] },
      mcp: {
        servers: [
          {
            id: "datatap",
            url: "https://mcp.datatap.example/mcp",
            label: "DataTap",
            default: true,
            token: "tenant-static-key",
            tokenEnv: "DATATAP_MCP_TOKEN",
            authHeader: "X-API-Key",
          },
        ],
        allowUserServers: false,
        allowAddForm: false,
      },
    } as unknown as DigichatDeployment;
    const client = toDigichatClientConfig(dep);
    expect(client.mcp.servers).toEqual([{ id: "datatap", label: "DataTap", default: true }]);
    const serialized = JSON.stringify(client.mcp.servers);
    expect(serialized).not.toContain("tenant-static-key");
    expect(serialized).not.toContain("DATATAP_MCP_TOKEN");
    expect(serialized).not.toContain("X-API-Key");
    expect(serialized).not.toContain("mcp.datatap.example");
  });

  it("drops authScheme too: a jwt row projects no credential shape at all", () => {
    // The minted token only ever exists on the server-to-server header to
    // digigraph (lib/mcp-edge-token.ts). A client that learned the row is a
    // jwt row would have learned about the deployment's identity model without
    // being able to use it, and the field is operator-only.
    //
    // Read the real house document rather than a literal: the first assertion
    // fails if defaults.yaml stops marking its MCP rows jwt, and the second
    // fails if the projection starts leaking the scheme or a credential.
    const raw = loadYaml(readFileSync(HOUSE_DEFAULTS, "utf8")) as unknown;
    const parsed = parseDigichatConfig(raw, "defaults.yaml");
    const host = Object.keys(parsed.hosts ?? {})[0]!;
    const dep = (parsed.hosts ?? {})[host]!;
    expect(dep).toBeDefined();
    expect(dep.mcp?.servers.map((s) => [s.id, s.authScheme])).toEqual([
      ["digisearch", "jwt"],
      ["digivault", "jwt"],
    ]);
    const client = toDigichatClientConfig(dep);
    expect(client.mcp.servers).toEqual([
      { id: "digisearch", label: "Search", default: true },
      { id: "digivault", label: "Vault", default: true },
    ]);
    const serialized = JSON.stringify(client);
    expect(serialized).not.toContain("authScheme");
    expect(serialized).not.toContain("_stack/mcp");
    expect(serialized).not.toMatch(/eyJ[A-Za-z0-9_-]{10,}/);
  });
});

describe("projectCatalog omitted-default fail-closed (#3805)", () => {
  it("omitted/undefined default → false; explicit true → true; explicit false → false", () => {
    const client = toDigichatClientConfig(
      depWithCatalog([
        { id: "implicit-off" },
        { id: "explicit-on", default: true },
        { id: "explicit-off", default: false },
      ]),
    );
    const byId = new Map(client.tools.catalog.map((t) => [t.id, t.default]));
    expect(byId.get("implicit-off")).toBe(false);
    expect(byId.get("explicit-on")).toBe(true);
    expect(byId.get("explicit-off")).toBe(false);
  });
});

describe("clientConfigFromEmbedTenant omitted-default fail-closed (#3805)", () => {
  it("omitted/undefined default → false; explicit true → true; explicit false → false", () => {
    const embed = {
      slug: "test",
      gateMode: "turn_limited",
      theme: "dark",
      accent: null,
      attribution: false,
      tools: {
        catalog: [
          { id: "implicit-off" },
          { id: "explicit-on", default: true },
          { id: "explicit-off", default: false },
        ],
      },
    } as EmbedTenantClientConfig;
    const client = clientConfigFromEmbedTenant(embed);
    const byId = new Map(client.tools.catalog.map((t) => [t.id, t.default]));
    expect(byId.get("implicit-off")).toBe(false);
    expect(byId.get("explicit-on")).toBe(true);
    expect(byId.get("explicit-off")).toBe(false);
  });
});

describe("pageContext feature projection", () => {
  it("defaults to visible and passes an explicit silent through the bridge", () => {
    expect(DEFAULT_CLIENT_CONFIG.features.pageContext).toBe("visible");
    const base = { slug: "test", gateMode: "ungated", theme: "dark", accent: null, attribution: false } as EmbedTenantClientConfig;
    expect(clientConfigFromEmbedTenant(base).features.pageContext).toBe("visible");
    expect(
      clientConfigFromEmbedTenant({ ...base, pageContext: "silent" }).features.pageContext,
    ).toBe("silent");
    expect(
      clientConfigFromEmbedTenant({ ...base, pageContext: "off" }).features.pageContext,
    ).toBe("off");
  });
});

describe("page-layout embeds keep embed chrome (#3733)", () => {
  it("maps layout page to embed mode so the full-app catalog bar stays out", () => {
    const page = {
      slug: "test",
      gateMode: "ungated",
      theme: "dark",
      accent: null,
      attribution: false,
      layout: "page",
    } as EmbedTenantClientConfig;
    expect(clientConfigFromEmbedTenant(page).chrome.mode).toBe("embed");
  });
});

describe("foundry tenants do not inherit the house catalog", () => {
  it("blanks models and the picker even when a catalog was attached", () => {
    const foundry = {
      slug: "foundry-trial",
      gateMode: "ungated",
      theme: "dark",
      accent: null,
      attribution: false,
      backendType: "foundry",
      models: {
        default: "deepseek/deepseek-v4.1-flash-1017",
        available: ["deepseek/deepseek-v4.1-flash-1017"],
        allowPicker: true,
        picker: {
          showFullList: true,
          presets: [
            {
              id: "auto",
              label: "Auto",
              description: "default",
              model: "deepseek/deepseek-v4.1-flash-1017",
            },
          ],
          groups: [],
        },
      },
    } as EmbedTenantClientConfig;
    const client = clientConfigFromEmbedTenant(foundry);
    expect(client.models.available).toEqual([]);
    expect(client.models.allowPicker).toBe(false);
    expect(client.models.picker).toBeUndefined();
  });
});

describe("baseline embed models catalog (Cheaper Inference default)", () => {
  it("ships the deploy catalog with the V4.1 Flash default and an enabled picker", () => {
    expect(DEFAULT_CLIENT_CONFIG.models.default).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(DEFAULT_CLIENT_CONFIG.models.available).toHaveLength(13);
    expect(DEFAULT_CLIENT_CONFIG.models.available).toContain("deepseek/deepseek-v4.1-flash-1017");
    expect(DEFAULT_CLIENT_CONFIG.models.allowPicker).toBe(true);
  });
});

describe("client fallback matches house", () => {
  it("ships the house suggestions with web search, BYOK, and the context meter on", () => {
    expect(DEFAULT_CLIENT_CONFIG.slug).toBe("digithings-ai");
    expect(DEFAULT_CLIENT_CONFIG.chrome.suggestions).toHaveLength(8);
    expect(DEFAULT_CLIENT_CONFIG.chrome.welcome).toBe("Ask about digithings");
    expect(DEFAULT_CLIENT_CONFIG.mcp.allowUserServers).toBe(false);
    expect(DEFAULT_CLIENT_CONFIG.mcp.allowAddForm).toBe(false);
    expect(DEFAULT_CLIENT_CONFIG.gate.webSearch).toBe(true);
    expect(DEFAULT_CLIENT_CONFIG.gate.showByok).toBe(true);
    expect(DEFAULT_CLIENT_CONFIG.gate.showContextMeter).toBe(true);
    expect(DEFAULT_CLIENT_CONFIG.features.attachments).toBe(false);
  });

  it("enables user MCP, web search, and BYOK only for an explicitly-configured deployment", () => {
    const client = toDigichatClientConfig({
      slug: "configured",
      chrome: { mode: "embed", theme: "dark" },
      persistence: "none",
      auth: "anonymous",
      features: {},
      models: { available: [] },
      gate: { mode: "turn_limited", activityDetail: "labels", showByok: true, webSearch: true },
      backend: { type: "digigraph" },
      tools: { allowUserToggle: true, catalog: [] },
      mcp: { servers: [], allowUserServers: true, allowAddForm: true },
    } as unknown as DigichatDeployment);
    expect(client.mcp.allowUserServers).toBe(true);
    expect(client.mcp.allowAddForm).toBe(true);
    expect(client.gate.webSearch).toBe(true);
    expect(client.gate.showByok).toBe(true);
  });

  it("leaves searchEngine unset in the least-privilege default (auto by omission)", () => {
    expect("searchEngine" in DEFAULT_CLIENT_CONFIG.gate).toBe(false);
  });

  it("projects an allowlisted tenant searchEngine default into the client gate", () => {
    const client = toDigichatClientConfig({
      slug: "configured",
      chrome: { mode: "embed", theme: "dark" },
      persistence: "none",
      auth: "anonymous",
      features: {},
      models: { available: [] },
      gate: {
        mode: "turn_limited",
        activityDetail: "labels",
        showByok: true,
        webSearch: true,
        searchEngine: "exa",
      },
      backend: { type: "digigraph" },
      tools: { allowUserToggle: true, catalog: [] },
      mcp: { servers: [], allowUserServers: true, allowAddForm: true },
    } as unknown as DigichatDeployment);
    expect(client.gate.searchEngine).toBe("exa");
  });

  it("drops an unknown tenant searchEngine instead of projecting it", () => {
    const client = toDigichatClientConfig({
      slug: "configured",
      chrome: { mode: "embed", theme: "dark" },
      persistence: "none",
      auth: "anonymous",
      features: {},
      models: { available: [] },
      gate: {
        mode: "turn_limited",
        activityDetail: "labels",
        showByok: true,
        webSearch: true,
        searchEngine: "not-an-engine",
      },
      backend: { type: "digigraph" },
      tools: { allowUserToggle: true, catalog: [] },
      mcp: { servers: [], allowUserServers: true, allowAddForm: true },
    } as unknown as DigichatDeployment);
    expect(client.gate.searchEngine).toBeUndefined();
  });
});

describe("chrome.scroll client projection", () => {
  it("defaults to follow when the deployment does not say", () => {
    const client = toDigichatClientConfig(depWithCatalog([]));
    expect(client.chrome.scroll).toEqual({ mode: "follow" });
    expect(DEFAULT_CLIENT_CONFIG.chrome.scroll).toEqual({ mode: "follow" });
  });

  it("carries free through to the client", () => {
    const dep = depWithCatalog([]);
    const free = {
      ...dep,
      chrome: { ...dep.chrome, scroll: { mode: "free" as const } },
    } as DigichatDeployment;
    expect(toDigichatClientConfig(free).chrome.scroll).toEqual({ mode: "free" });
  });
});

describe("chrome.loading client projection", () => {
  it("defaults to the banner cover when the deployment does not say", () => {
    const client = toDigichatClientConfig(depWithCatalog([]));
    expect(client.chrome.loading).toBe("banner");
    expect(DEFAULT_CLIENT_CONFIG.chrome.loading).toBe("banner");
  });

  it("carries a chosen boot animation through to the client", () => {
    const dep = depWithCatalog([]);
    const chosen = {
      ...dep,
      chrome: { ...dep.chrome, loading: "tooltask" as const },
    } as DigichatDeployment;
    expect(toDigichatClientConfig(chosen).chrome.loading).toBe("tooltask");
  });
});
