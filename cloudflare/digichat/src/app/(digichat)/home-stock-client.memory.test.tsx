// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { AssistantRuntime } from "@assistant-ui/react";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import { HomeStockClient } from "./home-stock-client";

const listRuntime = {
  threads: { switchToNewThread: vi.fn() },
} as unknown as AssistantRuntime;

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const emptyAuiState = { thread: { messages: [] as unknown[] } };
  return {
    ...actual,
    useRemoteThreadListRuntime: () => listRuntime,
    AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
    useAuiState: <T,>(selector: (s: typeof emptyAuiState) => T) => selector(emptyAuiState),
  };
});

vi.mock("@ai-sdk/react", () => ({
  useChat: () => ({ messages: [], status: "ready" }),
}));

vi.mock("@assistant-ui/ai-sdk", () => ({
  AssistantChatTransport: class {
    constructor(_opts: unknown) {}
  },
  useAISDKRuntime: () => ({} as AssistantRuntime),
}));

vi.mock("@/components/assistant-ui/skins", () => ({
  ThreadSkinView: ({ skin }: { skin: string }) => (
    <div data-testid="stock-thread" data-skin={skin}>
      stock thread
    </div>
  ),
}));

vi.mock("@/components/stock/memory-thread-list-sidebar", () => ({
  MemoryThreadListSidebar: () => (
    <aside data-testid="memory-thread-list" data-memory-thread-list />
  ),
}));

describe("HomeStockClient memory persistence", () => {
  it("mounts memory sidebar when persistence is memory", () => {
    render(
      <HomeStockClient
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          persistence: "memory",
          chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, mode: "app" },
        }}
        userId="u-test"
      />,
    );
    expect(screen.getByTestId("memory-thread-list")).toBeTruthy();
    expect(
      document.querySelector('[data-persistence="memory"]'),
    ).toBeTruthy();
    expect(screen.getByTestId("stock-thread")).toBeTruthy();
  });

  it("does not mount memory sidebar when persistence is none", () => {
    render(
      <HomeStockClient
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          persistence: "none",
          chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, mode: "app" },
        }}
      />,
    );
    expect(screen.queryByTestId("memory-thread-list")).toBeNull();
    expect(document.querySelector('[data-persistence="none"]')).toBeTruthy();
  });

  it("does not mount memory sidebar for layout templates", () => {
    render(
      <HomeStockClient
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          persistence: "memory",
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            mode: "app",
            skin: "webpage-assistant",
          },
        }}
      />,
    );
    expect(screen.queryByTestId("memory-thread-list")).toBeNull();
  });
});
