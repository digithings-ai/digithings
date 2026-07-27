import { describe, expect, it } from "vitest";
import { isUnlockedMessage, UNLOCKED_MESSAGE_TYPE } from "@/lib/embed-trial-messages";

const parent = "https://datatap.stream";
const ev = (origin: string, data: unknown) => ({ origin, data }) as MessageEvent;

describe("isUnlockedMessage", () => {
  it("accepts the unlock type only from the exact parent origin", () => {
    expect(isUnlockedMessage(ev(parent, { type: UNLOCKED_MESSAGE_TYPE }), parent)).toBe(true);
  });
  it("rejects a wrong origin", () => {
    expect(isUnlockedMessage(ev("https://evil.example", { type: UNLOCKED_MESSAGE_TYPE }), parent)).toBe(false);
  });
  it("rejects a wrong type", () => {
    expect(isUnlockedMessage(ev(parent, { type: "datatap:gated" }), parent)).toBe(false);
  });
  it("rejects when the parent origin is unknown", () => {
    expect(isUnlockedMessage(ev(parent, { type: UNLOCKED_MESSAGE_TYPE }), undefined)).toBe(false);
  });
});
