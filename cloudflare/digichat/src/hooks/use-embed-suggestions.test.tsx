// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { useEmbedSuggestions } from "./use-embed-suggestions";
import { BASELINE_EMBED_SUGGESTIONS } from "../lib/baseline-embed";
import { getTenantSuggestionPool } from "../lib/embed-suggestion-pools";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderHookLocally<T>(callback: () => T): {
  result: { current: T; renders: T[] };
  rerender: (nextCallback: () => T) => void;
  unmount: () => void;
} {
  const result = { current: undefined as unknown as T, renders: [] as T[] };
  let renderCallback = callback;
  function Probe(): null {
    result.current = renderCallback();
    result.renders.push(result.current);
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(Probe));
  });
  return {
    result,
    rerender(nextCallback: () => T) {
      renderCallback = nextCallback;
      act(() => {
        root.render(createElement(Probe));
      });
    },
    unmount() {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

const BASELINE_CFG = {
  slug: "embed",
  suggestions: [...BASELINE_EMBED_SUGGESTIONS],
} as Parameters<typeof useEmbedSuggestions>[1];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useEmbedSuggestions hydration", () => {
  it("embeds a stable subset on first render", () => {
    const first = renderHookLocally(() => useEmbedSuggestions(undefined, BASELINE_CFG));
    const second = renderHookLocally(() => useEmbedSuggestions(undefined, BASELINE_CFG));
    // First committed render (what SSR ships and hydration expects) is identical
    // across mounts even though the post-mount pick reshuffles.
    expect(first.result.renders[0]).toEqual(second.result.renders[0]);
    expect(first.result.renders[0]).toEqual([...BASELINE_EMBED_SUGGESTIONS]);
    first.unmount();
    second.unmount();
  });

  it("reshuffles after mount", () => {
    // Deterministic draw sequence: blocks of three 0s then three 0.99s give
    // alternating Fisher-Yates orders, so variety holds without Math.random flakiness.
    const draws = Array.from({ length: 30 }, (_, i) => (Math.floor(i / 3) % 2 === 0 ? 0 : 0.99));
    let at = 0;
    const realRandom = Math.random;
    Math.random = () => draws[at++ % draws.length];
    try {
      const seen = new Set<string>();
      for (let i = 0; i < 10; i += 1) {
        const hook = renderHookLocally(() => useEmbedSuggestions(undefined, BASELINE_CFG));
        seen.add(hook.result.current.join("|"));
        hook.unmount();
      }
      expect(seen.size).toBeGreaterThan(1);
    } finally {
      Math.random = realRandom;
    }
  });

  it("keeps url override winning over the tenant pool", () => {
    const hook = renderHookLocally(() =>
      useEmbedSuggestions(["Ask about pricing", "Book a demo"], BASELINE_CFG),
    );
    expect(hook.result.current).toEqual(["Ask about pricing", "Book a demo"]);
    hook.unmount();
  });

  it("falls back to the tenant pool for known slugs", () => {
    const pool = getTenantSuggestionPool("datatapstream");
    expect(pool?.length).toBeGreaterThan(0);
    const hook = renderHookLocally(() =>
      useEmbedSuggestions(undefined, { slug: "datatapstream" } as Parameters<
        typeof useEmbedSuggestions
      >[1]),
    );
    expect(hook.result.current.length).toBeGreaterThan(0);
    expect(hook.result.current.length).toBeLessThanOrEqual(4);
    hook.unmount();
  });
});
