import { describe, it, expect, afterEach, vi } from "vitest";
import {
  PARENT_ERROR_MESSAGE_TYPE,
  MAX_PARENT_ERROR_AGE_MS,
  buildParentErrorMessage,
  formatParentErrorLine,
  parseParentErrorMessage,
} from "./embed-parent-error-messages";

describe("embed-parent-error-messages", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("exports digichat:parent-error", () => {
    expect(PARENT_ERROR_MESSAGE_TYPE).toBe("digichat:parent-error");
    expect(buildParentErrorMessage("ready_timeout").type).toBe(
      "digichat:parent-error",
    );
  });

  describe("formatParentErrorLine", () => {
    it("prefixes with error: and keeps the default copy visitor-facing", () => {
      for (const code of ["ready_timeout", "embed_unloadable", "ready_target_missing"] as const) {
        const line = formatParentErrorLine(code);
        expect(line.startsWith("error: ")).toBe(true);
        // Rendered in the chat: no env names, origins or internals.
        expect(line).not.toMatch(/DIGICHAT_|Container|ancestorOrigins|referrer|origin|tunnel/);
      }
    });

    it("accepts an override message", () => {
      expect(formatParentErrorLine("ready_timeout", "  custom  ")).toBe(
        "error: custom",
      );
    });

    it("formats ready_target_missing for embed self-report", () => {
      expect(formatParentErrorLine("ready_target_missing")).toContain(
        "could not connect",
      );
    });
  });

  describe("parseParentErrorMessage", () => {
    const allowed = new Set(["https://digithings.ai"]);

    it("accepts a well-formed parent-error from digithings.ai", () => {
      const event = {
        origin: "https://digithings.ai",
        data: buildParentErrorMessage("ready_timeout"),
      } as MessageEvent;
      const parsed = parseParentErrorMessage(event, allowed);
      expect(parsed?.code).toBe("ready_timeout");
      expect(parsed?.type).toBe("digichat:parent-error");
    });

    it("ignores wrong origin", () => {
      const event = {
        origin: "https://evil.example",
        data: buildParentErrorMessage("embed_unloadable"),
      } as MessageEvent;
      expect(parseParentErrorMessage(event, allowed)).toBeNull();
    });

    it("rejects unknown codes", () => {
      const event = {
        origin: "https://digithings.ai",
        data: {
          type: PARENT_ERROR_MESSAGE_TYPE,
          code: "not_a_code",
          ts: Date.now(),
        },
      } as MessageEvent;
      expect(parseParentErrorMessage(event, allowed)).toBeNull();
    });

    it("rejects missing or stale ts", () => {
      const noTs = {
        origin: "https://digithings.ai",
        data: { type: PARENT_ERROR_MESSAGE_TYPE, code: "ready_timeout" },
      } as MessageEvent;
      expect(parseParentErrorMessage(noTs, allowed)).toBeNull();

      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-08-10T12:00:00Z"));
      const stale = {
        origin: "https://digithings.ai",
        data: buildParentErrorMessage("ready_timeout", {
          ts: Date.now() - MAX_PARENT_ERROR_AGE_MS - 1,
        }),
      } as MessageEvent;
      expect(parseParentErrorMessage(stale, allowed)).toBeNull();
    });

    it("keeps an optional message override", () => {
      const event = {
        origin: "https://digithings.ai",
        data: buildParentErrorMessage("ready_timeout", {
          message: "custom detail",
        }),
      } as MessageEvent;
      expect(parseParentErrorMessage(event, allowed)?.message).toBe(
        "custom detail",
      );
    });
  });
});
