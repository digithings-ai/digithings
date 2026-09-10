/**
 * RED: websearch toggle pref must render SSR-identical first (off) on both
 * server and client, then sync the stored/default-ON value after mount.
 * (tool-catalog-bar initialized from localStorage during render, which
 * hydrates_websearch_on tenants like ?host=digithings.ai.)
 */
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, beforeEach } from "vitest";
import { useSyncedWebSearchPref } from "./use-synced-web-search-pref";
import { webSearchStorageKey } from "@/lib/web-search-pref";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function stubStorage(initial: Record<string, string> = {}) {
  const store = new Map(Object.entries(initial));
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
    },
  });
}

function renderHook(scope: string) {
  const result: { current: [boolean, (next: boolean) => void]; renders: boolean[] } = {
    current: [false, () => {}],
    renders: [],
  };
  function Probe() {
    result.current = useSyncedWebSearchPref(scope);
    result.renders.push(result.current[0]);
    return null;
  }
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => {
    root.render(<Probe />);
  });
  return {
    result,
    unmount: () => {
      act(() => {
        root.unmount();
      });
      el.remove();
    },
  };
}

describe("useSyncedWebSearchPref", () => {
  beforeEach(() => {
    stubStorage();
  });

  it("first render is off (SSR-agreeing) even with a stored opt-in, then syncs on", () => {
    stubStorage({ [webSearchStorageKey("test-scope")]: "1" });
    const { result, unmount } = renderHook("test-scope");
    try {
      expect(result.renders[0]).toBe(false);
      expect(result.current[0]).toBe(true);
    } finally {
      unmount();
    }
  });

  it("missing key first-renders off, then syncs to default-on", () => {
    const { result, unmount } = renderHook("fresh-scope");
    try {
      expect(result.renders[0]).toBe(false);
      expect(result.current[0]).toBe(true);
    } finally {
      unmount();
    }
  });

  it("stored opt-out stays off after mount", () => {
    stubStorage({ [webSearchStorageKey("out-scope")]: "0" });
    const { result, unmount } = renderHook("out-scope");
    try {
      expect(result.renders[0]).toBe(false);
      expect(result.current[0]).toBe(false);
    } finally {
      unmount();
    }
  });

  it("setter persists and updates", () => {
    const { result, unmount } = renderHook("write-scope");
    try {
      act(() => {
        result.current[1](false);
      });
      expect(result.current[0]).toBe(false);
      expect(window.localStorage.getItem(webSearchStorageKey("write-scope"))).toBe("0");
    } finally {
      unmount();
    }
  });
});
