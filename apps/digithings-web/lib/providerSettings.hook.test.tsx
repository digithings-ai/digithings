// @vitest-environment happy-dom
/**
 * AC3 regression test targeted at the hook itself (#2348).
 *
 * `providerSettings.test.ts` already proves `persistProviderPreference()`
 * never writes the raw key -- but AC3 is about `useProviderSettings().save()`,
 * one layer up. A future regression introduced only inside the hook's `save`
 * callback (e.g. an extra `localStorage.setItem` before it delegates to
 * `persistProviderPreference`) would pass that test while failing this one.
 *
 * `useState`/`useCallback` can't run outside React's renderer, so this needs
 * a real DOM to mount the hook via a throwaway component -- hence happy-dom
 * for this file only, rather than the repo's usual node-only SSR contracts
 * (there is no server-rendered markup to assert here; this is a live
 * localStorage-call assertion after invoking a returned callback).
 */
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useProviderSettings } from "./providerSettings";

describe("useProviderSettings().save() (#2348 AC3 — targets the hook, not persistProviderPreference directly)", () => {
  let store: Map<string, string>;
  let setItemSpy: ReturnType<typeof vi.fn>;
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    store = new Map<string, string>();
    setItemSpy = vi.fn((k: string, v: string) => {
      store.set(k, v);
    });
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: setItemSpy,
      removeItem: (k: string) => {
        store.delete(k);
      },
    });

    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.unstubAllGlobals();
  });

  it("never calls localStorage.setItem with the raw key, or under the legacy key name, when save() runs through the hook", () => {
    let api: ReturnType<typeof useProviderSettings> | undefined;
    function Harness() {
      api = useProviderSettings();
      return null;
    }

    act(() => {
      root.render(<Harness />);
    });

    act(() => {
      api!.save("xai-super-secret-key", "xai", "grok-4-3");
    });

    expect(setItemSpy).toHaveBeenCalled();
    for (const call of setItemSpy.mock.calls) {
      const [storedKeyName, storedValue] = call as [string, string];
      expect(storedKeyName).not.toBe("digichat:api_key");
      expect(storedValue).not.toContain("xai-super-secret-key");
    }
    expect(store.has("digichat:api_key")).toBe(false);

    // The non-secret provider/model preference IS expected to persist.
    expect(store.get("digichat:provider")).toBe("xai");
    expect(store.get("digichat:model")).toBe("grok-4-3");

    // And the hook's own returned state reflects the session-only key.
    expect(api!.isSet).toBe(true);
    expect(api!.apiKey).toBe("xai-super-secret-key");
  });

  it("save('') clears the stored provider/model preference through the hook", () => {
    let api: ReturnType<typeof useProviderSettings> | undefined;
    function Harness() {
      api = useProviderSettings();
      return null;
    }

    act(() => {
      root.render(<Harness />);
    });
    act(() => {
      api!.save("xai-super-secret-key", "xai", "grok-4-3");
    });
    act(() => {
      api!.clear();
    });

    expect(store.has("digichat:provider")).toBe(false);
    expect(store.has("digichat:model")).toBe(false);
    expect(api!.isSet).toBe(false);
    expect(api!.apiKey).toBe("");
  });
});
