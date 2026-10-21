import { describe, expect, it } from "vitest";
import { DEPLOY_DEFAULT_MODELS } from "./deploy-config/deploy-models";
import { contextMeterEnabled, sessionModelSeed, showModelPicker } from "./session-model-seed";

const FLASH = "deepseek/deepseek-v4.1-flash-1017";

describe("sessionModelSeed", () => {
  it("keeps a published list on its curated default", () => {
    expect(
      sessionModelSeed({
        slug: "digithings-ai",
        available: [FLASH, "openai/gpt-oss-120b"],
        defaultModel: FLASH,
        showContextMeter: true,
      }),
    ).toBe(FLASH);
  });

  it("seeds the catalog default for the house slug when the list is empty", () => {
    expect(
      sessionModelSeed({
        slug: "digithings",
        available: [],
      }),
    ).toBe(DEPLOY_DEFAULT_MODELS.default);
    expect(DEPLOY_DEFAULT_MODELS.default).toBe(FLASH);
  });

  it("seeds an explicit default for any host that opts in", () => {
    expect(
      sessionModelSeed({
        slug: "example",
        available: [],
        defaultModel: FLASH,
        showContextMeter: true,
      }),
    ).toBe(FLASH);
  });

  it("leaves other hosts and an explicit house opt-out on an empty model", () => {
    expect(sessionModelSeed({ slug: "occ", available: [] })).toBe("");
    expect(sessionModelSeed({ slug: "datatap-trial-foundry", available: [] })).toBe("");
    expect(
      sessionModelSeed({
        slug: "digithings",
        available: [],
        showContextMeter: false,
      }),
    ).toBe("");
    expect(contextMeterEnabled(undefined, "occ")).toBe(false);
    expect(contextMeterEnabled(false, "digithings-ai")).toBe(false);
    expect(contextMeterEnabled(true, "example")).toBe(true);
  });

  it("does not open the picker just because the meter has a window", () => {
    expect(
      showModelPicker({
        allowPicker: false,
        featureModelPicker: false,
        available: [],
      }),
    ).toBe(false);
    expect(
      showModelPicker({
        allowPicker: true,
        available: [FLASH],
      }),
    ).toBe(true);
  });
});
