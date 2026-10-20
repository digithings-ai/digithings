import { describe, expect, it } from "vitest";
import {
  CLEAR_PROVIDER_ROW_ID,
  PROVIDER_MENU_ORDER,
  defaultProviderPick,
  providerDisplayName,
  providerKeyPlaceholder,
  providerMenuRowIds,
  providerMenuRowIndex,
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

describe("provider menu rows", () => {
  it("renders the clear row first, then the provider order", () => {
    expect(providerMenuRowIds()).toEqual([
      CLEAR_PROVIDER_ROW_ID,
      ...PROVIDER_MENU_ORDER,
    ]);
  });

  it("points the cursor at the rendered row of the active provider", () => {
    for (const id of PROVIDER_MENU_ORDER) {
      expect(providerMenuRowIds()[providerMenuRowIndex(id)]).toBe(id);
    }
    // The rendered list carries the clear row first, so the cursor index of a
    // provider is not its index in the provider order.
    expect(providerMenuRowIndex("gemini")).not.toBe(
      PROVIDER_MENU_ORDER.indexOf("gemini"),
    );
  });

  it("keeps the cursor on the clear row when no provider is connected", () => {
    expect(providerMenuRowIndex()).toBe(0);
    expect(providerMenuRowIndex(undefined)).toBe(0);
    expect(providerMenuRowIds()[providerMenuRowIndex()]).toBe(CLEAR_PROVIDER_ROW_ID);
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
