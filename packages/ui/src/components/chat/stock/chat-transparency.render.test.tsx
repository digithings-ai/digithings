// @vitest-environment happy-dom
import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { act, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { DigichatThread } from "../DigichatThread";
import { BaseThread } from "../skins/base/thread";
import { backendNoticeOf } from "./chat-notice";
import { highlightJson, tokenizeJson } from "./json-view";
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

const TOOL_CAP_TURN: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "how many tables?" }] },
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "datatap__list_tables",
        args: { schema: "public" },
        argsText: '{"schema":"public"}',
        result: { tables: ["orders"] },
      },
      {
        type: "data",
        name: "notice",
        data: {
          tone: "status",
          message: "Tool-call limit reached (2 this turn). Answering from the results gathered so far.",
        },
      },
      { type: "text", text: "The orders table is the one that holds them." },
    ],
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
    // Long block: a max-height scroll area, no expand button (Chris, 21 Oct).
    const pre = args!.querySelector<HTMLElement>('[data-slot="tool-fallback-args-json"]')!;
    expect(pre.className).toMatch(/\bmax-h-72\b/);
    expect(pre.className).toMatch(/\boverflow-auto\b/);
    expect(host.querySelector('[data-slot$="-toggle"]')).toBeNull();
    expect(host.textContent).not.toMatch(/Show all|Show full error/);
    // Error after the arguments, in the red error notice, whole.
    expect(args!.compareDocumentPosition(error!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(error!.getAttribute("data-tone")).toBe("error");
    expect(error!.textContent).toContain("'pageSize' must be a string");
    expect(error!.textContent).toContain("McpServer.handle (server.ts:203)");
    // The traceback sits in a scroll area, never behind a fold.
    expect(error!.querySelector("details")).toBeNull();
    const detail = error!.querySelector<HTMLElement>('[data-slot="chat-notice-detail"]')!;
    expect(detail.className).toMatch(/\bmax-h-72\b.*\boverflow-auto\b/);
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
    expect(root!.querySelector("details")).toBeNull();
    unmount();
  });

  it("renders a backend status notice in the neutral tone", async () => {
    const { host, unmount } = await mount(Skin, STATUS_TURN);
    const notice = host.querySelector<HTMLElement>('[data-slot="chat-notice"][data-tone="status"]');
    expect(notice?.textContent).toContain("Waiting for model capacity — retrying in 8s");
    expect(notice?.getAttribute("role")).toBe("status");
    unmount();
  });

  it("keeps a tool-call limit notice visible beside a folded tool chain", async () => {
    const { host, unmount } = await mount(Skin, TOOL_CAP_TURN);
    const notice = host.querySelector<HTMLElement>('[data-slot="chat-notice"][data-tone="status"]');
    expect(notice?.textContent).toContain("Tool-call limit reached (2 this turn)");
    expect(notice?.getAttribute("role")).toBe("status");
    // The answer is on the page without opening the work chain. The notice
    // sits with it, not inside the collapsed tool group.
    expect(host.textContent).toContain("The orders table is the one that holds them.");
    const chain = host.querySelector('[data-slot="aui_chain-of-thought"]');
    // The gallery skin folds tool calls into the work chain. The notice has
    // to stay outside that chain or it disappears with the fold.
    if (_name === "gallery skin") {
      expect(chain).toBeTruthy();
      expect(chain!.contains(notice)).toBe(false);
    } else if (chain && notice) {
      expect(chain.contains(notice)).toBe(false);
    }
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

  it("tokenizes keys, strings, escapes and scalars in one pass", () => {
    expect(tokenizeJson('{"a" : "x\\"y", "n": -1.5e3, "t": true, "z": null, "w": "truex"}')).toEqual([
      "{",
      { kind: "key", text: '"a"', colon: " :" },
      " ",
      { kind: "string", text: '"x\\"y"' },
      ", ",
      { kind: "key", text: '"n"', colon: ":" },
      " ",
      { kind: "number", text: "-1.5e3" },
      ", ",
      { kind: "key", text: '"t"', colon: ":" },
      " ",
      { kind: "boolean", text: "true" },
      ", ",
      { kind: "key", text: '"z"', colon: ":" },
      " ",
      { kind: "null", text: "null" },
      ", ",
      { kind: "key", text: '"w"', colon: ":" },
      " ",
      { kind: "string", text: '"truex"' },
      "}",
    ]);
    expect(tokenizeJson("nullable trueish")).toEqual(["nullable trueish"]);
  });

  it("scans a quote followed by long whitespace in linear time", () => {
    const text = '"' + " ".repeat(100_000);
    const started = performance.now();
    const tokens = tokenizeJson(text);
    expect(performance.now() - started).toBeLessThan(500);
    expect(tokens).toEqual([{ kind: "string", text }]);
  });

  it("scans an unterminated string in linear time and keeps every character", () => {
    const text = '"' + '\\"'.repeat(50_000);
    const started = performance.now();
    const nodes = highlightJson(text);
    expect(performance.now() - started).toBeLessThan(500);
    const host = document.createElement("div");
    const root = createRoot(host);
    act(() => root.render(<pre>{nodes}</pre>));
    expect(host.textContent).toBe(text);
    act(() => root.unmount());
  });
});
