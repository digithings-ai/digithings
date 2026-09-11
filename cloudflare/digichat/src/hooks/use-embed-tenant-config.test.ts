// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, createElement, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  DEFAULT_EMBED_TENANT_CONFIG,
  type EmbedTenantClientConfig,
  useEmbedTenantConfig,
} from "./use-embed-tenant-config";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function renderHookLocally<T>(callback: () => T): {
  result: { current: T };
  rerender: (nextCallback: () => T) => void;
  unmount: () => void;
} {
  const result = { current: undefined as unknown as T };
  let renderCallback = callback;
  let forceRender: (() => void) | undefined;
  function TestComponent() {
    const [, setRenderVersion] = useState(0);
    forceRender = () => setRenderVersion((version) => version + 1);
    result.current = renderCallback();
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(TestComponent));
  });
  return {
    result,
    rerender: (nextCallback) => {
      renderCallback = nextCallback;
      act(() => {
        forceRender?.();
      });
    },
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

async function flushEffects(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const resolvedConfig: EmbedTenantClientConfig = {
  slug: "customer",
  gateMode: "ungated",
  theme: "light",
  accent: { color: "#123456", foreground: "#ffffff" },
  welcome: "Welcome",
  suggestions: ["Ask a question"],
  showByok: true,
  layout: "embed",
  llmAccess: "free_then_byok",
  attribution: true,
  showLanguageSelector: true,
};

describe("useEmbedTenantConfig", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts with the closed default configuration", () => {
    vi.mocked(fetch).mockReturnValue(new Promise(() => {}));

    const hook = renderHookLocally(() => useEmbedTenantConfig());

    expect(hook.result.current).toEqual(DEFAULT_EMBED_TENANT_CONFIG);
    hook.unmount();
  });

  it.each(["turn_limited", "ungated", "trial_form"] as const)(
    "accepts a valid %s response and forwards the resolved host and token",
    async (gateMode) => {
      const config = { ...resolvedConfig, gateMode };
      vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(config)));

      const hook = renderHookLocally(() =>
        useEmbedTenantConfig("tenant-token", "https://customer.example"),
      );
      await flushEffects();

      expect(hook.result.current).toEqual(config);
      expect(fetch).toHaveBeenCalledWith("/api/embed/tenant-config", {
        headers: {
          "X-Embed-Host": "https://customer.example",
          "X-Embed-Token": "tenant-token",
        },
      });
      hook.unmount();
    },
  );

  it.each([
    ["a non-OK response", () => Promise.resolve(new Response(null, { status: 503 }))],
    ["a rejected request", () => Promise.reject(new Error("network unavailable"))],
    ["a malformed gate mode", () =>
      Promise.resolve(new Response(JSON.stringify({ ...resolvedConfig, gateMode: "open" })))],
  ])("keeps the initial gated config after %s", async (_case, response) => {
    vi.mocked(fetch).mockImplementation(response);

    const hook = renderHookLocally(() => useEmbedTenantConfig());
    await flushEffects();

    expect(hook.result.current).toEqual(DEFAULT_EMBED_TENANT_CONFIG);
    hook.unmount();
  });

  it("retains a server-resolved initial config until a valid refresh supersedes it", async () => {
    vi.mocked(fetch).mockResolvedValue(
      new Response(JSON.stringify({ ...resolvedConfig, gateMode: "trial_form" })),
    );
    const initial = { ...resolvedConfig, gateMode: "turn_limited" as const };

    const hook = renderHookLocally(() => useEmbedTenantConfig(undefined, undefined, initial));

    expect(hook.result.current).toEqual(initial);
    await flushEffects();
    expect(hook.result.current).toEqual({ ...resolvedConfig, gateMode: "trial_form" });
    hook.unmount();
  });

  it("ignores an old response after the hook inputs change", async () => {
    const resolveFetches: Array<(response: Response) => void> = [];
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetches.push(resolve);
        }),
    );
    const hook = renderHookLocally(() =>
      useEmbedTenantConfig("first-token", "https://first.example"),
    );
    await flushEffects();
    hook.rerender(() => useEmbedTenantConfig("second-token", "https://second.example"));
    await flushEffects();
    expect(resolveFetches).toHaveLength(2);

    await act(async () => {
      resolveFetches[1]?.(new Response(JSON.stringify({ ...resolvedConfig, slug: "second" })));
      await Promise.resolve();
    });
    expect(hook.result.current).toEqual({ ...resolvedConfig, slug: "second" });

    await act(async () => {
      resolveFetches[0]?.(
        new Response(JSON.stringify({ ...resolvedConfig, slug: "first", gateMode: "turn_limited" })),
      );
      await Promise.resolve();
    });
    expect(hook.result.current).toEqual({ ...resolvedConfig, slug: "second" });
    hook.unmount();
  });
});
