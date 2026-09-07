// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AssistantRuntime } from "@assistant-ui/react";
import { ProductStockShell } from "./product-shell";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";

vi.mock("@/app/(vanilla)/stock/thread.aui", () => ({
  Thread: () => <div data-testid="stock-thread">stock thread</div>,
}));

vi.mock("@/components/assistant-ui/skins", () => ({
  ThreadSkinView: ({ skin }: { skin: string }) => (
    <div data-testid="stock-thread" data-skin={skin}>
      stock thread
    </div>
  ),
}));

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  return {
    ...actual,
    AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
  };
});

describe("ProductStockShell", () => {
  it("mounts stock Thread with deploy chrome metadata", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            mode: "embed",
            welcome: "Ask about docs",
          },
          features: {
            ...DEFAULT_CLIENT_CONFIG.features,
            attachments: false,
            dictation: false,
          },
        }}
      />,
    );
    expect(screen.getByTestId("stock-thread")).toBeTruthy();
    const root = document.querySelector("[data-stock-product]");
    expect(root?.getAttribute("data-chrome-mode")).toBe("embed");
    expect(root?.getAttribute("data-thread-skin")).toBe("base");
    expect(root?.getAttribute("data-persistence")).toBe("none");
  });

  it("renders chatgpt skin metadata", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            skin: "chatgpt",
          },
        }}
      />,
    );
    const root = document.querySelector("[data-stock-product]");
    expect(root?.getAttribute("data-thread-skin")).toBe("chatgpt");
    expect(screen.getByTestId("stock-thread").getAttribute("data-skin")).toBe(
      "chatgpt",
    );
  });

  it("renders sideSlot inside the runtime provider for memory persistence", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        persistence="memory"
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          persistence: "memory",
          chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, mode: "app" },
        }}
        sideSlot={<aside data-testid="memory-side">threads</aside>}
      />,
    );
    const root = document.querySelector("[data-stock-product]");
    expect(root?.getAttribute("data-persistence")).toBe("memory");
    expect(screen.getByTestId("memory-side")).toBeTruthy();
    expect(root?.contains(screen.getByTestId("memory-side"))).toBe(true);
  });

  it("omits host header and sideSlot for layout templates", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        headerSlot={<div data-testid="host-header">hdr</div>}
        sideSlot={<aside data-testid="host-side">side</aside>}
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            skin: "webpage-assistant",
            mode: "app",
          },
        }}
      />,
    );
    expect(screen.queryByTestId("host-header")).toBeNull();
    expect(screen.queryByTestId("host-side")).toBeNull();
    expect(
      document.querySelector("[data-stock-product]")?.getAttribute("data-thread-skin"),
    ).toBe("webpage-assistant");
  });
});
