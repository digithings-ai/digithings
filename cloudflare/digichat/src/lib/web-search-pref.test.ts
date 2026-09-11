/** @vitest-environment happy-dom */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  isWebSearchEnabled,
  readWebSearchPref,
  webSearchStorageKey,
  writeWebSearchPref,
} from "./web-search-pref";

describe("web-search-pref (#3420)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    try {
      window.localStorage.clear();
    } catch {
      /* ignore */
    }
  });

  it("missing key defaults on; explicit stored false stays off (#3859)", () => {
    expect(isWebSearchEnabled({ tenantAllows: false, userPref: false })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: true, userPref: false })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: false, userPref: true })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: true, userPref: true })).toBe(true);
    // happy-dom ships a non-functional localStorage — stub a real Map so the
    // missing-key default is exercised, not the catch branch.
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => store.clear(),
    });
    expect(readWebSearchPref("fresh-scope")).toBe(true);
    expect(readWebSearchPref("fresh-scope", true)).toBe(true);
    expect(readWebSearchPref("fresh-scope", false)).toBe(false);
  });

  it("persists user preference under a scoped key", () => {
    expect(webSearchStorageKey("datatap")).toBe("digichat-web-search:datatap");
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => store.clear(),
    });
    expect(readWebSearchPref("datatap")).toBe(true);
    writeWebSearchPref("datatap", true);
    expect(readWebSearchPref("datatap")).toBe(true);
    writeWebSearchPref("datatap", false);
    expect(readWebSearchPref("datatap")).toBe(false);
  });

  it("storage failure falls back to defaultOn, not off (#3859)", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("private mode");
      },
      setItem: () => {
        throw new Error("private mode");
      },
      removeItem: () => {},
      clear: () => {},
    });
    expect(readWebSearchPref("broken-scope")).toBe(true);
    expect(readWebSearchPref("broken-scope", true)).toBe(true);
    expect(readWebSearchPref("broken-scope", false)).toBe(false);
  });
});
