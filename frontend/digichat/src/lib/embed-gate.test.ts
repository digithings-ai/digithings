import { beforeEach, describe, expect, it, vi } from "vitest";
import { EMBED_FREE_TURN_LIMIT, emit, readTurns, writeTurns } from "./embed-gate";

type Store = Map<string, string>;

function installLocalStorage(store: Store = new Map()): Store {
  const api = {
    getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
    setItem: (k: string, v: string) => {
      store.set(k, v);
    },
    removeItem: (k: string) => {
      store.delete(k);
    },
    clear: () => store.clear(),
    key: (i: number) => Array.from(store.keys())[i] ?? null,
    get length() {
      return store.size;
    },
  };
  // @ts-expect-error — attach to global for the test run
  globalThis.localStorage = api;
  return store;
}

describe("embed-gate storage", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  it("returns 0 when no entry exists", () => {
    expect(readTurns("https://digithings.ai")).toBe(0);
  });

  it("round-trips a counter value, clamped to >= 0", () => {
    writeTurns("https://digithings.ai", 2);
    expect(readTurns("https://digithings.ai")).toBe(2);

    writeTurns("https://digithings.ai", -5);
    expect(readTurns("https://digithings.ai")).toBe(0);
  });

  it("isolates counters per host origin", () => {
    writeTurns("https://digithings.ai", 3);
    writeTurns("https://digiquant.io", 1);
    expect(readTurns("https://digithings.ai")).toBe(3);
    expect(readTurns("https://digiquant.io")).toBe(1);
  });

  it("ignores non-numeric garbage in storage", () => {
    const store = installLocalStorage();
    store.set("digichat_embed_turns:https://digithings.ai", "not-a-number");
    expect(readTurns("https://digithings.ai")).toBe(0);
  });

  it("swallows storage errors (private-mode safety)", () => {
    // @ts-expect-error — deliberately broken storage
    globalThis.localStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readTurns("x")).toBe(0);
    expect(() => writeTurns("x", 1)).not.toThrow();
  });
});

describe("embed-gate constants + analytics", () => {
  it("exposes the free-tier limit as 3", () => {
    expect(EMBED_FREE_TURN_LIMIT).toBe(3);
  });

  it("emit() is a no-op that accepts event + props", () => {
    const spy = vi.fn();
    const originalLog = console.log;
    console.log = spy;
    try {
      emit("embed_loaded", { host: "https://digithings.ai" });
      emit("embed_turn_submitted");
    } finally {
      console.log = originalLog;
    }
    expect(spy).not.toHaveBeenCalled();
  });
});
