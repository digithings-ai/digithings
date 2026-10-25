// @vitest-environment happy-dom
"use client";

/**
 * The starter chips a tenant defines are capped at the welcome row.
 *
 * The house tenant defines 8, OCC 8, DataTap 5. All of them reaching the
 * welcome was the "extensive list" the owner called out; the product shell is
 * the single boundary every surface mounts, so the cap is asserted here — 8
 * defined, 4 rendered.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { AssistantRuntime } from "@assistant-ui/react";

vi.mock("@/lib/warmup-gate", () => ({
  startWarmup: () => Promise.resolve(true),
  getWarmupServiceNames: () => ["auth", "assistant"],
}));

// The chips come from skinChrome, which is what every non-stock skin renders.
vi.mock("@digithings/ui/chat/stock/thread", () => ({
  Thread: () => <div data-testid="stock-thread">stock thread</div>,
}));

vi.mock("@digithings/ui/chat/skins", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@digithings/ui/chat/skins")>();
  const { useSkinChrome } = await import("@digithings/ui/chat/stock");
  return {
    ...actual,
    ThreadSkinView: ({ skin }: { skin: string }) => {
      const chrome = useSkinChrome();
      return (
        <div data-testid="skin-chrome" data-skin={skin}>
          {chrome.suggestions.map((prompt) => (
            <span key={prompt} data-testid="starter-chip">
              {prompt}
            </span>
          ))}
        </div>
      );
    },
  };
});

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const emptyAuiState = { thread: { messages: [] as unknown[] } };
  return {
    ...actual,
    AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
    useAuiState: <T,>(selector: (s: typeof emptyAuiState) => T) =>
      selector(emptyAuiState),
  };
});

const EIGHT = [
  "What does digigraph orchestrate?",
  "How do I run a backtest?",
  "Which models are available?",
  "What is in the knowledge base?",
  "How does digikey issue a token?",
  "Show me the MCP tool catalog",
  "What did the last release ship?",
  "How do I deploy the stack?",
];

afterEach(() => {
  cleanup();
});

describe("ProductStockShell starter chips", () => {
  it("shows four of the eight suggestions a tenant defines", async () => {
    const { ProductStockShell } = await import("./product-shell");
    const { DEFAULT_CLIENT_CONFIG } = await import("@/lib/deploy-config");
    render(
      <ProductStockShell
        runtime={{} as AssistantRuntime}
        clientConfig={{
          ...DEFAULT_CLIENT_CONFIG,
          chrome: {
            ...DEFAULT_CLIENT_CONFIG.chrome,
            skin: "digichat",
            mode: "embed",
            suggestions: EIGHT,
          },
        }}
      />,
    );

    const chips = screen.getAllByTestId("starter-chip");
    expect(chips).toHaveLength(4);
    expect(chips.map((chip) => chip.textContent)).toEqual(EIGHT.slice(0, 4));
  });
});
