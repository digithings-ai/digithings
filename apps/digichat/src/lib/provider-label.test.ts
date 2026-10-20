import { describe, expect, it } from "vitest";
import type { BYOKProvider } from "./byok-providers";
import { HOUSE_BACKEND_ID, backendLabel } from "./provider-label";

describe("backendLabel (#4597)", () => {
  it("names the own-key provider when the session carries one", () => {
    expect(backendLabel("openrouter")).toBe("openrouter");
    expect(backendLabel("anthropic")).toBe("anthropic");
  });

  it("falls back to the house backend when no own key is set", () => {
    expect(backendLabel(null)).toBe(HOUSE_BACKEND_ID);
    expect(backendLabel(undefined)).toBe(HOUSE_BACKEND_ID);
  });

  it("never names a blank provider", () => {
    expect(backendLabel("" as BYOKProvider)).toBe(HOUSE_BACKEND_ID);
    expect(backendLabel("  " as BYOKProvider)).toBe(HOUSE_BACKEND_ID);
  });
});
