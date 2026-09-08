/** @vitest-environment happy-dom */
import { describe, expect, it, beforeEach } from "vitest";
import {
  SessionMemoryThreadListAdapter,
  memoryThreadStorageKey,
} from "./session-memory-thread-list";

describe("SessionMemoryThreadListAdapter", () => {
  const key = memoryThreadStorageKey("test-host", "user-1");

  beforeEach(() => {
    sessionStorage.clear();
  });

  it("builds a stable storage key from host + user", () => {
    expect(memoryThreadStorageKey("app", "u1")).toBe(
      "digichat:memory-threads:app:u1",
    );
    expect(memoryThreadStorageKey("app")).toBe(
      "digichat:memory-threads:app:anon",
    );
  });

  it("persists initialize + list across adapter instances", async () => {
    const a = new SessionMemoryThreadListAdapter(key);
    await a.initialize("thread-a");
    await a.rename("thread-a", "First");

    const b = new SessionMemoryThreadListAdapter(key);
    const listed = await b.list();
    expect(listed.threads).toHaveLength(1);
    expect(listed.threads[0]?.remoteId).toBe("thread-a");
    expect(listed.threads[0]?.title).toBe("First");
  });

  it("isolates threads by remoteId and deletes cleanly", async () => {
    const a = new SessionMemoryThreadListAdapter(key);
    await a.initialize("t1");
    await a.initialize("t2");
    await a.delete("t1");
    const listed = await a.list();
    expect(listed.threads.map((t) => t.remoteId)).toEqual(["t2"]);
  });
});
