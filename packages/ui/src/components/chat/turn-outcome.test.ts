import { describe, expect, it } from "vitest";
import { turnCutShort, turnOutcome } from "./turn-outcome";

describe("turnOutcome", () => {
  it("reads the message status assistant-ui sets when the stream ends", () => {
    expect(turnOutcome({ type: "running" }, true)).toBe("running");
    expect(turnOutcome({ type: "complete", reason: "unknown" }, false)).toBe("done");
    expect(turnOutcome({ type: "incomplete", reason: "error" }, false)).toBe("failed");
    expect(turnOutcome({ type: "incomplete", reason: "cancelled" }, false)).toBe("stopped");
    expect(turnOutcome({ type: "incomplete", reason: "length" }, false)).toBe("stopped");
  });

  it("a pending server tool call with the thread idle is a stop, an approval is not", () => {
    expect(turnOutcome({ type: "requires-action", reason: "tool-calls" }, false)).toBe("stopped");
    expect(turnOutcome({ type: "requires-action", reason: "tool-calls" }, true)).toBe("running");
    expect(turnOutcome({ type: "requires-action", reason: "interrupt" }, false)).toBe("running");
  });

  it("no status is done", () => {
    expect(turnOutcome(undefined, false)).toBe("done");
    expect(turnCutShort("stopped")).toBe(true);
    expect(turnCutShort("failed")).toBe(true);
    expect(turnCutShort("done")).toBe(false);
    expect(turnCutShort("running")).toBe(false);
  });
});
