import { describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import {
  allowlistModelId,
  disclosureDefaultOpen,
  disclosureIsLocked,
  disclosureIsVisible,
  GateSchema,
  parseDigichatConfig,
  resolveHouseModelSelection,
  premiumModelsHeader,
  routerModelsHeader,
  welcomeTitle,
} from "./schema";
import { allowedForceTools } from "./force-tool";
import { THREAD_SKINS } from "@digithings/ui/chat/skins";

const examplesDir = resolve(__dirname, "../../../config/examples");

describe("DigichatConfigSchema", () => {
  it("parses a minimal single deployment", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
      },
    });
    expect(cfg.deployment?.slug).toBe("acme");
    expect(cfg.deployment?.chrome.mode).toBe("embed");
    expect(cfg.deployment?.persistence).toBe("none");
    expect(cfg.deployment?.auth).toBe("anonymous");
    expect(cfg.deployment?.features.view).toBe("balanced");
    expect(cfg.deployment?.features.thinking).toBe("auto");
    expect(cfg.deployment?.features.density).toBe("default");
    expect(cfg.deployment?.features.effort).toBe("medium");
    expect(cfg.deployment?.chrome.toolbar).toBe(true);
    expect(cfg.deployment?.chrome.scrollbars).toBe("always");
    expect(cfg.deployment?.chrome.palette).toBeUndefined();
    expect(cfg.deployment?.chrome.defaultLanguage).toBe("en");
    expect(cfg.deployment?.chrome.transcript.userAlign).toBe("right");
    expect(cfg.deployment?.chrome.skin).toBe("base");
    expect(cfg.deployment?.cli.enabled).toBe(false);
    expect(cfg.deployment?.models.available).toEqual([]);
    expect(cfg.deployment?.gate.activityDetail).toBe("labels");
    expect(cfg.deployment?.features.attachments).toBe(true);
    expect(cfg.deployment?.features.pageContext).toBe("visible");
  });

  it("accepts pageContext modes and fails closed on unknown values", () => {
    const silent = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { pageContext: "silent" },
      },
    });
    expect(silent.deployment?.features.pageContext).toBe("silent");
    const off = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { pageContext: "off" },
      },
    });
    expect(off.deployment?.features.pageContext).toBe("off");
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "acme",
          backend: { type: "digigraph" },
          features: { pageContext: "hidden" },
        },
      }),
    ).toThrow(/pageContext/);
  });

  it("folds legacy reasoning/toolCalls disclosure keys onto view/thinking", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { reasoning: true, toolCalls: false },
      },
    });
    expect(cfg.deployment?.features.view).toBe("quiet");
    expect(cfg.deployment?.features.thinking).toBe("collapsed");

    const expanded = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { reasoning: "expanded", toolCalls: "locked_open" },
      },
    });
    expect(expanded.deployment?.features.view).toBe("verbose");
    expect(expanded.deployment?.features.thinking).toBe("open");
  });

  it("folds the retired view ids forward", () => {
    const quiet = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { view: "compact" },
      },
    });
    expect(quiet.deployment?.features.view).toBe("quiet");

    const verbose = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { view: "detailed" },
      },
    });
    expect(verbose.deployment?.features.view).toBe("verbose");

    // `hidden` was the one-line level; the folded chain shows that line as
    // its header now, so a config that still says it means the titles only.
    const hidden = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { view: "hidden" },
      },
    });
    expect(hidden.deployment?.features.view).toBe("quiet");
  });

  it("accepts view/thinking modes and cli.enabled", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { view: "verbose", thinking: "open" },
        chrome: { defaultLanguage: "de", transcript: { userAlign: "left" } },
        models: {
          default: "gpt-4o-mini",
          available: ["gpt-4o-mini", "gpt-4o"],
          allowPicker: true,
        },
        cli: { enabled: true },
      },
    });
    expect(cfg.deployment?.features.view).toBe("verbose");
    expect(cfg.deployment?.features.thinking).toBe("open");
    expect(cfg.deployment?.chrome.defaultLanguage).toBe("de");
    expect(cfg.deployment?.chrome.transcript.userAlign).toBe("left");
    expect(cfg.deployment?.cli.enabled).toBe(true);
    expect(cfg.deployment?.models.available).toEqual(["gpt-4o-mini", "gpt-4o"]);
  });

  it("coerces chrome.welcome strings and objects", () => {
    const asString = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        chrome: { welcome: "Ask about docs" },
      },
    });
    expect(asString.deployment?.chrome.welcome).toEqual({ title: "Ask about docs" });
    const asObject = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        chrome: {
          welcome: {
            title: "digichat",
            body: "Scoped to this deployment.",
          },
        },
      },
    });
    expect(asObject.deployment?.chrome.welcome).toEqual({
      title: "digichat",
      body: "Scoped to this deployment.",
    });
  });

  it("fails closed on missing deployment and hosts", () => {
    expect(() => parseDigichatConfig({ version: 1 })).toThrow(
      /deployment or at least one hosts/,
    );
  });

  it("fails closed on invalid chrome.mode", () => {
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          chrome: { mode: "popup" },
          backend: { type: "digigraph" },
        },
      }),
    ).toThrow(/chrome/);
  });

  it("accepts official thread skins and fails closed on unknown ones", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        chrome: { skin: "chatgpt" },
        backend: { type: "digigraph" },
      },
    });
    expect(cfg.deployment?.chrome.skin).toBe("chatgpt");
    expect(
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "acme",
          chrome: { skin: "ChatGPT" },
          backend: { type: "digigraph" },
        },
      }).deployment?.chrome.skin,
    ).toBe("chatgpt");
    const ink = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        chrome: { skin: "react-ink" },
        backend: { type: "digigraph" },
      },
    });
    expect(ink.deployment?.chrome.skin).toBe("react-ink");
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          chrome: { skin: "ink" },
          backend: { type: "digigraph" },
        },
      }),
    ).toThrow(/skin/);
  });

  it("accepts a foundry per-turn tool-call cap and rejects a non-cap", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "x",
        backend: {
          type: "foundry",
          projectEndpoint: "https://example.services.ai.azure.com",
          agentName: "agent",
          maxToolCalls: 5,
        },
      },
    });
    expect(cfg.deployment?.backend).toMatchObject({ type: "foundry", maxToolCalls: 5 });

    const unlimited = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "x",
        backend: {
          type: "foundry",
          projectEndpoint: "https://example.services.ai.azure.com",
          agentName: "agent",
        },
      },
    });
    expect(unlimited.deployment?.backend).not.toHaveProperty("maxToolCalls");

    for (const maxToolCalls of [0, -1, 1.5, 101]) {
      expect(() =>
        parseDigichatConfig({
          version: 1,
          deployment: {
            slug: "x",
            backend: {
              type: "foundry",
              projectEndpoint: "https://example.services.ai.azure.com",
              agentName: "agent",
              maxToolCalls,
            },
          },
        }),
      ).toThrow(/maxToolCalls/);
    }
  });

  it("accepts shared guardrails and rejects a fraction that cannot pause", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "x",
        backend: { type: "digigraph" },
        guardrails: {
          maxToolCallsPerTurn: 5,
          tokensPerMinute: { deployment: 100_000, user: 80_000 },
        },
      },
    });
    expect(cfg.deployment?.guardrails).toEqual({
      maxToolCallsPerTurn: 5,
      tokensPerMinute: { deployment: 100_000, user: 80_000 },
    });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("notice/best-effort"));
    warn.mockRestore();
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          backend: { type: "digigraph" },
          guardrails: { answerAt: 0.95 },
        },
      }),
    ).toThrow(/answerAt must be below pauseAt/);
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          backend: { type: "digigraph" },
          guardrails: { tokensPerMinute: { user: 0 } },
        },
      }),
    ).toThrow(/user/);

    // The trial config filename contains a tenant name. Assemble it so this
    // public test file does not carry that literal.
    const trialFile = ["data", "tap-trial-foundry.yaml"].join("");
    const trial = parseDigichatConfig(
      loadYaml(readFileSync(resolve(__dirname, "../../../config", trialFile), "utf8")),
      trialFile,
    );
    expect(trial.deployment?.guardrails).toBeUndefined();
    expect(trial.deployment?.backend).not.toHaveProperty("maxToolCalls");
  });

  it("refuses a tool cap on a2a and warns on notice/best-effort backends", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    try {
      expect(() =>
        parseDigichatConfig({
          version: 1,
          deployment: {
            slug: "x",
            backend: { type: "a2a", baseUrl: "https://a2a.example.com" },
            guardrails: { maxToolCallsPerTurn: 2 },
          },
        }),
      ).toThrow(/no tool-call hook/);

      for (const backend of [
        { type: "langgraph", apiUrl: "https://lg.example.com", assistantId: "agent" },
        { type: "ag-ui", url: "https://agui.example.com/run" },
      ]) {
        warn.mockClear();
        const cfg = parseDigichatConfig({
          version: 1,
          deployment: { slug: "x", backend, guardrails: { maxToolCallsPerTurn: 2 } },
        });
        expect(cfg.deployment?.guardrails?.maxToolCallsPerTurn).toBe(2);
        expect(warn).toHaveBeenCalledWith(
          expect.stringContaining(`${backend.type} is notice/best-effort`),
        );
      }

      warn.mockClear();
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          backend: {
            type: "openai-responses",
            baseUrl: "https://api.example.com/v1",
            model: "gpt-5",
            apiKeyEnv: "DIGICHAT_BACKEND_EXAMPLE_KEY",
          },
          guardrails: { maxToolCallsPerTurn: 2 },
        },
      });
      expect(warn).not.toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });

  it("fails closed on foundry http endpoint", () => {
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "x",
          backend: {
            type: "foundry",
            projectEndpoint: "http://example.com",
            agentName: "agent",
          },
        },
      }),
    ).toThrow(/https/);
  });

  it("parses all example YAML files", () => {
    const files = [
      "digithings-ai-embed.yaml",
      "occ-embed.yaml",
      "dashboard-modal.yaml",
      "datatap-mcp.yaml",
      "local-app.yaml",
      "local-app-memory.yaml",
      "local-cli.yaml",
    ];
    const skinFiles = readdirSync(resolve(examplesDir, "skins"))
      .filter((name) => name.endsWith(".yaml"))
      .map((name) => `skins/${name}`);
    expect(skinFiles.length).toBeGreaterThanOrEqual(11);
    for (const name of [...files, ...skinFiles]) {
      const raw = readFileSync(resolve(examplesDir, name), "utf8");
      const doc = loadYaml(raw);
      const cfg = parseDigichatConfig(doc, name);
      expect(cfg.version).toBe(1);
      expect(cfg.deployment || (cfg.hosts && Object.keys(cfg.hosts).length > 0)).toBeTruthy();
    }
  });

  it("keeps dashboard-modal on the digichat skin without a user file picker", () => {
    const raw = readFileSync(resolve(examplesDir, "dashboard-modal.yaml"), "utf8");
    const cfg = parseDigichatConfig(loadYaml(raw), "dashboard-modal.yaml");
    expect(cfg.deployment?.chrome.skin).toBe("digichat");
    expect(welcomeTitle(cfg.deployment?.chrome.welcome)).toBe("Ask about this page.");
    expect(cfg.deployment?.chrome.mode).toBe("modal");
    expect(cfg.deployment?.features.attachments).toBe(false);
    expect(cfg.deployment?.features.pageContext).toBe("silent");
    expect(cfg.deployment?.gate.requiredPlanTier).toBe("desk");
    expect(cfg.deployment?.gate.showByok).toBe(true);
    expect(cfg.deployment?.gate.llmAccess).toBe("operator");
    expect(cfg.deployment?.models.default).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(cfg.deployment?.models.available).toEqual([
      "deepseek/deepseek-v4.1-flash-1017",
      "openai/gpt-oss-120b",
      "z-ai/glm-5.3-flash",
    ]);
    expect(cfg.deployment?.models.available.some((id) => id.endsWith(":free"))).toBe(
      false,
    );
  });

  it("pins product embed YAML to digichat skin + digigraph tool catalog", () => {
    const digithings = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "digithings-ai-embed.yaml"), "utf8")),
      "digithings-ai-embed.yaml",
    );
    const dt = digithings.hosts?.["digithings.ai"];
    expect(dt?.chrome.skin).toBe("digichat");
    expect(welcomeTitle(dt?.chrome.welcome)).toBe("Ask about digithings");
    expect(dt?.backend).toEqual({
      type: "digigraph",
      digisearchIndex: "digithings_docs",
      vaultPathPrefix: "clients/digithings",
    });
    expect(dt?.tools?.allowUserToggle).toBe(true);
    expect(dt?.tools?.catalog.map((t) => t.id)).toEqual([
      "digisearch",
      "digivault",
    ]);
    expect(dt?.tools?.catalog.find((t) => t.id === "digisearch")?.default).toBe(true);
    expect(dt?.tools?.catalog.find((t) => t.id === "digivault")?.default).toBe(true);
    expect(dt?.models.allowPicker).toBe(true);
    expect(dt?.gate.showContextMeter).toBe(true);
    expect(dt?.models.catalog).toBe(true);
    expect(dt?.models.default).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(dt?.models.available).toContain("deepseek/deepseek-v4.1-flash-1017");
    expect(dt?.models.available).toContain("deepseek/deepseek-v4.1-flash");
    expect(dt?.models.available).toContain("google/gemini-3.5-flash-lite");
    expect(dt?.models.available).toContain("openai/gpt-6-luna");
    expect(dt?.models.available).toContain("qwen/qwen3.8-flash");
    expect(dt?.models.available).toContain("z-ai/glm-5.3-flash");
    expect(dt?.models.available).toContain("z-ai/glm-5.3");
    expect(dt?.models.available).toContain("google/gemini-3.8-flash");
    expect(dt?.models.available).not.toContain("qwen/qwen3.8-max");
    expect(dt?.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });
    expect(dt?.models.picker?.groups.find((group) => group.premium)?.models.map((model) => model.id)).toEqual([
      "google/gemini-3.8-flash",
      "z-ai/glm-5.3",
    ]);
    expect(dt?.models.picker?.presets.find((preset) => preset.id === "reasoning")?.model).toBe(
      "z-ai/glm-5.3-flash",
    );
    expect(dt?.models.available).not.toContain("openai/gpt-5.6-luna");
    expect(dt?.models.available).not.toContain("google/gemini-3.1-flash-lite");
    expect(dt?.models.available).not.toContain("deepseek/deepseek-v4-pro");
    expect(dt?.models.available).not.toContain("z-ai/glm-4.7-flash");
    expect(dt?.models.available).not.toContain("openai/gpt-5.6-sol");
    expect(dt?.models.available).not.toContain("google/gemini-3.7-flash");
    expect(dt?.models.available.some((id) => id.endsWith(":free"))).toBe(false);
    expect(dt?.models.picker?.presets.map((preset) => preset.id)).toEqual([
      "auto",
      "reasoning",
      "fast",
      "light",
    ]);
    expect(dt?.models.picker?.groups.length).toBeGreaterThan(0);
    expect(dt?.mcp?.allowUserServers).toBe(false);
    expect(dt?.guardrails).toBeUndefined();
    expect(allowedForceTools(dt)).toEqual(["digisearch", "digivault"]);

    const occ = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "occ-embed.yaml"), "utf8")),
      "occ-embed.yaml",
    );
    const occHost = occ.hosts?.["occ.digithings.ai"];
    expect(occHost?.chrome.skin).toBe("digichat");
    expect(occHost?.backend.type).toBe("digigraph");
    expect(occHost?.guardrails).toBeUndefined();
    // backend.digisearchIndex was retired; Help search reaches the model only as
    // the digisearch MCP server, whose setup names the occ_help index.
    expect(occHost?.tools?.catalog).toEqual([]);
    const occServers = occHost?.mcp?.servers ?? [];
    expect(occServers.find((s) => s.id === "digisearch")?.setup?.index_name).toBe("occ_help");
    expect(occServers.find((s) => s.id === "digisearch")?.allowedTools).toEqual([
      "semantic",
      "web_search",
    ]);
    expect(occServers.find((s) => s.id === "digivault")?.allowedTools).toEqual([
      "search_notes",
      "search_tag",
      "backlinks",
    ]);
    expect(occHost?.gate?.webSearch).toBe(false);
    expect(occHost?.gate?.showContextMeter).toBeUndefined();
    expect(occHost?.gate?.lockSessionControls).toBe(true);
    expect(occHost?.features.modelPicker).toBe(true);
    expect(occHost?.models.catalog).toBe(true);
    expect(occHost?.models.allowPicker).toBe(true);
    expect(occHost?.models.picker?.presets[0]?.id).toBe("auto");
    expect(occHost?.models.occPicker).toBe(true);
    expect(occHost?.models.costPerWindow).toBeUndefined();
    expect(occHost?.models.available).toContain("z-ai/glm-5.3");
    expect(occHost?.models.available).toContain("google/gemini-3.8-flash");
    expect(occHost?.guardrails?.tokensPerMinute).toBeUndefined();
    expect(occHost?.models.picker?.presets.find((preset) => preset.id === "reasoning")?.model).toBe(
      "z-ai/glm-5.3-flash",
    );
    expect(occHost?.chrome.theme).toBe("light");
    expect(occHost?.mcp?.allowUserServers).toBe(false);
    expect(occHost?.mcp?.servers.map((s) => s.id)).toEqual([
      "zammad",
      "digisearch",
      "digivault",
    ]);
    expect(occHost?.mcp?.servers[0]?.tokenEnv).toBe("ZAMMAD_API_TOKEN");
    expect(occHost?.mcp?.servers[0]?.authHeader).toBe("Authorization");
    expect(allowedForceTools(occHost)).toEqual(["zammad", "digisearch", "digivault"]);
  });

  it("keeps the OCC picker locked unless occPicker is true", () => {
    const locked = parseDigichatConfig({
      version: 1,
      hosts: {
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          features: { modelPicker: true },
          gate: { lockSessionControls: true },
          models: {
            catalog: true,
            occPicker: false,
            costPerWindow: { usd: 0.0125565 },
          },
        },
      },
    });
    const host = locked.hosts?.["occ.digithings.ai"];
    expect(host?.models.available).toEqual([]);
    expect(host?.models.allowPicker).toBe(false);
    expect(host?.models.picker).toBeUndefined();
    expect(host?.models.default).toBeUndefined();
    expect(host?.features.modelPicker).toBe(false);
    expect(host?.gate.lockSessionControls).toBe(true);
    expect(host?.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });

    const open = parseDigichatConfig({
      version: 1,
      hosts: {
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          models: { catalog: true, occPicker: true, costPerWindow: { usd: 0.0125565 } },
        },
      },
    });
    const opened = open.hosts?.["occ.digithings.ai"];
    expect(opened?.features.modelPicker).toBe(true);
    expect(opened?.models.available).toContain("z-ai/glm-5.3");
    expect(
      opened?.models.picker?.presets.find((preset) => preset.id === "reasoning")?.model,
    ).toBe("z-ai/glm-5.3-flash");
    // OCC carries no premium meter, even when a row writes one (2.6.8).
    expect(opened?.models.costPerWindow).toBeUndefined();
  });

  it("parses operator MCP servers on the DataTap example without leaking URLs", () => {
    const cfg = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "datatap-mcp.yaml"), "utf8")),
      "datatap-mcp.yaml",
    );
    const dep = cfg.deployment;
    expect(dep?.mcp?.servers.map((s) => s.id)).toEqual(["datatap"]);
    expect(dep?.mcp?.allowUserServers).toBe(false);
    expect(allowedForceTools(dep)).toEqual(["digisearch", "digivault", "datatap"]);
  });

  it("denies web search on the DataTap tenant while keeping docs + MCP tools", () => {
    const cfg = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "datatap-mcp.yaml"), "utf8")),
      "datatap-mcp.yaml",
    );
    const dep = cfg.deployment;
    expect(dep?.gate?.webSearch).toBe(false);
    expect(dep?.tools?.catalog.some((t) => t.id === "web_search")).toBe(false);
  });

  it("ships a complete YAML install for every catalog template id", () => {
    const skinDir = resolve(examplesDir, "skins");
    for (const id of THREAD_SKINS) {
      const raw = readFileSync(resolve(skinDir, `${id}.yaml`), "utf8");
      const cfg = parseDigichatConfig(loadYaml(raw), id);
      expect(cfg.deployment?.chrome.skin).toBe(id);
      expect(cfg.deployment?.auth).toBe("anonymous");
      expect(cfg.deployment?.backend.type).toBe("digigraph");
      if (id === "digichat") {
        expect(cfg.deployment?.chrome.transcript.userAlign).toBe("left");
        expect(cfg.deployment?.chrome.theme).toBe("dark");
        expect(welcomeTitle(cfg.deployment?.chrome.welcome)).toBe("Ask a question");
        expect(cfg.deployment?.tools?.catalog ?? []).toEqual([]);
        expect(cfg.deployment?.features.attachments).toBe(true);
      }
    }
  });
});

describe("disclosure helpers", () => {
  it("maps visibility / defaultOpen / locked", () => {
    expect(disclosureIsVisible("off")).toBe(false);
    expect(disclosureIsVisible("collapsed")).toBe(true);
    expect(disclosureDefaultOpen("collapsed")).toBe(false);
    expect(disclosureDefaultOpen("expanded")).toBe(true);
    expect(disclosureDefaultOpen("locked_open")).toBe(true);
    expect(disclosureIsLocked("locked_open")).toBe(true);
    expect(disclosureIsLocked("expanded")).toBe(false);
  });
});

describe("McpServerSchema operator-static auth (#3841)", () => {
  it("accepts token/tokenEnv/authHeader on an operator MCP server", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "datatap",
              url: "https://mcp.datatap.example/mcp",
              tokenEnv: "DATATAP_MCP_TOKEN",
              authHeader: "X-API-Key",
            },
          ],
        },
      },
    });
    const server = cfg.deployment?.mcp?.servers?.[0];
    expect(server?.tokenEnv).toBe("DATATAP_MCP_TOKEN");
    expect(server?.authHeader).toBe("X-API-Key");
    expect(server?.token).toBeUndefined();
  });

  it("rejects a malformed authHeader value", () => {
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "acme",
          backend: { type: "digigraph" },
          mcp: {
            servers: [
              {
                id: "datatap",
                url: "https://mcp.datatap.example/mcp",
                authHeader: "bad header!",
              },
            ],
          },
        },
      }),
    ).toThrow();
  });
});

describe("McpServerSchema operator tool allowlist (DIG-284)", () => {
  it("parses an MCP server with allowedTools and mutatingTools", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "atlassian",
              url: "https://mcp.atlassian.com/v1/sse",
              allowedTools: ["addOrEditJiraIssueComment"],
              mutatingTools: ["addOrEditJiraIssueComment"],
            },
          ],
        },
      },
    });
    const server = cfg.deployment?.mcp?.servers?.[0];
    expect(server?.allowedTools).toEqual(["addOrEditJiraIssueComment"]);
    expect(server?.mutatingTools).toEqual(["addOrEditJiraIssueComment"]);
  });

  it("parses an allowlist as large as the widest real read-scope surface", () => {
    // digiquant's `scope="read"` server advertises 113 tools
    // (`READ_SCOPE_TOOLS` in digiquant/src/digiquant/mcp_server.py) and
    // `config/examples/dashboard-modal.yaml` is that row. So the entry bound
    // has to clear 113 with headroom — an allowlist the operator cannot
    // express is the silent whole-config parse failure this leaf removes, now
    // self-inflicted by a bound too small to hold our own corpus.
    const readScope = Array.from(
      { length: 113 },
      (_, i) => `digifetch_read_${String(i).padStart(3, "0")}`,
    );
    expect(readScope).toHaveLength(113);
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "digiquant",
              url: "https://mcp.digithings.ai/mcp",
              allowedTools: readScope,
            },
          ],
        },
      },
    });
    expect(cfg.deployment?.mcp?.servers?.[0]?.allowedTools).toHaveLength(113);
  });

  it("parses the longest tool name in the widest real read-scope surface", () => {
    // `dashboard_get_policy_gate_evaluation` is the longest name in digiquant's
    // `READ_SCOPE_TOOLS` — the same 113-tool surface as the test above. It ties
    // `MAX_MCP_TOOL_NAME_LENGTH` to our corpus rather than to a synthetic string:
    // a name bound that the widest row we actually ship has already cleared is a
    // bound we know something about.
    //
    // The literal 36 is asserted rather than imported. This file deliberately
    // does not import the bounds from `./mcp-servers`: a bound the test reads
    // out of the code moves when the code moves, and then pins nothing.
    const longest = "dashboard_get_policy_gate_evaluation";
    expect(longest).toHaveLength(36);
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "digiquant",
              url: "https://mcp.digithings.ai/mcp",
              allowedTools: [longest],
              mutatingTools: [longest],
            },
          ],
        },
      },
    });
    expect(cfg.deployment?.mcp?.servers?.[0]?.allowedTools).toEqual([longest]);
    expect(cfg.deployment?.mcp?.servers?.[0]?.mutatingTools).toEqual([longest]);
  });

  it("rejects an allowlist one entry over the bound, on either key", () => {
    // The other side of the 113-entry bound above (review #5061 round 2, S1).
    // Nothing pinned that these bounds reject: until now only the accepting side
    // was tested, so a bound that had quietly stopped rejecting would have gone
    // green. What that would hide is the expensive failure — an over-budget row
    // truncated to its first 256 entries, i.e. an allowlist that silently lost
    // tools, or a parse failure that takes the row's other servers with it.
    const overBudget = Array.from({ length: 257 }, (_, i) => `digifetch_read_${i}`);
    const parseWith = (allowedTools: string[], mutatingTools?: string[]) => ({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "digiquant",
              url: "https://mcp.digithings.ai/mcp",
              allowedTools,
              mutatingTools,
            },
          ],
        },
      },
    });
    expect(() => parseDigichatConfig(parseWith(overBudget))).toThrow();
    expect(() => parseDigichatConfig(parseWith(["search_tickets"], overBudget))).toThrow();
  });

  it("rejects a tool name one character over the name bound", () => {
    // Same two-sided argument for the name bound. 64 is the width of digigraph's
    // `prefixed_tool_name` truncation, so the 65th character is a name digigraph
    // cannot carry unambiguously — the whole reason the bound is where it is.
    const nameOf = (length: number) => "t".repeat(length);
    const parseWith = (allowedTools: string[]) => ({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        mcp: {
          servers: [
            {
              id: "atlassian",
              url: "https://mcp.atlassian.com/v1/sse",
              allowedTools,
            },
          ],
        },
      },
    });
    const atBound = parseDigichatConfig(parseWith([nameOf(64)]));
    expect(atBound.deployment?.mcp?.servers?.[0]?.allowedTools).toEqual([nameOf(64)]);
    expect(() => parseDigichatConfig(parseWith([nameOf(65)]))).toThrow();
  });

  it("still rejects an unknown key on an MCP server", () => {
    // The allowlist fields must not have loosened McpServerSchema from
    // `.strict()`. A typo'd key is still a hard parse failure rather than a
    // silently ignored field.
    expect(() =>
      parseDigichatConfig({
        version: 1,
        deployment: {
          slug: "acme",
          backend: { type: "digigraph" },
          mcp: {
            servers: [
              {
                id: "atlassian",
                url: "https://mcp.atlassian.com/v1/sse",
                allowdTools: ["addOrEditJiraIssueComment"],
              },
            ],
          },
        },
      }),
    ).toThrow();
  });
});

describe("allowlistModelId", () => {
  it("passes through when available is empty", () => {
    expect(allowlistModelId(undefined, "any-model")).toBe("any-model");
    expect(allowlistModelId({ available: [] }, undefined)).toBeUndefined();
    expect(allowlistModelId({ available: [], default: "d" }, undefined)).toBe("d");
  });

  it("fail-closes when available is non-empty", () => {
    const models = {
      default: "a",
      available: ["a", "b"],
    };
    expect(allowlistModelId(models, "b")).toBe("b");
    expect(allowlistModelId(models, "c")).toBeUndefined();
    expect(allowlistModelId(models, undefined)).toBe("a");
  });
});

describe("preset selection on the BFF", () => {
  const models = {
    default: "m/auto",
    available: ["m/auto", "m/reason", "m/light"],
    picker: {
      showFullList: true,
      groups: [],
      presets: [
        { id: "auto", label: "Auto", description: "", model: "m/auto" },
        { id: "reasoning", label: "Reasoning", description: "", model: "m/reason" },
        { id: "fast", label: "Fast", description: "", model: "m/off-list" },
        { id: "router", label: "Router", description: "", model: "openrouter/auto" },
      ],
    },
  };

  it("maps a preset token onto its model and re-checks the allowlist", () => {
    expect(resolveHouseModelSelection(models, "preset:reasoning")).toBe("m/reason");
    expect(resolveHouseModelSelection(models, " preset:auto ")).toBe("m/auto");
    // A preset whose model is not on the list is refused, not forwarded.
    expect(resolveHouseModelSelection(models, "preset:fast")).toBeUndefined();
    expect(resolveHouseModelSelection(models, "preset:nope")).toBeUndefined();
    expect(resolveHouseModelSelection(models, "preset:")).toBeUndefined();
  });

  it("keeps raw ids on the allowlist and refuses the rest", () => {
    expect(resolveHouseModelSelection(models, "m/light")).toBe("m/light");
    expect(resolveHouseModelSelection(models, "openai/gpt-5.6-sol")).toBeUndefined();
    expect(resolveHouseModelSelection(models, undefined)).toBe("m/auto");
  });

  it("builds the router list only for the router pick, never including the router", () => {
    expect(routerModelsHeader(models, "m/auto")).toBeUndefined();
    expect(routerModelsHeader(models, undefined)).toBeUndefined();
    const withRouter = { ...models, available: [...models.available, "openrouter/auto"] };
    expect(routerModelsHeader(withRouter, "openrouter/auto")).toBe("m/auto,m/reason,m/light");
    const withPremium = {
      ...withRouter,
      available: [...withRouter.available, "z-ai/glm-5.3"],
      picker: {
        ...withRouter.picker,
        groups: [
          {
            provider: "Premium",
            premium: true,
            models: [{ id: "z-ai/glm-5.3", label: "GLM 5.3" }],
          },
        ],
      },
    };
    expect(routerModelsHeader(withPremium, "openrouter/auto")).toBe("m/auto,m/reason,m/light");
    expect(premiumModelsHeader(withPremium)).toBe("z-ai/glm-5.3");
    const noRouterPreset = { ...models, picker: { ...models.picker, presets: [] } };
    expect(routerModelsHeader(noRouterPreset, "openrouter/auto")).toBeUndefined();
  });

  it("lets the catalog win over a hand list instead of failing the config", () => {
    const raw = loadYaml(
      readFileSync(resolve(examplesDir, "digithings-ai-embed.yaml"), "utf8"),
    ) as { hosts: Record<string, { models: Record<string, unknown> }> };
    const host = Object.keys(raw.hosts)[0]!;
    raw.hosts[host]!.models.available = ["openai/gpt-5.6-sol"];
    const parsed = parseDigichatConfig(raw, "mixed.yaml");
    const available = parsed.hosts?.[host]?.models.available ?? [];
    expect(available).not.toContain("openai/gpt-5.6-sol");
    expect(available).toContain("deepseek/deepseek-v4.1-flash-1017");
  });
});

describe("GateSchema searchEngine (#4724)", () => {
  it("accepts an allowlisted engine name", () => {
    expect(GateSchema.parse({ searchEngine: "exa" }).searchEngine).toBe("exa");
  });

  it("omits searchEngine when unset (auto by omission)", () => {
    expect(GateSchema.parse({}).searchEngine).toBeUndefined();
  });

  it("rejects an unknown engine name", () => {
    expect(() => GateSchema.parse({ searchEngine: "not-an-engine" })).toThrow();
  });
});
