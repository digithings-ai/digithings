import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  EMBED_FREE_TURN_LIMIT,
  emit,
  readTrialUnlocked,
  readTurns,
  resetLiveTrialUnlockedForTests,
  resolveEmbedHost,
  writeTrialUnlocked,
  writeTurns,
  writeChatAccessToken,
  readChatAccessToken,
} from "./embed-gate";

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
    resetLiveTrialUnlockedForTests();
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

describe("embed-gate trial-unlock persistence", () => {
  beforeEach(() => {
    installLocalStorage();
    resetLiveTrialUnlockedForTests();
  });

  it("defaults to false when nothing is stored", () => {
    expect(readTrialUnlocked("https://digithings.ai")).toBe(false);
  });

  it("round-trips the unlock flag and survives a simulated remount", () => {
    writeTrialUnlocked("https://digithings.ai", true);
    // A "remount" is just re-reading storage from scratch — there's no React
    // state left over, exactly like a fresh page load after a reload.
    resetLiveTrialUnlockedForTests();
    expect(readTrialUnlocked("https://digithings.ai")).toBe(true);
  });

  it("clears on writeTrialUnlocked(host, false)", () => {
    writeTrialUnlocked("https://digithings.ai", true);
    writeTrialUnlocked("https://digithings.ai", false);
    expect(readTrialUnlocked("https://digithings.ai")).toBe(false);
  });

  it("isolates the unlock flag per host origin", () => {
    writeTrialUnlocked("https://digithings.ai", true);
    expect(readTrialUnlocked("https://digiquant.io")).toBe(false);
  });

  it("keeps unlock in the live mirror when localStorage is blocked", () => {
    // @ts-expect-error — deliberately broken storage
    globalThis.localStorage = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    };
    expect(readTrialUnlocked("x")).toBe(false);
    expect(() => writeTrialUnlocked("x", true)).not.toThrow();
    // Same-tab unlock must still work so a frozen transport can send the header.
    expect(readTrialUnlocked("x")).toBe(true);
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

describe("chat access token", () => {
  beforeEach(() => {
    installLocalStorage();
  });

  it("round-trips a token per host", () => {
    writeChatAccessToken("https://dev.datatap.stream", "abc.def");
    expect(readChatAccessToken("https://dev.datatap.stream")).toBe("abc.def");
    expect(readChatAccessToken("https://other.example")).toBeNull();
  });

  it("returns null when nothing was stored", () => {
    expect(readChatAccessToken("https://dev.datatap.stream")).toBeNull();
  });
});
