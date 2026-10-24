// @vitest-environment happy-dom
"use client";

import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/warmup-gate", () => ({
  startWarmup: () => {
    if (typeof document !== "undefined") {
      document.documentElement.dataset.digichatWarmup = "ready";
    }
    return Promise.resolve(true);
  },
  getWarmupServiceNames: () => ["auth", "assistant"],
}));
import { render, screen } from "@testing-library/react";
import type { AssistantRuntime } from "@assistant-ui/react";
import {
  ProductStockShell,
  resolveProductHeadline,
  resolveProductPlaceholder,
} from "./product-shell";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";

vi.mock("@digithings/ui/chat/stock/thread", () => ({
  Thread: () => <div data-testid="stock-thread">stock thread</div>,
}));

vi.mock("@digithings/ui/chat/skins", async (importOriginal) => {
  // The barrel now carries the registry alongside the dispatch (WS4) — keep
  // the real registry exports and only stub the dispatch.
  const actual =
    await importOriginal<typeof import("@digithings/ui/chat/skins")>();
  return {
    ...actual,
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
  };
});

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

  it("does not mount tool chips on the full-app digichat skin", () => {
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
    expect(document.querySelector("[data-tool-catalog]")).toBeNull();
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Vault" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Web search" })).toBeNull();
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

/**
 * Finding T2 / P0 (product-shell.tsx:385): the product surface used to end its
 * headline chain on the stock template line "How can I help you today?". The
 * fallback is now the deployment's own house copy, so the product never ships
 * the template's empty state.
 */
describe("product copy", () => {
  const emptyCopy = {
    ...DEFAULT_CLIENT_CONFIG,
    chrome: {
      ...DEFAULT_CLIENT_CONFIG.chrome,
      welcome: "",
      title: "",
      placeholder: "",
    },
  };

  it("falls back to the deployment's house copy, never the stock template", () => {
    expect(resolveProductHeadline(emptyCopy)).toBe("Ask about digithings");
    expect(resolveProductPlaceholder(emptyCopy)).toBe("Ask a question");
    expect(resolveProductHeadline(emptyCopy)).not.toMatch(/how can i help you/i);
  });

  it("keeps the deployment copy when the config sets it", () => {
    const cfg = {
      ...DEFAULT_CLIENT_CONFIG,
      chrome: {
        ...DEFAULT_CLIENT_CONFIG.chrome,
        welcome: "Ask the vault.",
        title: "ask digichat",
        placeholder: "Ask the vault a question",
      },
    };
    expect(resolveProductHeadline(cfg)).toBe("Ask the vault.");
    expect(resolveProductPlaceholder(cfg)).toBe("Ask the vault a question");
  });

  it("lets a host override win over the deployment copy", () => {
    expect(
      resolveProductHeadline(
        { ...DEFAULT_CLIENT_CONFIG, chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, welcome: "Ask the vault." } },
        "  Ask this thread.  ",
      ),
    ).toBe("Ask this thread.");
  });

  it("keeps the stock template line out of the shell source", async () => {
    const { readFile } = await import("node:fs/promises");
    const path = await import("node:path");
    const source = await readFile(
      path.join(process.cwd(), "src/components/stock/product-shell.tsx"),
      "utf8",
    );
    expect(source).not.toMatch(/How can I help you today\?/);
  });
});
