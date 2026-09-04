// @vitest-environment happy-dom
import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import type { UIMessage } from "ai";
import {
  isEmbedTrialUnlockedAtSend,
  chatAccessTokenAtSend,
  uiMessageToDigiChat,
  useEmbedDigiChat,
  setPendingForceTool,
  takePendingForceTool,
} from "./use-embed-digi-chat";
import { ACTIVITY_PART_TYPE } from "@/lib/chat-activity";
import {
  resetLiveTrialUnlockedForTests,
  writeTrialUnlocked,
  writeChatAccessToken,
} from "@/lib/embed-gate";

// prepareSendMessagesRequest is a closure built inside useMemo(() => new
// DefaultChatTransport({...})) in use-embed-digi-chat.ts — there is no
// existing harness in this file for asserting on its output (the other
// describe blocks below only exercise plain exported functions). Capture the
// real config DefaultChatTransport is constructed with so the assertions
// below run against the actual closure, not a reimplementation of it.
//
// This intentionally does NOT use @testing-library/react's renderHook: in
// this npm workspace, @testing-library/react is hoisted to the repo-root
// node_modules and resolves "react"/"react-dom" from there, while this hook
// file (frontend/digichat/src/hooks/) resolves "react" from digichat's own
// local node_modules — a different react version. Rendering with one copy
// while the hook calls useMemo/useCallback from the other trips React's
// "Invalid hook call" (mismatched dispatcher). Importing react/react-dom
// directly from this test file resolves the same local copy the hook under
// test uses, so a minimal hand-rolled render harness sidesteps the conflict
// without touching workspace-wide dependency/config files.
type PrepareSendMessagesRequestResult = { headers: Record<string, string>; body: unknown };
type PrepareSendMessagesRequestFn = (args: {
  messages: UIMessage[];
  body?: unknown;
}) => PrepareSendMessagesRequestResult | Promise<PrepareSendMessagesRequestResult>;

let capturedTransportConfig: { prepareSendMessagesRequest: PrepareSendMessagesRequestFn } | undefined;

// Reading through a function (rather than the module-level binding directly)
// stops TS's control-flow analysis from carrying the "just reset to undefined"
// narrowing across the renderHookLocally(...) call below, where the mock
// above actually reassigns it — without this indirection tsc narrows the
// post-guard type to `never` even though the mock provably ran.
function readCapturedTransportConfig() {
  return capturedTransportConfig;
}

// useChat itself is hoisted to the repo root the same way @testing-library/react
// is (see above) — its internal useState/useRef calls would run against root's
// react copy even once the transport-construction useMemo above is fixed. This
// test only needs the transport config useChat is called with, so stub it out
// entirely rather than executing its real (foreign-copy) hook internals.
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
    // `new DefaultChatTransport(...)` requires the mock to be constructible —
    // an arrow-function mockImplementation would fail with "is not a
    // constructor", so this uses `function` deliberately.
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

// React 19's act() refuses to run unless this flag is set — @testing-library/react
// normally sets it for you; the hand-rolled harness above must do it itself.
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/** Minimal local stand-in for @testing-library/react's renderHook — see comment above. */
function renderHookLocally(callback: () => void): { unmount: () => void } {
  function TestComponent() {
    callback();
    return null;
  }
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => {
    root.render(createElement(TestComponent));
  });
  return {
    unmount: () => {
      act(() => {
        root.unmount();
      });
      container.remove();
    },
  };
}

type EmbedDigiChatOptions = Parameters<typeof useEmbedDigiChat>[0];

function baseEmbedOptions(overrides: Partial<EmbedDigiChatOptions> = {}): EmbedDigiChatOptions {
  return {
    accent: "#4f46e5",
    embedHost: "https://example.com",
    ...overrides,
  };
}

async function callPrepareSendMessagesRequest(
  overrides: Partial<EmbedDigiChatOptions> = {},
): Promise<{ headers: Headers; body: unknown }> {
  capturedTransportConfig = undefined;
  const { unmount } = renderHookLocally(() => useEmbedDigiChat(baseEmbedOptions(overrides)));
  const config = readCapturedTransportConfig();
  if (!config) {
    throw new Error("DefaultChatTransport was never constructed by useEmbedDigiChat");
  }
  const result = await config.prepareSendMessagesRequest({
    messages: [],
    body: undefined,
  });
  unmount();
  return { headers: new Headers(result.headers), body: result.body };
}

function tracePart(label: string, status: string, id: string) {
  return {
    type: "data-digigraphTrace" as const,
    id,
    data: { v: 1, type: "external_activity", payload: { label, status } },
  };
}

function assistantMessage(parts: UIMessage["parts"]): UIMessage {
  return { id: "m1", role: "assistant", parts } as UIMessage;
}

describe("isEmbedTrialUnlockedAtSend", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    // @ts-expect-error — minimal localStorage for the helper under test
    globalThis.localStorage = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    };
    resetLiveTrialUnlockedForTests();
  });

  it("is false when nothing has unlocked this host", () => {
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream")).toBe(false);
  });

  it("reads unlock written after the frozen transport was created", () => {
    // Simulates: transport closed over trialUnlocked=false, then parent posted
    // datatap:unlocked which called writeTrialUnlocked.
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", false)).toBe(false);
    writeTrialUnlocked("https://datatap.stream", true);
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", false)).toBe(true);
  });

  it("honors an explicit prop fallback when storage is empty", () => {
    expect(isEmbedTrialUnlockedAtSend("https://datatap.stream", true)).toBe(true);
  });
});

describe("uiMessageToDigiChat trace de-duplication", () => {
  it("collapses repeated identical trace labels into one activity", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-1"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities).toEqual([
      { kind: "trace", label: "Searching DataTapStream docs…", done: false },
    ]);
  });

  it("marks a collapsed step done if any frame for that label completed", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Searching DataTapStream docs…", "completed", "relay-trace-1"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities).toEqual([
      { kind: "trace", label: "Searching DataTapStream docs…", done: true },
    ]);
  });

  it("keeps distinct labels as separate steps in first-seen order", () => {
    const msg = assistantMessage([
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-0"),
      tracePart("Reading results…", "in_progress", "relay-trace-1"),
      tracePart("Searching DataTapStream docs…", "in_progress", "relay-trace-2"),
    ]);

    const { activities } = uiMessageToDigiChat(msg);

    expect(activities?.map((a) => a.kind === "trace" && a.label)).toEqual([
      "Searching DataTapStream docs…",
      "Reading results…",
    ]);
  });

  it("joins text parts and leaves activities undefined when no traces", () => {
    const msg = assistantMessage([
      { type: "text", text: "Hello " },
      { type: "text", text: "world" },
    ] as UIMessage["parts"]);

    const result = uiMessageToDigiChat(msg);

    expect(result.content).toBe("Hello world");
    expect(result.activities).toBeUndefined();
  });
});

const activityPart = (data: unknown) => ({ type: ACTIVITY_PART_TYPE, data });

describe("uiMessageToDigiChat activity parts", () => {
  it("projects activity spans into rich rows", () => {
    const msg = {
      id: "a1",
      role: "assistant",
      parts: [
        { type: "text", text: "Here you go." },
        activityPart({
          operation: "retrieve",
          toolName: "file_search",
          query: "auth",
          status: "completed",
          label: "Sources",
          documents: [{ title: "Auth", path: "https://x/auth" }],
        }),
      ],
    } as unknown as UIMessage;

    expect(uiMessageToDigiChat(msg)).toEqual({
      role: "assistant",
      content: "Here you go.",
      activities: [
        {
          kind: "tool_result",
          name: "file_search",
          query: "auth",
          hits: [{ title: "Auth", path: "https://x/auth" }],
          count: 1,
        },
      ],
    });
  });

  // The allowlist has to hold at the client boundary too, not only at the writer.
  it("drops a malformed span rather than rendering it", () => {
    const msg = {
      id: "a2",
      role: "assistant",
      parts: [{ type: "text", text: "hi" }, activityPart({ operation: "exfiltrate" })],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toBeUndefined();
  });

  // Compatibility window: a page cached across a deploy still speaks the old part.
  it("still renders a legacy digigraphTrace part when no activity parts are present", () => {
    const msg = {
      id: "a3",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Planning", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "Planning", done: true },
    ]);
  });

  // Activity parts win outright — a mid-stream deploy must not double-render.
  it("ignores legacy trace parts when activity parts are present", () => {
    const msg = {
      id: "a4",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "chat", status: "completed", label: "New" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Old", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toEqual([
      { kind: "trace", label: "New", done: true },
    ]);
  });

  // When both legacy trace and activity parts appear in one message (e.g. rolling
  // deploy), activity parts win — the embed hook must render that step once.
  it("renders a step once, not twice, when the same step arrives as both a legacy and an activity part", () => {
    const msg = {
      id: "a6",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "chat", status: "completed", label: "Searching…" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Searching…", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    const { activities } = uiMessageToDigiChat(msg);
    expect(activities).toEqual([{ kind: "trace", label: "Searching…", done: true }]);
    expect(activities).toHaveLength(1);
  });

  // Discriminating case: even when all activity spans are malformed, the presence of activity
  // parts gates out the legacy trace. A count-based gate would incorrectly fall back to legacy.
  it("ignores legacy trace even when all activity parts are malformed", () => {
    const msg = {
      id: "a5",
      role: "assistant",
      parts: [
        { type: "text", text: "hi" },
        activityPart({ operation: "exfiltrate" }),
        {
          type: "data-digigraphTrace",
          data: { v: 1, type: "external_activity", payload: { label: "Legacy", status: "completed" } },
        },
      ],
    } as unknown as UIMessage;
    expect(uiMessageToDigiChat(msg).activities).toBeUndefined();
  });
});

// Same freeze reason as the unlock flag (#1339, PR #1882): the transport is frozen on first
// render, so the token must be read when the request is built, not closed over.
describe("chatAccessTokenAtSend", () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    // @ts-expect-error — minimal localStorage for the helper under test
    globalThis.localStorage = {
      getItem: (k: string) => (store.has(k) ? store.get(k)! : null),
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
      clear: () => {
        store.clear();
      },
    };
  });

  it("reads the token at send time", () => {
    writeChatAccessToken("https://datatap.stream", "id.secret");
    expect(chatAccessTokenAtSend("https://datatap.stream")).toBe("id.secret");
  });

  it("is null when the host has no token", () => {
    expect(chatAccessTokenAtSend("https://datatap.stream")).toBeNull();
  });
});

describe("useEmbedDigiChat prepareSendMessagesRequest — X-Digi-Language", () => {
  it("sets X-Digi-Language when getResponseLanguage returns a non-English curated code", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      getResponseLanguage: () => "de",
    });
    expect(headers.get("X-Digi-Language")).toBe("de");
  });

  it("omits X-Digi-Language when getResponseLanguage returns English, or is unset", async () => {
    const { headers: withEnglish } = await callPrepareSendMessagesRequest({
      getResponseLanguage: () => "en",
    });
    expect(withEnglish.has("X-Digi-Language")).toBe(false);

    const { headers: withUnset } = await callPrepareSendMessagesRequest({});
    expect(withUnset.has("X-Digi-Language")).toBe(false);
  });

  // Regression for #2103 final review's Critical finding: prepareSendMessagesRequest
  // must read the language FRESH at send time, not close over the value that existed
  // when the transport (and this closure) were first built. useChat never adopts a
  // rebuilt transport after first render (#1339), so if this closure captured the
  // language by value, a language picked in the dropdown after mount would never
  // reach the outgoing header — only the initial detectBrowserLanguageCode() value
  // ever would. This test captures prepareSendMessagesRequest ONCE, then calls that
  // SAME closure twice, changing only what the getter returns in between — no
  // remount, no new transport, no new closure. Against the pre-fix `responseLanguage:
  // string` param captured by value, the second call would still report the first
  // call's language; against the fix, it reports whatever the getter returns at call
  // time.
  it("reads the language fresh on every call, not the value captured when the transport was built", async () => {
    let currentLanguage = "en";
    const { unmount } = renderHookLocally(() =>
      useEmbedDigiChat(baseEmbedOptions({ getResponseLanguage: () => currentLanguage })),
    );
    const config = readCapturedTransportConfig();
    if (!config) {
      throw new Error("DefaultChatTransport was never constructed by useEmbedDigiChat");
    }

    const first = await config.prepareSendMessagesRequest({ messages: [], body: undefined });
    expect(new Headers(first.headers).has("X-Digi-Language")).toBe(false);

    // Simulate picking a new language in the dropdown AFTER mount, with no
    // remount/unmount in between — exactly the interaction the Critical
    // finding says was broken.
    currentLanguage = "de";
    const second = await config.prepareSendMessagesRequest({ messages: [], body: undefined });
    expect(new Headers(second.headers).get("X-Digi-Language")).toBe("de");

    unmount();
  });
});

describe("useEmbedDigiChat prepareSendMessagesRequest — X-Digi-Force-Tool", () => {
  beforeEach(() => {
    takePendingForceTool("https://example.com");
  });

  it("omits the header when send did not force a tool", async () => {
    const { headers } = await callPrepareSendMessagesRequest({});
    expect(headers.has("X-Digi-Force-Tool")).toBe(false);
  });

  it("isolates pending force-tool by embed host", () => {
    setPendingForceTool("https://a.example", "digisearch");
    setPendingForceTool("https://b.example", "digivault_search_notes");
    expect(takePendingForceTool("https://a.example")).toBe("digisearch");
    expect(takePendingForceTool("https://a.example")).toBeUndefined();
    expect(takePendingForceTool("https://b.example")).toBe("digivault_search_notes");
  });

  it("reads the force tool at send time, then clears it", async () => {
    capturedTransportConfig = undefined;
    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions());
    });
    const config = readCapturedTransportConfig();
    if (!config || !chat) {
      throw new Error("useEmbedDigiChat did not construct a transport");
    }
    chat.send("RS256 token exchange", { forceTool: "digisearch" });
    const first = await config.prepareSendMessagesRequest({ messages: [], body: undefined });
    expect(new Headers(first.headers).get("X-Digi-Force-Tool")).toBe("digisearch");
    const second = await config.prepareSendMessagesRequest({ messages: [], body: undefined });
    expect(new Headers(second.headers).has("X-Digi-Force-Tool")).toBe(false);
    unmount();
  });
});

describe("useEmbedDigiChat reset (/new)", () => {
  const host = "https://example.com";
  const storageKey = `digichat_embed_conversation:${host}`;

  beforeEach(() => {
    takePendingForceTool(host);
    window.sessionStorage.clear();
  });

  it("clears transcript, stored conversation id, and pending force-tool", () => {
    capturedTransportConfig = undefined;
    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions({ embedHost: host }));
    });
    if (!chat) {
      throw new Error("useEmbedDigiChat did not return a controller");
    }
    window.sessionStorage.setItem(storageKey, "foundry-conv-123");
    setPendingForceTool(host, "digisearch");

    chat.reset();

    expect(window.sessionStorage.getItem(storageKey)).toBeNull();
    expect(takePendingForceTool(host)).toBeUndefined();
    unmount();
  });
});

describe("useEmbedDigiChat turn mutation (#3466)", () => {
  const host = "https://digithings.ai";

  beforeEach(() => {
    takePendingForceTool(host);
    vi.clearAllMocks();
  });

  it("exposes regenerate + editLastUser for digigraph (default)", () => {
    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions({ embedHost: host }));
    });
    expect(chat?.regenerate).toBeTypeOf("function");
    expect(chat?.editLastUser).toBeTypeOf("function");
    expect(chat?.onRetry).toBeTypeOf("function");
    unmount();
  });

  it("omits regenerate + editLastUser + onRetry when allowClientTurnMutation is false", () => {
    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(
        baseEmbedOptions({ embedHost: host, allowClientTurnMutation: false }),
      );
    });
    expect(chat?.regenerate).toBeUndefined();
    expect(chat?.editLastUser).toBeUndefined();
    expect(chat?.onRetry).toBeUndefined();
    unmount();
  });

  it("exposes regenerate + editLastUser when Foundry opts into turn mutation", () => {
    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(
        baseEmbedOptions({ embedHost: host, allowClientTurnMutation: true }),
      );
    });
    expect(chat?.regenerate).toBeTypeOf("function");
    expect(chat?.editLastUser).toBeTypeOf("function");
    unmount();
  });

  it("clears pending force-tool before regenerate (slash is send-only)", async () => {
    const { useChat } = await import("@ai-sdk/react");
    const regenerate = vi.fn();
    vi.mocked(useChat).mockReturnValueOnce({
      messages: [],
      sendMessage: vi.fn(),
      status: "ready",
      error: undefined,
      regenerate,
      setMessages: vi.fn(),
      stop: vi.fn(),
    } as ReturnType<typeof useChat>);

    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions({ embedHost: host }));
    });
    setPendingForceTool(host, "digisearch");
    chat?.regenerate?.();
    expect(takePendingForceTool(host)).toBeUndefined();
    expect(regenerate).toHaveBeenCalledOnce();
    unmount();
  });

  it("editLastUser truncates past the last user turn and sends without force-tool", async () => {
    const { useChat } = await import("@ai-sdk/react");
    const sendMessage = vi.fn();
    const setMessages = vi.fn();
    const prior: UIMessage[] = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "old question" }] },
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "old answer" }] },
    ];
    vi.mocked(useChat).mockReturnValueOnce({
      messages: prior,
      sendMessage,
      status: "ready",
      error: undefined,
      regenerate: vi.fn(),
      setMessages,
      stop: vi.fn(),
    } as ReturnType<typeof useChat>);

    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions({ embedHost: host }));
    });
    setPendingForceTool(host, "digisearch");
    chat?.editLastUser?.("fixed question");
    expect(setMessages).toHaveBeenCalledWith([]);
    expect(sendMessage).toHaveBeenCalledWith({
      role: "user",
      parts: [{ type: "text", text: "fixed question" }],
    });
    expect(takePendingForceTool(host)).toBeUndefined();
    unmount();
  });

  it("editLastUser no-ops on empty text", async () => {
    const { useChat } = await import("@ai-sdk/react");
    const sendMessage = vi.fn();
    const setMessages = vi.fn();
    vi.mocked(useChat).mockReturnValueOnce({
      messages: [
        { id: "u1", role: "user", parts: [{ type: "text", text: "q" }] },
      ],
      sendMessage,
      status: "ready",
      error: undefined,
      regenerate: vi.fn(),
      setMessages,
      stop: vi.fn(),
    } as ReturnType<typeof useChat>);

    let chat: ReturnType<typeof useEmbedDigiChat> | undefined;
    const { unmount } = renderHookLocally(() => {
      chat = useEmbedDigiChat(baseEmbedOptions({ embedHost: host }));
    });
    chat?.editLastUser?.("   ");
    expect(setMessages).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    unmount();
  });
});

describe("useEmbedDigiChat prepareSendMessagesRequest — X-BYOK-Model (#2490)", () => {
  // The embed widget used to gate this header on byokRequiresModel(provider),
  // so a visitor who pasted an OpenAI key and picked a model had the model
  // dropped on the floor. digigraph then answered on its own default — an
  // `openrouter/…` model on the shipped release config — leaving the visitor's
  // key bound, shown as active, and never billed. The provider flag says
  // whether a model is *mandatory*; it never said to discard a chosen one.
  it("forwards a chosen model for a provider whose model is optional", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      byokKey: "sk-test",
      byokProvider: "openai",
      byokModel: "gpt-4o-mini",
    });
    expect(headers.get("X-BYOK-Key")).toBe("sk-test");
    expect(headers.get("X-BYOK-Provider")).toBe("openai");
    expect(headers.get("X-BYOK-Model")).toBe("gpt-4o-mini");
  });

  it("omits X-BYOK-Model when the model is blank or whitespace", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      byokKey: "sk-test",
      byokProvider: "openai",
      byokModel: "   ",
    });
    expect(headers.get("X-BYOK-Key")).toBe("sk-test");
    expect(headers.has("X-BYOK-Model")).toBe(false);
  });

  it("sends no X-BYOK-* header at all without a key", async () => {
    const { headers } = await callPrepareSendMessagesRequest({
      byokProvider: "openai",
      byokModel: "gpt-4o-mini",
    });
    expect(headers.has("X-BYOK-Key")).toBe(false);
    expect(headers.has("X-BYOK-Provider")).toBe(false);
    expect(headers.has("X-BYOK-Model")).toBe(false);
  });
});
