import { describe, it, expect } from "vitest";
import { createSeedPayload, shouldAcceptReady } from "./digichatSeedBridge";

describe("digichatSeedBridge", () => {
  it("builds digichat:seed from handoff", () => {
    const p = createSeedPayload({
      messages: [{ role: "user", content: "q" }],
      pending: "more",
      ts: 123,
    });
    expect(p).toEqual({
      type: "digichat:seed",
      messages: [{ role: "user", content: "q" }],
      pending: "more",
      ts: 123,
    });
  });

  it("accepts ready only from digichat origin", () => {
    expect(
      shouldAcceptReady(
        { origin: "https://chat.digithings.ai", data: { type: "digichat:ready" } } as MessageEvent,
        "https://chat.digithings.ai",
      ),
    ).toBe(true);
    expect(
      shouldAcceptReady(
        { origin: "https://evil.example", data: { type: "digichat:ready" } } as MessageEvent,
        "https://chat.digithings.ai",
      ),
    ).toBe(false);
  });
});
