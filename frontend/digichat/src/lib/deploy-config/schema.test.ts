import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import {
  allowlistModelId,
  disclosureDefaultOpen,
  disclosureIsLocked,
  disclosureIsVisible,
  parseDigichatConfig,
  welcomeTitle,
} from "./schema";
import { allowedForceTools } from "./force-tool";
import { THREAD_SKINS } from "@/lib/thread-skins";

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
    expect(cfg.deployment?.features.reasoning).toBe("collapsed");
    expect(cfg.deployment?.features.toolCalls).toBe("collapsed");
    expect(cfg.deployment?.chrome.defaultLanguage).toBe("en");
    expect(cfg.deployment?.chrome.transcript.userAlign).toBe("right");
    expect(cfg.deployment?.chrome.skin).toBe("base");
    expect(cfg.deployment?.cli.enabled).toBe(false);
    expect(cfg.deployment?.models.available).toEqual([]);
    expect(cfg.deployment?.gate.activityDetail).toBe("labels");
    expect(cfg.deployment?.features.attachments).toBe(true);
  });

  it("coerces reasoning/toolCalls booleans", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { reasoning: true, toolCalls: false },
      },
    });
    expect(cfg.deployment?.features.reasoning).toBe("collapsed");
    expect(cfg.deployment?.features.toolCalls).toBe("off");
  });

  it("accepts disclosure enums and cli.enabled", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      deployment: {
        slug: "acme",
        backend: { type: "digigraph" },
        features: { reasoning: "expanded", toolCalls: "locked_open" },
        chrome: { defaultLanguage: "de", transcript: { userAlign: "left" } },
        models: {
          default: "gpt-4o-mini",
          available: ["gpt-4o-mini", "gpt-4o"],
          allowPicker: true,
        },
        cli: { enabled: true },
      },
    });
    expect(cfg.deployment?.features.reasoning).toBe("expanded");
    expect(cfg.deployment?.features.toolCalls).toBe("locked_open");
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
    expect(cfg.deployment?.gate.requiredPlanTier).toBe("desk");
    expect(cfg.deployment?.gate.showByok).toBe(true);
    expect(cfg.deployment?.gate.llmAccess).toBe("operator");
    expect(cfg.deployment?.models.default).toBe("deepseek/deepseek-v4-flash");
    expect(cfg.deployment?.models.available).toEqual([
      "deepseek/deepseek-v4-flash",
      "deepseek/deepseek-v4-flash-0731",
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
    expect(welcomeTitle(dt?.chrome.welcome)).toBe("Ask about digithings.");
    expect(dt?.backend).toEqual({ type: "digigraph" });
    expect(dt?.tools?.allowUserToggle).toBe(true);
    expect(dt?.tools?.catalog.map((t) => t.id)).toEqual([
      "digisearch",
      "digivault",
      "web_search",
    ]);
    expect(dt?.tools?.catalog.find((t) => t.id === "web_search")?.default).toBe(true);
    expect(dt?.tools?.catalog.find((t) => t.id === "digisearch")?.default).toBe(true);
    expect(dt?.tools?.catalog.find((t) => t.id === "digivault")?.default).toBe(true);
    expect(dt?.models.allowPicker).toBe(true);
    expect(dt?.models.default).toBe("deepseek/deepseek-v4-flash");
    expect(dt?.models.available).toEqual([
      "deepseek/deepseek-v4-flash",
      "deepseek/deepseek-v4-flash-0731",
      "openai/gpt-oss-120b",
      "z-ai/glm-5.3-flash",
    ]);
    expect(dt?.models.available.some((id) => id.endsWith(":free"))).toBe(false);
    expect(dt?.models.available).not.toContain("google/gemini-3.1-flash-lite");
    expect(dt?.models.available).not.toContain("openai/gpt-5.6-luna");
    expect(allowedForceTools(dt)).toEqual(["digisearch", "digivault"]);

    const occ = parseDigichatConfig(
      loadYaml(readFileSync(resolve(examplesDir, "occ-embed.yaml"), "utf8")),
      "occ-embed.yaml",
    );
    const occHost = occ.hosts?.["occ.digithings.ai"];
    expect(occHost?.chrome.skin).toBe("digichat");
    expect(occHost?.backend.type).toBe("digigraph");
    if (occHost?.backend.type === "digigraph") {
      expect(occHost.backend.digisearchIndex).toBe("occ_help");
      expect(occHost.backend.vaultPathPrefix).toBe("clients/online-compliance-center");
    }
    expect(occHost?.tools?.catalog.map((t) => t.id)).toEqual(["digisearch", "digivault"]);
    expect(occHost?.tools?.catalog.some((t) => t.id === "web_search")).toBe(false);
    expect(allowedForceTools(occHost)).toEqual(["digisearch", "digivault"]);
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
