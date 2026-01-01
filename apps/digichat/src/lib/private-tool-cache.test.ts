import type { UIMessage } from "ai";
import { beforeEach, describe, expect, it } from "vitest";
import {
  privateToolRecorder,
  privateToolScope,
  rehydratePrivateToolParts,
  resetPrivateToolCacheForTests,
} from "./private-tool-cache";

const scope = privateToolScope({ tenantSlug: "t1", ownerUserSub: "embed:anonymous" });
const ID = "call_7f3a9c21e4";

function recordTurn(s = scope, id = ID) {
  const record = privateToolRecorder(s);
  record({ type: "tool-input-start", toolCallId: id, toolName: "deskly_search_tickets" });
  record({
    type: "tool-input-available",
    toolCallId: id,
    toolName: "deskly_search_tickets",
    input: { q: "Jane Doe" },
  });
  record({ type: "tool-output-available", toolCallId: id, output: { requester: "Jane Doe" } });
}

/** What the browser sends back: the stripped step. */
function strippedThread(id = ID, state = "output-available"): UIMessage[] {
  return [
    { id: "u1", role: "user", parts: [{ type: "text", text: "Show my tickets" }] },
    {
      id: "a1",
      role: "assistant",
      parts: [
        {
          type: "tool-search_tickets",
          toolCallId: id,
          state,
          input: {},
          ...(state === "output-error" ? { errorText: "Step failed." } : { output: {} }),
        } as never,
        { type: "text", text: "You have one ticket." },
      ],
    },
    { id: "u2", role: "user", parts: [{ type: "text", text: "Who opened it?" }] },
  ];
}

beforeEach(() => resetPrivateToolCacheForTests());

describe("private tool memory", () => {
  it("puts the original tool name, input and output back on the next turn", () => {
    recordTurn();
    const out = rehydratePrivateToolParts(strippedThread(), scope);
    expect(out[1]?.parts[0]).toEqual({
      type: "tool-deskly_search_tickets",
      toolCallId: ID,
      state: "output-available",
      input: { q: "Jane Doe" },
      output: { requester: "Jane Doe" },
    });
    expect(out[1]?.parts[1]).toEqual({ type: "text", text: "You have one ticket." });
    expect(out[0]?.parts).toEqual(strippedThread()[0]?.parts);
  });

  it("restores the real error text of a failed step", () => {
    const record = privateToolRecorder(scope);
    record({ type: "tool-input-available", toolCallId: ID, toolName: "list", input: { a: 1 } });
    record({ type: "tool-output-error", toolCallId: ID, errorText: "403 for jane@x.io" });
    const part = rehydratePrivateToolParts(strippedThread(ID, "output-error"), scope)[1]?.parts[0];
    expect(part).toMatchObject({ type: "tool-list", input: { a: 1 }, errorText: "403 for jane@x.io" });
  });

  it("keeps a dynamic tool's name in toolName", () => {
    const record = privateToolRecorder(scope);
    record({ type: "tool-input-available", toolCallId: ID, toolName: "deskly_x", dynamic: true, input: {} });
    record({ type: "tool-output-available", toolCallId: ID, output: { ok: 1 } });
    const thread: UIMessage[] = [
      {
        id: "a",
        role: "assistant",
        parts: [
          { type: "dynamic-tool", toolName: "x", toolCallId: ID, state: "output-available", input: {}, output: {} } as never,
        ],
      },
    ];
    expect(rehydratePrivateToolParts(thread, scope)[0]?.parts[0]).toMatchObject({
      type: "dynamic-tool",
      toolName: "deskly_x",
      output: { ok: 1 },
    });
  });

  it("does not cross sessions, tenants or owners", () => {
    recordTurn();
    const thread = strippedThread();
    for (const other of [
      privateToolScope({ tenantSlug: "t2", ownerUserSub: "embed:anonymous" }),
      privateToolScope({ tenantSlug: "t1", ownerUserSub: "user:b" }),
      privateToolScope({ tenantSlug: "t1", ownerUserSub: "embed:anonymous", sessionHeader: "s2" }),
    ]) {
      expect(rehydratePrivateToolParts(thread, other)).toBe(thread);
    }
  });

  it("leaves parts alone on a miss, and ignores short guessable ids", () => {
    const thread = strippedThread();
    expect(rehydratePrivateToolParts(thread, scope)).toBe(thread);
    recordTurn(scope, "c1");
    const short = strippedThread("c1");
    expect(rehydratePrivateToolParts(short, scope)).toBe(short);
  });

  it("expires after the TTL", async () => {
    const { vi } = await import("vitest");
    vi.useFakeTimers();
    try {
      recordTurn();
      vi.advanceTimersByTime(2 * 60 * 60_000 + 1);
      const thread = strippedThread();
      expect(rehydratePrivateToolParts(thread, scope)).toBe(thread);
    } finally {
      vi.useRealTimers();
    }
  });
});
