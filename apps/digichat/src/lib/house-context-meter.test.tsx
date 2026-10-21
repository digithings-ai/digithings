// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { load as loadYaml } from "js-yaml";
import { cleanup, render, screen } from "@testing-library/react";
import { DigichatContextMeter } from "@digithings/ui/chat/context-meter";
import { parseDigichatConfig } from "./deploy-config/schema";
import { deploymentToEmbedTenant } from "./deploy-config/loader";
import { toEmbedClientConfig } from "./embed-client-config";
import { clientConfigFromEmbedTenant } from "./deploy-config/embed-bridge";
import { sessionModelSeed, showModelPicker } from "./session-model-seed";

vi.mock("@assistant-ui/react", () => ({
  useAuiState: (selector: (state: unknown) => unknown) =>
    selector({ thread: { messages: [] as unknown[] } }),
}));

afterEach(() => {
  cleanup();
});

const FLASH = "deepseek/deepseek-v4.1-flash-1017";

function paint(model: string) {
  return render(<DigichatContextMeter model={model} toolCount={0} />);
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
      slug: client.slug,
      available: client.models.available,
      defaultModel: client.models.default,
      showContextMeter: tenant.showContextMeter,
    });
    expect(model).toBe(FLASH);
    expect(client.models.available).toEqual([FLASH, "openai/gpt-oss-120b", "z-ai/glm-5.3-flash"]);
    paint(model);
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });

  it("renders the bar for the live house shape without opening the picker", () => {
    const client = clientConfigFromEmbedTenant({
      slug: "digithings",
      gateMode: "ungated",
      theme: "dark",
      skin: "digichat",
      accent: null,
      attribution: true,
      backendType: "digigraph",
      models: { available: [] },
    });
    expect(client.models.available).toEqual([]);
    const model = sessionModelSeed({
      slug: client.slug,
      available: client.models.available,
      defaultModel: client.models.default,
    });
    expect(model).toBe(FLASH);
    expect(
      showModelPicker({
        allowPicker: client.models.allowPicker,
        featureModelPicker: client.features.modelPicker,
        available: client.models.available,
      }),
    ).toBe(false);
    paint(model);
    expect(screen.getByRole("img", { name: /^Context / })).toBeTruthy();
  });

  it("keeps the meter off for the foundry trial and for an OCC host with an empty list", () => {
    const configDir = resolve(__dirname, "../../config");
    const trialName = readdirSync(configDir).find((entry) => entry.endsWith("-trial-foundry.yaml"));
    if (!trialName) throw new Error("foundry trial config is missing");
    const trialRaw = readFileSync(resolve(configDir, trialName), "utf8");
    const trial = parseDigichatConfig(loadYaml(trialRaw), trialName).deployment!;
    expect(trial.gate.showContextMeter).toBeUndefined();
    const trialClient = clientConfigFromEmbedTenant(
      toEmbedClientConfig(deploymentToEmbedTenant(trial)),
    );
    const trialModel = sessionModelSeed({
      slug: trialClient.slug,
      available: trialClient.models.available,
      defaultModel: trialClient.models.default,
      showContextMeter: true,
    });
    expect(trialClient.backendType).toBe("foundry");
    expect(trialClient.models.available).toEqual([]);
    expect(trialClient.models.allowPicker).toBe(false);
    expect(trialModel).toBe("");
    const { container: trialDom } = paint(trialModel);
    expect(trialDom.querySelector(".aui-context-meter")).toBeNull();

    const occRaw = readFileSync(resolve(__dirname, "../../config/examples/occ-embed.yaml"), "utf8");
    const occ = parseDigichatConfig(loadYaml(occRaw), "occ-embed.yaml").hosts![
      "occ.digithings.ai"
    ]!;
    expect(occ.gate.showContextMeter).toBeUndefined();
    expect(occ.features.modelPicker).toBe(false);
    const occYamlClient = clientConfigFromEmbedTenant(
      toEmbedClientConfig(deploymentToEmbedTenant(occ)),
    );
    expect(
      sessionModelSeed({
        slug: occYamlClient.slug,
        available: occYamlClient.models.available,
        defaultModel: occYamlClient.models.default,
        showContextMeter: occYamlClient.gate.showContextMeter,
      }),
    ).toBe("");
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
        slug: client.slug,
        available: client.models.available,
        defaultModel: client.models.default,
      }),
    ).toBe(FLASH);
  });
});
