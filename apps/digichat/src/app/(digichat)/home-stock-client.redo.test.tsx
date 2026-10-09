// @vitest-environment happy-dom
/**
 * Memory /redo must regenerate the thread on screen.
 * useRemoteThreadListRuntime keeps earlier runtimes mounted and does not
 * restart them when the main thread changes, so a shared redo ref stays on
 * the last thread that mounted.
 */
import { describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import type { AssistantRuntime } from "@assistant-ui/react";
import { DEFAULT_CLIENT_CONFIG } from "@/lib/deploy-config";
import {
  takePendingForceTool,
  takePendingTurnMode,
} from "@/lib/pending-chat-headers";
import { HomeStockClient } from "./home-stock-client";

type FakeChat = {
  id: string;
  messages: never[];
  status: "ready";
  regenerate: ReturnType<typeof vi.fn>;
};

const harness = vi.hoisted(() => ({
  threadIds: ["thread-a"] as string[],
  mainThreadId: "thread-a",
  renderingThreadId: "thread-a",
  runtimeHook: null as null | (() => unknown),
  chats: [] as FakeChat[],
  redo: (() => {}) as () => void,
  runtime: {
    threads: {
      getState: () => ({ mainThreadId: "thread-a" }),
      switchToNewThread: () => {},
    },
  },
}));

harness.runtime.threads.getState = () => ({
  mainThreadId: harness.mainThreadId,
});

vi.mock("@assistant-ui/react", async () => {
  const actual = await vi.importActual<typeof import("@assistant-ui/react")>(
    "@assistant-ui/react",
  );
  function MountedThreadRuntime({ id }: { id: string }) {
    harness.renderingThreadId = id;
    harness.runtimeHook?.();
    return null;
  }
  return {
    ...actual,
    useRemoteThreadListRuntime: ({
      runtimeHook,
    }: {
      runtimeHook: () => unknown;
    }) => {
      harness.runtimeHook = runtimeHook;
      return harness.runtime;
    },
    AssistantRuntimeProvider: ({
      children,
    }: {
      children: React.ReactNode;
    }) => (
      <>
        {harness.threadIds.map((id) => (
          <MountedThreadRuntime key={id} id={id} />
        ))}
        {children}
      </>
    ),
    RuntimeAdapterProvider: ({ children }: { children: React.ReactNode }) => (
      <>{children}</>
    ),
    AuiConfig: (c: unknown) => c,
    Suggestions: (s: unknown) => s,
    useAuiState: <T,>(
      selector: (s: {
        thread: { messages: unknown[] };
        threadListItem: { id: string };
      }) => T,
    ) =>
      selector({
        thread: { messages: [] },
        threadListItem: { id: harness.renderingThreadId },
      }),
  };
});

vi.mock("@ai-sdk/react", async () => {
  const React = await import("react");
  return {
    useChat: () => {
      const slot = React.useRef<FakeChat | null>(null);
      if (!slot.current) {
        const chat: FakeChat = {
          id: `chat-${harness.chats.length + 1}`,
          messages: [],
          status: "ready",
          regenerate: vi.fn(),
        };
        slot.current = chat;
        harness.chats.push(chat);
      }
      return slot.current;
    },
  };
});

vi.mock("@assistant-ui/ai-sdk", () => ({
  AssistantChatTransport: class {},
  useAISDKRuntime: () => ({} as AssistantRuntime),
}));

vi.mock("@digithings/ui/chat/skins", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@digithings/ui/chat/skins")>();
  return {
    ...actual,
    ThreadSkinView: () => <div data-testid="stock-thread" />,
  };
});

vi.mock("@/components/stock/memory-thread-list-sidebar", async () => {
  const { useEmbedChatPrefsOptional } = await import(
    "@digithings/ui/chat/stock"
  );
  return {
    MemoryThreadListSidebar: () => {
      const prefs = useEmbedChatPrefsOptional();
      if (prefs) harness.redo = prefs.redo;
      return <aside data-testid="memory-thread-list" />;
    },
  };
});

const clientConfig = {
  ...DEFAULT_CLIENT_CONFIG,
  persistence: "memory" as const,
  chrome: { ...DEFAULT_CLIENT_CONFIG.chrome, mode: "app" as const },
};

describe("HomeStockClient memory /redo", () => {
  it("regenerates the thread on screen after switching back to an earlier mounted runtime", () => {
    const view = render(
      <HomeStockClient clientConfig={clientConfig} userId="redo-screen" />,
    );
    expect(harness.chats).toHaveLength(1);
    const first = harness.chats[0]!;

    harness.threadIds = ["thread-a", "thread-b"];
    harness.mainThreadId = "thread-b";
    view.rerender(
      <HomeStockClient clientConfig={clientConfig} userId="redo-screen" />,
    );
    expect(harness.chats).toHaveLength(2);
    const second = harness.chats[1]!;

    harness.mainThreadId = "thread-a";
    view.rerender(
      <HomeStockClient clientConfig={clientConfig} userId="redo-screen" />,
    );
    expect(harness.chats).toHaveLength(2);

    harness.redo();

    expect([first.regenerate.mock.calls.length, second.regenerate.mock.calls.length]).toEqual([
      1, 0,
    ]);
    expect(takePendingTurnMode(first.id)).toBe("regenerate");
    expect(takePendingTurnMode(second.id)).toBeUndefined();
    takePendingForceTool("app:redo-screen");
    takePendingForceTool(first.id);
    takePendingForceTool(second.id);
  });
});
