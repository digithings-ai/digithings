// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AssistantRuntime } from "@assistant-ui/react";
import { ProductStockShell } from "./product-shell";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import {
  takePendingForceTool,
} from "@/lib/pending-chat-headers";

vi.mock("@/app/(baseline)/stock/thread.aui", () => ({
  Thread: () => <div data-testid="stock-thread">stock thread</div>,
}));

vi.mock("@/components/assistant-ui/skins", () => ({
  ThreadSkinView: ({
    skin,
    composerLayout,
  }: {
    skin: string;
    composerLayout?: string;
  }) => (
    <div
      data-testid="stock-thread"
      data-skin={skin}
      data-composer-layout={composerLayout ?? ""}
    >
      stock thread
    </div>
  ),
}));

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const emptyAuiState = { thread: { messages: [] as unknown[] } };
  return {
    ...actual,
    AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
    useAuiState: <T,>(selector: (s: typeof emptyAuiState) => T) => selector(emptyAuiState),
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
    expect(root?.getAttribute("data-thread-skin")).toBe("digichat");
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

  it("forces left align and rose host class for the first-party digichat skin", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            skin: "digichat",
            transcript: { userAlign: "right" },
          },
        }}
      />,
    );
    const root = document.querySelector("[data-stock-product]");
    expect(root?.getAttribute("data-thread-skin")).toBe("digichat");
    expect(root?.getAttribute("data-user-align")).toBe("left");
    expect(root?.className).toContain("accent-digichat");
    expect(screen.getByTestId("stock-thread").getAttribute("data-skin")).toBe(
      "digichat",
    );
  });

  it("omits the tool catalog on embed / modal / sidebar (#3733)", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        sessionKey="embed-host"
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            mode: "embed",
            skin: "digichat",
          },
          tools: {
            allowUserToggle: true,
            catalog: [
              { id: "digisearch", default: true, label: "Search" },
              { id: "digivault", default: true, label: "Vault" },
              { id: "web_search", default: true, label: "Web search" },
            ],
          },
          gate: { ...DEFAULT_CLIENT_CONFIG.gate, webSearch: true },
        }}
      />,
    );
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
  });

  it("keeps Search / Vault / Web search on the full-app digichat skin", async () => {
    takePendingForceTool("embed-host");
    const user = userEvent.setup();
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        sessionKey="embed-host"
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            mode: "app",
            skin: "digichat",
          },
          tools: {
            allowUserToggle: true,
            catalog: [
              { id: "digisearch", default: true, label: "Search" },
              { id: "digivault", default: true, label: "Vault" },
              { id: "web_search", default: false, label: "Web search" },
            ],
          },
          gate: { ...DEFAULT_CLIENT_CONFIG.gate, webSearch: true },
        }}
      />,
    );
    const bar = document.querySelector("[data-tool-catalog]");
    expect(bar).toBeTruthy();
    expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Vault" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Web search" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(takePendingForceTool("embed-host")).toBe("digisearch");
  });

  it("omits the tool catalog on layout templates", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        sessionKey="embed-host"
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            skin: "webpage-assistant",
          },
          tools: {
            allowUserToggle: true,
            catalog: [
              { id: "digisearch", default: true, label: "Search" },
              { id: "digivault", default: true, label: "Vault" },
            ],
          },
        }}
      />,
    );
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
  });

  it("forwards composerLayout to the skin view", () => {
    const runtime = {} as AssistantRuntime;
    render(
      <ProductStockShell
        runtime={runtime}
        composerLayout="compact"
        clientConfig={DEFAULT_CLIENT_CONFIG}
      />,
    );
    expect(
      screen.getByTestId("stock-thread").getAttribute("data-composer-layout"),
    ).toBe("compact");
  });
});
