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
    expect(catalogJson.policy.priceCapUsdPerMillion).toBe(2);
    expect(catalogJson.policy.premiumCapUsdPerMillion).toBe(2.5);
    expect(catalogJson.policy.latestGenerationsPerFamily).toBe(1);
    expect(catalogJson.policy.maxAgeDays).toBeNull();
    expect(catalogJson.policy.asOf).toBe("2026-10-21");
    expect(catalogJson.routers.map((router) => router.requires)).toEqual(["openrouter"]);
  });

  it("keeps only the newest generation of each family under the cap", () => {
    const resolved = policy();
    expect(resolved.available).toEqual([
      "deepseek/deepseek-v4.1-flash-1017",
      "deepseek/deepseek-v4.1-flash",
      "openai/gpt-oss-120b",
      "openai/gpt-6-luna",
      "google/gemini-3.5-flash-lite",
      "z-ai/glm-5.3-flash",
      "qwen/qwen3.8-flash",
      "qwen/qwen3.8-27b",
      "xiaomi/mimo-v2.6-flash",
      "xiaomi/mimo-v2.6-pro",
      "minimax/minimax-m3",
      "google/gemini-3.8-flash",
      "z-ai/glm-5.3",
    ]);
    const premium = resolved.picker.groups.find((group) => group.premium);
    expect(premium?.provider).toBe("Premium");
    expect(premium?.models.map((model) => model.id)).toEqual([
      "google/gemini-3.8-flash",
      "z-ai/glm-5.3",
    ]);
    expect(resolved.picker.presets.find((preset) => preset.id === "reasoning")?.model).toBe(
      "z-ai/glm-5.3-flash",
    );
    for (const id of [
      "deepseek/deepseek-v4-pro",
      "deepseek/deepseek-v4-flash",
      "deepseek/deepseek-v4-flash-0731",
      "deepseek/deepseek-v4-flash-0731-fast",
      "deepseek/deepseek-v4-pro-0813",
      "deepseek/deepseek-v3.2",
      "deepseek/deepseek-v3.1",
      "deepseek/deepseek-r1",
      "z-ai/glm-4.7-flash",
      "openai/gpt-5.6-luna",
      "openai/gpt-5-mini",
      "google/gemini-3.1-flash-lite",
    ]) {
      expect(models.some((model) => model.id === id)).toBe(true);
      expect(resolved.available).not.toContain(id);
    }
    expect(models.some((model) => model.id === "google/gemma-4-31b-it")).toBe(false);
  });

  it("drops models over the output cap and keeps a pinned current-generation default", () => {
    const resolved = policy();
    expect(resolved.available).toContain("z-ai/glm-5.3");
    expect(resolved.available).toContain("google/gemini-3.8-flash");
    expect(resolved.available).not.toContain("openai/gpt-6.1-sol");
    expect(resolved.available).not.toContain("qwen/qwen3.8-max");
    expect(resolved.picker.presets.map((preset) => preset.model)).not.toContain("z-ai/glm-5.3");
    expect(resolved.picker.presets.map((preset) => preset.model)).not.toContain(
      "google/gemini-3.8-flash",
    );
    const high = resolveModelCatalog(
      { default: "z-ai/glm-5.3", priceCapUsdPerMillion: 2, showFullList: true },
      { openRouterConfigured: false },
    );
    expect(high.default).toBe("z-ai/glm-5.3");
    expect(high.available).toContain("z-ai/glm-5.3");
    expect(() =>
      resolveModelCatalog(
        { default: "openai/gpt-5.6-sol", priceCapUsdPerMillion: 2 },
        { openRouterConfigured: false },
      ),
    ).toThrow(/current generation/);
  });

  it("brings the previous generation back when the catalog keeps two", () => {
    const wide = resolveModelCatalog(
      { latestGenerationsPerFamily: 2, showFullList: true },
      { openRouterConfigured: false },
    );
    expect(wide.available).toContain("deepseek/deepseek-v4-pro");
    expect(wide.available).toContain("z-ai/glm-4.7-flash");
    expect(wide.available).toContain("openai/gpt-5.6-luna");
    expect(wide.available).not.toContain("deepseek/deepseek-v3.2");
    expect(wide.available).not.toContain("openai/gpt-5-mini");
    expect(wide.picker.presets.find((preset) => preset.id === "reasoning")?.model).toBe(
      "deepseek/deepseek-v4-pro",
    );
  });

  it("drops a dated checkpoint past maxAgeDays and keeps an undated one", () => {
    expect(() =>
      resolveModelCatalog({ maxAgeDays: 3 }, { openRouterConfigured: false }),
    ).toThrow(/current generation/);
    const aged = resolveModelCatalog(
      { maxAgeDays: 3, default: "z-ai/glm-5.3-flash", priceCapUsdPerMillion: 20 },
      { openRouterConfigured: false },
    );
    expect(aged.available).toContain("z-ai/glm-5.3-flash");
    expect(aged.available).toContain("z-ai/glm-5.3");
    expect(aged.available).not.toContain("deepseek/deepseek-v4.1-flash-1017");
    expect(aged.available).not.toContain("qwen/qwen3.8-max-0902");
  });

  it("picks Auto, Reasoning, Fast, and Light from the newest capped set", () => {
    const resolved = policy();
    const byId = Object.fromEntries(resolved.picker.presets.map((preset) => [preset.id, preset]));
    expect(byId.auto?.model).toBe("deepseek/deepseek-v4.1-flash-1017");
    expect(byId.auto?.description).toMatch(/DeepSeek V4.1 Flash 1017/);
    expect(byId.reasoning?.model).toBe("z-ai/glm-5.3-flash");
    expect(byId.reasoning?.description).toMatch(/Best reasoning/);
    expect(byId.fast?.model).toBe("google/gemini-3.5-flash-lite");
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
      "Premium",
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
      "z-ai/glm-5.3-flash",
      "google/gemini-3.5-flash-lite",
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
    // Standard ids are at or under $2. Premium ids are above $2 and at or under $2.50. No router.
    expect(deployModels.sessionAllowlist).toEqual(deployModels.available);
    expect(deployModels.sessionAllowlist).not.toContain("openrouter/auto");
    const premiumIds =
      resolved.picker.groups.find((group) => group.premium)?.models.map((model) => model.id) ??
      [];
    expect(premiumIds).toEqual(["google/gemini-3.8-flash", "z-ai/glm-5.3"]);
    const catalogRows = JSON.parse(JSON.stringify(catalogJson)).models as Array<{
      id: string;
      outputPerM: number;
    }>;
    for (const id of deployModels.sessionAllowlist) {
      const row = catalogRows.find((model) => model.id === id);
      if (id === deployModels.default) continue;
      expect(row?.outputPerM ?? Infinity).toBeLessThanOrEqual(2.5);
      const premium = premiumIds.includes(id);
      if (premium) expect(row?.outputPerM ?? 0).toBeGreaterThan(2);
      else expect(row?.outputPerM ?? Infinity).toBeLessThanOrEqual(2);
    }
  });
});
