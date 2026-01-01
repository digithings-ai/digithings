// @vitest-environment happy-dom
/**
 * Stock home transport: `?private=1` and `/private` have to reach the header
 * the frozen AssistantChatTransport sends. The embed path is covered in
 * use-embed-digi-chat.test.ts.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import type { UIMessage } from "ai";
import type { AssistantRuntime } from "@assistant-ui/react";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import { seedPrivateMode } from "@/lib/product-slash-commands";
import { HomeStockClient } from "./home-stock-client";

type Prepare = (args: {
  messages: UIMessage[];
  id?: string;
  body?: unknown;
  headers?: HeadersInit;
}) => { headers: HeadersInit; body: unknown } | Promise<{ headers: HeadersInit; body: unknown }>;

const captured = vi.hoisted(() => ({
  prepare: null as Prepare | null,
}));

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  const emptyAuiState = { thread: { messages: [] as unknown[] } };
  return {
    ...actual,
    useRemoteThreadListRuntime: () => ({ threads: { switchToNewThread: vi.fn() } }),
    AssistantRuntimeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
    useAuiState: <T,>(selector: (s: typeof emptyAuiState) => T) => selector(emptyAuiState),
  };
});

vi.mock("@ai-sdk/react", () => ({
  useChat: () => ({ messages: [], status: "ready", regenerate: vi.fn() }),
}));

vi.mock("@assistant-ui/ai-sdk", () => ({
  AssistantChatTransport: class {
    constructor(opts: { prepareSendMessagesRequest?: Prepare }) {
      captured.prepare = opts.prepareSendMessagesRequest ?? null;
    }
  },
  useAISDKRuntime: () => ({}) as AssistantRuntime,
}));

vi.mock("@digithings/ui/chat/skins", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@digithings/ui/chat/skins")>();
  return {
    ...actual,
    ThreadSkinView: () => <div data-testid="stock-thread" />,
  };
});

vi.mock("@/components/stock/memory-thread-list-sidebar", () => ({
  MemoryThreadListSidebar: () => <aside data-testid="memory-thread-list" />,
}));

const clientConfig = {
  ...DEFAULT_CLIENT_CONFIG,
  persistence: "none" as const,
  chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, mode: "app" as const },
  features: { ...DEFAULT_CLIENT_CONFIG.features, privateMode: true },
};

describe("HomeStockClient private header", () => {
  afterEach(() => {
    seedPrivateMode({ tenantOptIn: false, urlPrivate: false });
    window.history.pushState({}, "", "/");
    captured.prepare = null;
  });

  it("sends X-Digi-Private from ?private=1 and drops it after the tenant opts out", async () => {
    window.history.pushState({}, "", "/?private=1");
    render(<HomeStockClient clientConfig={clientConfig} />);
    const prepare = captured.prepare;
    if (!prepare) throw new Error("stock transport was not constructed");
    const stored = [
      { id: "u1", role: "user" as const, parts: [{ type: "text" as const, text: "John Smith" }] },
    ];

    const on = await prepare({ messages: stored, id: "thread-1", body: undefined });
    expect(new Headers(on.headers).get("X-Digi-Private")).toBe("1");
    expect(JSON.stringify(on.body)).toContain("John Smith");
    expect(JSON.stringify(on.body)).not.toContain("PRIVATE DEMO SESSION");

    seedPrivateMode({ tenantOptIn: false, urlPrivate: true });
    const off = await prepare({ messages: stored, id: "thread-1", body: undefined });
    expect(new Headers(off.headers).has("X-Digi-Private")).toBe(false);
  });

  it("stays off when the tenant did not opt in", async () => {
    window.history.pushState({}, "", "/?private=1");
    render(
      <HomeStockClient
        clientConfig={{
          ...clientConfig,
          features: { ...clientConfig.features, privateMode: false },
        }}
      />,
    );
    const prepare = captured.prepare;
    if (!prepare) throw new Error("stock transport was not constructed");
    const sent = await prepare({ messages: [], id: "thread-1", body: undefined });
    expect(new Headers(sent.headers).has("X-Digi-Private")).toBe(false);
  });
});
