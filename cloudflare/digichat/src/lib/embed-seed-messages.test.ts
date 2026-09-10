import { describe, it, expect } from "vitest";
import {
  READY_MESSAGE,
  parseSeedMessage,
  isAllowedSeedParentOrigin,
  resolveReadyTargetOrigin,
  MAX_SEED_MESSAGES,
} from "./embed-seed-messages";

describe("embed-seed-messages", () => {
  it("exports digichat:ready", () => {
    expect(READY_MESSAGE.type).toBe("digichat:ready");
  });

  describe("resolveReadyTargetOrigin", () => {
    it("prefers ancestorOrigins over referrer (OCC under digithings.ai)", () => {
      expect(
        resolveReadyTargetOrigin({
          ancestorOrigins: ["https://digithings.ai"],
          referrer: "https://digithings.ai/chat/occ",
        }),
      ).toBe("https://digithings.ai");
    });

    it("falls back to document.referrer origin when ancestorOrigins is empty", () => {
      expect(
        resolveReadyTargetOrigin({
          ancestorOrigins: [],
          referrer: "https://digithings.ai/chat/occ",
        }),
      ).toBe("https://digithings.ai");
    });

    it("does not use a virtual embed host string as the ready target", () => {
      // Callers must not pass ?host=occ.digithings.ai here — contract: only
      // ancestor/referrer. Confirm empty inputs yield null (no host fallback).
      expect(
        resolveReadyTargetOrigin({
          ancestorOrigins: null,
          referrer: "",
        }),
      ).toBeNull();
      expect(
        resolveReadyTargetOrigin({
          ancestorOrigins: undefined,
          referrer: null,
        }),
      ).toBeNull();
    });

    it("ignores unparseable referrer", () => {
      expect(
        resolveReadyTargetOrigin({
          ancestorOrigins: null,
          referrer: "not-a-url",
        }),
      ).toBeNull();
    });
  });

  it("accepts a well-formed seed from digithings.ai", () => {
    const event = {
      origin: "https://digithings.ai",
      data: {
        type: "digichat:seed",
        messages: [{ role: "user", content: "hi" }],
        pending: "follow up?",
        ts: Date.now(),
      },
    } as MessageEvent;
    const parsed = parseSeedMessage(event, new Set(["https://digithings.ai"]));
    expect(parsed?.pending).toBe("follow up?");
    expect(parsed?.messages).toHaveLength(1);
  });

  it("ignores wrong origin", () => {
    const event = {
      origin: "https://evil.example",
      data: {
        type: "digichat:seed",
        messages: [],
        pending: "x",
        ts: Date.now(),
      },
    } as MessageEvent;
    expect(parseSeedMessage(event, new Set(["https://digithings.ai"]))).toBeNull();
  });

  it("drops over-cap message lists", () => {
    const messages = Array.from({ length: MAX_SEED_MESSAGES + 1 }, () => ({
      role: "user" as const,
      content: "x",
    }));
    const event = {
      origin: "https://digithings.ai",
      data: { type: "digichat:seed", messages, pending: "", ts: Date.now() },
    } as MessageEvent;
    expect(parseSeedMessage(event, new Set(["https://digithings.ai"]))).toBeNull();
  });

  it("recognizes first-party parent origins", () => {
    expect(isAllowedSeedParentOrigin("https://digithings.ai")).toBe(true);
    expect(isAllowedSeedParentOrigin("https://www.digithings.ai")).toBe(true);
    expect(isAllowedSeedParentOrigin("https://datatapstream.com")).toBe(false);
  });
});
