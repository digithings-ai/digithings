// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { cleanup, render, screen } from "@testing-library/react";
import { DigichatContextMeter } from "@digithings/ui/chat/context-meter";
import { DigichatComposerToolbar } from "@digithings/ui/chat/composer-toolbar";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";
import { parseDigichatConfig } from "./deploy-config/schema";
import { deploymentToEmbedTenant } from "./deploy-config/loader";
import { toEmbedClientConfig } from "./embed-client-config";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";
import {
  contextMeterEnabled,
  contextMeterModel,
  sessionModelSeed,
  showModelPicker,
} from "./session-model-seed";

const thread = vi.hoisted(() => ({ messages: [] as unknown[] }));

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (selector: (state: unknown) => unknown) =>
    selector({ thread: { messages: thread.messages } }),
}));

afterEach(() => {
  thread.messages = [];
  cleanup();
});

const FLASH = "deepseek/deepseek-v4.1-flash";

function paint(model: string) {
  return render(<DigichatContextMeter model={model} toolCount={0} />);
}

function footer(input: { showContextMeter?: boolean; meterModel?: string; model?: string }) {
  const noop = () => {};
  const prefs: EmbedChatPrefsApi = {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: input.model ?? "" },
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
    showModels: true,
    showContextMeter: input.showContextMeter,
    meterModel: input.meterModel,
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

describe("house host context meter", () => {
  it("renders the existing bar for the digithings.ai YAML host", () => {
    const raw = readFileSync(
      resolve(__dirname, "../../config/examples/digithings-ai-embed.yaml"),
      "utf8",
    );
    const host = parseDigichatConfig(loadYaml(raw), "digithings-ai-embed.yaml").hosts?.[
      "digithings.ai"
    ];
    expect(host?.gate.showContextMeter).toBe(true);
    expect(host?.models.allowPicker).toBe(true);
    const tenant = deploymentToEmbedTenant(host!);
    const client = clientConfigFromEmbedTenant(toEmbedClientConfig(tenant));
    const model = sessionModelSeed({
      available: client.models.available,
      defaultModel: client.models.default,
    });
    expect(model).toBe(FLASH);
    expect(contextMeterModel({ sessionModel: model })).toBe(FLASH);
    expect(client.models.available).toContain(FLASH);
    expect(client.models.default).toBe(FLASH);
    const enabled = contextMeterEnabled(host?.gate.showContextMeter, host?.slug);
    expect(enabled).toBe(true);
    footer({ showContextMeter: enabled, meterModel: model, model });
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });

  it("shows no house meter in this release when the tenant publishes no models", () => {
    const client = clientConfigFromEmbedTenant({
      slug: "digithings",
      gateMode: "ungated",
      theme: "dark",
      skin: "digichat",
      accent: null,
      attribution: true,
      backendType: "digigraph",
      showContextMeter: true,
      models: { available: [], default: FLASH },
    });
    expect(client.models.available).toEqual([]);
    const model = sessionModelSeed({
      available: client.models.available,
      defaultModel: client.models.default,
    });
    expect(model).toBe("");
    const meterModel = contextMeterModel({ sessionModel: model });
    expect(meterModel).toBe("");
    expect(
      showModelPicker({
        allowPicker: client.models.allowPicker,
        featureModelPicker: client.features.modelPicker,
        available: client.models.available,
      }),
    ).toBe(false);
    const enabled = contextMeterEnabled(true, "digithings");
    expect(enabled).toBe(true);
    const { container } = footer({ showContextMeter: enabled, meterModel, model });
    expect(container.querySelector(".aui-context-meter")).toBeNull();
  });

  it("sizes the bar to the model the turn reported", () => {
    thread.messages = [
      {
        metadata: {
          custom: { model: "z-ai/glm-4.7-flash", usage: { inputTokens: 0 } },
        },
      },
    ];
    paint(FLASH);
    expect(screen.getByRole("img", { name: "Context 0 / 200.0k tokens" })).toBeTruthy();

    thread.messages = [
      {
        metadata: {
          custom: { model: "digigraph-rag", usage: { inputTokens: 12 } },
        },
      },
    ];
    paint(FLASH);
    expect(screen.getByRole("img", { name: "Context 12 / 1.0m tokens" })).toBeTruthy();
  });

  it("does not treat a built-in object key as a context window", () => {
    const { container } = paint("constructor");
    expect(container.querySelector(".aui-context-meter")).toBeNull();
    thread.messages = [
      {
        metadata: {
          custom: { model: "constructor", usage: { inputTokens: 0 } },
        },
      },
    ];
    paint(FLASH);
    expect(screen.getByRole("img", { name: "Context 0 / 1.0m tokens" })).toBeTruthy();
  });

  it("renders no meter for occ when the flag is off, even with a known window", () => {
    const occRaw = readFileSync(resolve(__dirname, "../../config/examples/occ-embed.yaml"), "utf8");
    const occ = parseDigichatConfig(loadYaml(occRaw), "occ-embed.yaml").hosts![
      "occ.digithings.ai"
    ]!;
    expect(occ.gate.showContextMeter).toBeUndefined();
    const occClient = clientConfigFromEmbedTenant(
      toEmbedClientConfig(deploymentToEmbedTenant(occ)),
    );
    const model = sessionModelSeed({
      available: occClient.models.available,
      defaultModel: occClient.models.default,
    });
    expect(model).toBe(FLASH);
    const enabled = contextMeterEnabled(occ.gate.showContextMeter, occ.slug);
    expect(enabled).toBe(false);
    const { container } = footer({
      showContextMeter: enabled,
      meterModel: contextMeterModel({ sessionModel: model }),
      model,
    });
    expect(container.querySelector(".aui-context-meter")).toBeNull();
  });

  it("renders no meter for an embed config that does not enable it", () => {
    const client = clientConfigFromEmbedTenant({
      slug: "example",
      gateMode: "ungated",
      theme: "dark",
      skin: "digichat",
      accent: null,
      attribution: true,
      backendType: "digigraph",
    });
    const model = sessionModelSeed({
      available: client.models.available,
      defaultModel: client.models.default,
    });
    expect(model).toBe(FLASH);
    const enabled = contextMeterEnabled(undefined, client.slug);
    expect(enabled).toBe(false);
    const { container } = footer({
      showContextMeter: enabled,
      meterModel: contextMeterModel({ sessionModel: model }),
      model,
    });
    expect(container.querySelector(".aui-context-meter")).toBeNull();
  });

  it("keeps the foundry trial off the meter", () => {
    const configDir = resolve(__dirname, "../../config");
    const trialName = readdirSync(configDir).find((entry) => entry.endsWith("-trial-foundry.yaml"));
    if (!trialName) throw new Error("foundry trial config is missing");
    const trialRaw = readFileSync(resolve(configDir, trialName), "utf8");
    const trial = parseDigichatConfig(loadYaml(trialRaw), trialName).deployment!;
    expect(trial.gate.showContextMeter).toBeUndefined();
    const trialClient = clientConfigFromEmbedTenant(
      toEmbedClientConfig(deploymentToEmbedTenant(trial)),
    );
    expect(trialClient.backendType).toBe("foundry");
    expect(trialClient.models.available).toEqual([]);
    expect(trialClient.models.allowPicker).toBe(false);
    const enabled = contextMeterEnabled(trial.gate.showContextMeter, trial.slug);
    expect(enabled).toBe(false);
    const { container } = footer({ showContextMeter: enabled, meterModel: FLASH, model: FLASH });
    expect(container.querySelector(".aui-context-meter")).toBeNull();
  });

  it("keeps the OCC picker closed when models are omitted and the catalog is inherited", () => {
    const client = clientConfigFromEmbedTenant({
      slug: "occ",
      gateMode: "ungated",
      theme: "light",
      skin: "digichat",
      accent: null,
      attribution: true,
      backendType: "digigraph",
    });
    expect(client.models.available).toContain(FLASH);
    expect(client.models.default).toBe(FLASH);
    expect(
      showModelPicker({
        allowPicker: client.models.allowPicker,
        featureModelPicker: client.features.modelPicker,
        available: client.models.available,
      }),
    ).toBe(false);
    expect(
      sessionModelSeed({
        available: client.models.available,
        defaultModel: client.models.default,
      }),
    ).toBe(FLASH);
  });
});
