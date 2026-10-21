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

  // DIG-4879. A Foundry tenant is answered by its own agent, not by the
  // house model provider: naming the house backend there would be a lie
  // (ARCHITECTURE.md, "The composer provider chip names the backend that
  // serves the chat"). This branch arrived with #6073 and no test read it,
  // so it could be deleted with the whole suite green.
  it("names the Foundry backend when the session runs on one", () => {
    expect(backendLabel(null, "foundry")).toBe("Azure AI Foundry");
    expect(backendLabel(undefined, "foundry")).toBe("Azure AI Foundry");
  });

  // The branch is narrow on purpose: a Foundry tenant is answered by its
  // own agent, every other backend is the house one, and a session that
  // carries its own key names that key. A branch that answered every
  // backend with the Foundry name would name a lie on every other tenant.
  it("names the Foundry backend only when the session runs on one", () => {
    expect(backendLabel(null, "digigraph")).toBe(HOUSE_BACKEND_ID);
    expect(backendLabel(undefined, "digigraph")).toBe(HOUSE_BACKEND_ID);
    // The own key still wins over the serving backend.
    expect(backendLabel("openrouter", "foundry")).toBe("openrouter");
  });
});
