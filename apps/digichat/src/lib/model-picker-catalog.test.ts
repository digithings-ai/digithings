import { describe, expect, it } from "vitest";
import catalogJson from "../../config/model-picker-catalog.json";
import deployModels from "../../config/digichat-deploy-models.json";
import {
  resolveModelCatalog,
  sessionAllowlistIds,
  type CatalogModel,
} from "./model-picker-catalog";

const models = catalogJson.models as CatalogModel[];

function policy() {
  return resolveModelCatalog(
    {
      presets: ["auto", "reasoning", "fast", "light", "router"],
      showFullList: true,
    },
    { openRouterConfigured: false },
  );
}

describe("model picker catalog", () => {
  it("names its price source and does not invent a Cheaper Inference router", () => {
    expect(catalogJson.source).toMatch(/cheaperinference.com\/markets/);
    expect(catalogJson.source).toMatch(/No chat\/completions/);
    expect(catalogJson.source.toLowerCase()).toMatch(/no router model/);
    expect(catalogJson.routers.map((router) => router.requires)).toEqual(["openrouter"]);
  });

  it("keeps both DeepSeek V4.1 Flash checkpoints and every DeepSeek row under the cap", () => {
    const resolved = policy();
    expect(resolved.available).toContain("deepseek/deepseek-v4.1-flash-1017");
    expect(resolved.available).toContain("deepseek/deepseek-v4.1-flash");
    const deepseek = models.filter(
      (model) =>
        model.provider === "DeepSeek" &&
        model.tools &&
        model.context >= catalogJson.policy.minContextTokens &&
        model.outputPerM <= catalogJson.policy.priceCapUsdPerMillion,
    );
    for (const model of deepseek) {
      expect(resolved.available).toContain(model.id);
    }
    expect(resolved.available).not.toContain("deepseek/deepseek-r1");
  });

  it("drops models over the output cap and keeps the pinned default if the cap would exclude it", () => {
    const resolved = policy();
    expect(resolved.available).not.toContain("openai/gpt-5.6-sol");
    expect(resolved.available).not.toContain("google/gemini-3.7-flash");
    const high = resolveModelCatalog(
      { default: "openai/gpt-5.6-sol", priceCapUsdPerMillion: 2, showFullList: true },
      { openRouterConfigured: false },
    );
    expect(high.default).toBe("openai/gpt-5.6-sol");
    expect(high.available).toContain("openai/gpt-5.6-sol");
  });

  it("picks Auto, Reasoning, Fast, and Light from the capped set", () => {
    const resolved = policy();
    const byId = Object.fromEntries(resolved.picker.presets.map((preset) => [preset.id, preset]));
    expect(byId.auto?.model).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(byId.auto?.description).toMatch(/DeepSeek V4.1 Flash 1017/);
    expect(byId.reasoning?.model).toBe("deepseek/deepseek-v4-pro");
    expect(byId.reasoning?.description).toMatch(/Best reasoning/);
    expect(byId.fast?.model).toBe("z-ai/glm-4.7-flash");
    expect(byId.fast?.description).toMatch(/Fastest/);
    expect(byId.light?.model).toBe("openai/gpt-oss-120b");
    expect(byId.light?.description).toMatch(/Lowest price/);
    expect(byId.router).toBeUndefined();
  });

  it("adds the OpenRouter router only when that provider is configured", () => {
    const open = resolveModelCatalog({}, { openRouterConfigured: true });
    const router = open.picker.presets.find((preset) => preset.id === "router");
    expect(router?.model).toBe("openrouter/auto");
    expect(router?.description).toMatch(/OpenRouter/);
    expect(open.available).toContain("openrouter/auto");
    expect(policy().available).not.toContain("openrouter/auto");
  });

  it("groups the full list by provider and can hide it", () => {
    const resolved = policy();
    expect(resolved.picker.groups.map((group) => group.provider)).toEqual([
      "DeepSeek",
      "OpenAI",
      "Google",
      "Z.ai",
      "Alibaba",
      "Xiaomi",
      "MiniMax",
    ]);
    const deepseek = resolved.picker.groups[0]?.models ?? [];
    const prices = deepseek.map(
      (row) => models.find((model) => model.id === row.id)?.outputPerM ?? 0,
    );
    expect(prices).toEqual([...prices].sort((a, b) => a - b));
    const hidden = resolveModelCatalog({ showFullList: false }, { openRouterConfigured: false });
    expect(hidden.picker.groups).toEqual([]);
    expect(hidden.available).toEqual([
      "deepseek/deepseek-v4.1-flash-1017",
      "deepseek/deepseek-v4-pro",
      "z-ai/glm-4.7-flash",
      "openai/gpt-oss-120b",
    ]);
  });

  it("matches the published deploy table and the session allowlist", () => {
    const resolved = policy();
    expect(deployModels.available).toEqual(resolved.available);
    expect(deployModels.default).toBe(resolved.default);
    expect(deployModels.sessionAllowlist).toEqual(sessionAllowlistIds());
    for (const id of deployModels.available) {
      expect(deployModels.sessionAllowlist).toContain(id);
    }
    expect(deployModels.sessionAllowlist).toContain("openrouter/auto");
    expect(deployModels.sessionAllowlist).toContain("openai/gpt-5.6-sol");
  });
});
