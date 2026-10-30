// @vitest-environment happy-dom
/**
 * The two product chats open with the model chip and a usable picker when the
 * tenant registry names no model policy. That is the live registry today:
 * #6193 made the picker opt-in (`models.catalog`, and `occPicker` on OCC), so
 * the chip vanished on digithings.ai and OCC. Chris signed off the OCC picker
 * on 21 Oct 2026, 19:19 Rome. OCC is unmetered; digithings.ai keeps its
 * per-visitor premium window. A Foundry tenant stays closed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { DigichatComposerToolbar } from "@digithings/ui/chat/composer-toolbar";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import { deploymentToEmbedTenant, loadDigichatConfig } from "./deploy-config/loader";
import {
  allowlistModelId,
  parseDigichatConfig,
  type DigichatDeployment,
} from "./deploy-config/schema";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";
import { toEmbedClientConfig } from "./embed-client-config";
import { premiumIdsFromGroups } from "./model-picker-catalog";
import { sessionModelSeed, showModelPicker } from "./session-model-seed";

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (selector: (state: unknown) => unknown) =>
    selector({ thread: { messages: [] as unknown[] } }),
  // The stock thread's trace builds its chain grouping at import time.
  groupPartByType: () => () => [],
}));

afterEach(() => {
  cleanup();
});

function footer(input: { showModels: boolean; model: string }) {
  const noop = () => {};
  const prefs: EmbedChatPrefsApi = {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: input.model },
    setWebSearch: noop,
    setDigisearch: noop,
    setVault: noop,
    setExtraTool: noop,
    extraToolOn: () => true,
    setMcpConfig: noop,
    removeMcpConfig: noop,
    setLanguage: noop,
    setToolbar: noop,
    setScrollbars: noop,
    setDensity: noop,
    setView: noop,
    setThinking: noop,
    setModel: noop,
    setEffort: noop,
    setSearchEngine: noop,
    reset: noop,
    tenantAllowsWeb: true,
    showByok: false,
    showModels: input.showModels,
    showContextMeter: false,
    hasDigisearch: false,
    hasVault: false,
    hasSessions: false,
    hasArtifacts: false,
    allowUserMcp: false,
    allowAddMcp: false,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "test-session",
    openSettings: noop,
    openHelp: noop,
    openTools: noop,
    openMcp: noop,
    openByok: noop,
    openModels: noop,
    openEffort: noop,
    openSearchEngine: noop,
    openView: noop,
    openDensity: noop,
    openThinking: noop,
    openLanguage: noop,
    openSessions: noop,
    openArtifacts: noop,
    newThread: noop,
    compactThread: noop,
    undo: noop,
    redo: noop,
  };
  return render(<DigichatComposerToolbar prefs={prefs} />);
}

/** Registry rows shaped like the live copy: no `models` block on either chat. */
const LIVE_SHAPED_REGISTRY = JSON.stringify({
  "digithings.ai": {
    slug: "digithings",
    aliases: ["www.digithings.ai"],
    token: "unused-for-first-party",
    backend: { type: "digigraph" },
    gateMode: "ungated",
    llmAccess: "free_then_byok",
  },
  "occ.digithings.ai": {
    slug: "occ",
    token: "fixture-token-123",
    backend: { type: "digigraph" },
    gateMode: "ungated",
    lockSessionControls: true,
    llmAccess: "free_then_byok",
  },
  "trial.example": {
    slug: "trial",
    token: "fixture-trial-token",
    backend: {
      type: "foundry",
      projectEndpoint: "https://trial.example/api/projects/p",
      agentName: "agent",
    },
    gateMode: "ungated",
  },
});

function live(host: string): DigichatDeployment {
  const cfg = loadDigichatConfig({
    fileContents: null,
    env: { DIGICHAT_EMBED_TENANTS: LIVE_SHAPED_REGISTRY },
  });
  const dep = cfg.hosts?.[host];
  if (!dep) throw new Error(`no host ${host}`);
  return dep;
}

function toolbarFor(dep: DigichatDeployment) {
  const tenantConfig = toEmbedClientConfig(deploymentToEmbedTenant(dep));
  const client = clientConfigFromEmbedTenant(tenantConfig);
  const picker = showModelPicker({
    allowPicker: client.models.allowPicker,
    featureModelPicker: client.features.modelPicker,
    available: client.models.available,
  });
  const model = sessionModelSeed({
    available: client.models.available,
    defaultModel: client.models.default,
  });
  return { tenantConfig, client, picker, model };
}

describe("product chats open with the model picker", () => {
  it("digithings.ai shows the model name and a picker over the capped list, metered per visitor", () => {
    const dep = live("digithings.ai");
    expect(dep.models.catalog).toBe(true);
    expect(dep.models.allowPicker).toBe(true);
    expect(dep.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });
    const { tenantConfig, client, picker, model } = toolbarFor(dep);
    expect(tenantConfig.models?.allowPicker).toBe(true);
    expect(picker).toBe(true);
    expect(model).not.toBe("");
    expect(client.models.available).toContain(model);
    expect(client.models.picker?.presets.map((p) => p.id)).toEqual([
      "auto",
      "reasoning",
      "fast",
      "light",
    ]);
    footer({ showModels: picker, model });
    const chip = screen.getByRole("button", { name: "Open models" });
    expect(chip.textContent).toBe(model);
  });

  it("OCC shows the model name and the full catalog picker, with no meter and no TPM limit", () => {
    const dep = live("occ.digithings.ai");
    expect(dep.models.occPicker).toBeUndefined();
    expect(dep.features.modelPicker).toBe(true);
    expect(dep.models.costPerWindow).toBeUndefined();
    expect(dep.guardrails?.tokensPerMinute).toBeUndefined();
    expect(dep.gate.lockSessionControls).toBe(true);
    const { client, picker, model } = toolbarFor(dep);
    expect(picker).toBe(true);
    expect(model).not.toBe("");
    // Unrestricted: every catalog model the house lists, Premium included.
    const house = toolbarFor(live("digithings.ai")).client;
    expect(client.models.available).toEqual(house.models.available);
    // One shared list and one shared set of modes; only usage limits differ.
    expect(client.models.picker?.presets).toEqual(house.models.picker?.presets);
    expect(client.models.picker?.presets.map((preset) => preset.label)).toEqual([
      "Default",
      "Reasoning",
      "Fast",
      "Light",
    ]);
    const premium = premiumIdsFromGroups(client.models.picker?.groups);
    expect(premium.length).toBeGreaterThan(0);
    for (const id of premium) expect(client.models.available).toContain(id);
    footer({ showModels: picker, model });
    expect(screen.getByRole("button", { name: "Open models" }).textContent).toBe(model);
  });

  it("the public chat stays restricted: picks outside the list are refused, premium is metered", () => {
    const house = live("digithings.ai");
    const occ = live("occ.digithings.ai");
    expect(house.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });
    expect(occ.models.costPerWindow).toBeUndefined();
    expect(allowlistModelId(house.models, "vendor/not-in-the-catalog")).toBeUndefined();
    const pick = house.models.available[0]!;
    expect(allowlistModelId(house.models, pick)).toBe(pick);
  });

  it("keeps the Foundry tenant closed", () => {
    const { client, picker } = toolbarFor(live("trial.example"));
    expect(picker).toBe(false);
    expect(client.models.available).toEqual([]);
    footer({ showModels: picker, model: "" });
    expect(screen.queryByRole("button", { name: "Open models" })).toBeNull();
  });

  it("honours an explicit off switch on either chat", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          models: { allowPicker: false },
        },
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          models: { occPicker: false },
        },
      },
    });
    expect(toolbarFor(cfg.hosts!["digithings.ai"]!).picker).toBe(false);
    expect(toolbarFor(cfg.hosts!["occ.digithings.ai"]!).picker).toBe(false);
    expect(cfg.hosts!["occ.digithings.ai"]!.features.modelPicker).toBe(false);
  });

  it("keeps a registry catalog policy as written", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          models: {
            catalog: true,
            presets: ["auto"],
            priceCapUsdPerMillion: 2,
            costPerWindow: { usd: 0.01 },
          },
        },
      },
    });
    const dep = cfg.hosts!["digithings.ai"]!;
    expect(dep.models.picker?.presets.map((p) => p.id)).toEqual(["auto"]);
    expect(dep.models.costPerWindow?.usd).toBe(0.01);
    expect(toolbarFor(dep).picker).toBe(true);
  });
  it("keeps the house window when the row writes a catalog policy without one", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          models: { catalog: true },
        },
      },
    });
    const dep = cfg.hosts!["digithings.ai"]!;
    expect(dep.models.costPerWindow).toEqual({ usd: 0.0125565, windowSeconds: 86400 });
    expect(dep.models.allowPicker).toBe(true);
    expect(dep.features.modelPicker).toBe(true);
  });

  it("strips a meter and a TPM limit an OCC row writes; keeps the tool-call cap", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          guardrails: {
            maxToolCallsPerTurn: 8,
            answerAt: 0.6,
            pauseAt: 0.8,
            tokensPerMinute: { user: 1000 },
          },
          models: {
            catalog: true,
            priceCapUsdPerMillion: 2,
            costPerWindow: { usd: 0.01 },
          },
        },
      },
    });
    const dep = cfg.hosts!["occ.digithings.ai"]!;
    expect(dep.models.costPerWindow).toBeUndefined();
    expect(dep.guardrails?.tokensPerMinute).toBeUndefined();
    expect(dep.guardrails?.maxToolCallsPerTurn).toBe(8);
    expect(dep.guardrails?.answerAt).toBe(0.6);
    expect(dep.guardrails?.pauseAt).toBe(0.8);
    expect(toolbarFor(dep).picker).toBe(true);
  });

  it("keeps the tool-call cap and answer guard on both product chats", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          guardrails: {
            maxToolCallsPerTurn: 8,
            answerAt: 0.6,
            pauseAt: 0.8,
            tokensPerMinute: { user: 1000 },
          },
        },
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          guardrails: {
            maxToolCallsPerTurn: 8,
            answerAt: 0.6,
            pauseAt: 0.8,
            tokensPerMinute: { user: 1000 },
          },
        },
      },
    });
    const house = cfg.hosts!["digithings.ai"]!;
    const occ = cfg.hosts!["occ.digithings.ai"]!;
    for (const dep of [house, occ]) {
      expect(dep.guardrails?.maxToolCallsPerTurn).toBe(8);
      expect(dep.guardrails?.answerAt).toBe(0.6);
      expect(dep.guardrails?.pauseAt).toBe(0.8);
    }
    // Only the per-visitor token limiting differs.
    expect(house.guardrails?.tokensPerMinute).toEqual({ user: 1000 });
    expect(occ.guardrails?.tokensPerMinute).toBeUndefined();
    expect(house.models.available).toEqual(occ.models.available);
  });

  it("grants nothing to a customer host that reuses a product slug", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "acme.example": { slug: "occ", backend: { type: "digigraph" } },
        "beta.example": { slug: "digithings", backend: { type: "digigraph" } },
        "plain.example": { slug: "plain", backend: { type: "digigraph" } },
      },
    });
    for (const host of ["acme.example", "beta.example", "plain.example"]) {
      const dep = cfg.hosts![host]!;
      expect(toolbarFor(dep).picker).toBe(false);
      expect(dep.models.catalog).toBeUndefined();
      expect(dep.models.costPerWindow).toBeUndefined();
    }
  });

  it("keeps a Foundry backend on a product host closed", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: {
            type: "foundry",
            projectEndpoint: "https://trial.example/api/projects/p",
            agentName: "agent",
          },
        },
      },
    });
    const dep = cfg.hosts!["digithings.ai"]!;
    expect(dep.models.catalog).toBeUndefined();
    expect(toolbarFor(dep).picker).toBe(false);
  });

  it("leaves a hand-written list without a picker grant", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "digithings.ai": {
          slug: "digithings",
          backend: { type: "digigraph" },
          models: { available: ["vendor/model-a"] },
        },
      },
    });
    const dep = cfg.hosts!["digithings.ai"]!;
    expect(dep.models.available).toEqual(["vendor/model-a"]);
    expect(dep.models.allowPicker).toBeUndefined();
  });
  it("locked OCC still drops a written meter and TPM", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "occ.digithings.ai": {
          slug: "occ",
          backend: { type: "digigraph" },
          guardrails: { tokensPerMinute: { user: 1000 } },
          models: {
            occPicker: false,
            priceCapUsdPerMillion: 2,
            costPerWindow: { usd: 0.01 },
          },
        },
      },
    });
    const dep = cfg.hosts!["occ.digithings.ai"]!;
    expect(toolbarFor(dep).picker).toBe(false);
    expect(dep.models.costPerWindow).toBeUndefined();
    expect(dep.guardrails?.tokensPerMinute).toBeUndefined();
  });

  it("a customer row reusing the occ slug keeps its own model allowlist", () => {
    const cfg = parseDigichatConfig({
      version: 1,
      hosts: {
        "acme.example": {
          slug: "occ",
          backend: { type: "digigraph" },
          models: { available: ["vendor/model-a"], default: "vendor/model-a" },
        },
      },
    });
    const dep = cfg.hosts!["acme.example"]!;
    expect(dep.models.available).toEqual(["vendor/model-a"]);
    expect(dep.models.default).toBe("vendor/model-a");
    expect(dep.models.allowPicker).toBe(false);
    expect(toolbarFor(dep).picker).toBe(false);
  });
});
