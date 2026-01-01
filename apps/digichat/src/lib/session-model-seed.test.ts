import { describe, expect, it } from "vitest";
import {
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

  it("starts on Auto when the curated default is the auto preset model", () => {
    // The picker shows "auto" and selects the Auto row; the turn still runs
    // on the deployment default because an empty session model sends no
    // X-Digi-Model and the route falls back to models.default.
    expect(
      sessionModelSeed({
        available: [FLASH, "openai/gpt-oss-120b"],
        defaultModel: FLASH,
        autoModel: FLASH,
      }),
    ).toBe("");
    expect(
      sessionModelSeed({
        available: [FLASH, "openai/gpt-oss-120b"],
        defaultModel: "openai/gpt-oss-120b",
        autoModel: FLASH,
      }),
    ).toBe("openai/gpt-oss-120b");
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

  it("keeps the session model when the report has no known window", () => {
    expect(contextMeterModel({ sessionModel: FLASH, reportedModel: "digigraph-rag" })).toBe(FLASH);
    expect(contextMeterModel({ sessionModel: "", reportedModel: "digigraph-rag" })).toBe("");
    expect(contextMeterModel({ sessionModel: FLASH, reportedModel: "constructor" })).toBe(FLASH);
  });

  it("sizes the meter to the bring-your-own-key model the turn sends", () => {
    const sent = modelSentOnTurn("", { isSet: true, model: "z-ai/glm-4.7-flash" });
    expect(contextMeterModel({ sessionModel: sent ?? "" })).toBe("z-ai/glm-4.7-flash");
    expect(modelSentOnTurn(FLASH, { isSet: true, model: "z-ai/glm-4.7-flash" })).toBe(
      "z-ai/glm-4.7-flash",
    );
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
