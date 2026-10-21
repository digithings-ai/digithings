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

  it("does not seed a non-house slug that sets the flag", () => {
    expect(
      sessionModelSeed({
        slug: "example",
        available: [],
        defaultModel: FLASH,
        showContextMeter: true,
      }),
    ).toBe("");
  });

  it("leaves other hosts and an explicit house opt-out on an empty model", () => {
    expect(sessionModelSeed({ slug: "occ", available: [] })).toBe("");
    expect(sessionModelSeed({ slug: "trial-foundry", available: [], showContextMeter: true })).toBe(
      "",
    );
    expect(
      sessionModelSeed({
        slug: "digithings",
        available: [],
        showContextMeter: false,
      }),
    ).toBe("");
    expect(contextMeterEnabled(undefined, "digithings")).toBe(true);
    expect(contextMeterEnabled(undefined, "digithings-ai")).toBe(true);
    expect(contextMeterEnabled(true, "digithings")).toBe(true);
    expect(contextMeterEnabled(undefined, "occ")).toBe(false);
    expect(contextMeterEnabled(false, "digithings-ai")).toBe(false);
    expect(contextMeterEnabled(true, "example")).toBe(false);
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
