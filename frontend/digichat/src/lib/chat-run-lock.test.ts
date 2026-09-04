import { afterEach, describe, expect, it } from "vitest";
import {
  acquireChatRunLock,
  releaseChatRunLockOnResponseEnd,
  resetChatRunLocksForTests,
} from "./chat-run-lock";

afterEach(() => {
  resetChatRunLocksForTests();
});

describe("acquireChatRunLock", () => {
  it("blocks a second concurrent run on the same session", () => {
    const first = acquireChatRunLock("sess-a", null);
    expect(first.ok).toBe(true);
    const second = acquireChatRunLock("sess-a", null);
    expect(second).toEqual({ ok: false, error: "run_in_progress" });
    if (first.ok) first.release();
    const third = acquireChatRunLock("sess-a", null);
    expect(third.ok).toBe(true);
    if (third.ok) third.release();
  });

  it("rejects a duplicate run id for the same session", () => {
    const first = acquireChatRunLock("sess-b", "run-1");
    expect(first.ok).toBe(true);
    if (first.ok) first.release();
    const replay = acquireChatRunLock("sess-b", "run-1");
    expect(replay).toEqual({ ok: false, error: "run_id_replay" });
  });

  it("allows the same run id on a different session", () => {
    const a = acquireChatRunLock("sess-1", "shared-run");
    expect(a.ok).toBe(true);
    if (a.ok) a.release();
    const b = acquireChatRunLock("sess-2", "shared-run");
    expect(b.ok).toBe(true);
    if (b.ok) b.release();
  });
});

describe("releaseChatRunLockOnResponseEnd", () => {
  it("releases when the body is fully read", async () => {
    const lock = acquireChatRunLock("sess-stream", null);
    expect(lock.ok).toBe(true);
    if (!lock.ok) return;

    const inner = new Response("ok", { status: 200 });
    const wrapped = releaseChatRunLockOnResponseEnd(inner, lock.release);
    await wrapped.text();

    const next = acquireChatRunLock("sess-stream", null);
    expect(next.ok).toBe(true);
    if (next.ok) next.release();
  });
});
