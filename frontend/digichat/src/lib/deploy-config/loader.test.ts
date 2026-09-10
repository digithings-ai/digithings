import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  loadDigichatConfig,
  resetDigichatConfigForTests,
  embedTenantToDeployment,
  deploymentToEmbedTenant,
  getAnonymousClientInstall,
  setDigichatConfigForTests,
  matchHostDeployment,
} from "./loader";
import { toDigichatClientConfig, toChromeClientConfig } from "./client-projection";
import { filterForceToolHeader } from "./force-tool";
import { clientConfigFromEmbedTenant } from "./embed-bridge";
import { toEmbedClientConfig } from "@/lib/embed-client-config";
import type { EmbedTenantConfig } from "@/lib/embed-tenants";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

beforeEach(() => {
  resetDigichatConfigForTests();
});

describe("loadDigichatConfig", () => {
  it("loads YAML from injected file contents", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: acme-docs
  chrome:
    mode: embed
    theme: light
    title: Ask docs
  backend:
    type: digigraph
  gate:
    mode: ungated
`,
      env: {},
    });
    expect(cfg.deployment?.slug).toBe("acme-docs");
    expect(cfg.deployment?.chrome.title).toBe("Ask docs");
  });

  it("fails closed on invalid YAML schema", () => {
    expect(() =>
      loadDigichatConfig({
        fileContents: `
version: 1
deployment:
  slug: BAD_SLUG
  backend:
    type: digigraph
`,
        env: {},
      }),
    ).toThrow(/slug/);
  });

  it("hydrates DIGICHAT_EMBED_TENANTS into hosts", () => {
    const tenants = JSON.stringify({
      "customer.example": {
        slug: "customer",
        token: "tok_customer_secret",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        theme: "light",
        attribution: true,
        activityDetail: "labels",
        webSearch: true,
      },
    });
    const cfg = loadDigichatConfig({
      fileContents: null,
      env: { DIGICHAT_EMBED_TENANTS: tenants },
    });
    expect(cfg.hosts?.["customer.example"]?.slug).toBe("customer");
    expect(cfg.hosts?.["customer.example"]?.token).toBe("tok_customer_secret");
    expect(cfg.hosts?.["customer.example"]?.tools?.catalog.some((t) => t.id === "web_search")).toBe(
      true,
    );
    expect(cfg.hosts?.["customer.example"]?.gate.requiredPlanTier).toBeUndefined();
    expect(cfg.hosts?.["customer.example"]?.chrome.skin).toBe("base");
  });

  it("defaults first-party DIGICHAT_EMBED_TENANTS hosts to digichat when skin is omitted", () => {
    const tenants = JSON.stringify({
      "digithings.ai": {
        slug: "digithings",
        aliases: ["www.digithings.ai"],
        token: "unused-for-first-party",
        backend: { type: "digigraph" },
        gateMode: "ungated",
      },
      "occ.digithings.ai": {
        slug: "occ",
        token: "unused-for-first-party",
        backend: { type: "digigraph" },
        gateMode: "ungated",
      },
    });
    const cfg = loadDigichatConfig({
      fileContents: null,
      env: { DIGICHAT_EMBED_TENANTS: tenants },
    });
    expect(cfg.hosts?.["digithings.ai"]?.chrome.skin).toBe("digichat");
    expect(cfg.hosts?.["www.digithings.ai"]?.chrome.skin).toBe("digichat");
    expect(cfg.hosts?.["occ.digithings.ai"]?.chrome.skin).toBe("digichat");
    const client = toDigichatClientConfig(cfg.hosts!["digithings.ai"]!);
    expect(client.chrome.skin).toBe("digichat");
  });

  it("hydrates requiredPlanTier from DIGICHAT_EMBED_TENANTS (#3662 YAML round-trip)", () => {
    const tenants = JSON.stringify({
      "digiquant.io": {
        slug: "digiquant-dashboard",
        token: "dash-secret",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        llmAccess: "operator",
        showByok: true,
        requiredPlanTier: "desk",
      },
    });
    const cfg = loadDigichatConfig({
      fileContents: null,
      env: { DIGICHAT_EMBED_TENANTS: tenants },
    });
    expect(cfg.hosts?.["digiquant.io"]?.gate.requiredPlanTier).toBe("desk");
    expect(cfg.hosts?.["digiquant.io"]?.gate.showByok).toBe(true);
  });

  it("copies requiredPlanTier from JSON overlay onto a YAML host that omitted it", () => {
    const tenants = JSON.stringify({
      "digiquant.io": {
        slug: "digiquant-dashboard",
        token: "dash-secret",
        backend: { type: "digigraph" },
        gateMode: "ungated",
        llmAccess: "operator",
        showByok: true,
        requiredPlanTier: "desk",
      },
    });
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
hosts:
  digiquant.io:
    slug: digiquant-dashboard
    token: yaml-tok
    backend:
      type: digigraph
    gate:
      mode: ungated
      llmAccess: operator
      showByok: true
`,
      env: { DIGICHAT_EMBED_TENANTS: tenants },
    });
    expect(cfg.hosts?.["digiquant.io"]?.gate.requiredPlanTier).toBe("desk");
    expect(cfg.hosts?.["digiquant.io"]?.token).toBe("yaml-tok");
  });

  it("overlays DIGICHAT_EMBED_TOKEN onto deployment", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: acme
  backend:
    type: digigraph
`,
      env: { DIGICHAT_EMBED_TOKEN: "from_env" },
    });
    expect(cfg.deployment?.token).toBe("from_env");
  });

  it("overlays DIGICHAT_CHROME_SKIN onto deployment", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: acme
  backend:
    type: digigraph
`,
      env: { DIGICHAT_CHROME_SKIN: "claude" },
    });
    expect(cfg.deployment?.chrome.skin).toBe("claude");
  });

  it("overlays DIGICHAT_CHROME_SKIN onto hosts", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
hosts:
  example.com:
    slug: acme
    backend:
      type: digigraph
`,
      env: { DIGICHAT_CHROME_SKIN: "ChatGPT" },
    });
    expect(cfg.hosts?.["example.com"]?.chrome.skin).toBe("chatgpt");
  });

  it("fails closed on unknown DIGICHAT_CHROME_SKIN", () => {
    expect(() =>
      loadDigichatConfig({
        fileContents: `
version: 1
deployment:
  slug: acme
  backend:
    type: digigraph
`,
        env: { DIGICHAT_CHROME_SKIN: "ink" },
      }),
    ).toThrow(/DIGICHAT_CHROME_SKIN/);
  });

  it("uses the unconfigured container default when no file and no tenants", () => {
    const cfg = loadDigichatConfig({ fileContents: null, env: {} });
    expect(cfg.deployment?.slug).toBe("local");
    expect(cfg.deployment?.chrome.mode).toBe("embed");
    expect(cfg.deployment?.chrome.skin).toBe("digichat");
    expect(cfg.deployment?.chrome.theme).toBe("dark");
    expect(cfg.deployment?.features.attachments).toBe(true);
    expect(cfg.deployment?.tools?.catalog ?? []).toEqual([]);
    expect(cfg.deployment?.models).toEqual({
      default: "deepseek/deepseek-v4-flash",
      available: [
        "deepseek/deepseek-v4-flash",
        "deepseek/deepseek-v4-flash-0731",
        "openai/gpt-oss-120b",
        "z-ai/glm-5.3-flash",
      ],
      allowPicker: true,
    });
  });
});

describe("client projection", () => {
  it("strips token, consumeUrl, and Foundry credentials", () => {
    const dep = embedTenantToDeployment({
      slug: "cust",
      token: "secret-token",
      backend: {
        type: "foundry",
        projectEndpoint: "https://proj.example.com",
        agentName: "my-agent",
      },
      gateMode: "turn_limited",
      theme: "dark",
      attribution: false,
      activityDetail: "full",
      requiredPlanTier: "desk",
      gate: { consumeUrl: "https://quota.example.com/spend" },
    } satisfies EmbedTenantConfig);

    dep.mcp = {
      servers: [{ id: "extra", url: "https://mcp.example.com/sse", label: "Extra" }],
      allowUserServers: false,
      allowAddForm: false,
    };

    const client = toDigichatClientConfig(dep);
    const json = JSON.stringify(client);
    expect(json).not.toContain("secret-token");
    expect(json).not.toContain("quota.example.com");
    expect(json).not.toContain("proj.example.com");
    expect(json).not.toContain("my-agent");
    expect(json).not.toContain("mcp.example.com");
    expect(json).not.toContain("requiredPlanTier");
    expect(client.backendType).toBe("foundry");
    expect(client.mcp.servers).toEqual([{ id: "extra", label: "Extra" }]);
    expect(client.mcp.servers[0]).not.toHaveProperty("url");
    expect(client.mcp.allowUserServers).toBe(false);
  });

  it("chrome projection exposes launcher without secrets", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: dash
  token: never-leak
  chrome:
    mode: modal
    launcher:
      hotkey: meta+i
      mobileFullscreen: true
      label: ask digichat
  backend:
    type: digigraph
`,
      env: {},
    });
    const chrome = toChromeClientConfig(cfg.deployment!);
    expect(chrome.launcher?.hotkey).toBe("meta+i");
    expect(JSON.stringify(chrome)).not.toContain("never-leak");
  });
});

describe("force-tool allowlist", () => {
  it("allows only catalogued force tools", () => {
    const dep = embedTenantToDeployment({
      slug: "x",
      token: "t",
      backend: { type: "digigraph" },
      gateMode: "ungated",
      theme: "light",
      attribution: false,
      activityDetail: "labels",
      tools: {
        allowUserToggle: true,
        catalog: [
          { id: "digisearch", default: true, label: "Search" },
          { id: "digivault", default: true, label: "Vault" },
        ],
      },
    });
    expect(filterForceToolHeader(dep, "digisearch")).toBe("digisearch");
    expect(filterForceToolHeader(dep, "digivault")).toBe("digivault");
    expect(filterForceToolHeader(dep, "not-a-tool")).toBeUndefined();
  });

  it("denies digisearch/digivault when catalog empty (fail-closed, #3806)", () => {
    const dep = embedTenantToDeployment({
      slug: "x",
      token: "t",
      backend: { type: "digigraph" },
      gateMode: "ungated",
      theme: "light",
      attribution: false,
      activityDetail: "labels",
    });
    expect(dep.tools?.catalog ?? []).toEqual([]);
    expect(filterForceToolHeader(dep, "digisearch")).toBeUndefined();
    expect(filterForceToolHeader(dep, "digivault")).toBeUndefined();
    expect(filterForceToolHeader(dep, "not-a-tool")).toBeUndefined();
  });
});

describe("embed tenant round-trip", () => {
  it("deploymentToEmbedTenant preserves backend discriminator fields", () => {
    const original: EmbedTenantConfig = {
      slug: "occ",
      token: "tok",
      backend: {
        type: "digigraph",
        digisearchIndex: "occ_help",
        vaultPathPrefix: "clients/occ",
      },
      gateMode: "ungated",
      theme: "light",
      attribution: true,
      activityDetail: "labels",
      webSearch: false,
    };
    const back = deploymentToEmbedTenant(embedTenantToDeployment(original));
    expect(back.backend).toEqual(original.backend);
    expect(back.token).toBe("tok");
  });

  it("preserves requiredPlanTier through YAML converters (#3662)", () => {
    const original: EmbedTenantConfig = {
      slug: "digiquant-dashboard",
      token: "dash-secret",
      backend: { type: "digigraph" },
      gateMode: "ungated",
      theme: "dark",
      attribution: false,
      activityDetail: "labels",
      llmAccess: "operator",
      showByok: true,
      requiredPlanTier: "desk",
    };
    const dep = embedTenantToDeployment(original);
    expect(dep.gate.requiredPlanTier).toBe("desk");
    const back = deploymentToEmbedTenant(dep);
    expect(back.requiredPlanTier).toBe("desk");
    expect(back.gate).toBeUndefined();
    expect(back.showByok).toBe(true);
    expect(back.llmAccess).toBe("operator");
  });

  it("projects a tokenless YAML deployment (client container)", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: client-chatgpt
  chrome:
    mode: embed
    skin: chatgpt
  backend:
    type: digigraph
`,
      env: {},
    });
    const tenant = deploymentToEmbedTenant(cfg.deployment!);
    expect(tenant.token).toBe("");
    expect(tenant.skin).toBe("chatgpt");
    expect(tenant.gateMode).toBe("ungated");
  });
});

describe("matchHostDeployment", () => {
  it("resolves product embed YAML hosts without leaking hosts[0] to unknowns", () => {
    const raw = readFileSync(
      resolve(__dirname, "../../../config/examples/digithings-ai-embed.yaml"),
      "utf8",
    );
    const cfg = loadDigichatConfig({ fileContents: raw, env: {} });
    const dt = matchHostDeployment("https://digithings.ai", cfg);
    expect(dt?.chrome.skin).toBe("digichat");
    expect(dt?.backend.type).toBe("digigraph");
    expect(dt?.tools?.catalog.map((t) => t.id)).toEqual([
      "digisearch",
      "digivault",
      "web_search",
    ]);
    expect(matchHostDeployment("www.digithings.ai", cfg)?.slug).toBe("digithings-ai");
    expect(matchHostDeployment("https://unknown.example", cfg)).toBeNull();
  });

  it("round-trips YAML host skin into the embed client projection", () => {
    const raw = readFileSync(
      resolve(__dirname, "../../../config/examples/digithings-ai-embed.yaml"),
      "utf8",
    );
    const cfg = loadDigichatConfig({ fileContents: raw, env: {} });
    const tenant = deploymentToEmbedTenant(cfg.hosts!["digithings.ai"]!);
    const client = clientConfigFromEmbedTenant(toEmbedClientConfig(tenant));
    expect(client.chrome.skin).toBe("digichat");
    expect(client.backendType).toBe("digigraph");
    expect(client.tools.catalog.map((t) => t.id)).toEqual(
      expect.arrayContaining(["digisearch", "digivault", "web_search"]),
    );
    expect(client.features.attachments).toBe(false);
    expect(cfg.hosts!["digithings.ai"]!.gate.activityDetail).toBe("full");
    expect(tenant.activityDetail).toBe("full");
    expect(cfg.hosts!["digithings.ai"]!.backend.vaultPathPrefix).toBe("clients/digithings");
  });

  it("does not inject Search/Vault onto an empty catalog", () => {
    const client = clientConfigFromEmbedTenant({
      slug: "embed",
      gateMode: "ungated",
      theme: "dark",
      skin: "digichat",
      accent: null,
      attribution: false,
      attachments: true,
      showByok: false,
      layout: "embed",
      showLanguageSelector: false,
      webSearch: false,
    });
    expect(client.tools.catalog).toEqual([]);
    expect(client.features.attachments).toBe(true);
    expect(client.chrome.skin).toBe("digichat");
  });
});

describe("getAnonymousClientInstall", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    resetDigichatConfigForTests();
  });

  it("ignores the synthetic no-file default", () => {
    setDigichatConfigForTests(loadDigichatConfig({ fileContents: null, env: {} }));
    expect(getAnonymousClientInstall({})).toBeNull();
  });

  it("treats DIGICHAT_CHROME_SKIN as an explicit client install", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: acme
  chrome:
    skin: chatgpt
  backend:
    type: digigraph
`,
      env: { DIGICHAT_CHROME_SKIN: "claude" },
    });
    setDigichatConfigForTests(cfg);
    expect(getAnonymousClientInstall({ DIGICHAT_CHROME_SKIN: "claude" })?.chrome.skin).toBe(
      "claude",
    );
  });

  it("does not expose session-auth deployments as anonymous embeds", () => {
    const cfg = loadDigichatConfig({
      fileContents: `
version: 1
deployment:
  slug: local-app
  auth: session
  chrome:
    mode: app
    skin: base
  backend:
    type: digigraph
`,
      env: { DIGICHAT_CHROME_SKIN: "base" },
    });
    setDigichatConfigForTests(cfg);
    expect(getAnonymousClientInstall({ DIGICHAT_CHROME_SKIN: "base" })).toBeNull();
  });
});
