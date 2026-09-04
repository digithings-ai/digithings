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

  it("defaults off and requires tenant + user", () => {
    expect(isWebSearchEnabled({ tenantAllows: false, userPref: false })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: true, userPref: false })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: false, userPref: true })).toBe(false);
    expect(isWebSearchEnabled({ tenantAllows: true, userPref: true })).toBe(true);
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
    expect(readWebSearchPref("datatap")).toBe(false);
    writeWebSearchPref("datatap", true);
    expect(readWebSearchPref("datatap")).toBe(true);
    writeWebSearchPref("datatap", false);
    expect(readWebSearchPref("datatap")).toBe(false);
  });
});
