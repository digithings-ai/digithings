import { describe, expect, it } from "vitest";
import { bucketOpenRouterModels, OPENROUTER_CATALOG_ENTRY_CAP } from "./openrouter-catalog";

describe("bucketOpenRouterModels", () => {
  it("buckets a $0/$0 model as free", () => {
    const { free, all } = bucketOpenRouterModels([
      { id: "openai/gpt-oss-20b:free", pricing: { prompt: "0", completion: "0" } },
    ]);
    expect(free.map((m) => m.id)).toEqual(["openai/gpt-oss-20b:free"]);
    expect(all).toHaveLength(1);
  });

  it("buckets a model with a hugging_face_id as opensource", () => {
    const { opensource } = bucketOpenRouterModels([
      {
        id: "meta-llama/llama-3.3-70b-instruct",
        pricing: { prompt: "0.0000001", completion: "0.0000003" },
        hugging_face_id: "meta-llama/Llama-3.3-70B-Instruct",
      },
    ]);
    expect(opensource.map((m) => m.id)).toEqual(["meta-llama/llama-3.3-70b-instruct"]);
  });

  it("falls back to the publisher-prefix allowlist when hugging_face_id is absent", () => {
    const { opensource } = bucketOpenRouterModels([
      { id: "qwen/qwen3-coder", pricing: { prompt: "0.0000002", completion: "0.0000006" } },
    ]);
    expect(opensource.map((m) => m.id)).toEqual(["qwen/qwen3-coder"]);
  });

  it("buckets a model priced at/above the flagship floor as flagship", () => {
    const { flagship } = bucketOpenRouterModels([
      // $3 / 1M tokens == 0.000003 / token
      { id: "anthropic/claude-opus-4", pricing: { prompt: "0.000005", completion: "0.000025" } },
    ]);
    expect(flagship.map((m) => m.id)).toEqual(["anthropic/claude-opus-4"]);
  });

  it("buckets a model priced at exactly the flagship floor as flagship (inclusive boundary)", () => {
    const { flagship } = bucketOpenRouterModels([
      // exactly $3 / 1M tokens == 0.000003 / token
      { id: "some-vendor/at-floor", pricing: { prompt: "0.000003", completion: "0.000003" } },
    ]);
    expect(flagship.map((m) => m.id)).toEqual(["some-vendor/at-floor"]);
  });

  it("does not bucket a model priced just below the flagship floor as flagship", () => {
    const { flagship, all } = bucketOpenRouterModels([
      // just under $3 / 1M tokens
      { id: "some-vendor/below-floor", pricing: { prompt: "0.0000029", completion: "0.0000029" } },
    ]);
    expect(flagship).toHaveLength(0);
    expect(all[0].tier).toBeUndefined();
  });

  it("a mid-priced, non-open-weight model has no tier but still appears in all", () => {
    const { free, opensource, flagship, all } = bucketOpenRouterModels([
      { id: "some-vendor/mid-tier", pricing: { prompt: "0.0000005", completion: "0.0000015" } },
    ]);
    expect(free).toHaveLength(0);
    expect(opensource).toHaveLength(0);
    expect(flagship).toHaveLength(0);
    expect(all).toHaveLength(1);
    expect(all[0].tier).toBeUndefined();
  });

  it("labels fall back to id when name is absent", () => {
    const { all } = bucketOpenRouterModels([{ id: "vendor/model" }]);
    expect(all[0]).toEqual({ id: "vendor/model", label: "vendor/model", tier: undefined, supportsTools: false });
  });

  it("detects tool support from supported_parameters", () => {
    const { all } = bucketOpenRouterModels([
      { id: "vendor/tool-model", supported_parameters: ["tools", "temperature"] },
    ]);
    expect(all[0].supportsTools).toBe(true);
  });

  it("skips entries with no id", () => {
    const { all } = bucketOpenRouterModels([{ id: "" }, { id: "vendor/ok" }]);
    expect(all.map((m) => m.id)).toEqual(["vendor/ok"]);
  });

  it("caps processing at OPENROUTER_CATALOG_ENTRY_CAP entries", () => {
    const entries = Array.from({ length: OPENROUTER_CATALOG_ENTRY_CAP + 500 }, (_, i) => ({
      id: `vendor/model-${i}`,
    }));
    const { all } = bucketOpenRouterModels(entries);
    expect(all).toHaveLength(OPENROUTER_CATALOG_ENTRY_CAP);
  });
});
