import { describe, expect, it } from "vitest";
import {
  contextMeterEnabled,
  contextMeterModel,
  modelSentOnTurn,
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
    const sessionModel = sessionModelSeed({ available: [] });
    expect(sessionModel).toBe("");
    expect(contextMeterModel({ sessionModel })).toBe("");
    expect(modelSentOnTurn(sessionModel, { isSet: false, model: "" })).toBeUndefined();
  });

  it("sizes the meter to the model the turn reported", () => {
    expect(sessionModelSeed({ available: [], defaultModel: FLASH })).toBe("");
    expect(
      contextMeterModel({
        sessionModel: "",
        reportedModel: "z-ai/glm-4.7-flash",
      }),
    ).toBe("z-ai/glm-4.7-flash");
    expect(contextMeterModel({ sessionModel: FLASH, reportedModel: "z-ai/glm-4.7-flash" })).toBe(
      "z-ai/glm-4.7-flash",
    );
  });

  it("leaves other hosts on an empty model", () => {
    expect(sessionModelSeed({ available: [] })).toBe("");
    expect(contextMeterModel({ sessionModel: "" })).toBe("");
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
