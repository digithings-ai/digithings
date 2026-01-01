import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { CONTEXT_WINDOWS } from "@digithings/ui/chat/context-meter";
import { resolveModelCatalog } from "./model-picker-catalog";

describe("context windows", () => {
  it("matches the catalog context for every resolved picker model", () => {
    const catalog = JSON.parse(
      readFileSync(resolve(__dirname, "../../config/model-picker-catalog.json"), "utf8"),
    ) as { models: Array<{ id: string; context: number }> };
    const context = new Map(catalog.models.map((model) => [model.id, model.context]));
    const resolved = resolveModelCatalog(
      {
        default: "deepseek/deepseek-v4.1-flash-1017",
        priceCapUsdPerMillion: 2,
        showFullList: true,
      },
      { openRouterConfigured: false },
    );
    for (const id of resolved.available) {
      expect(CONTEXT_WINDOWS[id], id).toBe(context.get(id));
    }
  });

  it("uses the models.dev window for gpt-5.6-terra", () => {
    expect(CONTEXT_WINDOWS["gpt-5.6-terra"]).toBe(1_050_000);
    expect(CONTEXT_WINDOWS["openai/gpt-5.6-terra"]).toBe(1_050_000);
  });
});