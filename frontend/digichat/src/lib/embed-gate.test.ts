import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EMBED_FREE_TURN_LIMIT, emit, readTurns, resolveEmbedHost, writeTurns } from "./embed-gate";

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

describe("resolveEmbedHost", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("prefers an explicit host over any client-side detection, even during SSR", () => {
    expect(resolveEmbedHost("https://explicit.example.com")).toBe(
      "https://explicit.example.com",
    );
  });

  it("falls back to document.referrer's origin when no explicit host is given", () => {
    vi.stubGlobal("window", {});
    vi.stubGlobal("document", { referrer: "https://parent.example.com/some/page" });
    expect(resolveEmbedHost()).toBe("https://parent.example.com");
  });

  it("never falls back to the iframe's own origin — reports 'unknown' when both referrer and window.parent access fail", () => {
    vi.stubGlobal("document", { referrer: "" });
    vi.stubGlobal("window", {
      location: { origin: "https://digichat-own-origin.example.com" },
      get parent(): never {
        throw new Error("cross-origin, as expected in production");
      },
    });
    expect(resolveEmbedHost()).toBe("unknown");
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
