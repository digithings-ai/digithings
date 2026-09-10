import { describe, expect, it } from "vitest";
import { DEFAULT_CLIENT_CONFIG, toDigichatClientConfig } from "./client-projection";
import { clientConfigFromEmbedTenant } from "./embed-bridge";
import type { EmbedTenantClientConfig } from "@/lib/embed-client-config";
import type { DigichatDeployment } from "./schema";

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

describe("baseline embed models catalog (Cheaper Inference default)", () => {
  it("ships the 4-slug catalog with deepseek default and an enabled picker", () => {
    expect(DEFAULT_CLIENT_CONFIG.models).toEqual({
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
