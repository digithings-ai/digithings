import { describe, expect, it } from "vitest";
import { BACKEND_ADAPTERS } from "./backend-adapters";
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
    // Every backend type the app supports, from the registry that holds
    // one adapter per type. The registry's key set is pinned against the
    // BackendType union by `backend-adapters.test.ts`, so a new backend
    // type cannot fall behind this case.
    const types = Object.keys(BACKEND_ADAPTERS);
    expect(types).toContain("foundry");
    for (const type of types) {
      if (type === "foundry") continue;
      expect(backendLabel(null, type)).toBe(HOUSE_BACKEND_ID);
      expect(backendLabel(undefined, type)).toBe(HOUSE_BACKEND_ID);
    }
    // No backend type at all is the house backend too.
    expect(backendLabel(null, undefined)).toBe(HOUSE_BACKEND_ID);
    // The own key still wins over the serving backend.
    expect(backendLabel("openrouter", "foundry")).toBe("openrouter");
    // A blank own key is no own key.
    expect(backendLabel("" as BYOKProvider, "foundry")).toBe("Azure AI Foundry");
  });
});
