import { describe, expect, it } from "vitest";
import {
  PROVIDER_MENU_ORDER,
  defaultProviderPick,
  providerDisplayName,
  providerKeyPlaceholder,
  providerModelChoices,
  sessionPickerModels,
  tryResolveProviderInput,
  wantsProviderKeyPing,
} from "./embed-provider-flow";

describe("tryResolveProviderInput", () => {
  it("accepts ids and display names", () => {
    expect(tryResolveProviderInput("openai")).toBe("openai");
    expect(tryResolveProviderInput("OpenRouter")).toBe("openrouter");
    expect(tryResolveProviderInput("x.ai")).toBe("xai");
    expect(tryResolveProviderInput("nope")).toBeUndefined();
  });
});

describe("providerModelChoices", () => {
  it("adds a default row only when a model is optional", () => {
    const openai = providerModelChoices("openai");
    expect(openai[0]).toEqual({ id: "", label: "(default)" });
    expect(openai.at(-1)?.id).toBe("__custom__");
    expect(providerModelChoices("anthropic")[0]?.id).not.toBe("");
  });
});

describe("sessionPickerModels", () => {
  const house = [
    "deepseek/deepseek-v4-flash",
    "z-ai/glm-5.3-flash",
  ] as const;

  it("stays on the house CI list when no BYOK provider is connected", () => {
    expect(sessionPickerModels(house)).toEqual([...house]);
    expect(sessionPickerModels(house, null)).toEqual([...house]);
  });

  it("switches to that provider's presets when BYOK is connected", () => {
    expect(sessionPickerModels(house, "openai")).toEqual([
      "gpt-4o-mini",
      "gpt-4o",
      "o4-mini",
    ]);
    expect(sessionPickerModels(house, "openai")).not.toContain(
      "deepseek/deepseek-v4-flash",
    );
  });
});

describe("provider chrome copy", () => {
  it("names providers for the settings row", () => {
    expect(providerDisplayName("openrouter")).toBe("OpenRouter");
    expect(providerKeyPlaceholder("anthropic")).toBe("sk-ant-…");
    expect(wantsProviderKeyPing("openai")).toBe(true);
    expect(wantsProviderKeyPing("openrouter")).toBe(false);
  });

  it("lists first-party providers before OpenRouter", () => {
    expect(PROVIDER_MENU_ORDER).toEqual([
      "openai",
      "anthropic",
      "gemini",
      "xai",
      "openrouter",
    ]);
    expect(defaultProviderPick()).toBe("openai");
    expect(defaultProviderPick("gemini")).toBe("gemini");
  });
});
