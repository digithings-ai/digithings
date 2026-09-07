import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  loadDigichatConfig,
  resetDigichatConfigForTests,
  embedTenantToDeployment,
  deploymentToEmbedTenant,
  getAnonymousClientInstall,
  setDigichatConfigForTests,
} from "./loader";
import { toDigichatClientConfig, toChromeClientConfig } from "./client-projection";
import { filterForceToolHeader } from "./force-tool";
import type { EmbedTenantConfig } from "@/lib/embed-tenants";

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

  it("uses dev default when no file and no tenants", () => {
    const cfg = loadDigichatConfig({ fileContents: null, env: {} });
    expect(cfg.deployment?.slug).toBe("local");
    expect(cfg.deployment?.chrome.mode).toBe("embed");
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
      gate: { consumeUrl: "https://quota.example.com/spend" },
    } satisfies EmbedTenantConfig);

    dep.mcp = {
      servers: [{ id: "extra", url: "https://mcp.example.com/sse", label: "Extra" }],
    };

    const client = toDigichatClientConfig(dep);
    const json = JSON.stringify(client);
    expect(json).not.toContain("secret-token");
    expect(json).not.toContain("quota.example.com");
    expect(json).not.toContain("proj.example.com");
    expect(json).not.toContain("my-agent");
    expect(json).not.toContain("mcp.example.com");
    expect(client.backendType).toBe("foundry");
    expect(client.mcp.servers).toEqual([{ id: "extra", label: "Extra" }]);
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
    });
    expect(filterForceToolHeader(dep, "digisearch")).toBe("digisearch");
    expect(filterForceToolHeader(dep, "digivault")).toBe("digivault");
    expect(filterForceToolHeader(dep, "not-a-tool")).toBeUndefined();
  });

  it("legacy-allows digisearch/digivault when catalog empty", () => {
    const dep = embedTenantToDeployment({
      slug: "x",
      token: "t",
      backend: { type: "digigraph" },
      gateMode: "ungated",
      theme: "light",
      attribution: false,
      activityDetail: "labels",
    });
    dep.tools = { allowUserToggle: true, catalog: [] };
    expect(filterForceToolHeader(dep, "digisearch")).toBe("digisearch");
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
