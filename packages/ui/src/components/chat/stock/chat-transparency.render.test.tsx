// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "../DigichatThread";
import { BaseThread } from "../skins/base/thread";
import { backendNoticeOf } from "./chat-notice";
import { highlightJson } from "./json-view";
import { toolErrorText } from "./tool-fallback.aui";

/**
 * DIG-4459 chat transparency: full tool arguments, the tool's error under
 * them (never instead of them), and one boxed notice family for errors and
 * status lines. Mocked messages only.
 */
const adapter: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const LONG_ARGS = {
  collectorId: "c-7f3a",
  pageSize: 20,
  includeArchived: false,
  cursor: null,
  filters: Array.from({ length: 30 }, (_, i) => ({ field: `mailbox_${i}`, op: "eq", value: `user${i}@example.com` })),
};

const TRACEBACK = [
  "ToolError: 'pageSize' must be a string, but a number was provided.",
  "  at ToolArguments.validate (tool-arguments.ts:88)",
  "  at ToolDispatch.run (tool-dispatch.ts:41)",
  "  at McpServer.handle (server.ts:203)",
].join("\n");

const FAILED_TOOL: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "list reports" }] },
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "list_collector_reports",
        argsText: JSON.stringify(LONG_ARGS),
        result: { error: TRACEBACK },
        isError: true,
      },
    ],
  },
];

const ERRORED_TURN: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "hi" }] },
  {
    role: "assistant",
    content: [{ type: "text", text: "" }],
    status: {
      type: "incomplete",
      reason: "error",
      error: "get_collector_report_accounts: Response exceeded the token limit (250000 tokens per minute).",
    },
  },
];

const STATUS_TURN: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "hi" }] },
  {
    role: "assistant",
    content: [
      { type: "data", name: "notice", data: { message: "Waiting for model capacity — retrying in 8s" } },
      { type: "text", text: "Partial answer" },
    ],
  },
];

async function mount(Skin: FC, initialMessages: ThreadMessageLike[]) {
  const Harness: FC = () => {
    const runtime = useLocalRuntime(adapter, { initialMessages });
    return (
      <AssistantRuntimeProvider runtime={runtime}>
        <Skin />
      </AssistantRuntimeProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  await act(async () => {});
  return { host, unmount: () => act(() => root.unmount()) };
}

async function openTool(host: HTMLElement) {
  // Open the work chain / tool group / tool row, outermost first.
  for (let i = 0; i < 6; i++) {
    const closed = [...host.querySelectorAll<HTMLElement>('[aria-expanded="false"]')].filter((el) =>
      /work-chain-trigger|tool-group-trigger|tool-fallback-trigger|aui-tool-group|aui-tool-fallback/.test(
        `${el.getAttribute("data-slot") ?? ""} ${el.className}`,
      ),
    );
    if (closed.length === 0) break;
    await act(async () => closed[0]!.click());
  }
  expect(host.querySelector('[data-slot="tool-fallback-trigger"]')).toBeTruthy();
}

const Gallery: FC = () => <DigichatThread placeholder="Ask digichat…" />;

afterEach(() => {
  document.body.replaceChildren();
});

describe.each([
  ["gallery skin", Gallery],
  ["base skin", BaseThread as FC],
])("chat transparency (%s)", (_name, Skin) => {
  it("shows the full pretty-printed arguments and the error under them", async () => {
    const { host, unmount } = await mount(Skin, FAILED_TOOL);
    await openTool(host);
    const args = host.querySelector<HTMLElement>('[data-slot="tool-fallback-args"]');
    const error = host.querySelector<HTMLElement>('[data-slot="tool-fallback-error"]');
    expect(args).toBeTruthy();
    expect(error).toBeTruthy();
    // Nothing cut: every filter row is in the DOM, pretty-printed.
    const json = args!.querySelector("pre")!.textContent ?? "";
    expect(json).toContain('"mailbox_29"');
    expect(json).toContain('\n  "pageSize": 20,');
    // Long block: capped with its own toggle, not truncated.
    expect(args!.querySelector('[data-slot="tool-fallback-args-json-toggle"]')?.textContent).toMatch(/Show all/);
    // Error after the arguments, in the red error notice, whole.
    expect(args!.compareDocumentPosition(error!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(error!.getAttribute("data-tone")).toBe("error");
    expect(error!.textContent).toContain("'pageSize' must be a string");
    expect(error!.textContent).toContain("McpServer.handle (server.ts:203)");
    unmount();
  });

  it("renders a failed turn as a boxed error notice with the backend's message", async () => {
    const { host, unmount } = await mount(Skin, ERRORED_TURN);
    const root = host.querySelector<HTMLElement>(".aui-message-error-root");
    expect(root).toBeTruthy();
    expect(root!.getAttribute("data-tone")).toBe("error");
    expect(root!.getAttribute("role")).toBe("alert");
    expect(root!.textContent).toContain("Response exceeded the token limit (250000 tokens per minute).");
    expect(root!.textContent).toMatch(/Retry/);
    unmount();
  });

  it("renders a backend status notice in the neutral tone", async () => {
    const { host, unmount } = await mount(Skin, STATUS_TURN);
    const notice = host.querySelector<HTMLElement>('[data-slot="chat-notice"][data-tone="status"]');
    expect(notice?.textContent).toContain("Waiting for model capacity — retrying in 8s");
    expect(notice?.getAttribute("role")).toBe("status");
    unmount();
  });
});

describe("notice helpers", () => {
  it("reads notices only from notice/status parts with a message", () => {
    expect(backendNoticeOf({ type: "data", name: "connection", data: { message: "x" } })).toBeNull();
    expect(backendNoticeOf({ type: "data", name: "status", data: { status: "started" } })).toBeNull();
    expect(backendNoticeOf({ type: "data", name: "notice", data: { message: "Hi", tone: "error" } })).toEqual({
      tone: "error",
      message: "Hi",
    });
  });

  it("keeps tool errors whole and pretty-prints JSON ones", () => {
    expect(toolErrorText(TRACEBACK)).toBe(TRACEBACK);
    expect(toolErrorText({ code: 400, message: "bad" })).toBe('{\n  "code": 400,\n  "message": "bad"\n}');
    expect(toolErrorText('{"a":1}')).toBe('{\n  "a": 1\n}');
    expect(toolErrorText("")).toBeNull();
  });

  it("highlights JSON tokens without dropping text", () => {
    const text = '{\n  "a": "b",\n  "n": 1,\n  "t": true,\n  "z": null\n}';
    const host = document.createElement("div");
    const root = createRoot(host);
    act(() => root.render(<pre>{highlightJson(text)}</pre>));
    expect(host.textContent).toBe(text);
    expect(host.querySelectorAll('[data-json="key"]').length).toBe(4);
    expect(host.querySelector('[data-json="string"]')?.textContent).toBe('"b"');
    expect(host.querySelector('[data-json="number"]')?.textContent).toBe("1");
    act(() => root.unmount());
  });
});
