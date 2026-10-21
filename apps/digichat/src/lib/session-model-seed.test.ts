import { describe, expect, it } from "vitest";
import { DEPLOY_DEFAULT_MODELS } from "./deploy-config/deploy-models";
import {
  contextMeterEnabled,
  contextMeterModel,
  sessionModelSeed,
  showModelPicker,
} from "./session-model-seed";

const FLASH = "deepseek/deepseek-v4.1-flash-1017";

describe("sessionModelSeed", () => {
  it("keeps a published list on its curated default", () => {
    expect(
      sessionModelSeed({
        available: [FLASH, "openai/gpt-oss-120b"],
        defaultModel: FLASH,
      }),
    ).toBe(FLASH);
  });

  it("leaves the session model empty when the house list is empty", () => {
    expect(sessionModelSeed({ available: [] })).toBe("");
    expect(
      contextMeterModel({
        slug: "digithings",
        sessionModel: "",
      }),
    ).toBe(DEPLOY_DEFAULT_MODELS.default);
    expect(DEPLOY_DEFAULT_MODELS.default).toBe(FLASH);
  });

  it("does not size the meter for a non-house slug that sets the flag", () => {
    expect(sessionModelSeed({ available: [], defaultModel: FLASH })).toBe("");
    expect(
      contextMeterModel({
        slug: "example",
        showContextMeter: true,
        sessionModel: "",
      }),
    ).toBe("");
  });

  it("leaves other hosts and an explicit house opt-out on an empty model", () => {
    expect(sessionModelSeed({ available: [] })).toBe("");
    expect(contextMeterModel({ slug: "occ", sessionModel: "" })).toBe("");
    expect(
      contextMeterModel({ slug: "trial-foundry", showContextMeter: true, sessionModel: "" }),
    ).toBe("");
    expect(
      contextMeterModel({ slug: "digithings", showContextMeter: false, sessionModel: "" }),
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
