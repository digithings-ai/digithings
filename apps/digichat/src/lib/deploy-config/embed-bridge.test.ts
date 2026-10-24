import { describe, expect, it } from "vitest";
import { deploymentToEmbedTenant } from "./loader";
import { parseDigichatConfig } from "./schema";
import { clientConfigFromEmbedTenant } from "./embed-bridge";
import { toEmbedClientConfig, type EmbedClientConfig } from "../embed-client-config";
import { showModelPicker } from "../session-model-seed";

/**
 * The model chip is one decision, not two.
 *
 * `models.allowPicker` and `features.modelPicker` used to be computed
 * separately, so a row that locked its list could still carry the house
 * `features.modelPicker: true` and the toolbar drew an open-models button over
 * a list the visitor could not pick from (#6335).
 */
function clientFor(dep: Parameters<typeof deploymentToEmbedTenant>[0]) {
  return clientConfigFromEmbedTenant(toEmbedClientConfig(deploymentToEmbedTenant(dep)));
}

function embedFor(over: Partial<EmbedClientConfig>): EmbedClientConfig {
  return {
    slug: "embed",
    gateMode: "ungated",
    theme: "dark",
    skin: "digichat",
    accent: null,
    attribution: false,
    welcome: "Ask",
    welcomeBody: [],
    placeholder: "Ask",
    suggestions: [],
    attachments: false,
    pageContext: "visible",
    showByok: false,
    layout: "embed",
    showLanguageSelector: false,
    webSearch: false,
    backendType: "digigraph",
    ...over,
  };
}

function pickerOn(client: ReturnType<typeof clientFor>) {
  return showModelPicker({
    allowPicker: client.models?.allowPicker,
    featureModelPicker: client.features?.modelPicker,
    available: client.models?.available ?? [],
  });
}

describe("clientConfigFromEmbedTenant", () => {
  it("turns the chip off with the list when a row locks the picker", () => {
    // The shape that was broken: a customer row reusing the occ slug keeps its
    // own one-model list and resolves allowPicker: false.
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
    expect(dep.models?.allowPicker).toBe(false);

    const client = clientFor(dep);
    expect(client.models?.allowPicker).toBe(false);
    expect(client.features?.modelPicker).toBe(false);
    expect(pickerOn(client)).toBe(false);
  });

  it("keeps the chip on where the list is a real one", () => {
    const client = clientConfigFromEmbedTenant(
      embedFor({
        models: {
          available: ["vendor/a", "vendor/b"],
          default: "vendor/a",
          allowPicker: true,
        } as never,
      }),
    );
    expect(client.features?.modelPicker).toBe(true);
    expect(pickerOn(client)).toBe(true);
  });

  it("turns the chip off for a Foundry tenant with no enumerable list", () => {
    const client = clientConfigFromEmbedTenant(
      embedFor({ backendType: "foundry", models: { available: ["vendor/a"] } as never }),
    );
    expect(client.models?.available).toEqual([]);
    expect(client.models?.allowPicker).toBe(false);
    expect(client.features?.modelPicker).toBe(false);
    expect(pickerOn(client)).toBe(false);
  });
});
