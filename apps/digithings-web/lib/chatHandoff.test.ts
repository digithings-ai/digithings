import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { writeHandoff, readAndClearHandoff } from "./chatHandoff";

describe("chatHandoff", () => {
  const store = new Map<string, string>();

  beforeEach(() => {
    store.clear();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("round-trips write then readAndClear", () => {
    writeHandoff([{ role: "user", content: "hi" }], "follow up");
    const handoff = readAndClearHandoff();
    expect(handoff?.pending).toBe("follow up");
    expect(handoff?.messages).toHaveLength(1);
    expect(readAndClearHandoff()).toBeNull();
  });
});
