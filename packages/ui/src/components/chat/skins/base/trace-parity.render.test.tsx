// @vitest-environment happy-dom
import type {
  ChatModelAdapter,
  ChatModelRunResult,
  ThreadMessageLike,
} from "@assistant-ui/react";
import { AssistantRuntimeProvider, useAui, useLocalRuntime } from "@assistant-ui/react";
import { act, useEffect, type FC } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { BaseThread } from "./thread";
import { Thread as StockThread } from "../../stock/thread.aui";
import { DigichatThread } from "../../DigichatThread";
import { TraceLocaleProvider } from "../../trace-i18n";
import { DEFAULT_DEPLOY_UI, DeployUiProvider } from "../../stock/deploy-ui-context";
import { workVisibilityForView, type ViewMode } from "../../stock/skin-types";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

/**
 * The base skin's trace groups and folds a turn exactly like the digichat
 * skin's: the same chains, headers, reasoning boxes, tool groups with their
 * counts, tool rows with their words, and the same open/closed states. Only
 * the look differs, so the comparison is on structure and text, not classes.
 * Mocked messages only.
 */

const idle: ChatModelAdapter = {
  async run() {
    return { content: [{ type: "text", text: "ok" }] };
  },
};

const user = (text: string): ThreadMessageLike => ({
  role: "user",
  content: [{ type: "text", text }],
});

/** reasoning → web search → more reasoning → two tool calls → answer. */
const DONE_TURN: ThreadMessageLike[] = [
  user("what are the opening hours?"),
  {
    role: "assistant",
    content: [
      { type: "reasoning", text: "The visitor wants opening hours; search for them." },
      {
        type: "tool-call",
        toolCallId: "t1",
        toolName: "web_search",
        argsText: '{"query":"opening hours"}',
        result: { results: [{ title: "Hours", url: "https://example.com/hours" }] },
      },
      { type: "reasoning", text: "Read the page and check the holiday notice." },
      {
        type: "tool-call",
        toolCallId: "t2",
        toolName: "web_fetch",
        argsText: '{"url":"https://example.com/hours"}',
        result: { text: "Open 9 to 5." },
      },
      {
        type: "tool-call",
        toolCallId: "t3",
        toolName: "web_fetch",
        argsText: '{"url":"https://example.com/holidays"}',
        result: { text: "Closed on public holidays." },
      },
      { type: "text", text: "We are open from 9:00 to 17:00." },
    ],
  },
];

const FAILED_TOOL: ThreadMessageLike[] = [
  user("search"),
  {
    role: "assistant",
    content: [
      {
        type: "tool-call",
        toolCallId: "f1",
        toolName: "web_search",
        argsText: '{"query":"x"}',
        result: { error: "timeout" },
        isError: true,
      },
      { type: "text", text: "The search failed." },
    ],
  },
];

/** Streams reasoning and a running tool call, then holds the turn open. */
const streaming: ChatModelAdapter = {
  async *run(): AsyncGenerator<ChatModelRunResult> {
    yield {
      content: [
        { type: "reasoning", text: "Searching for the opening hours." },
        {
          type: "tool-call",
          toolCallId: "s1",
          toolName: "web_search",
          args: { query: "opening hours" },
          argsText: '{"query":"opening hours"}',
        },
      ],
    };
    await new Promise(() => {});
  },
};

const SendOnMount: FC = () => {
  const aui = useAui();
  useEffect(() => {
    aui.thread().append({ role: "user", content: [{ type: "text", text: "hours?" }] });
  }, [aui]);
  return null;
};

type Skin = "base" | "digichat" | "stock";

let cleanup: (() => void) | undefined;
function teardown(): void {
  cleanup?.();
  cleanup = undefined;
  document.body.innerHTML = "";
}
afterEach(teardown);

async function mount(
  skin: Skin,
  opts: {
    initialMessages?: ThreadMessageLike[];
    adapter?: ChatModelAdapter;
    send?: boolean;
    locale?: string;
    view?: ViewMode;
  },
) {
  const view = opts.view ?? DEFAULT_DEPLOY_UI.view;
  const Harness: FC = () => {
    const runtime = useLocalRuntime(opts.adapter ?? idle, {
      initialMessages: opts.initialMessages ?? [],
    });
    return (
      <TraceLocaleProvider locale={opts.locale ?? "en"}>
        <DeployUiProvider value={{ ...DEFAULT_DEPLOY_UI, view }}>
          <AssistantRuntimeProvider runtime={runtime}>
            {skin === "base" ? (
              <BaseThread />
            ) : skin === "stock" ? (
              <StockThread autoFocus={false} />
            ) : (
              <DigichatThread
                placeholder="Ask"
                workVisibility={workVisibilityForView(view)}
                reasoningMode={DEFAULT_DEPLOY_UI.reasoning}
                toolCallsMode={DEFAULT_DEPLOY_UI.toolCalls}
              />
            )}
            {opts.send ? <SendOnMount /> : null}
          </AssistantRuntimeProvider>
        </DeployUiProvider>
      </TraceLocaleProvider>
    );
  };
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<Harness />);
  });
  await act(async () => {
    await new Promise((r) => setTimeout(r, 20));
  });
  cleanup = () => act(() => root.unmount());
  return host;
}

const text = (el: Element | null) => (el?.textContent ?? "").replace(/\s+/g, " ").trim();
const all = (host: HTMLElement, sel: string) => [...host.querySelectorAll<HTMLElement>(sel)];
const expanded = (el: Element) => el.getAttribute("aria-expanded") === "true";

/** What the trace shows, independent of the skin's look. */
function trace(host: HTMLElement) {
  return {
    chains: all(host, '[data-slot="aui_work-chain-trigger"]').map((t) => ({
      title: text(t),
      open: expanded(t),
    })),
    reasoning: all(host, '[data-slot="reasoning-trigger"]').map((t) => ({
      label: text(t.querySelector('[data-slot="reasoning-trigger-label"]')),
      open: expanded(t),
    })),
    toolGroups: all(host, '[data-slot="tool-group-trigger"]').map((t) => ({
      label: text(t.querySelector('[data-slot="tool-group-trigger-label"]')),
      open: expanded(t),
    })),
    toolRows: all(host, '[data-slot="tool-fallback-trigger"]').map((t) => ({
      label: text(t),
    })),
    indicators: all(host, '[data-slot="aui_assistant-working"], [data-slot="aui_loading-row"]').length,
  };
}

async function both(opts: Parameters<typeof mount>[1]) {
  const base = trace(await mount("base", opts));
  teardown();
  const digichat = trace(await mount("digichat", opts));
  teardown();
  return { base, digichat };
}

describe("base skin trace parity with the digichat skin", () => {
  for (const locale of ["en", "fr"]) {
    it(`groups a finished turn the same way (${locale})`, async () => {
      const { base, digichat } = await both({ initialMessages: DONE_TURN, locale });
      expect(base).toEqual(digichat);
      // One chain for the whole run of work, folded once the answer is in.
      expect(base.chains).toHaveLength(1);
      expect(base.chains[0]!.open).toBe(false);
      // reasoning | 1 tool call | reasoning | 2 tool calls (back-to-back).
      expect(base.reasoning).toHaveLength(2);
      expect(base.toolGroups.map((g) => g.label)).toEqual(
        locale === "fr" ? ["1 appel d’outil", "2 appels d’outils"] : ["1 tool call", "2 tool calls"],
      );
      // The folded groups do not mount their rows, in either skin.
      expect(base.toolRows).toHaveLength(0);
    });
  }

  it("names a failed tool call the same way", async () => {
    const { base, digichat } = await both({ initialMessages: FAILED_TOOL, view: "verbose" });
    expect(base).toEqual(digichat);
    expect(base.toolRows[0]!.label).toMatch(/^Failed tool/);
  });

  for (const view of ["quiet", "verbose"] as const) {
    it(`follows the ${view} view the same way`, async () => {
      const { base, digichat } = await both({ initialMessages: DONE_TURN, view });
      expect(base).toEqual(digichat);
      if (view === "verbose") {
        expect(base.chains[0]!.open).toBe(true);
        expect(base.toolRows.map((r) => r.label)).toEqual([
          "Used tool: web_search",
          "Used tool: web_fetch",
          "Used tool: web_fetch",
        ]);
      }
    });
  }

  it("streams the same way: chain, reasoning box and tool group open", async () => {
    const { base, digichat } = await both({ adapter: streaming, send: true });
    // Tool rows: the base card opens while its call runs to show the
    // arguments; the row words are the same.
    expect(base.toolRows).toEqual(digichat.toolRows);
    expect(base.chains).toEqual(digichat.chains);
    expect(base.reasoning).toEqual(digichat.reasoning);
    expect(base.toolGroups).toEqual(digichat.toolGroups);
    expect(base.chains).toHaveLength(1);
    expect(base.chains[0]!.open).toBe(true);
    expect(base.reasoning[0]!.open).toBe(true);
    expect(base.toolGroups[0]!.open).toBe(true);
    expect(base.toolRows[0]!.label).toMatch(/^Running tool: ?web_search/);
  });

  it("shows a running call's arguments in the base card", async () => {
    const host = await mount("base", { adapter: streaming, send: true });
    const row = host.querySelector('[data-slot="tool-fallback-trigger"]')!;
    expect(expanded(row)).toBe(true);
    expect(host.textContent).toContain('"query"');
  });
});

/**
 * The stock thread (expo, docs and product-page skins) draws the base skin's
 * trace (`elements/assistant-trace.aui.tsx`): same chain, reasoning boxes,
 * tool groups, tool cards and open/closed states.
 */
describe("stock thread trace parity with the base skin", () => {
  async function pair(opts: Parameters<typeof mount>[1]) {
    const base = trace(await mount("base", opts));
    teardown();
    const stock = trace(await mount("stock", opts));
    teardown();
    return { base, stock };
  }

  it("groups a finished turn under one folded work chain", async () => {
    const { base, stock } = await pair({ initialMessages: DONE_TURN });
    expect(stock.chains).toEqual(base.chains);
    expect(stock.reasoning).toEqual(base.reasoning);
    expect(stock.toolGroups).toEqual(base.toolGroups);
    expect(stock.toolRows).toEqual(base.toolRows);
    expect(stock.chains).toHaveLength(1);
    expect(stock.chains[0]!.open).toBe(false);
  });

  it("opens every card in the verbose view", async () => {
    const { base, stock } = await pair({ initialMessages: DONE_TURN, view: "verbose" });
    expect(stock.chains).toEqual(base.chains);
    expect(stock.toolRows.map((r) => r.label)).toEqual([
      "Used tool: web_search",
      "Used tool: web_fetch",
      "Used tool: web_fetch",
    ]);
  });

  it("streams with the chain, reasoning box, tool group and running card open", async () => {
    const { base, stock } = await pair({ adapter: streaming, send: true });
    expect(stock.chains).toEqual(base.chains);
    expect(stock.reasoning).toEqual(base.reasoning);
    expect(stock.toolGroups).toEqual(base.toolGroups);
    expect(stock.toolRows).toEqual(base.toolRows);
    expect(stock.chains[0]!.open).toBe(true);
  });
});
