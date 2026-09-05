// @vitest-environment happy-dom
import { type ReactNode } from "react";
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { UIMessage } from "ai";
import {
  BYOK_PROVIDER_LIST,
  byokRequiresModel,
  type BYOKKeyState,
  type BYOKProvider,
} from "@/hooks/use-byok-key";

// prepareSendMessagesRequest is a closure built inside useMemo(() => new
// AssistantChatTransport({...})) in chat-panel.tsx — same situation as
// use-embed-digi-chat.test.ts. Capture the real config AssistantChatTransport is
// constructed with so the assertions below run against the actual closure,
// not a reimplementation of it.
type PrepareSendMessagesRequestResult = { headers: HeadersInit; body: unknown };
type PrepareSendMessagesRequestFn = (args: {
  messages: UIMessage[];
  id?: string;
  body?: unknown;
  headers?: HeadersInit;
}) => PrepareSendMessagesRequestResult | Promise<PrepareSendMessagesRequestResult>;

let capturedTransportConfig: { prepareSendMessagesRequest: PrepareSendMessagesRequestFn } | undefined;

function readCapturedTransportConfig() {
  return capturedTransportConfig;
}

vi.mock("@ai-sdk/react", () => ({
  useChat: vi.fn(() => ({
    messages: [],
    sendMessage: vi.fn(),
    status: "ready",
    error: undefined,
    regenerate: vi.fn(),
    setMessages: vi.fn(),
    stop: vi.fn(),
  })),
}));

vi.mock("ai", async (importOriginal) => {
  const actual = await importOriginal<typeof import("ai")>();
  return {
    ...actual,
    DefaultChatTransport: vi.fn().mockImplementation(function (config: unknown) {
      capturedTransportConfig = config as {
        prepareSendMessagesRequest: PrepareSendMessagesRequestFn;
      };
      return new actual.DefaultChatTransport(
        config as ConstructorParameters<typeof actual.DefaultChatTransport>[0],
      );
    }),
  };
});

vi.mock("@assistant-ui/ai-sdk", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@assistant-ui/ai-sdk")>();
  return {
    ...actual,
    AssistantChatTransport: vi.fn().mockImplementation(function (config: unknown) {
      capturedTransportConfig = config as {
        prepareSendMessagesRequest: PrepareSendMessagesRequestFn;
      };
      return new actual.AssistantChatTransport(
        config as ConstructorParameters<typeof actual.AssistantChatTransport>[0],
      );
    }),
    useAISDKRuntime: () => ({ kind: "runtime" }),
    useAISDKChat: () => ({
      messages: [],
      status: "ready",
      sendMessage: vi.fn(),
      stop: vi.fn(),
      setMessages: vi.fn(),
    }),
  };
});

vi.mock("@assistant-ui/react", () => ({
  AssistantRuntimeProvider: ({ children }: { children: ReactNode }) => children,
  ThreadPrimitive: {
    Root: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Viewport: ({ children, className }: { children?: ReactNode; className?: string }) => (
      <div className={className}>{children}</div>
    ),
    Empty: ({ children }: { children?: ReactNode }) => children,
    Messages: () => null,
  },
  ComposerPrimitive: {
    Root: ({ children }: { children?: ReactNode }) => children,
    Input: "textarea",
  },
  MessagePrimitive: { Root: "div", Parts: () => null },
  ActionBarPrimitive: { Root: "div", Copy: "button" },
}));

// Only useBYOKKey is faked — byokRequiresModel/BYOK_PROVIDER_LIST/etc. stay
// real so this test exercises the actual predicate chat-panel.tsx now calls,
// not a reimplementation of it.
let mockByokState: BYOKKeyState = { key: "", provider: "openrouter", model: "", isSet: false };
vi.mock("@/hooks/use-byok-key", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/use-byok-key")>();
  return {
    ...actual,
    useBYOKKey: () => ({
      ...mockByokState,
      setKey: vi.fn(),
      clearKey: vi.fn(),
    }),
  };
});

// Mocked away entirely — this test only needs the transport config ChatPanel
// builds, not real markdown/echarts/quant-strip rendering.
vi.mock("@digithings/digichat-ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@digithings/digichat-ui")>();
  return {
    ...actual,
    ChatActivities: () => null,
  };
});

import { ChatPanel } from "./chat-panel";
import {
  setPendingForceTool,
  setPendingTurnMode,
  takePendingForceTool,
  takePendingTurnMode,
} from "@/lib/pending-chat-headers";

function baseProps() {
  return {
    threadId: "t1",
    threadTitle: "New chat",
    initialMessages: [] as UIMessage[],
    onMessagesCommit: vi.fn(),
  };
}

async function callPrepareSendMessagesRequest(
  byokState: BYOKKeyState,
): Promise<{ headers: Headers; body: unknown }> {
  mockByokState = byokState;
  capturedTransportConfig = undefined;
  render(<ChatPanel {...baseProps()} />);
  const config = readCapturedTransportConfig();
  if (!config) {
    throw new Error("AssistantChatTransport was never constructed by ChatPanel");
  }
  const result = await config.prepareSendMessagesRequest({ messages: [], id: "t1", body: undefined });
  return { headers: new Headers(result.headers), body: result.body };
}

describe("ChatPanel prepareSendMessagesRequest — X-BYOK-Model (Fix 1 regression)", () => {
  beforeEach(() => {
    mockByokState = { key: "", provider: "openrouter", model: "", isSet: false };
  });

  // The pre-fix code was a hand-maintained OR-chain of
  // (openrouter|anthropic|gemini) that silently omitted xai — and would omit
  // any future 6th provider too. Iterating BYOK_PROVIDER_LIST itself (rather
  // than a hardcoded list here) is what makes this regress loudly the next
  // time a provider is added without updating this predicate.
  it.each(BYOK_PROVIDER_LIST)(
    "sets X-BYOK-Model for provider=%s whenever the user chose a model",
    async (provider: BYOKProvider) => {
      const { headers } = await callPrepareSendMessagesRequest({
        key: "test-key",
        provider,
        model: "some-model-slug",
        isSet: true,
      });

      expect(headers.get("X-BYOK-Key")).toBe("test-key");
      expect(headers.get("X-BYOK-Provider")).toBe(provider);
      expect(headers.get("X-BYOK-Model")).toBe("some-model-slug");
    },
  );

  // This assertion used to read `iff byokRequiresModel(provider)`, dropping the
  // header for providers whose catalog entry says the model is optional. Optional
  // is not "discard it": with no X-BYOK-Model, digigraph answers on *its own*
  // default, which on the shipped release config is an openrouter/… model billed
  // to the operator's key while the user's sits bound and unspent (#2490). The
  // flag governs whether a model is *mandatory*, never whether a chosen one is
  // forwarded.
  it("forwards a chosen model even where byokRequiresModel is false", async () => {
    const optional = BYOK_PROVIDER_LIST.filter((p) => !byokRequiresModel(p));
    // If the catalog ever makes every provider require a model this test would
    // pass by iterating nothing — fail loudly instead, since the regression it
    // guards is exactly about the optional case.
    expect(optional.length).toBeGreaterThan(0);
    for (const provider of optional) {
      const { headers } = await callPrepareSendMessagesRequest({
        key: "test-key",
        provider,
        model: "gpt-4o-mini",
        isSet: true,
      });
      expect(headers.get("X-BYOK-Model")).toBe("gpt-4o-mini");
    }
  });

  it("never sets X-BYOK-* headers at all when no key is set", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      key: "",
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
      isSet: false,
    });
    expect(headers.has("X-BYOK-Key")).toBe(false);
    expect(headers.has("X-BYOK-Provider")).toBe(false);
    expect(headers.has("X-BYOK-Model")).toBe(false);
  });

  it("omits X-BYOK-Model for a model-requiring provider when the model is blank", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      key: "test-key",
      provider: "xai",
      model: "   ",
      isSet: true,
    });
    expect(headers.has("X-BYOK-Model")).toBe(false);
  });
});

describe("ChatPanel prepareSendMessagesRequest — turn mode vs force-tool", () => {
  beforeEach(() => {
    takePendingForceTool("t1");
    takePendingTurnMode("t1");
    mockByokState = { key: "", provider: "openrouter", model: "", isSet: false };
  });

  it("sends X-Digi-Turn-Mode and omits force-tool on regenerate", async () => {
    setPendingTurnMode("t1", "regenerate");
    setPendingForceTool("t1", "digisearch");
    const { headers } = await callPrepareSendMessagesRequest({
      key: "",
      provider: "openrouter",
      model: "",
      isSet: false,
    });
    expect(headers.get("X-Digi-Turn-Mode")).toBe("regenerate");
    expect(headers.has("X-Digi-Force-Tool")).toBe(false);
  });

  it("sends X-Digi-Force-Tool on a plain send", async () => {
    setPendingForceTool("t1", "digisearch");
    const { headers } = await callPrepareSendMessagesRequest({
      key: "",
      provider: "openrouter",
      model: "",
      isSet: false,
    });
    expect(headers.get("X-Digi-Force-Tool")).toBe("digisearch");
    expect(headers.has("X-Digi-Turn-Mode")).toBe(false);
  });
});
