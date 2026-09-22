import { describe, expect, it } from "vitest";
import {
  armForceToolThenHold,
  setPendingForceTool,
  setPendingTurnMode,
  setPendingWebSearchForce,
  takePendingForceTool,
  takePendingTurnMode,
  takePendingWebSearchForce,
} from "./pending-chat-headers";

describe("pending-chat-headers", () => {
  it("isolates force-tool by key and clears on take", () => {
    setPendingForceTool("thread-a", "digisearch");
    setPendingForceTool("thread-b", "digivault_search_notes");
    expect(takePendingForceTool("thread-a")).toBe("digisearch");
    expect(takePendingForceTool("thread-a")).toBeUndefined();
    expect(takePendingForceTool("thread-b")).toBe("digivault_search_notes");
  });

  it("isolates turn mode by key and clears on take", () => {
    setPendingTurnMode("t1", "regenerate");
    setPendingTurnMode("t2", "edit_last_user");
    expect(takePendingTurnMode("t1")).toBe("regenerate");
    expect(takePendingTurnMode("t1")).toBeUndefined();
    expect(takePendingTurnMode("t2")).toBe("edit_last_user");
  });

  it("set without a value clears the pending entry", () => {
    setPendingForceTool("k", "digisearch");
    setPendingTurnMode("k", "regenerate");
    setPendingForceTool("k");
    setPendingTurnMode("k");
    expect(takePendingForceTool("k")).toBeUndefined();
    expect(takePendingTurnMode("k")).toBeUndefined();
  });

  it("ignores blank keys", () => {
    setPendingForceTool("  ", "digisearch");
    setPendingTurnMode("", "regenerate");
    expect(takePendingForceTool("  ")).toBeUndefined();
    expect(takePendingTurnMode("")).toBeUndefined();
  });

  it("arms slash force-tool before a gated onHold that takes it", () => {
    let held: string | undefined;
    armForceToolThenHold("embed-host", "digisearch", () => {
      held = takePendingForceTool("embed-host");
    });
    expect(held).toBe("digisearch");
  });

  it("isolates web-search force by key and clears on take", () => {
    setPendingWebSearchForce("thread-a");
    setPendingWebSearchForce("thread-b", true);
    expect(takePendingWebSearchForce("thread-a")).toBe(true);
    expect(takePendingWebSearchForce("thread-a")).toBe(false);
    expect(takePendingWebSearchForce("thread-b")).toBe(true);
  });
});
