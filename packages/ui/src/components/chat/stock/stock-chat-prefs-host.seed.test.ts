import { describe, expect, it } from "vitest";
import { initialStockSessionModel } from "./stock-chat-prefs-host";

const DEFAULT = "deepseek/deepseek-v4.1-flash-1017";
const picker = {
  presets: [
    { id: "auto", label: "Default", model: DEFAULT },
    { id: "fast", label: "Fast", model: "google/gemini-3.5-flash-lite" },
  ],
  groups: [],
  showFullList: false,
};

describe("initialStockSessionModel", () => {
  it("starts on Auto when the curated default is the Auto preset's model", () => {
    expect(
      initialStockSessionModel({
        defaultModel: DEFAULT,
        availableModels: [DEFAULT, "openai/gpt-oss-120b"],
        modelPicker: picker,
      }),
    ).toBe("");
  });

  it("keeps a curated default that differs from Auto", () => {
    expect(
      initialStockSessionModel({
        defaultModel: "openai/gpt-oss-120b",
        availableModels: [DEFAULT, "openai/gpt-oss-120b"],
        modelPicker: picker,
      }),
    ).toBe("openai/gpt-oss-120b");
  });

  it("falls back to the default, then the first id, without an Auto preset", () => {
    expect(initialStockSessionModel({ defaultModel: DEFAULT, availableModels: [DEFAULT] })).toBe(
      DEFAULT,
    );
    expect(initialStockSessionModel({ availableModels: ["a", "b"] })).toBe("a");
    expect(initialStockSessionModel({ availableModels: [] })).toBe("");
  });
});
